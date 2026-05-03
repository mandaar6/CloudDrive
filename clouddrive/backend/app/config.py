import json
import logging
import os
from datetime import timedelta

logger = logging.getLogger(__name__)


def _fetch_secrets_manager(secret_name: str, region: str) -> dict:
    """
    Attempt to retrieve a JSON secret from AWS Secrets Manager.
    Returns the parsed dict on success, or {} on any failure so callers
    can safely fall back to environment variables.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        client = boto3.client("secretsmanager", region_name=region)
        response = client.get_secret_value(SecretId=secret_name)
        raw = response.get("SecretString") or ""
        return json.loads(raw)
    except Exception as exc:
        logger.warning(
            "Secrets Manager unavailable (%s: %s) — falling back to env vars",
            type(exc).__name__, exc,
        )
        return {}


class Config:
    # ── AWS region is needed before the Secrets Manager call ──────────────────
    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

    # Fetch secrets once at class-definition time so every config attribute
    # below can reference _sm without repeating the call.
    _sm = _fetch_secrets_manager("clouddrive/app/secrets", AWS_REGION)

    # ── Flask ──────────────────────────────────────────────────────────────────
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret")
    FLASK_ENV  = os.environ.get("FLASK_ENV", "production")
    DEBUG      = False
    TESTING    = False

    # Maximum upload size: 10 MB
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    # ── Database ───────────────────────────────────────────────────────────────
    # POSTGRES_PASSWORD from Secrets Manager overrides the baked-in DATABASE_URL
    # only when the URL contains the placeholder password from the environment.
    _db_url = os.environ.get("DATABASE_URL", "")
    _sm_pg_password = _sm.get("POSTGRES_PASSWORD")
    if _sm_pg_password and _db_url:
        # Replace whatever password is in the URL with the one from Secrets Manager.
        # URL format: postgresql://user:PASSWORD@host:port/db
        try:
            from urllib.parse import urlparse, urlunparse
            _parsed = urlparse(_db_url)
            _db_url = urlunparse(_parsed._replace(
                netloc=f"{_parsed.username}:{_sm_pg_password}@{_parsed.hostname}:{_parsed.port}"
            ))
        except Exception:
            pass  # malformed URL — leave as-is

    SQLALCHEMY_DATABASE_URI        = _db_url or None
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── JWT ────────────────────────────────────────────────────────────────────
    # Secrets Manager value takes precedence; env var is the fallback.
    JWT_SECRET_KEY = _sm.get("JWT_SECRET_KEY") or os.environ.get("JWT_SECRET_KEY", "jwt-dev-secret")
    JWT_EXPIRY     = timedelta(hours=int(os.environ.get("JWT_EXPIRY_HOURS", 24)))

    # ── AWS / S3 ───────────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID     = os.environ.get("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
    S3_BUCKET_NAME        = os.environ.get("S3_BUCKET_NAME")

    # Presigned URL lifetime (seconds)
    S3_PRESIGNED_EXPIRY = 300

    # ── Rate limiting ──────────────────────────────────────────────────────────
    RATELIMIT_STORAGE_URI = "memory://"

    # ── Mail (Flask-Mail / Amazon SES SMTP) ────────────────────────────────────
    MAIL_SERVER         = os.getenv("MAIL_SERVER")
    MAIL_PORT           = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS        = os.getenv("MAIL_USE_TLS", "True") == "True"
    MAIL_USERNAME       = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD       = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_FROM")
