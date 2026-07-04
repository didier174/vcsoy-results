"""
Contrôle d'accès applicatif : restreint la connexion (Google ou mode
développement) aux adresses e-mail explicitement autorisées.

Important : ceci est indépendant du statut "Test" de l'écran de
consentement Google. La liste de "test users" côté Google Cloud Console
contrôle qui peut *terminer le flux OAuth Google*, mais si l'application
est un jour publiée (ou si quelqu'un d'autre est ajouté côté Google sans
qu'on en soit informé), cette restriction Google disparaît. La liste
ci-dessous est donc la vraie barrière de sécurité, côté application.
"""

import os


def _load_allowed_emails():
    raw = os.environ.get("ALLOWED_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


ALLOWED_EMAILS = _load_allowed_emails()


def is_email_allowed(email):
    """
    Retourne True si l'adresse e-mail peut se connecter à l'outil.

    Si ALLOWED_EMAILS n'est pas configurée (variable d'environnement vide),
    aucune restriction n'est appliquée -- pratique en tout début de
    configuration, mais à définir avant toute mise en production réelle.
    """
    if not ALLOWED_EMAILS:
        return True
    return (email or "").strip().lower() in ALLOWED_EMAILS


def has_allowlist_configured():
    return bool(ALLOWED_EMAILS)
