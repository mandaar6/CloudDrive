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
    with app.app_context():
        from app import bcrypt
        user = User(
            email="testuser@example.com",
            password_hash=bcrypt.generate_password_hash(
                "TestPass123!"
            ).decode("utf-8"),
            is_verified=True
        )
        _db.session.add(user)
        _db.session.commit()

    resp = client.post("/api/auth/login", json={
        "email": "testuser@example.com",
        "password": "TestPass123!"
    })
    return client
