"""
Gestion des « éditions » annuelles (même concept que côté application Mac).

Différence importante par rapport au Mac : ici, plusieurs collaborateurs
utilisent l'outil en même temps. L'édition sélectionnée est donc stockée
dans la session **de chaque utilisateur** (cookie de session Flask), et non
dans un réglage global partagé — ainsi, une personne peut travailler sur
l'édition 2027 pendant qu'une autre travaille sur 2028, sans se marcher
dessus.
"""

from flask import session

EDITIONS = [
    {
        "id": "2027",
        "short_label": "ESCDA 2027",
        "full_label": "1ère Édition — ESCDA 2027",
        "logo_file": "logo_2027_fr.png",
    },
    {
        "id": "2028",
        "short_label": "ESCDA 2028",
        "full_label": "2ème Édition — ESCDA 2028",
        "logo_file": "logo_2028_fr.png",
    },
    {
        "id": "2029",
        "short_label": "ESCDA 2029",
        "full_label": "3ème Édition — ESCDA 2029",
        "logo_file": "logo_2029_fr.png",
    },
    {
        "id": "2030",
        "short_label": "ESCDA 2030",
        "full_label": "4ème Édition — ESCDA 2030",
        "logo_file": "logo_2030_fr.png",
    },
]

_BY_ID = {e["id"]: e for e in EDITIONS}
DEFAULT_EDITION_ID = EDITIONS[0]["id"]


def list_editions():
    return list(EDITIONS)


def is_valid_edition(edition_id):
    return edition_id in _BY_ID


def get_edition(edition_id):
    return _BY_ID.get(edition_id, EDITIONS[0])


def get_current_edition_id():
    """Retourne l'édition en cours pour l'utilisateur courant (stockée en session)."""
    edition_id = session.get("edition_id")
    if not edition_id or not is_valid_edition(edition_id):
        edition_id = DEFAULT_EDITION_ID
        session["edition_id"] = edition_id
    return edition_id


def set_current_edition_id(edition_id):
    if is_valid_edition(edition_id):
        session["edition_id"] = edition_id
