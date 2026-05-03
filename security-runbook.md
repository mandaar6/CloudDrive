# Operational Runbook: Failed Security Tests

**Version:** 1.0
**Date:** April 2026
**Author:** Mandaar Rao

---

## 1. Overview

This runbook describes how to investigate, mitigate, and recover from failed security tests in CloudDrive. Each section maps to a specific test in the security testing document. A failed security test means a security control is no longer functioning — either a regression, a new vulnerability introduced by recent code changes, or a new CVE found in a dependency.

**How to use this runbook:** When a security test fails in GitHub Actions, the PR shows a red X. Click the failing job to see which test failed, then find the corresponding section below and follow Investigate, Mitigate, then Recover in order.

---

## 2. TEST-SEC-001 Failure: Rate Limiting Not Enforced

**What the test checks:** POST /api/auth/login returns HTTP 429 after 5 failed attempts within 60 seconds.

**What failure means:** Brute force attacks against login are no longer blocked.

### Investigate

```bash
# Verify flask-limiter is installed in the container
sudo docker compose exec backend pip show flask-limiter

# Check the rate limit decorator is on the login route
grep -n "limiter.limit" backend/app/auth.py

# Check limiter is initialized
grep -n "limiter" backend/app/__init__.py

# Reproduce manually
for i in $(seq 1 6); do
  curl -s -X POST http://localhost/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"test@test.com","password":"wrong"}' \
    -o /dev/null -w "Attempt $i: HTTP %{http_code}\n"
done
# If attempt 6 returns 200 instead of 429: rate limiting is broken
```

**Common causes:** flask-limiter removed from requirements.txt, decorator removed from login route, `limiter.init_app(app)` removed from `create_app()`.

### Mitigate

Block the failing PR from merging. If the running app is already unprotected, add an emergency nginx rate limit:

Add to nginx.conf inside `server {}`:
```
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
```

Add to the `/api/auth/login` location block:
```
limit_req zone=login burst=2 nodelay;
```

Then: `sudo docker compose exec nginx nginx -s reload`

### Recover

Restore the three required components, rebuild, and verify the test passes locally before pushing the fix:

```bash
sudo docker compose down && sudo docker compose up --build -d
python3 -m pytest backend/tests/test_security.py::test_rate_limiting -v
```

---

## 3. TEST-SEC-002 Failure: IDOR Prevention Broken

**What the test checks:** Authenticated user B cannot access user A's file using user A's file UUID.

**What failure means:** Any authenticated user can read any other user's files.

### Investigate

```bash
# Check ownership check is present in the download endpoint
grep -n "owner_id\|403\|Forbidden" backend/app/files.py | head -20

# Confirm manually with two test accounts
curl -s "http://localhost/api/files/{OTHER_USER_FILE_UUID}/download" \
  -H "Cookie: access_token=CURRENT_USER_TOKEN" \
  -w "\nHTTP: %{http_code}\n"
# Expected: 403. If 200: IDOR is active
```

**Common causes:** Ownership check removed from a file endpoint, new endpoint added without the check, login_required decorator missing.

### Mitigate

If unauthorized file access may have occurred, check Grafana for cross-user access patterns. Temporarily disable file endpoints if data exposure is confirmed:

Add to nginx.conf: `location /api/files/ { return 503; }`
Then: `sudo docker compose exec nginx nginx -s reload`

### Recover

Restore the ownership check in every file endpoint. Every endpoint that returns file data must verify `file.owner_id == current_user.id` OR an active FileShare record exists for the requesting user.

```bash
sudo docker compose down && sudo docker compose up --build -d
python3 -m pytest backend/tests/test_security.py::test_idor_prevention -v
```

---

## 4. TEST-SEC-003 Failure: JWT Token Not Revoked After Logout

**What the test checks:** A JWT token used after logout returns HTTP 401.

**What failure means:** Stolen or captured tokens remain valid for up to 24 hours after the user logs out.

### Investigate

```bash
# Check RevokedToken table exists and has entries
sudo docker compose exec db psql -U clouddrive -d clouddrive \
  -c "SELECT COUNT(*) FROM revoked_tokens;"

# Check the before_request hook
grep -n "RevokedToken\|check_revoked" backend/app/__init__.py

# Check logout inserts JTI
grep -n "RevokedToken\|jti" backend/app/auth.py

# Reproduce: log in, log out, try old token
curl -s http://localhost/api/files \
  -H "Cookie: access_token=OLD_TOKEN_AFTER_LOGOUT" \
  -w "\nHTTP: %{http_code}\n"
# Expected: 401. If 200: revocation is broken
```

**Common causes:** before_request hook removed, logout no longer inserts JTI, RevokedToken table dropped.

### Mitigate

Reduce JWT expiry as an emergency measure to limit the exposure window of unrevocable tokens:

In `.env`: change `JWT_EXPIRY_HOURS=24` to `JWT_EXPIRY_HOURS=1`

Then: `sudo docker compose restart backend`

### Recover

Restore all three revocation components. If the RevokedToken table was dropped, recreate it:

```bash
sudo docker compose exec backend python3 -c \
  "from app import create_app, db; app=create_app(); \
   ctx=app.app_context(); ctx.push(); db.create_all()"

python3 -m pytest backend/tests/test_security.py::test_jwt_revocation -v
```

---

## 5. TEST-SEC-004 Failure: File Extension Validation Missing

**What the test checks:** Requesting a presigned upload URL for a .exe file returns HTTP 400.

**What failure means:** Malicious executables and scripts can be uploaded to S3.

### Investigate

```bash
# Check allowlist exists in files.py
grep -n "ALLOWED_EXTENSIONS\|allowed\|extension" backend/app/files.py | head -10

# Test manually
curl -s "http://localhost/api/files/upload-url?filename=test.exe&content_type=application/octet-stream" \
  -H "Cookie: access_token=VALID_TOKEN" -w "\nHTTP: %{http_code}\n"
# Expected: 400. If 200: validation missing
```

### Mitigate

If dangerous files were uploaded during the outage, list and remove them from S3:

```bash
aws s3 ls s3://clouddrive-files-mxndi/uploads/ --recursive | \
  grep -iE "\.(exe|sh|bat|ps1|php)$"
# Remove any found: aws s3 rm s3://clouddrive-files-mxndi/uploads/path/to/file
```

### Recover

Restore the extension validation check in the `upload-url` endpoint. Rebuild and verify:

```bash
sudo docker compose down && sudo docker compose up --build -d
python3 -m pytest backend/tests/test_security.py::test_file_extension_validation -v
```

---

## 6. Trivy/pip-audit CVE Finding: Gunicorn Request Smuggling

**CVEs:** CVE-2024-1135, CVE-2024-6827 in gunicorn 21.2.0

**Current state:** Accepted risk, retained for CI/CD demonstration.

**When to act immediately:** If Grafana shows unexpected access to restricted endpoints, unusual 400/500 spikes, or if the CVE severity is upgraded to CRITICAL.

### Investigate

```bash
sudo docker compose logs nginx --tail=100 | grep -E "Transfer-Encoding|smuggl"
sudo docker compose logs backend --tail=100 | grep -E "ERROR|unexpected"
```

### Recover

```bash
# Upgrade gunicorn in requirements.txt
sed -i 's/gunicorn==21.2.0/gunicorn==22.0.0/' backend/requirements.txt

sudo docker compose down && sudo docker compose up --build -d

# Verify fix
sudo trivy image clouddrive-backend --severity HIGH,CRITICAL 2>/dev/null | grep gunicorn
```

---

## 7. ZAP Finding: Missing HTTP Security Headers

**Findings:** Missing CSP, X-Frame-Options, X-Content-Type-Options, server version disclosure.

### Investigate

```bash
curl -s -I http://localhost | grep -E "Content-Security|X-Frame|X-Content|Server"
# If these are absent: headers not configured
```

### Recover

Add to `nginx/nginx.conf` inside the `server {}` block:

```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://*.amazonaws.com;" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
server_tokens off;
```

Then reload nginx — no downtime required:

```bash
sudo docker compose exec nginx nginx -s reload
curl -s -I http://localhost | grep -E "X-Frame|Content-Security|Server"
```

---

## 8. General CI/CD Failure Procedure

1. Do not merge the PR — branch protection prevents merging when checks fail
2. Click the failing job in the GitHub Actions tab, read the full log
3. Reproduce the failure locally: `python3 -m pytest backend/tests/ -v`
4. Follow the relevant runbook section above
5. Push the fix to the same branch — GitHub Actions re-runs automatically
6. Only merge when all required checks pass

**Escalation — if failure indicates active exploitation (not just a code regression):**

1. Take affected endpoints offline immediately via nginx 503
2. Capture Grafana log evidence before any container restart
3. Identify affected users from the log pattern
4. Apply the code fix and restore service
5. Notify affected users if their data was accessed without authorization
