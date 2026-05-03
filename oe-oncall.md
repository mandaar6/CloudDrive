# On-Call Guide: Using the CloudDrive OE Dashboard

**Version:** 2.0
**Date:** April 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document describes how an on-call engineer uses the CloudDrive OE dashboard to detect, investigate, and respond to operational problems. The dashboard runs on Grafana at http://localhost:3000 inside its own Docker container (`clouddrive-grafana-1`), separate from the application containers. It stays accessible even when the application is restarting, which is intentional — the observability layer must survive the thing it is observing.

The dashboard auto-refreshes every 30 seconds. All log data is real, pulled from the running application via Promtail and Loki.

---

## 2. Dashboard Layout and What Each Panel Tells You

**Backend Logs (top, full width)**
The raw log stream from the Flask backend. This is your ground truth. Everything else on the dashboard is derived from these logs. If this panel is empty, the backend is not running.

**Login Activity Over Time (time series graph, left)**
Two lines: successful logins in green, failed logins in red, plotted in 5-minute buckets over the last hour. Normal state: a moderate green line, flat or slightly varying red line near zero. Concerning state: red line rising while green line stays flat or drops.

**File Operations Over Time (time series graph, right)**
Two lines: uploads in blue, downloads in orange, plotted in 5-minute buckets. Normal state: some activity on both lines when users are active. Concerning state: downloads continuing while uploads drop to zero (S3 write permission lost) or both dropping to zero (application down).

**Four stat counters (middle row)**
Login Success, Login Failures, File Uploads, Error Logs — each showing totals for the last hour. The Login Failures counter has a color threshold: green below 3, yellow from 3 to 9, red at 10 or above. The Error counter turns red at 1.

**Auth Events and File Events log streams (bottom)**
Filtered views of the backend log stream showing only authentication and file operation events respectively. Easier to read than the full log when investigating a specific type of issue.

---

## 3. Incident Scenario 1: Users Cannot Log In

**How you detect it**
The Login Success counter shows zero or near-zero while Login Failures is non-zero and climbing. The Login Activity graph shows the red (failure) line above the green (success) line.

**Step 1: Check if the backend is running**
Look at the Backend Logs panel. If it shows log entries in the last 2 minutes, the backend is alive. If it is empty, the backend container has crashed — run `sudo docker compose ps` in the terminal and look for the backend showing `Exit` status.

**Step 2: Read the Auth Events stream**
Filter by looking at the Auth Events log panel. Each failed login shows a line like:
```
WARNING app.auth login_failure email=user@example.com
```
If you see many of these from the same email in rapid succession, it is a brute force attempt. If the failures say something about database errors, PostgreSQL is the problem.

**Step 3: Check the failure pattern**
- Many failures against one email, rapid succession: brute force. The rate limiter should have triggered. Check if the Login Failures counter jumped by 5 in under a minute — if yes, the limiter is working and is blocking the attacker. If the counter keeps climbing past 5 per minute, the rate limiter may not be functioning.
- Failures across many different emails: credential stuffing attack or a bug that broke authentication for everyone.
- Zero successful logins but no failures either: the login page may not be reaching the backend. Check if nginx is running.

**Step 4: Check the database**
If the auth logs show database-related errors, run:
```bash
sudo docker compose logs db --tail=20
```
Look for `FATAL` entries indicating the database container is down or rejecting connections.

**Resolution:** Restart crashed containers with `sudo docker compose up -d`. If the database volume is corrupted, `sudo docker compose down -v && sudo docker compose up --build` — note this wipes all data.

---

## 4. Incident Scenario 2: File Uploads Are Failing

**How you detect it**
The File Uploads stat counter is zero. The File Operations graph shows uploads at zero while downloads may still be working. Users report the upload area is not responding or showing errors.

**Step 1: Check the File Events stream**
Look at the File Events log panel. If uploads are failing at the S3 presigned URL generation step, you will see a line like:
```
INFO app.files upload_success
```
is absent, meaning no uploads are reaching the confirm-upload endpoint. If you see the upload-url endpoint being called but no confirm-upload following it, the S3 direct upload is failing.

**Step 2: Check the Backend Logs panel**
Look for any ERROR lines related to S3, boto3, or AWS. Common patterns:
- `NoCredentialsError` — AWS credentials in the .env file are missing or the container was restarted without the .env being present
- `ClientError: AccessDenied` — the IAM policy on the clouddrive-app user was modified and no longer allows PutObject or GeneratePresignedPost
- `EndpointResolutionError` — the backend container cannot reach the AWS API, likely a network issue

**Step 3: Check S3 credentials directly**
```bash
sudo docker compose exec backend python3 -c "
import boto3
s3 = boto3.client('s3')
print(s3.list_buckets())
"
```
If this prints buckets, AWS credentials are valid. If it throws NoCredentialsError, the credentials are missing from the container environment.

**Step 4: Check the browser console**
The direct S3 upload happens from the browser, not through nginx. Open browser DevTools, Network tab, and try an upload. If the request to `/api/files/upload-url` succeeds but the subsequent POST to S3 fails with a CORS error, the S3 bucket CORS configuration was removed. Re-add it in the AWS S3 console under the bucket Permissions tab.

**Resolution:** Restore AWS credentials in .env and restart the backend container. Fix IAM permissions in the AWS console if needed. Re-add CORS configuration to the S3 bucket if missing.

---

## 5. Incident Scenario 3: Application Is Completely Down

**How you detect it**
The Backend Logs panel in Grafana is empty. http://localhost returns no response or a 502 Bad Gateway from nginx. All stat counters show No data.

**Step 1: Check Grafana is still accessible**
If Grafana itself at http://localhost:3000 is unreachable, Docker itself may have crashed or the machine rebooted. Run `sudo systemctl start docker` and then `sudo docker compose up -d` in the project directory.

**Step 2: Check container status**
```bash
sudo docker compose ps
```
Note which containers show `Exit` or `Restarting` status.

**Step 3: Check the crashed container logs**
```bash
sudo docker compose logs backend --tail=50
sudo docker compose logs db --tail=20
sudo docker compose logs nginx --tail=20
```
The error in the logs will tell you the root cause. Common causes:
- Backend shows `ImportError` — a Python dependency is missing, rebuild with `sudo docker compose up --build`
- Backend shows `OperationalError` connecting to database — PostgreSQL is not ready yet, wait 10 seconds and the backend will retry
- Database shows `FATAL: password authentication failed` — the POSTGRES_PASSWORD in .env does not match what the volume was initialized with, requires `sudo docker compose down -v && sudo docker compose up --build` (data loss)
- Nginx shows `connect() failed` — the backend container is not running, restart it

**Step 4: Restart procedure**
```bash
cd /home/kali/CloudDrive/clouddrive
sudo docker compose down
sudo docker compose up --build
```

**Step 5: Verify recovery**
After restart wait 30 seconds for Grafana to reconnect to Loki. Then check:
- Backend Logs panel shows recent log entries
- A test login succeeds
- A test file upload succeeds
- The time-series graphs begin showing fresh data points

---

## 6. Reading the Time-Series Graphs During an Incident

The Login Activity and File Operations graphs use 5-minute buckets. This means each data point represents the count of events in a 5-minute window. When investigating an incident:

- Set the Grafana time range to "Last 3 hours" to see the full context of when things changed
- Look for the exact moment a line drops to zero or spikes — that is when the incident started
- Cross-reference that timestamp with the Backend Logs panel filtered to the same time window using Grafana's time range brush

The graphs turn a brute force attack visible: the failed logins line will show a sharp spike upward at the exact moment the attack started. If the spike then drops or flattens, the rate limiter is working. If it continues rising, the attack is ongoing.

---

## 7. Known Gaps in the Dashboard

The following situations cannot be detected by the current dashboard and require manual investigation:

- **S3 connection failures** — not yet emitting structured logs, must check raw backend logs
- **Rate limit triggers** — not yet emitting structured logs, must check nginx logs for 429 responses
- **Email send failures** — partially logged but not queryable in Grafana yet
- **Container resource exhaustion** — no CPU or memory panels, must use `docker stats` in terminal

These gaps are highest priority for the next observability sprint. Until then, the on-call procedure for these scenarios involves checking raw logs directly in the terminal rather than through Grafana.

---

## 8. AI Generation Notes

The incident scenario structure was generated with AI assistance. The following were written manually based on real incidents encountered during development:

- The specific boto3 error messages in Scenario 2 (NoCredentialsError, AccessDenied, EndpointResolutionError) were taken directly from real errors encountered while setting up the AWS S3 integration
- The CORS gap in Scenario 2 was added after personally debugging a direct S3 upload failure where the presigned URL was generated correctly but the browser blocked the cross-origin POST
- The database password mismatch scenario in Scenario 3 step 3 was added after personally losing development data by running docker compose down -v unnecessarily
- The time-series graph reading instructions in section 6 were written based on actually using the Grafana dashboard during a simulated brute force test (failed login attempts 6 times rapidly to trigger rate limiting)
