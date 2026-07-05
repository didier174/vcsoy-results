"""
Calcul des taxes applicables à une facture.

Le modèle fourni en exemple facture un client situé aux États-Unis avec
0% de taxes, mention « Export of services to a non-resident (zero-rated
supply) » : c'est le traitement standard d'une exportation de services hors
Canada. On applique donc les taxes du Québec (TPS + TVQ) uniquement quand
l'adresse de facturation du participant est au Canada ; sinon, la facture
est détaxée à 0%, comme dans l'exemple fourni.
"""

GST_RATE = 0.05       # TPS (fédérale)
QST_RATE = 0.09975    # TVQ (Québec)


def compute_taxes(subtotal, billing_country):
    """
    Retourne un dict {gst, qst, total, is_export} à partir du sous-total
    (montant hors taxes) et du pays de facturation du participant.
    """
    is_export = (billing_country or "").strip().lower() != "canada"

    if is_export:
        return {"gst": 0.0, "qst": 0.0, "total": round(subtotal, 2), "is_export": True}

    gst = round(subtotal * GST_RATE, 2)
    qst = round(subtotal * QST_RATE, 2)
    total = round(subtotal + gst + qst, 2)
    return {"gst": gst, "qst": qst, "total": total, "is_export": False}
