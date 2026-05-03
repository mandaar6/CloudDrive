# Unknown Unknowns: Potential Risks Not Yet Modeled

**Version:** 1.0
**Date:** April 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document identifies potential risks to CloudDrive that are not currently captured in the threat model. These are risks that exist in areas where visibility is limited, where assumptions are made without verification, or where the threat landscape is evolving faster than the threat model. The term "unknown unknowns" refers to risks that you do not know you do not know — gaps in awareness rather than gaps in implementation.

The goal of this document is to make those gaps explicit so they can be monitored, prioritized, and eventually incorporated into the threat model as known risks.

---

## 2. Supply Chain and Upstream Dependency Risks

### 2.1 PyPI Package Tampering

CloudDrive installs Python packages from PyPI via pip. PyPI is a public registry that has historically been targeted by attackers who publish malicious packages with names similar to popular legitimate packages (typosquatting). When `pip install` runs during a Docker build, it fetches packages from PyPI at that moment.

**What is unknown:** Whether any of the 35+ packages in requirements.txt has been replaced by a malicious version at the registry level between when the version was first pinned and the next Docker build. PyPI does not guarantee immutability — a package maintainer's account can be compromised and a malicious version published under the same version number in some edge cases.

**Why it matters for CloudDrive:** The Docker build process runs `pip install -r requirements.txt` on every `docker compose up --build`. If a dependency is compromised at PyPI between builds, the malicious code runs inside the backend container with access to AWS credentials, the database, and all user data.

**Monitoring approach:** Add `pip-audit` to the CI/CD pipeline so every build scans for known vulnerabilities. Consider pinning packages by hash digest in requirements.txt using `pip-compile --generate-hashes` so the exact bytes of each package are verified at install time.

---

### 2.2 boto3 and AWS SDK Silent Behavior Changes

The application relies on boto3 for all AWS interactions: S3 presigned URL generation, S3 object operations, and Secrets Manager fetches. boto3 is maintained by AWS and receives frequent updates. The version pinned in requirements.txt (1.34.84) will eventually drift significantly behind the current release.

**What is unknown:** Whether a future boto3 update changes the behavior of `generate_presigned_post()` in a way that silently weakens the security of uploaded URLs. For example, a change to default conditions or signature algorithms could produce presigned URLs that are easier to forge or that bypass the content-length-range enforcement.

**Why it matters:** The entire direct S3 upload security model depends on presigned POST URL correctness. A silent boto3 behavior change that relaxes the conditions would allow users to upload files of unrestricted type or size without CloudDrive being aware.

**Monitoring approach:** Pin boto3 to a specific version and review the boto3 changelog before upgrading. Add an integration test that verifies the presigned POST URL rejects uploads exceeding the content-length-range condition.

---

### 2.3 Gunicorn Worker Process Vulnerabilities

Gunicorn spawns 4 worker processes. The current version (21.2.0) has known HTTP Request Smuggling vulnerabilities. Beyond the known CVEs, Gunicorn's worker management has historically had edge cases around slow client connections (slowloris-style attacks) that can exhaust the worker pool.

**What is unknown:** Whether the combination of nginx in front of Gunicorn provides sufficient protection against the specific Transfer-Encoding smuggling technique in CVE-2024-1135. The CVE description notes that users with a "network path which does not filter out invalid requests" are vulnerable — it is not fully tested whether nginx filters these specific malformed headers before they reach Gunicorn.

**Monitoring approach:** Test nginx's Transfer-Encoding handling explicitly. Upgrade to gunicorn 22.0.0 in the next sprint.

---

### 2.4 Grafana and Loki Upstream Vulnerabilities

The application depends on grafana/grafana:10.2.0 and grafana/loki:2.9.0 as Docker images pulled from Docker Hub. These images contain their own dependencies and have their own CVE surface. Trivy scans the backend image but does not scan the Grafana or Loki images.

**What is unknown:** The CVE state of the Grafana and Loki images. Grafana has had multiple critical authentication bypass vulnerabilities historically. If Grafana has an unpatched authentication bypass, an attacker on the same network can access the OE dashboard and read all application logs — including user emails, file names, and activity patterns.

**Monitoring approach:** Run Trivy against the Grafana and Loki images: `sudo trivy image grafana/grafana:10.2.0`. Add these to the CI/CD pipeline scan. Grafana is currently exposed on port 3000 publicly — restrict this to localhost only in production.

---

## 3. Environmental and Infrastructure Assumptions

### 3.1 Docker Volume Data Persistence

The application assumes that Docker named volumes (`postgres_data`, `grafana_data`) persist between container restarts. The entire user database — accounts, file metadata, shares, revoked tokens — lives in the `postgres_data` volume on the host filesystem.

**What is unknown:** The data protection state of the host filesystem. If the Kali Linux machine's disk fails, is encrypted (and the key is lost), or if someone runs `docker volume prune` without understanding what it does, all user data is permanently lost with no backup.

**Why it matters:** There is no backup strategy for the PostgreSQL volume. There is no disaster recovery procedure. A single hardware failure or accidental command destroys all data irreversibly.

**Monitoring approach:** For production: use AWS RDS instead of a containerized PostgreSQL so AWS handles backups and multi-AZ replication. For the current dev environment: document that the postgres_data volume is the only copy of all data and never run `docker compose down -v` without explicit intent to wipe data.

---

### 3.2 AWS Secrets Manager Availability as a Single Point of Failure

The application fetches JWT_SECRET_KEY and POSTGRES_PASSWORD from AWS Secrets Manager at startup. If Secrets Manager is unavailable (AWS outage, network partition, IAM permission change), the application falls back to .env values.

**What is unknown:** What happens to in-flight requests during a Secrets Manager fetch failure. More importantly — if the fallback .env value differs from the Secrets Manager value (for example, after a key rotation in Secrets Manager that was not applied to .env), all existing JWT tokens become invalid and every logged-in user is silently logged out on the next request.

**Why it matters:** A Secrets Manager key rotation that is not synchronized with the .env fallback creates a silent mass logout event. Users experience "Token has been revoked" errors with no explanation. The on-call engineer would see a spike in JWT rejection errors in Grafana but the cause (key mismatch, not an attack) would not be immediately obvious.

**Monitoring approach:** Add a startup log entry indicating whether the Secrets Manager fetch succeeded or fell back to .env. Alert in Grafana if the Secrets Manager fallback log message appears — this indicates AWS connectivity issues or a key mismatch.

---

### 3.3 S3 CORS Configuration as an Undocumented Dependency

The direct browser-to-S3 upload flow requires a specific CORS configuration on the S3 bucket allowing `http://localhost` as an origin. This configuration exists in the AWS console but is not version-controlled anywhere in the repository.

**What is unknown:** Whether the CORS configuration survives an AWS account audit, security review, or policy enforcement that removes permissive CORS settings. If the CORS configuration is removed (by an automated policy tool or a team member), all file uploads silently fail — the browser receives a CORS error and users see "upload failed" with no server-side log entry because the request never reaches Flask.

**Why it matters:** The failure is invisible to the OE dashboard because it happens between the browser and S3, completely bypassing the backend. Grafana shows no errors, the file list endpoint works fine, and only a browser console inspection reveals the CORS block.

**Monitoring approach:** Add a health check endpoint that verifies the S3 CORS configuration is intact by calling `s3_client.get_bucket_cors()` and checking that `AllowedOrigins` includes the expected origin. Store the required CORS configuration as a JSON file in the repository so it can be reapplied if removed.

---

## 4. Operational and Human Factor Risks

### 4.1 Developer Accidentally Commits .env File

The .env file is listed in .gitignore and has never appeared in git history. However, .gitignore only prevents accidentally staging the file — it does not prevent a developer from explicitly forcing it with `git add -f .env` or from creating a differently-named file with the same contents (for example, `.env.local`, `config.env`, or `secrets.yaml`) that is not listed in .gitignore.

**What is unknown:** Whether all future developers who contribute to the repository understand the sensitivity of the .env file and the .gitignore convention. A single `git add -f .env && git push` to a public repository exposes all AWS credentials, the JWT secret, and database credentials simultaneously. Automated credential scanners on GitHub would detect and alert on some credential formats (AWS keys), but not on all values (the JWT secret, for example, has no recognizable format).

**Monitoring approach:** Add a pre-commit hook using `detect-secrets` or `gitleaks` that scans every commit for high-entropy strings and known secret formats before the commit is accepted. This runs locally and catches the mistake before it reaches GitHub.

---

### 4.2 Email SMTP Credentials as an Unmonitored Secret

The application uses Gmail SMTP credentials (`MAIL_USERNAME`, `MAIL_PASSWORD`) stored in .env to send verification and password reset emails. These credentials are not stored in AWS Secrets Manager — only the JWT secret and database password are. The Gmail App Password is not covered by any automated rotation or audit.

**What is unknown:** Whether the Gmail account used as the mail sender has 2-factor authentication enforced, what happens if the App Password is revoked by Google's security system (for example, if Google detects unusual sending patterns and revokes the App Password automatically), and whether anyone can tell when this happens.

**Why it matters:** If the Gmail App Password is revoked, all email sending silently fails. Users who register cannot verify their accounts. Users who forget their passwords cannot reset them. The application continues to accept registration attempts, returning a success response, while the verification email is never delivered. The on-call engineer sees no error in Grafana because the email failure may or may not be logged depending on the exception path.

**Monitoring approach:** Add a structured log event for every email send attempt — success and failure — that is queryable in Grafana. Add an alert that fires if zero verification emails were sent in a 24-hour period when user registrations occurred.

---

### 4.3 The Security of the Developer Machine

The entire security model of CloudDrive in its current local deployment rests on the security of the Kali Linux machine where it runs. The .env file, the PostgreSQL data volume, the Docker socket, and the AWS credentials all exist on this machine. If the machine is compromised, all of these are immediately accessible to an attacker.

**What is unknown:** The security posture of the Kali Linux machine itself. Does it have automatic security updates enabled? Is the disk encrypted? Is the screen locked when unattended? Is the machine exposed to the internet on any port (for example, via SSH)?

**Why it matters:** CloudDrive's application-level security controls (JWT, bcrypt, least-privilege IAM) are irrelevant if an attacker has filesystem access to the machine running it. This is a risk that exists outside the application's threat model but directly affects the data CloudDrive stores.

**Monitoring approach:** This risk is mitigated by moving to a production EC2 deployment with IAM instance roles (no credentials on disk), RDS (database off the application server), and proper OS hardening. For the current development environment, it is an accepted risk that is documented here.

---

## 5. Future Threat Landscape Risks

### 5.1 JWT Algorithm Confusion Attacks

The application uses PyJWT to sign and verify tokens with HMAC-SHA256 (HS256). A known class of JWT attacks called "algorithm confusion" involves sending a token that specifies a different algorithm (such as `none` or `RS256`) in the header, causing some JWT libraries to verify the token incorrectly.

**What is unknown:** Whether the current PyJWT 2.12.0 implementation is fully protected against all algorithm confusion variants, and whether future changes to the JWT verification code could accidentally re-introduce this vulnerability.

**Monitoring approach:** Add a test that verifies the backend rejects tokens with `"alg": "none"` in the header. Verify that the JWT decode call explicitly specifies `algorithms=["HS256"]` in `auth.py`.

---

### 5.2 S3 Presigned URL Signature Algorithm Deprecation

AWS periodically deprecates older signature algorithms. CloudDrive uses Signature Version 4 (SigV4) for all S3 operations, which is the current standard. If AWS were to announce deprecation of SigV4 in favor of a newer scheme, all presigned URLs would stop working on the deprecation date.

**What is unknown:** AWS's timeline for any future signature algorithm changes, and whether boto3 would handle the transition automatically or require code changes.

**Monitoring approach:** Follow the AWS security bulletin RSS feed for S3 signature deprecation notices. Subscribe to boto3 release notes.

---

## 6. Summary of Unknown Unknowns by Priority

| Risk | Area | Priority | Detection Method |
| :--- | :--- | :--- | :--- |
| PyPI package tampering | Supply chain | High | pip hash pinning, pip-audit in CI |
| Grafana/Loki unscanned images | Supply chain | High | Add to Trivy scan in CI |
| S3 CORS config removed silently | Infrastructure | High | Health check endpoint for CORS |
| Developer commits .env | Human factor | High | pre-commit hook with detect-secrets |
| PostgreSQL volume with no backup | Infrastructure | High | Migrate to RDS in production |
| Secrets Manager key mismatch on rotation | Infrastructure | Medium | Startup log entry, Grafana alert |
| Gmail App Password revoked silently | Human factor | Medium | Email send/fail structured logging |
| boto3 behavior change in presigned URLs | Supply chain | Medium | Integration test for URL conditions |
| JWT algorithm confusion attack | Application | Medium | Test for alg:none rejection |
| Gunicorn vs nginx Transfer-Encoding | Infrastructure | Medium | Upgrade to gunicorn 22.0.0 |
| Developer machine compromise | Human factor | Low (dev only) | Mitigated by EC2 deployment |
| S3 signature algorithm deprecation | Infrastructure | Low | Monitor AWS bulletins |
