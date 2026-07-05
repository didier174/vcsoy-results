"""
Fabrique de l'application Flask (« application factory »).
"""

from flask import Flask

from app.config import Config
from app.extensions import db, login_manager, oauth


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

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
    from app.admin.routes import admin_bp
    from app.invoicing.routes import invoicing_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(participants_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(invoicing_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()

    return app
