"""
Liste des items du menu latéral, centralisée ici pour être utilisée par
tous les blueprints (dashboard, catégories, participants, ...) sans risque
d'oubli lors du rendu d'un template qui étend app_shell.html.
"""

MENU_ITEMS = [
    "Configuration catégorie",
    "Configuration Participant",
    "Chargement d'un fichier de résultat",
    "Compilation des résultats",
    "Présentation de la liste de test",
    "Présentation des résultats",
    "Liste des lauréats",
    "Facturation",
    "Administration",
]
