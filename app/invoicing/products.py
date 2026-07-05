"""
Catalogue des produits facturables.

Non modifiable depuis l'interface (comme demandé) : toute évolution de
cette liste (ex. les « Goodies » avec quantité et prix prédéterminés dans
une future version) se fait ici, dans le code, par un développeur.
"""

# Produits regroupés sous l'intitulé "VCSOY Edition <année>" sur la facture.
VCSOY_PRODUCTS = [
    {
        "id": "vcsoy_dev_scenarios",
        "label_en": "Development of test scenarios",
        "label_fr": "Élaboration des scénarios de test",
    },
    {
        "id": "vcsoy_organization",
        "label_en": "Organization and execution of mystery shopping tests",
        "label_fr": "Organisation et réalisation des tests mystères",
    },
    {
        "id": "vcsoy_report",
        "label_en": "Report on customer experience based on mystery shopping tests",
        "label_fr": "Rapport d'expérience client basé sur les tests mystères",
    },
]

# Produits indépendants (pas de regroupement sous un intitulé commun).
STANDALONE_PRODUCTS = [
    {
        "id": "trademark_right",
        "label_en": "Right to use the trademark VCSOY as winner during one year",
        "label_fr": "Droit d'utilisation de la marque VCSOY à titre de gagnant pendant un an",
    },
    {
        "id": "goodies",
        "label_en": "Goodies",
        "label_fr": "Goodies",
        # Note pour une évolution future : ce produit deviendra une liste de
        # goodies à choisir, avec quantités et prix prédéterminés (non
        # modifiables par l'utilisateur). Pour l'instant, simple ligne avec
        # un montant libre, comme les autres produits.
    },
]

ALL_PRODUCTS = VCSOY_PRODUCTS + STANDALONE_PRODUCTS
PRODUCTS_BY_ID = {p["id"]: p for p in ALL_PRODUCTS}


def vcsoy_heading(language, edition_id):
    """Intitulé de regroupement des produits VCSOY, ex. 'VCSOY Edition 2027'."""
    if language == "fr":
        return f"Élu Service à la Clientèle de l'Année (VCSOY) Édition {edition_id}"
    return f"Voted Customer Service Of the Year (VCSOY) Edition {edition_id}"


def product_label(product_id, language):
    product = PRODUCTS_BY_ID.get(product_id)
    if not product:
        return product_id
    return product["label_fr"] if language == "fr" else product["label_en"]
