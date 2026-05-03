# Threat Model: CloudDrive

**Version:** 2.0
**Date:** April 2026
**Method:** STRIDE
**Author:** Mandaar Rao
**Change from v1.0:** Updated to reflect current hardened architecture. All previously intentional vulnerabilities have been patched. New threats added for new attack surface introduced by direct S3 upload, email flows, AWS Secrets Manager, and Gunicorn.

---

## 1. Overview

This document covers the threat model for CloudDrive, a secure cloud file storage and sharing web application. The system allows users to register with email verification, upload files directly to AWS S3 via presigned POST URLs, and share files with configurable read or edit permissions. All authentication uses JWT tokens with a server-side revocation blocklist.

Threats are analyzed across three layers: the application layer, the container infrastructure layer, and the cloud configuration layer. This version reflects the current production-like state of the application after security hardening performed between v1.0 and v2.0.

---

## 2. System Components (Current Architecture)

| Component | Description |
| :--- | :--- |
| React Frontend | Browser-based UI served through Nginx |
| Flask Backend (Gunicorn) | REST API with 4 worker processes, handles auth, file operations, sharing |
| PostgreSQL | Stores users, file metadata, share records, revoked tokens, reset tokens |
| AWS S3 | Stores actual file bytes via direct browser upload using presigned POST URLs |
| AWS Secrets Manager | Stores JWT secret key and database password |
| AWS SES / Gmail SMTP | Sends verification and password reset emails |
| Nginx | Reverse proxy, routes requests, enforces TLS |
| Grafana + Loki + Promtail | OE dashboard, log storage, log collection |
| Docker Compose | Orchestrates all 7 containers with resource limits |

---

## 3. Data Flow (Current)

```
User Browser
     |
     | HTTP (localhost dev / HTTPS production)
     v
Nginx Container (port 80)
     |
     +---> /api/* --> Flask Backend (port 5000, internal only)
     |                    |
     |                    +---> PostgreSQL (port 5432, internal only)
     |                    |     (users, files, shares, revoked_tokens)
     |                    |
     |                    +---> AWS Secrets Manager (startup only)
     |                    |     (fetches JWT_SECRET_KEY, POSTGRES_PASSWORD)
     |                    |
     |                    +---> AWS S3 (generate presigned POST URL only)
     |                    |
     |                    +---> AWS SES/Gmail (send verification, reset emails)
     |                    |
     |                    +---> Loki (structured log events)
     |
     +---> /* --> Frontend container (React static files)
     |
     v
Browser uploads file DIRECTLY to AWS S3 (bypasses Flask/nginx entirely)
     |
     v
Browser calls POST /api/files/confirm-upload (metadata only, no file bytes)
```

**Key security properties of current data flow:**
- File bytes never pass through Flask or nginx — direct browser to S3
- JWT tokens stored as HTTP-only cookies — JavaScript cannot read them
- Passwords stored as bcrypt hashes — never logged or returned in responses
- AWS credentials in .env (gitignored) with Secrets Manager as primary source
- Presigned URLs expire in 300 seconds (5 minutes)

---

## 4. Trust Boundaries

| Boundary | Description | Current State |
| :--- | :--- | :--- |
| Internet to Nginx | Public-facing entry point | Exposed on port 80 |
| Nginx to Flask | Internal Docker network | Not exposed externally |
| Flask to PostgreSQL | Internal Docker network | Not exposed externally |
| Flask to AWS S3 | External HTTPS to AWS API | Authenticated via IAM credentials |
| Browser to AWS S3 | Direct upload via presigned POST URL | New boundary introduced in v2.0 |
| Flask to AWS Secrets Manager | External HTTPS at startup | Authenticated via same IAM credentials |
| Flask to SES/SMTP | External SMTP connection | Authenticated via SMTP credentials |
| Grafana | Exposed on port 3000 | Should be restricted in production |
| Loki | Exposed on port 3100 | Should be restricted in production |

---

## 5. STRIDE Threat Analysis

### 5.1 Application Layer

---

**THREAT-001 — Brute Force Login**
- **Category:** Spoofing
- **Component:** POST /api/auth/login
- **Description:** An attacker attempts repeated login attempts to guess a user's password or validate a list of stolen credentials (credential stuffing).
- **Likelihood:** High
- **Impact:** High
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** flask-limiter enforces 5 attempts per minute per IP. Returns HTTP 429 on violation.
- **Residual risk:** Rate limiting is per-IP. An attacker with a botnet of many IPs can distribute attempts below the threshold. No CAPTCHA or account lockout after N total failures.
- **Remaining recommendation:** Add account-level lockout after 20 total failures regardless of IP. Add CAPTCHA for unrecognized IPs.

---

**THREAT-002 — Insecure Direct Object Reference on File Access**
- **Category:** Elevation of Privilege
- **Component:** GET /api/files/:id/download, GET /api/files/:id/preview
- **Description:** An authenticated user attempts to access another user's file by manipulating the file ID in the request.
- **Likelihood:** Medium
- **Impact:** High
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** File IDs changed from sequential integers to UUIDs (uuid4). Ownership validation added to every file endpoint — returns 403 if requesting user is not the owner and has no active share record.
- **Residual risk:** Share permission enforcement is incomplete — read and edit permissions currently produce identical behavior at the API level.
- **Remaining recommendation:** Enforce edit vs read at the API level. Prevent read-only users from calling re-upload endpoint.

---

**THREAT-003 — JWT Token Reuse After Logout**
- **Category:** Elevation of Privilege
- **Component:** JWT authentication middleware
- **Description:** A stolen or captured JWT token remains valid after the legitimate user logs out, allowing an attacker to impersonate the user.
- **Likelihood:** Medium
- **Impact:** High
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** RevokedToken table in PostgreSQL stores the JTI of every logged-out token. before_request hook checks this table on every authenticated request. Token expiry reduced from 30 days to 24 hours.
- **Residual risk:** The RevokedToken table grows over time. Cleanup runs at startup only, not continuously. A very large table could slow down authentication under sustained load.
- **Remaining recommendation:** Add a scheduled cleanup job to remove expired revoked tokens periodically.

---

**THREAT-004 — Presigned URL Forwarding**
- **Category:** Information Disclosure
- **Component:** Presigned S3 download URLs
- **Description:** A user who receives a presigned download URL can forward it to any other person. The URL works for anyone who has it regardless of authentication state.
- **Likelihood:** Medium
- **Impact:** Medium
- **Status in v2.0:** PARTIALLY MITIGATED
- **Mitigation applied:** Presigned URL expiry reduced from 3600 seconds to 300 seconds (5 minutes). S3 bucket is now private — direct S3 object URLs return 403.
- **Residual risk:** A forwarded URL is still valid for 5 minutes. For highly sensitive files, 5 minutes is still a meaningful window.
- **Remaining recommendation:** Add user-agent or IP binding to presigned URLs via S3 conditions. Notify file owner when a download occurs.

---

**THREAT-005 — Malicious File Upload**
- **Category:** Tampering
- **Component:** GET /api/files/upload-url (presigned POST generation)
- **Description:** An attacker uploads malicious files (executables, scripts) disguised as permitted file types, or uploads extremely large files to exhaust S3 storage and inflate AWS costs.
- **Likelihood:** Medium
- **Impact:** Medium
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** Extension allowlist enforced at the upload-url endpoint before presigned URL is generated. S3 presigned POST conditions include a content-length-range constraint (1 byte to 5GB). File type checked before the presigned URL is issued.
- **Residual risk:** Extension can be spoofed (rename .exe to .pdf). No server-side MIME type verification. No malware scanning. The 5GB limit is intentionally generous.
- **Remaining recommendation:** Add MIME type sniffing via python-magic. Add AWS Lambda trigger on S3 upload to scan with ClamAV or AWS GuardDuty.

---

**THREAT-006 — Sensitive Information in Error Responses**
- **Category:** Information Disclosure
- **Component:** Flask error handlers
- **Description:** Unhandled exceptions return stack traces or internal details to the client.
- **Likelihood:** Low
- **Impact:** Low
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** Flask running in production mode (FLASK_ENV=production, DEBUG=False) via Gunicorn. Generic error responses returned to clients. Detailed errors logged internally to Loki only.
- **Residual risk:** Some endpoints may still return verbose error messages in edge cases. Not fully audited.

---

**THREAT-007 — Email Address Logged in Password Reset Flow**
- **Category:** Information Disclosure
- **Component:** POST /api/auth/forgot-password, POST /api/auth/reset-password
- **Description:** Semgrep identified that user email addresses are logged during the password reset flow. Logs containing PII create compliance risk and may expose user identity if logs are accessed.
- **Likelihood:** Low
- **Impact:** Medium
- **Status in v2.0:** IDENTIFIED (Semgrep finding, not yet remediated)
- **CVE/Reference:** CWE-532 — Insertion of Sensitive Information into Log File
- **Affected lines:** auth.py lines 231, 245, 247
- **Recommended fix:** Remove email address from log messages. Log only non-identifying information such as user ID or action type.

---

**THREAT-008 — Email Verification Token Enumeration**
- **Category:** Spoofing
- **Component:** GET /api/auth/verify-email, POST /api/auth/forgot-password
- **Description:** Verification tokens and password reset tokens are UUID4 values. If the token generation uses a weak random source, tokens could be predicted or enumerated. Additionally, the forgot-password endpoint could be used to enumerate valid email addresses if it returns different responses for registered vs unregistered emails.
- **Likelihood:** Low
- **Impact:** High
- **Status in v2.0:** PARTIALLY MITIGATED
- **Mitigation applied:** Python's uuid.uuid4() uses os.urandom() which is cryptographically secure. Forgot-password endpoint returns the same success message regardless of whether the email exists (prevents enumeration).
- **Residual risk:** Tokens have a 15-minute expiry for password reset and 24-hour expiry for email verification. If an attacker intercepts an email (man-in-the-middle on the mail server), they have that window to use the token.

---

**THREAT-009 — Gunicorn HTTP Request Smuggling**
- **Category:** Tampering
- **Component:** Gunicorn WSGI server
- **Description:** Gunicorn 21.2.0 does not properly validate Transfer-Encoding headers, enabling HTTP Request Smuggling attacks. An attacker can craft requests with conflicting Transfer-Encoding headers to bypass security controls, access restricted endpoints, or perform cache poisoning.
- **Likelihood:** Medium (requires network path without filtering)
- **Impact:** High
- **Status in v2.0:** KNOWN VULNERABILITY — ACCEPTED RISK (temporary)
- **CVEs:** CVE-2024-1135, CVE-2024-6827
- **Fix available:** Upgrade to gunicorn==22.0.0
- **Reason not yet patched:** Retained intentionally to demonstrate CI/CD vulnerability detection in future sprint. Documented in requirements.txt.
- **Recommended fix:** Upgrade gunicorn to 22.0.0 in requirements.txt and rebuild Docker image.

---

### 5.2 Container Infrastructure Layer

---

**THREAT-010 — Container Privilege Escalation**
- **Category:** Elevation of Privilege
- **Component:** Flask backend Dockerfile
- **Description:** If the backend container runs as root and an attacker achieves code execution, they have full root access inside the container which may facilitate escape.
- **Likelihood:** Low
- **Impact:** Critical
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** Dockerfile creates a non-root system user (appuser, uid=100) and switches to it before starting Gunicorn. Verified: `docker compose exec backend whoami` returns `appuser`. Container capabilities confirmed dropped (CapEff: 0x0000000000000000).

---

**THREAT-011 — Container Resource Exhaustion**
- **Category:** Denial of Service
- **Component:** Docker Compose configuration
- **Description:** A misbehaving or attacked container consumes all host memory or CPU, taking down the entire application stack.
- **Likelihood:** Medium
- **Impact:** Medium
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** All 7 containers have resource limits in docker-compose.yml (memory: 512m, cpus: 0.5). Grafana and Loki set to 64m and 0.25 CPU since they are observability-only.

---

**THREAT-012 — Grafana and Loki Exposed on Public Ports**
- **Category:** Information Disclosure
- **Component:** Grafana (port 3000), Loki (port 3100)
- **Description:** Grafana is exposed on 0.0.0.0:3000 and Loki on 0.0.0.0:3100. In a production deployment on EC2, this would expose the operational dashboard and log query API to the internet. An attacker could query Loki directly to extract application logs including user emails, file names, and activity patterns.
- **Likelihood:** High (if deployed to EC2 without firewall)
- **Impact:** High
- **Status in v2.0:** IDENTIFIED — acceptable in local dev, critical gap for production
- **Recommended fix:** Remove port mappings for Grafana and Loki from docker-compose.yml in production. Access them via SSH tunnel only. Alternatively, add Nginx authentication in front of Grafana.

---

### 5.3 Cloud Configuration Layer

---

**THREAT-013 — AWS S3 Public Access**
- **Category:** Information Disclosure
- **Component:** S3 bucket policy
- **Description:** A publicly readable S3 bucket allows anyone with a direct object URL to download files without authentication.
- **Likelihood:** N/A
- **Impact:** Critical
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** Public bucket policy removed. Block All Public Access enabled at both account and bucket level. All access via presigned URLs only.

---

**THREAT-014 — Overprivileged IAM Credentials**
- **Category:** Elevation of Privilege
- **Component:** IAM user clouddrive-app
- **Description:** Overprivileged IAM credentials allow an attacker who obtains them to access all S3 resources in the AWS account, not just the CloudDrive bucket.
- **Likelihood:** Medium
- **Impact:** Critical
- **Status in v2.0:** MITIGATED
- **Mitigation applied:** Custom IAM policy CloudDriveAppPolicy attached, allowing only s3:GetObject, s3:PutObject, s3:DeleteObject on the specific bucket ARN and s3:ListBucket on the bucket itself. AmazonS3FullAccess removed.

---

**THREAT-015 — AWS Credentials Exposure**
- **Category:** Information Disclosure
- **Component:** .env file, AWS access keys
- **Description:** AWS access keys stored in plaintext .env file. If committed to Git or if the host machine is compromised, credentials are immediately usable by an attacker.
- **Likelihood:** Medium
- **Impact:** Critical
- **Status in v2.0:** PARTIALLY MITIGATED
- **Mitigation applied:** .env added to .gitignore. Git history confirmed clean. AWS Secrets Manager integrated — JWT secret and DB password fetched from Secrets Manager at startup. AWS access keys remain in .env as the mechanism for authenticating to Secrets Manager itself.
- **Residual risk:** Static AWS access keys still required locally. In production, an IAM instance role on EC2 would eliminate this entirely.
- **Recommended fix:** Deploy to EC2 with IAM instance role. Remove AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY from .env entirely.

---

**THREAT-016 — Flask Missing Vary:Cookie Header**
- **Category:** Information Disclosure
- **Component:** Flask session handling
- **Description:** Flask 3.0.3 does not set the Vary: Cookie header in all session access patterns. A caching proxy between the user and the server may cache a response intended for an authenticated user and serve it to an anonymous user.
- **Likelihood:** Low (requires a caching proxy in the path)
- **Impact:** Medium
- **Status in v2.0:** KNOWN VULNERABILITY — ACCEPTED RISK (temporary)
- **CVE:** CVE-2026-27205
- **Fix available:** Upgrade to flask==3.1.3
- **Reason not yet patched:** Retained to demonstrate dependency vulnerability management in CI/CD pipeline.

---

**THREAT-017 — Missing HTTP Security Headers**
- **Category:** Tampering / Information Disclosure
- **Component:** Nginx configuration
- **Description:** ZAP baseline scan identified missing security headers: Content-Security-Policy, X-Frame-Options (clickjacking), X-Content-Type-Options, server version disclosure via Server header, and missing CORS policy headers.
- **Likelihood:** Medium
- **Impact:** Medium
- **Status in v2.0:** IDENTIFIED — not yet remediated
- **ZAP findings:** 8 alerts including Medium risk CSP and clickjacking findings
- **Recommended fix:** Add security headers to nginx.conf server block. Set server_tokens off to suppress version disclosure.

---

## 6. Threat Summary

| ID | Description | Category | Layer | Likelihood | Impact | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| THREAT-001 | Brute force login | Spoofing | App | Medium | High | Mitigated |
| THREAT-002 | IDOR on file access | Elevation of Privilege | App | Medium | High | Mitigated |
| THREAT-003 | JWT reuse after logout | Elevation of Privilege | App | Low | High | Mitigated |
| THREAT-004 | Presigned URL forwarding | Information Disclosure | App | Medium | Medium | Partial |
| THREAT-005 | Malicious file upload | Tampering | App | Medium | Medium | Mitigated |
| THREAT-006 | Verbose error responses | Information Disclosure | App | Low | Low | Mitigated |
| THREAT-007 | PII in log files | Information Disclosure | App | Low | Medium | Identified |
| THREAT-008 | Email token enumeration | Spoofing | App | Low | High | Partial |
| THREAT-009 | Gunicorn request smuggling | Tampering | App | Medium | High | Accepted risk |
| THREAT-010 | Container privilege escalation | Elevation of Privilege | Container | Low | Critical | Mitigated |
| THREAT-011 | Container resource exhaustion | Denial of Service | Container | Low | Medium | Mitigated |
| THREAT-012 | Grafana/Loki exposed publicly | Information Disclosure | Container | High | High | Identified |
| THREAT-013 | S3 public access | Information Disclosure | Cloud | N/A | Critical | Mitigated |
| THREAT-014 | Overprivileged IAM | Elevation of Privilege | Cloud | Low | Critical | Mitigated |
| THREAT-015 | AWS credential exposure | Information Disclosure | Cloud | Medium | Critical | Partial |
| THREAT-016 | Flask Vary:Cookie missing | Information Disclosure | Cloud | Low | Medium | Accepted risk |
| THREAT-017 | Missing HTTP security headers | Tampering | App/Nginx | Medium | Medium | Identified |

---

## 7. Changes from v1.0

| Change | Reason |
| :--- | :--- |
| All v1.0 threats marked as intentional updated to reflect actual status | Architecture was hardened between v1.0 and v2.0 |
| THREAT-007 added | Semgrep finding: PII logged in password reset flow |
| THREAT-008 added | New attack surface: email verification and password reset tokens |
| THREAT-009 added | pip-audit finding: Gunicorn HTTP request smuggling CVEs |
| THREAT-010 updated | Confirmed mitigated — container user verified as appuser |
| THREAT-012 added | ZAP scan revealed Grafana and Loki exposed on public ports |
| THREAT-013 updated | Confirmed mitigated — bucket policy removed, Block All Public Access enabled |
| THREAT-016 added | pip-audit finding: Flask CVE-2026-27205 |
| THREAT-017 added | ZAP baseline scan identified 8 missing security header findings |
| Data flow diagram updated | Reflects direct browser-to-S3 upload architecture |
| Trust boundaries updated | New boundary: browser to S3 direct upload |
