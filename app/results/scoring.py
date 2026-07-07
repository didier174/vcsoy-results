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
            "participant_code": participant.code,
            "category_label": participant.category_label(),
            "channels": channels,
            "note_brute": overall_brute,
            "note_20": overall_20,
            "nb_tests_total": len(participant_tests),
            "tests": sorted(participant_tests, key=lambda t: (t["channel"], t["test_id"])),
        })

    rows.sort(key=lambda r: (r["category_label"].lower(), r["participant_name"].lower()))
    return rows
