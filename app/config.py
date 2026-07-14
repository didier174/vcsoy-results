"""
Configuration de l'application VCSOY RESULTS (web).

Toutes les valeurs sensibles viennent de variables d'environnement (jamais
codées en dur), pour pouvoir utiliser des valeurs différentes en local et
sur Render.
"""

import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

    # Durcissement du cookie de session. SESSION_COOKIE_SECURE est
    # désactivé par défaut (nécessaire pour tester en local en http://),
    # mais activé explicitement sur Render (voir render.yaml) puisque le
    # site n'y est servi qu'en https. SameSite=Lax bloque l'envoi du cookie
    # depuis un site tiers (protection CSRF complémentaire), sans gêner la
    # navigation normale (liens, redirections OAuth).
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # En local (aucune variable DATABASE_URL définie) : base SQLite dans un
    # fichier local, zéro configuration nécessaire pour démarrer.
    # En production (Render) : DATABASE_URL est fournie automatiquement par
    # l'add-on PostgreSQL.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///vcsoy_dev.db")
    # Certains fournisseurs (dont Render, historiquement) donnent une URL
    # commençant par "postgres://" alors que SQLAlchemy exige "postgresql://".
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Clé API Anthropic (Claude) : génération automatique des scénarios
    # (voir app/scenarios/ai_generation.py). Le SDK Anthropic lit aussi
    # directement ANTHROPIC_API_KEY depuis l'environnement.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

    # Connexion simplifiée (simple adresse e-mail, sans Google) — pratique en
    # développement local. À mettre à "0" en production une fois la
    # connexion Google validée, pour ne garder qu'une seule porte d'entrée.
    ALLOW_DEV_LOGIN = os.environ.get("ALLOW_DEV_LOGIN", "1") == "1"

    # Limite la taille totale d'une requête envoyée (chargement de fichiers).
    # 300 Mo pour permettre le chargement d'un lot de fichiers "records"
    # (audio notamment) en une seule fois, en plus du fichier Excel de
    # résultats (largement sous les 20 Mo initiaux).
    MAX_CONTENT_LENGTH = 300 * 1024 * 1024
