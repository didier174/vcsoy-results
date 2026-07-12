"""
Construit le dictionnaire des données disponibles pour remplir les
balises {{ Nom de la balise }} d'un modèle de rapport, pour un
participant donné.

Ce dictionnaire est volontairement incomplet au départ : il ne reprend
que ce qui est déjà calculé ailleurs dans l'application (Compilation des
résultats). De nouvelles balises (ex. temps moyen de décroché pour le
canal Phone) seront ajoutées ici au fur et à mesure qu'elles seront
spécifiées. Toute balise présente dans un modèle mais absente de ce
dictionnaire est signalée avant la génération (voir generator.py),
plutôt que silencieusement laissée vide.
"""

from app.models import TestResult
from app.results.presentation import CHANNEL_ORDER
from app.results.scoring import build_compilation_rows


def build_participant_placeholders(participant, edition_id):
    """
    Retourne {nom de balise: valeur} pour ce participant. Les balises par
    canal utilisent la clé interne du canal (phone, mail, web, rs, chat),
    ex. {{ Note sur 20 canal phone }}, pas le libellé français affiché
    ailleurs (Téléphone) — convention confirmée sur le premier modèle
    soumis.
    """
    tests = TestResult.query.filter_by(edition_id=edition_id, participant_id=participant.id).all()
    rows = build_compilation_rows([participant], tests)
    row = rows[0] if rows else None

    values = {
        "Participant": participant.participant_name,
        "Code participant": participant.code,
        "Catégorie": participant.category_label(),
    }

    if row:
        for channel in CHANNEL_ORDER:
            channel_data = row["channels"][channel]
            values[f"Nb tests canal {channel}"] = channel_data["nb_test"]
            values[f"Note sur 20 canal {channel}"] = (
                channel_data["note_20"] if channel_data["note_20"] is not None else "—"
            )
        values["Note consolidée"] = row["consolidated_score"] if row["consolidated_score"] is not None else "—"

    return values
