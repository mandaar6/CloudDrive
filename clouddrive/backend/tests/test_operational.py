"""
Operational risk tests - verify core business functions
work correctly. Maps to operational-risks.md.
"""
import pytest


class TestCoreUploadFlow:
    """
    Tests for RISK-001: File upload flow must work end-to-end.
    The upload flow has two steps:
    1. GET /api/files/upload-url - generates presigned S3 URL
    2. POST /api/files/confirm-upload - saves metadata after S3 upload
    Both must work for the core feature to function.
    """

    def test_upload_url_endpoint_returns_required_fields(self, auth_client, auth_token):
        """
        Upload URL endpoint must return all fields needed for
        a browser to complete the direct S3 upload.
        If any field is missing, the upload silently fails.
        RISK-001: Silent upload failure.
        """
        resp = auth_client.get(
            "/api/files/upload-url?filename=test.txt&content_type=text/plain",
            headers={"Cookie": f"access_token={auth_token}"},
        )
        assert resp.status_code == 200, (
            f"Upload URL endpoint returned {resp.status_code}. "
            "Core upload feature is broken for all users."
        )
        data = resp.get_json()
        assert "upload_url" in data, (
            "Response missing upload_url. Browser cannot upload to S3."
        )
        assert "fields" in data, (
            "Response missing fields. Presigned POST will fail without these."
        )
        assert "s3_key" in data, (
            "Response missing s3_key. confirm-upload step will fail."
        )

    def test_confirm_upload_saves_file_metadata(self, auth_client, app, auth_token):
        """
        confirm-upload endpoint must save file metadata to the database.
        This is step 2 of the upload flow - if this fails, the file
        exists in S3 but is invisible to the user in their dashboard.
        RISK-001: Silent upload failure.
        """
        import uuid
        fake_s3_key = f"uploads/test@example.com/{uuid.uuid4()}/test.txt"

        resp = auth_client.post(
            "/api/files/confirm-upload",
            json={
                "filename": "test.txt",
                "s3_key": fake_s3_key,
                "size_bytes": 1234,
                "content_type": "text/plain",
            },
            headers={"Cookie": f"access_token={auth_token}"},
        )
        assert resp.status_code in (200, 201), (
            f"confirm-upload returned {resp.status_code}. "
            "Files will appear to upload but never show in dashboard."
        )
        data = resp.get_json()
        assert "id" in data or "file" in data or "filename" in data, (
            "confirm-upload did not return a file record. "
            "Cannot verify the file was saved."
        )

    def test_file_appears_in_list_after_upload(self, auth_client, app, auth_token):
        """
        After confirming an upload, the file must appear in the file list.
        This is the complete user-visible outcome of a successful upload.
        RISK-001: If the file list does not reflect the upload,
        users think their upload was lost.
        """
        import uuid
        fake_s3_key = f"uploads/test@example.com/{uuid.uuid4()}/visible.txt"

        auth_client.post(
            "/api/files/confirm-upload",
            json={
                "filename": "visible.txt",
                "s3_key": fake_s3_key,
                "size_bytes": 500,
                "content_type": "text/plain",
            },
            headers={"Cookie": f"access_token={auth_token}"},
        )

        list_resp = auth_client.get(
            "/api/files/",
            headers={"Cookie": f"access_token={auth_token}"},
        )
        assert list_resp.status_code == 200
        data = list_resp.get_json()
        if isinstance(data, list):
            files = data
        elif "files" in data:
            files = data["files"]
        else:
            files = data.get("owned", []) + data.get("shared", [])
        filenames = [f.get("filename") for f in files]
        assert "visible.txt" in filenames, (
            "File was confirmed uploaded but does not appear in the file list. "
            "Users would see their upload as lost. RISK-001."
        )


class TestCoreAuthFlow:
    """
    Tests for RISK-002: Login endpoint must always work for valid users.
    A broken login endpoint locks out every user simultaneously.
    """

    def test_valid_verified_user_can_login(self, app):
        """
        A verified user with the correct password must always be able
        to log in. This is the most fundamental user flow.
        RISK-002: If this fails, every user is locked out.

        Uses a fresh test client so the session-scoped shared client's
        cookie jar is not polluted with an auth cookie that would cause
        subsequent unauthenticated-access tests to see 404 instead of 401.
        """
        from app import db, bcrypt
        from app.models import User

        user = User(
            email="operational_test@example.com",
            password_hash=bcrypt.generate_password_hash(
                "OperationalPass123!"
            ).decode("utf-8"),
            is_verified=True,
        )
        db.session.add(user)
        db.session.commit()

        with app.test_client() as fresh_client:
            resp = fresh_client.post("/api/auth/login", json={
                "email": "operational_test@example.com",
                "password": "OperationalPass123!",
            })

        assert resp.status_code == 200, (
            f"Login returned {resp.status_code} for a valid verified user. "
            "RISK-002: All users would be locked out of the product."
        )
        cookies = resp.headers.getlist("Set-Cookie")
        has_token = any("access_token" in c for c in cookies)
        assert has_token, (
            "Login succeeded but no access_token cookie was set. "
            "User would be logged in according to the response but "
            "all subsequent requests would fail authentication."
        )

    def test_login_returns_proper_error_for_wrong_password(self, client):
        """
        Wrong password must return 401, not 500.
        A 500 on wrong password means the auth system is crashing,
        not just rejecting bad credentials.
        RISK-002: A 500 here affects all login attempts.
        """
        resp = client.post("/api/auth/login", json={
            "email": "doesnotexist@example.com",
            "password": "wrongpassword",
        })
        assert resp.status_code in (401, 403), (
            f"Wrong password returned {resp.status_code} instead of 401. "
            "A 500 here would mean the auth system is broken for everyone."
        )
        assert resp.status_code != 500, (
            "Login endpoint crashed on invalid credentials. RISK-002."
        )
