"""
Module « Facturation ».

Permet de générer une facture pour un participant de l'édition en cours :
langue, numéro de facture, numéro de client, date, sélection du
participant puis des produits à facturer (avec leur montant hors taxes).
Les taxes du Québec (TPS/TVQ) sont appliquées automatiquement, sauf pour
un participant facturé hors Canada (exportation de services détaxée).

La facture est ensuite téléchargeable en Excel (à partir du modèle
fourni, pour permettre des ajustements manuels) et en PDF.
"""

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, send_file, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Participant, Invoice, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.invoicing.products import VCSOY_PRODUCTS, STANDALONE_PRODUCTS, vcsoy_heading, product_label
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


def _get_invoice_or_404(invoice_id):
    edition_id = get_current_edition_id()
    invoice = Invoice.query.get(invoice_id)
    if not invoice or invoice.edition_id != edition_id:
        abort(404)
    return invoice


@invoicing_bp.route("/", methods=["GET"])
@login_required
def list_invoices():
    edition_id = get_current_edition_id()
    invoices = Invoice.query.filter_by(edition_id=edition_id).order_by(Invoice.id.desc()).all()
    return render_template(
        "invoicing/list.html", edition=get_edition(edition_id), invoices=invoices,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@invoicing_bp.route("/create", methods=["GET"])
@login_required
def create_form():
    edition_id = get_current_edition_id()
    return render_template(
        "invoicing/create.html", edition=get_edition(edition_id), participants=_current_participants(edition_id),
        vcsoy_products=VCSOY_PRODUCTS, standalone_products=STANDALONE_PRODUCTS,
        errors=[], form_values={}, active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@invoicing_bp.route("/create", methods=["POST"])
@login_required
def create_invoice():
    edition_id = get_current_edition_id()
    edition = get_edition(edition_id)
    form = request.form

    def _redisplay(errors):
        return render_template(
            "invoicing/create.html", edition=edition, participants=_current_participants(edition_id),
            vcsoy_products=VCSOY_PRODUCTS, standalone_products=STANDALONE_PRODUCTS,
            errors=errors, form_values=form, active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
        )

    errors = []

    language = form.get("language", "").strip()
    if language not in ("fr", "en"):
        errors.append("Merci de choisir la langue de la facture.")

    invoice_number = form.get("invoice_number", "").strip()
    if not invoice_number:
        errors.append("Le numéro de facture est obligatoire.")

    customer_number = form.get("customer_number", "").strip()
    if not customer_number:
        errors.append("Le numéro de client est obligatoire.")

    invoice_date = None
    date_raw = form.get("invoice_date", "").strip()
    if not date_raw:
        errors.append("La date de facture est obligatoire.")
    else:
        try:
            invoice_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            errors.append("Date de facture invalide.")

    participant = None
    participant_id = form.get("participant_id", "").strip()
    if not participant_id:
        errors.append("Merci de sélectionner un participant.")
    else:
        participant = Participant.query.get(int(participant_id)) if participant_id.isdigit() else None
        if not participant or participant.edition_id != edition_id:
            errors.append("Participant introuvable pour cette édition.")
            participant = None

    selected_vcsoy = [p for p in VCSOY_PRODUCTS if form.get(f"product_{p['id']}")]
    selected_standalone = [p for p in STANDALONE_PRODUCTS if form.get(f"product_{p['id']}")]
    selected_all = selected_vcsoy + selected_standalone

    if not selected_all:
        errors.append("Merci de sélectionner au moins un produit à facturer.")

    lang_for_labels = language if language in ("fr", "en") else "fr"
    prices = {}
    for product in selected_all:
        raw_price = form.get(f"price_{product['id']}", "").strip().replace(",", ".")
        try:
            amount = float(raw_price)
            if amount <= 0:
                raise ValueError()
            prices[product["id"]] = amount
        except ValueError:
            errors.append(f"Montant hors taxes invalide pour « {product_label(product['id'], lang_for_labels)} ».")

    if errors:
        return _redisplay(errors)

    line_items = []
    if selected_vcsoy:
        line_items.append({
            "description": vcsoy_heading(language, edition["short_label"]),
            "is_heading": True,
        })
        for product in selected_vcsoy:
            amount = prices[product["id"]]
            line_items.append({
                "description": product_label(product["id"], language),
                "is_heading": False, "quantity": 1, "unit_price": amount, "total": amount,
            })
    for product in selected_standalone:
        amount = prices[product["id"]]
        line_items.append({
            "description": product_label(product["id"], language),
            "is_heading": False, "quantity": 1, "unit_price": amount, "total": amount,
        })

    subtotal = sum(i["total"] for i in line_items if not i.get("is_heading"))
    tax = compute_taxes(subtotal, participant.billing_country)

    invoice = Invoice(
        edition_id=edition_id,
        participant_id=participant.id,
        language=language,
        invoice_number=invoice_number,
        customer_number=customer_number,
        invoice_date=invoice_date,
        bill_to_contact_name=participant.billing_contact_name or participant.representative_name,
        bill_to_company_name=participant.participant_name,
        bill_to_address1=participant.billing_address1,
        bill_to_address2=participant.billing_address2,
        bill_to_city=participant.billing_city,
        bill_to_postal_code=participant.billing_postal_code,
        bill_to_country=participant.billing_country,
        line_items=line_items,
        subtotal=subtotal,
        gst_amount=tax["gst"],
        qst_amount=tax["qst"],
        total_amount=tax["total"],
        is_export=tax["is_export"],
        created_by_id=current_user.id,
    )
    db.session.add(invoice)
    db.session.commit()

    _log("Création facture", details=f"{invoice_number} — {participant.participant_name} (édition {edition_id})")

    return redirect(url_for("invoicing.preview_invoice", invoice_id=invoice.id))


@invoicing_bp.route("/<int:invoice_id>", methods=["GET"])
@login_required
def preview_invoice(invoice_id):
    invoice = _get_invoice_or_404(invoice_id)
    return render_template(
        "invoicing/preview.html", edition=get_edition(get_current_edition_id()), invoice=invoice,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


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
