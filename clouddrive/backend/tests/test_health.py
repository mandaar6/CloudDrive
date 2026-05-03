"""Health and smoke tests added in HW5.

These give CI/CD a fast, deterministic signal that the application can
boot and reach its critical dependencies without making any network calls.
They run on every push and pull request via .github/workflows/ci-cd.yml.
"""
import pytest
from sqlalchemy import text


class TestAppFactory:
    def test_app_factory_returns_flask_app(self, app):
        """create_app() must return a configured Flask application."""
        assert app is not None
        assert app.name == "app"

    def test_testing_config_active(self, app):
        """The test app must run in TESTING mode with an in-memory database."""
        assert app.config["TESTING"] is True
        uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
        assert "sqlite" in uri or "memory" in uri, (
            f"Tests must run against sqlite/in-memory, got {uri!r}"
        )

    def test_jwt_secret_present(self, app):
        """JWT secret must be set; otherwise auth is silently broken."""
        assert app.config.get("JWT_SECRET_KEY"), (
            "JWT_SECRET_KEY missing - auth will not work"
        )


class TestDatabase:
    def test_db_connection_is_live(self, app):
        """SQLAlchemy must be able to execute a trivial query."""
        from app import db
        with app.app_context():
            result = db.session.execute(text("SELECT 1")).scalar()
            assert result == 1

    def test_user_table_exists(self, app):
        """The User table is the cornerstone of auth and must exist."""
        from app import db
        from app.models import User
        with app.app_context():
            count = db.session.query(User).count()
            assert count >= 0


class TestRouting:
    def test_unknown_route_returns_404(self, client):
        """Unknown routes return 404, not 500 (no stack-trace leaks)."""
        resp = client.get("/this-path-does-not-exist")
        assert resp.status_code == 404

    def test_register_endpoint_registered(self, client):
        """The register blueprint is wired up (not a 404)."""
        resp = client.post("/api/auth/register", json={})
        assert resp.status_code != 404


class TestSecurityHeaders:
    """Lightweight checks - failures here flag regressions in HTTP hardening."""

    def test_response_has_content_type(self, client):
        resp = client.post("/api/auth/forgot-password", json={
            "email": "anyone@example.com"
        })
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("Content-Type", "")

    def test_register_rejects_empty_payload(self, client):
        """Empty register payload must not 500 - it should 400."""
        resp = client.post("/api/auth/register", json={})
        assert resp.status_code == 400, (
            f"Empty register payload returned {resp.status_code}, "
            "expected 400. A 500 here means input validation is missing."
        )

    def test_login_rejects_empty_payload(self, client):
        """Empty login payload must not 500 - it should 400 or 401."""
        resp = client.post("/api/auth/login", json={})
        assert resp.status_code in (400, 401), (
            f"Empty login payload returned {resp.status_code}, "
            "expected 400 or 401."
        )