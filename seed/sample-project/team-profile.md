# Team Profile

- Mina Patel, product-minded backend engineer; comfortable with Python, FastAPI, and SQL.
- Eli Novak, frontend engineer; comfortable with React, TypeScript, and accessible design.
- Jo Laurent, platform generalist; operates Docker, Postgres, and ordinary Linux services.
- Sam Okafor, applied-ML engineer; owns retrieval and evaluation.

The team has no dedicated database administrator, security engineer, or site-reliability
engineer. On-call rotates across all four engineers.

The team has shipped Postgres-backed services and Docker Compose deployments. It has not
operated Kafka, Pulsar, Kubernetes, or a custom distributed vector database in production.

During the pilot, the team can spend at most one engineer-day per week on infrastructure
maintenance. Restore procedures must be executable by any on-call engineer from a
documented runbook.

The team agreed on one working preference after its prototype retrospective: when two
options meet the product need, prefer the option with fewer independently operated
services. This preference is advisory until a user explicitly confirms it for a decision.

