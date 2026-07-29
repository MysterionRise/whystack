---
artifact: system-test-design
baseline: IB-001
status: accepted
date: 2026-07-27
risk_model: P0-P3
---

# System Test Design

## Purpose

This strategy verifies that AI CTO Cockpit remains useful, reproducible, secure,
and user-controlled across deterministic software behavior and probabilistic AI
behavior. It complements feature-level test plans; it does not replace their
failing acceptance tests.

## Risk classification

- **P0 — release blocking:** could leak secrets or workspace data, violate a
  hard constraint, fabricate provenance, activate unconfirmed memory, execute
  untrusted content, duplicate consequential state, or lose an accepted outcome.
- **P1 — release blocking:** materially wrong retrieval/recommendation, broken
  deletion/recovery, inaccessible canonical journey, contract drift, or
  unbounded cost/latency.
- **P2 — fix before release unless explicitly waived:** degraded secondary
  journey, confusing but recoverable state, incomplete observability, or minor
  compatibility defect.
- **P3 — backlog eligible:** cosmetic or low-impact issue with a clear safe
  workaround.

No P0 waiver is permitted. A P1 waiver requires an accepted baseline change,
named owner, expiry, user-visible mitigation, and evidence that the canonical
journeys remain safe.

## Principal risks and controls

| Risk | Priority | Preventive control | Detecting test |
|---|---|---|---|
| Cross-workspace canonical or vector access | P0 | Server-derived scope on every record/query | 10,000 randomized isolation operations plus crafted vector filters |
| Indirect prompt injection changes policy or reveals secrets | P0 | Untrusted-content boundary, no consequential tools, strict output schemas | 100-case attack corpus across sources and run stages |
| Failed/unknown hard constraint is recommended | P0 | Deterministic fail-closed constraint service | Property tests and every constrained evaluation case |
| Fabricated or shifted citation | P0 | Immutable revisions, locator validation, one repair maximum | Locator mutation, deletion, parser-version, and adversarial citation cases |
| Inferred preference affects a run before confirmation | P0 | Inactive proposal state enforced by query policy | State-machine and multi-session evaluation cases |
| Duplicate outcome after retry/replay | P0 | Idempotency record, transaction, expected revision | Network interruption and duplicate delivery tests |
| Accepted state lost on restart | P0 | PostgreSQL canonical transaction and recovery | Process/container kill and restore tests |
| Public demo ingests visitor or connector data | P0 | Mode capability checks at API and worker | Direct endpoint, forged UI, queued-job, and model-output attempts |
| Deleted private material remains active | P0 | Staged deletion plus index reconciliation | Canonical/vector/blob inspection within 60 seconds |
| Weak retrieval produces confident answer | P1 | Coverage threshold and abstention | Insufficient, conflicting, stale, and distractor cases |
| Model/provider change silently regresses quality | P1 | Versioned release manifest and comparative gate | Protected candidate-versus-baseline evaluation |
| Controlled UI renders unsafe behavior | P0 | Closed component/action registries and runtime validation | Generated/fuzzed envelopes and browser content-security tests |
| Public spend or concurrency becomes unbounded | P1 | Server quotas, bounded steps/context, daily stop | Load, race, and provider-accounting simulations |
| Trace exports contain private passages or credentials | P0 | Allowlisted telemetry fields and redaction | Canary secrets across every input and error path |
| Connector executes or escapes retrieved content | P0 | Read-only adapters, path and URL guards | Hooks, symlinks, archives, redirects, DNS rebinding, MIME and size attacks |
| User cannot understand or correct memory | P1 | Provenance ledger and explicit controls | Moderated journey plus accessibility tests |

## Test layers

### Contract and static checks

- Validate OpenAPI, JSON Schema, event, UI-envelope, export, evaluation-manifest,
  and connector contracts.
- Regenerate TypeScript artifacts from canonical Pydantic models and reject
  drift.
- Check requirement-to-feature-to-test traceability.
- Scan source, commits, images, dependencies, containers, fixtures, and
  generated artifacts for secrets, vulnerabilities, licenses, and provenance.
- Verify migrations have forward, restore/rollback, and compatibility metadata.

### Unit and property tests

- Constraint parsing and pass/fail/unknown policy.
- Weight normalization, evidence coverage, scoring, lead threshold, and
  recommendation/close-call/abstention selection.
- Locator parsing and excerpt verification.
- Memory priority, conflict, validity, supersession, deletion, and context
  budgeting.
- Mode/capability authorization and workspace query construction.
- Idempotency keys, request hashes, expected revisions, and event rebuilding.
- URL/path validation, redirect resolution, checksum and content addressing.
- UI-envelope and action registry rejection for unknown or additional fields.

Property tests generate boundary weights, score ties, constraint combinations,
revision conflicts, duplicate event orders, invalid cursors, workspace IDs,
Unicode paths, URLs, and schema payloads.

### Service integration tests

Run API, worker, PostgreSQL, Qdrant, and fake provider together to verify:

- migration and readiness;
- transaction plus outbox atomicity;
- leased-job recovery and dead-letter behavior;
- source revisioning, chunking, indexing, tombstones, and reconciliation;
- run stages, persisted events, reconnect and terminal replay;
- outcome-to-memory state transitions;
- canonical export after index outage or source deletion;
- guest expiry and staged deletion;
- OpenTelemetry field allowlist and canary redaction.

Each failure-sensitive test inspects canonical state, derived state, and
emitted events rather than relying only on an HTTP response.

### Browser and accessibility tests

Playwright covers public entry, framing, progress, evidence inspection,
recommendation, close call, abstention, accept/edit/dismiss, memory confirmation
and correction, second-decision delta, export, reset, reconnect, stale conflict,
mode denial, dependency failure, and spend stop.

Run automated accessibility checks on every stable route and component state.
Manually verify the canonical journeys with keyboard-only navigation, reduced
motion, 200% zoom, and one supported desktop screen reader. Test 360, 768, 1280,
and 1440-pixel viewports.

### AI evaluations

The project evaluation harness loads immutable cases, runs the full decision
workflow, and scores retrieval, citations, result type, recommendation,
constraint safety, memory behavior, UI schema, latency, and cost. The detailed
dataset, scoring, replication, and gate policy is binding in
`ai-quality-contract.md`.

Deterministic CI uses a fake provider and fixed embeddings for structural
invariants. A protected provider job runs the pinned live model on candidate
releases and on any change to prompt, model, retrieval, reranking, chunking,
memory selection, or recommendation policy.

### Security tests

- Indirect and direct prompt-injection corpus.
- Cross-workspace randomized and targeted access attempts.
- Canary credentials and private passages through success, validation, repair,
  timeout, retry, export, trace, and error paths.
- Connector path traversal, symlink, hook, submodule, archive, unsafe URL,
  redirect, DNS, MIME, decompression, size, and timeout cases.
- Forged guest cookie, capability, action, cursor, workspace, idempotency, and
  expected-revision cases.
- UI payload script, markup, URL, action, prototype, and unknown-version fuzzing.
- Dependency, container, and secret scanning.

### Reliability and operations tests

- Kill API, worker, PostgreSQL connection, Qdrant, and provider at each durable
  workflow boundary.
- Reconnect streams from every persisted cursor.
- Retry every mutation and worker effect.
- Rebuild Qdrant from canonical sources and atomically switch embedding
  generation.
- Backup PostgreSQL/blob state, destroy the deployment, restore, and validate
  decisions, citations, outcomes, and memory.
- Expire demo overlays and delete local sources while runs and retries are
  present.
- Exercise rate, turn, concurrency, context, step, timeout, and spend limits
  under races.

### Performance and cost tests

Use the reference Linux profile of four vCPUs, eight GiB RAM, SSD storage, warm
containers, and five concurrent demo users. The public seed corpus is loaded,
but recommendation results are not response-cached.

Measure first useful UI, terminal result, non-model API reads, retrieval,
reranking, provider latency, stream delivery, token use, and provider-reported
cost. Use at least 200 completed turns after a 20-turn warm-up. Report p50, p95,
p99, error rate, and sample count.

## Test environments

| Environment | Provider | Data | Purpose |
|---|---|---|---|
| Local deterministic | Fake model and fixed vector fixtures | Minimal synthetic | Fast contract, unit, integration, and browser CI |
| Local live | Developer-selected pinned provider | Public seed | Prompt/retrieval iteration without private evaluation cases |
| Protected evaluation | Pinned OpenRouter model | Versioned release corpus plus hidden holdout | Candidate release decision |
| Security | Fake and pinned live provider | Attack corpus and canary secrets | Policy, leakage, and injection |
| Reference performance | Pinned live provider | Public seed and load fixtures | Latency, concurrency, and cost |

Private local-data material never enters shared CI or the evaluation corpus.

## Data management

- Seed and evaluation artifacts are original, versioned, and checksummed.
- The bootstrap seed contains twelve visible cases for harness validation.
- The release corpus contains sixty cases with a twelve-case hidden holdout.
- The prompt-injection corpus contains one hundred independent attacks.
- Dataset changes receive review separate from model/prompt changes.
- Test outcomes identify case IDs without copying private content into logs.
- Expected labels include relevant evidence, admissible result types, constraint
  outcomes, applicable memory, forbidden memory, and citation locators.

## Release evidence

Each candidate produces a signed or checksummed evaluation manifest containing:

- commit and Spec Kit feature identifiers;
- inception baseline;
- schema and migration versions;
- provider, model, temperature and decoding settings;
- system and task prompt hashes;
- embedding, chunking, fusion, reranker and index generation;
- dataset and attack-corpus hashes;
- metric values, confidence summaries, case-level failures;
- latency sample distribution and cost;
- test command identities and timestamps;
- final pass/fail decision and any accepted non-P0 waiver.

The release report compares the candidate with the last accepted manifest and
links every regression to a feature or baseline change.

## Exit criteria

A release can proceed only when:

- every P0 and P1 automated gate passes;
- no open P0 defect exists;
- all `QUALITY-*` thresholds pass;
- the canonical, abstention, correction, deletion, replay, restore, and
  cross-workspace journeys pass;
- manual accessibility and moderated-usability acceptance pass;
- clean-clone deployment and provenance verification pass;
- the release manifest is complete and attributable.

