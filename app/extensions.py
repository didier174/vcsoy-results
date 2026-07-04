"""
Instances partagées des extensions Flask, créées ici (sans application
attachée) puis initialisées dans create_app() — pattern classique pour
éviter les imports circulaires.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager()
oauth = OAuth()
