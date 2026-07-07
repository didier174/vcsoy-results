"""
Calcul des notes (« Compilation des résultats », étape 8).

Pour chaque test, on additionne les valeurs des colonnes « Code N » qui
contiennent un 0, 1 ou 2 ; les colonnes vides ou « Non applicable » sont
exclues du calcul (aussi bien du numérateur que du dénominateur — elles ne
comptent pas comme un critère valide). Une colonne « Code N » précise,
propre à chaque canal, compte double : Code 13 pour Phone, Code 11 pour
Mail/Web Navigation/Social Networks, Code 10 pour Chat (si sa valeur est 1
ou 2, elle rapporte donc 2 ou 4 points au lieu de 1 ou 2).

La note brute d'un test va donc de 0 à un maximum qui dépend du nombre de
critères valides (jusqu'à 32 quand tous les critères d'un canal à 15 codes
sont renseignés). Elle est aussi ramenée sur 20 (note_brute / note_max *
20), ce qui permet de comparer des tests dont le nombre de critères valides
diffère (certains « Non applicable ») ou qui appartiennent à des canaux
n'ayant pas le même nombre total de codes (14 ou 15 selon le canal).

Un test sans aucun critère valide (tous ses « Code N » vides ou « Non
applicable ») n'a pas de note calculable et n'est pas pris en compte dans
les moyennes par participant/canal.

Ce module calcule aussi (étape 9) la note finale consolidée d'un
participant, qui pondère ses notes par canal selon l'ensemble exact des
canaux sur lesquels il a des tests (voir CONSOLIDATED_WEIGHTS), pour
déterminer le lauréat de chaque catégorie.
"""

from app.results.presentation import extract_codes, CHANNEL_ORDER

# Code compté double, selon le canal.
DOUBLED_CODE_BY_CHANNEL = {
    "phone": 13,
    "mail": 11,
    "web": 11,
    "rs": 11,
    "chat": 10,
}

EXCLUDED_VALUES = {"non applicable", "non observable"}


def compute_test_score(channel, raw_data):
    """
    Retourne {"note_brute", "note_max", "note_20", "nb_criteres"} pour un
    test, ou None si aucun critère « Code N » valide n'est renseigné.
    """
    doubled_code = DOUBLED_CODE_BY_CHANNEL.get(channel)
    raw_sum = 0
    max_sum = 0
    nb_criteres = 0

    for code in extract_codes(raw_data):
        value = code["value"]
        if value is None or str(value).strip() == "":
            continue
        sval = str(value).strip().lower()
        if sval in EXCLUDED_VALUES:
            continue
        try:
            numeric = int(float(sval))
        except ValueError:
            continue

        weight = 2 if code["number"] == doubled_code else 1
        raw_sum += numeric * weight
        max_sum += 2 * weight
        nb_criteres += 1

    if nb_criteres == 0:
        return None

    note_20 = round(raw_sum / max_sum * 20, 2) if max_sum else 0.0
    return {
        "note_brute": raw_sum,
        "note_max": max_sum,
        "note_20": note_20,
        "nb_criteres": nb_criteres,
    }


def build_compilation_rows(participants, tests):
    """
    participants : liste des Participant de l'édition en cours.
    tests : liste des TestResult de l'édition en cours.

    Retourne une liste de lignes (une par participant), triées par
    catégorie puis participant, prêtes pour le template de compilation.
    """
    tests_by_participant = {}
    for t in tests:
        if not t.participant_id:
            continue
        score = compute_test_score(t.channel, t.raw_data or {})
        if score is None:
            continue
        tests_by_participant.setdefault(t.participant_id, []).append({
            "id": t.id,
            "test_id": t.test_id,
            "channel": t.channel,
            **score,
        })

    rows = []
    for participant in participants:
        participant_tests = tests_by_participant.get(participant.id, [])

        channels = {}
        for channel in CHANNEL_ORDER:
            channel_tests = sorted(
                (t for t in participant_tests if t["channel"] == channel),
                key=lambda t: t["test_id"],
            )
            if channel_tests:
                note_20 = round(sum(t["note_20"] for t in channel_tests) / len(channel_tests), 2)
            else:
                note_20 = None
            channels[channel] = {"nb_test": len(channel_tests), "note_20": note_20}

        if participant_tests:
            overall_20 = round(sum(t["note_20"] for t in participant_tests) / len(participant_tests), 2)
            overall_brute = round(overall_20 / 20 * 32, 2)
        else:
            overall_20 = None
            overall_brute = None

        rows.append({
            "participant_id": participant.id,
            "participant_name": participant.participant_name,
            "category_code": participant.category.code if participant.category else "",
            "category_label": participant.category_label(),
            "channels": channels,
            "note_brute": overall_brute,
            "note_20": overall_20,
            "nb_tests_total": len(participant_tests),
            "tests": sorted(participant_tests, key=lambda t: (t["channel"], t["test_id"])),
        })

    rows.sort(key=lambda r: (r["category_label"].lower(), r["participant_name"].lower()))
    return rows


# --------------------------------------------------- Note finale consolidée
#
# Étape 9 : la note finale consolidée d'un participant sert à départager les
# participants d'une même catégorie (lauréat). Sa formule dépend de
# l'ensemble exact des canaux sur lesquels le participant a des tests
# comptabilisés (nb_test > 0 pour ce canal) : chaque combinaison possible a
# sa propre pondération, définie ci-dessous d'après le cahier des charges.
# Une combinaison de canaux qui n'y figure pas n'a pas de note consolidée
# calculable (résultat None).

CONSOLIDATED_WEIGHTS = {
    frozenset({"phone", "mail", "web", "rs", "chat"}): (
        {"phone": 0.57, "mail": 0.23, "web": 0.08, "rs": 0.06, "chat": 0.06}, 1.0),
    frozenset({"phone", "mail", "web", "rs"}): (
        {"phone": 0.6, "mail": 0.24, "web": 0.09, "rs": 0.07}, 0.98),
    frozenset({"phone", "mail", "web", "chat"}): (
        {"phone": 0.6, "mail": 0.24, "web": 0.09, "chat": 0.07}, 0.98),
    frozenset({"phone", "mail", "web"}): (
        {"phone": 0.63, "mail": 0.27, "web": 0.1}, 0.95),
    frozenset({"phone", "web", "rs", "chat"}): (
        {"phone": 0.70, "web": 0.14, "rs": 0.08, "chat": 0.08}, 0.90),
    frozenset({"phone", "web", "chat"}): (
        {"phone": 0.75, "web": 0.15, "chat": 0.1}, 0.85),
    frozenset({"phone", "web", "rs"}): (
        {"phone": 0.75, "web": 0.15, "rs": 0.1}, 0.85),
    frozenset({"phone", "web"}): (
        {"phone": 0.8, "web": 0.2}, 0.80),
}


def compute_consolidated_score(channel_notes):
    """
    channel_notes : {canal: note sur 20} pour les seuls canaux sur lesquels
    le participant a des tests comptabilisés. Retourne la note finale
    consolidée (float, arrondie à 2 décimales), ou None si cette
    combinaison exacte de canaux n'a pas de pondération définie.
    """
    present = frozenset(channel_notes.keys())
    entry = CONSOLIDATED_WEIGHTS.get(present)
    if entry is None:
        return None
    weights, multiplier = entry
    raw = sum(weights[c] * channel_notes[c] for c in weights)
    return round(raw * multiplier, 2)


def row_channel_notes(row):
    """Extrait {canal: note} pour les canaux d'une ligne de build_compilation_rows ayant au moins un test."""
    return {
        c: row["channels"][c]["note_20"]
        for c in CHANNEL_ORDER
        if row["channels"][c]["note_20"] is not None
    }


def build_category_winners(rows):
    """
    rows : sortie de build_compilation_rows (une ligne par participant).

    Retourne une liste {category_code, category_label, winner_name,
    winner_score}, une entrée par catégorie ayant au moins un participant
    dont la note finale consolidée est calculable, triée par catégorie.
    """
    by_category = {}
    for row in rows:
        score = compute_consolidated_score(row_channel_notes(row))
        if score is None:
            continue
        key = (row["category_code"], row["category_label"])
        by_category.setdefault(key, []).append((score, row["participant_name"]))

    winners = []
    for (category_code, category_label), scores in by_category.items():
        scores.sort(key=lambda s: s[0], reverse=True)
        best_score, best_name = scores[0]
        winners.append({
            "category_code": category_code,
            "category_label": category_label,
            "winner_name": best_name,
            "winner_score": best_score,
        })

    winners.sort(key=lambda w: w["category_label"].lower())
    return winners
