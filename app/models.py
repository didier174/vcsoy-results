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
    # Administrateur : accès à Administration et à la suppression de
    # données (Annuler un fichier). Voir aussi ADMIN_EMAILS (access_control.py).
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    # Édition sur laquelle démarrer l'outil à la connexion (voir
    # editions.resolve_startup_edition_id) ; sans effet pour les
    # administrateurs, qui démarrent toujours sur l'édition blanche.
    default_edition_id = db.Column(db.String(20), nullable=True)
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


class AuthorizedUser(db.Model):
    """
    Liste des adresses e-mail autorisées à se connecter, gérable depuis
    l'écran Administration. Vient en complément de la variable
    d'environnement ALLOWED_EMAILS (qui continue de fonctionner telle
    quelle) : un e-mail est autorisé s'il figure dans l'une OU l'autre des
    deux listes. Cela évite tout risque de blocage accidentel de l'accès
    lors de l'introduction de cette table.
    """

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    added_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    added_by = db.relationship("User")


class FileUpload(db.Model):
    """Historique des fichiers de résultats chargés avec succès, par édition."""

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)
    filename = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    added_count = db.Column(db.Integer, default=0)
    updated_count = db.Column(db.Integer, default=0)
    total_count = db.Column(db.Integer, default=0)

    uploaded_by = db.relationship("User")


class Invoice(db.Model):
    """
    Une facture générée pour un participant, rattachée à l'édition en
    cours. Les informations du participant sont dupliquées ici au moment
    de la génération (nom, adresse de facturation...) afin que la facture
    reste inchangée même si les données du participant sont modifiées par
    la suite.
    """

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=True)

    language = db.Column(db.String(2), default="fr")  # "fr" ou "en"
    invoice_number = db.Column(db.String(50))
    customer_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)

    # Instantané des informations de facturation du participant au moment
    # de la génération.
    bill_to_contact_name = db.Column(db.String(255), default="")
    bill_to_company_name = db.Column(db.String(255), default="")
    bill_to_address1 = db.Column(db.String(255), default="")
    bill_to_address2 = db.Column(db.String(255), default="")
    bill_to_city = db.Column(db.String(120), default="")
    bill_to_postal_code = db.Column(db.String(20), default="")
    bill_to_country = db.Column(db.String(20), default="")

    # [{"description": ..., "is_heading": bool, "quantity": 1, "unit_price": 0, "total": 0}, ...]
    line_items = db.Column(db.JSON)

    subtotal = db.Column(db.Float, default=0)
    gst_amount = db.Column(db.Float, default=0)
    qst_amount = db.Column(db.Float, default=0)
    total_amount = db.Column(db.Float, default=0)
    is_export = db.Column(db.Boolean, default=False)

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    participant = db.relationship("Participant")
    created_by = db.relationship("User")


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


class TestRecord(db.Model):
    """
    Le "record" d'un test mystère : la preuve du test (fichier audio pour
    un test Phone, PDF pour les autres canaux), liée à un TestResult par
    son ID Mystery Test. Stocké directement en base (comme le reste des
    données) plutôt que sur le disque du serveur, qui est réinitialisé à
    chaque déploiement Render.

    Un seul record par test : un rechargement du même ID Mystery Test met
    à jour le record existant plutôt que d'en créer un second.
    """

    id = db.Column(db.Integer, primary_key=True)
    test_result_id = db.Column(db.Integer, db.ForeignKey("test_result.id"), nullable=False, unique=True)

    filename = db.Column(db.String(255))
    content_type = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_size = db.Column(db.Integer)

    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    test_result = db.relationship("TestResult", backref=db.backref("record", uselist=False))
    uploaded_by = db.relationship("User")

    @property
    def is_audio(self):
        return bool(self.content_type) and self.content_type.startswith("audio/")


class ReportTemplate(db.Model):
    """
    Un modèle de rapport chargé pour « Rapport d'étude » : le fichier de
    base à partir duquel un rapport sera créé. Stocké directement en base
    (comme les records), le disque du serveur étant réinitialisé à chaque
    déploiement Render.
    """

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)

    filename = db.Column(db.String(255))
    content_type = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_size = db.Column(db.Integer)

    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship("User")


class StudyReport(db.Model):
    """
    Un rapport d'étude généré pour un participant, à partir d'un modèle
    de rapport (ReportTemplate) : le fichier PowerPoint résultant, balises
    {{ ... }} remplacées par les données du participant, est stocké
    directement en base (comme les modèles et les records), le disque du
    serveur étant réinitialisé à chaque déploiement Render.
    """

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)

    name = db.Column(db.String(255), nullable=False)

    participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=True)
    report_template_id = db.Column(db.Integer, db.ForeignKey("report_template.id"), nullable=True)

    filename = db.Column(db.String(255))
    content_type = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_size = db.Column(db.Integer)

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    participant = db.relationship("Participant")
    report_template = db.relationship("ReportTemplate")
    created_by = db.relationship("User")


class ScenarioTemplate(db.Model):
    """
    Un modèle chargé pour « Gestion des scénarios » > « Générer des
    scénarios » : soit un modèle de Book scénario, soit un modèle de
    Problématiques (kind). Stocké directement en base (comme les modèles
    de rapport), le disque du serveur étant réinitialisé à chaque
    déploiement Render.
    """

    KIND_BOOK = "book"
    KIND_PROBLEMATIQUES = "problematiques"

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)

    filename = db.Column(db.String(255))
    content_type = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_size = db.Column(db.Integer)

    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship("User")


class ScenarioFile(db.Model):
    """
    Un fichier scénario d'un participant (Book scénario ou Problématiques,
    voir kind), créé à partir d'un modèle (ScenarioTemplate) puis enrichi
    par la génération IA (voir ScenarioGenerationJob et app/scenarios/).
    """

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)
    # Nul pour un fichier chargé directement (voir upload_scenario_file) :
    # son type n'est pas demandé à l'utilisateur dans ce cas.
    kind = db.Column(db.String(20), nullable=True)

    name = db.Column(db.String(255), nullable=False)

    participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=True)
    source_template_id = db.Column(db.Integer, db.ForeignKey("scenario_template.id"), nullable=True)

    filename = db.Column(db.String(255))
    content_type = db.Column(db.String(100))
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_size = db.Column(db.Integer)

    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    participant = db.relationship("Participant")
    source_template = db.relationship("ScenarioTemplate")
    created_by = db.relationship("User")


class ScenarioGenerationJob(db.Model):
    """
    Suivi d'une génération de scénarios par IA (« Générer un book ») lancée
    en arrière-plan : la requête web renvoie immédiatement, la génération
    (qui peut prendre plusieurs minutes) continue dans un thread séparé, et
    cette table permet d'afficher son état/résultat à la prochaine
    consultation de la page (voir app/scenarios/routes.py, _run_generation).
    """

    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_ERROR = "error"

    id = db.Column(db.Integer, primary_key=True)
    edition_id = db.Column(db.String(20), nullable=False, index=True)
    participant_id = db.Column(db.Integer, db.ForeignKey("participant.id"), nullable=False)

    status = db.Column(db.String(20), nullable=False, default=STATUS_RUNNING)
    scenarios_generated = db.Column(db.Integer, nullable=True)
    error_message = db.Column(db.String(1000), nullable=True)

    # Usage réel renvoyé par l'API Anthropic (voir ai_generation.py), rempli
    # dès qu'une réponse a été obtenue même en cas d'échec après coup, pour
    # pouvoir suivre le coût engagé.
    input_tokens = db.Column(db.Integer, nullable=True)
    output_tokens = db.Column(db.Integer, nullable=True)
    web_search_count = db.Column(db.Integer, nullable=True)
    estimated_cost_usd = db.Column(db.Float, nullable=True)

    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    requested_by_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    requested_by_email = db.Column(db.String(255))

    participant = db.relationship("Participant")
    requested_by = db.relationship("User")
