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

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import AuthorizedUser, ActionLog, User, Category, Participant
from app.editions import get_current_edition_id, get_edition, list_editions, is_valid_edition
from app.access_control import ALLOWED_EMAILS, ADMIN_EMAILS, admin_required
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
    all_users = User.query.order_by(User.email).all()
    edition = get_edition(get_current_edition_id())
    return render_template(
        "admin/users.html",
        edition=edition, db_users=db_users, env_emails=env_emails, all_users=all_users,
        admin_emails=sorted(ADMIN_EMAILS), error=error, editions=list_editions(),
        active_item=ACTIVE_ITEM, menu_items=MENU_ITEMS,
    )


@admin_bp.route("/users", methods=["GET"])
@login_required
@admin_required
def list_users():
    return _render_users()


@admin_bp.route("/users/add", methods=["POST"])
@login_required
@admin_required
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
@admin_required
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


@admin_bp.route("/users/toggle-admin", methods=["POST"])
@login_required
@admin_required
def toggle_admin():
    user = User.query.get(request.form.get("user_id", type=int))
    if not user:
        return _render_users(error="Utilisateur introuvable.")
    if user.id == current_user.id:
        return _render_users(error="Vous ne pouvez pas modifier vos propres droits depuis cet écran.")

    user.is_admin = not user.is_admin
    db.session.commit()
    _log(
        "Modification droits administrateur",
        details=f"{user.email} -> {'administrateur' if user.is_admin else 'collaborateur standard'}",
    )
    return redirect(url_for("admin.list_users"))


@admin_bp.route("/edition/load", methods=["POST"])
@login_required
@admin_required
def load_edition():
    """
    Copie les catégories et les participants (rien d'autre — surtout pas
    les tests) d'une édition source vers une édition cible. Sans effet sur
    les catégories/participants déjà présents dans l'édition cible (une
    catégorie/un participant existant, identifié par son code, n'est
    jamais dupliqué) : l'opération peut donc être relancée sans risque.
    """
    source_id = request.form.get("source_edition", "").strip()
    target_id = request.form.get("target_edition", "").strip()

    if not is_valid_edition(source_id) or not is_valid_edition(target_id):
        return _render_users(error="Édition source ou cible invalide.")
    if source_id == target_id:
        return _render_users(error="L'édition source et l'édition cible doivent être différentes.")

    source_categories = Category.query.filter_by(edition_id=source_id).all()
    target_categories_by_code = {
        c.code: c for c in Category.query.filter_by(edition_id=target_id).all()
    }

    category_id_map = {}
    added_categories = 0
    for cat in source_categories:
        existing = target_categories_by_code.get(cat.code)
        if existing:
            category_id_map[cat.id] = existing.id
            continue
        new_cat = Category(
            edition_id=target_id, category_name=cat.category_name,
            display_name=cat.display_name, code=cat.code,
        )
        db.session.add(new_cat)
        db.session.flush()
        category_id_map[cat.id] = new_cat.id
        added_categories += 1

    source_participants = Participant.query.filter_by(edition_id=source_id).all()
    target_participant_keys = {
        (p.category_id, p.code) for p in Participant.query.filter_by(edition_id=target_id).all()
    }

    added_participants = 0
    skipped_participants = 0
    for p in source_participants:
        target_category_id = category_id_map.get(p.category_id)
        if target_category_id and (target_category_id, p.code) in target_participant_keys:
            skipped_participants += 1
            continue

        db.session.add(Participant(
            edition_id=target_id, participant_name=p.participant_name, code=p.code,
            category_id=target_category_id,
            representative_name=p.representative_name, representative_email=p.representative_email,
            participant_phone=p.participant_phone,
            participant_address1=p.participant_address1, participant_address2=p.participant_address2,
            participant_city=p.participant_city, participant_postal_code=p.participant_postal_code,
            participant_country=p.participant_country,
            billing_address1=p.billing_address1, billing_address2=p.billing_address2,
            billing_city=p.billing_city, billing_postal_code=p.billing_postal_code,
            billing_country=p.billing_country,
            billing_contact_name=p.billing_contact_name, billing_contact_email=p.billing_contact_email,
            billing_contact_phone=p.billing_contact_phone,
            channel_phone=p.channel_phone, channel_mail=p.channel_mail, channel_web=p.channel_web,
            channel_rs=p.channel_rs, channel_chat=p.channel_chat,
            active_ref=p.active_ref,
        ))
        added_participants += 1

    db.session.commit()

    _log(
        "Chargement d'édition",
        details=(
            f"{source_id} -> {target_id} : {added_categories} catégorie(s) et "
            f"{added_participants} participant(s) ajouté(s), {skipped_participants} déjà présent(s)"
        ),
    )
    flash(
        f"{added_categories} catégorie(s) et {added_participants} participant(s) copiés de "
        f"{source_id} vers {target_id} ({skipped_participants} participant(s) déjà présents ignorés).",
        "success",
    )
    return redirect(url_for("admin.list_users"))
