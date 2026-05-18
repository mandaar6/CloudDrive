# OE Dashboard: Operational Questions and Remaining Gaps

**Version:** 2.0
**Date:** May 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document defines the operational questions the CloudDrive OE dashboard is designed to answer and the gaps that remain. The dashboard is directly connected to the running CloudDrive product through Loki. Promtail collects logs from all Docker containers in real time, ships them to Loki, and Grafana queries Loki using LogQL every 30 seconds. Every number and graph reflects actual events from the Flask backend, not hardcoded or simulated data.

This sprint added six new structured log events to Flask: `upload_url_requested`, `confirm_upload_received`, `email_send_success`, `email_send_failure`, `s3_error`, and `request_completed` with method, path, status code, and duration in milliseconds on every request. These new events power the most important new panels added this sprint.

---

## 2. Operational Questions the Dashboard Can Answer

### Section 1: System Health

**Is the application currently responding to requests?**
The Total API Requests stat panel and System Activity Over Time graph answer this. During testing, the request count hit 41 in 5 minutes and 134 during a heavier session. A drop to zero while Grafana itself is still reachable means the application has stopped responding. This is the single most important availability signal.

**How fast is the login endpoint responding?**
The Login Response Time gauge answers this. During testing it consistently showed 716ms to 737ms, which is expected for bcrypt password hashing. If this climbs above 1200ms, the database or another dependency is degraded. The gauge turns yellow at 700ms and red at 1200ms.

**How fast is the application overall?**
The Avg Response Time gauge answers this. During testing this showed 210ms average across all endpoints. Endpoints like logout and file listing are fast (under 30ms) while login is slow by design, so the average gives a good middle picture.

**Are there any errors right now?**
The Error Rate stat panel turns red the moment any ERROR level log appears. During all testing sessions this showed green (No data), confirming healthy operation.

**What does overall traffic look like over time?**
The System Activity Over Time graph shows total requests, successful 2xx responses, and 4xx/5xx errors as three separate lines. This makes it easy to see whether a rise in total traffic brings a proportional rise in errors.

---

### Section 2: User and File Activity

**How many users logged in successfully and how many failed?**
Login Success (green stat) and Login Failures (yellow stat with threshold coloring) answer this. During testing, 7 failures correctly turned the panel yellow. Both panels include sparklines showing recent trends.

**Is there a brute force attack in progress?**
The Login Failures stat and Login Activity Over Time graph answer this together. The stat panel turns yellow at 3 failures and red at 10 failures. The graph shows the pattern over time, distinguishing a single forgotten password from a sustained attack that keeps the failure line elevated.

**Are file uploads completing successfully end to end?**
The Upload Funnel Over Time graph answers this. It tracks three sequential events: upload_url_requested, confirm_upload_received, and upload_success. During testing all three lines tracked together, confirming the full upload flow was healthy. A gap between the first line and the second means uploads are starting but the browser-to-S3 step is failing without Flask knowing about it. This is the primary monitoring panel for RISK-001 (silent upload failure).

**How many upload attempts happened vs completions?**
The Upload URL Requests stat (purple) and File Uploads stat (blue) answer this. During testing both showed 4, confirming all attempts completed. Upload URL Requests counts how many users started an upload. File Uploads counts how many confirmed completions reached the database.

**Are new registrations converting to verified accounts?**
The Registrations vs Verifications graph answers this. A rising registration line with a flat verification line means verification emails are not reaching users.

**Is email delivery working?**
The Email Success vs Failure graph answers this directly. Flask now emits email_send_success and email_send_failure events immediately when SMTP attempts succeed or fail, so this panel reflects real sending outcomes rather than just registration counts.

---

### Section 3: Alert Panels

**Has anything critical failed in the last hour?**
The four alert stat panels (Email Send Failures, S3 Errors, Database Fatal Errors, Login Failure Alert) answer this with a single glance. All green means nothing is broken. Any red panel requires immediate investigation. During all testing sessions these panels stayed green, confirming healthy operation.

**Is the rate limiter working?**
The Login Failure Alert panel uses a 10-minute window and turns yellow at 5 failures and red at 15. This shorter window catches active attacks faster than the hourly counter.

---

### Section 4: Live Logs

**What exactly happened in the last few minutes?**
The Backend Application Logs stream shows the complete raw output from Flask including every `request_completed` event with method, path, status, and duration_ms. This is the ground truth during any incident investigation.

**What auth and file events happened recently?**
The Auth and File Events panel filters the full log stream to show only lines containing login, upload, email, or s3_error keywords. This is faster to scan during an incident than the full log.

**Is PostgreSQL healthy?**
The Database Container Logs panel shows raw PostgreSQL logs. Normal operation shows checkpoint entries. A FATAL entry here means the database has crashed.

---

## 3. Remaining Gaps

### GAP-001: Loki Overload Under High Query Load

The most significant operational gap discovered this sprint is that Grafana returns `Status: 500 — too many outstanding requests` from Loki during periods of high dashboard activity. This happens when many panels query Loki simultaneously and Loki's query concurrency limit is reached.

The dashboard has 21 panels all refreshing every 30 seconds. When a refresh cycle starts, all 21 LogQL queries fire at roughly the same time. Loki's default `max_outstanding_per_tenant` limit is 100 concurrent queries, but with 21 queries per 30-second cycle and some queries taking several seconds to resolve (particularly the regexp extraction queries for response time), the limit can be hit.

The practical effect is that some panels show No data for one refresh cycle and then recover on the next. This makes the dashboard look unreliable even when the underlying application is healthy.

**What is needed to fix this:**
Stagger panel refresh intervals so not all panels query at the same second. Increase Loki's `max_outstanding_per_tenant` limit in the Loki configuration. Simplify the more expensive LogQL queries (particularly the unwrap queries for response time extraction) to reduce per-query execution time. Move response time logging to Prometheus metrics rather than log-based extraction, which is significantly more efficient for numeric aggregation.

---

### GAP-002: S3 Download Outcome Not Visible

Flask logs `download_success` when it generates a presigned URL. This means Flask considers its job done. But the actual file transfer happens directly between the user's browser and S3. If S3 rejects the presigned URL (due to an IAM policy change or bucket configuration problem), the user gets an Access Denied error in their browser and Flask never finds out. The S3 Errors alert panel only catches errors during presigned URL generation inside Flask, not rejections that happen at the S3 level afterward.

**What is needed:** Client-side reporting where the React frontend calls a Flask endpoint after the S3 download completes, reporting success or failure. This gives the dashboard end-to-end visibility into whether users actually received their files.

---

### GAP-003: No Per-Endpoint Response Time Breakdown

The Login Response Time gauge correctly shows 716ms because bcrypt is intentionally slow. The average across all endpoints shows around 210ms. But there is no breakdown showing individual response times for the file list endpoint, upload URL endpoint, or download endpoint. A slow database query affecting only one endpoint would be hidden behind these averages.

**What is needed:** Additional gauge or stat panels filtering `request_completed` events by specific path values. The data already exists in the logs.

---

### GAP-004: No Container Resource Usage

The dashboard has no visibility into CPU or memory usage per container. A memory leak in Flask or an unusually heavy database query would not be visible until the container is OOM killed.

**What is needed:** Add cAdvisor as a Docker container and configure Grafana with a Prometheus data source alongside the existing Loki data source.

---

### GAP-005: Upload Outcome Not Fully Verified

The Upload Funnel shows that confirm_upload_received was called after the S3 step, but it cannot distinguish between a genuine successful S3 upload and a case where the browser called confirm_upload despite the S3 upload failing. A frontend bug could produce false positives in the funnel.

**What is needed:** Explicit S3 outcome reporting from the browser before calling confirm_upload. Flask would then log `s3_upload_verified` only after the browser confirms S3 accepted the file.

---

## 4. AI Generation Notes

The question framework was generated with AI assistance. The following were written or verified manually:

- The Loki overload issue in GAP-001 was observed directly during dashboard testing when the Status 500 error appeared on multiple panels simultaneously. The root cause was identified by looking at Loki's query concurrency behavior with 21 panels refreshing simultaneously.
- All response time values mentioned (716ms login, 210ms average) are from actual gauge readings observed in the dashboard screenshots captured during this sprint.
- The upload funnel behavior described in Section 2 was verified by watching all three lines track together during a live upload session.
