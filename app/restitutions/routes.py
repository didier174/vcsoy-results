"""
Module « Restitution ».

Même principe que « Rapport d'étude » (voir app/reports/routes.py) : liste
des présentations de restitution existantes (nom + date de création),
chargement d'un modèle de présentation (.pptx, stocké en base comme les
rapports), création d'une restitution pour un participant à partir d'un
modèle (balises {{ ... }} remplacées par ses données, même moteur que le
rapport d'étude — voir reports/generator.py et reports/report_data.py),
chargement direct d'une restitution déjà prête depuis le disque local,
téléchargement et suppression de restitutions.

Le futur enrichissement (identification par canal des 3 tests les moins
bien notés, récupération de leurs records, caviardage et insertion dans la
présentation) sera ajouté une fois le modèle de présentation finalisé.
"""

import io
import mimetypes
import re

from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from pptx import Presentation

from app.access_control import admin_required
from app.extensions import db
from app.models import Restitution, RestitutionTemplate, Participant, TestResult, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.reports.generator import substitute_tags
from app.reports.report_cache import get_fresh_edition_cache
from app.reports.report_data import build_participant_placeholders
from app.restitutions.debrief_visuals import apply_debrief_visuals

restitutions_bp = Blueprint("restitutions", __name__, url_prefix="/restitutions")

ACTIVE_ITEM = "Restitution"
ACTIVE_ITEM_SELECT_TESTS = "Selection test pour restitution"
ACTIVE_ITEM_REDACT_RECORDS = "Caviarder des records"

RESTITUTION_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _sanitize_restitution_filename(raw):
    """
    Nettoie le nom de fichier saisi par l'utilisateur : retire une
    éventuelle extension .pptx déjà tapée (l'extension est toujours
    imposée par le serveur) et remplace les caractères interdits dans un
    nom de fichier, sans toucher aux accents/espaces.
    """
    name = re.sub(r"\.pptx$", "", raw.strip(), flags=re.IGNORECASE)
    name = FILENAME_UNSAFE_RE.sub("_", name).strip()
    return name or "Restitution"


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id, user_email=current_user.email,
        edition_id=get_current_edition_id(), action=action, details=details,
    )
    db.session.add(entry)
    db.session.commit()


@restitutions_bp.route("/", methods=["GET"])
@login_required
def list_restitutions():
    edition_id = get_current_edition_id()
    # defer(file_data) : voir reports.list_reports, même raison (éviter de
    # charger en mémoire le contenu binaire complet de toutes les
    # présentations déjà générées à chaque affichage de cette liste).
    restitutions = (
        Restitution.query.options(db.defer(Restitution.file_data))
        .filter_by(edition_id=edition_id).order_by(Restitution.created_at.desc()).all()
    )
    templates = (
        RestitutionTemplate.query.options(db.defer(RestitutionTemplate.file_data))
        .filter_by(edition_id=edition_id).order_by(RestitutionTemplate.uploaded_at.desc()).all()
    )
    participants = Participant.query.filter_by(edition_id=edition_id).order_by(Participant.participant_name).all()
    edition = get_edition(edition_id)
    return render_template(
        "restitutions/list.html", edition=edition, restitutions=restitutions, templates=templates,
        participants=participants, active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@restitutions_bp.route("/selection-tests", methods=["GET"])
@login_required
def select_tests():
    """Choix, par canal, des tests les moins bien notés à insérer (records
    caviardés) dans la restitution — fonctionnalité en cours de réflexion,
    page en place pour la navigation en attendant sa conception."""
    edition_id = get_current_edition_id()
    edition = get_edition(edition_id)
    return render_template(
        "restitutions/select_tests.html", edition=edition,
        active_item=ACTIVE_ITEM_SELECT_TESTS, menu_items=MENU_ITEMS,
    )


@restitutions_bp.route("/caviardage", methods=["GET"])
@login_required
def redact_records():
    """Caviardage des records sélectionnés avant insertion dans la
    restitution — fonctionnalité en cours de réflexion, page en place pour
    la navigation en attendant sa conception."""
    edition_id = get_current_edition_id()
    edition = get_edition(edition_id)
    return render_template(
        "restitutions/redact_records.html", edition=edition,
        active_item=ACTIVE_ITEM_REDACT_RECORDS, menu_items=MENU_ITEMS,
    )


@restitutions_bp.route("/templates/upload", methods=["POST"])
@login_required
def upload_template():
    edition_id = get_current_edition_id()
    file = request.files.get("template_file")
    if not file or not file.filename:
        flash("Merci de choisir un fichier avant de cliquer sur « Charger ».", "error")
        return redirect(url_for("restitutions.list_restitutions"))

    filename = file.filename
    content = file.read()
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    db.session.add(RestitutionTemplate(
        edition_id=edition_id, filename=filename, content_type=content_type,
        file_data=content, file_size=len(content), uploaded_by_id=current_user.id,
    ))
    db.session.commit()

    _log("Chargement d'un modèle de restitution", details=f"{filename} (édition {edition_id})")
    flash(f"Modèle « {filename} » chargé avec succès.", "success")
    return redirect(url_for("restitutions.list_restitutions"))


@restitutions_bp.route("/templates/delete", methods=["POST"])
@login_required
@admin_required
def delete_templates():
    edition_id = get_current_edition_id()
    selected_ids = [int(i) for i in request.form.getlist("template_ids") if i.isdigit()]
    if not selected_ids:
        flash("Merci de choisir au moins un modèle à supprimer.", "error")
        return redirect(url_for("restitutions.list_restitutions"))

    to_delete = RestitutionTemplate.query.options(db.defer(RestitutionTemplate.file_data)).filter(
        RestitutionTemplate.edition_id == edition_id, RestitutionTemplate.id.in_(selected_ids)
    ).all()
    deleted = len(to_delete)
    names = ", ".join(t.filename for t in to_delete)

    ids = [t.id for t in to_delete]
    Restitution.query.filter(Restitution.restitution_template_id.in_(ids)).update(
        {"restitution_template_id": None}, synchronize_session=False
    )
    for template in to_delete:
        db.session.delete(template)
    db.session.commit()

    _log("Suppression de modèle(s) de restitution", details=f"{deleted} supprimé(s) (édition {edition_id}) : {names}")
    flash(f"{deleted} modèle(s) supprimé(s).", "success")
    return redirect(url_for("restitutions.list_restitutions"))


@restitutions_bp.route("/new", methods=["POST"])
@login_required
def create_restitution():
    edition_id = get_current_edition_id()
    template_id = request.form.get("template_id", "").strip()
    participant_id = request.form.get("participant_id", "").strip()
    restitution_filename = request.form.get("restitution_filename", "").strip()

    if not template_id.isdigit() or not participant_id.isdigit() or not restitution_filename:
        flash("Merci de choisir un modèle, un participant et un nom de fichier.", "error")
        return redirect(url_for("restitutions.list_restitutions"))

    template = RestitutionTemplate.query.filter_by(id=int(template_id), edition_id=edition_id).first()
    participant = Participant.query.filter_by(id=int(participant_id), edition_id=edition_id).first()
    if not template or not participant:
        flash("Modèle ou participant introuvable pour cette édition.", "error")
        return redirect(url_for("restitutions.list_restitutions"))

    # Même passerelle que le rapport d'étude (voir reports.create_report) :
    # la restitution compare elle aussi chaque participant à l'ensemble des
    # résultats de l'édition, via le même cache d'agrégats précalculé par
    # « Liste des lauréats » — pour ne pas recharger/retraiter tous les
    # tests de l'édition à chaque présentation générée.
    cache = get_fresh_edition_cache(edition_id)
    if cache is None or not cache["has_winners"]:
        flash(
            "Aucun lauréat n'a pu être déterminé pour cette édition (aucun "
            "résultat chargé, ou aucun participant n'atteint 11,5/20 et le "
            "1er rang de sa catégorie), ou les résultats ont changé depuis "
            "le dernier calcul. La restitution ne peut pas être générée : "
            "chargez les fichiers de résultats de toute l'édition, vérifiez "
            "« Liste des lauréats », puis réessayez.",
            "error",
        )
        return redirect(url_for("restitutions.list_restitutions"))

    # Seuls les tests de CE participant sont chargés ici (pas ceux de toute
    # l'édition) : le reste vient du cache ci-dessus.
    participant_tests = TestResult.query.filter_by(edition_id=edition_id, participant_id=participant.id).all()
    values = build_participant_placeholders(participant, edition_id, cache, all_tests=participant_tests)

    prs = Presentation(io.BytesIO(template.file_data))

    unknown_tags = substitute_tags(prs, values)

    if unknown_tags:
        flash(
            "Ce modèle contient des balises non reconnues : {{ "
            + " }}, {{ ".join(sorted(unknown_tags))
            + " }}. La restitution n'a pas été générée.",
            "error",
        )
        return redirect(url_for("restitutions.list_restitutions"))

    # Graphiques de comparaison/classement + répartition verte/rouge des
    # critères (voir debrief_visuals.py) : best-effort — si le modèle de
    # restitution ne correspond pas à la structure attendue (nom/position
    # de forme différente), on préfère livrer la présentation avec les
    # balises texte déjà remplies plutôt que de faire échouer toute la
    # génération.
    try:
        apply_debrief_visuals(prs, participant, cache, values)
    except Exception:
        current_app.logger.exception("Échec de la mise à jour des graphiques natifs de la restitution")

    out = io.BytesIO()
    prs.save(out)
    file_bytes = out.getvalue()

    name = _sanitize_restitution_filename(restitution_filename)
    filename = f"{name}.pptx"

    restitution = Restitution(
        edition_id=edition_id, name=name, participant_id=participant.id, restitution_template_id=template.id,
        filename=filename, content_type=RESTITUTION_CONTENT_TYPE,
        file_data=file_bytes, file_size=len(file_bytes), created_by_id=current_user.id,
    )
    db.session.add(restitution)
    db.session.commit()

    _log("Création d'une restitution", details=f"{name} (édition {edition_id})")
    flash(f"Restitution « {name} » créée avec succès.", "success")
    return redirect(url_for("restitutions.list_restitutions"))


@restitutions_bp.route("/upload", methods=["POST"])
@login_required
def upload_restitution():
    edition_id = get_current_edition_id()
    file = request.files.get("restitution_file")
    if not file or not file.filename:
        flash("Merci de choisir un fichier avant de cliquer sur « Charger ».", "error")
        return redirect(url_for("restitutions.list_restitutions"))

    if not file.filename.lower().endswith(".pptx"):
        flash("Seul le format .pptx est accepté pour une restitution.", "error")
        return redirect(url_for("restitutions.list_restitutions"))

    base_name = _sanitize_restitution_filename(file.filename)
    content = file.read()

    restitution = Restitution(
        edition_id=edition_id, name=base_name, filename=f"{base_name}.pptx",
        content_type=RESTITUTION_CONTENT_TYPE, file_data=content, file_size=len(content),
        created_by_id=current_user.id,
    )
    db.session.add(restitution)
    db.session.commit()

    _log("Chargement direct d'une restitution", details=f"{base_name} (édition {edition_id})")
    flash(f"Restitution « {base_name} » chargée avec succès.", "success")
    return redirect(url_for("restitutions.list_restitutions"))


@restitutions_bp.route("/<int:restitution_id>/download", methods=["GET"])
@login_required
def download_restitution(restitution_id):
    edition_id = get_current_edition_id()
    restitution = Restitution.query.filter_by(id=restitution_id, edition_id=edition_id).first()
    if not restitution:
        return "Restitution introuvable pour cette édition.", 404

    return send_file(
        io.BytesIO(restitution.file_data), mimetype=restitution.content_type or RESTITUTION_CONTENT_TYPE,
        as_attachment=True, download_name=restitution.filename or f"{restitution.name}.pptx",
    )


@restitutions_bp.route("/delete", methods=["POST"])
@login_required
@admin_required
def delete_restitutions():
    edition_id = get_current_edition_id()
    selected_ids = [int(i) for i in request.form.getlist("selected_ids") if i.isdigit()]
    if not selected_ids:
        flash("Merci de choisir au moins une restitution à supprimer.", "error")
        return redirect(url_for("restitutions.list_restitutions"))

    to_delete = Restitution.query.options(db.defer(Restitution.file_data)).filter(
        Restitution.edition_id == edition_id, Restitution.id.in_(selected_ids)
    ).all()
    deleted = len(to_delete)
    names = ", ".join(r.name for r in to_delete)
    for restitution in to_delete:
        db.session.delete(restitution)
    db.session.commit()

    _log("Suppression de restitution(s)", details=f"{deleted} supprimé(s) (édition {edition_id}) : {names}")
    flash(f"{deleted} restitution(s) supprimée(s).", "success")
    return redirect(url_for("restitutions.list_restitutions"))
