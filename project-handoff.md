# CloudDrive Project Handoff — Complete Context

## Project Overview

This is a 10-week course project for a class called Incident Response and Risk Management. The student's name is Mandaar Rao (GitHub: mandaar6/CloudDrive). The project is called **CloudDrive** — a secure cloud file storage and sharing web application similar to Dropbox. It is built as a learning platform for cloud security, DevSecOps, and operational excellence.

The project runs entirely on a **Kali Linux virtual machine**. All development uses **Claude Code** running in the terminal. The project is at `/home/kali/CloudDrive/` on the Kali machine.

---

## Repository Structure

```
/home/kali/CloudDrive/
├── .github/
│   └── workflows/
│       └── ci.yml                    ← GitHub Actions CI/CD pipeline
├── clouddrive/                       ← Main application (Docker Compose project)
│   ├── docker-compose.yml
│   ├── .env                          ← Real secrets (gitignored)
│   ├── .env.example                  ← Template with placeholders
│   ├── .gitignore                    ← Includes .env
│   ├── backend/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── app/
│   │       ├── __init__.py
│   │       ├── auth.py
│   │       ├── files.py
│   │       ├── models.py
│   │       └── config.py
│   ├── frontend/
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   ├── vite.config.js
│   │   ├── index.html
│   │   └── src/
│   │       ├── App.jsx
│   │       ├── Dashboard.jsx
│   │       ├── Login.jsx
│   │       ├── Register.jsx
│   │       ├── ShareModal.jsx
│   │       ├── ResetPassword.jsx
│   │       └── main.jsx
│   ├── nginx/
│   │   └── nginx.conf
│   └── dashboard/
│       ├── grafana-datasource.yml
│       ├── grafana-dashboard-provider.yml
│       ├── promtail-config.yml
│       └── dashboards/
│           └── clouddrive.json       ← Grafana dashboard (21 panels)
├── README.md
├── technical-design.md
├── threat-model.md                   ← v1.0 (original with intentional vulns)
├── threat-model-v2.md                ← v2.0 (updated, hardened)
├── security-testing.md               ← v1.0
├── security-testing-v2.md            ← v2.0 (with real Trivy/Semgrep/ZAP output)
├── security-runbook.md
├── unknown-unknowns.md
├── gaps-analysis.md
├── oe-questions.md
├── oe-metrics.md
├── oe-oncall.md
├── cicd-gaps.md
├── operational-risks.md
├── oe-gaps.md
├── oe-dashboard-questions.md
└── oe-dashboard-comparison.md
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python / Flask with Gunicorn (4 workers) |
| Frontend | React (Vite) |
| Database | PostgreSQL 15 |
| File Storage | AWS S3 (direct browser upload via presigned POST URLs) |
| Email | Gmail SMTP via Flask-Mail |
| Secrets | AWS Secrets Manager (JWT secret + DB password), .env fallback |
| Reverse Proxy | Nginx |
| Monitoring | Grafana + Loki + Promtail |
| Orchestration | Docker Compose (7 containers) |
| CI/CD | GitHub Actions |
| Security scanning | Semgrep, Trivy, pip-audit, OWASP ZAP (manual) |

---

## The 7 Docker Containers

All run on a Docker bridge network called `internal`. Only Nginx (port 80), Grafana (port 3000), and Loki (port 3100) are exposed to the host.

1. **nginx** — reverse proxy, routes `/api/*` to Flask and `/*` to React frontend
2. **backend** — Flask app running under Gunicorn with 4 workers
3. **frontend** — React app served as static files
4. **db** — PostgreSQL, data persisted in named Docker volume `postgres_data`
5. **loki** — log storage and indexing
6. **promtail** — collects Docker container logs via Docker socket, ships to Loki
7. **grafana** — OE dashboard at localhost:3000

All containers have resource limits: `memory: 512m, cpus: "0.5"`.

---

## How to Run the Project

```bash
cd /home/kali/CloudDrive/clouddrive
sudo docker compose up --build -d
```

App is at `http://localhost`. Grafana at `http://localhost:3000`.

To stop without losing data:
```bash
sudo docker compose down
```

To wipe all data and restart fresh (destroys database):
```bash
sudo docker compose down -v
sudo docker compose up --build -d
```

---

## AWS Setup

**S3 Bucket:** `clouddrive-files-mxndi` (region: us-east-1)
- Block All Public Access: ON
- Encryption: SSE-S3 (AES-256 at rest)
- CORS configured to allow `http://localhost` as origin

**IAM User:** `clouddrive-app`
- Custom policy `CloudDriveAppPolicy` with only: `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on the specific bucket ARN, `s3:ListBucket` on the bucket, `secretsmanager:GetSecretValue` on the app secret

**AWS Secrets Manager:** Secret named `clouddrive/app/secrets` with keys:
- `JWT_SECRET_KEY`
- `POSTGRES_PASSWORD`

Flask fetches these at startup and falls back to `.env` if Secrets Manager is unavailable.

**AWS SES:** Configured but in sandbox mode. Gmail SMTP is used instead.

---

## Environment Variables (.env structure)

```
FLASK_SECRET_KEY=<random 32 char hex>
FLASK_ENV=production

POSTGRES_USER=clouddrive
POSTGRES_PASSWORD=<password>
POSTGRES_DB=clouddrive
DATABASE_URL=postgresql://clouddrive:<password>@db:5432/clouddrive

JWT_SECRET_KEY=<random 32 char hex>
JWT_EXPIRY_HOURS=24

AWS_ACCESS_KEY_ID=<key>
AWS_SECRET_ACCESS_KEY=<secret>
AWS_REGION=us-east-1
S3_BUCKET_NAME=clouddrive-files-mxndi

MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=<gmail address>
MAIL_PASSWORD=<16-char Gmail App Password>
MAIL_FROM=<gmail address>

GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<password>
```

---

## Database Schema (PostgreSQL)

```sql
users
  id SERIAL PK
  email VARCHAR(255) UNIQUE NOT NULL
  password_hash VARCHAR(255) NOT NULL
  created_at TIMESTAMP
  is_verified BOOLEAN DEFAULT FALSE
  verification_token VARCHAR(255)
  verification_token_expires TIMESTAMP
  username VARCHAR(255)

files
  id UUID PK (default uuid4)
  owner_id FK → users.id
  filename VARCHAR(255)
  s3_key VARCHAR(500)        -- format: uploads/{email}/{uuid}/{filename}
  size_bytes BIGINT
  content_type VARCHAR(255)
  uploaded_at TIMESTAMP
  is_deleted BOOLEAN DEFAULT FALSE
  deleted_at TIMESTAMP
  is_starred BOOLEAN DEFAULT FALSE
  folder_id UUID FK → folders.id (nullable)

file_shares
  id SERIAL PK
  file_id UUID FK → files.id
  shared_with_email VARCHAR(255)
  permission VARCHAR(10)     -- 'read' or 'edit'
  created_at TIMESTAMP
  expires_at TIMESTAMP

folders
  id UUID PK
  name VARCHAR(255)
  owner_id FK → users.id
  parent_id UUID FK → folders.id (self-referential, nullable)
  created_at TIMESTAMP

revoked_tokens
  jti VARCHAR(255) PK
  revoked_at TIMESTAMP
  expires_at TIMESTAMP

password_reset_tokens
  id UUID PK
  user_id FK → users.id
  token VARCHAR(255) UNIQUE
  created_at TIMESTAMP
  expires_at TIMESTAMP
  used BOOLEAN DEFAULT FALSE
```

---

## Key Flask API Endpoints

**Authentication:**
- `POST /api/auth/register` — email validation, bcrypt hash, send verification email
- `POST /api/auth/login` — rate limited 5/min, bcrypt check, JWT issued as HTTP-only cookie
- `POST /api/auth/logout` — adds JWT JTI to revoked_tokens table
- `GET /api/auth/verify-email?token=...` — verifies email
- `POST /api/auth/forgot-password` — generates reset token, sends email
- `POST /api/auth/reset-password` — validates token, updates password hash

**Files:**
- `GET /api/files/upload-url?filename=&content_type=` — generates S3 presigned POST URL, validates extension, logs upload_url_requested
- `POST /api/files/confirm-upload` — saves metadata after S3 upload, logs confirm_upload_received and upload_success
- `GET /api/files/` — list user files (owned + shared)
- `GET /api/files/trash` — list soft-deleted files
- `GET /api/files/<id>/download` — generates 5-minute presigned GET URL
- `GET /api/files/<id>/preview` — returns URL or text content based on file type
- `DELETE /api/files/<id>` — soft delete
- `POST /api/files/<id>/restore` — restore from trash
- `DELETE /api/files/<id>/permanent` — permanent delete from S3 and DB
- `PUT /api/files/<id>/star` — toggle is_starred
- `PUT /api/files/<id>/move` — move to folder
- `PUT /api/files/<id>/content` — re-upload (edit permission required)
- `POST /api/files/<id>/share` — share file

**Shares:**
- `GET /api/shares/outgoing` — files I shared
- `GET /api/shares/incoming` — files shared with me
- `DELETE /api/shares/<share_id>` — revoke a share

**Folders:**
- `GET /api/folders` — list folders
- `POST /api/folders` — create folder
- `DELETE /api/folders/<id>` — delete empty folder

---

## Security Controls Implemented

**Application layer:**
- bcrypt password hashing with automatic salting
- JWT tokens (HS256, 24h expiry) as HTTP-only cookies
- JWT revocation blocklist (RevokedToken table)
- Rate limiting: 5 login attempts per minute per IP (flask-limiter)
- File IDs as UUIDs (prevents IDOR guessing)
- Ownership validation on every file endpoint
- File extension allowlist: pdf, txt, doc, docx, png, jpg, jpeg, gif, mp4, mov, zip, csv, xlsx, pptx
- No file size limit (5GB max via S3 presigned POST conditions)
- Email verification required before login
- Forgot password returns identical response for registered and unknown emails

**Container layer:**
- Backend runs as non-root user (appuser, uid=100)
- All container capabilities dropped
- Resource limits on all containers

**Cloud layer:**
- S3 bucket: Block All Public Access ON
- IAM: least-privilege custom policy
- Credentials in .env (gitignored), Secrets Manager as primary source

**Known accepted CVEs (retained for CI/CD demonstration):**
```
# KNOWN: CVE-2024-1135, CVE-2024-6827 - fix: gunicorn==22.0.0
gunicorn==21.2.0
# KNOWN: CVE-2026-27205 - fix: flask==3.1.3
flask==3.0.3
# KNOWN: CVE-2026-28684 - fix: python-dotenv==1.2.2
python-dotenv==1.0.1
```

---

## Structured Log Events Emitted by Flask

Every request emits:
```
request_completed method=GET path=/api/files/ status=200 duration_ms=22
```

Authentication:
```
login_success user=email@example.com id=2
login_failure email=email@example.com
New user registered: email@example.com (id=3)
Email verified for user id=2
email_send_success type=verification
email_send_failure type=verification error=SMTPException
email_send_success type=password_reset
email_send_failure type=password_reset error=SMTPException
```

File operations:
```
upload_url_requested user=2 filename=report.pdf
confirm_upload_received user=2 filename=report.pdf
upload_success user=2 file=report.pdf id=<uuid>
download_success user=2 file_id=<uuid>
File soft-deleted by user 2: file_id=<uuid>
s3_error operation=generate_presigned_post error=ClientError
s3_error operation=get_object error=ClientError
s3_error operation=delete_object error=ClientError
```

---

## CI/CD Pipeline (GitHub Actions)

File: `.github/workflows/ci.yml`

Four jobs on every push:

1. **Run Tests** — installs from `clouddrive/backend/requirements.txt` + pytest, runs `clouddrive/backend/tests/`. Blocks merge on failure.
2. **Static Analysis (Semgrep)** — owasp-top-ten ruleset. Reports only.
3. **Dependency Scan (pip-audit)** — reports known CVEs. Does not block.
4. **Container Scan (Trivy)** — HIGH/CRITICAL. Does not block (known CVEs retained).

CI test environment variables:
```
TESTING=true, FLASK_ENV=testing, DATABASE_URL=sqlite:///:memory:
JWT_SECRET_KEY=test-secret-key-ci, SECRET_KEY=test-flask-secret-ci
POSTGRES_USER=test, POSTGRES_PASSWORD=test, POSTGRES_DB=test
AWS_ACCESS_KEY_ID=test, AWS_SECRET_ACCESS_KEY=test
AWS_REGION=us-east-1, S3_BUCKET_NAME=test-bucket
MAIL_SUPPRESS_SEND=1, MAIL_SERVER=localhost
RATELIMIT_STORAGE_URI=memory://
```

---

## Test Suite (26 tests, all passing)

Located at `clouddrive/backend/tests/`:

**conftest.py** — sets env vars before imports, in-memory SQLite, `_CookieHeaderClient` wrapper for Werkzeug 3.x cookie handling, `auth_client` fixture with verified user and JWT token injection.

**test_functional.py** — registration, login, duplicate email, unverified user rejection, unauthenticated endpoints, forgot password enumeration, edge cases.

**test_security.py** — rate limiting, IDOR prevention, JWT forgery rejection, file extension validation, email enumeration prevention, SQL injection handling, long input handling.

**test_operational.py** — upload-url returns required fields, confirm-upload saves metadata, file appears in list, verified user can login, wrong password returns 401 not 500.

Run tests locally:
```bash
cd /home/kali/CloudDrive/clouddrive/backend
export TESTING=true FLASK_ENV=testing DATABASE_URL=sqlite:///:memory: \
  JWT_SECRET_KEY=test SECRET_KEY=test POSTGRES_USER=test \
  POSTGRES_PASSWORD=test POSTGRES_DB=test AWS_ACCESS_KEY_ID=test \
  AWS_SECRET_ACCESS_KEY=test AWS_REGION=us-east-1 \
  S3_BUCKET_NAME=test-bucket MAIL_SUPPRESS_SEND=1 \
  MAIL_SERVER=localhost RATELIMIT_STORAGE_URI=memory://
python3 -m pytest tests/ -v --tb=short
```

---

## Grafana OE Dashboard

**Location:** `clouddrive/dashboard/dashboards/clouddrive.json`
**Loki datasource UID:** `P8E80F9AEF21F6940`
**Dashboard UID:** `clouddrive-oe`
**Refresh:** 5 minutes
**Time range:** Last 1 hour

**Four collapsible row sections, 21 panels total:**

**Row 1 — System Health:**
Total API Requests (stat), Avg Response Time gauge (0-2000ms), Login Response Time gauge, Active Session Check (stat), Error Rate (stat red at 1), System Activity Over Time (timeseries: total/2xx/errors)

**Row 2 — User and File Activity:**
Login Success (stat green), Login Failures (stat yellow/red), File Uploads (stat blue), Upload URL Requests (stat purple), Login Activity Over Time (timeseries), Upload Funnel Over Time (timeseries: url_requested/confirm_received/upload_success), Registrations vs Verifications (timeseries), Email Success vs Failure (timeseries)

**Row 3 — Alert Panels (green=healthy, red=any event):**
Email Send Failures, S3 Errors, Database Fatal Errors, Login Failure Alert (10m window)

**Row 4 — Live Logs:**
Backend Application Logs (full stream), Auth and File Events (filtered), Database Container Logs

**Important:** All count_over_time queries use `sum()` wrapper. Stat panels use `[1h]` range. Timeseries panels use `[2m]` range. Gauge panels use `[2m]` range. The 5-minute refresh prevents Loki chunk flush flickering. For presentations, turn off auto-refresh in Grafana and manually refresh once to freeze the display.

---

## Git Branch History

Each homework has its own branch with a PR submitted to the professor. PRs are never merged:
- `week-2-technical-design-doc` — technical design document
- `week-3-hw2` — dockerized product, threat model v1, security testing v1, gaps analysis
- `week-4-hw3` — OE dashboard Grafana setup, oe-questions, oe-metrics, oe-oncall
- `week-5-hw4` — security tests v2, automated pytest, GitHub Actions CI, runbook, unknown unknowns
- `week-6-hw5` — 26 passing tests, CI/CD gaps analysis
- `week-7-hw6` — operational risks, alert panels, operational tests, oe-gaps
- `week-8-hw7` — Flask structured logging, 21-panel Grafana redesign, dashboard questions and comparison docs

New branches follow the pattern: `git checkout main && git pull && git checkout -b week-N-hwN`

---

## Current State (End of Week 8 / HW7)

**Working:**
- Full multi-container Docker deployment (7 containers)
- User registration with email verification via Gmail SMTP
- JWT authentication with 24h expiry and server-side revocation blocklist
- Direct S3 upload (browser to S3, no backend bottleneck)
- File sharing with read/edit permissions
- Soft delete, trash, restore, permanent delete
- Rate limiting (5 attempts per minute per IP)
- Folders (backend endpoints exist, not wired in frontend)
- Star files (backend endpoint exists, not wired in frontend)
- 26 automated tests, all passing in GitHub Actions
- 21-panel live Grafana dashboard connected to real application logs
- Structured logging for all key business events with response timing

**Known gaps:**
- Star button and folder creation not wired in frontend UI
- Edit permission stored in DB but not fully enforced at API level
- No client-side S3 transfer telemetry (upload/download outcome blind spot)
- No HTTPS in local dev
- No EC2 deployment (running locally only)
- gunicorn 21.2.0 known CVEs retained intentionally
- Missing HTTP security headers in nginx (CSP, X-Frame-Options) — ZAP finding
- Email PII in some log messages — Semgrep finding, partially fixed

**Upcoming work (remaining weeks):**
- Incident simulation and walkthrough
- Compliance document
- Final presentation
- Potential EC2 deployment
- Fix remaining security header findings
- Enforce edit permission in frontend

---

## Critical Notes for the Next AI

1. **Always run Docker with sudo** on Kali: `sudo docker compose up --build -d`

2. **Never run `docker compose down -v`** unless intentionally wiping all data. The `-v` flag deletes the postgres_data volume permanently.

3. **The .env file** is at `/home/kali/CloudDrive/clouddrive/.env` and is gitignored. Never commit it or display its contents.

4. **Claude Code working directory** for backend/docker work: `/home/kali/CloudDrive/clouddrive/`. For git operations: `/home/kali/CloudDrive/`.

5. **GitHub repo:** `https://github.com/mandaar6/CloudDrive` (public)

6. **Grafana Loki datasource UID is `P8E80F9AEF21F6940`** — use this exact string in all dashboard JSON panel datasource references.

7. **Backend container name in Loki:** `clouddrive-backend-1`. Database container: `clouddrive-db-1`. Use these exact strings in LogQL queries.

8. **S3 files stored at** `uploads/{email}/{uuid}/{filename}` in the `clouddrive-files-mxndi` bucket.

9. **Professor submission pattern:** Each homework creates a new branch, commits all deliverables, pushes, and opens a PR on GitHub. The PR link is submitted as the homework. PRs are never merged.

10. **Document style:** All markdown files use easy human-like language, no em-dashes, written in third person where specified by the professor.
