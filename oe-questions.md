# OE Dashboard: Operational Questions for CloudDrive

**Version:** 2.0
**Date:** April 2026
**Author:** Mandaar Rao

---

## 1. Purpose

This document defines the questions an on-call engineer or product owner must be able to answer at any moment about the operational state of CloudDrive. Every panel on the OE dashboard exists to answer one or more of these questions. The dashboard runs on Grafana at http://localhost:3000, backed by Loki for log aggregation and Promtail for log collection from all Docker containers.

---

## 2. Is the product up and working right now?

- Are all containers running (nginx, backend, PostgreSQL, frontend, Grafana, Loki)?
- Is the backend producing logs? A silent backend is a dead backend.
- When was the last successful login?
- When was the last successful file upload?
- Are there any ERROR level log entries in the last 10 minutes?

**Answered by:** Backend Logs panel (full log stream, newest first), Error Logs stat counter

These are the first questions any on-call engineer asks when paged. If the backend log stream in Grafana is empty or frozen, the container has likely crashed. If the error counter is non-zero and climbing, something is actively failing in the application.

---

## 3. Are users able to use the product normally?

- How many users have logged in successfully in the last hour?
- How many file uploads have succeeded in the last hour?
- How many file downloads have been requested in the last hour?
- Is login activity trending up, down, or flat over the last hour?
- Is upload activity consistent or showing unexpected spikes or drops?

**Answered by:** Login Activity Over Time graph (shows successful vs failed logins as separate lines over time), File Operations Over Time graph (uploads vs downloads over time), Login Success stat counter, File Uploads stat counter

A healthy product shows consistent login and upload activity during active use. A sudden drop to zero in uploads while logins continue is a signal that S3 connectivity has been lost. The app appears healthy but the core feature is broken.

---

## 4. Is the system under attack or behaving suspiciously?

- How many failed login attempts have occurred in the last hour?
- Is the failed login count trending upward, suggesting a brute force attempt?
- Are repeated failed logins coming from the same user or spreading across many accounts?
- How many rate limit rejections have been issued in the last hour?

**Answered by:** Login Failures stat counter (color threshold: green below 3, yellow at 3, red at 10), Login Activity Over Time graph showing failed logins as a separate colored line, Auth Events log stream showing individual login events with email and timestamp

A spike in the failed login counter alongside flat or zero successful logins is a classic brute force pattern. The rate limiter caps attempts at 5 per minute per IP. The dashboard shows whether the limiter is triggering or whether an attacker is successfully staying under the threshold.

---

## 5. What file operations are happening?

- What files have been uploaded in the last hour, by which users?
- What files have been downloaded in the last hour?
- Have any files been soft-deleted recently?
- Are there any upload failures appearing in the log stream?

**Answered by:** File Events log stream (shows upload_success, download_success, soft-delete events with user ID and filename), File Operations Over Time graph

This answers whether the core product functionality is being actively used and whether any file operations are failing silently. An upload count of zero during active use when users are logged in indicates a broken upload flow, likely an S3 permission or connectivity issue.

---

## 6. What happened recently?

- What were the last 20 log entries from the backend?
- Were there any errors or warnings in the last 5 minutes?
- What sequence of events preceded a user complaint?

**Answered by:** Backend Logs panel (full stream, all log levels), Auth Events log panel, File Events log panel

The raw log stream is what an on-call engineer uses to establish a timeline during an incident. The first question after "what is broken" is always "when did this start." The Grafana time range picker lets you scroll back to any window to reconstruct what happened.

---

## 7. Questions the dashboard cannot currently answer

- Per-container CPU and memory usage — requires cAdvisor or node-exporter, not yet integrated
- S3 connectivity status in real time — no dedicated health check endpoint emitting structured logs yet
- Email delivery success and failure rates — SES metrics not yet shipped to Loki
- End-to-end upload latency from browser click to S3 confirmation — not yet instrumented
- Number of currently active sessions — JWT is stateless so there is no session count without a dedicated counter
- Database query performance — no slow query logging configured in PostgreSQL

These are documented here so they are addressed in future observability work rather than discovered during an actual incident.

---

## 8. AI Generation Notes

The initial question framework was generated with AI assistance. The following were added or modified manually based on real observations during development and testing of the running application:

- The "silent backend is a dead backend" point was added after observing that container crashes do not always produce visible error messages — the absence of logs is itself a detection signal
- The S3 gap in section 7 was added after personally experiencing an S3 authentication failure during development that looked like a healthy system from outside because the nginx health check did not verify S3 connectivity
- The brute force detection framing in section 4 was refined after implementing flask-limiter and realizing the threshold needed to be visible on the dashboard to confirm the limiter was actually triggering
