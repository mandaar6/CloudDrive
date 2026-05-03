import re
import uuid
import jwt
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Blueprint, request, jsonify, make_response, current_app

from flask_mail import Message

from . import db, bcrypt, limiter, mail
from .models import User, RevokedToken, PasswordResetToken

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
logger  = logging.getLogger(__name__)

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_token(user_id: int) -> str:
    """Create a signed JWT for the given user ID with a unique jti claim."""
    cfg = current_app.config
    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
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

        jti = payload.get("jti")
        if jti and RevokedToken.query.filter_by(jti=jti).first():
            return jsonify({"error": "Token has been revoked"}), 401

        user = db.session.get(User, int(payload["sub"]))
        if not user:
            return jsonify({"error": "User not found"}), 401

        request.current_user  = user
        request.token_payload = payload
        return f(*args, **kwargs)
    return decorated


# ── Routes ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
@limiter.limit("10 per minute")
def register():
    data     = request.get_json(silent=True) or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    if not EMAIL_RE.match(email):
        return jsonify({"error": "Invalid email format"}), 400

    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409

    hashed             = bcrypt.generate_password_hash(password).decode("utf-8")
    verification_token = str(uuid.uuid4())

    user = User(
        email                      = email,
        password_hash              = hashed,
        is_verified                = False,
        verification_token         = verification_token,
        verification_token_expires = datetime.utcnow() + timedelta(hours=24),
    )
    db.session.add(user)
    db.session.commit()

    logger.info("registration user=%s id=%d", email, user.id)

    try:
        msg = Message(
            subject    = "Verify your CloudDrive email",
            recipients = [user.email],
            body       = (
                f"Click to verify your account:\n\n"
                f"http://localhost/verify-email?token={verification_token}\n\n"
                f"This link expires in 24 hours."
            ),
        )
        mail.send(msg)
        logger.info("Verification email sent to: %s", email)
    except Exception as exc:
        logger.error("Failed to send verification email to %s: %s", email, exc)

    return jsonify({
        "message": "Account created. Please check your email to verify your account."
    }), 201


@auth_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    data     = request.get_json(silent=True) or {}
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()

    # Use a constant-time check to prevent user-enumeration via timing
    dummy_hash = "$2b$12$KIX/RUGTjB8XqMbFb4jq8uYgBiClpBfN9MHp1dONKnfJf1XJ3t4Pi"
    if user:
        valid = bcrypt.check_password_hash(user.password_hash, password)
    else:
        bcrypt.check_password_hash(dummy_hash, password)
        valid = False

    if not valid:
        logger.warning("login_failure email=%s", email)
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.is_verified:
        return jsonify({"error": (
            "Please verify your email before logging in. "
            "Check your inbox for the verification link."
        )}), 403

    logger.info("login_success user=%s id=%d", email, user.id)

    token    = _make_token(user.id)
    response = make_response(jsonify({"message": "logged in", "user": user.to_dict()}))
    response.set_cookie(
        "access_token", token,
        httponly=True,
        samesite="Lax",
        max_age=int(current_app.config["JWT_EXPIRY"].total_seconds()),
    )
    return response


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    payload = request.token_payload
    jti     = payload.get("jti")
    if jti:
        exp_ts     = payload.get("exp")
        expires_at = datetime.utcfromtimestamp(exp_ts) if exp_ts else None
        db.session.add(RevokedToken(jti=jti, expires_at=expires_at))
        db.session.commit()

    response = make_response(jsonify({"message": "logged out"}))
    response.set_cookie("access_token", "", expires=0, httponly=True, samesite="Lax")
    return response


@auth_bp.route("/me", methods=["GET"])
@login_required
def me():
    return jsonify({"user": request.current_user.to_dict()})


@auth_bp.route("/verify-email", methods=["GET"])
def verify_email():
    token = request.args.get("token", "").strip()
    if not token:
        return jsonify({"error": "Token is required"}), 400

    user = User.query.filter_by(verification_token=token).first()
    if not user:
        return jsonify({"error": "Invalid token"}), 404

    if user.verification_token_expires < datetime.utcnow():
        return jsonify({"error": "Token expired"}), 400

    user.is_verified                = True
    user.verification_token         = None
    user.verification_token_expires = None
    db.session.commit()

    logger.info("Email verified for user id=%d", user.id)
    return jsonify({"message": "Email verified successfully. You can now log in."}), 200


@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data  = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "email is required"}), 400

    _success = {"message": "If that email exists, a password reset link has been sent."}

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify(_success), 200

    token_str   = str(uuid.uuid4())
    reset_token = PasswordResetToken(
        user_id    = user.id,
        token      = token_str,
        expires_at = datetime.utcnow() + timedelta(minutes=15),
    )
    db.session.add(reset_token)
    db.session.commit()

    logger.info("Password reset token generated for: %s", email)

    try:
        msg = Message(
            subject    = "Reset your CloudDrive password",
            recipients = [email],
            body       = (
                f"Click to reset your password:\n\n"
                f"http://localhost/reset-password?token={token_str}\n\n"
                f"This link expires in 15 minutes.\n\n"
                f"If you did not request this, ignore this email."
            ),
        )
        mail.send(msg)
        logger.info("Password reset email sent to: %s", email)
    except Exception as exc:
        logger.error("Failed to send password reset email to %s: %s", email, exc)

    return jsonify(_success), 200


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data         = request.get_json(silent=True) or {}
    token_str    = data.get("token") or ""
    new_password = data.get("new_password") or ""

    if not token_str or not new_password:
        return jsonify({"error": "token and new_password are required"}), 400

    reset_token = PasswordResetToken.query.filter_by(token=token_str).first()
    if not reset_token:
        return jsonify({"error": "Invalid token"}), 400

    if reset_token.used:
        return jsonify({"error": "Token already used"}), 400

    if reset_token.expires_at < datetime.utcnow():
        return jsonify({"error": "Token expired"}), 400

    user = db.session.get(User, reset_token.user_id)
    if not user:
        return jsonify({"error": "User not found"}), 400

    user.password_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
    reset_token.used   = True
    db.session.commit()

    logger.info("Password reset completed for user id=%d", user.id)
    return jsonify({"message": "Password reset successfully"}), 200
