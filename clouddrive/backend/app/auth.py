import jwt
import logging
from datetime import datetime, timezone
from functools import wraps

# new imports
import time
from flask import request
from .logging_utils import log_event


from flask import Blueprint, request, jsonify, make_response, current_app

from . import db, bcrypt
from .models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
logger  = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_token(user_id: int) -> str:
    """Create a signed JWT for the given user ID."""
    cfg = current_app.config
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + cfg["JWT_EXPIRY"],
    }
    return jwt.encode(payload, cfg["JWT_SECRET_KEY"], algorithm="HS256")


def _decode_token(token: str) -> dict:
    cfg = current_app.config
    return jwt.decode(token, cfg["JWT_SECRET_KEY"], algorithms=["HS256"])


def login_required(f):
    """Decorator that validates the JWT HTTP-only cookie."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("access_token")
        if not token:
            return jsonify({"error": "Authentication required"}), 401
        try:
            payload = _decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        # VULN: No server-side revocation check.
        # Even after a user "logs out" the token remains valid until expiry.
        # A stolen token can be replayed for up to JWT_EXPIRY_DAYS days.
        user = db.session.get(User, payload["sub"])
        if not user:
            return jsonify({"error": "User not found"}), 401

        request.current_user = user
        return f(*args, **kwargs)
    return decorated


# ── Routes ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email already registered"}), 409

    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    user   = User(email=email, password_hash=hashed)
    db.session.add(user)
    db.session.commit()

    logger.info("New user registered: %s (id=%d)", email, user.id)

    token    = _make_token(user.id)
    response = make_response(jsonify({"message": "registered", "user": user.to_dict()}), 201)
    # JWT stored as an HTTP-only cookie so it is not accessible via JS
    response.set_cookie(
        "access_token", token,
        httponly=True,
        samesite="Lax",
        max_age=int(current_app.config["JWT_EXPIRY"].total_seconds()),
    )
    return response


@auth_bp.route("/login", methods=["POST"])
def login():
    # VULN: No rate limiting on this endpoint.
    # An attacker can brute-force credentials with unlimited attempts.
    # Fix: add Flask-Limiter or a reverse-proxy rate-limit rule.
    start = time.time()

    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()

    # Use a constant-time check to prevent user-enumeration via timing
    dummy_hash = "$2b$12$KIX/RUGTjB8XqMbFb4jq8uYgBiClpBfN9MHp1dONKnfJf1XJ3t4Pi"
    if user:
        valid = bcrypt.check_password_hash(user.password_hash, password)
    else:
        bcrypt.check_password_hash(dummy_hash, password)  # timing equaliser
        valid = False

    if not valid:
        logger.warning("Failed login attempt for email: %s", email)

        log_event(
            "login_failure",
            level="warning",
            endpoint=request.path,
            http_status=401,
            ip=request.remote_addr,
            email=email
        )

        return jsonify({"error": "Invalid credentials"}), 401

    logger.info("User logged in: %s (id=%d)", email, user.id)

    log_event(
        "login_success",
        endpoint=request.path,
        http_status=200,
        ip=request.remote_addr,
        user_id=user.id,
        email=email,
        latency_ms=int((time.time() - start) * 1000)
    )

    token = _make_token(user.id)
    response = make_response(jsonify({
        "message": "logged in",
        "user": user.to_dict()
    }))
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="Lax",
        max_age=int(current_app.config["JWT_EXPIRY"].total_seconds()),
    )
    return response


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    # VULN: Logout only clears the cookie client-side.
    # The JWT itself is NOT added to a blocklist, so if someone captured the
    # raw token (e.g. from a proxy log) they can still use it until expiry.
    response = make_response(jsonify({"message": "logged out"}))
    response.set_cookie("access_token", "", expires=0, httponly=True, samesite="Lax")
    return response


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return jsonify({"user": request.current_user.to_dict()})
