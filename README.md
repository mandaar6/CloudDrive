# CloudDrive

A secure cloud file storage and sharing platform built as a course 
project for Incident Response and Risk Management. CloudDrive 
demonstrates real-world security concepts across three vulnerability 
layers: application, container infrastructure, and cloud configuration.

## What it does

- User registration and login with bcrypt-hashed passwords and JWT auth
- File upload and download via AWS S3 with presigned URLs
- File sharing with configurable read or edit permissions
- Shared file indicators on the dashboard
- Operational logging via Grafana and Loki

## Architecture

- **Frontend:** React
- **Backend:** Flask (Python)
- **Database:** PostgreSQL
- **File storage:** AWS S3
- **Reverse proxy:** Nginx
- **Monitoring:** Grafana + Loki
- **Orchestration:** Docker Compose

## Running locally

### Prerequisites
- Docker and Docker Compose
- An AWS account with an S3 bucket
- An IAM user with S3 access

### Setup

1. Clone the repository:
   git clone https://github.com/mandaar6/CloudDrive.git
   cd CloudDrive

2. Copy the environment template:
   cp .env.example .env

3. Fill in your values in .env:
   - FLASK_SECRET_KEY: generate with `python3 -c "import secrets; 
     print(secrets.token_hex(32))"`
   - JWT_SECRET_KEY: generate the same way
   - POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB: set to any values,
     make sure DATABASE_URL matches
   - AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY: from your IAM user
   - S3_BUCKET_NAME: your bucket name
   - AWS_REGION: your bucket region

4. Start the application:
   docker compose up --build

5. Visit http://localhost

### Services
- Main app: http://localhost
- Grafana dashboard: http://localhost:3000 (admin/admin default)

## Intentional vulnerabilities (documented for course purposes)

| Vulnerability | Location | Purpose |
|---|---|---|
| No rate limiting on login | /api/auth/login | Enables brute force simulation |
| Sequential file IDs | Database | Enables IDOR attack demo |
| JWT tokens never revoked server-side | Auth system | Stolen token reuse scenario |
| App container runs as root | Dockerfile | Container privilege misconfiguration |
| AWS credentials in .env | Configuration | Secrets management failure |
| S3 bucket publicly readable | AWS | Cloud misconfiguration demo |
| IAM role has s3:* permissions | AWS IAM | Overprivileged access demo |

## Security documents

- [Threat Model](docs/threat-model.md)
- [Security Testing](docs/security-testing.md)
- [Gaps Analysis](docs/gaps-analysis.md)
