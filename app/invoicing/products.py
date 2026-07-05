"""
Catalogue des produits facturables.

Non modifiable depuis l'interface (comme demandé) : toute évolution de
cette liste (ex. les « Goodies » avec quantité et prix prédéterminés dans
une future version) se fait ici, dans le code, par un développeur.

Important : le produit VCSOY (« Voted Customer Service Of the Year ») est
un produit UNIQUE et INDISSOCIABLE présenté sur 4 lignes (un intitulé +
3 puces descriptives), avec une seule quantité et un seul prix pour
l'ensemble — ce n'est pas 3 produits distincts.
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

# Produits indépendants (une ligne chacun, pas de regroupement).
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

PRODUCTS_BY_ID = {p["id"]: p for p in STANDALONE_PRODUCTS}


def vcsoy_heading(language, edition_id):
    """Intitulé du produit VCSOY (la 1ère des 4 lignes), ex. 'VCSOY Edition 2027'."""
    if language == "fr":
        return f"Élu Service à la Clientèle de l'Année (VCSOY) Édition {edition_id}"
    return f"Voted Customer Service Of the Year (VCSOY) Edition {edition_id}"


def vcsoy_bullets(language):
    return VCSOY_PACKAGE["bullets_fr"] if language == "fr" else VCSOY_PACKAGE["bullets_en"]


def product_label(product_id, language):
    product = PRODUCTS_BY_ID.get(product_id)
    if not product:
        return product_id
    return product["label_fr"] if language == "fr" else product["label_en"]
