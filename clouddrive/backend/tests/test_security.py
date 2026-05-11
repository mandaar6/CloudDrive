"""
Security tests — verify security controls are functioning.
Each test maps to a threat in the threat model document.
"""
import pytest
import uuid
import base64
import json


class TestRateLimiting:

    def test_rate_limiting_on_login(self, app, client):

        app.config["RATELIMIT_ENABLED"] = True
        responses = []
        for i in range(7):
            resp = client.post("/api/auth/login", json={
                "email": "ratelimitTarget_xzq99@nowhere.invalid",  # unique throwaway
                "password": "wrongpassword"
            })
            responses.append(resp.status_code)

        app.config["RATELIMIT_ENABLED"] = False
        assert 429 in responses, (
            "Rate limiter did not return HTTP 429 after repeated login failures."
        )
    


class TestIDOR:
    def test_unauthenticated_cannot_access_files(self, client):
        """
        Unauthenticated users cannot access any file endpoint.
        TEST-SEC-002: Maps to THREAT-002 (IDOR).
        """
        fake_uuid = str(uuid.uuid4())
        endpoints = [
            f"/api/files/{fake_uuid}/download",
            f"/api/files/{fake_uuid}/preview",
        ]
        for endpoint in endpoints:
            resp = client.get(endpoint, follow_redirects=True)
            assert resp.status_code == 401, (
                f"Endpoint {endpoint} returned {resp.status_code} "
                f"instead of 401 for unauthenticated request."
            )

    def test_nonexistent_file_with_auth_returns_not_found(
        self, client, auth_token
    ):
        """
        Requesting a nonexistent file UUID with valid auth returns
        403 or 404, not a server error.
        Maps to THREAT-002 — ensures no information disclosure.
        """
        fake_uuid = str(uuid.uuid4())
        resp = client.get(
            f"/api/files/{fake_uuid}/download",
            headers={"Cookie": f"access_token={auth_token}"},
            follow_redirects=True
        )
        assert resp.status_code in (403, 404), (
            f"Expected 403 or 404 for nonexistent file, "
            f"got {resp.status_code}"
        )


class TestJWTSecurity:
    def test_invalid_token_rejected(self, client):
        """
        Requests with a forged JWT are rejected with 401.
        TEST-SEC-003: Maps to THREAT-003 (JWT reuse after logout).
        """
        resp = client.get(
            "/api/files/",
            headers={"Cookie": "access_token=forged.invalid.token"},
            follow_redirects=True
        )
        assert resp.status_code == 401, (
            "Backend accepted a forged JWT token. "
            "THREAT-003 mitigation may not be functioning. "
            f"Got: {resp.status_code}"
        )

    def test_algorithm_none_token_rejected(self, client):
        """
        A JWT with alg:none in the header is rejected.
        Protects against algorithm confusion attacks.
        """
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            json.dumps({
                "sub": "1",
                "jti": str(uuid.uuid4())
            }).encode()
        ).decode().rstrip("=")
        # alg:none means no signature
        forged_token = f"{header}.{payload}."

        resp = client.get(
            "/api/files/",
            headers={"Cookie": f"access_token={forged_token}"},
            follow_redirects=True
        )
        assert resp.status_code == 401, (
            f"Backend accepted alg:none JWT token. "
            f"Got: {resp.status_code}"
        )

    def test_wrong_signature_rejected(self, client):
        """
        A JWT with correct format but wrong signature is rejected.
        """
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(
            json.dumps({
                "sub": "1",
                "jti": str(uuid.uuid4())
            }).encode()
        ).decode().rstrip("=")
        forged_token = f"{header}.{payload}.invalidsignature"

        resp = client.get(
            "/api/files/",
            headers={"Cookie": f"access_token={forged_token}"},
            follow_redirects=True
        )
        assert resp.status_code == 401


class TestFileValidation:
    def test_disallowed_extension_rejected(self, client, auth_token):
        """
        Upload URL is denied for disallowed file extensions.
        TEST-SEC-004: Maps to THREAT-005 (Malicious file upload).
        """
        disallowed = [
            "malware.exe",
            "script.sh",
            "payload.bat",
            "shell.php"
        ]
        for filename in disallowed:
            resp = client.get(
                f"/api/files/upload-url"
                f"?filename={filename}"
                f"&content_type=application/octet-stream",
                headers={"Cookie": f"access_token={auth_token}"},
                follow_redirects=True
            )
            assert resp.status_code == 400, (
                f"File extension '{filename}' was not rejected. "
                f"Got HTTP {resp.status_code}. "
                f"THREAT-005 mitigation may be broken."
            )

    def test_allowed_extension_accepted(self, client, auth_token):
        """
        Upload URL endpoint does not reject allowed extensions.
        The request may fail for other reasons (e.g. S3 not available)
        but must not return 400 for extension validation.
        """
        allowed = ["document.pdf", "notes.txt", "photo.png", "data.csv"]
        for filename in allowed:
            resp = client.get(
                f"/api/files/upload-url"
                f"?filename={filename}"
                f"&content_type=text/plain",
                headers={"Cookie": f"access_token={auth_token}"},
                follow_redirects=True
            )
            # 400 would mean extension rejected — that is the failure case
            # 200, 500, or other codes are acceptable here
            assert resp.status_code != 400, (
                f"Allowed extension '{filename}' was incorrectly rejected. "
                f"Extension validation is too strict."
            )


class TestEmailEnumeration:
    def test_forgot_password_no_enumeration(self, client):
        """
        Forgot password returns identical response for known
        and unknown emails. Maps to THREAT-008.
        """
        resp_unknown = client.post(
            "/api/auth/forgot-password",
            json={"email": "definitelynotregistered@nowhere.invalid"}
        )
        resp_known = client.post(
            "/api/auth/forgot-password",
            json={"email": "anyaddress@example.com"}
        )

        assert resp_unknown.status_code == 200
        assert resp_known.status_code == 200
        assert (
            resp_unknown.get_json()["message"]
            == resp_known.get_json()["message"]
        ), (
            "Forgot password returns different responses for known vs "
            "unknown emails. THREAT-008: email enumeration is possible."
        )


class TestSecurityHeaders:
    def test_response_has_content_type_header(self, client):
        """
        Any API response includes a Content-Type header.
        Absence of Content-Type allows MIME-sniffing attacks.
        """
        resp = client.get("/api/files/")
        assert "Content-Type" in resp.headers, (
            "Response is missing Content-Type header. "
            "Browsers may MIME-sniff the response type."
        )

    def test_sql_injection_in_login_email_handled(self, client):
        """
        A SQL injection string in the email field returns 400 or 401,
        never a 500 server error. ORM parameterisation must hold.
        Maps to THREAT-006 (injection attacks).

        Uses a dedicated REMOTE_ADDR so the rate-limit bucket for this
        test is independent of the bucket exhausted by TestRateLimiting.
        """
        resp = client.post(
            "/api/auth/login",
            json={"email": "' OR '1'='1", "password": "anything"},
            environ_overrides={"REMOTE_ADDR": "192.0.2.10"},
        )
        assert resp.status_code in (400, 401), (
            f"SQL injection payload returned HTTP {resp.status_code}. "
            f"Expected 400 or 401 — server must not crash or leak data."
        )

    def test_very_long_input_handled_gracefully(self, client):
        """
        A 10 000-character email field returns 400 or 401, not a 500.
        The app must not crash or time-out on oversized input.

        Uses a dedicated REMOTE_ADDR so the rate-limit bucket for this
        test is independent of the bucket exhausted by TestRateLimiting.
        """
        import random
        import string
        long_email = "".join(random.choices(string.ascii_lowercase, k=10_000))
        resp = client.post(
            "/api/auth/login",
            json={"email": long_email, "password": "anything"},
            environ_overrides={"REMOTE_ADDR": "192.0.2.11"},
        )
        assert resp.status_code in (400, 401), (
            f"Oversized input returned HTTP {resp.status_code}. "
            f"Expected 400 or 401 — server must handle large payloads gracefully."
        )
