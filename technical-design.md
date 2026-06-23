# Technical Design Document: CloudDrive

**Status:** Initial Architecture

**Version:** 0.1.0

**Name:** Mandaar Rao (2578362)

---

## 1. Overview

**CloudDrive** is a secure, cloud-native file storage and sharing web application. Think of it as a simplified Dropbox built with security operations in mind from day one. Users can sign up, upload files, and share them with configurable access permissions. Files are stored in AWS S3, access is managed through short-lived presigned URLs, and every meaningful user action is logged to an operational dashboard for monitoring and incident response.

The project is intentionally designed with vulnerabilities planted at three distinct layers: the application layer, the container infrastructure layer, and the cloud configuration layer. This makes it a realistic platform for practicing threat modeling, security testing, compliance mapping, and incident response rather than a sanitized academic exercise.

---

## 2. Motivation

The question this project asks is: "What does it actually look like to secure a real product end to end, from the code all the way up to the cloud?"

Most security exercises focus on a single layer. A CTF challenge targets one vulnerability. A pen test report covers application weaknesses. But production systems fail across multiple layers simultaneously, and defenders need to think that way too.

CloudDrive was designed with the following goals:

- **Realism:** The product itself (file storage and sharing) is something everyone understands. The security concepts map directly to what real engineering teams deal with every day.
- **Layered attack surface:** Vulnerabilities are planted at the app, container, and cloud levels to reflect how production systems actually get compromised. An attacker does not always go through the front door.
- **Operational visibility:** An observability dashboard runs alongside the product, giving a simulated SOC view of what is happening inside the system at all times.
- **Cloud learning:** The project uses AWS S3 and IAM in a way that teaches the fundamentals of cloud security without requiring deep cloud expertise to get started.

---

## 3. Project Components and Requirements

### 3.1 Web Application (App Container)

- **Framework:** Flask (Python) backend with a React frontend.
- **Purpose:** The main product that users interact with. Handles authentication, file operations, and sharing logic.
- **Core endpoints:**
  - `POST /auth/register` and `POST /auth/login` for user management
  - `POST /files/upload` and `GET /files/download/:id` for file operations
  - `POST /files/share` to grant another user access to a file
  - `GET /files` to list the authenticated user's files

### 3.2 Authentication and User Management

- **Password storage:** bcrypt with automatic salting. The plaintext password is never stored or logged.
- **Session management:** JWT tokens issued on login, sent as an HTTP-only cookie. Tokens carry the user ID and expiry claim.
- **Intentional weakness (documented):** Tokens are set with a very long expiry and there is no rate limiting on the login endpoint, making brute force and session hijacking viable attack scenarios for the incident walkthrough.

### 3.3 File Storage (AWS S3)

- **Storage:** All uploaded files live in a private S3 bucket. Each file is stored under a key formatted as `uploads/{user_id}/{uuid}/{filename}`.
- **Access:** Files are never served directly from S3 to the user. The backend generates a presigned URL (valid for one hour) and redirects the user to it. This means users never need AWS credentials of their own.
- **Encryption:** S3-managed AES-256 encryption at rest is enabled on the bucket (SSE-S3). All traffic between the backend and S3 goes over TLS.
- **Intentional weakness (documented):** The bucket policy is misconfigured to allow public read access, and the IAM role used by the app has `s3:*` permissions instead of least-privilege `s3:GetObject` and `s3:PutObject`.

### 3.4 Database (PostgreSQL Container)

- **Storage:** PostgreSQL running in its own container. Stores user accounts, file metadata, and sharing records. The actual file bytes never touch the database.
- **Schema (three tables):**

```
users        -> id, email, username, password_hash, created_at, is_active
files        -> id, owner_id, filename, s3_key, size_bytes, uploaded_at, is_deleted
file_shares  -> id, file_id, shared_with_email, permission (read | edit), expires_at
```

### 3.5 Observability Dashboard (OE Container)

- **Stack:** Grafana and Loki running in a dedicated container.
- **Purpose:** A SOC-style operational dashboard showing login attempts, file access events, sharing activity, and anomaly alerts in near real time.
- **Log sources:** The Flask app ships structured JSON logs to Loki. Grafana queries Loki and renders the dashboards.
- **Key panels:** Failed login attempts over time, file download volume per user, sharing activity feed, and a triggered-alerts list.

### 3.6 Reverse Proxy (Nginx Container)

- **Purpose:** Sits in front of the Flask app and handles TLS termination. Users connect to `https://yourdomain.com` and Nginx forwards traffic to the Flask container on port 5000 internally.
- **Why this matters:** Users never interact with Flask directly. This is standard production practice and provides a realistic network boundary to discuss in the threat model.

### 3.7 CI/CD Pipeline (GitHub Actions)

- Runs automatically on every push to the repository.
- **Pipeline steps:**
  1. Unit tests with pytest
  2. Static analysis (SAST) with Semgrep targeting OWASP Top 10 patterns
  3. Container image vulnerability scan with Trivy
  4. Docker Compose build validation to catch configuration errors early

---

## 4. Out of Scope

To keep the project completable within the course timeline, the following are not included in this version:

- **Email verification and password reset:** Users are created and managed directly. A real product would require email confirmation flows.
- **Mobile application:** The frontend is a web app only. A mobile client would not add meaningful security coverage for this course.
- **Real-time collaboration:** File sharing is permission-based access, not concurrent editing. Google Docs-style real-time editing is out of scope.
- **Virus and malware scanning of uploads:** Uploaded files are not scanned before being stored. This is noted as a gap in the compliance document.
- **Multi-region redundancy:** The deployment runs in a single AWS region on a single EC2 instance. High availability is not a requirement for this course.

---

## 5. Practical Technical Decisions

### 5.1 Technology Stack and Rationale

| Decision | Choice | Rationale |
| :--- | :--- | :--- |
| **Backend** | Python / Flask | Lightweight, well-supported, and fast to generate with AI tooling. Strong bcrypt and JWT library support. |
| **Frontend** | React | Fast to scaffold, component-based, and reliable when generated with AI assistance. |
| **Database** | PostgreSQL | Provides real relational integrity for the user/file/share model. More realistic than SQLite for a multi-user product. |
| **File storage** | AWS S3 | Industry standard. Teaches IAM, bucket policies, and presigned URLs, which are core cloud security concepts. |
| **Log management** | Grafana + Loki | Open source, runs in Docker, and requires no external accounts. Gives a realistic SOC dashboard without building one from scratch. |
| **CI/CD** | GitHub Actions | Free, tightly integrated with GitHub, and has pre-built actions for Semgrep and Trivy. |

### 5.2 Tradeoff Decisions

1. **Flask over Django:**
   - *Decision:* Flask is used instead of the more complete Django framework.
   - *Reason:* Flask gives more control over the authentication flow, which matters because the intentional weaknesses in the auth system need to be deliberate and visible. Django's built-in auth would hide too much of the implementation detail.

2. **Presigned URLs over a file proxy:**
   - *Decision:* Downloads redirect to a short-lived S3 presigned URL rather than streaming the file through the Flask backend.
   - *Reason:* This is how production systems like Dropbox and Google Drive actually work. It also introduces a realistic security tradeoff worth documenting: a captured presigned URL works for anyone for up to one hour, regardless of their session state.

3. **Intentional vulnerabilities documented rather than hidden:**
   - *Decision:* All planted weaknesses are listed explicitly in the threat model and security testing documents rather than left as hidden traps.
   - *Reason:* The goal of the project is to practice detection and response. Documenting what is broken, why it is broken, and what the correct fix would be demonstrates more understanding than simply leaving vulnerabilities in place without analysis.

4. **Single EC2 instance over ECS or Kubernetes:**
   - *Decision:* Docker Compose on a single EC2 t2.micro instance rather than a managed container service.
   - *Reason:* Keeps AWS costs within the free tier and avoids introducing ECS or EKS complexity that is not necessary for the course objectives. The security concepts around IAM roles, security groups, and network exposure apply equally at this scale.

---

## 6. Intentional Vulnerability Summary

| Layer | Vulnerability | Purpose |
| :--- | :--- | :--- |
| Application | No rate limiting on `/auth/login` | Enables brute force simulation for incident walkthrough |
| Application | File IDs are sequential integers, not UUIDs | Enables IDOR (Insecure Direct Object Reference) attack demo |
| Application | JWT tokens have no server-side expiry enforcement | Enables stolen token reuse scenario |
| Container | App container runs as root user | Demonstrates container privilege misconfiguration |
| Container | Docker socket mounted inside app container | Demonstrates container escape vector |
| Cloud | S3 bucket policy set to public-read | Demonstrates cloud misconfiguration and data exposure |
| Cloud | IAM role granted `s3:*` instead of least privilege | Demonstrates overprivileged cloud access |
| Cloud | AWS credentials hardcoded in `.env` file | Demonstrates secrets management failure |

---

## 7. Architecture Diagram

```
[ Browser ]
     |
     | HTTPS
     v
[ Nginx Container ]               <-- TLS termination, reverse proxy
     |
     v
[ Flask App Container ] <-------> [ PostgreSQL Container ]
     |                                (users, files, shares metadata)
     |
     +------> [ AWS S3 ]              (file storage, AES-256 at rest)
     |
     +------> [ Grafana + Loki Container ]    (logs, alerts, OE dashboard)
     |
     +------> [ GitHub Actions ]      (CI/CD: pytest, Semgrep, Trivy)

AWS Account (one account, managed by project owner):
  - S3 Bucket      : clouddrive-files
  - IAM Role       : clouddrive-app-role (assumed by EC2 instance)
  - EC2 Instance   : t2.micro, runs all containers via Docker Compose
  - Security Group : ports 80 and 443 exposed (intentionally misconfigured
                     to allow all ports from 0.0.0.0/0 for demo purposes)
```
