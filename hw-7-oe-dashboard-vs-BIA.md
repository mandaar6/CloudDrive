# OE Dashboard Comparison: Current State vs Business Risk Analysis

**Version:** 2.0
**Date:** May 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document compares what the CloudDrive OE dashboard can currently answer against the five business risks identified in the HW6 operational risk assessment. For each risk, it describes the coverage before this sprint, what the dashboard now shows, and what gaps remain.

The key improvement this sprint was adding six new structured log events to Flask and rebuilding the dashboard with 21 panels organized into four sections. The new log events are visible in the Backend Application Logs and Auth and File Events panels, confirming the dashboard is genuinely connected to real product behavior.

---

## 2. What Changed This Sprint

**New Flask log events added:**

| Event | Where emitted | Purpose |
| :--- | :--- | :--- |
| `upload_url_requested user=X filename=Y` | get_upload_url endpoint | Tracks start of every upload attempt |
| `confirm_upload_received user=X filename=Y` | confirm_upload endpoint | Tracks browser calling back after S3 step |
| `email_send_success type=verification/password_reset` | auth.py email send | Confirms email was sent via SMTP |
| `email_send_failure type=X error=Y` | auth.py except blocks | Confirms email failed with error type |
| `s3_error operation=X error=Y` | All boto3 except blocks | Catches any AWS S3 error by operation |
| `request_completed method=X path=Y status=Z duration_ms=N` | after_request hook in __init__.py | Logs every HTTP request with timing |

**New dashboard structure:**
The dashboard was rebuilt from scratch with four collapsible row sections: System Health, User and File Activity, Alert Panels, and Live Logs. Panel types now include gauges (for response time), stat panels with sparklines (for counts with trend), time series graphs (for activity over time), and log stream panels (for raw event viewing).

---

## 3. Risk-by-Risk Comparison

---

### RISK-001: File Uploads Fail Silently

**HW6 assessment:**
Priority score 20 out of 25. Highest business risk. File upload is the core feature and failures are completely invisible to server-side monitoring because the browser uploads directly to S3, bypassing Flask entirely.

**Before this sprint:**
The dashboard had a single upload_success count and a basic File Operations graph. Neither could detect a failure between the browser and S3. The detection difficulty was rated 4 out of 5.

**After this sprint:**
The Upload Funnel Over Time graph now tracks all three stages of the upload flow on one chart. During testing all three lines (Upload Requested, Confirm Received, Upload Confirmed) tracked together, confirming the complete flow was healthy. A gap between the first and second line is the early warning signal that the browser-to-S3 step is failing before Flask even knows an upload attempt was started. The Upload URL Requests stat (4 during testing) and File Uploads stat (4 during testing) matching each other also confirms all attempts completed.

**What this means in practice:**
An on-call engineer can now detect a silent upload failure within 5 to 10 minutes by seeing the Upload Requested line rise while Confirm Received stays flat. Before this sprint, this failure mode could go undetected for hours until users complained.

**Remaining gap:**
The funnel cannot confirm that the S3 upload actually succeeded before confirm_upload was called. A frontend bug could call confirm_upload even after an S3 failure, making the funnel look healthy when it is not. Client-side S3 outcome reporting would close this gap.

**Coverage change:** None to Partial.

---

### RISK-002: Login Endpoint Down

**HW6 assessment:**
Priority score 10. Customer impact 5 (all users locked out). Detection difficulty 2 (failures are logged and visible). Already relatively well covered before this sprint.

**Before this sprint:**
Login failure count and Login Activity Over Time graph were working. Coverage was partial because there was no response time signal to detect degradation before complete failure.

**After this sprint:**
The Login Response Time gauge now shows real-time average response time for the login endpoint specifically. During testing this was consistently 716ms to 737ms. If the database connection pool starts degrading, this number rises before the endpoint fails completely, giving an early warning signal that did not exist before. The Login Failure Alert panel now uses a 10-minute window instead of 1 hour, making it more sensitive to attacks in progress.

**What this means in practice:**
An engineer watching the dashboard can now see login response times creeping up from 720ms toward 1200ms and investigate the database before the login endpoint fails entirely. This changes the response from reactive (users complaining they cannot log in) to proactive (investigate before users are affected).

**Remaining gap:**
The dashboard does not distinguish between 401 errors from wrong passwords (expected and harmless) and 500 errors from server crashes (a real incident). Both show up in the failure count.

**Coverage change:** Partial to Good.

---

### RISK-003: File Downloads Return Errors

**HW6 assessment:**
Priority score 16. Customer impact 4 (files appear lost). Detection difficulty 4 (Flask thinks it succeeded but S3 may reject the presigned URL).

**Before this sprint:**
No specific download monitoring. Flask logged download_success after generating a presigned URL but had no visibility into whether S3 accepted the URL when the browser used it.

**After this sprint:**
The S3 Errors alert panel now catches boto3 ClientError exceptions that happen inside Flask during presigned URL generation. The `s3_error operation=get_object` event is emitted specifically when the download endpoint fails inside Flask. If the IAM policy is changed to remove s3:GetObject permission, the next download attempt fires an s3_error event and the alert panel turns red within seconds.

The Auth and File Events log panel also filters for s3_error events, making them easy to spot during an incident investigation.

**What this means in practice:**
Failures that happen inside Flask during presigned URL generation are now caught within one Grafana refresh cycle. This covers IAM permission errors and network issues between Flask and S3.

**Remaining gap:**
Flask considers its job done after generating the presigned URL. If S3 rejects the URL when the user's browser tries to use it (for example due to a policy change that took effect between URL generation and the user clicking download), that rejection goes to the browser as an Access Denied page and Flask never sees it. This is still completely invisible to the dashboard.

**Coverage change:** None to Partial.

---

### RISK-004: Email Verification Completely Broken

**HW6 assessment:**
Priority score 15. Customer impact 3 (new user onboarding blocked). Detection difficulty 5 (highest) because Flask returns 201 success even when email sending fails, making the failure invisible to users and to server-side monitoring.

**Before this sprint:**
The Registrations vs Verifications graph existed but had a significant time lag because a verification only appears in Loki when a user clicks the link, which might be hours after registration. An email failure would not be visible until users eventually gave up waiting.

**After this sprint:**
The Email Success vs Failure graph now shows email_send_success and email_send_failure events emitted immediately when Flask attempts to send an email via SMTP. If Gmail SMTP credentials are revoked, the very next registration triggers an email_send_failure event and the Email Send Failures alert panel turns red within 30 seconds.

This reduced the effective detection difficulty from 5 to approximately 2. The failure is now visible within the same minute it occurs rather than being discovered hours later.

**What this means in practice:**
An engineer can now see exactly when email delivery started failing and correlate it with any configuration changes made around the same time. Before this sprint, the only signal was a growing gap in the Registrations vs Verifications graph which could take hours to become obvious.

**Remaining gap:**
The dashboard cannot detect cases where Flask successfully sends the email to the SMTP server but the email never reaches the user's inbox (spam filtering, recipient domain bouncing). These delivery failures happen at the mail server level and require SMTP delivery status callbacks or bounce tracking.

**Coverage change:** Partial to Good. This was the biggest detection improvement of the sprint.

---

### RISK-005: Database Container Crash

**HW6 assessment:**
Priority score 10. Customer impact 5 (complete outage). Detection difficulty 2 (crashes produce obvious errors). Already well covered before this sprint.

**Before this sprint:**
Database Container Logs panel and the Error Rate stat were working. Coverage was good.

**After this sprint:**
The Database Fatal Errors alert panel was added as a dedicated red/green indicator for FATAL level PostgreSQL log entries. The System Activity Over Time graph also shows a rising error line when Flask starts returning 500 errors due to database unavailability. The request_completed events with status codes make it easy to see when database failures start causing application errors.

**What this means in practice:**
An engineer can now see a PostgreSQL FATAL event in both the Database Container Logs stream and the dedicated Database Fatal Errors alert panel simultaneously, making the failure impossible to miss on a dashboard glance.

**Remaining gap:**
The dashboard still has no visibility into database query performance or connection pool utilization. A slow query that is not causing failures would not appear on any panel.

**Coverage change:** Good to Good (incremental improvement).

---

## 4. Summary

| Risk | HW6 Coverage | HW7 Coverage | Key Change |
| :--- | :--- | :--- | :--- |
| RISK-001: Upload silently fails | None | Partial | Upload Funnel three-line graph added |
| RISK-002: Login endpoint down | Partial | Good | Response time gauge adds proactive warning |
| RISK-003: Downloads return errors | None | Partial | s3_error events now caught from Flask-side operations |
| RISK-004: Email verification broken | Partial | Good | Same-minute email failure detection via email_send_failure event |
| RISK-005: Database crash | Good | Good | Dedicated Fatal Errors alert panel added |

---

## 5. Biggest Remaining Gap

The most significant gap across all five risks is the absence of client-side telemetry. Two of the five risks involve operations that happen directly between the user's browser and AWS S3, completely bypassing Flask. RISK-001 (silent upload failure) and RISK-003 (download errors) both have blind spots at exactly the moment the user either gets their file or does not. Flask generates a presigned URL and considers its job done. Whether the user actually transferred the file is invisible to every server-side panel on the dashboard.

A lightweight JavaScript event added to the React frontend that reports the S3 transfer outcome back to Flask would close both gaps simultaneously. Flask would log `s3_transfer_success` or `s3_transfer_failure` with the operation type, and Grafana would finally have end-to-end visibility into the product's two most important operations.

A second significant gap discovered this sprint is the Loki overload issue. With 21 panels refreshing every 30 seconds, Loki occasionally returns `Status 500: too many outstanding requests`. This causes some panels to show No data for one refresh cycle before recovering. The fix involves increasing Loki's concurrent query limit and simplifying the more expensive LogQL queries that use regexp extraction for numeric field parsing.

---

## 6. AI Generation Notes

The comparison framework was generated with AI assistance. The following were written or verified manually:

- All response time values (716ms, 737ms login; 210ms average) are from actual gauge readings in the dashboard screenshots captured during this sprint
- The Upload Funnel behavior described in RISK-001 was verified by watching the three lines track together during a live upload session
- The Loki overload issue mentioned in the final section was observed directly during dashboard testing when the 500 error appeared across multiple panels simultaneously
- The email failure detection improvement for RISK-004 was verified by confirming that email_send_success events appear in the Email Success vs Failure graph within the same Grafana refresh cycle as the registration event
