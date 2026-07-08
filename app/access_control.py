"""
Contrôle d'accès applicatif : restreint la connexion (Google ou mode
développement) aux adresses e-mail explicitement autorisées, et distingue
les administrateurs des collaborateurs réguliers.

Important : ceci est indépendant du statut "Test" de l'écran de
consentement Google. La liste de "test users" côté Google Cloud Console
contrôle qui peut *terminer le flux OAuth Google*, mais si l'application
est un jour publiée (ou si quelqu'un d'autre est ajouté côté Google sans
qu'on en soit informé), cette restriction Google disparaît. La liste
ci-dessous est donc la vraie barrière de sécurité, côté application.
"""

import os
from functools import wraps

from flask import abort
from flask_login import current_user


def _load_allowed_emails():
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


ALLOWED_EMAILS = _load_allowed_emails()


def is_email_allowed(email):
    """
    Retourne True si l'adresse e-mail peut se connecter à l'outil.

    Deux listes sont consultées, de façon additive (l'une OU l'autre) :
    - ALLOWED_EMAILS (variable d'environnement, non modifiable depuis
      l'interface) ;
    - la table AuthorizedUser, gérable depuis l'écran Administration.

    Si les deux sont vides, aucune restriction n'est appliquée -- pratique
    en tout début de configuration, mais à définir avant toute mise en
    production réelle.
    """
    email_norm = (email or "").strip().lower()
    if not email_norm:
        return False

    if email_norm in ALLOWED_EMAILS:
        return True

    # Import différé pour éviter un import circulaire (models.py importe
    # depuis extensions.py, pas depuis ce module).
    from app.models import AuthorizedUser

    if AuthorizedUser.query.filter_by(email=email_norm).first():
        return True

    db_has_entries = AuthorizedUser.query.first() is not None
    if not ALLOWED_EMAILS and not db_has_entries:
        return True  # aucune restriction configurée nulle part

    return False


def has_allowlist_configured():
    from app.models import AuthorizedUser
    return bool(ALLOWED_EMAILS) or AuthorizedUser.query.first() is not None


# --------------------------------------------------------------- Administrateurs
#
# Toutes les adresses autorisées (ALLOWED_EMAILS / AuthorizedUser) ont accès
# à l'outil, mais seuls les administrateurs peuvent gérer les accès
# (Administration) ou supprimer des données de test (Annuler un fichier).
# Comme pour ALLOWED_EMAILS, ADMIN_EMAILS est une variable d'environnement
# non modifiable depuis l'interface — c'est la barrière de sécurité de
# référence, qui ne dépend d'aucune donnée en base. Le champ User.is_admin
# permet en complément à un administrateur d'en promouvoir un autre depuis
# l'écran Administration, sans toucher à la configuration serveur.

def _load_admin_emails():
    raw = os.environ.get("ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


ADMIN_EMAILS = _load_admin_emails()


def user_is_admin(user):
    """Retourne True si l'utilisateur (objet User) a des droits d'administrateur."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    email = (getattr(user, "email", "") or "").strip().lower()
    return email in ADMIN_EMAILS or bool(getattr(user, "is_admin", False))


def admin_required(view_func):
    """Décorateur : bloque l'accès (403) aux utilisateurs non administrateurs."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not user_is_admin(current_user):
            abort(403)
        return view_func(*args, **kwargs)
    return wrapper
