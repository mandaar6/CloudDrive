# CI/CD Gaps Analysis: Getting to Full CI/CD

**Version:** 1.0 | **Date:** May 2026 | **Author:** Mandaar Rao

---

## 1. Overview

This document describes the gap between the current CI/CD pipeline for CloudDrive and what a production-grade pipeline would look like at a company like Google, Stripe, or Dropbox. The current pipeline is a solid starting point. It runs tests, scans dependencies, and scans container images automatically on every push. But several important capabilities are missing before this pipeline could be trusted to ship software to real users without any manual steps.

---

## 2. What the Current Pipeline Does

The GitHub Actions pipeline in `.github/workflows/ci.yml` runs four jobs automatically on every push and every pull request:

| Job | Tool | What it checks |
| :--- | :--- | :--- |
| Run Tests | pytest | 26 functional and security tests |
| Static Analysis | Semgrep | OWASP Top 10 code patterns |
| Dependency Scan | pip-audit | Known CVEs in Python packages |
| Container Scan | Trivy | Known CVEs in Docker image |

All four jobs run in parallel. The Run Tests job blocks a PR from merging if any test fails. The other three jobs report findings but do not currently block merges.

**What changed this sprint:** The test suite grew from 18 to 26 tests. Eight new tests were added across two new test classes. One real bug was also found and fixed in the process.

---

## 3. What Changed in the Product This Sprint

### New tests added

**TestHealthAndEdgeCases (in test_functional.py):**

Five new functional tests covering edge cases that were previously untested:

- Login with the wrong password returns 401
- Login with an empty request body returns 400
- Registration with a missing password field returns 400
- The shares endpoint rejects unauthenticated requests with 401
- The folders endpoint rejects unauthenticated requests with 401

**TestSecurityHeaders (in test_security.py):**

Three new security tests:

- Every response from the app includes a Content-Type header
- Sending a SQL injection string as the email field returns 400 or 401, never a 500 server crash
- Sending a 10,000 character string as the email field returns 400 or 401, never a 500 server crash

The SQL injection and long input tests verify that the application handles malicious or unusual input gracefully without crashing. A 500 error on an injection attempt is a signal that the input reached the database layer, which is worth catching even if SQLAlchemy's ORM protects against actual data extraction.

### Real bug found and fixed during testing

When writing the test for missing login fields, Claude Code discovered that submitting an empty JSON body to the login endpoint returned 401 instead of 400. This happened because the login route was reading the email and password fields, getting None for both, and then running the constant-time invalid credentials check rather than rejecting the request early with a validation error.

The register endpoint already had this guard. The login endpoint did not. Claude Code added the same early validation check to login. This is a real code quality fix that came directly from writing tests, which is exactly the value automated tests are supposed to provide.

### Rate limiter behavior discovered

While writing the SQL injection and long input tests, a subtle issue appeared with flask-limiter 3.12. The rate limiter caches its enabled or disabled state at startup and does not respond to runtime config changes. This meant that after the brute force test exhausted the rate limit counter for the loopback IP address, all subsequent tests from the same IP were rate-limited regardless of what they were testing.

The fix was to assign different fake IP addresses to each test class using Werkzeug's `environ_overrides` parameter. This keeps the rate limit buckets isolated between test classes so they do not interfere with each other.

---

## 4. Gaps in the Current CI Pipeline

### GAP-CI-001: Security Scans Do Not Block Merges

**Current state:** Semgrep, pip-audit, and Trivy all run and show their findings, but they are configured with `exit-code: 0`. This means even if they find HIGH severity vulnerabilities, the pipeline still shows green and the PR can be merged.

**Why this matters:** A CI pipeline that reports vulnerabilities without blocking is really just a dashboard. Developers learn to ignore it because it always passes. Real teams configure severity thresholds that block merges when CRITICAL findings appear.

**What full CI/CD does:** Sets Trivy to `exit-code: 1` for CRITICAL findings. Configures Semgrep to fail on ERROR severity. Blocks merges until findings are resolved or explicitly documented as accepted risk.

**Why not done yet:** CloudDrive currently has known HIGH severity CVEs in gunicorn 21.2.0 and flask 3.0.3 that are retained intentionally to demonstrate the CI detection pipeline. Setting a CRITICAL threshold would allow these through while still catching any new critical issues introduced by future changes. This is the immediate next configuration step.

---

### GAP-CI-002: No Code Coverage Threshold

**Current state:** pytest runs 26 tests but there is no measurement of what percentage of the application code is actually being exercised. The pipeline does not know whether the tests cover 30% or 80% of the codebase.

**Why this matters:** Tests that only cover the happy path give a false sense of security. Error handling code, edge cases, and security-critical paths may be completely untested. Without a coverage threshold, a developer can add new features with zero tests and the pipeline still passes.

**What full CI/CD does:** Runs pytest with the coverage plugin, then fails the build if coverage drops below a defined threshold. Most teams start at 60% and raise it over time.

```yaml
- name: Run tests with coverage
  run: |
    pytest tests/ -v --tb=short \
      --cov=app \
      --cov-report=xml \
      --cov-fail-under=60
```

**Estimated current coverage:** Based on reviewing which endpoints and code paths the 26 tests actually call, coverage is roughly 35 to 40 percent. The tests cover the main auth and file endpoints but do not touch error handlers, the Secrets Manager fallback logic, email failure paths, or most of the folder management code.

---

### GAP-CI-003: No Automated Deployment (Missing the CD)

**Current state:** The pipeline runs tests and scans but never deploys anything. After a successful merge to main, a developer still has to manually SSH into the server and run `docker compose up --build`.

**Why this matters:** Manual deployment is one of the biggest sources of production incidents. People skip steps under pressure, deploy the wrong branch, or forget to restart a service. The D in CI/CD means deployment is also automated and repeatable.

**What full CI/CD does:** After all tests pass and the PR merges to main, a deployment job automatically builds the Docker images, pushes them to a container registry, connects to the production server, pulls the new images, restarts the containers, runs a smoke test, and rolls back if the smoke test fails.

**Why not done yet:** CloudDrive has not been deployed to EC2. There is no container registry, no production server to deploy to, and no health check endpoint for smoke testing. All of these are required before CD can be implemented.

---

### GAP-CI-004: No Health Check Endpoint

**Current state:** The application has no `/api/health` endpoint. There is no way for an automated system to verify the application is alive and responding correctly after a deployment.

**Why this matters:** Without a health check, a CD pipeline can only verify that the containers started. It cannot verify they are actually serving requests. A bug that causes the app to start but immediately fail on the first database query would go undetected.

**What full CI/CD does:** The health endpoint returns a JSON response confirming the app is running, the database is reachable, and critical external services like S3 are accessible. The CD pipeline hits this endpoint after every deployment and fails the deployment if it does not return 200.

```python
@app.route("/api/health")
def health():
    checks = {}
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"
    return jsonify({
        "status": "healthy" if all(v == "ok" for v in checks.values()) else "degraded",
        "checks": checks
    })
```

---

### GAP-CI-005: No Container Registry or Image Versioning

**Current state:** Docker images are built locally on the developer machine. There is no central registry where built images are stored and versioned. Every deployment requires rebuilding from scratch.

**Why this matters:** Without a registry, there is no reliable record of exactly which version of the code is running in production. There is no way to roll back to a previous known-good image quickly during an incident.

**What full CI/CD does:** Every successful merge to main builds a Docker image and pushes it to Amazon ECR tagged with the git commit SHA. Deployments reference specific tags rather than rebuilding from source. Rolling back is as simple as pointing to a previous tag.

---

### GAP-CI-006: No Integration Tests

**Current state:** All 26 tests are unit tests. They use an in-memory SQLite database and mock out all external dependencies. None of them test the actual interaction between Flask, PostgreSQL, and S3.

**Why this matters:** Many bugs only appear when real services talk to each other. A good example from this project is the SQLAlchemy UUID handling difference between SQLite and PostgreSQL that required workarounds in the test setup. Unit tests would never catch a bug that only appears with real PostgreSQL.

**What full CI/CD does:** Runs a separate integration test job that spins up real PostgreSQL and a mock S3 using LocalStack as Docker service containers inside GitHub Actions, then runs tests against the real stack.

---

### GAP-CI-007: No Automated Dynamic Security Testing

**Current state:** OWASP ZAP was run manually once against the running application. The 8 findings (missing security headers, clickjacking vulnerability, server version disclosure) were documented. ZAP does not run automatically in the pipeline.

**Why this matters:** If a future code or configuration change re-introduces one of these findings, the pipeline would not catch it because ZAP is not automated. Static analysis (Semgrep) checks code patterns but cannot find issues that only appear when the app is actually running and responding to HTTP requests.

**What full CI/CD does:** Runs a ZAP baseline scan automatically against a staging deployment as part of the pipeline. Any new findings above the severity threshold fail the pipeline before the code reaches production.

---

## 5. Roadmap to Full CI/CD

Ordered by effort and immediate impact:

| Priority | Gap | Effort | What it unblocks |
| :--- | :--- | :--- | :--- |
| 1 | Add health check endpoint | 1 hour | Required for CD smoke testing |
| 2 | Set Trivy exit-code to 1 for CRITICAL | 5 minutes | Makes container scan actually enforce |
| 3 | Add code coverage with 60% threshold | 30 minutes | Catches untested new code |
| 4 | Store real secrets in GitHub Actions Secrets | 30 minutes | Required for production deployment |
| 5 | Deploy to EC2 with IAM instance role | 1 day | Enables the CD half of CI/CD |
| 6 | Push images to Amazon ECR | 2 hours | Enables fast rollback |
| 7 | Add integration tests with real PostgreSQL | 1 day | Catches database-specific bugs |
| 8 | Automate ZAP in staging pipeline | 2 hours | Catches security regressions automatically |

---

## 6. What Full CI/CD Looks Like for CloudDrive

The complete pipeline for a production CloudDrive deployment would look like this:

```
Code merged to main
        |
        v
Stage 1: Validate (runs in parallel, about 3 minutes)
  - pytest with 60% coverage threshold
  - Semgrep blocks on ERROR severity
  - pip-audit blocks on CRITICAL CVEs
  - Trivy blocks on CRITICAL CVEs
        |
        v
Stage 2: Build (about 2 minutes)
  - Build Docker images
  - Push tagged images to Amazon ECR
        |
        v
Stage 3: Deploy to Staging (about 1 minute)
  - Pull new images to staging EC2
  - Restart containers
  - Smoke test against /api/health
        |
        v
Stage 4: Integration and Security Testing (about 5 minutes)
  - Run integration tests against staging
  - Run ZAP baseline scan against staging
        |
        v
Stage 5: Deploy to Production (about 1 minute)
  - Pull new images to production EC2
  - Restart containers
  - Smoke test against /api/health
  - Alert on-call via Grafana if anything fails
        |
Total: about 12 minutes from merge to production
```

The current pipeline completes Stage 1 partially. Stages 2 through 5 do not exist yet. The gap between current state and this full pipeline is roughly 2 to 3 weeks of engineering work, primarily because deploying to EC2 and building a staging environment require infrastructure that has not been set up for this project yet.

---

## 7. AI Generation Notes

The structure of this document was generated with AI assistance. The following were written manually or based on direct observation:

- The bug discovered and fixed during test writing (empty login body returning 401 instead of 400) is a real finding that occurred while writing tests, not a hypothetical example
- The rate limiter IP isolation issue with flask-limiter 3.12 was a real problem encountered during test development and is documented here because it reveals a non-obvious behavior of the library that future contributors should know about
- The coverage estimate of 35 to 40 percent is based on manually reviewing which endpoints the 26 tests actually exercise
- The roadmap priorities are based on what was actually attempted and learned during development, not generated generically
