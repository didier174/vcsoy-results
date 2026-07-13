"""
Routes d'authentification.

Deux portes d'entrée possibles :
- « Se connecter avec Google » (production) — via Authlib / OAuth2.
- Connexion simplifiée par e-mail (developpement local uniquement, activée
  par ALLOW_DEV_LOGIN=1), pour pouvoir travailler sans configurer de
  vraies identifiants Google tout de suite.
"""

import re

from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app, session
from flask_login import login_user, logout_user, login_required, current_user

from app.extensions import db, oauth
from app.models import User, ActionLog
from app.editions import get_current_edition_id, resolve_startup_edition_id, set_current_edition_id
from app.access_control import is_email_allowed

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def _log(user, action, details=""):
    entry = ActionLog(
        user_id=user.id,
        user_email=user.email,
        edition_id=get_current_edition_id(),
        action=action,
        details=details,
    )
    db.session.add(entry)
    db.session.commit()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    dev_login_enabled = current_app.config["ALLOW_DEV_LOGIN"]
    google_enabled = bool(current_app.config.get("GOOGLE_CLIENT_ID"))

    if request.method == "POST" and dev_login_enabled:
        email = request.form.get("email", "").strip().lower()
        if not EMAIL_REGEX.match(email):
            flash("Merci de saisir une adresse e-mail valide.", "error")
            return render_template("login.html", dev_login_enabled=dev_login_enabled, google_enabled=google_enabled)

        if not is_email_allowed(email):
            flash("Cette adresse n'est pas autorisée à accéder à VCSOY RESULTS. Contactez l'administrateur.", "error")
            return render_template("login.html", dev_login_enabled=dev_login_enabled, google_enabled=google_enabled)

        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(email=email, name=email.split("@")[0])
            db.session.add(user)
            db.session.commit()

        session.permanent = True
        login_user(user)
        set_current_edition_id(resolve_startup_edition_id(user))
        _log(user, "Ouverture de session (mode développement)")
        return redirect(url_for("main.dashboard"))

    return render_template("login.html", dev_login_enabled=dev_login_enabled, google_enabled=google_enabled)


@auth_bp.route("/google")
def google_login():
    redirect_uri = url_for("auth.google_callback", _external=True)
    # prompt="select_account" : force Google à toujours proposer le choix du
    # compte, pour que "Fermer la session" soit suivi d'une vraie reconnexion
    # explicite plutôt que d'un rattachement automatique silencieux au compte
    # Google déjà ouvert dans le navigateur.
    return oauth.google.authorize_redirect(redirect_uri, prompt="select_account")


@auth_bp.route("/google/callback")
def google_callback():
    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo") or {}

    email = (userinfo.get("email") or "").strip().lower()
    if not email:
        flash("La connexion Google n'a pas renvoyé d'adresse e-mail. Merci de réessayer.", "error")
        return redirect(url_for("auth.login"))

    if not is_email_allowed(email):
        flash("Cette adresse n'est pas autorisée à accéder à VCSOY RESULTS. Contactez l'administrateur.", "error")
        return redirect(url_for("auth.login"))

    name = userinfo.get("name") or email.split("@")[0]
    google_sub = userinfo.get("sub")
    picture = userinfo.get("picture")

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, name=name, google_sub=google_sub, picture_url=picture)
        db.session.add(user)
    else:
        user.name = name
        user.google_sub = google_sub
        user.picture_url = picture
    db.session.commit()

    session.permanent = True
    login_user(user)
    set_current_edition_id(resolve_startup_edition_id(user))
    _log(user, "Ouverture de session (Google)")
    return redirect(url_for("main.dashboard"))


@auth_bp.route("/logout")
@login_required
def logout():
    _log(current_user, "Fermeture de session")
    logout_user()
    return redirect(url_for("auth.login"))
