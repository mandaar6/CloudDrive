# Gaps Analysis and Potential Improvements: CloudDrive

**Version:** 1.0
**Date:** April 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document identifies gaps in what the AI-generated code and AI-assisted threat model produced versus what a production-grade secure file storage system would actually require. It is organized into three categories: security gaps (vulnerabilities the AI did not flag or implement fixes for), functional gaps (features that are incomplete or missing), and operational gaps (things missing from the monitoring and incident response setup).

---

## 2. How the AI Was Used

Claude Code was used to generate the full project from a single detailed prompt. Claude.ai (this chat) was used to act as a second reviewer on the technical design, generate the threat model, and produce the initial security testing documentation.

The AI was given the full stack specification, the folder structure, and a list of intentional vulnerabilities to plant. It produced working code in a single session that ran successfully on the first docker compose up after minor environment configuration.

---

## 3. Security Gaps the AI Missed or Underspecified

### GAP-001: Edit Permission Is Not Enforced

The AI generated a database schema with a `permission` column that stores either `read` or `edit` for each file share. However, the API and frontend were never wired up to actually differentiate between these two values. When tested, both read and edit shared files showed only a download button with identical behavior.

In a real system, edit permission should at minimum allow the recipient to re-upload a new version of the file. The AI built the data model correctly but did not complete the feature logic on either the backend or the frontend.

This was caught through manual testing of the running application, not through any AI-generated test or review.

**What should be implemented:**
- A re-upload endpoint that checks the permission column before allowing overwrite
- File versioning so the original is not permanently replaced
- File type validation on re-upload to prevent a .txt being replaced by a .exe
- A notification to the owner when an editor uploads a new version

---

### GAP-002: No File Size or Type Limits on Upload

The AI-generated upload endpoint accepts any file regardless of type or size. This was not flagged by the AI in either the threat model or the initial security testing outline.

A user could upload a 5GB video file, an executable disguised as a document, or an empty file with no validation errors. Against an S3 bucket with overprivileged IAM access this could result in significant AWS cost accumulation from a single malicious or careless user.

Semgrep did not catch this because it is a logic gap rather than a code pattern. Trivy did not catch it because it is an application design issue, not a library vulnerability.

**What should be implemented:**
- A maximum file size limit enforced at both the Nginx layer and the Flask layer
- An allowlist of permitted file extensions
- MIME type verification on the server side since file extensions can be spoofed

---

### GAP-003: PyJWT Version Has a Known HIGH Severity CVE

Trivy identified that PyJWT 2.8.0 (the version installed by the AI-generated requirements.txt) contains CVE-2026-32597, a HIGH severity vulnerability where the library accepts unknown `crit` header extensions in violation of RFC 7515. A fix is available in version 2.12.0.

The AI did not pin library versions to their latest secure releases and did not include a step in the workflow to verify dependencies against known CVE databases before generating requirements.txt.

**What should be implemented:**
- Upgrade PyJWT to 2.12.0 in requirements.txt
- Add `pip-audit` or `safety` to the CI/CD pipeline to automatically check Python dependencies against known CVEs on every push

---

### GAP-004: No Access Revocation for Shared Files

Once a file is shared with another user, the owner has no way to revoke that access through the UI. The shares table in the database has an `expires_at` column but it is never populated or enforced.

The AI built the data model to support expiry but did not implement the expiry logic, the revocation endpoint, or any UI for the owner to manage existing shares.

**What should be implemented:**
- A revocation button next to each share in the owner's file list
- A DELETE /api/files/:id/share/:share_id endpoint
- Enforcement of the expires_at column so time-limited shares actually stop working

---

### GAP-005: No Notification System for File Access Events

When someone downloads a shared file or accesses a presigned URL, the file owner receives no notification. In a real file sharing system this is a critical transparency feature, especially when combined with the presigned URL forwarding risk identified in the threat model.

The AI generated structured logging to Loki but the logs are only visible to an administrator in Grafana. The file owner themselves has no visibility into who accessed their files or when.

**What should be implemented:**
- An activity log visible to the file owner on the dashboard
- Email notifications when a shared file is first accessed (requires SMTP integration)
- An alert to the owner if a file is downloaded more than N times in a short period

---

### GAP-006: Grafana Dashboard Has No Pre-built Panels

The AI generated a Grafana data source configuration that connects to Loki, but no actual dashboards or panels were created. When Grafana is accessed at localhost:3000 it is completely empty. An operator would have to build all panels from scratch.

For the OE dashboard to function as a security monitoring tool it needs pre-configured panels at a minimum showing failed login attempts over time, file download volume per user, sharing activity, and any requests that returned 4xx or 5xx status codes.

**What should be implemented:**
- A Grafana dashboard JSON file provisioned at startup via the grafana/dashboards/ directory
- Panels for login failures, file access events, error rates, and share activity
- An alert rule for more than 10 failed login attempts from the same IP in 60 seconds

---

### GAP-007: No Container Resource Limits

The docker-compose.yml generated by the AI has no memory or CPU limits on any container. A single misbehaving or attacked container can consume all host resources and take down the entire application stack.

This was identified through manual review of the docker-compose.yml and was not flagged by any automated tool.

**What should be implemented:**
```yaml
deploy:
  resources:
    limits:
      memory: 512m
      cpus: "0.5"
```
Applied to each service in docker-compose.yml.

---

## 4. Functional Gaps

### GAP-008: No File Delete by Shared Users

The delete button is visible only to the file owner, which is correct. However, a user who has edit permission on a shared file cannot remove their own copy of the share or opt out of a share they no longer want. There is no self-service way for a recipient to remove a shared file from their view.

---

### GAP-009: No Search or Filtering on the Dashboard

As the number of files grows, the dashboard becomes a flat unordered list with no search, sort, or filter capability. This is a usability gap that becomes a security gap when an owner cannot easily find a specific file to check or revoke its share status.

---

### GAP-010: Presigned URL Expiry Not Configurable

The presigned URL expiry is hardcoded in the backend. For high-sensitivity files a shorter expiry (5 minutes) would be appropriate. For large files that take time to download a longer window may be needed. This should be configurable per file or per share rather than a global constant.

---

## 5. Operational Gaps

### GAP-011: No Incident Runbook Generated by AI

The AI did not generate any incident response documentation. The threat model identified threats and the security testing confirmed them, but there are no documented procedures for what to do when one of those threats is exploited. Detection, containment, and recovery steps for each identified threat need to be written and stored in the repository.

---

### GAP-012: CI/CD Pipeline Has No Defined Failure Thresholds

The GitHub Actions pipeline runs Semgrep and Trivy but the AI did not configure severity thresholds that determine whether the pipeline actually blocks a merge. Without thresholds the scans are informational only. A developer could merge code with HIGH severity findings and the pipeline would still show green.

**What should be implemented:**
- `trivy image --exit-code 1 --severity CRITICAL` to fail the build on any CRITICAL finding
- Semgrep already blocks on its `blocking` classification but this should be verified in the workflow file

---

## 6. What the AI Did Well

It is worth noting what the AI produced correctly so the gaps are understood in context.

The overall architecture was sound and matched the technical design document accurately. The Docker Compose multi-container setup with Nginx, Flask, PostgreSQL, and Grafana worked on the first run with no structural errors. The bcrypt password hashing, JWT issuance, and S3 presigned URL logic were all implemented correctly. The intentional vulnerabilities were planted where specified and were confirmed working through manual testing. The database schema correctly represented the three-way relationship between users, files, and shares.

The AI also correctly identified that the biggest threats in the threat model would come from the cloud configuration layer, not just the application code, which reflects a more mature understanding of real-world attack surfaces than a purely code-focused approach would produce.

---

## 7. Summary of Gaps

| Gap ID | Category | Severity | Caught by AI | Caught by Testing |
| :--- | :--- | :--- | :--- | :--- |
| GAP-001 | Security | High | No | Manual testing |
| GAP-002 | Security | High | No | Manual testing |
| GAP-003 | Security | High | No | Trivy scan |
| GAP-004 | Security | Medium | No | Manual testing |
| GAP-005 | Security | Medium | No | Manual review |
| GAP-006 | Operational | Medium | No | Manual review |
| GAP-007 | Security | Medium | No | Manual review |
| GAP-008 | Functional | Low | No | Manual testing |
| GAP-009 | Functional | Low | No | Manual review |
| GAP-010 | Functional | Low | Partial | Manual review |
| GAP-011 | Operational | High | No | Manual review |
| GAP-012 | Operational | Medium | No | Manual review |

The most consistent pattern across all gaps is that the AI produced correct data models and architectural structures but left business logic and enforcement incomplete. It built the skeleton but required a security-aware developer to identify where the muscles were missing.
