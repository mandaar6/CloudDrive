import os
import pytest

# Set testing environment variables BEFORE any app imports
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-only")
os.environ.setdefault("SECRET_KEY", "test-flask-secret-only")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("MAIL_SUPPRESS_SEND", "1")

from app import create_app, db as _db
from app.models import User

@pytest.fixture(scope="session")
def app():
    application = create_app()
    application.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret-key-only",
        "RATELIMIT_ENABLED": False,
        "MAIL_SUPPRESS_SEND": True,
        "WTF_CSRF_ENABLED": False,
    })
    with application.app_context():
        _db.create_all()
        yield application
        _db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_client(client, app):
    """Authenticated test client.

    Idempotent: only inserts the test user if it does not already exist,
    so multiple tests in the same session can reuse this fixture without
    triggering a UNIQUE-constraint failure on the email column.
    """
    with app.app_context():
        from app import bcrypt
        existing = User.query.filter_by(email="testuser@example.com").first()
        if existing is None:
            user = User(
                email="testuser@example.com",
                password_hash=bcrypt.generate_password_hash(
                    "TestPass123!"
                ).decode("utf-8"),
                is_verified=True,
            )
            _db.session.add(user)
            _db.session.commit()

    resp = client.post("/api/auth/login", json={
        "email": "testuser@example.com",
        "password": "TestPass123!",
    })
    assert resp.status_code in (200, 201), (
        f"auth_client login failed: {resp.status_code} "
        f"{resp.get_data(as_text=True)}"
    )
    return client