# Gaps to "Full CI/CD" — CloudDrive

**Author:** Kanishka J. Sharma
**Homework:** Week 6 / HW5
**Branch:** `kanishka-week-6-hw5`
**Pipeline file:** [.github/workflows/ci-cd.yml](.github/workflows/ci-cd.yml)

---

## 1. What this PR delivers

This pull request adds a baseline GitHub Actions pipeline (`ci-cd.yml`) for the CloudDrive backend. The pipeline runs on every push and pull request to any branch, plus manual `workflow_dispatch`, and contains five ordered stages:

| Stage | Job | Blocks deploy? |
|---|---|---|
| 1 | `lint` — `ruff` + `black --check` (advisory) | No |
| 2 | `test` — pytest with coverage on a Python 3.11 / 3.12 matrix | **Yes** |
| 3 | `sast` — Semgrep (OWASP Top 10) | No (advisory) |
| 3 | `dependency-scan` — `pip-audit` against `requirements.txt` | No (advisory) |
| 3 | `container-scan` — Trivy on the built backend image | No (advisory) |
| 4 (CD) | `publish-image` — build + push image to GHCR (only on `main`) | — |
| 5 (CD) | `deploy-staging` — placeholder for real deployment | — |

The PR also adds **10 new tests** (`tests/test_health.py`) covering the application factory, database connectivity, routing, and HTTP hardening; fixes 3 broken/erroring tests inherited from HW4 (JWT redirects + non-idempotent `auth_client` fixture under the rate limiter); makes `psycopg2-binary` install only on Python <3.14 (PEP 508 marker) so local Windows dev on Python 3.14 isn't blocked; and adds a `pytest.ini` so CI output stays focused on real signal.

Total tests: **27 passing** (was 14 passing / 3 failing / 2 erroring on HW4 main).

---

## 2. Why this is "Basic CI/CD" and not "Full CI/CD"

The pipeline gives us automated build, test, and image publication, but it stops short of a true **continuous-deployment** loop in several important ways. The gaps below are grouped by the lifecycle stage where they sit.

### 2.1 Source-control gaps

- **No required status checks on `main`.** GitHub Actions runs the workflow, but branch protection is not configured to *require* `test`, `sast`, or `dependency-scan` to pass before merge. Today a maintainer with write access can still force a merge through a red build.
- **No CODEOWNERS / required reviewers.** Any maintainer can self-merge. For a regulated GRC product this is a meaningful audit gap.
- **No automated `dependabot.yml`** for weekly dependency PRs. The `requirements.txt` already documents three accepted CVEs by hand; a Dependabot config would surface fixes proactively instead of relying on `pip-audit` after the fact.
- **No commit-signing enforcement** (DCO / signed commits). For security-critical infrastructure this is normally a baseline control.

### 2.2 Build / packaging gaps

- **Single-arch image only.** `publish-image` builds `linux/amd64`. Production fleets that include Graviton (`arm64`) need a `docker buildx` multi-arch matrix.
- **No SBOM and no image signing.** Full CI/CD pipelines emit a CycloneDX or SPDX SBOM (e.g., via Syft) and sign the published image with Cosign / Sigstore so consumers can verify provenance. Neither is wired up here.
- **No artifact versioning policy.** Images are tagged `:latest` and `:<short-sha>`. There is no semver release tag, no `:edge` channel, and no immutable release branch — making rollbacks ambiguous.

### 2.3 Test gaps

- **No true end-to-end tests against a running stack.** The Flask test client exercises route handlers in-process. There is no test that boots the actual `docker-compose.yml` (Postgres + S3 mock + nginx) and hits the API over HTTP. Network, TLS, CORS, and gunicorn config bugs all slip past today.
- **No frontend tests in CI.** The `clouddrive/frontend/` directory has no unit / component / Playwright tests in the workflow.
- **Coverage is reported but not gated.** The pipeline prints coverage but does not fail when it drops below a threshold (e.g., 70%). Today's coverage is **49%**, heavily weighted to auth; `app/files.py` is at 26%.
- **No mutation testing** (e.g., `mutmut`) — high line coverage can still mask weak assertions.
- **Security tests are partial.** They cover rate limiting, IDOR, JWT replay, file-extension validation, and email enumeration. There are no tests for CSRF, CSP headers, secure-cookie flags, or path-traversal in S3 keys.

### 2.4 Security-pipeline gaps

- **All scans are advisory (`exit-code: "0"` or `|| true`).** Semgrep, pip-audit, and Trivy report findings but never break the build. "Full CI/CD" would block on `HIGH`/`CRITICAL` and require an explicit allow-list (similar to the CVE comments already in `requirements.txt`).
- **No secret scanning.** GitHub native secret scanning + push protection are not enabled in this workflow, and there is no `gitleaks` or `trufflehog` step.
- **No DAST.** Once an image is deployed to staging, a tool like ZAP Baseline or Nuclei should hit the running app — none is configured.
- **No IaC scanning.** `docker-compose.yml` and the eventual Terraform / Helm chart should be scanned with `checkov` or `tfsec`.

### 2.5 Deployment gaps (the biggest gap)

- **There is no real deploy target.** `deploy-staging` is a placeholder job. A real CD step would:
  1. Authenticate to AWS / GCP / Azure with OIDC (no long-lived secrets).
  2. Run database migrations (`flask db upgrade`) gated behind a manual approval for prod.
  3. Roll the new image (`kubectl set image`, ECS `update-service`, or Helm upgrade) with a defined rollout strategy (blue/green or canary).
  4. Run smoke tests against the new revision before flipping traffic.
  5. Auto-rollback on smoke-test failure or SLO regression.
- **No environment promotion model.** Full CD uses environments (`dev` → `staging` → `prod`) with manual approval gates. We have one placeholder environment.
- **No infrastructure-as-code in this repo.** There is nothing for the pipeline to apply — no Terraform, no Helm chart, no CloudFormation. Real CD is impossible without this.
- **No feature flags.** Without flags, every deploy is a release. A LaunchDarkly / OpenFeature integration is needed to decouple the two.
- **No database migration safety net.** `app/__init__.py` calls `db.create_all()` for fresh dev environments. Production migrations through Flask-Migrate are not exercised in CI, so a migration bug only surfaces in production.

### 2.6 Observability + post-deploy gaps

- **No deploy markers in monitoring.** When the staging job runs we should emit a marker to Grafana / Loki / Datadog so operators can correlate deploys with regressions. The HW3 dashboard already exists; this pipeline does not talk to it.
- **No SLO-aware deploys.** "Full CI/CD" pauses promotion when an error-budget burn-rate alert is firing.
- **No automated rollback.** A failed health check after deploy should trigger a re-deploy of the previous tag — today there is no health check at all because there is no deploy.
- **No notifications.** The workflow does not post pass/fail to Slack, Teams, or email.

### 2.7 Compliance / governance gaps (relevant for GRC)

- **No tamper-evident build logs.** SLSA Level 3+ requires hermetic builds and provenance attestations (e.g., GitHub's `actions/attest-build-provenance`). Not enabled.
- **No change-management linkage.** A real CD pipeline writes a change record to ServiceNow / Jira on every prod deploy with the diff, the approver, and the test results. We have none.
- **No retention policy on artifacts.** `actions/upload-artifact@v4` defaults to 90 days. SOC 2 / ISO 27001 evidence collection should pin retention explicitly.

---

## 3. Prioritized roadmap to "Full CI/CD"

Rank ordered by `(risk reduction) / (effort)`:

| # | Gap | Effort | Why now |
|---|---|---|---|
| 1 | Make `test` a **required status check** on `main` and turn on branch protection | XS | Closes the "merge-while-red" loophole at zero cost. |
| 2 | Flip `pip-audit` and Trivy `HIGH`/`CRITICAL` to `exit-code: "1"` with an explicit allow-list | S | Forces the team to triage CVEs before merge instead of ad-hoc README comments. |
| 3 | Add `dependabot.yml` (weekly, grouped) | XS | Eliminates a whole class of stale-dependency findings. |
| 4 | Enable GitHub native secret scanning + push protection | XS | One-click control that catches the highest-impact mistake (committed credentials). |
| 5 | Provision a real staging environment (ECS Fargate or k8s) + Terraform in-repo + OIDC to cloud | L | Unlocks every later step; this is the single biggest gap. |
| 6 | Add real deploy + smoke-test job replacing the `deploy-staging` placeholder | M | Closes the loop between "image built" and "image running". |
| 7 | Cosign-sign the image and emit an SBOM | S | Required for SLSA-aligned supply-chain controls. |
| 8 | Add Playwright e2e job that boots `docker-compose` and hits the API | M | Catches the integration bugs unit tests cannot. |
| 9 | Add coverage threshold gate (start at 50%, raise quarterly) | XS | Cheap pressure to keep tests honest. |
| 10 | Wire deploy markers + Slack notifications into the existing Grafana/Loki stack | S | Reuses HW3 work; closes the observability loop. |

---

## 4. Acceptance criteria recap (HW5 grading)

| Criterion (5 pts each) | Where it lives in this PR |
|---|---|
| Basic CI/CD pipeline (GitHub Actions) | [`.github/workflows/ci-cd.yml`](.github/workflows/ci-cd.yml) — seven staged jobs with explicit `needs:` |
| Automated unit tests run in CI/CD | `test` job runs `pytest -v --cov=app` on Python 3.11 and 3.12 |
| Necessary updates to product / tests | New `tests/test_health.py` (10 tests); fixed `auth_client` fixture; fixed JWT redirect tests; PEP 508 marker on `psycopg2-binary` for Python 3.14 dev support; added `pytest.ini` |
| `.md` for gaps to "Full CI/CD" | This file (`cicd-gaps.md`) |