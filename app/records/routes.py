"""
Module « Chargement des records ».

Permet de charger en une fois un lot de fichiers "record" (la preuve d'un
test mystère : fichier audio pour un test Phone, PDF pour les autres
canaux), chacun nommé "IDMYSTERYTEST-record.ext" (ex. 44031450-record.pdf).
Chaque fichier est lié au TestResult existant portant le même ID Mystery
Test, pour l'édition en cours.

Le chargement est tout-ou-rien, comme pour les résultats : si un seul
fichier du lot est invalide, rien n'est enregistré.
"""

import io
import mimetypes

from flask import Blueprint, render_template, request, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Category, Participant, TestResult, TestRecord, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.records.validation import validate_record_files
from app.results.presentation import CHANNEL_LABELS

records_bp = Blueprint("records", __name__, url_prefix="/records")

ACTIVE_ITEM = "Chargement des records"


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id, user_email=current_user.email,
        edition_id=get_current_edition_id(), action=action, details=details,
    )
    db.session.add(entry)
    db.session.commit()


def _render_report(**kwargs):
    edition = get_edition(get_current_edition_id())
    defaults = dict(
        edition=edition, active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
        success=False, global_error=None, errors=[], added=0, updated=0, total=0,
    )
    defaults.update(kwargs)
    return render_template("records/report.html", **defaults)


@records_bp.route("/upload", methods=["GET"])
@login_required
def upload_page():
    edition_id = get_current_edition_id()
    edition = get_edition(edition_id)
    records = (
        TestRecord.query.join(TestResult)
        .filter(TestResult.edition_id == edition_id)
        .order_by(TestRecord.uploaded_at.desc())
        .all()
    )
    return render_template(
        "records/upload.html", edition=edition, records=records, channel_labels=CHANNEL_LABELS,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@records_bp.route("/upload", methods=["POST"])
@login_required
def upload_records():
    edition_id = get_current_edition_id()

    files = [f for f in request.files.getlist("record_files") if f and f.filename]
    if not files:
        return _render_report(global_error="Merci de choisir au moins un fichier avant de cliquer sur « Charger ».")

    categories = Category.query.filter_by(edition_id=edition_id).all()
    participants = Participant.query.filter_by(edition_id=edition_id).all()
    tests_by_test_id = {t.test_id: t for t in TestResult.query.filter_by(edition_id=edition_id).all()}

    safe_names = {f: secure_filename(f.filename) for f in files}
    errors, valid = validate_record_files(safe_names.values(), categories, participants, tests_by_test_id)

    if errors:
        _log("Chargement des records — échec", details=f"{len(files)} fichier(s) : {len(errors)} erreur(s) (édition {edition_id})")
        return _render_report(success=False, errors=errors)

    valid_by_filename = {item["filename"]: item for item in valid}

    added, updated = 0, 0
    for file in files:
        filename = safe_names[file]
        item = valid_by_filename[filename]
        test = item["test_result"]
        content = file.read()
        content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

        existing = TestRecord.query.filter_by(test_result_id=test.id).first()
        if existing:
            existing.filename = filename
            existing.content_type = content_type
            existing.file_data = content
            existing.file_size = len(content)
            existing.uploaded_by_id = current_user.id
            updated += 1
        else:
            db.session.add(TestRecord(
                test_result_id=test.id, filename=filename, content_type=content_type,
                file_data=content, file_size=len(content), uploaded_by_id=current_user.id,
            ))
            added += 1

    db.session.commit()

    _log(
        "Chargement des records — succès",
        details=f"{added} ajouté(s), {updated} mis à jour (édition {edition_id})",
    )
    return _render_report(success=True, added=added, updated=updated, total=len(files))


@records_bp.route("/<int:record_id>/download", methods=["GET"])
@login_required
def download_record(record_id):
    edition_id = get_current_edition_id()
    record = (
        TestRecord.query.join(TestResult)
        .filter(TestRecord.id == record_id, TestResult.edition_id == edition_id)
        .first()
    )
    if not record:
        return "Record introuvable pour cette édition.", 404

    return send_file(
        io.BytesIO(record.file_data),
        mimetype=record.content_type or "application/octet-stream",
        as_attachment=True,
        download_name=record.filename,
    )
