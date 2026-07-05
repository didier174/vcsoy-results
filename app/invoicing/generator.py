"""
Génération de la facture, dans les deux formats demandés :
- Excel : à partir du modèle fourni (assets/invoice_template.xlsx), en ne
  modifiant que les cellules variables (dates, montants, adresse du
  participant...) — toute la mise en forme, le logo et les informations de
  l'émetteur (CA2D) restent ceux du modèle d'origine.
- PDF : mise en page indépendante, générée avec reportlab (pas de
  dépendance à un logiciel externe type LibreOffice, ce qui garde le
  déploiement simple).
"""

import io
import os

import openpyxl
from openpyxl.styles import Font

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "invoice_template.xlsx")

FIRST_ITEM_ROW = 27
MAX_ITEM_ROW = 35

LABELS = {
    "fr": {
        "invoice_title": "FACTURE",
        "date": "DATE",
        "invoice_no": "No de facture :",
        "customer_no": "No de client :",
        "bill_to": "Facturé à",
        "description": "DESCRIPTION",
        "quantity": "QUANTITÉ",
        "unit_price": "PRIX UNITAIRE",
        "total": "TOTAL",
        "subtotal": "SOUS-TOTAL",
        "gst": "TPS",
        "qst": "TVQ",
        "total_cad": "TOTAL CAD",
        "export_note": "TPS/TVQ : 0 % – Exportation de services à un non-résident (fourniture détaxée)",
        "payment_intro": "Virement bancaire ou chèque",
    },
    "en": {
        "invoice_title": "INVOICE",
        "date": "DATE",
        "invoice_no": "Invoice No:",
        "customer_no": "Customer No:",
        "bill_to": "Bill to",
        "description": "DESCRIPTION",
        "quantity": "QUANTITY",
        "unit_price": "UNIT PRICE",
        "total": "TOTAL",
        "subtotal": "SUB TOTAL",
        "gst": "TPS",
        "qst": "TVQ",
        "total_cad": "TOTAL CAD",
        "export_note": "GST/QST: 0% – Export of services to a non-resident (zero-rated supply)",
        "payment_intro": "Wire transfert or check",
    },
}


def _labels_for(language):
    return LABELS.get(language, LABELS["fr"])


def _bill_to_address_lines(invoice):
    addr_line = invoice.bill_to_address1 or ""
    if invoice.bill_to_address2:
        addr_line = f"{addr_line}, {invoice.bill_to_address2}" if addr_line else invoice.bill_to_address2
    city_line = ", ".join(p for p in [invoice.bill_to_city, invoice.bill_to_postal_code] if p)
    return addr_line, city_line


# ------------------------------------------------------------------ Excel

def fill_invoice_xlsx(invoice):
    """Retourne un BytesIO contenant le fichier Excel de la facture."""
    wb = openpyxl.load_workbook(TEMPLATE_PATH)
    ws = wb["Feuil1"]
    labels = _labels_for(invoice.language)

    ws["AH1"] = labels["invoice_title"]
    ws["W5"] = labels["invoice_no"]
    ws["W6"] = labels["customer_no"]
    ws["W10"] = labels["bill_to"]
    ws["A22"] = labels["description"]
    ws["U22"] = labels["quantity"]
    ws["Z22"] = labels["unit_price"]
    ws["AF22"] = labels["total"]
    ws["Y38"] = labels["subtotal"]
    ws["Y39"] = labels["gst"]
    ws["Y40"] = labels["qst"]
    ws["Y41"] = labels["total_cad"]
    ws["B46"] = labels["payment_intro"]

    ws["AC4"] = invoice.invoice_date
    ws["AC5"] = invoice.invoice_number
    ws["AC6"] = invoice.customer_number

    ws["W12"] = invoice.bill_to_contact_name
    ws["W14"] = invoice.bill_to_company_name
    addr_line, city_line = _bill_to_address_lines(invoice)
    ws["W15"] = addr_line
    ws["W16"] = city_line
    ws["W17"] = invoice.bill_to_country

    row = FIRST_ITEM_ROW
    for item in invoice.line_items:
        if row > MAX_ITEM_ROW:
            break  # garde-fou : ne devrait pas arriver (5 produits maximum)
        desc_cell = ws[f"A{row}"]
        desc_cell.value = item["description"]
        desc_cell.font = Font(
            name=desc_cell.font.name, size=desc_cell.font.size, bold=bool(item.get("is_heading"))
        )
        if not item.get("is_heading"):
            ws[f"U{row}"] = item["quantity"]
            ws[f"Z{row}"] = item["unit_price"]
            ws[f"AF{row}"] = item["total"]
        row += 1

    ws["AF38"] = invoice.subtotal
    ws["AF39"] = invoice.gst_amount
    ws["AF40"] = invoice.qst_amount
    ws["AF41"] = invoice.total_amount

    ws["B40"] = labels["export_note"] if invoice.is_export else ""

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# -------------------------------------------------------------------- PDF

def render_invoice_pdf(invoice):
    labels = _labels_for(invoice.language)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter, topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
    )

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("normal9", parent=styles["Normal"], fontSize=9, leading=13)
    title_style = ParagraphStyle("title", parent=styles["Title"], alignment=TA_RIGHT, fontSize=24)
    note_style = ParagraphStyle("note", parent=normal, fontSize=8, textColor=colors.grey)
    footer_style = ParagraphStyle("footer", parent=normal, fontSize=8)

    elements = []

    header_data = [[
        Paragraph(
            "<b>CA2D Inc.</b><br/>1203 Avenue Bernard<br/>MONTREAL, QC, H2V 1V7<br/>CANADA<br/>"
            "Phone: +1 514 690 3652<br/>TPS: 811652985RT001<br/>TVQ: 1222850718",
            normal,
        ),
        Paragraph(labels["invoice_title"], title_style),
    ]]
    header_table = Table(header_data, colWidths=[300, 195])
    header_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elements.append(header_table)
    elements.append(Spacer(1, 16))

    meta_data = [
        [labels["date"], invoice.invoice_date.strftime("%Y-%m-%d") if invoice.invoice_date else ""],
        [labels["invoice_no"], invoice.invoice_number or ""],
        [labels["customer_no"], invoice.customer_number or ""],
    ]
    meta_table = Table(meta_data, colWidths=[85, 110])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "LEFT"),
    ]))

    addr_line, city_line = _bill_to_address_lines(invoice)
    bill_to_parts = [
        invoice.bill_to_contact_name, invoice.bill_to_company_name, addr_line, city_line, invoice.bill_to_country,
    ]
    bill_to_text = "<br/>".join(p for p in bill_to_parts if p)
    bill_to_para = Paragraph(f"<b>{labels['bill_to']}</b><br/>{bill_to_text}", normal)

    top_table = Table([[bill_to_para, meta_table]], colWidths=[300, 195])
    top_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elements.append(top_table)
    elements.append(Spacer(1, 22))

    table_data = [[labels["description"], labels["quantity"], labels["unit_price"], labels["total"]]]
    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A1A1A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
        ("LEFTPADDING", (0, 1), (0, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i, item in enumerate(invoice.line_items, start=1):
        if item.get("is_heading"):
            table_data.append([item["description"], "", "", ""])
            style_commands.append(("SPAN", (0, i), (-1, i)))
            style_commands.append(("FONTNAME", (0, i), (0, i), "Helvetica-Bold"))
            style_commands.append(("ALIGN", (0, i), (0, i), "LEFT"))
        else:
            table_data.append([
                "- " + item["description"],
                f"{item['quantity']:.2f}",
                f"{item['unit_price']:,.2f} $",
                f"{item['total']:,.2f} $",
            ])
            style_commands.append(("ALIGN", (0, i), (0, i), "LEFT"))

    products_table = Table(table_data, colWidths=[255, 70, 90, 90])
    products_table.setStyle(TableStyle(style_commands))
    elements.append(products_table)
    elements.append(Spacer(1, 16))

    totals_data = [
        [labels["subtotal"], f"{invoice.subtotal:,.2f} $"],
        [labels["gst"], f"{invoice.gst_amount:,.2f} $"],
        [labels["qst"], f"{invoice.qst_amount:,.2f} $"],
        [labels["total_cad"], f"{invoice.total_amount:,.2f} $"],
    ]
    totals_table = Table(totals_data, colWidths=[110, 100])
    totals_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    wrapper = Table([[None, totals_table]], colWidths=[295, 210])
    elements.append(wrapper)

    if invoice.is_export:
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(labels["export_note"], note_style))

    elements.append(Spacer(1, 34))
    elements.append(Paragraph(
        f"<b>{labels['payment_intro']}</b><br/>CA2D Inc<br/>"
        "Bank: RBC 1 Place Ville-Marie, Montréal, QC H3B 3Y1<br/>"
        "Swift: ROYCCAT2MIC<br/>"
        "Institution Number: 003 &nbsp;&nbsp; Transit Number: 04896 &nbsp;&nbsp; Account Number: 1009836",
        footer_style,
    ))

    doc.build(elements)
    buf.seek(0)
    return buf
