# Compliance Requirements for CloudDrive

## Overview
CloudDrive is a file upload/download application with a Flask backend that stores user files in cloud storage (AWS S3). As a cloud file storage product, it is subject to multiple regulatory frameworks.

## Applicable Regulations

### 1. GDPR (General Data Protection Regulation)
- Applies because CloudDrive stores files that may contain personal data from EU users.
- Requires data minimization, right to erasure, and explicit user consent for data processing.
- Source: https://gdpr-info.eu/

### 2. CCPA (California Consumer Privacy Act)
- Applies if any California residents use the product.
- Users must have the right to know, delete, and opt out of sale of their personal data.
- Source: https://oag.ca.gov/privacy/ccpa

### 3. HIPAA (Health Insurance Portability and Accountability Act)
- Applies if any uploaded files contain Protected Health Information (PHI).
- Requires encryption at rest and in transit, access controls, and audit logs.
- Source: https://www.hhs.gov/hipaa/index.html

### 4. SOC 2 (Service Organization Control 2)
- Industry standard for SaaS/cloud products covering Security, Availability, and Confidentiality.
- Requires documented security policies, access controls, and incident response.
- Source: https://www.aicpa-cima.com/resources/landing/soc-2

### 5. NIST Cybersecurity Framework
- Provides best practices for identifying, protecting, detecting, responding, and recovering from cyber incidents.
- Source: https://www.nist.gov/cyberframework

## Key Technical Requirements
- HTTPS/TLS encryption for all data in transit
- Encryption at rest for stored files (AWS S3 server-side encryption)
- Authentication and access control (e.g., JWT tokens, rate limiting)
- Audit logging of file access/upload/download events
- Data retention and deletion policies