"""
Module « Gestion des scénarios » > « Générer des scénarios ».

Modèles de scénarios (Book scénario / Problématiques) chargés par
l'utilisateur. Le bouton « Générer un book » crée (ou réutilise, s'ils
existent déjà) les fichiers Book scénario et Problématiques d'un
participant, puis lance en arrière-plan (thread séparé, voir
_run_generation) l'appel à Claude Sonnet 5 (ai_generation.py) qui recherche
sur le vrai site web du participant et génère 10 nouveaux scénarios,
ajoutés dans la feuille « step 1 » du Book (colonnes A-G ; H-K réservées à
« Générer les tests ») et référencés dans le PowerPoint Problématiques
(numéro + URL source). La génération peut prendre plusieurs minutes ; elle
tourne donc hors de la requête web (voir ScenarioGenerationJob), pour ne
pas dépendre d'un timeout HTTP.

« Générer les tests » sera spécifié dans une prochaine étape.
"""

import io
import mimetypes
import os
import re
import threading
from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user

from app.access_control import admin_required
from app.extensions import db
from app.models import ScenarioTemplate, ScenarioFile, ScenarioGenerationJob, Participant, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.timezone_utils import format_local
from app.scenarios import ai_generation, excel_utils, pptx_utils

scenarios_bp = Blueprint("scenarios", __name__, url_prefix="/scenarios")

ACTIVE_ITEM_GENERATE = "Générer des scénarios"
ACTIVE_ITEM_TESTS = "Générer les tests"

KIND_LABELS = {
    ScenarioTemplate.KIND_BOOK: "Book scénario",
    ScenarioTemplate.KIND_PROBLEMATIQUES: "Problématiques",
}

LANGUAGE_LABELS = {
    ScenarioTemplate.LANG_FR: "Français",
    ScenarioTemplate.LANG_EN: "English",
}

FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|]')


def _sanitize_filename(raw):
    name = FILENAME_UNSAFE_RE.sub("_", raw.strip())
    return name or "Fichier"


BOOK_EXTENSIONS = (".xlsx", ".xlsm", ".xls")
PROBLEMATIQUES_EXTENSIONS = (".pptx", ".ppt", ".potx")


def _scenario_names(participant, edition):
    """Noms attendus des fichiers Book scénario / Problématiques d'un
    participant, utilisés à la fois pour la génération IA (create_scenario_files)
    et pour retrouver un fichier rechargé manuellement (upload_scenario_file)."""
    base_suffix = _sanitize_filename(f"{participant.participant_name}_{edition['short_label']}").replace(" ", "_")
    return f"Book_scénario_{base_suffix}", f"Problématiques_{base_suffix}"


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
    files = ScenarioFile.query.filter_by(edition_id=edition_id).order_by(ScenarioFile.updated_at.desc()).all()
    participants = Participant.query.filter_by(edition_id=edition_id).order_by(Participant.participant_name).all()
    book_templates = [t for t in templates if t.kind == ScenarioTemplate.KIND_BOOK]
    problematiques_templates = [t for t in templates if t.kind == ScenarioTemplate.KIND_PROBLEMATIQUES]
    edition = get_edition(edition_id)

    running_jobs = (
        ScenarioGenerationJob.query.filter_by(edition_id=edition_id, status=ScenarioGenerationJob.STATUS_RUNNING)
        .order_by(ScenarioGenerationJob.started_at.desc())
        .all()
    )
    recent_jobs = (
        ScenarioGenerationJob.query.filter(
            ScenarioGenerationJob.edition_id == edition_id,
            ScenarioGenerationJob.status != ScenarioGenerationJob.STATUS_RUNNING,
        )
        .order_by(ScenarioGenerationJob.finished_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "scenarios/generate.html", edition=edition, templates=templates, files=files, participants=participants,
        book_templates=book_templates, problematiques_templates=problematiques_templates, kind_labels=KIND_LABELS,
        language_labels=LANGUAGE_LABELS, active_item=ACTIVE_ITEM_GENERATE, menu_items=MENU_ITEMS,
        running_jobs=running_jobs, recent_jobs=recent_jobs,
    )


@scenarios_bp.route("/templates/upload", methods=["POST"])
@login_required
def upload_template():
    edition_id = get_current_edition_id()
    kind = request.form.get("kind", "").strip()
    if kind not in (ScenarioTemplate.KIND_BOOK, ScenarioTemplate.KIND_PROBLEMATIQUES):
        flash("Type de modèle invalide.", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    language = request.form.get("language", "").strip()
    if language not in LANGUAGE_LABELS:
        flash("Merci de préciser la langue du modèle (Français ou English).", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    file = request.files.get("template_file")
    if not file or not file.filename:
        flash("Merci de choisir un fichier avant de cliquer sur « Charger ».", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    filename = file.filename
    content = file.read()
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    db.session.add(ScenarioTemplate(
        edition_id=edition_id, kind=kind, language=language, filename=filename, content_type=content_type,
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
    language = request.form.get("language", "").strip()

    if (
        not book_template_id.isdigit()
        or not problematiques_template_id.isdigit()
        or not participant_id.isdigit()
        or not website_url
        or language not in LANGUAGE_LABELS
    ):
        flash(
            "Merci de choisir un modèle de Book scénario, un modèle de Problématiques, "
            "un participant, une langue et de saisir l'URL de son site web.",
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

    for template in (book_template, problematiques_template):
        if template.language and template.language != language:
            flash(
                f"Le modèle « {template.filename} » est en {LANGUAGE_LABELS.get(template.language, template.language)}, "
                f"pas en {LANGUAGE_LABELS[language]}. Chargez un modèle dans la bonne langue ou changez la langue "
                "demandée, puis relancez avec « Générer un book ».",
                "error",
            )
            return redirect(url_for("scenarios.generate_scenarios"))

    already_running = ScenarioGenerationJob.query.filter_by(
        edition_id=edition_id, participant_id=participant.id, status=ScenarioGenerationJob.STATUS_RUNNING
    ).first()
    if already_running:
        flash(
            f"Une génération est déjà en cours pour « {participant.participant_name} » "
            f"(lancée à {format_local(already_running.started_at, '%H:%M')}). Patientez qu'elle se termine.",
            "error",
        )
        return redirect(url_for("scenarios.generate_scenarios"))

    book_name, problematiques_name = _scenario_names(participant, edition)

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

    # Un fichier déjà enrichi par une génération précédente porte déjà une
    # langue : impossible de continuer dans une autre langue (mélange dans
    # le même fichier). Les fichiers neufs n'ont pas encore de langue et la
    # reçoivent maintenant.
    for scenario_file in (book_file, problematiques_file):
        if scenario_file.language and scenario_file.language != language:
            flash(
                f"Le fichier « {scenario_file.name} » existant est déjà en "
                f"{LANGUAGE_LABELS.get(scenario_file.language, scenario_file.language)}, incompatible avec "
                f"{LANGUAGE_LABELS[language]}. Relancez avec « Générer un book » en choisissant la bonne langue.",
                "error",
            )
            return redirect(url_for("scenarios.generate_scenarios"))
    for scenario_file in (book_file, problematiques_file):
        if not scenario_file.language:
            scenario_file.language = language

    job = ScenarioGenerationJob(
        edition_id=edition_id, participant_id=participant.id, status=ScenarioGenerationJob.STATUS_RUNNING,
        requested_by_id=current_user.id, requested_by_email=current_user.email,
    )
    db.session.add(job)
    # Commit immédiat (fichiers créés/réutilisés + job "en cours") avant de
    # lancer la tâche de fond, qui peut prendre plusieurs minutes : réduit
    # au minimum la fenêtre où un second clic verrait encore "rien
    # n'existe" et recréerait les fichiers en double.
    db.session.commit()

    app_obj = current_app._get_current_object()
    threading.Thread(
        target=_run_generation,
        args=(app_obj, job.id, book_file.id, problematiques_file.id, website_url, language),
        daemon=True,
    ).start()

    flash(
        f"Génération lancée pour « {participant.participant_name} » dans « {book_name} » et "
        f"« {problematiques_name} » (peut prendre plusieurs minutes). Actualisez cette page pour suivre l'avancement.",
        "success",
    )
    return redirect(url_for("scenarios.generate_scenarios"))


def _apply_usage_to_job(job, usage):
    """Reporte l'usage réel (tokens, recherches web, coût estimé) sur le
    job, qu'il ait réussi ou échoué après avoir tout de même consommé de
    l'API (voir ai_generation.ScenarioGenerationError.usage)."""
    if not usage:
        return
    job.input_tokens = usage.get("input_tokens")
    job.output_tokens = usage.get("output_tokens")
    job.web_search_count = usage.get("web_search_count")
    job.estimated_cost_usd = usage.get("estimated_cost_usd")


def _run_generation(app, job_id, book_file_id, problematiques_file_id, website_url, language):
    """
    Exécutée dans un thread séparé (voir create_scenario_files) : appelle
    l'IA puis met à jour les fichiers et le job de suivi. Ne doit jamais
    lever d'exception non gérée (le thread tournerait sans que personne ne
    puisse la voir) : toute erreur est capturée et consignée dans le job.
    """
    with app.app_context():
        job = None
        try:
            job = db.session.get(ScenarioGenerationJob, job_id)
            book_file = db.session.get(ScenarioFile, book_file_id)
            problematiques_file = db.session.get(ScenarioFile, problematiques_file_id)
            if not job or not book_file or not problematiques_file:
                return
            participant = job.participant

            validated_examples, _next_row, _last_num = excel_utils.load_book_state(book_file.file_data)
            problematiques_text = pptx_utils.read_problematiques_text(problematiques_file.file_data)

            scenarios, usage = ai_generation.generate_scenarios(
                participant_name=participant.participant_name,
                website_url=website_url,
                problematiques_text=problematiques_text,
                examples=validated_examples,
                num_to_generate=SCENARIOS_PER_BATCH,
                language=language,
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

            job.status = ScenarioGenerationJob.STATUS_SUCCESS
            job.scenarios_generated = len(scenarios)
            _apply_usage_to_job(job, usage)
            job.finished_at = datetime.utcnow()
            db.session.add(ActionLog(
                user_id=job.requested_by_id, user_email=job.requested_by_email, edition_id=job.edition_id,
                action="Génération de scénarios par IA",
                details=f"{len(scenarios)} scénario(s) pour {participant.participant_name} (édition {job.edition_id})",
            ))
            db.session.commit()
        except (excel_utils.BookWorkbookError, ai_generation.ScenarioGenerationError) as exc:
            db.session.rollback()
            if job:
                job.status = ScenarioGenerationJob.STATUS_ERROR
                job.error_message = str(exc)
                _apply_usage_to_job(job, getattr(exc, "usage", None))
                job.finished_at = datetime.utcnow()
                db.session.commit()
        except Exception as exc:  # noqa: BLE001 - tâche de fond : ne doit jamais échouer silencieusement
            db.session.rollback()
            if job:
                job.status = ScenarioGenerationJob.STATUS_ERROR
                job.error_message = f"Erreur inattendue : {exc}"
                job.finished_at = datetime.utcnow()
                db.session.commit()
        finally:
            db.session.remove()


@scenarios_bp.route("/upload", methods=["POST"])
@login_required
def upload_scenario_file():
    edition_id = get_current_edition_id()
    edition = get_edition(edition_id)
    file = request.files.get("scenario_file")
    if not file or not file.filename:
        flash("Merci de choisir un fichier avant de cliquer sur « Charger ».", "error")
        return redirect(url_for("scenarios.generate_scenarios"))

    filename = file.filename
    content = file.read()
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    ext = os.path.splitext(filename)[1].lower()

    participant_id = request.form.get("participant_id", "").strip()
    participant = None
    if participant_id.isdigit():
        participant = Participant.query.filter_by(id=int(participant_id), edition_id=edition_id).first()

    if participant:
        # Fichier rattaché à un participant (ex. Book/Problématiques
        # retéléchargé, nettoyé, puis rechargé) : on lui donne le même nom
        # que « Générer un book » attend, pour que les prochaines
        # générations continuent à partir de ce fichier plutôt que d'en
        # recréer un depuis le modèle.
        if ext in BOOK_EXTENSIONS:
            kind = ScenarioTemplate.KIND_BOOK
        elif ext in PROBLEMATIQUES_EXTENSIONS:
            kind = ScenarioTemplate.KIND_PROBLEMATIQUES
        else:
            flash(
                "Pour lier ce fichier à un participant, chargez un fichier Excel "
                "(Book scénario) ou PowerPoint (Problématiques).",
                "error",
            )
            return redirect(url_for("scenarios.generate_scenarios"))

        book_name, problematiques_name = _scenario_names(participant, edition)
        name = book_name if kind == ScenarioTemplate.KIND_BOOK else problematiques_name

        scenario_file = ScenarioFile.query.filter_by(
            edition_id=edition_id, participant_id=participant.id, name=name
        ).first()
        if scenario_file:
            scenario_file.kind = kind
            scenario_file.filename = filename
            scenario_file.content_type = content_type
            scenario_file.file_data = content
            scenario_file.file_size = len(content)
        else:
            db.session.add(ScenarioFile(
                edition_id=edition_id, kind=kind, name=name, participant_id=participant.id,
                filename=filename, content_type=content_type, file_data=content, file_size=len(content),
                created_by_id=current_user.id,
            ))
    else:
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
