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
seulement de ce participant — voir build_category_winners. L'utilisateur
doit donc avoir chargé l'ensemble des fichiers de résultats de l'édition
avant de générer un rapport d'étude (rappelé dans l'interface, voir
reports/routes.py).
"""

import re
from collections import defaultdict

from app.models import TestResult, Participant
from app.results.presentation import CHANNEL_ORDER, extract_codes
from app.results.scoring import (
    build_compilation_rows,
    build_category_winners,
    compute_test_score,
    compute_criterion_stats,
    compute_importance,
    is_test_completed,
    CRITERIA_BY_CHANNEL,
)

DAY_RAW_BY_KEY = {
    "lundi": "Monday", "mardi": "Tuesday", "mercredi": "Wednesday",
    "jeudi": "Thursday", "vendredi": "Friday", "samedi": "Saturday",
}
HALF_RAW_BY_KEY = {"matin": "AM", "apresmidi": "PM"}

SCOPE_KEYS = ("vous", "categorie", "tous")


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


def build_participant_placeholders(participant, edition_id, all_participants=None, all_tests=None, rows=None):
    """
    all_participants/all_tests/rows : déjà calculés par l'appelant (voir
    reports/routes.py) pour éviter de refaire ces requêtes/calculs coûteux
    (tous les tests de l'édition) plusieurs fois dans la même requête HTTP
    — recalculés ici uniquement si absents, pour rester utilisable seule.
    """
    values = {
        "Participant": participant.participant_name,
        "Code participant": participant.code,
        "Catégorie": participant.category_label(),
    }

    if all_participants is None:
        all_participants = Participant.query.filter_by(edition_id=edition_id).all()
    if all_tests is None:
        all_tests = TestResult.query.filter_by(edition_id=edition_id).all()
    if rows is None:
        rows = build_compilation_rows(all_participants, all_tests)
    row_by_pid = {r["participant_id"]: r for r in rows}
    own_row = row_by_pid.get(participant.id)

    if own_row:
        for channel in CHANNEL_ORDER:
            channel_data = own_row["channels"][channel]
            values[f"Nb tests canal {channel}"] = channel_data["nb_test"]
            values[f"Note sur 20 canal {channel}"] = (
                channel_data["note_20"] if channel_data["note_20"] is not None else "—"
            )
        values["Note consolidée"] = own_row["consolidated_score"] if own_row["consolidated_score"] is not None else "—"

    # ------------------------------------------------------------ Portées
    winners = build_category_winners(rows)
    laureat_ids = {w["winner_participant_id"] for w in winners}
    tested_ids = {r["participant_id"] for r in rows if r["nb_tests_total"] > 0}
    non_laureat_ids = tested_ids - laureat_ids
    category_mate_ids = {p.id for p in all_participants if p.category_id == participant.category_id}

    tests_by_participant = defaultdict(list)
    for t in all_tests:
        if t.participant_id:
            tests_by_participant[t.participant_id].append(t)

    def tests_for(participant_ids, channel=None):
        result = []
        for pid in participant_ids:
            for t in tests_by_participant.get(pid, []):
                if channel is None or t.channel == channel:
                    result.append(t)
        return result

    scope_ids = {
        "vous": {participant.id},
        "categorie": category_mate_ids,
        "tous": tested_ids,
        "laureats": laureat_ids,
        "non_laureats": non_laureat_ids,
    }

    # ------------------------------------------- Tableaux détaillés par critère
    #
    # Confirmé : le détail par critère (nb/note/%) ne compte que les tests
    # "propres" (QS = Completed, là où cette colonne existe), contrairement
    # au "Total" du canal qui lui compte tous les tests tentés — c'est pour
    # ça que le modèle d'origine affichait un nb différent par critère (123)
    # et sur la ligne "Total" (130).
    for channel in CHANNEL_ORDER:
        for code in CRITERIA_BY_CHANNEL[channel]:
            stats = {
                scope: compute_criterion_stats(
                    channel, code,
                    [
                        t.raw_data for t in tests_for(scope_ids[scope], channel)
                        if is_test_completed(channel, t.raw_data or {})
                    ],
                )
                for scope in SCOPE_KEYS
            }
            values[f"C{code} {channel} nb"] = stats["vous"]["nb"]
            for scope in SCOPE_KEYS:
                values[f"C{code} {channel} note {scope}"] = _fmt_note(stats[scope]["note"])
                values[f"C{code} {channel} pct {scope}"] = _fmt_pct(stats[scope]["pct"])

        # ------------------------------------------------- Totaux par canal
        for scope in SCOPE_KEYS:
            tests = tests_for(scope_ids[scope], channel)
            note20_list = _channel_note20_list(channel, tests)
            values[f"Total {channel} note {scope}"] = _fmt_note(_avg(note20_list))
            if scope == "vous":
                values[f"Total {channel} nb"] = len(note20_list)

            completed = [t for t in tests if is_test_completed(channel, t.raw_data or {})]
            completed_note20 = _channel_note20_list(channel, completed)
            values[f"Total QS {channel} note {scope}"] = _fmt_note(_avg(completed_note20))
            if scope == "vous":
                values[f"Total QS {channel} nb"] = len(completed_note20)

            if scope == "tous":
                # Alias sans le préfixe "Total", utilisé dans le texte de
                # synthèse par canal (diapositives 6-8).
                values[f"{channel} note tous"] = values[f"Total {channel} note tous"]

        for scope in ("laureats", "non_laureats"):
            tests = tests_for(scope_ids[scope], channel)
            note20_list = _channel_note20_list(channel, tests)
            suffix = "laureats" if scope == "laureats" else "non laureats"
            values[f"{channel} note {suffix}"] = _fmt_note(_avg(note20_list))
            if scope == "laureats":
                values[f"Total {channel} note laureats"] = values[f"{channel} note laureats"]

    # ---------------------------------------------------------- Note globale
    def avg_consolidated(participant_ids):
        scores = [
            row_by_pid[pid]["consolidated_score"]
            for pid in participant_ids
            if pid in row_by_pid and row_by_pid[pid]["consolidated_score"] is not None
        ]
        return _avg(scores)

    values["Global note tous"] = _fmt_note(avg_consolidated(tested_ids))
    values["Global note categorie"] = _fmt_note(avg_consolidated(category_mate_ids))
    values["Global note laureats"] = _fmt_note(avg_consolidated(laureat_ids))
    values["Global note non laureats"] = _fmt_note(avg_consolidated(non_laureat_ids))

    # ------------------------------------------------------- Accessibilité

    # -- Téléphone : qualité de service (taux de tests complétés)
    for scope in ("vous", "categorie", "tous", "laureats"):
        tests = tests_for(scope_ids[scope], "phone")
        pct = round(100 * sum(1 for t in tests if is_test_completed("phone", t.raw_data or {})) / len(tests)) if tests else None
        values[f"QS phone pct {scope}"] = _fmt_pct(pct)

    vous_phone_tests = tests_for(scope_ids["vous"], "phone")
    values["coupures avant phone vous"] = sum(
        1 for t in vous_phone_tests if str((t.raw_data or {}).get("Call Drop", "")).strip().lower() in ("1", "oui", "yes", "true")
    )
    def _slow_pickup(raw_data):
        try:
            return float(raw_data.get("code 8 Answered Call Time MIN")) > 4
        except (TypeError, ValueError):
            return False
    values["prise charge sup4min phone vous"] = sum(1 for t in vous_phone_tests if _slow_pickup(t.raw_data or {}))

    # -- Téléphone : temps moyens (accès / prise en charge / durée totale)
    for metric in ("acces", "prise", "totale"):
        for scope in ("vous", "categorie", "tous", "laureats"):
            tests = tests_for(scope_ids[scope], "phone")
            durations = [_phone_duration(t.raw_data or {}, metric) for t in tests]
            values[f"temps {metric} phone {scope}"] = _format_duration(_avg(durations))

    # -- Téléphone : répartition jour de la semaine / matin-après-midi
    def bucket_stats(channel, tests, day=None, half=None):
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

    for scope in ("vous", "categorie", "tous", "laureats"):
        tests = tests_for(scope_ids[scope], "phone")
        for day in DAY_RAW_BY_KEY:
            note, pct = bucket_stats("phone", tests, day=day)
            values[f"note jour {day} phone {scope}"] = _fmt_note(note)
            values[f"pct jour {day} phone {scope}"] = _fmt_pct(pct)
        for half in HALF_RAW_BY_KEY:
            note, pct = bucket_stats("phone", tests, half=half)
            values[f"note horaire {half} phone {scope}"] = _fmt_note(note)
            values[f"pct horaire {half} phone {scope}"] = _fmt_pct(pct)

    # -- Mail : taux de réponse / délai de réponse / cas d'inaccessibilité
    for scope in ("vous", "categorie", "tous", "laureats"):
        tests = tests_for(scope_ids[scope], "mail")
        if tests:
            repondus = sum(1 for t in tests if (t.raw_data or {}).get("Return date"))
            pct_reponse = round(100 * repondus / len(tests))
        else:
            pct_reponse = None
        values[f"taux reponse mail {scope}"] = _fmt_pct(pct_reponse)

        delais_heures = [_mail_business_hours(t.raw_data or {}) for t in tests]
        delais_heures = [d for d in delais_heures if d is not None]
        avg_heures = _avg(delais_heures)
        values[f"delai reponse mail {scope}"] = _format_duration(avg_heures * 3600 if avg_heures is not None else None)

    vous_mail_tests = tests_for(scope_ids["vous"], "mail")
    values["reponses non recues mail vous"] = sum(
        1 for t in vous_mail_tests if not (t.raw_data or {}).get("Return date")
    )
    values["reponses recues sup2j mail vous"] = sum(
        1 for t in vous_mail_tests
        if _mail_business_hours(t.raw_data or {}) is not None and _mail_business_hours(t.raw_data or {}) > 16
    )

    # -- Internet : taux de disponibilité / note et clics moyens
    for scope in ("vous", "categorie", "tous", "laureats"):
        tests = tests_for(scope_ids[scope], "web")
        # Aucune colonne de statut d'échec confirmée pour Internet à ce jour :
        # tous les tests valides sont considérés disponibles (hypothèse à
        # vérifier en conditions réelles, voir résumé fourni à l'utilisateur).
        values[f"taux disponibilite web {scope}"] = _fmt_pct(100.0 if tests else None)
        clicks = [_extract_clicks(t.raw_data or {}) for t in tests]
        values[f"clics web {scope}"] = _fmt_note(_avg(clicks))

    # -- Réseaux sociaux : taux de réponse (sous 12h ouvrées) / délai de réponse.
    # "Test Duration" (confirmé) est un temps réel écoulé, pas des heures
    # ouvrées à proprement parler (contrairement à "Business hours" pour le
    # mail) : on le compare néanmoins directement au seuil de 12h, faute de
    # colonne équivalente convertie en heures ouvrées pour ce canal.
    def _within_hours(raw_data, key, hours):
        seconds = _duration_like_seconds(raw_data or {}, key)
        return seconds is not None and seconds <= hours * 3600

    for scope in ("vous", "categorie", "tous", "laureats", "non_laureats"):
        tests = tests_for(scope_ids[scope], "rs")
        durations = [_duration_like_seconds(t.raw_data or {}, "Test Duration") for t in tests]
        durations = [d for d in durations if d is not None]
        pct = round(100 * sum(1 for t in tests if _within_hours(t.raw_data, "Test Duration", 12)) / len(tests)) if tests else None
        if scope == "non_laureats":
            values["rs note pct non laureats"] = _fmt_pct(pct)
        else:
            values[f"taux reponse rs {scope}"] = _fmt_pct(pct)
            values[f"delai reponse rs {scope}"] = _format_duration(_avg(durations))

    # -- Chat : taux de conversations abouties / temps moyens.
    # Aucune règle de calcul du "taux de conversations abouties" n'a été
    # précisée : on utilise ici, à titre d'hypothèse à valider, la
    # proportion de tests exploitables (au moins un critère valide) parmi
    # tous les tests chat de la portée, comme proxy d'une conversation
    # effectivement aboutie.
    for scope in ("vous", "categorie", "tous", "laureats"):
        tests = tests_for(scope_ids[scope], "chat")
        if tests:
            aboutis = sum(1 for t in tests if compute_test_score("chat", t.raw_data or {}) is not None)
            pct = round(100 * aboutis / len(tests))
        else:
            pct = None
        values[f"taux conv abouties chat {scope}"] = _fmt_pct(pct)

        demandes = [_duration_like_seconds(t.raw_data or {}, "Respond Time") for t in tests]
        demandes = [d for d in demandes if d is not None]
        values[f"temps demande chat {scope}"] = _format_duration(_avg(demandes))

        convs = [_duration_like_seconds(t.raw_data or {}, "Test Duration") for t in tests]
        convs = [d for d in convs if d is not None]
        values[f"temps conv chat {scope}"] = _format_duration(_avg(convs))

    vous_chat_tests = tests_for(scope_ids["vous"], "chat")
    values["interactions non repondues chat vous"] = sum(
        1 for t in vous_chat_tests if _duration_like_seconds(t.raw_data or {}, "Respond Time") is None
    )

    return values
