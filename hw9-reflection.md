# HW9 Incident Reflection: Leaked JWT Secret

### 1. Were the steps in your runbook easy to follow and understand?
Yes, the steps were intentionally designed to be executed during a high-stress, Severity-1 security emergency. Instead of vague guidelines like "Rotate the secret," the runbook provided the exact terminal commands required to generate a cryptographically secure 64-character hex string (e.g., `python -c "import secrets..."`) and explicitly stated the Docker command needed to reload the backend without bringing down the database. This eliminated guesswork and reduced the Time to Recover (TTR).

### 2. Can you simplify your runbook further?
The manual generation of the key and the manual editing of the `.env` file using a text editor (`nano`) introduces room for human error (e.g., a typo while pasting). This could be simplified by writing a single bash script (e.g., `rotate-jwt.sh`) that automatically generates the key, safely injects it into the `.env` file, and triggers the Docker restart in one action.

### 3. Any steps in your runbook that should be automated further?
In an enterprise cloud environment, the entire concept of manually editing a `.env` file should be automated away. We should migrate the `JWT_SECRET_KEY` from a static `.env` file into a centralized enterprise vault (like HashiCorp Vault or AWS Secrets Manager). The CI/CD pipeline would then automatically fetch the secret during deployment. If a leak is detected by GitHub Advanced Security, an automated webhook could theoretically trigger a rotation in the Vault and redeploy the backend automatically, achieving a "Zero-Touch" recovery.

### 4. Any automated steps in your runbook that need manual supplementation?
The detection phase is highly automated (GitHub Advanced Security secret scanning automatically fires an alert when a regex pattern matching a secret is committed). However, this automated step strictly requires manual supplementation: an SRE must manually verify if the leaked string is the *actual* production key or just a harmless dummy string used in a testing file. If we fully automated the rotation based purely on the scanner, a developer committing a fake test key could accidentally trigger a global logout for millions of legitimate users.
