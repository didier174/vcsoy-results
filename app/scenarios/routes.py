"""
Module « Gestion des scénarios » > « Générer des scénarios ».

Modèles de scénarios (Book scénario / Problématiques) chargés par
l'utilisateur. Le bouton « Générer un book » crée (ou réutilise, s'ils
existent déjà) les fichiers Book scénario et Problématiques d'un
participant, puis appelle Claude Sonnet 5 (voir ai_generation.py) pour
rechercher sur le vrai site web du participant et générer 10 nouveaux
scénarios, ajoutés dans la feuille « step 1 » du Book (colonnes A-G ; H-K
réservées à « Générer les tests ») et référencés dans le PowerPoint
Problématiques (numéro + URL source).

« Générer les tests » sera spécifié dans une prochaine étape.
"""

import io
import mimetypes
import os
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user

from app.access_control import admin_required
from app.extensions import db
from app.models import ScenarioTemplate, ScenarioFile, Participant, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.scenarios import ai_generation, excel_utils, pptx_utils

scenarios_bp = Blueprint("scenarios", __name__, url_prefix="/scenarios")

ACTIVE_ITEM_GENERATE = "Générer des scénarios"
ACTIVE_ITEM_TESTS = "Générer les tests"

KIND_LABELS = {
    ScenarioTemplate.KIND_BOOK: "Book scénario",
    ScenarioTemplate.KIND_PROBLEMATIQUES: "Problématiques",
}

FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _sanitize_filename(raw):
    name = FILENAME_UNSAFE_RE.sub("_", raw.strip())
    return name or "Fichier"


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id, user_email=current_user.email,
        edition_id=get_current_edition_id(), action=action, details=details,
    )
    db.session.add(entry)
    db.session.commit()


@scenarios_bp.route("/", methods=["GET"])
@login_required
def index():
    return redirect(url_for("scenarios.generate_scenarios"))


@scenarios_bp.route("/generate", methods=["GET"])
@login_required
def generate_scenarios():
    edition_id = get_current_edition_id()
    templates = (
        ScenarioTemplate.query.filter_by(edition_id=edition_id).order_by(ScenarioTemplate.uploaded_at.desc()).all()
    )
    files = ScenarioFile.query.filter_by(edition_id=edition_id).order_by(ScenarioFile.created_at.desc()).all()
    participants = Participant.query.filter_by(edition_id=edition_id).order_by(Participant.participant_name).all()
    book_templates = [t for t in templates if t.kind == ScenarioTemplate.KIND_BOOK]
    problematiques_templates = [t for t in templates if t.kind == ScenarioTemplate.KIND_PROBLEMATIQUES]
    edition = get_edition(edition_id)
    return render_template(
        "scenarios/generate.html", edition=edition, templates=templates, files=files, participants=participants,
        book_templates=book_templates, problematiques_templates=problematiques_templates, kind_labels=KIND_LABELS,
        active_item=ACTIVE_ITEM_GENERATE, menu_items=MENU_ITEMS,
    )


@scenarios_bp.route("/templates/upload", methods=["POST"])
@login_required
def upload_template():
    edition_id = get_current_edition_id()
    kind = request.form.get("kind", "").strip()
    if kind not in (ScenarioTemplate.KIND_BOOK, ScenarioTemplate.KIND_PROBLEMATIQUES):
        flash("Type de modèle invalide.", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    file = request.files.get("template_file")
    if not file or not file.filename:
        flash("Merci de choisir un fichier avant de cliquer sur « Charger ».", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    filename = file.filename
    content = file.read()
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    db.session.add(ScenarioTemplate(
        edition_id=edition_id, kind=kind, filename=filename, content_type=content_type,
        file_data=content, file_size=len(content), uploaded_by_id=current_user.id,
    ))
    db.session.commit()

    _log("Chargement d'un modèle de scénario", details=f"{KIND_LABELS[kind]} : {filename} (édition {edition_id})")
    flash(f"Modèle « {filename} » chargé avec succès.", "success")
    return redirect(url_for("scenarios.generate_scenarios"))


@scenarios_bp.route("/templates/delete", methods=["POST"])
@login_required
@admin_required
def delete_templates():
    edition_id = get_current_edition_id()
    selected_ids = [int(i) for i in request.form.getlist("template_ids") if i.isdigit()]
    if not selected_ids:
        flash("Merci de choisir au moins un modèle à supprimer.", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    to_delete = ScenarioTemplate.query.filter(
        ScenarioTemplate.edition_id == edition_id, ScenarioTemplate.id.in_(selected_ids)
    ).all()
    deleted = len(to_delete)
    names = ", ".join(t.filename for t in to_delete)

    ids = [t.id for t in to_delete]
    ScenarioFile.query.filter(ScenarioFile.source_template_id.in_(ids)).update(
        {"source_template_id": None}, synchronize_session=False
    )
    for template in to_delete:
        db.session.delete(template)
    db.session.commit()

    _log("Suppression de modèle(s) de scénario", details=f"{deleted} supprimé(s) (édition {edition_id}) : {names}")
    flash(f"{deleted} modèle(s) supprimé(s).", "success")
    return redirect(url_for("scenarios.generate_scenarios"))


SCENARIOS_PER_BATCH = 10


@scenarios_bp.route("/new", methods=["POST"])
@login_required
def create_scenario_files():
    edition_id = get_current_edition_id()
    edition = get_edition(edition_id)
    book_template_id = request.form.get("book_template_id", "").strip()
    problematiques_template_id = request.form.get("problematiques_template_id", "").strip()
    participant_id = request.form.get("participant_id", "").strip()
    website_url = request.form.get("website_url", "").strip()

    if (
        not book_template_id.isdigit()
        or not problematiques_template_id.isdigit()
        or not participant_id.isdigit()
        or not website_url
    ):
        flash(
            "Merci de choisir un modèle de Book scénario, un modèle de Problématiques, "
            "un participant et de saisir l'URL de son site web.",
            "error",
        )
        return redirect(url_for("scenarios.generate_scenarios"))

    book_template = ScenarioTemplate.query.filter_by(
        id=int(book_template_id), edition_id=edition_id, kind=ScenarioTemplate.KIND_BOOK
    ).first()
    problematiques_template = ScenarioTemplate.query.filter_by(
        id=int(problematiques_template_id), edition_id=edition_id, kind=ScenarioTemplate.KIND_PROBLEMATIQUES
    ).first()
    participant = Participant.query.filter_by(id=int(participant_id), edition_id=edition_id).first()

    if not book_template or not problematiques_template or not participant:
        flash("Modèle ou participant introuvable pour cette édition.", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    base_suffix = _sanitize_filename(f"{participant.participant_name}_{edition['short_label']}").replace(" ", "_")
    book_name = f"Book_scénario_{base_suffix}"
    problematiques_name = f"Problématiques_{base_suffix}"

    book_file = ScenarioFile.query.filter_by(
        edition_id=edition_id, participant_id=participant.id, name=book_name
    ).first()
    if not book_file:
        book_ext = os.path.splitext(book_template.filename or "")[1] or ""
        book_file = ScenarioFile(
            edition_id=edition_id, kind=ScenarioTemplate.KIND_BOOK, name=book_name,
            participant_id=participant.id, source_template_id=book_template.id,
            filename=f"{book_name}{book_ext}", content_type=book_template.content_type,
            file_data=book_template.file_data, file_size=book_template.file_size,
            created_by_id=current_user.id,
        )
        db.session.add(book_file)

    problematiques_file = ScenarioFile.query.filter_by(
        edition_id=edition_id, participant_id=participant.id, name=problematiques_name
    ).first()
    if not problematiques_file:
        problematiques_ext = os.path.splitext(problematiques_template.filename or "")[1] or ""
        problematiques_file = ScenarioFile(
            edition_id=edition_id, kind=ScenarioTemplate.KIND_PROBLEMATIQUES, name=problematiques_name,
            participant_id=participant.id, source_template_id=problematiques_template.id,
            filename=f"{problematiques_name}{problematiques_ext}", content_type=problematiques_template.content_type,
            file_data=problematiques_template.file_data, file_size=problematiques_template.file_size,
            created_by_id=current_user.id,
        )
        db.session.add(problematiques_file)

    db.session.flush()

    try:
        validated_examples, _next_row, _last_num = excel_utils.load_book_state(book_file.file_data)
        problematiques_text = pptx_utils.read_problematiques_text(problematiques_file.file_data)

        scenarios = ai_generation.generate_scenarios(
            participant_name=participant.participant_name,
            website_url=website_url,
            problematiques_text=problematiques_text,
            examples=validated_examples,
            num_to_generate=SCENARIOS_PER_BATCH,
        )

        new_book_data, assigned_numbers = excel_utils.append_scenarios(
            book_file.file_data, participant.participant_name, scenarios
        )
        book_file.file_data = new_book_data
        book_file.file_size = len(new_book_data)

        new_pptx_data = pptx_utils.append_scenario_slides(
            problematiques_file.file_data, list(zip(assigned_numbers, scenarios))
        )
        problematiques_file.file_data = new_pptx_data
        problematiques_file.file_size = len(new_pptx_data)
    except (excel_utils.BookWorkbookError, ai_generation.ScenarioGenerationError) as exc:
        db.session.rollback()
        flash(f"Génération impossible : {exc}", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    db.session.commit()

    _log(
        "Génération de scénarios par IA",
        details=f"{len(scenarios)} scénario(s) pour {participant.participant_name} (édition {edition_id})",
    )
    flash(
        f"{len(scenarios)} scénario(s) généré(s) pour « {participant.participant_name} » "
        f"dans « {book_name} » et « {problematiques_name} ».",
        "success",
    )
    return redirect(url_for("scenarios.generate_scenarios"))


@scenarios_bp.route("/upload", methods=["POST"])
@login_required
def upload_scenario_file():
    edition_id = get_current_edition_id()
    file = request.files.get("scenario_file")
    if not file or not file.filename:
        flash("Merci de choisir un fichier avant de cliquer sur « Charger ».", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    filename = file.filename
    content = file.read()
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    name = _sanitize_filename(os.path.splitext(filename)[0])

    db.session.add(ScenarioFile(
        edition_id=edition_id, name=name, filename=filename, content_type=content_type,
        file_data=content, file_size=len(content), created_by_id=current_user.id,
    ))
    db.session.commit()

    _log("Chargement direct d'un fichier scénario", details=f"{filename} (édition {edition_id})")
    flash(f"Fichier « {filename} » chargé avec succès.", "success")
    return redirect(url_for("scenarios.generate_scenarios"))


@scenarios_bp.route("/<int:file_id>/download", methods=["GET"])
@login_required
def download_scenario_file(file_id):
    edition_id = get_current_edition_id()
    scenario_file = ScenarioFile.query.filter_by(id=file_id, edition_id=edition_id).first()
    if not scenario_file:
        return "Fichier introuvable pour cette édition.", 404

    return send_file(
        io.BytesIO(scenario_file.file_data), mimetype=scenario_file.content_type or "application/octet-stream",
        as_attachment=True, download_name=scenario_file.filename or scenario_file.name,
    )


@scenarios_bp.route("/delete", methods=["POST"])
@login_required
@admin_required
def delete_scenario_files():
    edition_id = get_current_edition_id()
    selected_ids = [int(i) for i in request.form.getlist("selected_ids") if i.isdigit()]
    if not selected_ids:
        flash("Merci de choisir au moins un fichier à supprimer.", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    to_delete = ScenarioFile.query.filter(
        ScenarioFile.edition_id == edition_id, ScenarioFile.id.in_(selected_ids)
    ).all()
    deleted = len(to_delete)
    names = ", ".join(f.name for f in to_delete)
    for f in to_delete:
        db.session.delete(f)
    db.session.commit()

    _log("Suppression de fichier(s) scénario", details=f"{deleted} supprimé(s) (édition {edition_id}) : {names}")
    flash(f"{deleted} fichier(s) supprimé(s).", "success")
    return redirect(url_for("scenarios.generate_scenarios"))


@scenarios_bp.route("/tests", methods=["GET"])
@login_required
def generate_tests():
    edition = get_edition(get_current_edition_id())
    return render_template(
        "placeholder.html", edition=edition, menu_items=MENU_ITEMS,
        active_item=ACTIVE_ITEM_TESTS, title=ACTIVE_ITEM_TESTS,
    )
