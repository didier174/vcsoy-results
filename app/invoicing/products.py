"""
Catalogue des produits facturables.

Le produit VCSOY (« Voted Customer Service Of the Year ») est un produit
UNIQUE et INDISSOCIABLE, calculé dynamiquement (l'intitulé embarque le nom
de l'édition) — ce n'est pas un produit du catalogue, il reste défini ici.

Les autres produits (droit d'utilisation de la marque, goodies, ...) sont
gérés depuis « Facturation » > « Liste des produits » : un catalogue
global (modèle Product, voir app/models.py), partagé entre toutes les
éditions, où chaque produit a un titre + jusqu'à 3 puces de détail
optionnelles et un seul prix pour l'ensemble — présenté sur la facture
exactement comme le produit VCSOY.
"""

VCSOY_PACKAGE_ID = "vcsoy_package"

VCSOY_PACKAGE = {
    "id": VCSOY_PACKAGE_ID,
    "bullets_en": [
        "Development of test scenarios",
        "Organization and execution of mystery shopping tests",
        "Report on customer experience based on mystery shopping tests",
    ],
    "bullets_fr": [
        "Élaboration des scénarios de test",
        "Organisation et réalisation des tests mystères",
        "Rapport d'expérience client basé sur les tests mystères",
    ],
}


def vcsoy_heading(language, edition_id):
    """Intitulé du produit VCSOY (la 1ère des 4 lignes), ex. 'VCSOY Edition 2027'."""
    if language == "fr":
        return f"Élu Service à la Clientèle de l'Année (VCSOY) Édition {edition_id}"
    return f"Voted Customer Service Of the Year (VCSOY) Edition {edition_id}"


def vcsoy_bullets(language):
    return VCSOY_PACKAGE["bullets_fr"] if language == "fr" else VCSOY_PACKAGE["bullets_en"]
