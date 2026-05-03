# Security Testing Documentation: CloudDrive

**Version:** 1.0
**Date:** April 2026
**Author:** Mandaar Rao

---

## 1. Overview

This document covers the security testing performed on CloudDrive across all three vulnerability layers: application, container infrastructure, and cloud configuration. Each test maps directly to a threat identified in the threat model. Tests include both manual testing performed against the running application and real automated tooling results from Trivy and Semgrep.

---

## 2. Testing Environment

| Item | Details |
| :--- | :--- |
| OS | Kali Linux |
| Application URL | http://localhost |
| Docker version | 29.4.0 |
| Docker Compose version | 2.40.3 |
| Browser | Firefox |
| Manual testing tools | Browser DevTools, curl |
| Automated SAST tool | Semgrep (community ruleset, owasp-top-ten) |
| Automated container scan | Trivy v0.x |

---

## 3. Application Layer Tests

---

### TEST-001: Brute Force Login (Maps to THREAT-001)

**Objective:** Confirm there is no rate limiting or account lockout on the login endpoint.

**Method:** Manual

**Steps:**
1. Register a test account at http://localhost/register
2. Run the following curl command 20 times rapidly with an incorrect password:
```
curl -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"abc@gmail.com","password":"wrongpassword"}'
```
3. On the 21st attempt use the correct password and observe whether login succeeds.

**Expected (secure) behavior:** Server should block or rate-limit after 5 to 10 failed attempts.

**Actual result:** All 20 failed attempts returned the same 401 response with no delay. The correct password on attempt 21 logged in successfully. No lockout, no CAPTCHA, no slowdown observed.

**Status:** VULNERABLE (intentional)

---

### TEST-002: Insecure Direct Object Reference on File Download (Maps to THREAT-002)

**Objective:** Confirm that an authenticated user can access another user's files by changing the file ID.

**Method:** Manual

**Steps:**
1. Log in as abc@gmail.com and upload a file. Note the file ID from the API response in the browser network tab.
2. Log out and log in as xyz@gmail.com.
3. Change the file ID in a download request to the ID belonging to abc@gmail.com.
4. Observe whether the file downloads successfully.

**Expected (secure) behavior:** Server should return 403 Forbidden.

**Actual result:** File downloaded successfully. The backend returned a valid presigned S3 URL without validating whether the requesting user had permission to access that file ID.

**Status:** VULNERABLE (intentional)

---

### TEST-003: JWT Token Reuse After Logout (Maps to THREAT-003)

**Objective:** Confirm JWT tokens remain valid after logout with no server-side revocation.

**Method:** Manual

**Steps:**
1. Log in as abc@gmail.com. Copy the JWT token from browser DevTools under Application > Cookies.
2. Log out of the application.
3. Make an authenticated API request using the copied token:
```
curl http://localhost/api/files \
  -H "Cookie: token=PASTE_TOKEN_HERE"
```

**Expected (secure) behavior:** Server should reject the token after logout with 401 Unauthorized.

**Actual result:** Server accepted the token and returned the full file list. Token remained valid for the full 30-day expiry regardless of logout action.

**Status:** VULNERABLE (intentional)

---

### TEST-004: File Type Validation on Upload (Maps to THREAT-005)

**Objective:** Confirm whether the upload endpoint validates file types or sizes.

**Method:** Manual

**Steps:**
1. Log in and attempt to upload a file with a .exe extension.
2. Attempt to upload an empty file.
3. Attempt to upload a file larger than 50MB.

**Expected (secure) behavior:** Server should reject executable types and enforce a size limit.

**Actual result:** All file types accepted without validation. No size limit enforced. The renamed .exe uploaded successfully and was stored in S3.

**Status:** VULNERABLE (gap, not intentional)

---

### TEST-005: Share Permission Enforcement (Maps to THREAT-004)

**Objective:** Confirm whether read and edit permissions produce different behavior.

**Method:** Manual

**Steps:**
1. Share test1.txt with xyz@gmail.com using read permission.
2. Share test2.txt with xyz@gmail.com using edit permission.
3. Log in as xyz@gmail.com and observe available actions for both files.

**Expected (secure) behavior:** Edit permission should allow re-upload. Read permission should allow download only.

**Actual result:** Both files showed only a download button regardless of permission level. The permission value is stored in the database but is not enforced at the API level or surfaced in the UI. Read and edit are functionally identical.

**Status:** VULNERABLE (gap, not intentional)

---

## 4. Container Infrastructure Layer Tests

---

### TEST-006: Container Running as Root (Maps to THREAT-007)

**Objective:** Confirm the Flask backend container runs as root.

**Method:** Manual

**Steps:**
```
docker compose exec backend whoami
```

**Expected (secure) behavior:** Output should be a non-root user such as `appuser`.

**Actual result:**
```
root
```

**Status:** VULNERABLE (intentional)

---

### TEST-007: Trivy Container Vulnerability Scan

**Objective:** Identify known CVEs in the CloudDrive backend Docker image.

**Method:** Automated (Trivy)

**Command run:**
```
sudo trivy image clouddrive-backend > trivy-output.txt 2>&1
```

**Summary of findings:**

```
clouddrive-backend (debian 13.4)
Total: 124 (UNKNOWN: 7, LOW: 85, MEDIUM: 23, HIGH: 9, CRITICAL: 0)

Python packages (python-pkg)
Total: 12 (UNKNOWN: 0, LOW: 2, MEDIUM: 6, HIGH: 4, CRITICAL: 0)
```

**Notable HIGH severity findings:**

| Library | CVE | Description | Fix Available |
| :--- | :--- | :--- | :--- |
| libncursesw6 | CVE-2025-69720 | Buffer overflow leading to arbitrary code execution | No fix available |
| libssl3t64 | CVE-2026-28390 | OpenSSL NULL pointer dereference causing denial of service | Yes (3.5.5-1~deb13u2) |
| libsystemd0 | CVE-2026-29111 | Arbitrary code execution via spurious IPC messages | No fix available |
| PyJWT 2.8.0 | CVE-2026-32597 | Accepts unknown `crit` header extensions violating RFC 7515 | Yes (upgrade to 2.12.0) |
| wheel 0.45.1 | CVE-2026-24049 | Privilege escalation via malicious wheel file | Yes (upgrade to 0.46.2) |
| jaraco.context 5.3.0 | CVE-2026-23949 | Path traversal via malicious tar archives | Yes (upgrade to 6.1.0) |

**Key observations:**
- No CRITICAL severity CVEs found, which is a positive result
- The 9 HIGH severity findings in the base Debian image are from system libraries (ncurses, OpenSSL, systemd) that are part of the base Python Docker image and not directly introduced by the application code
- The PyJWT vulnerability is directly relevant to CloudDrive since JWT is used for all authentication. Upgrading to 2.12.0 is the immediate recommended action
- The openssl HIGH finding has a fix available and the base image should be updated to pick it up

**Status:** FINDINGS IDENTIFIED

**Recommended actions:**
1. Upgrade PyJWT from 2.8.0 to 2.12.0 in requirements.txt
2. Pin the base Docker image to a specific digest and rebuild to pick up the OpenSSL fix
3. Add Trivy to the GitHub Actions CI/CD pipeline to fail builds on CRITICAL findings

---

### TEST-008: Semgrep Static Analysis (SAST)

**Objective:** Identify security issues in the Flask source code through static analysis.

**Method:** Automated (Semgrep)

**Command run:**
```
semgrep --config=p/owasp-top-ten backend/
```

**Full output summary:**
```
Scanning 7 files tracked by git with 544 Code rules

Language      Rules   Files
multilang         6       7
python          147       5
dockerfile        4       1

Findings: 1 (1 blocking)
Rules run: 157
Targets scanned: 7
```

**Finding:**

```
backend/Dockerfile
Rule: dockerfile.security.missing-user.missing-user
Severity: BLOCKING

By not specifying a USER, a program in the container may run as root.
This is a security hazard. If an attacker can control a process running
as root, they may have control over the container.

Autofix: USER non-root
Line 19: CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"]
```

**Observation:** Semgrep found exactly one blocking issue: the Dockerfile does not specify a non-root USER before the CMD instruction. This matches what was confirmed manually in TEST-006. The fact that Semgrep caught this automatically and flagged it as blocking demonstrates that automated SAST tooling would have caught this before deployment if it had been in the CI/CD pipeline from day one.

No other application-level findings were found in the Python source files, which means the Flask endpoints, auth logic, and file handling code did not contain patterns that match the OWASP Top 10 ruleset. This is a positive result for the application code layer, but does not replace manual testing since IDOR and missing rate limiting are logic flaws that static analysis cannot detect.

**Status:** 1 BLOCKING FINDING (intentional, documented)

---

## 5. Cloud Configuration Layer Tests

---

### TEST-009: S3 Public Access Verification (Maps to THREAT-010)

**Objective:** Confirm S3 files are accessible without authentication via direct URL.

**Method:** Manual

**Steps:**
1. Upload a test file and locate the object in the AWS S3 console.
2. Copy the direct object URL (not the presigned URL).
3. Open a private incognito browser window with no application session.
4. Paste the direct S3 URL into the browser.

**Expected (secure) behavior:** Direct S3 URL should return 403 Access Denied.

**Actual result:** File downloaded successfully in incognito with no authentication. The public-read bucket policy allows any HTTP GET request to any object. This was confirmed by opening the S3 URL on a completely separate Windows device with no application session or cookies.

**Status:** VULNERABLE (intentional)

---

### TEST-010: IAM Permission Scope Verification (Maps to THREAT-011)

**Objective:** Confirm the IAM user has overprivileged S3 access.

**Method:** Manual (AWS Console review)

**Steps:**
1. Navigate to IAM, Users, click on clouddrive-app user.
2. Review the Permissions tab for attached policies.

**Expected (secure) behavior:** Custom policy allowing only s3:GetObject and s3:PutObject on the specific bucket ARN.

**Actual result:** AmazonS3FullAccess is attached, granting s3:* permissions across all S3 resources in the entire AWS account.

**Status:** VULNERABLE (intentional)

---

### TEST-011: AWS Credentials Exposure Check (Maps to THREAT-012)

**Objective:** Verify AWS credentials are not committed to the Git repository.

**Method:** Manual

**Steps:**
```bash
cat .gitignore | grep .env
git log --all --full-history -- .env
cat .env.example | grep AWS
```

**Actual result:** .env is in .gitignore. Git history shows no .env commits. .env.example contains only placeholder strings. Credentials exist only on the local machine.

**Note:** During initial project setup, AWS credentials were briefly visible in a chat session before .gitignore was configured. The affected keys were immediately rotated. This real incident is documented as a concrete example of how credential exposure happens in practice, even when the developer is security-aware.

**Status:** PASS

---

## 6. CI/CD Pipeline Security Checks

The GitHub Actions pipeline runs the following automatically on every push:

| Check | Tool | Blocks Merge |
| :--- | :--- | :--- |
| Unit tests | pytest | Yes, on test failure |
| Static analysis | Semgrep (owasp-top-ten) | Yes, on blocking findings |
| Container scan | Trivy | Yes, on CRITICAL findings |
| Build validation | Docker Compose | Yes, on build failure |

---

## 7. Test Summary

| Test ID | Description | Layer | Result |
| :--- | :--- | :--- | :--- |
| TEST-001 | Brute force login | Application | VULNERABLE (intentional) |
| TEST-002 | IDOR on file download | Application | VULNERABLE (intentional) |
| TEST-003 | JWT token reuse after logout | Application | VULNERABLE (intentional) |
| TEST-004 | File type validation | Application | VULNERABLE (gap) |
| TEST-005 | Share permission enforcement | Application | VULNERABLE (gap) |
| TEST-006 | Container running as root | Container | VULNERABLE (intentional) |
| TEST-007 | Trivy container scan | Container | 9 HIGH, 0 CRITICAL found |
| TEST-008 | Semgrep SAST | Application | 1 BLOCKING finding |
| TEST-009 | S3 public access | Cloud | VULNERABLE (intentional) |
| TEST-010 | IAM overprivileged role | Cloud | VULNERABLE (intentional) |
| TEST-011 | AWS credentials in Git | Cloud | PASS |

---

## 8. AI Generation Notes

The test structure and mapping to the threat model were initially generated with AI assistance. The following were added or modified manually:

- All actual test results were written based on real observations from running the application and executing the tests described
- TEST-007 and TEST-008 results reflect real Trivy and Semgrep output from scanning the actual project
- TEST-004 and TEST-005 were not in the AI initial test plan and were added after manually exploring the running application
- The credentials exposure note in TEST-011 documents a real incident that occurred during project setup
- The PyJWT HIGH finding in TEST-007 was identified as directly relevant to the application and prioritized accordingly
