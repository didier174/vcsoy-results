"""
Routes principales : tableau de bord, navigation dans le menu, changement
d'édition. Les modules « Configuration catégorie » et « Configuration
Participant » seront ajoutés dans les prochaines étapes ; pour l'instant
tous les items (sauf placeholder) affichent un écran d'attente générique.
"""

from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user

from app.editions import list_editions, get_edition, is_valid_edition, get_current_edition_id, set_current_edition_id
from app.models import ActionLog
from app.extensions import db
from app.menu import MENU_ITEMS

main_bp = Blueprint("main", __name__)


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id,
        user_email=current_user.email,
        edition_id=get_current_edition_id(),
        action=action,
        details=details,
    )
    db.session.add(entry)
    db.session.commit()


@main_bp.route("/")
@login_required
def dashboard():
    edition = get_edition(get_current_edition_id())
    return render_template(
        "dashboard.html", edition=edition, menu_items=MENU_ITEMS, active_item=None,
    )


@main_bp.route("/module/<path:item_name>")
@login_required
def module(item_name):
    if item_name == "Configuration catégorie":
        return redirect(url_for("categories.list_categories"))
    if item_name == "Configuration Participant":
        return redirect(url_for("participants.list_participants"))
    if item_name == "Chargement fichier résultat":
        return redirect(url_for("results.upload_page"))
    if item_name == "Compilation des résultats":
        return redirect(url_for("results.compilation_results"))
    if item_name in ("Liste des tests", "Présentation de la liste de test"):
        return redirect(url_for("results.list_tests"))
    if item_name == "Liste des résultats":
        return redirect(url_for("results.presentation_results"))
    if item_name == "Liste des lauréats":
        return redirect(url_for("results.winners_page"))
    if item_name == "Administration":
        return redirect(url_for("admin.list_users"))
    if item_name == "Facturation":
        return redirect(url_for("invoicing.list_invoices"))

    if item_name not in MENU_ITEMS:
        return redirect(url_for("main.dashboard"))

    edition = get_edition(get_current_edition_id())
    _log("Navigation menu", details=f"{item_name} (édition {edition['id']})")

    return render_template(
        "placeholder.html", edition=edition, menu_items=MENU_ITEMS, active_item=item_name, title=item_name,
    )


@main_bp.route("/edition", methods=["GET", "POST"])
@login_required
def choose_edition():
    if request.method == "POST":
        new_edition_id = request.form.get("edition_id", "")
        if is_valid_edition(new_edition_id):
            old_edition_id = get_current_edition_id()
            set_current_edition_id(new_edition_id)
            if new_edition_id != old_edition_id:
                _log("Changement d'édition", details=new_edition_id)
        return redirect(url_for("main.dashboard"))

    return render_template(
        "choose_edition.html", editions=list_editions(), current_edition_id=get_current_edition_id(),
    )
