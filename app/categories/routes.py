"""
Module « Configuration catégorie ».

Reproduit le comportement de la version Mac : un tableau où « Ajouter »
crée une ligne éditable, « Modifier » passe les lignes cochées en édition,
« Supprimer » les retire, et « Enregistrer »/« Annuler » valident ou
abandonnent les modifications en cours.

Comme plusieurs collaborateurs partagent l'outil, l'état "quelles lignes
sont en cours d'édition" est propre à chaque utilisateur (stocké dans son
cookie de session Flask), pas partagé — deux personnes peuvent donc
travailler sur l'écran catégories en même temps sans se marcher dessus.
"""

import re
import uuid

from flask import Blueprint, render_template, request, redirect, url_for, session
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Category, Participant, TestResult, TestRecord, Invoice, StudyReport, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.access_control import user_is_admin
from app.menu import MENU_ITEMS

categories_bp = Blueprint("categories", __name__, url_prefix="/categories")

CODE_REGEX = re.compile(r"^\d{2}$")

SESSION_EDITING_IDS = "cat_editing_ids"
SESSION_NEW_ROWS = "cat_new_rows"


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id, user_email=current_user.email,
        edition_id=get_current_edition_id(), action=action, details=details,
    )
    db.session.add(entry)
    db.session.commit()


def _editing_ids():
    return session.get(SESSION_EDITING_IDS, [])


def _new_rows():
    return session.get(SESSION_NEW_ROWS, [])


def _clear_editing_state():
    session.pop(SESSION_EDITING_IDS, None)
    session.pop(SESSION_NEW_ROWS, None)


def _build_rows(categories, pending_values=None):
    """
    Construit la liste des lignes à afficher : les catégories existantes
    (en mode lecture ou édition selon _editing_ids()) suivies des nouvelles
    lignes non encore enregistrées (_new_rows()). pending_values permet de
    réafficher des valeurs invalides après un échec de validation, sans les
    perdre.
    """
    pending_values = pending_values or {}
    editing_ids = set(_editing_ids())
    rows = []

    for cat in categories:
        row_key = str(cat.id)
        editing = cat.id in editing_ids
        values = pending_values.get(row_key, {
            "category_name": cat.category_name, "display_name": cat.display_name, "code": cat.code,
        })
        rows.append({"row_key": row_key, "is_new": False, "editing": editing, "fields": values})

    for new_row in _new_rows():
        row_key = new_row["tmp_id"]
        values = pending_values.get(row_key, {
            "category_name": new_row.get("category_name", ""),
            "display_name": new_row.get("display_name", ""),
            "code": new_row.get("code", ""),
        })
        rows.append({"row_key": row_key, "is_new": True, "editing": True, "fields": values})

    return rows


def _render(pending_values=None, error=None, confirm_delete=None):
    edition_id = get_current_edition_id()
    categories = Category.query.filter_by(edition_id=edition_id).order_by(Category.id).all()
    rows = _build_rows(categories, pending_values=pending_values)
    any_editing = any(r["editing"] for r in rows)
    return render_template(
        "categories/list.html",
        edition=get_edition(edition_id), rows=rows, any_editing=any_editing, error=error,
        confirm_delete=confirm_delete,
        active_item="Configuration catégorie", menu_items=MENU_ITEMS,
    )


@categories_bp.route("/", methods=["GET"])
@login_required
def list_categories():
    return _render()


@categories_bp.route("/add", methods=["POST"])
@login_required
def add_row():
    new_rows = _new_rows()
    new_rows.append({"tmp_id": f"new_{uuid.uuid4().hex[:8]}", "category_name": "", "display_name": "", "code": ""})
    session[SESSION_NEW_ROWS] = new_rows
    return redirect(url_for("categories.list_categories"))


@categories_bp.route("/edit", methods=["POST"])
@login_required
def edit_rows():
    selected_ids = [int(i) for i in request.form.getlist("selected_ids")]
    if not selected_ids:
        return _render(error="Veuillez cocher au moins une ligne à modifier.")
    session[SESSION_EDITING_IDS] = selected_ids
    return redirect(url_for("categories.list_categories"))


@categories_bp.route("/delete", methods=["POST"])
@login_required
def delete_rows():
    selected_ids = [int(i) for i in request.form.getlist("selected_ids")]
    if not selected_ids:
        return _render(error="Veuillez cocher au moins une ligne à supprimer.")

    edition_id = get_current_edition_id()
    to_delete = Category.query.filter(Category.edition_id == edition_id, Category.id.in_(selected_ids)).all()
    if not to_delete:
        return _render(error="Veuillez cocher au moins une ligne à supprimer.")

    ids = [cat.id for cat in to_delete]
    nb_participants = Participant.query.filter(Participant.category_id.in_(ids)).count()
    nb_tests = TestResult.query.filter(TestResult.category_id.in_(ids)).count()

    if nb_participants or nb_tests:
        if not user_is_admin(current_user):
            return _render(error=(
                "Impossible de supprimer : "
                + ", ".join(cat.label() for cat in to_delete)
                + f" contient {nb_participants} participant(s) et {nb_tests} test(s). "
                "Seul un administrateur peut supprimer une catégorie avec ses données."
            ))

        if request.form.get("confirm_delete") != "1":
            return _render(confirm_delete={
                "ids": ids,
                "message": (
                    ", ".join(cat.label() for cat in to_delete)
                    + f" : {nb_participants} participant(s) et {nb_tests} test(s) seront "
                    "supprimés définitivement en même temps que la catégorie."
                ),
            })

        test_ids = [t.id for t in TestResult.query.filter(TestResult.category_id.in_(ids)).all()]
        TestRecord.query.filter(TestRecord.test_result_id.in_(test_ids)).delete(synchronize_session=False)
        TestResult.query.filter(TestResult.category_id.in_(ids)).delete(synchronize_session=False)

        participant_ids = [p.id for p in Participant.query.filter(Participant.category_id.in_(ids)).all()]
        # Instantanés autonomes : on détache la référence plutôt que de les
        # supprimer, pour ne pas perdre l'historique des factures/rapports.
        Invoice.query.filter(Invoice.participant_id.in_(participant_ids)).update(
            {"participant_id": None}, synchronize_session=False
        )
        StudyReport.query.filter(StudyReport.participant_id.in_(participant_ids)).update(
            {"participant_id": None}, synchronize_session=False
        )
        Participant.query.filter(Participant.category_id.in_(ids)).delete(synchronize_session=False)

    count = len(to_delete)
    for cat in to_delete:
        db.session.delete(cat)
    db.session.commit()

    _log(
        "Suppression catégorie(s)",
        details=f"{count} catégorie(s), {nb_participants} participant(s), {nb_tests} test(s) (édition {edition_id})",
    )
    _clear_editing_state()
    return redirect(url_for("categories.list_categories"))


@categories_bp.route("/save", methods=["POST"])
@login_required
def save_rows():
    edition_id = get_current_edition_id()
    editing_ids = _editing_ids()
    new_rows = _new_rows()

    row_keys = [str(i) for i in editing_ids] + [r["tmp_id"] for r in new_rows]

    submitted = {}
    pending_values = {}
    errors = []
    for key in row_keys:
        category_name = request.form.get(f"category_name_{key}", "").strip()
        display_name = request.form.get(f"display_name_{key}", "").strip()
        code = request.form.get(f"code_{key}", "").strip()
        pending_values[key] = {"category_name": category_name, "display_name": display_name, "code": code}
        submitted[key] = (category_name, display_name, code)

        if not category_name or not display_name or not code:
            errors.append("Merci de renseigner Category Name, Nom de la Catégorie et Code pour chaque ligne en cours d'édition.")
        elif not CODE_REGEX.match(code):
            errors.append(f"Le code « {code} » n'est pas valide : il doit être composé d'exactement 2 chiffres (0-9).")

    # Unicité du code : ni en doublon avec une autre catégorie existante de
    # l'édition, ni en doublon entre deux lignes de la saisie en cours.
    existing = Category.query.filter_by(edition_id=edition_id).all()
    existing_others = {c.code: c for c in existing if str(c.id) not in row_keys}
    seen_in_batch = {}
    for key in row_keys:
        _, _, code = submitted[key]
        if not code or not CODE_REGEX.match(code):
            continue
        if code in existing_others:
            errors.append(f"Le code « {code} » est déjà utilisé par une autre catégorie de cette édition.")
        elif code in seen_in_batch and seen_in_batch[code] != key:
            errors.append(f"Le code « {code} » est utilisé plusieurs fois dans cette saisie.")
        else:
            seen_in_batch[code] = key

    if errors:
        return _render(pending_values=pending_values, error=" • ".join(dict.fromkeys(errors)))

    added = 0
    modified = 0

    for cat_id in editing_ids:
        cat = Category.query.get(cat_id)
        if cat and cat.edition_id == edition_id:
            category_name, display_name, code = submitted[str(cat_id)]
            cat.category_name = category_name
            cat.display_name = display_name
            cat.code = code
            modified += 1

    for new_row in new_rows:
        category_name, display_name, code = submitted[new_row["tmp_id"]]
        db.session.add(Category(
            edition_id=edition_id, category_name=category_name, display_name=display_name, code=code,
        ))
        added += 1

    db.session.commit()

    details = []
    if added:
        details.append(f"{added} ajoutée(s)")
    if modified:
        details.append(f"{modified} modifiée(s)")
    _log("Enregistrement catégorie(s)", details=", ".join(details) + f" (édition {edition_id})")

    _clear_editing_state()
    return redirect(url_for("categories.list_categories"))


@categories_bp.route("/cancel", methods=["POST"])
@login_required
def cancel_edit():
    _clear_editing_state()
    return redirect(url_for("categories.list_categories"))
