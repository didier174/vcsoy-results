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

# Édition « bac à sable » : toujours proposée en premier, utilisée pour
# tester/simuler des données sans jamais perturber une édition réelle.
# Les administrateurs y démarrent systématiquement (voir
# resolve_startup_edition_id) ; les autres utilisateurs peuvent y être
# rattachés par défaut depuis Administration tant qu'une édition réelle
# ne leur a pas été assignée.
WHITE_EDITION_ID = "blanche"

EDITIONS = [
    {
        "id": WHITE_EDITION_ID,
        "short_label": "Édition Blanche",
        "full_label": "Édition Blanche — environnement de test",
        "logo_file": "logo_annee_fr.png",
    },
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


def resolve_startup_edition_id(user):
    """
    Détermine l'édition sur laquelle démarrer l'outil pour cet utilisateur
    à la connexion. Les administrateurs démarrent toujours sur l'édition
    blanche (pour ne jamais mélanger leurs tests/simulations avec les
    données réelles d'une édition en cours) ; les autres utilisateurs
    démarrent sur l'édition qui leur a été assignée dans Administration
    (édition blanche par défaut tant qu'elle n'a pas été changée).
    """
    from app.access_control import user_is_admin

    if user_is_admin(user):
        return WHITE_EDITION_ID

    default_edition_id = getattr(user, "default_edition_id", None)
    if default_edition_id and is_valid_edition(default_edition_id):
        return default_edition_id

    return WHITE_EDITION_ID
