"""
Module « Facturation ».

Permet de générer une facture pour un participant de l'édition en cours :
langue, numéro de facture, numéro de client, nom du client, date,
sélection du participant puis des produits à facturer (avec leur montant
hors taxes). Les taxes du Québec (TPS/TVQ) sont appliquées
automatiquement, sauf pour un participant facturé hors Canada
(exportation de services détaxée).

La facture est ensuite téléchargeable en Excel (à partir du modèle fourni,
pour permettre des ajustements manuels) et en PDF. Elle peut aussi être
modifiée ou supprimée depuis la liste des factures.
"""

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, send_file, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Participant, Invoice, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.invoicing.products import (
    VCSOY_PACKAGE_ID, VCSOY_PACKAGE, STANDALONE_PRODUCTS, vcsoy_heading, vcsoy_bullets, product_label,
)
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
    return Participant.query.filter_by(edition_id=edition_id).order_by(Participant.participant_name).all()


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


def _invoice_edit_payload(invoice):
    products_data = []
    vcsoy_price = None
    for item in (invoice.line_items or []):
        if item.get("role") == "vcsoy_priced":
            vcsoy_price = item.get("unit_price")
        elif item.get("role") == "standalone" and item.get("product_id"):
            products_data.append({"product_id": item["product_id"], "unit_price": item.get("unit_price")})
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
    data["participant"] = participant

    selected_vcsoy = bool(form.get(f"product_{VCSOY_PACKAGE_ID}"))
    selected_standalone = [p for p in STANDALONE_PRODUCTS if form.get(f"product_{p['id']}")]

    if not selected_vcsoy and not selected_standalone:
        errors.append("Merci de sélectionner au moins un produit à facturer.")

    prices = {}
    if selected_vcsoy:
        raw_price = form.get(f"price_{VCSOY_PACKAGE_ID}", "").strip().replace(",", ".")
        try:
            amount = float(raw_price)
            if amount <= 0:
                raise ValueError()
            prices[VCSOY_PACKAGE_ID] = amount
        except ValueError:
            errors.append("Montant hors taxes invalide pour « Voted Customer Service Of the Year (VCSOY) ».")

    for product in selected_standalone:
        raw_price = form.get(f"price_{product['id']}", "").strip().replace(",", ".")
        try:
            amount = float(raw_price)
            if amount <= 0:
                raise ValueError()
            prices[product["id"]] = amount
        except ValueError:
            errors.append(f"Montant hors taxes invalide pour « {product_label(product['id'], data['language'])} ».")

    if errors:
        return errors, data

    line_items = []
    if selected_vcsoy:
        amount = prices[VCSOY_PACKAGE_ID]
        bullets = vcsoy_bullets(data["language"])
        # Un seul produit, indissociable, présenté sur 4 lignes : l'intitulé
        # (sans prix), puis les 3 puces descriptives. Le prix et la quantité
        # de l'ensemble sont portés par la 1ère puce uniquement (comme dans
        # le modèle fourni), les 2 autres puces restant de simples lignes
        # descriptives sans montant.
        line_items.append({
            "role": "vcsoy_heading",
            "description": vcsoy_heading(data["language"], edition_id),
            "is_heading": True,
        })
        line_items.append({
            "role": "vcsoy_priced",
            "description": bullets[0],
            "is_heading": False, "quantity": 1, "unit_price": amount, "total": amount,
        })
        line_items.append({"role": "vcsoy_plain", "description": bullets[1], "is_heading": False})
        line_items.append({"role": "vcsoy_plain", "description": bullets[2], "is_heading": False})

    for product in selected_standalone:
        amount = prices[product["id"]]
        line_items.append({
            "role": "standalone",
            "product_id": product["id"],
            "description": product_label(product["id"], data["language"]),
            "is_heading": False, "quantity": 1, "unit_price": amount, "total": amount,
        })

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
    return render_template(
        "invoicing/list.html", edition=get_edition(edition_id), invoices=invoices,
        edit_payloads=edit_payloads,
        vcsoy_package=VCSOY_PACKAGE, vcsoy_package_id=VCSOY_PACKAGE_ID, standalone_products=STANDALONE_PRODUCTS,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS, error=None,
    )


def _render_list_with_error(error):
    edition_id = get_current_edition_id()
    invoices = Invoice.query.filter_by(edition_id=edition_id).order_by(Invoice.id.desc()).all()
    edit_payloads = {inv.id: _invoice_edit_payload(inv) for inv in invoices}
    return render_template(
        "invoicing/list.html", edition=get_edition(edition_id), invoices=invoices,
        edit_payloads=edit_payloads,
        vcsoy_package=VCSOY_PACKAGE, vcsoy_package_id=VCSOY_PACKAGE_ID, standalone_products=STANDALONE_PRODUCTS,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS, error=error,
    )


@invoicing_bp.route("/create", methods=["GET"])
@login_required
def create_form():
    edition_id = get_current_edition_id()
    participants = _current_participants(edition_id)
    return render_template(
        "invoicing/create.html", edition=get_edition(edition_id), participants=participants,
        participants_json=_participants_json(participants),
        vcsoy_package=VCSOY_PACKAGE, vcsoy_package_id=VCSOY_PACKAGE_ID, standalone_products=STANDALONE_PRODUCTS,
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
            vcsoy_package=VCSOY_PACKAGE, vcsoy_package_id=VCSOY_PACKAGE_ID, standalone_products=STANDALONE_PRODUCTS,
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
