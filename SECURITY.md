# Security Policy

## Reporting

Use GitHub private vulnerability reporting for the standalone
`ai-cto-cockpit` repository. Do not disclose suspected vulnerabilities in a
public issue. Include the affected revision, reproduction steps, realistic
impact, and any evidence needed to validate the report without including
unrelated private data.

The maintainers will acknowledge a report within five business days, provide a
severity assessment after reproduction, and coordinate disclosure after a fix
or documented mitigation is available.

## Supported versions

Before the first tagged release, only the default branch is supported. After
release, the latest minor release receives security fixes. Older releases may
receive a migration advisory rather than a patch.

## Security boundaries

AI CTO Cockpit treats every model response and every ingested artifact as
untrusted. Security-sensitive behavior is enforced outside the model:

- workspace scope comes from signed or authenticated server context;
- connectors are read-only in version one;
- repository hooks and downloaded code are never executed;
- web fetching blocks private-network destinations and validates every
  redirect;
- provider credentials stay server-side;
- mutation requests require idempotency and optimistic revision checks;
- only explicit user actions can commit decisions or activate inferred memory;
- controlled UI schemas reject unknown components and actions;
- logs and traces omit raw private evidence and secrets by default.

The public demo uses a synthetic corpus and disables uploads and live
connectors. Local-data mode stores data locally but may send selected context
to the configured remote inference provider; this boundary must be shown before
activation.

## Secret handling

Use environment variables or an approved secret store. Never place credentials
in source, fixtures, logs, screenshots, issue bodies, prompts, evaluation
records, or telemetry. Revoke and rotate any exposed secret immediately, then
remove it from reachable history according to the hosting provider’s guidance.

