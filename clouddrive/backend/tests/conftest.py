import os
import uuid
import pytest
from datetime import datetime, timezone, timedelta

# Set testing environment variables BEFORE any app imports
os.environ["TESTING"] = "true"
os.environ["FLASK_ENV"] = "testing"
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-jwt-signing-only")
os.environ.setdefault("SECRET_KEY", "test-flask-secret-only-for-testing-xyz")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("MAIL_SUPPRESS_SEND", "1")
os.environ.setdefault("MAIL_SERVER", "localhost")
os.environ.setdefault("RATELIMIT_STORAGE_URI", "memory://")

from flask.testing import FlaskClient
from app import create_app, db as _db


class _CookieHeaderClient(FlaskClient):
    """
    Werkzeug 3.x removed support for passing cookies via
    headers={"Cookie": "..."}.  Cookies must now be injected through
    set_cookie() / delete_cookie().  This subclass intercepts the old
    headers-based pattern, temporarily applies the cookies for the
    duration of the request, then cleans them up so tests remain
    isolated from one another.
    """

    def open(self, *args, **kwargs):
        headers = kwargs.get("headers") or {}
        cookie_str = None
        if isinstance(headers, dict):
            cookie_str = headers.pop("Cookie", None) or headers.pop("cookie", None)

        temp_cookies: list[str] = []
        if cookie_str:
            for pair in cookie_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    name, value = name.strip(), value.strip()
                    self.set_cookie(name, value)
                    temp_cookies.append(name)

        try:
            return super().open(*args, **kwargs)
        finally:
            for name in temp_cookies:
                self.delete_cookie(name)


@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.test_client_class = _CookieHeaderClient
    application.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret-key-for-jwt-signing-only",
        "RATELIMIT_ENABLED": False,
        "MAIL_SUPPRESS_SEND": True,
        "WTF_CSRF_ENABLED": False,
    })
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()


@pytest.fixture(scope="session")
def client(app):
    return app.test_client()


@pytest.fixture(scope="session")
def auth_token(client, app):
    """
    Creates a test user and returns a valid JWT without making an HTTP login
    request. Doing an HTTP login via the session-scoped client stores a cookie
    in the client's internal jar, which then bleeds into JWT security tests
    that deliberately pass forged cookies.

    Operates in the app fixture's already-active app context (no extra push)
    so that the committed user is visible to request contexts via the shared
    StaticPool SQLite connection.
    """
    import jwt as pyjwt
    from app import bcrypt
    from app.models import User

    existing = User.query.filter_by(email="testuser@example.com").first()
    if not existing:
        user = User(
            email="testuser@example.com",
            password_hash=bcrypt.generate_password_hash(
                "TestPass123!"
            ).decode("utf-8"),
            is_verified=True,
        )
        _db.session.add(user)
        _db.session.commit()
        user_id = user.id
    else:
        user_id = existing.id

    payload = {
        "sub": str(user_id),
        "jti": str(uuid.uuid4()),
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    token = pyjwt.encode(
        payload,
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )
    return token


@pytest.fixture(scope="session")
def auth_client(client, auth_token):
    """
    Returns the test client. Use auth_token directly in Cookie headers for
    reliable cookie passing.
    """
    return client
