"""
Module « Facturation ».

Permet de générer une facture pour un participant de l'édition en cours :
langue, numéro de facture, numéro de client, nom du client, date,
sélection du participant puis des produits à facturer (avec leur montant
hors taxes et leur quantité). Les taxes du Québec (TPS/TVQ) sont
appliquées automatiquement, sauf pour un participant facturé hors Canada
(exportation de services détaxée).

Les produits (hors VCSOY, unique et indissociable) viennent d'un
catalogue global géré depuis « Liste des produits » (voir le modèle
Product) : chaque produit a un titre + jusqu'à 3 puces de détail
optionnelles et un seul prix pour l'ensemble.

La facture est ensuite téléchargeable en Excel (à partir du modèle fourni,
pour permettre des ajustements manuels) et en PDF. Elle peut aussi être
modifiée ou supprimée depuis la liste des factures.
"""

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, send_file, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Participant, Invoice, Product, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.invoicing.products import VCSOY_PACKAGE_ID, VCSOY_PACKAGE, vcsoy_heading, vcsoy_bullets
from app.invoicing.taxes import compute_taxes
from app.invoicing.generator import fill_invoice_xlsx, render_invoice_pdf

invoicing_bp = Blueprint("invoicing", __name__, url_prefix="/invoicing")

ACTIVE_ITEM = "Facturation"


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id, user_email=current_user.email,
        edition_id=get_current_edition_id(), action=action, details=details,
    )
    db.session.add(entry)
    db.session.commit()


def _current_participants(edition_id):
    """
    Participants proposés à la création d'une facture : jamais un acteur
    de référence (case « Act Réf. » cochée dans Gestion des participants),
    qui ne doit pas être facturé.
    """
    return (
        Participant.query.filter_by(edition_id=edition_id, active_ref=False)
        .order_by(Participant.participant_name)
        .all()
    )


def _participants_json(participants):
    return {
        str(p.id): {
            "name": p.participant_name,
            "address1": p.billing_address1 or "",
            "address2": p.billing_address2 or "",
            "city": p.billing_city or "",
            "postal_code": p.billing_postal_code or "",
            "country": p.billing_country or "Canada",
            "contact_name": p.billing_contact_name or p.representative_name or "",
        }
        for p in participants
    }


def _all_products():
    return Product.query.order_by(Product.title).all()


def _products_json(products):
    return {
        str(p.id): {
            "title": p.title,
            "language": p.language or "fr",
            "bullet1": p.bullet1 or "",
            "bullet2": p.bullet2 or "",
            "bullet3": p.bullet3 or "",
            "price": p.price or 0,
        }
        for p in products
    }


def _validate_product_form(form):
    """Valide les champs communs à l'ajout et à la modification d'un
    produit du catalogue. Retourne (error, data)."""
    title = form.get("title", "").strip()
    if not title:
        return "Le titre du produit est obligatoire.", None

    language = form.get("language", "").strip()
    if language not in ("fr", "en"):
        return "Merci de choisir la langue (Français ou English) du produit.", None

    bullets = [form.get(f"bullet{i}", "").strip() for i in (1, 2, 3)]
    raw_price = form.get("price", "").strip().replace(",", ".")
    try:
        price = float(raw_price) if raw_price else 0.0
        if price < 0:
            raise ValueError()
    except ValueError:
        return "Prix de produit invalide.", None

    return None, {
        "title": title, "language": language,
        "bullet1": bullets[0] or None, "bullet2": bullets[1] or None, "bullet3": bullets[2] or None,
        "price": price,
    }


def _invoice_edit_payload(invoice):
    products_data = []
    vcsoy_price = None
    for item in (invoice.line_items or []):
        if item.get("role") == "vcsoy_heading":
            vcsoy_price = item.get("unit_price")
        elif item.get("role") == "catalog_heading" and item.get("product_id"):
            products_data.append({
                "product_id": item["product_id"], "unit_price": item.get("unit_price"),
                "quantity": item.get("quantity", 1),
            })
        elif item.get("role") == "standalone" and item.get("product_id"):
            # Facture créée avant le catalogue de produits : le product_id
            # (ex. "goodies") ne correspond plus à une case à cocher du
            # nouveau catalogue, ignoré ici (la facture reste néanmoins
            # consultable/téléchargeable telle quelle).
            pass
    if vcsoy_price is not None:
        products_data.insert(0, {"product_id": VCSOY_PACKAGE_ID, "unit_price": vcsoy_price})
    return {
        "id": invoice.id,
        "language": invoice.language or "fr",
        "invoice_number": invoice.invoice_number or "",
        "customer_number": invoice.customer_number or "",
        "customer_name": invoice.bill_to_company_name or "",
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else "",
        "bill_to_contact_name": invoice.bill_to_contact_name or "",
        "bill_to_address1": invoice.bill_to_address1 or "",
        "bill_to_address2": invoice.bill_to_address2 or "",
        "bill_to_city": invoice.bill_to_city or "",
        "bill_to_postal_code": invoice.bill_to_postal_code or "",
        "bill_to_country": invoice.bill_to_country or "Canada",
        "products": products_data,
    }


def _get_invoice_or_404(invoice_id):
    edition_id = get_current_edition_id()
    invoice = Invoice.query.get(invoice_id)
    if not invoice or invoice.edition_id != edition_id:
        abort(404)
    return invoice


def _validate_and_build(form, edition_id, edition, require_participant):
    """
    Contrôle les champs communs à la création et à la modification d'une
    facture, et construit les lignes de facture + montants si tout est
    valide. Retourne (errors, data) où data est un dict prêt à appliquer
    sur un Invoice si errors est vide.
    """
    errors = []
    data = {}

    language = form.get("language", "").strip()
    if language not in ("fr", "en"):
        errors.append("Merci de choisir la langue de la facture.")
    data["language"] = language if language in ("fr", "en") else "fr"

    invoice_number = form.get("invoice_number", "").strip()
    if not invoice_number:
        errors.append("Le numéro de facture est obligatoire.")
    data["invoice_number"] = invoice_number

    customer_number = form.get("customer_number", "").strip()
    if not customer_number:
        errors.append("Le numéro de client est obligatoire.")
    data["customer_number"] = customer_number

    customer_name = form.get("customer_name", "").strip()
    if not customer_name:
        errors.append("Le nom du client est obligatoire.")
    data["customer_name"] = customer_name

    invoice_date = None
    date_raw = form.get("invoice_date", "").strip()
    if not date_raw:
        errors.append("La date de facture est obligatoire.")
    else:
        try:
            invoice_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Date de facture invalide.")
    data["invoice_date"] = invoice_date

    # Adresse de facturation (pré-remplie depuis le participant à la
    # création, mais reste modifiable — notamment lors d'une correction).
    data["bill_to_address1"] = form.get("bill_to_address1", "").strip()
    data["bill_to_address2"] = form.get("bill_to_address2", "").strip()
    data["bill_to_city"] = form.get("bill_to_city", "").strip()
    data["bill_to_postal_code"] = form.get("bill_to_postal_code", "").strip()
    data["bill_to_country"] = form.get("bill_to_country", "").strip() or "Canada"
    data["bill_to_contact_name"] = form.get("bill_to_contact_name", "").strip()

    participant = None
    if require_participant:
        participant_id = form.get("participant_id", "").strip()
        if not participant_id:
            errors.append("Merci de sélectionner un participant.")
        else:
            participant = Participant.query.get(int(participant_id)) if participant_id.isdigit() else None
            if not participant or participant.edition_id != edition_id:
                errors.append("Participant introuvable pour cette édition.")
                participant = None
            elif participant.active_ref:
                errors.append(
                    f"« {participant.participant_name} » est un acteur de référence (Act Réf.) : "
                    "il ne peut pas être facturé."
                )
                participant = None
    data["participant"] = participant

    selected_vcsoy = bool(form.get(f"product_{VCSOY_PACKAGE_ID}"))
    all_products = _all_products()
    # Un produit n'est proposé que dans sa propre langue (voir le filtrage
    # JS sur la page) : on l'ignore ici s'il ne correspond pas à la langue
    # de la facture, par sécurité si jamais coché malgré tout.
    selected_products = [
        p for p in all_products
        if form.get(f"product_cat_{p.id}") and p.language == data["language"]
    ]

    if not selected_vcsoy and not selected_products:
        errors.append("Merci de sélectionner au moins un produit à facturer.")

    vcsoy_price = None
    if selected_vcsoy:
        raw_price = form.get(f"price_{VCSOY_PACKAGE_ID}", "").strip().replace(",", ".")
        try:
            vcsoy_price = float(raw_price)
            if vcsoy_price <= 0:
                raise ValueError()
        except ValueError:
            errors.append("Montant hors taxes invalide pour « Voted Customer Service Of the Year (VCSOY) ».")

    catalog_values = {}  # product.id -> (price, quantity)
    for product in selected_products:
        raw_price = form.get(f"price_cat_{product.id}", "").strip().replace(",", ".")
        raw_qty = form.get(f"qty_cat_{product.id}", "").strip()
        try:
            price = float(raw_price)
            if price < 0:
                raise ValueError()
        except ValueError:
            errors.append(f"Montant hors taxes invalide pour « {product.title} ».")
            price = None
        try:
            qty = float(raw_qty) if raw_qty else 1.0
            if qty <= 0:
                raise ValueError()
        except ValueError:
            errors.append(f"Quantité invalide pour « {product.title} ».")
            qty = None
        if price is not None and qty is not None:
            catalog_values[product.id] = (price, qty)

    if errors:
        return errors, data

    line_items = []
    if selected_vcsoy:
        bullets = vcsoy_bullets(data["language"])
        # Un seul produit, indissociable, présenté sur 4 lignes : l'intitulé
        # porte le prix et la quantité de l'ensemble, suivi des 3 puces
        # descriptives (décalées à droite), sans montant propre.
        line_items.append({
            "role": "vcsoy_heading",
            "description": vcsoy_heading(data["language"], edition_id),
            "is_heading": True, "quantity": 1, "unit_price": vcsoy_price, "total": vcsoy_price,
        })
        line_items.append({"role": "vcsoy_plain", "description": bullets[0], "is_heading": False})
        line_items.append({"role": "vcsoy_plain", "description": bullets[1], "is_heading": False})
        line_items.append({"role": "vcsoy_plain", "description": bullets[2], "is_heading": False})

    for product in selected_products:
        price, qty = catalog_values[product.id]
        total = round(price * qty, 2)
        # Comme le VCSOY : un titre (portant prix/quantité/total) suivi de
        # ses puces de détail éventuelles (jusqu'à 3), sans montant propre.
        line_items.append({
            "role": "catalog_heading", "product_id": product.id,
            "description": product.title, "is_heading": True,
            "quantity": qty, "unit_price": price, "total": total,
        })
        for bullet in product.bullets():
            line_items.append({"role": "catalog_bullet", "description": bullet, "is_heading": False})

    subtotal = sum(i.get("total", 0) for i in line_items)
    tax = compute_taxes(subtotal, data["bill_to_country"])

    data["line_items"] = line_items
    data["subtotal"] = subtotal
    data["gst_amount"] = tax["gst"]
    data["qst_amount"] = tax["qst"]
    data["total_amount"] = tax["total"]
    data["is_export"] = tax["is_export"]

    return errors, data


@invoicing_bp.route("/", methods=["GET"])
@login_required
def list_invoices():
    edition_id = get_current_edition_id()
    invoices = Invoice.query.filter_by(edition_id=edition_id).order_by(Invoice.id.desc()).all()
    edit_payloads = {inv.id: _invoice_edit_payload(inv) for inv in invoices}
    products = _all_products()
    return render_template(
        "invoicing/list.html", edition=get_edition(edition_id), invoices=invoices,
        edit_payloads=edit_payloads,
        vcsoy_package=VCSOY_PACKAGE, vcsoy_package_id=VCSOY_PACKAGE_ID,
        products=products, products_json=_products_json(products),
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS, error=None,
    )


def _render_list_with_error(error):
    edition_id = get_current_edition_id()
    invoices = Invoice.query.filter_by(edition_id=edition_id).order_by(Invoice.id.desc()).all()
    edit_payloads = {inv.id: _invoice_edit_payload(inv) for inv in invoices}
    products = _all_products()
    return render_template(
        "invoicing/list.html", edition=get_edition(edition_id), invoices=invoices,
        edit_payloads=edit_payloads,
        vcsoy_package=VCSOY_PACKAGE, vcsoy_package_id=VCSOY_PACKAGE_ID,
        products=products, products_json=_products_json(products),
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS, error=error,
    )


# ------------------------------------------------------- Catalogue produits

@invoicing_bp.route("/products/add", methods=["POST"])
@login_required
def add_product():
    error, data = _validate_product_form(request.form)
    if error:
        return _render_list_with_error(error)

    db.session.add(Product(created_by_id=current_user.id, **data))
    db.session.commit()

    _log("Ajout d'un produit au catalogue", details=data["title"])
    return redirect(url_for("invoicing.list_invoices"))


@invoicing_bp.route("/products/<int:product_id>/update", methods=["POST"])
@login_required
def update_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        return _render_list_with_error("Produit introuvable.")

    error, data = _validate_product_form(request.form)
    if error:
        return _render_list_with_error(error)

    for key, value in data.items():
        setattr(product, key, value)
    db.session.commit()

    _log("Modification d'un produit du catalogue", details=data["title"])
    return redirect(url_for("invoicing.list_invoices"))


@invoicing_bp.route("/products/delete", methods=["POST"])
@login_required
def delete_products():
    selected_ids = [int(i) for i in request.form.getlist("product_ids") if i.isdigit()]
    if not selected_ids:
        return _render_list_with_error("Veuillez cocher au moins un produit à supprimer.")

    to_delete = Product.query.filter(Product.id.in_(selected_ids)).all()
    titles = [p.title for p in to_delete]
    # Les factures déjà générées gardent leur propre copie (description,
    # prix) dans line_items : supprimer le produit du catalogue ne les
    # modifie pas.
    for product in to_delete:
        db.session.delete(product)
    db.session.commit()

    _log("Suppression de produit(s) du catalogue", details=", ".join(titles))
    return redirect(url_for("invoicing.list_invoices"))


# ------------------------------------------------------------------ Factures

@invoicing_bp.route("/create", methods=["GET"])
@login_required
def create_form():
    edition_id = get_current_edition_id()
    participants = _current_participants(edition_id)
    return render_template(
        "invoicing/create.html", edition=get_edition(edition_id), participants=participants,
        participants_json=_participants_json(participants),
        vcsoy_package=VCSOY_PACKAGE, vcsoy_package_id=VCSOY_PACKAGE_ID, products=_all_products(),
        errors=[], form_values={}, active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@invoicing_bp.route("/create", methods=["POST"])
@login_required
def create_invoice():
    edition_id = get_current_edition_id()
    edition = get_edition(edition_id)
    form = request.form

    errors, data = _validate_and_build(form, edition_id, edition, require_participant=True)

    if errors:
        participants = _current_participants(edition_id)
        return render_template(
            "invoicing/create.html", edition=edition, participants=participants,
            participants_json=_participants_json(participants),
            vcsoy_package=VCSOY_PACKAGE, vcsoy_package_id=VCSOY_PACKAGE_ID, products=_all_products(),
            errors=errors, form_values=form, active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
        )

    participant = data["participant"]

    invoice = Invoice(
        edition_id=edition_id,
        participant_id=participant.id,
        language=data["language"],
        invoice_number=data["invoice_number"],
        customer_number=data["customer_number"],
        invoice_date=data["invoice_date"],
        bill_to_contact_name=data["bill_to_contact_name"] or participant.billing_contact_name or participant.representative_name,
        bill_to_company_name=data["customer_name"],
        bill_to_address1=data["bill_to_address1"],
        bill_to_address2=data["bill_to_address2"],
        bill_to_city=data["bill_to_city"],
        bill_to_postal_code=data["bill_to_postal_code"],
        bill_to_country=data["bill_to_country"],
        line_items=data["line_items"],
        subtotal=data["subtotal"],
        gst_amount=data["gst_amount"],
        qst_amount=data["qst_amount"],
        total_amount=data["total_amount"],
        is_export=data["is_export"],
        created_by_id=current_user.id,
    )
    db.session.add(invoice)
    db.session.commit()

    _log("Création facture", details=f"{data['invoice_number']} — {participant.participant_name} (édition {edition_id})")

    return redirect(url_for("invoicing.preview_invoice", invoice_id=invoice.id))


@invoicing_bp.route("/<int:invoice_id>", methods=["GET"])
@login_required
def preview_invoice(invoice_id):
    invoice = _get_invoice_or_404(invoice_id)
    return render_template(
        "invoicing/preview.html", edition=get_edition(get_current_edition_id()), invoice=invoice,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@invoicing_bp.route("/<int:invoice_id>/update", methods=["POST"])
@login_required
def update_invoice(invoice_id):
    invoice = _get_invoice_or_404(invoice_id)
    edition_id = get_current_edition_id()
    edition = get_edition(edition_id)
    form = request.form

    errors, data = _validate_and_build(form, edition_id, edition, require_participant=False)

    if errors:
        return _render_list_with_error(
            "La modification n'a pas pu être enregistrée : " + " • ".join(errors) +
            " Rouvrez « Modifier » sur cette facture pour corriger."
        )

    invoice.language = data["language"]
    invoice.invoice_number = data["invoice_number"]
    invoice.customer_number = data["customer_number"]
    invoice.invoice_date = data["invoice_date"]
    invoice.bill_to_contact_name = data["bill_to_contact_name"]
    invoice.bill_to_company_name = data["customer_name"]
    invoice.bill_to_address1 = data["bill_to_address1"]
    invoice.bill_to_address2 = data["bill_to_address2"]
    invoice.bill_to_city = data["bill_to_city"]
    invoice.bill_to_postal_code = data["bill_to_postal_code"]
    invoice.bill_to_country = data["bill_to_country"]
    invoice.line_items = data["line_items"]
    invoice.subtotal = data["subtotal"]
    invoice.gst_amount = data["gst_amount"]
    invoice.qst_amount = data["qst_amount"]
    invoice.total_amount = data["total_amount"]
    invoice.is_export = data["is_export"]
    db.session.commit()

    _log("Modification facture", details=f"{invoice.invoice_number} (édition {edition_id})")

    return redirect(url_for("invoicing.preview_invoice", invoice_id=invoice.id))


@invoicing_bp.route("/delete", methods=["POST"])
@login_required
def delete_invoices():
    edition_id = get_current_edition_id()
    selected_ids = [int(i) for i in request.form.getlist("selected_ids")]
    if not selected_ids:
        return _render_list_with_error("Veuillez cocher au moins une facture à supprimer.")

    to_delete = Invoice.query.filter(Invoice.edition_id == edition_id, Invoice.id.in_(selected_ids)).all()
    numbers = [i.invoice_number for i in to_delete]
    for inv in to_delete:
        db.session.delete(inv)
    db.session.commit()

    _log("Suppression facture(s)", details=", ".join(numbers))
    return redirect(url_for("invoicing.list_invoices"))


@invoicing_bp.route("/<int:invoice_id>/download.xlsx", methods=["GET"])
@login_required
def download_xlsx(invoice_id):
    invoice = _get_invoice_or_404(invoice_id)
    buf = fill_invoice_xlsx(invoice)
    filename = f"{invoice.invoice_number or 'facture'}.xlsx"
    return send_file(
        buf, as_attachment=True, download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@invoicing_bp.route("/<int:invoice_id>/download.pdf", methods=["GET"])
@login_required
def download_pdf(invoice_id):
    invoice = _get_invoice_or_404(invoice_id)
    buf = render_invoice_pdf(invoice)
    filename = f"{invoice.invoice_number or 'facture'}.pdf"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/pdf")
