"""
Module « Chargement fichier résultat ».

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
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Category, Participant, TestResult, ActionLog, FileUpload
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS
from app.results.validation import validate_workbook, EXPECTED_SHEETS
from app.results.presentation import build_test_view, CHANNEL_LABELS, CHANNEL_ORDER
from app.results.scoring import build_compilation_rows

results_bp = Blueprint("results", __name__, url_prefix="/results")

ACTIVE_ITEM = "Chargement fichier résultat"
ACTIVE_ITEM_TESTS = "Liste des tests"
ACTIVE_ITEM_COMPILATION = "Compilation des résultats"


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
        added=0, updated=0, total=0, invalid_channels={},
    )
    defaults.update(kwargs)
    return render_template("results/report.html", **defaults)


def _backfill_missing_file_uploads(edition_id):
    """
    Le modèle FileUpload (historique des chargements) a été introduit après
    que des fichiers de résultats aient déjà été chargés en production : ces
    chargements antérieurs n'ont donc pas de ligne FileUpload, alors que les
    TestResult correspondants existent bel et bien (avec leur
    source_filename/uploaded_at/uploaded_by_id d'origine, présents depuis le
    tout premier chargement). On reconstitue ici, une fois pour toutes, les
    lignes FileUpload manquantes à partir de ces données déjà en base.
    """
    tracked_filenames = {
        fu.filename for fu in FileUpload.query.filter_by(edition_id=edition_id).all()
    }
    tests = (
        TestResult.query.filter_by(edition_id=edition_id)
        .filter(TestResult.source_filename.isnot(None))
        .all()
    )

    by_filename = {}
    for t in tests:
        by_filename.setdefault(t.source_filename, []).append(t)

    created = False
    for filename, group in by_filename.items():
        if filename in tracked_filenames:
            continue
        uploaded_at = min((t.uploaded_at for t in group if t.uploaded_at), default=None)
        db.session.add(FileUpload(
            edition_id=edition_id, filename=filename,
            uploaded_by_id=group[0].uploaded_by_id, uploaded_at=uploaded_at,
            added_count=len(group), updated_count=0, total_count=len(group),
        ))
        created = True

    if created:
        db.session.commit()


@results_bp.route("/upload", methods=["GET"])
@login_required
def upload_page():
    edition_id = get_current_edition_id()
    _backfill_missing_file_uploads(edition_id)
    edition = get_edition(edition_id)
    uploads = FileUpload.query.filter_by(edition_id=edition_id).order_by(FileUpload.id.desc()).all()
    return render_template(
        "results/upload.html", edition=edition, uploads=uploads,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@results_bp.route("/upload/cancel", methods=["POST"])
@login_required
def cancel_upload():
    """
    Supprime définitivement un fichier déjà chargé : son entrée dans
    l'historique (FileUpload) et tous les TestResult qui en proviennent
    pour l'édition en cours. Aucun autre fichier n'est affecté.
    """
    edition_id = get_current_edition_id()
    filename = request.form.get("filename", "").strip()
    if not filename:
        flash("Merci de choisir un fichier à annuler.", "error")
        return redirect(url_for("results.upload_page"))

    deleted = TestResult.query.filter_by(edition_id=edition_id, source_filename=filename).delete()
    FileUpload.query.filter_by(edition_id=edition_id, filename=filename).delete()
    db.session.commit()

    _log(
        "Annulation fichier résultat",
        details=f"{filename} : {deleted} test(s) supprimé(s) (édition {edition_id})",
    )
    flash(f"Fichier « {filename} » annulé : {deleted} test(s) supprimé(s) de la base.", "success")
    return redirect(url_for("results.upload_page"))


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

    errors, valid_rows, invalid_channels = validate_workbook(wb, categories, participants)

    if errors:
        _log("Chargement fichier résultat — échec", details=f"{filename} : {len(errors)} erreur(s) (édition {edition_id})")
        invalid_channels_view = {
            sheet: sorted(names) for sheet, names in invalid_channels.items()
        }
        return _render_report(success=False, errors=errors, filename=filename, invalid_channels=invalid_channels_view)

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

    db.session.add(FileUpload(
        edition_id=edition_id, filename=filename, uploaded_by_id=current_user.id,
        added_count=added, updated_count=updated, total_count=len(valid_rows),
    ))
    db.session.commit()

    _log(
        "Chargement fichier résultat — succès",
        details=f"{filename} : {added} ajouté(s), {updated} mis à jour (édition {edition_id})",
    )

    return _render_report(success=True, filename=filename, added=added, updated=updated, total=len(valid_rows))


# --------------------------------------------- Compilation des résultats

@results_bp.route("/compilation", methods=["GET"])
@login_required
def compilation_results():
    edition_id = get_current_edition_id()
    participants = Participant.query.filter_by(edition_id=edition_id).all()
    tests = TestResult.query.filter_by(edition_id=edition_id).all()
    rows = build_compilation_rows(participants, tests)

    edition = get_edition(edition_id)
    return render_template(
        "results/compilation.html", edition=edition, rows=rows,
        channel_order=CHANNEL_ORDER, channel_labels=CHANNEL_LABELS,
        active_item=ACTIVE_ITEM_COMPILATION, menu_items=MENU_ITEMS,
    )


# ----------------------------------------------------- Liste des tests

def _sort_key(test_result):
    category_label = test_result.category.label() if test_result.category else "~"
    participant_name = test_result.participant.participant_name if test_result.participant else "~"
    channel_rank = CHANNEL_ORDER.index(test_result.channel) if test_result.channel in CHANNEL_ORDER else 99
    return (category_label.lower(), participant_name.lower(), channel_rank, test_result.row_number or 0)


@results_bp.route("/tests", methods=["GET"])
@login_required
def list_tests():
    edition_id = get_current_edition_id()
    tests = TestResult.query.filter_by(edition_id=edition_id).all()
    tests.sort(key=_sort_key)

    groups = []
    current_key = None
    for t in tests:
        key = (t.category_id, t.participant_id)
        if key != current_key:
            groups.append({
                "category_label": t.category.label() if t.category else "(catégorie supprimée)",
                "participant_name": t.participant.participant_name if t.participant else "(participant supprimé)",
                "participant_code": t.participant.code if t.participant else "",
                "tests": [],
            })
            current_key = key
        groups[-1]["tests"].append(build_test_view(t))

    edition = get_edition(edition_id)
    return render_template(
        "results/tests_list.html", edition=edition, groups=groups, total_tests=len(tests),
        channel_options=CHANNEL_LABELS, active_item=ACTIVE_ITEM_TESTS, menu_items=MENU_ITEMS,
    )


@results_bp.route("/tests/search", methods=["GET"])
@login_required
def search_tests():
    edition_id = get_current_edition_id()
    test_id_query = request.args.get("test_id", "").strip()
    channel_query = request.args.get("channel", "").strip()
    date_query = request.args.get("date", "").strip()
    participant_query = request.args.get("participant_name", "").strip()

    if not test_id_query and not channel_query and not date_query and not participant_query:
        edition = get_edition(edition_id)
        return render_template(
            "results/search_results.html", edition=edition, active_item=ACTIVE_ITEM_TESTS, menu_items=MENU_ITEMS,
            error="Merci de renseigner au moins un critère (numéro de test, canal, date ou participant).", results=[],
        )

    query = TestResult.query.filter_by(edition_id=edition_id)
    if test_id_query:
        query = query.filter(TestResult.test_id.like(f"%{test_id_query}%"))
    if channel_query:
        query = query.filter_by(channel=channel_query)
    candidates = query.all()

    if date_query:
        candidates = [
            t for t in candidates
            if date_query.lower() in str((t.raw_data or {}).get(
                {"phone": "Call_Date"}.get(t.channel, "Day_Open"), ""
            )).lower()
        ]

    if participant_query:
        candidates = [
            t for t in candidates
            if t.participant and participant_query.lower() in t.participant.participant_name.lower()
        ]

    edition = get_edition(edition_id)

    if len(candidates) == 1:
        return test_detail(candidates[0].id)

    views = [build_test_view(t) for t in candidates]
    return render_template(
        "results/search_results.html", edition=edition, active_item=ACTIVE_ITEM_TESTS, menu_items=MENU_ITEMS,
        error=None, results=views,
    )


@results_bp.route("/tests/<int:test_result_id>", methods=["GET"])
@login_required
def test_detail(test_result_id):
    edition_id = get_current_edition_id()
    t = TestResult.query.get(test_result_id)
    if not t or t.edition_id != edition_id:
        edition = get_edition(edition_id)
        return render_template(
            "results/search_results.html", edition=edition, active_item=ACTIVE_ITEM_TESTS, menu_items=MENU_ITEMS,
            error="Ce test est introuvable pour l'édition en cours.", results=[],
        )

    edition = get_edition(edition_id)
    view = build_test_view(t)
    return render_template(
        "results/test_detail.html", edition=edition, active_item=ACTIVE_ITEM_TESTS, menu_items=MENU_ITEMS,
        test=view,
    )
