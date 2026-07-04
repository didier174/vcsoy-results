"""
Modèles de données communs (utilisateurs + historique des actions).
Les modèles métier (catégories, participants, ...) seront ajoutés dans les
prochaines étapes.
"""

from datetime import datetime

from flask_login import UserMixin

from app.extensions import db


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    name = db.Column(db.String(255))
    google_sub = db.Column(db.String(255), unique=True, nullable=True)
    picture_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_id(self):
        # Flask-Login exige une chaîne de caractères.
        return str(self.id)


class ActionLog(db.Model):
    """Journal des actions des utilisateurs, équivalent de history.json côté Mac."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    user_email = db.Column(db.String(255))
    edition_id = db.Column(db.String(20))
    action = db.Column(db.String(255))
    details = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")


class Category(db.Model):
    """Une catégorie, rattachée à une édition (edition_id)."""

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)
    category_name = db.Column(db.String(255), default="")
    display_name = db.Column(db.String(255), default="")
    code = db.Column(db.String(50), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def label(self):
        return self.display_name or self.category_name or "(sans nom)"


class Participant(db.Model):
    """Un participant, rattaché à une édition (edition_id)."""

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)

    participant_name = db.Column(db.String(255), default="")
    code = db.Column(db.String(2), default="")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    representative_name = db.Column(db.String(255), default="")
    representative_email = db.Column(db.String(255), default="")
    participant_phone = db.Column(db.String(50), default="")

    participant_address1 = db.Column(db.String(255), default="")
    participant_address2 = db.Column(db.String(255), default="")
    participant_city = db.Column(db.String(120), default="")
    participant_postal_code = db.Column(db.String(20), default="")
    participant_country = db.Column(db.String(20), default="Canada")

    billing_address1 = db.Column(db.String(255), default="")
    billing_address2 = db.Column(db.String(255), default="")
    billing_city = db.Column(db.String(120), default="")
    billing_postal_code = db.Column(db.String(20), default="")
    billing_country = db.Column(db.String(20), default="Canada")

    billing_contact_name = db.Column(db.String(255), default="")
    billing_contact_email = db.Column(db.String(255), default="")
    billing_contact_phone = db.Column(db.String(50), default="")

    channel_phone = db.Column(db.Boolean, default=False)
    channel_mail = db.Column(db.Boolean, default=False)
    channel_web = db.Column(db.Boolean, default=False)
    channel_rs = db.Column(db.Boolean, default=False)
    channel_chat = db.Column(db.Boolean, default=False)

    active_ref = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = db.relationship("Category")

    CHANNEL_FIELDS = ("channel_phone", "channel_mail", "channel_web", "channel_rs", "channel_chat")
    CHANNEL_LABELS = {
        "channel_phone": "Téléphone",
        "channel_mail": "Mail",
        "channel_web": "WEB",
        "channel_rs": "RS",
        "channel_chat": "Chat",
    }

    def category_label(self):
        return self.category.label() if self.category else "(catégorie supprimée)"

    def has_any_channel(self):
        return any(getattr(self, f) for f in self.CHANNEL_FIELDS)


class TestResult(db.Model):
    """
    Une ligne de test (un test mystère), importée depuis un onglet du fichier
    de résultat Excel. Rattachée à une édition, une catégorie et un
    participant (résolus à partir de l'ID Mystery Test : CCPPXXXX).

    Toutes les colonnes brutes de la ligne source (Code 1..15, leurs
    observations, les champs spécifiques au canal comme Call_Date, QS,
    Status, etc.) sont conservées telles quelles dans `raw_data`, en
    attendant que les futures étapes (calcul du score, présentation des
    résultats) définissent précisément quoi en extraire. Cela évite de
    devoir modifier le schéma de base de données à chaque nouvelle étape.
    """

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)

    channel = db.Column(db.String(20), nullable=False, index=True)  # "phone","mail","web","rs","chat"
    test_id = db.Column(db.String(20), nullable=False, index=True)  # ex: "44011201"
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=True)

    sheet_name = db.Column(db.String(50))
    row_number = db.Column(db.Integer)
    raw_data = db.Column(db.JSON)

    source_filename = db.Column(db.String(255))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    category = db.relationship("Category")
    participant = db.relationship("Participant")
    uploaded_by = db.relationship("User")

    CHANNELS = ["phone", "mail", "web", "rs", "chat"]
