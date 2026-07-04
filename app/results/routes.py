"""
Module « Chargement d'un fichier de résultat ».

Permet de charger un fichier Excel de résultats de tests mystères, de le
valider intégralement (voir validation.py), et — seulement si aucune
erreur n'est détectée — d'enregistrer toutes les lignes en base de
données, rattachées à l'édition en cours.

Le chargement est tout-ou-rien : si la moindre erreur est trouvée, rien
n'est enregistré et la liste complète des erreurs est affichée, pour que
l'utilisateur corrige le fichier avant de le recharger.
"""

import io

import openpyxl
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Category, Participant, TestResult, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.results.validation import validate_workbook, EXPECTED_SHEETS

results_bp = Blueprint("results", __name__, url_prefix="/results")

ACTIVE_ITEM = "Chargement d'un fichier de résultat"


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
        success=False, global_error=None, errors=[], filename=None,
        added=0, updated=0, total=0,
    )
    defaults.update(kwargs)
    return render_template("results/report.html", **defaults)


@results_bp.route("/upload", methods=["GET"])
@login_required
def upload_page():
    edition = get_edition(get_current_edition_id())
    return render_template(
        "results/upload.html", edition=edition, active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@results_bp.route("/upload", methods=["POST"])
@login_required
def upload_file():
    edition_id = get_current_edition_id()

    file = request.files.get("result_file")
    if not file or not file.filename:
        return _render_report(global_error="Merci de choisir un fichier avant de cliquer sur « Charger un fichier ».")

    filename = secure_filename(file.filename)
    if not filename.lower().endswith(".xlsx"):
        return _render_report(global_error="Seul le format Excel (.xlsx) est accepté.", filename=filename)

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file.read()), data_only=True)
    except Exception:
        return _render_report(
            global_error="Le fichier n'a pas pu être ouvert. Vérifiez qu'il s'agit bien d'un fichier Excel (.xlsx) valide et non corrompu.",
            filename=filename,
        )

    if not any(sheet in wb.sheetnames for sheet in EXPECTED_SHEETS):
        return _render_report(
            global_error=(
                "Le fichier ne contient aucun des onglets attendus "
                "(Phone, Email, Web Navigation, Social Networks, Chat)."
            ),
            filename=filename,
        )

    categories = Category.query.filter_by(edition_id=edition_id).all()
    participants = Participant.query.filter_by(edition_id=edition_id).all()

    errors, valid_rows = validate_workbook(wb, categories, participants)

    if errors:
        _log("Chargement fichier résultat — échec", details=f"{filename} : {len(errors)} erreur(s) (édition {edition_id})")
        return _render_report(success=False, errors=errors, filename=filename)

    existing_by_test_id = {tr.test_id: tr for tr in TestResult.query.filter_by(edition_id=edition_id).all()}
    added, updated = 0, 0
    for row in valid_rows:
        existing = existing_by_test_id.get(row["test_id"])
        if existing:
            existing.channel = row["channel"]
            existing.category_id = row["category_id"]
            existing.participant_id = row["participant_id"]
            existing.sheet_name = row["sheet"]
            existing.row_number = row["row"]
            existing.raw_data = row["raw_data"]
            existing.source_filename = filename
            existing.uploaded_by_id = current_user.id
            updated += 1
        else:
            db.session.add(TestResult(
                edition_id=edition_id, channel=row["channel"], test_id=row["test_id"],
                category_id=row["category_id"], participant_id=row["participant_id"],
                sheet_name=row["sheet"], row_number=row["row"], raw_data=row["raw_data"],
                source_filename=filename, uploaded_by_id=current_user.id,
            ))
            added += 1
    db.session.commit()

    _log(
        "Chargement fichier résultat — succès",
        details=f"{filename} : {added} ajouté(s), {updated} mis à jour (édition {edition_id})",
    )

    return _render_report(success=True, filename=filename, added=added, updated=updated, total=len(valid_rows))
