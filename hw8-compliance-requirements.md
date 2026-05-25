# CloudDrive Compliance Requirements

This document outlines the specific compliance requirements CloudDrive must adhere to, categorized into People Controls (Privacy) and Technical Controls (Security).

## 1. People Controls (Data Privacy)

### General Data Protection Regulation (GDPR)
GDPR is the European Union's data privacy law, considered the strictest global standard. Due to extraterritoriality, CloudDrive must comply if it serves any EU residents.
*   **Official Source:** [GDPR Official Text (Interinstitutional File: 2012/0011)](https://gdpr-info.eu/)
*   **Article 17 (Right to Erasure):** Also known as the "Right to be Forgotten." Users must have the ability to permanently delete their personal data and account without undue delay. CloudDrive meets this by providing a "Delete Account" button that wipes the database record and S3 objects.
*   **Article 5 (Data Minimization):** Personal data collected must be adequate, relevant, and limited to what is strictly necessary. CloudDrive meets this by cryptographically hashing user emails in operational logs so PII is not stored unnecessarily.
*   **Article 7 (Conditions for Consent):** A user's consent must be freely given, specific, informed, and unambiguous. CloudDrive meets this by forcing users to check an explicit Privacy Policy consent box before registration.

### California Consumer Privacy Act (CCPA)
The CCPA is the United States' most stringent state-level privacy law.
*   **Official Source:** [California Attorney General CCPA Guidelines](https://oag.ca.gov/privacy/ccpa)
*   **Section 1798.105 (Right to Delete):** Consumers have the right to request the deletion of personal information collected from them. CloudDrive complies via the hard-delete account endpoint.

---

## 2. Technical Controls (Security & Operations)

### SOC 2 (System and Organization Controls 2)
Developed by the AICPA, SOC 2 evaluates an organization's information systems relevant to security, availability, processing integrity, confidentiality, and privacy.
*   **Official Source:** [AICPA Trust Services Criteria (TSC)](https://www.aicpa-cima.com/resources/article/trust-services-and-information-security)
*   **CC6.1 (Logical Access Security):** The system must implement logical access controls to prevent unauthorized access. CloudDrive complies by using JWT authentication with http-only cookies.
*   **CC7.2 (Security Monitoring):** The system must continuously monitor for anomalies and track security events. CloudDrive complies by streaming Docker logs via Promtail to Loki, tracking all successful and failed authentication attempts (using hashed user IDs to avoid clashing with GDPR).

### NIST Cybersecurity Framework (CSF)
A set of guidelines for mitigating organizational cybersecurity risks, created by the US Government.
*   **Official Source:** [NIST Cybersecurity Framework Official Documentation](https://www.nist.gov/cyberframework)
*   **PR.AC-5 (Network Integrity):** Network protections must be implemented to protect against threats. CloudDrive complies by enforcing strict HTTP Security Headers (Content-Security-Policy, X-Frame-Options) in the Nginx reverse proxy to prevent XSS and clickjacking.

### ISO/IEC 27001
The international standard for Information Security Management Systems (ISMS).
*   **Official Source:** [ISO/IEC 27001 Information Security Management](https://www.iso.org/isoiec-27001-information-security.html)
*   **Annex A.12.4 (Logging and Monitoring):** Event logs recording user activities, exceptions, faults, and information security events must be produced and securely retained. CloudDrive meets this via the Loki/Grafana stack.

---

## 3. Future Scope Compliance

As CloudDrive scales and targets new markets or introduces paid features, the following regulatory frameworks must be evaluated for implementation:
*   **Health Insurance Portability and Accountability Act (HIPAA):** Required if CloudDrive is marketed to healthcare providers or businesses to store Protected Health Information (PHI).
*   **Payment Card Industry Data Security Standard (PCI-DSS):** Required if CloudDrive introduces premium paid tiers and processes user credit card transactions.
*   **Family Educational Rights and Privacy Act (FERPA):** Required if CloudDrive is adopted by educational institutions (schools/colleges) for storing student records.
*   **Children's Online Privacy Protection Act (COPPA):** Required if CloudDrive intentionally targets users under the age of 13.
*   **Federal Risk and Authorization Management Program (FedRAMP):** Required if CloudDrive intends to offer services to United States federal government agencies.
