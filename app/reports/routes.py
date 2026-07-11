"""
Module « Rapport d'études ».

Étape initiale : liste des rapports d'études existants (nom + date de
création), chargement d'un modèle de rapport (fichier de base, stocké en
base comme les records de test), et suppression de rapports sélectionnés.
Les fonctionnalités « Créer » et « Modifier » seront définies dans une
prochaine étape.
"""

import mimetypes

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.access_control import admin_required
from app.extensions import db
from app.models import StudyReport, ReportTemplate, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

ACTIVE_ITEM = "Rapport d'études"


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
    edition = get_edition(edition_id)
    return render_template(
        "reports/list.html", edition=edition, reports=reports,
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
