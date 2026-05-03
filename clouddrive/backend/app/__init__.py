import jwt
import logging
from datetime import datetime

from flask import Flask, request, jsonify, current_app
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db      = SQLAlchemy()
bcrypt  = Bcrypt()
mail    = Mail()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address)

# Auth endpoints that do not require a valid token — skip revocation check
_SKIP_REVOCATION = {
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
    "/api/auth/reset-password",
    "/api/auth/verify-email",
}


def create_app() -> Flask:
    app = Flask(__name__)

    # Load config
    from .config import Config
    app.config.from_object(Config)

    # Extensions
    db.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    # Blueprints
    from .auth  import auth_bp
    from .files import files_bp, shares_bp, folders_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(shares_bp)
    app.register_blueprint(folders_bp)

    # Structured logging to stdout
    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    @app.before_request
    def check_revoked_token():
        """Reject requests that carry a revoked JWT before they reach any endpoint."""
        if request.path in _SKIP_REVOCATION:
            return
        token = request.cookies.get("access_token")
        if not token:
            return
        try:
            payload = jwt.decode(
                token,
                current_app.config["JWT_SECRET_KEY"],
                algorithms=["HS256"],
            )
            jti = payload.get("jti")
            if jti:
                from .models import RevokedToken
                if RevokedToken.query.filter_by(jti=jti).first():
                    return jsonify({"error": "Token has been revoked"}), 401
        except jwt.InvalidTokenError:
            # Expired or malformed — the individual endpoint's decorator handles it
            pass

    with app.app_context():
        # Create tables (used for fresh dev environments; production uses migrations)
        db.create_all()

        # Remove expired revoked-token rows on startup to keep the table small
        from .models import RevokedToken
        try:
            RevokedToken.query.filter(
                RevokedToken.expires_at < datetime.utcnow()
            ).delete()
            db.session.commit()
        except Exception:
            db.session.rollback()

    return app


# Only create the app instance when running directly
# (not when imported by pytest)
import os
if os.environ.get("FLASK_ENV") != "testing" and \
   os.environ.get("TESTING") != "true":
    app = create_app()
