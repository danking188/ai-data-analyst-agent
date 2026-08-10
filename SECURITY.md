# Security Policy

Please report suspected vulnerabilities privately to the repository owner or the security contact
configured by the deployment organization. Do not open a public issue containing exploit details,
credentials, session material, personal data or customer datasets.

Include the affected version/commit, deployment context, reproduction steps, impact and any safe
mitigation. The responder should acknowledge the report within two business days, assign severity
and ownership, rotate exposed credentials immediately, and coordinate disclosure after a fix is
available.

Production operators must keep registration disabled unless explicitly approved, store all secrets
outside Git, run the scheduled dependency/container scans, and follow the backup, monitoring and
rollback procedures in `docs/deployment/DEPLOYMENT.md`.
