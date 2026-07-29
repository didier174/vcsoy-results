"""
Construit le dictionnaire des données disponibles pour remplir les
balises {{ Nom de la balise }} du modèle de rapport d'étude, pour un
participant donné.

Conventions de portée (scope), communes à la plupart des balises :
  vous        : le participant lui-même
  categorie   : tous les participants de la même catégorie (lui compris)
  tous        : tous les participants de l'édition ayant au moins un test
  laureats    : les lauréats de catégorie (1er de catégorie ET note finale
                consolidée >= 11,5/20 — voir scoring.MIN_WINNER_SCORE)
  non_laureats: les participants testés qui ne sont pas lauréats

Important : les lauréats dépendent de TOUS les résultats de l'édition, pas
seulement de ce participant. Pour éviter de recharger et retraiter tous les
tests de l'édition à CHAQUE génération de rapport (source d'un dépassement
mémoire sur Render dès que l'édition grossit un peu), les portées "tous" /
"categorie" / "laureats" / "non_laureats" sont précalculées une seule fois
et mises en cache (voir report_cache.py), rafraîchi quand l'utilisateur
relance « Liste des lauréats ». Seule la portée "vous" (les tests du seul
participant courant, toujours petite) est calculée ici, en direct.
"""

import re

from app.results.presentation import CHANNEL_ORDER
from app.results.scoring import (
    compute_test_score,
    compute_criterion_stats,
    is_test_completed,
    CRITERIA_BY_CHANNEL,
)

DAY_RAW_BY_KEY = {
    "lundi": "Monday", "mardi": "Tuesday", "mercredi": "Wednesday",
    "jeudi": "Thursday", "vendredi": "Friday", "samedi": "Saturday",
}
HALF_RAW_BY_KEY = {"matin": "AM", "apresmidi": "PM"}

CACHE_SCOPES = ("tous", "categorie", "laureats", "non_laureats")


def _fmt_note(value):
    return "—" if value is None else f"{value:.2f}".replace(".", ",")


def _fmt_pct(value):
    return "—" if value is None else f"{round(value)}%"


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def _channel_note20_list(channel, tests):
    scores = [compute_test_score(channel, t.raw_data or {}) for t in tests if t.channel == channel]
    return [s["note_20"] for s in scores if s is not None]


def _parse_minsec(raw_data, min_key, sec_key):
    """None si les deux colonnes sont vides (ex. Code 10 Navig Time IVR
    quand l'appel n'est jamais passé par un SVI) : à ne pas confondre avec
    une vraie durée de 0 seconde, qui fausserait la moyenne à la baisse."""
    m, s = raw_data.get(min_key), raw_data.get(sec_key)
    if m in (None, "") and s in (None, ""):
        return None
    try:
        m = float(m) if m not in (None, "") else 0.0
        s = float(s) if s not in (None, "") else 0.0
    except (TypeError, ValueError):
        return None
    return m * 60 + s


def _format_duration(total_seconds):
    if total_seconds is None:
        return "—"
    total_seconds = round(total_seconds)
    h, rem = divmod(total_seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m}min" if m else f"{h}h"
    if m:
        return f"{m}min{s}sec" if s else f"{m}min"
    return f"{s}sec"


def _phone_duration(raw_data, metric):
    if metric == "acces":
        return _parse_minsec(raw_data, "Code 10 Navig  Time IVR MIN", "Code 10 Navig  Time IVR SEC")
    if metric == "prise":
        return _parse_minsec(raw_data, "Code 9 Time to Answer MIN", "Code 9 Time to Answer SEC")
    if metric == "totale":
        # Stocké en secondes (float) : voir validation._json_safe, qui convertit
        # tout datetime.timedelta lu depuis Excel via .total_seconds().
        return _duration_like_seconds(raw_data, "Call Duration")
    return None


def _mail_business_hours(raw_data):
    value = raw_data.get("Business hours")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _duration_like_seconds(raw_data, key):
    """
    Une durée Excel (ex. 'Test Duration', 'Respond Time', 'Call Duration')
    arrive sous deux formes possibles selon le format de la cellule source,
    toutes deux passées par validation._json_safe au chargement du fichier :
    - cellule "durée" (datetime.timedelta) -> nombre de secondes (float) ;
    - cellule "heure" (datetime.time, cas le plus courant en pratique pour
      ces colonnes) -> chaîne "HH:MM:SS" (.isoformat()), à reconvertir ici.
    Retourne None si absente/illisible.
    """
    value = raw_data.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, str) and re.match(r"^\d{1,2}:\d{2}:\d{2}", value):
        h, m, s = (int(p) for p in value.split(":")[:3])
        return h * 3600 + m * 60 + s
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_clicks(raw_data):
    """Le nombre de clics web n'est pas dans une colonne dédiée : il est
    écrit en toutes lettres dans 'Code 5 Obs' (ex. '6 clicks to find the
    answer', confirmé). On extrait le premier nombre entier trouvé."""
    text = raw_data.get("Code 5 Obs")
    if not text:
        return None
    match = re.search(r"\d+", str(text))
    return int(match.group(0)) if match else None


def _within_hours(raw_data, key, hours):
    seconds = _duration_like_seconds(raw_data or {}, key)
    return seconds is not None and seconds <= hours * 3600


def _slow_pickup(raw_data):
    try:
        return float(raw_data.get("code 8 Answered Call Time MIN")) > 4
    except (TypeError, ValueError):
        return False


def _bucket_stats(channel, tests, day=None, half=None):
    filtered = [
        t for t in tests
        if (day is None or (t.raw_data or {}).get("Day") == DAY_RAW_BY_KEY[day])
        and (half is None or (t.raw_data or {}).get("Périod") == HALF_RAW_BY_KEY[half])
    ]
    note20 = _channel_note20_list(channel, filtered)
    pct = (
        round(100 * sum(1 for t in filtered if is_test_completed(channel, t.raw_data or {})) / len(filtered))
        if filtered else None
    )
    return _avg(note20), pct


def compute_scope_values(tests):
    """
    tests : liste de TestResult, déjà filtrée sur le périmètre voulu (un
    seul participant pour "vous", ou tous les participants d'une portée
    pour le cache — voir report_cache.py).

    Retourne un dict de valeurs SANS suffixe de portée (ex. "C1 phone nb",
    pas "C1 phone nb tous") : c'est l'appelant (build_participant_placeholders
    ou compute_edition_cache) qui combine ces valeurs avec le bon suffixe de
    portée selon le contexte, les deux appelants ayant des conventions de
    nommage différentes pour la même donnée sous-jacente.
    """
    v = {}
    for channel in CHANNEL_ORDER:
        for code in CRITERIA_BY_CHANNEL[channel]:
            # Confirmé : le détail par critère (nb/note/%) ne compte que les
            # tests "propres" (QS = Completed, là où cette colonne existe),
            # contrairement au "Total" du canal qui compte tous les tests
            # tentés.
            stats = compute_criterion_stats(
                channel, code,
                [t.raw_data for t in tests if t.channel == channel and is_test_completed(channel, t.raw_data or {})],
            )
            v[f"C{code} {channel} nb"] = stats["nb"]
            v[f"C{code} {channel} note"] = _fmt_note(stats["note"])
            v[f"C{code} {channel} pct"] = _fmt_pct(stats["pct"])

        channel_tests = [t for t in tests if t.channel == channel]
        note20_list = _channel_note20_list(channel, channel_tests)
        v[f"Total {channel} note"] = _fmt_note(_avg(note20_list))
        v[f"Total {channel} nb"] = len(note20_list)

        completed = [t for t in channel_tests if is_test_completed(channel, t.raw_data or {})]
        completed_note20 = _channel_note20_list(channel, completed)
        v[f"Total QS {channel} note"] = _fmt_note(_avg(completed_note20))
        v[f"Total QS {channel} nb"] = len(completed_note20)

    # -- Téléphone : qualité de service (taux de tests complétés)
    phone_tests = [t for t in tests if t.channel == "phone"]
    pct = (
        round(100 * sum(1 for t in phone_tests if is_test_completed("phone", t.raw_data or {})) / len(phone_tests))
        if phone_tests else None
    )
    v["QS phone pct"] = _fmt_pct(pct)
    v["coupures avant phone"] = sum(
        1 for t in phone_tests if str((t.raw_data or {}).get("Call Drop", "")).strip().lower() in ("1", "oui", "yes", "true")
    )
    v["prise charge sup4min phone"] = sum(1 for t in phone_tests if _slow_pickup(t.raw_data or {}))

    # -- Téléphone : temps moyens (accès / prise en charge / durée totale)
    for metric in ("acces", "prise", "totale"):
        durations = [_phone_duration(t.raw_data or {}, metric) for t in phone_tests]
        v[f"temps {metric} phone"] = _format_duration(_avg(durations))

    # -- Téléphone : répartition jour de la semaine / matin-après-midi
    for day in DAY_RAW_BY_KEY:
        note, pct = _bucket_stats("phone", phone_tests, day=day)
        v[f"note jour {day} phone"] = _fmt_note(note)
        v[f"pct jour {day} phone"] = _fmt_pct(pct)
    for half in HALF_RAW_BY_KEY:
        note, pct = _bucket_stats("phone", phone_tests, half=half)
        v[f"note horaire {half} phone"] = _fmt_note(note)
        v[f"pct horaire {half} phone"] = _fmt_pct(pct)

    # -- Mail : taux de réponse / délai de réponse / cas d'inaccessibilité
    mail_tests = [t for t in tests if t.channel == "mail"]
    if mail_tests:
        repondus = sum(1 for t in mail_tests if (t.raw_data or {}).get("Return date"))
        pct_reponse = round(100 * repondus / len(mail_tests))
    else:
        pct_reponse = None
    v["taux reponse mail"] = _fmt_pct(pct_reponse)

    delais_heures = [_mail_business_hours(t.raw_data or {}) for t in mail_tests]
    delais_heures = [d for d in delais_heures if d is not None]
    avg_heures = _avg(delais_heures)
    v["delai reponse mail"] = _format_duration(avg_heures * 3600 if avg_heures is not None else None)

    v["reponses non recues mail"] = sum(1 for t in mail_tests if not (t.raw_data or {}).get("Return date"))
    v["reponses recues sup2j mail"] = sum(
        1 for t in mail_tests
        if _mail_business_hours(t.raw_data or {}) is not None and _mail_business_hours(t.raw_data or {}) > 16
    )

    # -- Internet : taux de disponibilité / note et clics moyens
    web_tests = [t for t in tests if t.channel == "web"]
    # Aucune colonne de statut d'échec confirmée pour Internet à ce jour :
    # tous les tests valides sont considérés disponibles (hypothèse à
    # vérifier en conditions réelles).
    v["taux disponibilite web"] = _fmt_pct(100.0 if web_tests else None)
    clicks = [_extract_clicks(t.raw_data or {}) for t in web_tests]
    v["clics web"] = _fmt_note(_avg(clicks))

    # -- Réseaux sociaux : taux de réponse (sous 12h ouvrées) / délai de réponse.
    # "Test Duration" (confirmé) est un temps réel écoulé, pas des heures
    # ouvrées à proprement parler (contrairement à "Business hours" pour le
    # mail) : on le compare néanmoins directement au seuil de 12h, faute de
    # colonne équivalente convertie en heures ouvrées pour ce canal.
    rs_tests = [t for t in tests if t.channel == "rs"]
    durations = [_duration_like_seconds(t.raw_data or {}, "Test Duration") for t in rs_tests]
    durations = [d for d in durations if d is not None]
    pct = (
        round(100 * sum(1 for t in rs_tests if _within_hours(t.raw_data, "Test Duration", 12)) / len(rs_tests))
        if rs_tests else None
    )
    v["taux reponse rs"] = _fmt_pct(pct)
    v["delai reponse rs"] = _format_duration(_avg(durations))

    # -- Chat : taux de conversations abouties / temps moyens.
    # Aucune règle de calcul du "taux de conversations abouties" n'a été
    # précisée : on utilise ici, à titre d'hypothèse à valider, la
    # proportion de tests exploitables (au moins un critère valide) parmi
    # tous les tests chat de la portée, comme proxy d'une conversation
    # effectivement aboutie.
    chat_tests = [t for t in tests if t.channel == "chat"]
    if chat_tests:
        aboutis = sum(1 for t in chat_tests if compute_test_score("chat", t.raw_data or {}) is not None)
        pct = round(100 * aboutis / len(chat_tests))
    else:
        pct = None
    v["taux conv abouties chat"] = _fmt_pct(pct)

    demandes = [_duration_like_seconds(t.raw_data or {}, "Respond Time") for t in chat_tests]
    demandes = [d for d in demandes if d is not None]
    v["temps demande chat"] = _format_duration(_avg(demandes))

    convs = [_duration_like_seconds(t.raw_data or {}, "Test Duration") for t in chat_tests]
    convs = [d for d in convs if d is not None]
    v["temps conv chat"] = _format_duration(_avg(convs))

    v["interactions non repondues chat"] = sum(
        1 for t in chat_tests if _duration_like_seconds(t.raw_data or {}, "Respond Time") is None
    )

    return v


def _apply_scope_suffix(values, scope_values, scope):
    """Combine les valeurs (sans suffixe) d'une portée dans le dict final
    `values`, en respectant les conventions de nommage EXACTES du modèle
    (irrégulières selon les sections — héritées telles quelles)."""
    for channel in CHANNEL_ORDER:
        if scope in ("vous", "categorie", "tous"):
            for code in CRITERIA_BY_CHANNEL[channel]:
                values[f"C{code} {channel} note {scope}"] = scope_values[f"C{code} {channel} note"]
                values[f"C{code} {channel} pct {scope}"] = scope_values[f"C{code} {channel} pct"]

        if scope in ("vous", "categorie", "tous"):
            values[f"Total {channel} note {scope}"] = scope_values[f"Total {channel} note"]
            values[f"Total QS {channel} note {scope}"] = scope_values[f"Total QS {channel} note"]
            if scope == "tous":
                # Alias sans le préfixe "Total", utilisé dans le texte de
                # synthèse par canal (diapositives 6-8).
                values[f"{channel} note tous"] = scope_values[f"Total {channel} note"]
        if scope in ("laureats", "non_laureats"):
            suffix = "laureats" if scope == "laureats" else "non laureats"
            values[f"{channel} note {suffix}"] = scope_values[f"Total {channel} note"]
            if scope == "laureats":
                values[f"Total {channel} note laureats"] = scope_values[f"Total {channel} note"]

    if scope in ("vous", "categorie", "tous", "laureats"):
        values[f"QS phone pct {scope}"] = scope_values["QS phone pct"]
        for metric in ("acces", "prise", "totale"):
            values[f"temps {metric} phone {scope}"] = scope_values[f"temps {metric} phone"]
        for day in DAY_RAW_BY_KEY:
            values[f"note jour {day} phone {scope}"] = scope_values[f"note jour {day} phone"]
            values[f"pct jour {day} phone {scope}"] = scope_values[f"pct jour {day} phone"]
        for half in HALF_RAW_BY_KEY:
            values[f"note horaire {half} phone {scope}"] = scope_values[f"note horaire {half} phone"]
            values[f"pct horaire {half} phone {scope}"] = scope_values[f"pct horaire {half} phone"]
        values[f"taux reponse mail {scope}"] = scope_values["taux reponse mail"]
        values[f"delai reponse mail {scope}"] = scope_values["delai reponse mail"]
        values[f"taux disponibilite web {scope}"] = scope_values["taux disponibilite web"]
        values[f"clics web {scope}"] = scope_values["clics web"]
        values[f"taux conv abouties chat {scope}"] = scope_values["taux conv abouties chat"]
        values[f"temps demande chat {scope}"] = scope_values["temps demande chat"]
        values[f"temps conv chat {scope}"] = scope_values["temps conv chat"]

    if scope in ("vous", "categorie", "tous", "laureats", "non_laureats"):
        if scope == "non_laureats":
            values["rs note pct non laureats"] = scope_values["taux reponse rs"]
        else:
            values[f"taux reponse rs {scope}"] = scope_values["taux reponse rs"]
            values[f"delai reponse rs {scope}"] = scope_values["delai reponse rs"]


def build_participant_placeholders(participant, edition_id, cache, all_tests=None):
    """
    cache : dict retourné par report_cache.get_fresh_edition_cache (portées
    "tous"/"categorie" par catégorie/"laureats"/"non_laureats", déjà
    calculées et rafraîchies quand l'utilisateur relance « Liste des
    lauréats »).
    all_tests : les tests du SEUL participant courant (pas de toute
    l'édition) ; rechargés ici si absents.
    """
    from app.models import TestResult
    from app.results.scoring import build_compilation_rows

    values = {
        "Participant": participant.participant_name,
        "Code participant": participant.code,
        "Catégorie": participant.category_label(),
    }

    if all_tests is None:
        all_tests = TestResult.query.filter_by(edition_id=edition_id, participant_id=participant.id).all()

    # La note consolidée et les notes par canal du participant ne dépendent
    # QUE de ses propres tests (aucune donnée croisée avec les autres
    # participants) : calculées ici en direct plutôt que mises en cache,
    # pour ne pas faire grossir le cache avec une entrée par participant.
    own_row = build_compilation_rows([participant], all_tests)[0]
    for channel in CHANNEL_ORDER:
        channel_data = own_row["channels"][channel]
        values[f"Nb tests canal {channel}"] = channel_data["nb_test"]
        values[f"Note sur 20 canal {channel}"] = (
            channel_data["note_20"] if channel_data["note_20"] is not None else "—"
        )
    values["Note consolidée"] = (
        own_row["consolidated_score"] if own_row["consolidated_score"] is not None else "—"
    )

    # ------------------------------------------------------------ Portée "vous"
    vous_values = compute_scope_values(all_tests)
    for channel in CHANNEL_ORDER:
        for code in CRITERIA_BY_CHANNEL[channel]:
            values[f"C{code} {channel} nb"] = vous_values[f"C{code} {channel} nb"]
        values[f"Total {channel} nb"] = vous_values[f"Total {channel} nb"]
        values[f"Total QS {channel} nb"] = vous_values[f"Total QS {channel} nb"]
    values["coupures avant phone vous"] = vous_values["coupures avant phone"]
    values["prise charge sup4min phone vous"] = vous_values["prise charge sup4min phone"]
    values["reponses non recues mail vous"] = vous_values["reponses non recues mail"]
    values["reponses recues sup2j mail vous"] = vous_values["reponses recues sup2j mail"]
    values["interactions non repondues chat vous"] = vous_values["interactions non repondues chat"]
    _apply_scope_suffix(values, vous_values, "vous")

    # ---------------------------------------------- Portées mises en cache
    category_key = str(participant.category_id)
    for scope in CACHE_SCOPES:
        scope_values = (
            cache["by_category"].get(category_key, cache["empty_scope"])
            if scope == "categorie"
            else cache[scope]
        )
        _apply_scope_suffix(values, scope_values, scope)

    # ---------------------------------------------------------- Note globale
    values["Global note tous"] = cache["global_note"]["tous"]
    values["Global note categorie"] = cache["global_note"]["by_category"].get(category_key, "—")
    values["Global note laureats"] = cache["global_note"]["laureats"]
    values["Global note non laureats"] = cache["global_note"]["non_laureats"]

    # ------------------------------------------- Plage min/max (classement)
    # cache["ranking"][scope] : tous les participants TESTÉS de l'édition
    # (toutes catégories), déjà triés décroissant (voir report_cache.py) —
    # le min/max est donc simplement le dernier/premier élément.
    ranking = cache.get("ranking", {})
    global_scores = [r["score"] for r in ranking.get("global", [])]
    values["Global note min"] = _fmt_note(global_scores[-1]) if global_scores else "—"
    values["Global note max"] = _fmt_note(global_scores[0]) if global_scores else "—"
    for channel in CHANNEL_ORDER:
        channel_scores = [r["score"] for r in ranking.get(channel, [])]
        values[f"{channel} note min"] = _fmt_note(channel_scores[-1]) if channel_scores else "—"
        values[f"{channel} note max"] = _fmt_note(channel_scores[0]) if channel_scores else "—"

    return values
