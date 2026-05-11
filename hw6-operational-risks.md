# Operational Risk Assessment: CloudDrive

**Version:** 2.0
**Date:** May 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document identifies the highest risks to customer use of CloudDrive from a business impact perspective. The focus here is not on attackers or security vulnerabilities but on failures that break the experience of real users and could cause them to stop using the product entirely.

CloudDrive's core promise is simple: users upload files and trust that those files are safe, accessible, and shareable. Any failure that breaks that promise is a high-priority operational risk, regardless of whether it is caused by a bug, a misconfiguration, a dependency failure, or an AWS outage.

---

## 2. Risk Scoring

Each risk is scored on two dimensions to produce a priority score.

**Customer impact (1 to 5):**
- 5: All users cannot use the product at all
- 4: The core feature is unavailable for all users
- 3: The core feature is down for some users, or a secondary feature is down for everyone
- 2: Degraded experience for some users
- 1: Minor inconvenience with a workaround available

**Detection difficulty (1 to 5):**
- 5: Completely invisible with no logs or errors. Users experience silent failure with no way to know why
- 4: Hard to detect. Requires knowing exactly what to look for
- 3: Detectable with monitoring in place
- 2: Obvious from logs or error rates
- 1: Immediately obvious. System visibly crashes

**Priority score = Customer impact multiplied by Detection difficulty**

---

## 3. Risk Inventory

---

### RISK-001: File Uploads Fail Silently

**Customer impact:** 5

File upload is the core feature of CloudDrive. If users cannot upload files, the product has no value. This is the most critical operational risk.

**Detection difficulty:** 4

The upload flow is split across two steps. The first step (getting the presigned URL) goes through Flask and is logged. The second step (the actual file upload to S3) happens directly between the user's browser and AWS S3, completely bypassing the backend. If the S3 upload fails, Flask never receives any error. Grafana shows no errors because Flask never saw the failure. The only way to detect this is by noticing that `upload_success` log events stop appearing even though users are logged in and active.

**Priority score:** 20 (Highest)

**How this fails in practice:**
- AWS S3 outage or degradation in us-east-1
- S3 CORS configuration removed or changed, causing the browser to block the cross-origin upload request
- IAM access key rotated without updating the application
- S3 bucket accidentally deleted or renamed
- Network partition between the user's ISP and AWS

**What the customer experiences:** The user selects a file and clicks upload. The progress indicator either never starts or freezes partway through. The file never appears in their dashboard. No error message is shown because the failure happened in the browser-to-S3 step with no server-side visibility. The user tries again, fails again, and concludes the product is broken.

**Current detection capability:** Partial. The Grafana dashboard shows upload_success events as they happen. If uploads stop but login activity continues, this is the signal. A dedicated panel showing upload completions over time was added as part of this sprint.

**Early alert target:** Alert when the upload_success count drops to zero during a period when login_success events are still occurring. This indicates users are active but uploads are failing.

**Automated test added:** TEST-OP-001 verifies the upload-url endpoint returns all required fields. TEST-OP-002 verifies confirm-upload saves metadata correctly. TEST-OP-003 verifies the file appears in the file list after upload.

---

### RISK-002: Login Endpoint Down

**Customer impact:** 5

Every user is locked out simultaneously. Nobody can access their files. The product is completely inaccessible.

**Detection difficulty:** 2

Login failures are logged and visible in Grafana. However the current threshold is tuned for brute force detection rather than total login failure. If the login endpoint starts returning 500 errors for legitimate users, the failed login counter goes up but does not distinguish between wrong passwords and server crashes.

**Priority score:** 10

**How this fails in practice:**
- PostgreSQL connection pool exhausted so Flask cannot query the users table
- JWT secret key missing from the environment after a container restart
- An unhandled exception introduced by a recent code change
- nginx misconfiguration routing auth requests to the wrong service

**What the customer experiences:** The user enters correct credentials and receives an error or a spinner that never resolves. They cannot access their files. If they try to register instead, they may also be blocked depending on which component failed.

**Current detection capability:** Partial. The Login Activity Over Time graph shows successful and failed login trends side by side. A total absence of successful logins during active hours is the key signal.

**Early alert target:** Alert when login_success events drop to zero while total API activity remains non-zero. Also alert immediately on any 5xx response from the login endpoint.

**Automated test added:** TEST-OP-004 verifies a verified user can log in and receives an access token. TEST-OP-005 verifies wrong passwords return 401 and not 500.

---

### RISK-003: File Downloads Return Errors

**Customer impact:** 4

Users can log in and see their files but cannot access them. Files feel lost even though they still exist in S3. This is particularly damaging when users have urgent documents they need immediately.

**Detection difficulty:** 4

The download flow generates a presigned S3 URL and redirects the browser to S3. If the presigned URL is invalid due to a changed IAM policy or bucket configuration, the user receives an S3 Access Denied page in their browser. Flask logged a download_success event (it successfully generated the URL) but the user never got their file.

**Priority score:** 16

**How this fails in practice:**
- S3 bucket policy changed to block all access after a configuration change
- IAM policy modified to remove s3:GetObject permission
- Presigned URL expiry too short causing timeout on slow connections
- AWS region mismatch between file storage and URL generation

**What the customer experiences:** The user clicks download, a new tab opens with an S3 URL, and they see an Access Denied XML error page. The file is visible in their dashboard but cannot be retrieved. This looks to the user as though their data was deleted.

**Current detection capability:** Limited. Flask logs download_success when the URL is generated but has no visibility into whether the user actually received the file from S3.

**Early alert target:** Alert when download_success events drop to zero while login_success events remain active. As a stronger signal, add CloudWatch monitoring on S3 GetObject errors which would catch this at the AWS layer.

---

### RISK-004: Email Verification Completely Broken

**Customer impact:** 3

Existing users are not affected. New user onboarding is completely blocked. No new customers can activate their accounts.

**Detection difficulty:** 5 (Highest)

When email sending fails, the Flask backend logs an error but still returns a 201 success response to the user. The user thinks their account was created successfully. They wait for a verification email that never arrives. From their perspective the product silently failed, and they have no way to know whether to try again, check spam, or contact support. This is the hardest failure mode to detect.

**Priority score:** 15

**How this fails in practice:**
- Gmail App Password revoked by Google's automated security system
- SMTP credentials changed without updating the application configuration
- Gmail account flagged for sending too many emails and suspended
- Network outage preventing the backend from reaching external SMTP servers

**What the customer experiences:** The user registers, sees the "check your email" confirmation, waits indefinitely, never receives the email, and cannot log in. There is no resend option. The product appears broken for all new signups while existing users notice nothing.

**Current detection capability:** The backend logs email failures, but these are not consistently structured enough for reliable Grafana alerting. The Registrations vs Email Verifications panel added this sprint helps by making the gap between registrations and verifications visible.

**Early alert target:** Alert when a registration event occurs but no email_send_success event follows within 60 seconds. Also alert on any email_send_failure event regardless of count.

---

### RISK-005: Database Container Crash

**Customer impact:** 5

Complete product outage. No logins, no file listings, no sharing, no registration. Every feature stops working simultaneously.

**Detection difficulty:** 2

PostgreSQL crashes produce obvious error logs. Flask immediately starts returning 500 errors on any endpoint that needs database access, which shows up in Grafana as a spike in ERROR log entries. This is the easiest major failure to detect.

**Priority score:** 10

**How this fails in practice:**
- Docker host runs out of disk space and PostgreSQL cannot write its transaction logs
- Docker volume corruption from an unclean host shutdown
- PostgreSQL container OOM killed for exceeding the 512MB memory limit
- Connection pool exhausted under load

**What the customer experiences:** Every page returns an error. Login fails. The product appears completely dead to all users simultaneously.

**Current detection capability:** Good. The Database Container Logs panel in Grafana shows PostgreSQL logs directly. The Errors counter on the dashboard turns red immediately when Flask starts returning 500 errors. The existing monitoring is adequate for this risk.

**Early alert target:** Alert when FATAL appears in the PostgreSQL container logs. Alert separately when Flask ERROR events exceed 5 in any 5-minute window.

---

## 4. Risk Summary Table

| Risk | Customer Impact | Detection Difficulty | Priority Score | OE Dashboard Coverage |
| :--- | :--- | :--- | :--- | :--- |
| RISK-001: Upload silently fails | 5 | 4 | 20 | Upload Completions panel added |
| RISK-003: Downloads return errors | 4 | 4 | 16 | Partial. No S3 outcome visibility |
| RISK-004: Email verification broken | 3 | 5 | 15 | Registrations vs Verifications panel added |
| RISK-002: Login endpoint down | 5 | 2 | 10 | Login Activity graph covers this |
| RISK-005: Database crash | 5 | 2 | 10 | Database Container Logs panel added |

---

## 5. Dashboard Panels Added This Sprint

The following panels were added to the Grafana OE dashboard to monitor these operational risks:

| Panel | Type | Risk Covered | Behavior |
| :--- | :--- | :--- | :--- |
| Upload Completions Over Time | Time series | RISK-001 | Shows upload_success events per 5 minutes. Drop to zero while users are active is the alert signal |
| Email Send Failures | Stat counter | RISK-004 | Green when zero. Turns red immediately on any failure |
| Database Errors | Stat counter | RISK-005 | Green when zero. Turns red on any FATAL PostgreSQL log |
| S3 Errors | Stat counter | RISK-001, RISK-003 | Green when zero. Turns red on any s3_error log event |
| Total API Requests Over Time | Time series | All risks | Shows overall backend activity. Complete drop to zero means app is down |
| Registrations vs Email Verifications | Time series | RISK-004 | Gap between these two lines indicates email sending is broken |
| Login Success vs Failure Over Time | Time series | RISK-002 | Failures above zero with zero successes indicates login is broken |
| Database Container Logs | Log stream | RISK-005 | Raw PostgreSQL logs. Look for FATAL or ERROR during incidents |

---

## 6. Automated Tests Added This Sprint

Five automated tests were added to `backend/tests/test_operational.py` and run in the CI/CD pipeline on every push:

| Test | Risk | What it verifies |
| :--- | :--- | :--- |
| test_upload_url_endpoint_returns_required_fields | RISK-001 | Upload URL endpoint returns all three required fields: upload_url, fields, s3_key |
| test_confirm_upload_saves_file_metadata | RISK-001 | confirm-upload endpoint saves metadata and returns a file record |
| test_file_appears_in_list_after_upload | RISK-001 | Uploaded file appears in the file list immediately after confirmation |
| test_valid_verified_user_can_login | RISK-002 | A verified user with correct credentials receives an access token |
| test_login_returns_proper_error_for_wrong_password | RISK-002 | Wrong password returns 401, never 500 |

---

## 7. Key Insight: The Silent Failure Problem

RISK-001 and RISK-003 share a common characteristic: they fail silently. The Flask backend is not involved in the final step of either the upload or the download flow. Both end with a direct browser-to-S3 interaction. Flask generates the presigned URL and logs success, but never knows whether the user actually transferred the file.

This is the correct architectural design for performance and scalability but it requires different monitoring than a traditional server-side file transfer. The solution in the long term is client-side telemetry where the React frontend reports the outcome of the S3 transfer back to the Flask backend, regardless of success or failure. This is documented as a gap in the OE gaps document.
