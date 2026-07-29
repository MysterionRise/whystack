# Threat Model

## Assets and Security Objectives

The system protects source contents, model credentials, workspace isolation, decision
integrity, memory correctness, user-approved actions, and public-demo availability.
Security decisions are deterministic application behavior, never prompt-only policy.

## Actors

- An authorized local operator using private project material.
- An anonymous public-demo visitor.
- A malicious contributor to an otherwise authorized repository or GitHub thread.
- A hostile web publisher whose content is retrieved as evidence.
- An attacker sending crafted API requests or attempting denial of service.
- A compromised or incorrect external model response.

## Principal Threats and Controls

| Threat | Boundary | Required controls | Verification |
|---|---|---|---|
| Indirect prompt injection in evidence | Source ingestion and model | Label source text as untrusted; delimit it; exclude instructions from tool authority; allowlist tools and UI actions; validate all output | Injection corpus and end-to-end tests |
| Cross-workspace retrieval | API, Postgres, Qdrant | Derive scope server-side; include scope in every query and vector filter; reject client-selected scope | Randomized isolation tests |
| Secret disclosure | Repository, logs, model egress | Allowlist paths; skip secret patterns and ignored files; redact traces; preview egress; keep provider key server-side | Canary-secret tests and log scans |
| SSRF and local-network access | Web connector | HTTPS only; DNS/IP validation before and after redirects; block loopback, link-local, private, metadata, and non-standard ports; response byte/time limits | Redirect and rebinding cases |
| Repository execution | Local connector | Read files without checkout hooks, builds, submodule execution, archive expansion, or rendered active content | Malicious repository fixture |
| Arbitrary generated UI | Model to browser | Versioned component union; escaped text; no raw HTML, script, URL action, or dynamically imported component | Schema/property tests and CSP |
| Unauthorized consequential action | Model to API | V1 exposes read-only connectors and explicit user outcome actions only; authorization and confirmation outside the model | Negative API and UI tests |
| Memory poisoning | Outcome and memory pipeline | Explicit facts activate immediately only after user action; inferred facts remain proposals; retain provenance; support supersession and deletion | Multi-session and injection tests |
| Evidence or citation fabrication | Model and recommendation | Resolve exact immutable locator; verify excerpt; mark freshness; abstain after failed repair | Citation precision gate |
| Race, replay, or duplicate mutation | API and jobs | Idempotency keys, expected revisions, append-only events, unique constraints, leased jobs | Concurrency and restart tests |
| Resource exhaustion and spend abuse | Public demo | Input, evidence, step, token, concurrency, rate, and daily-spend caps; cancellation and circuit breakers | Load and budget tests |
| Dependency or artifact compromise | Build pipeline | Lock dependencies; verify provenance; secret scan; dependency scan; minimal images; signed release manifest | CI and release checks |
| Data remanence | Storage and indexes | Tracked deletion job across relational, vector, blob, cache, and trace stores; measurable deletion SLO | Deletion reconciliation test |

## Prompt-Injection Policy

Retrieved text may assert that it is a system message, request secrets, redefine the task,
or propose UI/actions. Those statements remain quoted evidence only. The orchestration
layer supplies source text through data-only fields and maintains an independent,
server-controlled allowlist for tools and components. A model refusal or compliance is
not itself a security control.

## Connector Rules

- Local repository roots are canonicalized and explicitly allowlisted.
- Symbolic links and relative paths cannot escape an allowlisted root.
- `.gitignore` and a project denylist are honored; credential-like files are denied even
  if tracked.
- GitHub tokens are read-only and constrained to selected repositories.
- Web acquisition stores request URL, final URL, capture time, content checksum, and
  content type. JavaScript is not executed in v1.
- Parser limits apply before extraction. Unsupported or encrypted documents fail safely.

## Logging and Telemetry

OpenTelemetry spans may record identifiers, timings, counts, versions, and redacted error
classes. Raw private passages, prompts, model completions, authorization headers, cookies,
provider keys, and uploaded file contents are excluded by default. An operator may enable
content tracing only in local development with an explicit warning.

## Data Lifecycle

- Public guest state expires after 24 hours and can be reset immediately.
- Local source revisions persist until an operator deletes the source or workspace.
- Deletion first revokes access, then removes relational projections, vectors, blobs,
  caches, and content-bearing traces. Tombstones prevent a stale worker from recreating
  deleted material.
- Backups are outside the v1 public demo. Local operators are responsible for backup
  retention and receive documented deletion limitations.

## Residual Risks

- Evidence sent to an external model provider is subject to that provider's configured
  retention and processing terms.
- Heuristic secret detection can miss novel credentials; path allowlisting and egress
  preview remain required.
- A well-formed but misleading source can bias a recommendation. Source diversity,
  provenance, conflict presentation, and abstention reduce but do not eliminate this risk.
- The public demo is deliberately non-confidential and must never accept private content.

