"""
Liste des items du menu latéral, centralisée ici pour être utilisée par
tous les blueprints (dashboard, catégories, participants, ...) sans risque
d'oubli lors du rendu d'un template qui étend app_shell.html.
"""

MENU_ITEMS = [
    "Configuration catégorie",
    "Configuration Participant",
    "Chargement fichier résultat",
    "Listes des tests",
    "Compilation des résultats",
    "Présentation des résultats",
    "Liste des lauréats",
    "Facturation",
    "Administration",
]
