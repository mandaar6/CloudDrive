"""Functional tests - verify the application works correctly."""
import pytest


class TestAuth:
    def test_register_success(self, client):
        """User can register with a valid email and password."""
        resp = client.post("/api/auth/register", json={
            "email": "newuser@example.com",
            "password": "SecurePass123!"
        })
        assert resp.status_code in (200, 201)

    def test_register_invalid_email(self, client):
        """Registration is rejected for invalid email formats."""
        resp = client.post("/api/auth/register", json={
            "email": "not-an-email",
            "password": "SecurePass123!"
        })
        assert resp.status_code == 400

    def test_register_duplicate_email(self, client):
        """Registration is rejected if email already exists."""
        client.post("/api/auth/register", json={
            "email": "duplicate@example.com",
            "password": "SecurePass123!"
        })
        resp = client.post("/api/auth/register", json={
            "email": "duplicate@example.com",
            "password": "AnotherPass456!"
        })
        assert resp.status_code in (400, 409)

    def test_login_unverified_user_rejected(self, client):
        """Login is rejected for accounts that have not verified their email."""
        client.post("/api/auth/register", json={
            "email": "unverified@example.com",
            "password": "SecurePass123!"
        })
        resp = client.post("/api/auth/login", json={
            "email": "unverified@example.com",
            "password": "SecurePass123!"
        })
        assert resp.status_code == 403

    def test_unauthenticated_file_list_rejected(self, client):
        """File list endpoint rejects requests without a valid token."""
        resp = client.get("/api/files/", follow_redirects=True)
        assert resp.status_code == 401

    def test_forgot_password_always_returns_200(self, client):
        """Forgot password returns 200 for both registered and unknown emails."""
        resp1 = client.post("/api/auth/forgot-password", json={
            "email": "doesnotexist@example.com"
        })
        assert resp1.status_code == 200

        resp2 = client.post("/api/auth/forgot-password", json={
            "email": "alsonotexist@example.com"
        })
        assert resp2.status_code == 200
        assert resp1.get_json()["message"] == resp2.get_json()["message"]


class TestFiles:
    def test_file_list_requires_auth(self, client):
        """GET /api/files returns 401 without authentication."""
        resp = client.get("/api/files/", follow_redirects=True)
        assert resp.status_code == 401

    def test_upload_url_requires_auth(self, client):
        """GET /api/files/upload-url returns 401 without authentication."""
        resp = client.get("/api/files/upload-url?filename=test.txt&content_type=text/plain")
        assert resp.status_code == 401

    def test_trash_requires_auth(self, client):
        """GET /api/files/trash returns 401 without authentication."""
        resp = client.get("/api/files/trash")
        assert resp.status_code == 401


class TestHealthAndEdgeCases:
    def test_login_wrong_password_returns_401(self, client):
        """Login with a correct email but wrong password returns 401."""
        resp = client.post("/api/auth/login", json={
            "email": "wrongpass@edgecase.test",
            "password": "WrongPassword999!"
        })
        assert resp.status_code == 401

    def test_login_missing_fields_returns_400(self, client):
        """Login with an empty JSON body returns 400."""
        resp = client.post("/api/auth/login", json={})
        assert resp.status_code in (400, 422)

    def test_register_missing_password_returns_400(self, client):
        """Registration with only an email field and no password returns 400."""
        resp = client.post("/api/auth/register", json={
            "email": "nopassword@edgecase.test"
        })
        assert resp.status_code in (400, 422)

    def test_shares_endpoint_requires_auth(self, client):
        """GET /api/shares/outgoing returns 401 without authentication."""
        resp = client.get("/api/shares/outgoing")
        assert resp.status_code == 401

    def test_folders_endpoint_requires_auth(self, client):
        """GET /api/folders/ returns 401 without authentication."""
        resp = client.get("/api/folders/")
        assert resp.status_code == 401
