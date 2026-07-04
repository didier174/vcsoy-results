"""
Module « Configuration Participant ».

- Liste des participants avec case à cocher, Participants Name, Category
  Name, et Act Ref. (case à cocher directement modifiable, enregistrée
  immédiatement — sans passer par un mode édition).
- « Ajouter » / « Modifier » ouvrent une page de saisie dédiée (l'équivalent
  web de la fenêtre qui s'ouvrait « par-dessus » l'écran principal côté Mac),
  avec les champs du modèle fourni (mod_pres_saisi_part.pdf) et
  pré-remplissage automatique de l'adresse de facturation.
- « Modifier » n'accepte qu'un seul participant sélectionné à la fois
  (formulaire pensé pour un participant), comme sur la version Mac.
"""

import re

from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Category, Participant, ActionLog
from app.editions import get_current_edition_id, get_edition
from app.menu import MENU_ITEMS

participants_bp = Blueprint("participants", __name__, url_prefix="/participants")

COUNTRIES = ["Canada", "USA"]
CODE_REGEX = re.compile(r"^\d{2}$")


def _log(action, details=""):
    entry = ActionLog(
        user_id=current_user.id, user_email=current_user.email,
        edition_id=get_current_edition_id(), action=action, details=details,
    )
    db.session.add(entry)
    db.session.commit()


def _current_categories():
    return Category.query.filter_by(edition_id=get_current_edition_id()).order_by(Category.display_name).all()


def _render_list(error=None):
    edition_id = get_current_edition_id()
    participants = Participant.query.filter_by(edition_id=edition_id).order_by(Participant.id).all()
    return render_template(
        "participants/list.html",
        edition=get_edition(edition_id), participants=participants, error=error,
        active_item="Configuration Participant", menu_items=MENU_ITEMS,
    )


@participants_bp.route("/", methods=["GET"])
@login_required
def list_participants():
    return _render_list()


@participants_bp.route("/toggle_active/<int:participant_id>", methods=["POST"])
@login_required
def toggle_active(participant_id):
    edition_id = get_current_edition_id()
    participant = Participant.query.get(participant_id)
    if participant and participant.edition_id == edition_id:
        participant.active_ref = not participant.active_ref
        db.session.commit()
        _log(
            "Changement Act Ref. participant",
            details=f"{participant.participant_name} -> {participant.active_ref} (édition {edition_id})",
        )
    return redirect(url_for("participants.list_participants"))


@participants_bp.route("/edit", methods=["POST"])
@login_required
def edit_selected():
    """Reçoit la sélection de la liste et redirige vers le formulaire (un seul participant à la fois)."""
    selected_ids = request.form.getlist("selected_ids")
    if not selected_ids:
        return _render_list(error="Veuillez cocher au moins un participant à modifier.")
    if len(selected_ids) > 1:
        return _render_list(error="Veuillez ne sélectionner qu'un seul participant à la fois pour la modification.")
    return redirect(url_for("participants.edit_participant", participant_id=selected_ids[0]))


@participants_bp.route("/delete", methods=["POST"])
@login_required
def delete_selected():
    selected_ids = [int(i) for i in request.form.getlist("selected_ids")]
    if not selected_ids:
        return _render_list(error="Veuillez cocher au moins un participant à supprimer.")

    edition_id = get_current_edition_id()
    to_delete = Participant.query.filter(
        Participant.edition_id == edition_id, Participant.id.in_(selected_ids)
    ).all()
    count = len(to_delete)
    for p in to_delete:
        db.session.delete(p)
    db.session.commit()

    _log("Suppression participant(s)", details=f"{count} participant(s) (édition {edition_id})")
    return redirect(url_for("participants.list_participants"))


# ------------------------------------------------------------- formulaire

def _address_equal(p, prefix_a, prefix_b):
    fields = ("address1", "address2", "city", "postal_code", "country")
    for f in fields:
        if getattr(p, f"{prefix_a}_{f}") != getattr(p, f"{prefix_b}_{f}"):
            return False
    return True


def _billing_is_empty(p):
    return not any([
        p.billing_address1, p.billing_address2, p.billing_city, p.billing_postal_code,
    ])


def _validate_form(form):
    errors = []
    if not form.get("participant_name", "").strip():
        errors.append("Le nom du participant est obligatoire.")

    code = form.get("code", "").strip()
    if not code:
        errors.append("Le code du participant est obligatoire.")
    elif not CODE_REGEX.match(code):
        errors.append(f"Le code « {code} » n'est pas valide : il doit être composé d'exactement 2 chiffres (0-9).")

    if not form.get("category_id", "").strip():
        errors.append("La catégorie est obligatoire.")
    if not form.get("representative_name", "").strip():
        errors.append("Le nom du représentant est obligatoire.")
    channels = [form.get(f) for f in Participant.CHANNEL_FIELDS]
    if not any(channels):
        errors.append("Au moins un canal à tester doit être coché.")
    return errors


def _validate_code_uniqueness(participant, edition_id):
    """Le code participant doit être unique au sein de sa catégorie (édition en cours)."""
    if not participant.code or not CODE_REGEX.match(participant.code) or not participant.category_id:
        return []
    others = Participant.query.filter_by(edition_id=edition_id, category_id=participant.category_id).all()
    for other in others:
        if other.id != participant.id and other.code == participant.code:
            return [f"Le code « {participant.code} » est déjà utilisé par un autre participant de cette catégorie."]
    return []


def _apply_form(participant, form):
    participant.participant_name = form.get("participant_name", "").strip()
    participant.code = form.get("code", "").strip()
    category_id = form.get("category_id", "").strip()
    participant.category_id = int(category_id) if category_id else None
    participant.representative_name = form.get("representative_name", "").strip()
    participant.representative_email = form.get("representative_email", "").strip()
    participant.participant_phone = form.get("participant_phone", "").strip()

    participant.participant_address1 = form.get("participant_address1", "").strip()
    participant.participant_address2 = form.get("participant_address2", "").strip()
    participant.participant_city = form.get("participant_city", "").strip()
    participant.participant_postal_code = form.get("participant_postal_code", "").strip()
    participant.participant_country = form.get("participant_country", "Canada").strip()

    participant.billing_address1 = form.get("billing_address1", "").strip()
    participant.billing_address2 = form.get("billing_address2", "").strip()
    participant.billing_city = form.get("billing_city", "").strip()
    participant.billing_postal_code = form.get("billing_postal_code", "").strip()
    participant.billing_country = form.get("billing_country", "Canada").strip()

    participant.billing_contact_name = form.get("billing_contact_name", "").strip()
    participant.billing_contact_email = form.get("billing_contact_email", "").strip()
    participant.billing_contact_phone = form.get("billing_contact_phone", "").strip()

    for field in Participant.CHANNEL_FIELDS:
        setattr(participant, field, bool(form.get(field)))


def _render_form(participant, mode, errors=None):
    categories = _current_categories()

    same_address_default = _billing_is_empty(participant) or _address_equal(
        participant, "participant", "billing"
    )

    return render_template(
        "participants/form.html",
        participant=participant, categories=categories, countries=COUNTRIES,
        mode=mode, errors=errors or [], same_address_default=same_address_default,
        edition=get_edition(get_current_edition_id()), active_item="Configuration Participant",
        menu_items=MENU_ITEMS,
    )


@participants_bp.route("/add", methods=["GET", "POST"])
@login_required
def add_participant():
    edition_id = get_current_edition_id()

    if request.method == "POST":
        errors = _validate_form(request.form)
        participant = Participant(edition_id=edition_id)
        _apply_form(participant, request.form)
        errors += _validate_code_uniqueness(participant, edition_id)
        if errors:
            return _render_form(participant, mode="add", errors=errors)

        db.session.add(participant)
        db.session.commit()
        _log("Ajout participant", details=f"{participant.participant_name} (édition {edition_id})")
        return redirect(url_for("participants.list_participants"))

    blank = Participant(edition_id=edition_id, participant_country="Canada", billing_country="Canada")
    return _render_form(blank, mode="add")


@participants_bp.route("/<int:participant_id>/edit", methods=["GET", "POST"])
@login_required
def edit_participant(participant_id):
    edition_id = get_current_edition_id()
    participant = Participant.query.get(participant_id)
    if not participant or participant.edition_id != edition_id:
        return redirect(url_for("participants.list_participants"))

    if request.method == "POST":
        errors = _validate_form(request.form)
        _apply_form(participant, request.form)
        errors += _validate_code_uniqueness(participant, edition_id)
        if errors:
            return _render_form(participant, mode="edit", errors=errors)

        db.session.commit()
        _log("Modification participant", details=f"{participant.participant_name} (édition {edition_id})")
        return redirect(url_for("participants.list_participants"))

    return _render_form(participant, mode="edit")
