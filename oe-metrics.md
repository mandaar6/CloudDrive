# Metrics Specification: What CloudDrive Must Emit

**Version:** 2.0
**Date:** April 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document specifies every metric and log event that CloudDrive must emit for the OE dashboard to function. The current implementation uses Loki as the log store, Promtail as the log collector, and Grafana as the visualization layer. Promtail scrapes Docker container logs using the Docker socket discovery method, automatically labeling each log line with the container name.

All metrics in the current implementation are derived from structured log lines emitted by the Flask backend to stdout. There is no separate metrics endpoint yet — this is a known gap documented in section 5.

---

## 2. Log Events Currently Emitted

The following log lines are confirmed present in the running application and queryable in Grafana via Loki.

### 2.1 Authentication Events

**Successful login**
```
INFO app.auth login_success user=email@example.com id=2
```
Loki query: `{container="clouddrive-backend-1"} |= "login_success"`
Dashboard use: Login Success stat counter, Login Activity graph, Auth Events stream

**Failed login**
```
WARNING app.auth login_failure email=email@example.com
```
Loki query: `{container="clouddrive-backend-1"} |= "login_failure"`
Dashboard use: Login Failures stat counter, Login Activity graph (separate line)

**New user registration**
```
INFO app.auth New user registered: email@example.com (id=3)
```
Loki query: `{container="clouddrive-backend-1"} |= "New user registered"`

**Verification email sent**
```
INFO app.auth Verification email sent to: email@example.com
```

**Email verified**
```
INFO app.auth Email verified for user id=2
```

**User logged out**
```
INFO app.auth User logged out: id=2
```

---

### 2.2 File Operation Events

**Upload confirmed**
```
INFO app.files upload_success user=2 file=report.pdf id=uuid
```
Loki query: `{container="clouddrive-backend-1"} |= "upload_success"`
Dashboard use: File Uploads stat counter, File Operations graph, File Events stream

**Download URL generated**
```
INFO app.files download_success user=2 file_id=uuid
```
Loki query: `{container="clouddrive-backend-1"} |= "download_success"`
Dashboard use: File Operations graph, File Events stream

**File soft deleted**
```
INFO app.files File soft-deleted by user 2: file_id=uuid
```
Loki query: `{container="clouddrive-backend-1"} |= "soft-deleted"`

---

### 2.3 Error Events

**General ERROR level logs**
```
ERROR app.auth [error message here]
ERROR app.files [error message here]
```
Loki query: `{container="clouddrive-backend-1"} |= "ERROR"`
Dashboard use: Error Logs stat counter (turns red at 1)

**SQLAlchemy warnings** (currently present, non-critical)
```
SAWarning: Coercing Subquery object into a select()
```
These appear as stderr logs in the backend container. They are visible in the Backend Logs panel and indicate a minor ORM query that should be fixed but does not affect functionality.

---

### 2.4 Infrastructure Events

**Gunicorn startup**
```
[INFO] Starting gunicorn 21.2.0
[INFO] Booting worker with pid: N
```

**Database ready**
```
database system is ready to accept connections
```
These come from the PostgreSQL container (`clouddrive-db-1`) and are visible in Loki under `{container="clouddrive-db-1"}`.

---

## 3. How Logs Flow to Grafana

```
Flask backend (stdout/stderr)
        ↓
Docker container log driver
        ↓
Promtail (Docker socket discovery)
Labels each log with:
  container = clouddrive-backend-1
  logstream = stdout OR stderr
        ↓
Loki (log storage and indexing)
        ↓
Grafana (queries Loki via LogQL)
        ↓
Dashboard panels render results
```

Promtail is configured with Docker socket service discovery (`docker_sd_configs`) which automatically discovers all running containers and scrapes their log streams. This means any new container added to docker-compose.yml is automatically scraped without any Promtail config changes.

---

## 4. LogQL Queries Used in the Current Dashboard

| Panel | Query | Type |
| :--- | :--- | :--- |
| Backend Logs | `{container="clouddrive-backend-1"}` | Log stream |
| Login Activity graph — successes | `sum(count_over_time({container="clouddrive-backend-1"} \|= "login_success" [5m]))` | Time series |
| Login Activity graph — failures | `sum(count_over_time({container="clouddrive-backend-1"} \|= "login_failure" [5m]))` | Time series |
| File Operations graph — uploads | `sum(count_over_time({container="clouddrive-backend-1"} \|= "upload_success" [5m]))` | Time series |
| File Operations graph — downloads | `sum(count_over_time({container="clouddrive-backend-1"} \|= "download_success" [5m]))` | Time series |
| Login Success counter | `count_over_time({container="clouddrive-backend-1"} \|= "login_success" [1h])` | Stat |
| Login Failures counter | `count_over_time({container="clouddrive-backend-1"} \|= "login_failure" [1h])` | Stat |
| File Uploads counter | `count_over_time({container="clouddrive-backend-1"} \|= "upload_success" [1h])` | Stat |
| Error counter | `count_over_time({container="clouddrive-backend-1"} \|= "ERROR" [1h])` | Stat |
| Auth Events stream | `{container="clouddrive-backend-1"} \|= "login"` | Log stream |
| File Events stream | `{container="clouddrive-backend-1"} \|~ "upload\|download\|delete"` | Log stream |

---

## 5. Metrics Not Yet Implemented (Known Gaps)

| Metric | What is needed | Priority |
| :--- | :--- | :--- |
| Rate limit triggers | Flask-limiter needs to log a structured event when 429 is returned | High |
| S3 errors | try/except around S3 calls needs to emit a structured `s3_error` log | High |
| Email send failures | Already partially logged but not consistently structured | Medium |
| Upload rejection count | Extension/size validation rejections not yet logged | Medium |
| Request latency | Need middleware to log response time per endpoint | Medium |
| Container resource usage | Requires cAdvisor sidecar container | Low |
| Database metrics | Requires pg_stat_statements or PostgreSQL exporter | Low |

Until these are implemented, the dashboard panels for these metrics will show no data. The on-call guide documents how to check raw logs manually for these gaps.

---

## 6. AI Generation Notes

The log format specifications were generated with AI assistance and then verified against the actual running application. The following were added or corrected manually:

- The SAWarning log entry in section 2.3 was added after observing it in the actual Loki stream — it was not predicted by AI and represents a real code quality issue in files.py that should be fixed
- The LogQL query table was written based on what is actually in the provisioned clouddrive.json dashboard file, verified against real Loki query results
- The gaps table in section 5 reflects actual missing instrumentation confirmed by checking the running backend code, not hypothetical gaps
