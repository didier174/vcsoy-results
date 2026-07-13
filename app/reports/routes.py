"""
Module « Rapport d'étude ».

Liste des rapports d'études existants (nom + date de création),
chargement d'un modèle de rapport (.pptx, stocké en base comme les
records de test), création d'un rapport pour un participant à partir
d'un modèle (balises {{ ... }} remplacées par ses données, voir
generator.py/report_data.py), téléchargement et suppression de rapports.

La fonctionnalité « Modifier » sera définie dans une prochaine étape.
"""

import io
import mimetypes
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user

from app.access_control import admin_required
from app.extensions import db
from app.models import StudyReport, ReportTemplate, Participant, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.reports.generator import render_template as render_report_template
from app.reports.report_data import build_participant_placeholders

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

ACTIVE_ITEM = "Rapport d'étude"

REPORT_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _sanitize_report_filename(raw):
    """
    Nettoie le nom de fichier saisi par l'utilisateur : retire une
    éventuelle extension .pptx déjà tapée (l'extension est toujours
    imposée par le serveur) et remplace les caractères interdits dans un
    nom de fichier, sans toucher aux accents/espaces.
    """
    name = re.sub(r"\.pptx$", "", raw.strip(), flags=re.IGNORECASE)
    name = FILENAME_UNSAFE_RE.sub("_", name).strip()
    return name or "Rapport"


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id, user_email=current_user.email,
        edition_id=get_current_edition_id(), action=action, details=details,
    )
    db.session.add(entry)
    db.session.commit()


@reports_bp.route("/", methods=["GET"])
@login_required
def list_reports():
    edition_id = get_current_edition_id()
    reports = StudyReport.query.filter_by(edition_id=edition_id).order_by(StudyReport.created_at.desc()).all()
    templates = ReportTemplate.query.filter_by(edition_id=edition_id).order_by(ReportTemplate.uploaded_at.desc()).all()
    participants = Participant.query.filter_by(edition_id=edition_id).order_by(Participant.participant_name).all()
    edition = get_edition(edition_id)
    return render_template(
        "reports/list.html", edition=edition, reports=reports, templates=templates, participants=participants,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@reports_bp.route("/templates/upload", methods=["POST"])
@login_required
def upload_template():
    edition_id = get_current_edition_id()
    file = request.files.get("template_file")
    if not file or not file.filename:
        flash("Merci de choisir un fichier avant de cliquer sur « Charger ».", "error")
        return redirect(url_for("reports.list_reports"))

    filename = file.filename
    content = file.read()
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    db.session.add(ReportTemplate(
        edition_id=edition_id, filename=filename, content_type=content_type,
        file_data=content, file_size=len(content), uploaded_by_id=current_user.id,
    ))
    db.session.commit()

    _log("Chargement d'un modèle de rapport", details=f"{filename} (édition {edition_id})")
    flash(f"Modèle « {filename} » chargé avec succès.", "success")
    return redirect(url_for("reports.list_reports"))


@reports_bp.route("/templates/delete", methods=["POST"])
@login_required
@admin_required
def delete_templates():
    edition_id = get_current_edition_id()
    selected_ids = [int(i) for i in request.form.getlist("template_ids") if i.isdigit()]
    if not selected_ids:
        flash("Merci de choisir au moins un modèle à supprimer.", "error")
        return redirect(url_for("reports.list_reports"))

    to_delete = ReportTemplate.query.filter(
        ReportTemplate.edition_id == edition_id, ReportTemplate.id.in_(selected_ids)
    ).all()
    deleted = len(to_delete)
    names = ", ".join(t.filename for t in to_delete)

    ids = [t.id for t in to_delete]
    StudyReport.query.filter(StudyReport.report_template_id.in_(ids)).update(
        {"report_template_id": None}, synchronize_session=False
    )
    for template in to_delete:
        db.session.delete(template)
    db.session.commit()

    _log("Suppression de modèle(s) de rapport", details=f"{deleted} supprimé(s) (édition {edition_id}) : {names}")
    flash(f"{deleted} modèle(s) supprimé(s).", "success")
    return redirect(url_for("reports.list_reports"))


@reports_bp.route("/new", methods=["POST"])
@login_required
def create_report():
    edition_id = get_current_edition_id()
    template_id = request.form.get("template_id", "").strip()
    participant_id = request.form.get("participant_id", "").strip()
    report_filename = request.form.get("report_filename", "").strip()

    if not template_id.isdigit() or not participant_id.isdigit() or not report_filename:
        flash("Merci de choisir un modèle, un participant et un nom de fichier.", "error")
        return redirect(url_for("reports.list_reports"))

    template = ReportTemplate.query.filter_by(id=int(template_id), edition_id=edition_id).first()
    participant = Participant.query.filter_by(id=int(participant_id), edition_id=edition_id).first()
    if not template or not participant:
        flash("Modèle ou participant introuvable pour cette édition.", "error")
        return redirect(url_for("reports.list_reports"))

    values = build_participant_placeholders(participant, edition_id)
    file_bytes, unknown_tags = render_report_template(template.file_data, values)

    if unknown_tags:
        flash(
            "Ce modèle contient des balises non reconnues : {{ "
            + " }}, {{ ".join(sorted(unknown_tags))
            + " }}. Le rapport n'a pas été généré.",
            "error",
        )
        return redirect(url_for("reports.list_reports"))

    name = _sanitize_report_filename(report_filename)
    filename = f"{name}.pptx"

    report = StudyReport(
        edition_id=edition_id, name=name, participant_id=participant.id, report_template_id=template.id,
        filename=filename, content_type=REPORT_CONTENT_TYPE,
        file_data=file_bytes, file_size=len(file_bytes), created_by_id=current_user.id,
    )
    db.session.add(report)
    db.session.commit()

    _log("Création d'un rapport d'étude", details=f"{name} (édition {edition_id})")
    flash(f"Rapport « {name} » créé avec succès.", "success")
    return redirect(url_for("reports.list_reports"))


@reports_bp.route("/<int:report_id>/download", methods=["GET"])
@login_required
def download_report(report_id):
    edition_id = get_current_edition_id()
    report = StudyReport.query.filter_by(id=report_id, edition_id=edition_id).first()
    if not report:
        return "Rapport introuvable pour cette édition.", 404

    return send_file(
        io.BytesIO(report.file_data), mimetype=report.content_type or REPORT_CONTENT_TYPE,
        as_attachment=True, download_name=report.filename or f"{report.name}.pptx",
    )


@reports_bp.route("/delete", methods=["POST"])
@login_required
@admin_required
def delete_reports():
    edition_id = get_current_edition_id()
    selected_ids = [int(i) for i in request.form.getlist("selected_ids") if i.isdigit()]
    if not selected_ids:
        flash("Merci de choisir au moins un rapport à supprimer.", "error")
        return redirect(url_for("reports.list_reports"))

    to_delete = StudyReport.query.filter(
        StudyReport.edition_id == edition_id, StudyReport.id.in_(selected_ids)
    ).all()
    deleted = len(to_delete)
    names = ", ".join(r.name for r in to_delete)
    for report in to_delete:
        db.session.delete(report)
    db.session.commit()

    _log("Suppression de rapport(s) d'études", details=f"{deleted} supprimé(s) (édition {edition_id}) : {names}")
    flash(f"{deleted} rapport(s) supprimé(s).", "success")
    return redirect(url_for("reports.list_reports"))
