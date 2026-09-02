"""
Configuration de l'application VCSOY RESULTS (web).

Toutes les valeurs sensibles viennent de variables d'environnement (jamais
codées en dur), pour pouvoir utiliser des valeurs différentes en local et
sur Render.
"""

import os
from datetime import timedelta


class Config:
    # Render définit automatiquement la variable RENDER dans ses conteneurs
    # — sert ici à distinguer "vraie prod" de "poste de dev local", pour ne
    # JAMAIS démarrer en production avec le repli codé en dur ci-dessous
    # (qui, sinon, permettrait de forger cookies de session et jetons CSRF
    # si SECRET_KEY venait à manquer par erreur de configuration). En local,
    # le repli reste pratique pour démarrer sans .env dès le premier essai.
    if os.environ.get("RENDER") and not os.environ.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY manquant en production (Render) — refus de démarrer avec la valeur par "
            "défaut codée en dur. Définissez SECRET_KEY dans les variables d'environnement Render."
        )
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

    # pool_pre_ping : teste chaque connexion (requête minimale) avant de la
    # réutiliser, et la remplace silencieusement si elle est morte. Sans ça,
    # une connexion fermée côté serveur (Postgres géré par Render, qui coupe
    # les connexions inactives) fait planter la première requête suivante
    # avec une erreur SSL ("decryption failed or bad record mac") au lieu de
    # simplement en ouvrir une nouvelle. pool_recycle : ferme et remplace
    # une connexion avant qu'elle n'atteigne cet âge, par précaution
    # supplémentaire (marge sous les délais d'inactivité habituels).
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

    # Clé API Anthropic (Claude) : génération automatique des scénarios
    # (voir app/scenarios/ai_generation.py). Le SDK Anthropic lit aussi
    # directement ANTHROPIC_API_KEY depuis l'environnement.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

    # Connexion simplifiée (simple adresse e-mail, sans Google) — pratique en
    # développement local. Défaut "0" (désactivée) si la variable est
    # absente : mieux vaut devoir l'activer explicitement en local que de
    # risquer une réactivation silencieuse de cette porte dérobée en
    # production si la variable venait à disparaître par erreur (le fichier
    # .env local la définit explicitement à "1", donc le dev local n'est
    # pas affecté par ce changement de défaut).
    ALLOW_DEV_LOGIN = os.environ.get("ALLOW_DEV_LOGIN", "0") == "1"

    # Limite la taille totale d'une requête envoyée (chargement de fichiers).
    # 300 Mo pour permettre le chargement d'un lot de fichiers "records"
    # (audio notamment) en une seule fois, en plus du fichier Excel de
    # résultats (largement sous les 20 Mo initiaux).
    MAX_CONTENT_LENGTH = 300 * 1024 * 1024
