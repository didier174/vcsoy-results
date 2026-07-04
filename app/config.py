"""
Configuration de l'application VCSOY RESULTS (web).

Toutes les valeurs sensibles viennent de variables d'environnement (jamais
codées en dur), pour pouvoir utiliser des valeurs différentes en local et
sur Render.
"""

import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

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

    # Connexion simplifiée (simple adresse e-mail, sans Google) — pratique en
    # développement local. À mettre à "0" en production une fois la
    # connexion Google validée, pour ne garder qu'une seule porte d'entrée.
    ALLOW_DEV_LOGIN = os.environ.get("ALLOW_DEV_LOGIN", "1") == "1"

    # Limite la taille des fichiers envoyés (chargement de résultats) à 20 Mo.
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
