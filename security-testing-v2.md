# Security Testing Documentation: CloudDrive

**Version:** 2.0
**Date:** April 2026
**Author:** Mandaar Rao
**Change from v1.0:** Updated to reflect hardened architecture. Previously vulnerable tests now show PASS. New tests added for new attack surface. Real tool output from Trivy, Semgrep, pip-audit, and OWASP ZAP included.

---

## 1. Overview

This document covers security testing performed on CloudDrive v2.0. The application has been significantly hardened since v1.0. Tests are organized by the same three layers as the threat model: application, container infrastructure, and cloud configuration. Each test maps to a threat ID in the threat model.

All automated tool scans were run on April 26, 2026 against the live running application on Kali Linux.

---

## 2. Testing Environment

| Item | Details |
| :--- | :--- |
| OS | Kali Linux |
| Application URL | http://localhost |
| Docker version | 29.4.0 |
| Docker Compose version | 2.40.3 |
| SAST tool | Semgrep 1.159.0 (owasp-top-ten + secrets rulesets) |
| Dependency audit | pip-audit |
| Container scan | Trivy (HIGH/CRITICAL severity) |
| Dynamic scan | OWASP ZAP baseline scan (passive, unauthenticated) |
| Manual testing | Browser DevTools, curl |

---

## 3. Application Layer Tests

---

### TEST-001: Brute Force Rate Limiting (Maps to THREAT-001)

**Objective:** Confirm the login endpoint enforces rate limiting.

**Method:** Manual + Automated (pytest)

**Manual steps:**
```bash
for i in $(seq 1 6); do
  curl -s -X POST http://localhost/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@example.com","password":"wrongpassword"}' \
    -o /dev/null -w "Attempt $i: HTTP %{http_code}\n"
done
```

**Expected result:** Attempts 1-5 return HTTP 401. Attempt 6 returns HTTP 429.

**Actual result:** HTTP 429 returned on the 6th attempt. Rate limiter functioning correctly.

**Status:** PASS (was VULNERABLE in v1.0)

**Automated:** Yes, see test_security.py TEST-SEC-001.

---

### TEST-002: IDOR Prevention on File Download (Maps to THREAT-002)

**Objective:** Confirm a user cannot access another user's file by guessing the file ID.

**Method:** Manual + Automated (pytest)

**Steps:**
1. Register two accounts: userA and userB
2. Log in as userA, upload a file, note the UUID from the API response
3. Log in as userB, attempt GET /api/files/{userA_file_id}/download

**Expected result:** HTTP 403 Forbidden.

**Actual result:** HTTP 403 returned. File IDs are now UUIDs (unguessable). Ownership validation added to every file endpoint.

**Status:** PASS (was VULNERABLE in v1.0)

**Automated:** Yes, see test_security.py TEST-SEC-002.

---

### TEST-003: JWT Token Revocation After Logout (Maps to THREAT-003)

**Objective:** Confirm JWT tokens are invalidated after logout.

**Method:** Manual + Automated (pytest)

**Steps:**
1. Log in, copy the access_token cookie value
2. Log out via POST /api/auth/logout
3. Use the copied token to call GET /api/files

**Expected result:** HTTP 401 with message about revoked token.

**Actual result:** HTTP 401 returned. Token JTI found in RevokedToken table in PostgreSQL.

**Status:** PASS (was VULNERABLE in v1.0)

**Automated:** Yes, see test_security.py TEST-SEC-003.

---

### TEST-004: File Extension Validation (Maps to THREAT-005)

**Objective:** Confirm disallowed file extensions are rejected at the upload-url endpoint.

**Method:** Manual + Automated (pytest)

**Steps:**
```bash
curl -s "http://localhost/api/files/upload-url?filename=malware.exe&content_type=application/octet-stream" \
  -H "Cookie: access_token=VALID_TOKEN"
```

**Expected result:** HTTP 400 with "File type not allowed".

**Actual result:** HTTP 400 returned. Extension validation enforced before presigned URL is generated.

**Status:** PASS (was VULNERABLE in v1.0)

**Automated:** Yes, see test_security.py TEST-SEC-004.

---

### TEST-005: PII in Application Logs (Maps to THREAT-007)

**Objective:** Confirm user email addresses are not written to logs in the password reset flow.

**Method:** Semgrep SAST (real scan output)

**Semgrep findings:**
```
[WARNING] backend/app/auth.py:231
Rule: python-logger-credential-disclosure
"Password reset token generated for: %s" — email address logged

[WARNING] backend/app/auth.py:245
Rule: python-logger-credential-disclosure
"Password reset email sent to: %s" — email address logged

[WARNING] backend/app/auth.py:247
Rule: python-logger-credential-disclosure
"Failed to send password reset email to %s: %s" — email address logged
```

**Manual verification:** Triggered a password reset and confirmed email address visible in Grafana log stream.

**Status:** FAIL — CWE-532 confirmed. Email addresses present in logs.

**Remediation:** Remove email interpolation from log messages. Log user ID or action type only.

---

### TEST-006: Email Enumeration Prevention (Maps to THREAT-008)

**Objective:** Confirm forgot-password endpoint returns identical response for registered and unregistered emails.

**Method:** Manual

**Steps:**
```bash
curl -s -X POST http://localhost/api/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email":"registered@example.com"}'

curl -s -X POST http://localhost/api/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email":"doesnotexist@example.com"}'
```

**Expected result:** Both return HTTP 200 with identical response body.

**Actual result:** Both return HTTP 200 with "If that email exists, a password reset link has been sent." Enumeration prevented.

**Status:** PASS

---

### TEST-007: Missing HTTP Security Headers (Maps to THREAT-017)

**Objective:** Identify missing security headers in HTTP responses.

**Method:** OWASP ZAP Baseline Scan

**ZAP scan results (April 26, 2026 — 10 total alerts):**

| Risk | Alert | Description |
| :--- | :--- | :--- |
| Medium | Content Security Policy Header Not Set | No CSP header. Increases XSS attack surface. |
| Medium | Missing Anti-clickjacking Header | No X-Frame-Options or CSP frame-ancestors. |
| Low | Server Leaks Version via Server Header | nginx/1.25.5 disclosed in response. |
| Low | X-Content-Type-Options Header Missing | MIME sniffing not disabled. |
| Low | Cross-Origin-Embedder-Policy Missing | COEP not set. |
| Low | Cross-Origin-Opener-Policy Missing | COOP not set. |
| Low | Cross-Origin-Resource-Policy Missing | CORP not set. |
| Low | Permissions Policy Header Not Set | Browser features not restricted. |

**Status:** FAIL — 8 header findings. Scheduled for next sprint remediation via nginx.conf.

---

## 4. Container Infrastructure Layer Tests

---

### TEST-008: Container Non-Root User (Maps to THREAT-010)

**Objective:** Confirm backend container does not run as root.

**Method:** Manual

**Commands and results:**
```bash
$ sudo docker compose exec backend whoami
appuser

$ sudo docker compose exec backend id
uid=100(appuser) gid=101(appuser) groups=101(appuser)

$ sudo docker compose exec backend cat /proc/self/status | grep CapEff
CapEff: 0x0000000000000000
```

All Linux capabilities dropped. Container has no elevated privileges.

**Status:** PASS (was VULNERABLE in v1.0)

---

### TEST-009: Trivy Container CVE Scan

**Objective:** Identify known CVEs in the Docker image.

**Method:** Automated (Trivy)

**Command:** `sudo trivy image clouddrive-backend --severity HIGH,CRITICAL`

**Results (April 26, 2026 — HIGH only, CRITICAL: 0):**

| Package | Version | CVE | Severity | Fix |
| :--- | :--- | :--- | :--- | :--- |
| gunicorn | 21.2.0 | CVE-2024-1135 | HIGH | 22.0.0 |
| gunicorn | 21.2.0 | CVE-2024-6827 | HIGH | 22.0.0 |
| jaraco.context | 5.3.0 | CVE-2026-23949 | HIGH | 6.1.0 |
| wheel | 0.45.1 | CVE-2026-24049 | HIGH | 0.46.2 |
| openssl/libssl | system | CVE-2026-28388/9/90 | HIGH | patch available |

**Status:** 5 HIGH, 0 CRITICAL. Gunicorn CVEs retained intentionally for CI/CD demonstration. Documented in requirements.txt with fix versions noted.

---

### TEST-010: pip-audit Python Dependency Scan

**Objective:** Identify CVEs in Python packages.

**Method:** Automated (pip-audit)

**Command:** `pip-audit -r backend/requirements.txt`

**Results:**

| Package | Version | CVE | Fix |
| :--- | :--- | :--- | :--- |
| flask | 3.0.3 | CVE-2026-27205 | 3.1.3 |
| python-dotenv | 1.0.1 | CVE-2026-28684 | 1.2.2 |
| gunicorn | 21.2.0 | CVE-2024-1135 | 22.0.0 |
| gunicorn | 21.2.0 | CVE-2024-6827 | 22.0.0 |

**Clean packages:** PyJWT 2.12.0, werkzeug 3.1.6, flask-bcrypt, flask-limiter, boto3, SQLAlchemy, psycopg2-binary (all no vulnerabilities found)

**Status:** 4 findings. All accepted risk with documented fix paths.

---

### TEST-011: Semgrep SAST Scan

**Objective:** Identify security patterns in Flask source code.

**Method:** Automated (Semgrep)

**Command:** `semgrep --config=p/owasp-top-ten --config=p/secrets backend/`

**Results:**

| Severity | Rule | File | Line | Notes |
| :--- | :--- | :--- | :--- | :--- |
| ERROR | detected-bcrypt-hash | auth.py | 134 | False positive — test comparison value |
| WARNING | python-logger-credential-disclosure | auth.py | 231 | Real finding — email in log |
| WARNING | python-logger-credential-disclosure | auth.py | 245 | Real finding — email in log |
| WARNING | python-logger-credential-disclosure | auth.py | 247 | Real finding — email in log |
| WARNING | python-logger-credential-disclosure | config.py | 24 | Low severity — error type in log, not secret |

**Status:** 1 false positive, 4 genuine findings (3 confirmed PII logging issues).

---

## 5. Cloud Configuration Layer Tests

---

### TEST-012: S3 Bucket Private Access (Maps to THREAT-013)

**Objective:** Confirm S3 files are inaccessible via direct URL.

**Method:** Manual

**Steps:** Upload test file, copy direct S3 object URL from AWS console, open in incognito browser.

**Actual result:** HTTP 403 Access Denied. Block All Public Access confirmed. Bucket policy empty.

**Status:** PASS (was VULNERABLE in v1.0)

---

### TEST-013: IAM Least Privilege Verification (Maps to THREAT-014)

**Objective:** Confirm IAM user has minimal required permissions only.

**Method:** Manual (AWS Console)

**Result:** AmazonS3FullAccess confirmed NOT attached. CloudDriveAppPolicy confirmed attached with only: s3:GetObject, s3:PutObject, s3:DeleteObject on specific bucket ARN, s3:ListBucket on bucket, secretsmanager:GetSecretValue on the app secret.

**Status:** PASS (was VULNERABLE in v1.0)

---

### TEST-014: AWS Credentials Not in Git (Maps to THREAT-015)

**Objective:** Confirm no credentials in git history.

**Method:** Manual

**Commands:**
```bash
git log --all --full-history -- .env    # no results
git ls-files --error-unmatch .env       # error = not tracked (good)
cat .gitignore | grep .env              # .env present
```

**Status:** PASS

---

## 6. Test Summary

| Test | Layer | v1.0 Status | v2.0 Status |
| :--- | :--- | :--- | :--- |
| TEST-001: Rate limiting | App | VULNERABLE | PASS |
| TEST-002: IDOR prevention | App | VULNERABLE | PASS |
| TEST-003: JWT revocation | App | VULNERABLE | PASS |
| TEST-004: File extension validation | App | VULNERABLE | PASS |
| TEST-005: PII in logs | App | Not tested | FAIL (new finding) |
| TEST-006: Email enumeration | App | Not tested | PASS (new test) |
| TEST-007: HTTP security headers | App | Not tested | FAIL (ZAP finding) |
| TEST-008: Container non-root | Container | VULNERABLE | PASS |
| TEST-009: Trivy CVE scan | Container | 9 HIGH | 5 HIGH (improved) |
| TEST-010: pip-audit | All | Not run | 4 findings |
| TEST-011: Semgrep SAST | App | 1 blocking | 4 warnings |
| TEST-012: S3 private | Cloud | VULNERABLE | PASS |
| TEST-013: IAM least privilege | Cloud | VULNERABLE | PASS |
| TEST-014: Credentials not in git | Cloud | PASS | PASS |
