"""
Module « Administration ».

Permet de gérer la liste des utilisateurs autorisés à se connecter à
l'outil : ajout (adresse e-mail) et suppression. Cette liste est globale
(indépendante de l'édition en cours), puisque l'autorisation d'utiliser
l'outil ne dépend pas de l'édition qu'on est en train de consulter.

Vient en complément de la variable d'environnement ALLOWED_EMAILS, dont
les adresses restent toujours autorisées mais ne sont pas modifiables
depuis cet écran (elles sont affichées, marquées comme provenant de la
configuration serveur).
"""

import re

from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models import AuthorizedUser, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.access_control import ALLOWED_EMAILS
from app.menu import MENU_ITEMS

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ACTIVE_ITEM = "Administration"
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id, user_email=current_user.email,
        edition_id=get_current_edition_id(), action=action, details=details,
    )
    db.session.add(entry)
    db.session.commit()


def _render_users(error=None):
    db_users = AuthorizedUser.query.order_by(AuthorizedUser.email).all()
    env_emails = sorted(ALLOWED_EMAILS)
    edition = get_edition(get_current_edition_id())
    return render_template(
        "admin/users.html",
        edition=edition, db_users=db_users, env_emails=env_emails, error=error,
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@admin_bp.route("/users", methods=["GET"])
@login_required
def list_users():
    return _render_users()


@admin_bp.route("/users/add", methods=["POST"])
@login_required
def add_user():
    email = request.form.get("email", "").strip().lower()

    if not EMAIL_REGEX.match(email):
        return _render_users(error="Merci de saisir une adresse e-mail valide.")

    if email in ALLOWED_EMAILS:
        return _render_users(error="Cette adresse est déjà autorisée (configuration serveur).")

    if AuthorizedUser.query.filter_by(email=email).first():
        return _render_users(error="Cette adresse figure déjà dans la liste.")

    db.session.add(AuthorizedUser(email=email, added_by_id=current_user.id))
    db.session.commit()
    _log("Ajout utilisateur autorisé", details=email)

    return redirect(url_for("admin.list_users"))


@admin_bp.route("/users/delete", methods=["POST"])
@login_required
def delete_users():
    selected_ids = [int(i) for i in request.form.getlist("selected_ids")]
    if not selected_ids:
        return _render_users(error="Veuillez cocher au moins un utilisateur à supprimer.")

    to_delete = AuthorizedUser.query.filter(AuthorizedUser.id.in_(selected_ids)).all()

    if any(u.email == current_user.email.strip().lower() for u in to_delete):
        return _render_users(error="Vous ne pouvez pas retirer votre propre accès depuis cet écran.")

    emails = [u.email for u in to_delete]
    for u in to_delete:
        db.session.delete(u)
    db.session.commit()

    _log("Suppression utilisateur(s) autorisé(s)", details=", ".join(emails))
    return redirect(url_for("admin.list_users"))
