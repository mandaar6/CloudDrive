# Threat Model: CloudDrive

**Version:** 1.0
**Date:** April 2026
**Method:** STRIDE
**Author:** Mandaar Rao

---

## 1. Overview

This document covers the threat model for CloudDrive, a secure cloud file storage and sharing web application. The system allows users to register, upload files to AWS S3, and share those files with other users using configurable read or edit permissions.

Threats are analyzed across three layers: the application layer, the container infrastructure layer, and the cloud configuration layer. This multi-layer approach reflects real-world attack scenarios where an attacker does not always target the application directly but may instead go around it by targeting the infrastructure or cloud configuration underneath.

---

## 2. System Components

| Component | Description |
| :--- | :--- |
| React Frontend | Browser-based UI served through Nginx |
| Flask Backend | REST API handling auth, file operations, and sharing logic |
| PostgreSQL | Stores users, file metadata, and share records |
| AWS S3 | Stores actual file bytes |
| Nginx | Reverse proxy handling TLS termination |
| Grafana + Loki | Operational dashboard and log aggregation |
| Docker Compose | Orchestrates all containers |

---

## 3. Data Flow

```
User Browser
     |
     | HTTPS
     v
Nginx Container (port 80/443)
     |
     v
Flask Backend Container (port 5000)
     |
     +---------> PostgreSQL Container (user records, file metadata, share records)
     |
     +---------> AWS S3 (file bytes via presigned URLs)
     |
     +---------> Loki (structured logs) --> Grafana (dashboard)
```

**Key data flows:**
- User credentials travel from browser to Flask over HTTPS
- Passwords are hashed with bcrypt before being stored in PostgreSQL
- File bytes are sent directly from Flask to S3 via the AWS SDK
- File downloads use presigned S3 URLs that expire after one hour
- JWT tokens are issued on login and stored as HTTP-only cookies

---

## 4. Trust Boundaries

| Boundary | Description |
| :--- | :--- |
| Internet to Nginx | Public-facing entry point. All external traffic crosses here. |
| Nginx to Flask | Internal Docker network. Should not be exposed publicly. |
| Flask to PostgreSQL | Internal Docker network. Database should never be internet-facing. |
| Flask to AWS S3 | External call over TLS to AWS. Authenticated via IAM credentials. |
| User to S3 (presigned URL) | Direct browser-to-S3 download. Bypasses Flask entirely. |

---

## 5. STRIDE Threat Analysis

### 5.1 Application Layer

---

**THREAT-001**
- **Category:** Spoofing
- **Component:** Login endpoint (/api/auth/login)
- **Description:** An attacker can attempt unlimited login attempts against any account because there is no rate limiting or account lockout on the login endpoint. This makes brute force and credential stuffing attacks viable.
- **Likelihood:** High
- **Impact:** High
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Implement rate limiting (e.g. 5 attempts per minute per IP) and account lockout after 10 consecutive failures.

---

**THREAT-002**
- **Category:** Elevation of Privilege
- **Component:** File download endpoint (/api/files/download/:id)
- **Description:** File IDs are sequential integers (1, 2, 3...). An authenticated user can access another user's files by simply changing the file ID in the request. This is an Insecure Direct Object Reference (IDOR) vulnerability and is listed as the top risk in the OWASP Top 10.
- **Likelihood:** High
- **Impact:** High
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Use UUIDs instead of sequential integers for file IDs, and validate file ownership on every request before returning any data.

---

**THREAT-003**
- **Category:** Elevation of Privilege
- **Component:** JWT authentication
- **Description:** JWT tokens are issued with a 30-day expiry and there is no server-side revocation mechanism. If a token is stolen (via XSS, network interception, or physical access to a device), it remains valid for the full 30 days with no way to invalidate it.
- **Likelihood:** Medium
- **Impact:** High
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Implement a token revocation list in the database, reduce token expiry to 1 hour, and use refresh tokens for session continuation.

---

**THREAT-004**
- **Category:** Information Disclosure
- **Component:** File sharing and presigned URLs
- **Description:** When a user downloads a file, they receive a presigned S3 URL valid for one hour. This URL can be copied and shared with anyone. Because the S3 bucket is publicly readable, the URL works for any person who receives it regardless of whether they have an account.
- **Likelihood:** Medium
- **Impact:** Medium
- **Current State:** Partially intentional (public bucket is documented vulnerability, URL forwarding is a design gap)
- **Recommended Fix:** Make the bucket private and rely exclusively on presigned URLs. Add IP binding or signed URL fingerprinting for sensitive files.

---

**THREAT-005**
- **Category:** Tampering
- **Component:** File upload endpoint
- **Description:** There are no restrictions on file type or file size during upload. An attacker could upload very large files to exhaust S3 storage and inflate AWS costs (denial of service via cost), or upload malicious executables disguised as documents.
- **Likelihood:** Medium
- **Impact:** Medium
- **Current State:** Not implemented (gap identified by review)
- **Recommended Fix:** Enforce file type allowlists, maximum file size limits, and consider malware scanning via AWS Lambda or ClamAV on upload.

---

**THREAT-006**
- **Category:** Information Disclosure
- **Component:** Error responses from Flask API
- **Description:** Unhandled errors may return stack traces or internal system information to the client. This can reveal file paths, library versions, database structure, or other internal details useful to an attacker.
- **Likelihood:** Medium
- **Impact:** Low
- **Current State:** Not verified (gap identified by review)
- **Recommended Fix:** Implement a global error handler in Flask that returns generic error messages to clients and logs detailed errors internally only.

---

### 5.2 Container Infrastructure Layer

---

**THREAT-007**
- **Category:** Elevation of Privilege
- **Component:** Flask backend Dockerfile
- **Description:** The application container runs as the root user. If an attacker achieves remote code execution inside the container through an application vulnerability, they have root-level access within the container. Combined with other misconfigurations this can lead to a container escape.
- **Likelihood:** Low
- **Impact:** Critical
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Add a non-root user in the Dockerfile and switch to that user before running the application. Example: `RUN adduser --disabled-password appuser && USER appuser`

---

**THREAT-008**
- **Category:** Elevation of Privilege
- **Component:** Docker socket exposure
- **Description:** If the Docker socket (/var/run/docker.sock) is mounted inside the application container, an attacker who compromises the container can communicate with the Docker daemon on the host, spin up new containers, and escape to the host system entirely.
- **Likelihood:** Low
- **Impact:** Critical
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Never mount the Docker socket inside application containers. Use dedicated CI/CD tooling for any operations that require Docker access.

---

**THREAT-009**
- **Category:** Denial of Service
- **Component:** Docker Compose configuration
- **Description:** No resource limits (CPU or memory) are defined for any container. A single malfunctioning or attacked container can consume all available host resources, taking down the entire application stack.
- **Likelihood:** Medium
- **Impact:** Medium
- **Current State:** Not implemented (gap identified by review)
- **Recommended Fix:** Add `mem_limit` and `cpus` constraints to each service in docker-compose.yml.

---

### 5.3 Cloud Configuration Layer

---

**THREAT-010**
- **Category:** Information Disclosure
- **Component:** AWS S3 bucket policy
- **Description:** The S3 bucket has a public-read bucket policy allowing anyone on the internet to download any file using a direct S3 URL. This completely bypasses the application's authentication and authorization system.
- **Likelihood:** High (if URL is discovered)
- **Impact:** Critical
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Remove the public-read policy. Set block all public access at both the account and bucket level. Rely exclusively on presigned URLs generated by the authenticated backend.

---

**THREAT-011**
- **Category:** Elevation of Privilege
- **Component:** IAM role permissions
- **Description:** The IAM user used by the application has the AmazonS3FullAccess policy attached, granting s3:* permissions across all S3 resources in the account. If the credentials are compromised, an attacker can read, write, delete, and reconfigure any S3 bucket in the account, not just the CloudDrive bucket.
- **Likelihood:** Medium
- **Impact:** Critical
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Create a custom IAM policy scoped to only s3:GetObject and s3:PutObject on the specific CloudDrive bucket ARN. Apply the principle of least privilege.

---

**THREAT-012**
- **Category:** Information Disclosure
- **Component:** AWS credentials in .env file
- **Description:** AWS access keys are stored in a plaintext .env file on the host machine. If this file is accidentally committed to a public Git repository, or if the host machine is compromised, the credentials are immediately available to an attacker. The window between a key being pushed to GitHub and being discovered by automated scanners is measured in minutes.
- **Likelihood:** High
- **Impact:** Critical
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Use an IAM instance role attached to the EC2 instance instead of static credentials. The AWS SDK picks up instance role credentials automatically with no keys in any file.

---

**THREAT-013**
- **Category:** Tampering
- **Component:** EC2 security group
- **Description:** The EC2 security group allows inbound traffic on all ports from all IP addresses (0.0.0.0/0). This exposes internal services like PostgreSQL (port 5432) and Grafana (port 3000) directly to the internet.
- **Likelihood:** High
- **Impact:** High
- **Current State:** Intentionally vulnerable (documented)
- **Recommended Fix:** Restrict inbound rules to only port 80 and 443 from 0.0.0.0/0. All other ports should be inaccessible from the internet.

---

## 6. Threat Summary

| ID | Category | Layer | Likelihood | Impact | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| THREAT-001 | Spoofing | Application | High | High | Intentional vuln |
| THREAT-002 | Elevation of Privilege | Application | High | High | Intentional vuln |
| THREAT-003 | Elevation of Privilege | Application | Medium | High | Intentional vuln |
| THREAT-004 | Information Disclosure | Application | Medium | Medium | Design gap |
| THREAT-005 | Tampering | Application | Medium | Medium | Not implemented |
| THREAT-006 | Information Disclosure | Application | Medium | Low | Not verified |
| THREAT-007 | Elevation of Privilege | Container | Low | Critical | Intentional vuln |
| THREAT-008 | Elevation of Privilege | Container | Low | Critical | Intentional vuln |
| THREAT-009 | Denial of Service | Container | Medium | Medium | Not implemented |
| THREAT-010 | Information Disclosure | Cloud | High | Critical | Intentional vuln |
| THREAT-011 | Elevation of Privilege | Cloud | Medium | Critical | Intentional vuln |
| THREAT-012 | Information Disclosure | Cloud | High | Critical | Intentional vuln |
| THREAT-013 | Tampering | Cloud | High | High | Intentional vuln |

---

## 7. AI Generation Notes

The initial threat model structure and STRIDE categorization was generated with AI assistance. The following gaps were identified and added manually during review:

- THREAT-005 (file type and size limits) was not flagged by the AI initial pass and was added after manual review of the upload endpoint behavior
- THREAT-006 (error message information disclosure) was identified by manually testing the API with invalid inputs
- THREAT-009 (no container resource limits) was identified by reviewing the docker-compose.yml output and noticing the absence of any resource constraints
- The three-layer structure (application, container, cloud) was a deliberate design decision made before prompting the AI, based on the professor's example about how attackers do not always target the application directly
