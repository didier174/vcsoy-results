"""
Liste des items du menu latéral, centralisée ici pour être utilisée par
tous les blueprints (dashboard, catégories, participants, ...) sans risque
d'oubli lors du rendu d'un template qui étend app_shell.html.
"""

MENU_ITEMS = [
    "Configuration catégorie",
    "Gestion des participants",
    "Gestion des scénarios",
    "Chargement fichier résultat",
    "Chargement des records",
    "Liste des tests",
    "Compilation des résultats",
    "Liste des résultats",
    "Rapport d'études",
    "Liste des lauréats",
    "Facturation",
    "Administration",
]
