# OE Dashboard Gaps: Manual Tests and Missing Alert Metrics

**Version:** 2.0
**Date:** May 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document covers two types of gaps in the current CloudDrive operational monitoring setup:

**Manual tests** that verify important behaviors but cannot currently run automatically in the CI/CD pipeline, along with the reason why automation is not yet possible.

**Missing alert metrics** that should exist in the Grafana OE dashboard but are not implemented yet, along with what would be needed to add them.

Both categories represent monitoring debt. The goal of documenting them here is to make the gaps explicit rather than discovering them during an actual incident at 3am.

---

## 2. Manual Tests That Cannot Be Automated

---

### MANUAL-001: End-to-End File Upload to Real S3

**What it tests:** That a real file actually lands in AWS S3 after a user completes the upload flow in the browser.

**Why it cannot be automated:** The automated pytest tests run against an in-memory SQLite database with fake AWS credentials set to placeholder values like `test`. They verify that the Flask API returns the correct HTTP responses (200 for upload-url, 201 for confirm-upload) but they never actually contact AWS S3. Testing a real S3 upload in CI/CD would require real AWS credentials in GitHub Actions, which is a security risk, and would make tests dependent on AWS being available and correctly configured, which breaks the principle that tests should be fast, isolated, and deterministic.

**How to run manually:**
1. Start the full Docker Compose stack with real AWS credentials in .env
2. Log in to CloudDrive at http://localhost
3. Upload a small test file (any file under 1MB)
4. Go to the AWS S3 console and verify the file appears under the uploads/ prefix
5. Confirm the S3 key format is correct: `uploads/{email}/{uuid}/{filename}`
6. Click Download in CloudDrive and confirm the file downloads correctly
7. Clean up by deleting the test file from both the application and the S3 bucket directly

**When to run:** After any change to the upload flow, the S3 IAM policy, the S3 CORS configuration, or the AWS credentials.

**Signs that something is wrong:** File appears confirmed in the CloudDrive dashboard but is absent from S3. Or the download button opens an S3 Access Denied page instead of downloading the file.

---

### MANUAL-002: Email Verification Flow with a Real Inbox

**What it tests:** That registration emails actually arrive in a real inbox and that the verification link works end to end.

**Why it cannot be automated:** The CI/CD environment uses `MAIL_SUPPRESS_SEND=1` which prevents any real emails from being sent. Testing real email delivery requires a live SMTP connection to an external mail server, which introduces a dependency on network connectivity, Gmail availability, and SMTP credentials being correctly configured. These are not properties of the application code itself and should not block a CI/CD pipeline. Even using a test inbox service like Mailtrap would add a third-party dependency that could fail independently of the application.

**How to run manually:**
1. Start the Docker Compose stack with real SMTP credentials in .env
2. Register a new account using a real email address you control
3. Verify the registration confirmation message appears on the page
4. Check the real inbox including spam folders
5. Note the time between registration and email receipt. More than 2 minutes suggests a problem
6. Click the verification link and confirm it leads to a success message
7. Log in with the verified account to confirm the full flow works

**When to run:** After any change to email configuration, SMTP credentials, or the verification token logic.

**Signs that something is wrong:** Email not received within 5 minutes. Link leads to an error page. Link appears to work but login still returns the unverified account error.

---

### MANUAL-003: S3 Presigned URL Expiry

**What it tests:** That download URLs actually stop working after 5 minutes and cannot be reused or forwarded indefinitely.

**Why it cannot be automated:** Testing real URL expiry requires waiting 5 minutes in real time. CI/CD pipelines should run in well under 5 minutes total. A 5-minute sleep inside a test would make the entire pipeline too slow to be useful during code review. Mocking the expiry in tests would not verify the actual S3 behavior.

**How to run manually:**
1. Log in to CloudDrive and upload a file
2. Click Download and immediately copy the full presigned URL from the browser address bar before the download begins
3. Wait 6 minutes
4. Open the copied URL in a new incognito browser window
5. Confirm it returns an S3 error page with a message about the request having expired

**When to run:** After any change to the S3_PRESIGNED_EXPIRY configuration value or the presigned URL generation code.

**Signs that something is wrong:** The URL still works after 6 minutes, meaning the expiry is not being enforced. This is a security issue where forwarded URLs remain valid indefinitely.

---

### MANUAL-004: Database Recovery After Container Restart

**What it tests:** That user data, files, and shares all persist correctly after the database container is stopped and restarted, and that the application reconnects automatically.

**Why it cannot be automated:** This test requires running a full Docker Compose stack, stopping individual containers, and restarting them. The GitHub Actions CI/CD environment runs unit tests against a single in-memory process and does not have Docker Compose orchestration available.

**How to run manually:**
1. Create a test account, upload 2 files, and share one of them with another account
2. Run `sudo docker compose stop db`
3. Try to use the application. Verify it returns appropriate error responses rather than crashing silently
4. Run `sudo docker compose start db` and wait 10 seconds for PostgreSQL to initialize
5. Log back in and verify all data is intact: both files visible, share still active

**When to run:** After any change to the docker-compose.yml database configuration, after any schema migration, or after the host machine has been forcefully rebooted.

**Signs that something is wrong:** Data missing after restart. Application does not reconnect automatically after the database comes back. Schema errors indicating a migration was applied incorrectly.

---

### MANUAL-005: CORS Configuration Verification

**What it tests:** That the S3 CORS configuration allows the browser to upload files directly to S3 from the application's origin.

**Why it cannot be automated:** CORS enforcement happens at the AWS S3 level, not in the Flask application. The automated tests mock the S3 client and never send a real cross-origin request to S3. Verifying CORS requires a real browser making a real cross-origin request to a real S3 bucket, which cannot be done in a headless CI environment without significant browser automation infrastructure.

**How to run manually:**
1. Start the application and open browser DevTools on the Network tab
2. Attempt to upload a file
3. Look at the OPTIONS preflight request to the S3 URL. Verify it returns 200 with the correct Access-Control-Allow-Origin header
4. Verify the subsequent POST to S3 completes with HTTP 204

**Signs that something is wrong:** OPTIONS request returns an error. POST to S3 fails with a CORS error in the browser console. Upload appears to start but never completes.

**When to run:** After any change to the S3 bucket CORS configuration in the AWS console. This configuration is not version-controlled, which is itself a gap documented in the unknown unknowns document.

---

### MANUAL-006: Grafana Dashboard Data Accuracy

**What it tests:** That the Grafana OE dashboard correctly reflects real activity happening in the application.

**Why it cannot be automated:** Grafana is a visualization layer on top of Loki. There is no automated test that queries Grafana panels and verifies their values match expected numbers. Automating this would require either a Grafana API integration or a visual regression testing framework, neither of which is currently in the test infrastructure.

**How to run manually:**
1. Perform a known set of actions: log in twice, upload 2 files, attempt 1 failed login
2. Open Grafana at http://localhost:3000 and look at the dashboard
3. Verify the Login Success counter shows 2
4. Verify the File Uploads counter shows 2
5. Verify the Login Failures counter shows 1 and has turned yellow
6. Verify upload_success events appear in the Backend Logs panel at the correct timestamps
7. Verify the Upload Completions Over Time graph shows a spike at the time of the uploads

**When to run:** After any change to the Grafana dashboard JSON, after any change to the Flask logging format, or after a Grafana or Loki version upgrade.

---

## 3. Alert Metrics Not Yet in the OE Dashboard

---

### ALERT-GAP-001: Upload Abandonment Rate

**What it should alert on:** When more than 20% of upload attempts do not result in a completed upload within 60 seconds. This is the primary early warning indicator for RISK-001 (silent upload failure).

**Why it is not in the dashboard yet:** The current dashboard counts upload_success events, but detecting an incomplete upload requires tracking two events together: the upload-url request (which starts the upload attempt) and the upload_success event (which confirms completion). Loki can filter log lines but correlating pairs of events across a time window requires either a custom application metric or client-side telemetry that reports back to the server after the S3 step. Neither of these is implemented yet.

**What is needed to implement it:** Add a client-side reporting endpoint in Flask that the React frontend calls after every S3 upload attempt, whether it succeeds or fails. This gives the backend visibility into the outcome of the direct browser-to-S3 transfer, which it currently has no way to observe.

---

### ALERT-GAP-002: S3 GetObject Error Rate

**What it should alert on:** When users are getting Access Denied or other errors when trying to download files from S3. This is the early warning for RISK-003 (file downloads returning errors).

**Why it is not in the dashboard yet:** Flask generates presigned URLs and logs download_success, but the actual file transfer happens directly between the user's browser and S3. If S3 rejects the request, that error goes to the browser and never reaches Flask. The current S3 Errors panel in Grafana catches errors during presigned URL generation, but not errors that happen after the URL is generated.

**What is needed to implement it:** Either add client-side reporting (the browser tells Flask whether the S3 download succeeded) or integrate AWS CloudWatch to monitor S3 GetObject error rates at the AWS layer. CloudWatch would provide the most reliable signal since it captures what actually happens at S3 regardless of application code.

---

### ALERT-GAP-003: Email Send Success Confirmation

**What it should alert on:** When the ratio of registrations to successfully sent verification emails drops below 100% for any reason.

**Why it is not in the dashboard yet:** The application logs email failures when the SMTP call raises an exception, but does not currently log a separate email_send_success event when an email is sent successfully. The Registrations vs Email Verifications panel currently uses "Email verified" events as a proxy, but this only appears when a user clicks the link, not when the email was actually sent. These are different events separated by time.

**What is needed to implement it:** Add a structured log event immediately after a successful SMTP send: `logger.info("email_send_success type=verification")`. Then add a Grafana panel that alerts when this event count drops to zero during a period when registrations are occurring.

---

### ALERT-GAP-004: Response Time Tracking

**What it should alert on:** When the average response time for key endpoints (login, file list, upload-url) exceeds a threshold like 2 seconds, indicating the system is under load or a dependency is slow.

**Why it is not in the dashboard yet:** Flask does not currently measure or log response times. Gunicorn access logs include response time but in a format that is difficult for Loki to parse and aggregate. There is no middleware in the current codebase that records per-request timing.

**What is needed to implement it:** Add a Flask after_request hook that logs the response time for every request as a structured field. Then add a Grafana panel that computes average and 95th percentile response times from these log entries. Alert when the 95th percentile exceeds 2000ms for the login or upload-url endpoint.

---

### ALERT-GAP-005: Container Restart Detection

**What it should alert on:** When any application container restarts unexpectedly, since Docker's restart policy automatically recovers crashed containers but the crash itself indicates something went wrong.

**Why it is not in the dashboard yet:** Docker restart events are not captured in the application logs that Promtail collects. They appear in the Docker daemon's own event stream which requires a different collection mechanism. The current Promtail setup scrapes container stdout and stderr but not Docker system events.

**What is needed to implement it:** Add cAdvisor as a sidecar container in docker-compose.yml. cAdvisor exposes container metrics including restart count as Prometheus metrics. Configure Grafana to scrape the cAdvisor endpoint and alert when any container's restart count increases.

---

### ALERT-GAP-006: New User Onboarding Funnel Completion Rate

**What it should alert on:** When the percentage of registered users who complete email verification drops below 50% over a rolling 24-hour window, indicating that verification emails are not reaching users.

**Why it is not in the dashboard yet:** Computing this ratio requires correlating data from two different sources: the number of registrations (available from Loki logs) and the number of verified accounts (only available from the PostgreSQL users table). The current Grafana setup uses Loki as its only data source. Adding a PostgreSQL data source to Grafana would enable dashboard panels that query the database directly.

**What is needed to implement it:** Add a PostgreSQL data source to Grafana pointing to the clouddrive database. Then create a panel using the query: `SELECT COUNT(*) as verified FROM users WHERE is_verified = true` compared against `SELECT COUNT(*) as total FROM users`. Alert when the ratio drops below 50% over the last 24 hours.

---

## 4. Priority Order for Closing These Gaps

| Priority | Gap | Effort estimate | Risk addressed |
| :--- | :--- | :--- | :--- |
| 1 | Client-side upload outcome reporting | 1 day | RISK-001, ALERT-GAP-001 |
| 2 | email_send_success structured logging | 30 minutes | RISK-004, ALERT-GAP-003 |
| 3 | Response time middleware | 2 hours | All risks, ALERT-GAP-004 |
| 4 | PostgreSQL data source in Grafana | 1 hour | RISK-004, ALERT-GAP-006 |
| 5 | cAdvisor container restart detection | 2 hours | RISK-005, ALERT-GAP-005 |
| 6 | CloudWatch S3 error rate integration | Half day | RISK-003, ALERT-GAP-002 |
| 7 | Browser testing infrastructure (Playwright) | 2 days | MANUAL-003, MANUAL-005 |
