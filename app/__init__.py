"""
Fabrique de l'application Flask (« application factory »).
"""

from flask import Flask
from flask_login import current_user
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Config
from app.extensions import db, login_manager, oauth, csrf


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Render (comme la plupart des PaaS) place l'application derrière un
    # proxy inverse qui termine le HTTPS : sans ProxyFix, Flask verrait
    # chaque requête comme du http:// simple (en-têtes X-Forwarded-* non
    # pris en compte), ce qui casserait la détection HTTPS nécessaire à
    # SESSION_COOKIE_SECURE et aux URLs externes (callback OAuth).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    csrf.init_app(app)

    oauth.init_app(app)
    if app.config.get("GOOGLE_CLIENT_ID"):
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )

    # Import différé pour éviter les imports circulaires avec les modèles/blueprints.
    from app.models import User
    from app.auth.routes import auth_bp
    from app.main.routes import main_bp
    from app.categories.routes import categories_bp
    from app.participants.routes import participants_bp
    from app.results.routes import results_bp
    from app.records.routes import records_bp
    from app.admin.routes import admin_bp
    from app.invoicing.routes import invoicing_bp
    from app.reports.routes import reports_bp
    from app.scenarios.routes import scenarios_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(participants_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(records_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(invoicing_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(scenarios_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.access_control import user_is_admin

    @app.context_processor
    def inject_permissions():
        return {"is_admin": user_is_admin(current_user)}

    from app.timezone_utils import format_local

    app.jinja_env.filters["local_dt"] = format_local

    with app.app_context():
        db.create_all()
        _seed_default_products()

    return app


def _seed_default_products():
    """
    Reprend dans le catalogue (modèle Product) les 2 produits qui existaient
    en dur avant l'introduction du catalogue : le droit d'utilisation de la
    marque VCSOY, et « Goodies » renommé « Pack Goodies initial » à 0 $ (voir
    demande explicite de l'utilisateur). Chaque produit du catalogue étant
    désormais rattaché à une seule langue, on crée une entrée fr et une
    entrée en pour chacun (ils étaient auparavant bilingues). Ne s'exécute
    qu'une fois : si un produit du même titre existe déjà, on ne le recrée pas.
    """
    from app.models import Product

    defaults = [
        ("Droit d'utilisation de la marque VCSOY à titre de gagnant pendant un an", "fr", 0.0),
        ("Right to use the trademark VCSOY as winner during one year", "en", 0.0),
        ("Pack Goodies initial", "fr", 0.0),
        ("Initial Goodies Pack", "en", 0.0),
    ]
    for title, language, price in defaults:
        if not Product.query.filter_by(title=title).first():
            db.session.add(Product(title=title, language=language, price=price))
    db.session.commit()
