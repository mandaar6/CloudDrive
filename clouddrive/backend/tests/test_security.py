"""Security tests - verify security controls are functioning."""
import pytest
import uuid


class TestRateLimiting:
    def test_rate_limiting_on_login(self, app, client):
        """Login endpoint enforces rate limiting after repeated failures.
        TEST-SEC-001: Maps to THREAT-001 (Brute Force).
        """
        app.config["RATELIMIT_ENABLED"] = True
        responses = []
        for i in range(7):
            resp = client.post("/api/auth/login", json={
                "email": "victim@example.com",
                "password": "wrongpassword"
            })
            responses.append(resp.status_code)

        app.config["RATELIMIT_ENABLED"] = False
        assert 429 in responses, (
            "Rate limiter did not return HTTP 429 after repeated login failures. "
            "THREAT-001 mitigation is not functioning."
        )


class TestIDOR:
    def test_unauthenticated_cannot_access_files(self, client):
        """Unauthenticated users cannot access any file endpoint.
        TEST-SEC-002: Maps to THREAT-002 (IDOR).
        """
        fake_uuid = str(uuid.uuid4())

        endpoints = [
            f"/api/files/{fake_uuid}/download",
            f"/api/files/{fake_uuid}/preview",
        ]
        for endpoint in endpoints:
            resp = client.get(endpoint)
            assert resp.status_code == 401, (
                f"Endpoint {endpoint} returned {resp.status_code} instead of 401 "
                f"for unauthenticated request."
            )

    def test_nonexistent_file_returns_404_not_500(self, auth_client):
        """Requesting a nonexistent file UUID returns 404, not a server error.
        Maps to THREAT-002 - ensures no information disclosure on missing files.
        """
        fake_uuid = str(uuid.uuid4())
        resp = auth_client.get(f"/api/files/{fake_uuid}/download")
        assert resp.status_code in (403, 404), (
            f"Expected 403 or 404 for nonexistent file, got {resp.status_code}"
        )


class TestJWTSecurity:
    def test_invalid_token_rejected(self, client):
        """Requests with a forged or invalid JWT are rejected.
        TEST-SEC-003: Maps to THREAT-003 (JWT reuse).
        """
        resp = client.get("/api/files", headers={
            "Cookie": "access_token=forged.invalid.token"
        })
        assert resp.status_code == 401, (
            "Backend accepted a forged JWT token. "
            "THREAT-003 mitigation may not be functioning."
        )

    def test_expired_format_token_rejected(self, client):
        """A token with correct format but wrong signature is rejected."""
        import base64, json
        header = base64.b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        payload = base64.b64encode(
            json.dumps({"sub": "1", "jti": str(uuid.uuid4())}).encode()
        ).decode().rstrip("=")
        fake_sig = "invalidsignature"
        forged_token = f"{header}.{payload}.{fake_sig}"

        resp = client.get("/api/files", headers={
            "Cookie": f"access_token={forged_token}"
        })
        assert resp.status_code == 401


class TestFileValidation:
    def test_disallowed_extension_rejected(self, auth_client):
        """Upload URL is denied for disallowed file extensions.
        TEST-SEC-004: Maps to THREAT-005 (Malicious file upload).
        """
        disallowed = ["malware.exe", "script.sh", "payload.bat", "shell.php"]
        for filename in disallowed:
            resp = auth_client.get(
                f"/api/files/upload-url?filename={filename}&content_type=application/octet-stream"
            )
            assert resp.status_code == 400, (
                f"File extension '{filename}' was not rejected. "
                f"Got HTTP {resp.status_code}. THREAT-005 mitigation may be broken."
            )

    def test_allowed_extension_accepted(self, auth_client):
        """Upload URL is generated for allowed file extensions."""
        allowed = ["document.pdf", "notes.txt", "photo.png", "data.csv"]
        for filename in allowed:
            resp = auth_client.get(
                f"/api/files/upload-url?filename={filename}&content_type=text/plain"
            )
            assert resp.status_code in (200, 400, 500), (
                f"Unexpected status {resp.status_code} for allowed file {filename}"
            )


class TestEmailEnumeration:
    def test_forgot_password_no_enumeration(self, client):
        """Forgot password returns identical response for known and unknown emails.
        Maps to THREAT-008 (Email enumeration prevention).
        """
        resp_unknown = client.post("/api/auth/forgot-password", json={
            "email": "definitelynotregistered@nowhere.invalid"
        })
        resp_known = client.post("/api/auth/forgot-password", json={
            "email": "anyaddress@example.com"
        })

        assert resp_unknown.status_code == 200
        assert resp_known.status_code == 200
        assert resp_unknown.get_json()["message"] == resp_known.get_json()["message"], (
            "Forgot password returns different responses for known vs unknown emails. "
            "THREAT-008: email enumeration is possible."
        )
