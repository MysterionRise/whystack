# AI SDLC Operating Contract

## Purpose

AI CTO Cockpit uses a bounded BMAD-to-Spec Kit handoff. The combination is
intentional: BMAD supplies product discovery, UX, architecture, and readiness;
Spec Kit supplies small executable specifications, traceable tasks, analysis,
and convergence. Running both implementation loops would create competing
sources of truth, so it is prohibited.

## Toolchain

The accepted bootstrap pins:

- BMAD Method `6.10.0` for inception;
- BMAD Test Architect `1.19.1` for risk-based test and quality planning;
- GitHub Spec Kit `0.14.2`, using its constitution and feature-delivery flow.

Versions are recorded in `toolchain.lock.yaml`. Framework upgrades are isolated
maintenance changes. An upgrade must regenerate its owned artifacts in a test
branch, report semantic differences, pass bootstrap verification, and update
the accepted baseline deliberately.

The same lock records the implementation compatibility baseline: Node.js
`24.18.0` LTS, pnpm `11.17.0`, Python `3.12.13`, exact initial frontend and
backend direct dependencies, and versioned PostgreSQL and Qdrant images. These
are bootstrap pins, not an instruction to follow `latest`. T001 must materialize
them in package manifests, `pnpm-lock.yaml`, `uv.lock`, and Compose, including
the recorded image digests. A runtime upgrade follows the same isolated review
rule as a framework upgrade. The verifier's pinned Python `3.13` environment is
separate from the application runtime.

Community Spec Kit extensions are excluded from the initial baseline. BMAD
already owns discovery, and unreviewed extensions would add duplicate behavior
and a supply-chain surface.

## Authority matrix

| Concern | Canonical owner | Canonical artifact |
|---|---|---|
| User, problem, outcomes, scope | BMAD | `product-brief.md`, `prd.md` |
| UX, flows, accessibility, UI authority | BMAD | `DESIGN.md`, `EXPERIENCE.md` |
| Cross-cutting architecture and trust | BMAD | `ARCHITECTURE-SPINE.md` |
| Epics and implementation readiness | BMAD | `epics.md`, `implementation-readiness.md` |
| System quality and AI evaluation policy | BMAD TEA plus project contract | `system-test-design.md`, `ai-quality-contract.md` |
| Engineering principles | Spec Kit | `.specify/memory/constitution.md` |
| Feature behavior and acceptance | Spec Kit | `specs/<feature>/spec.md` |
| Feature design, contracts, tasks | Spec Kit | `plan.md`, `contracts/`, `tasks.md` |
| Implementation-to-spec consistency | Spec Kit | analysis and convergence reports |

BMAD does not own feature specifications, implementation stories, sprint
planning, quick development, automated development, or implementation review.
Spec Kit does not redefine the accepted persona, outcomes, non-goals, UX
authority, trust boundaries, canonical stores, or system quality thresholds.

## Baseline lifecycle

### Inception

BMAD produces:

1. product brief and research synthesis;
2. requirements with stable `FR-*` and `NFR-*` identifiers;
3. visual and interaction experience contracts;
4. an architecture spine;
5. epics with acceptance outcomes;
6. risk-based system test design and AI quality thresholds;
7. an implementation-readiness verdict.

The accepted artifacts are frozen as `IB-001`. The baseline manifest records
the framework versions, artifact paths, hashes, scope, and readiness state.

### Delivery

Each vertical slice follows this order:

1. `specify`
2. `clarify`
3. requirements checklist
4. `plan`
5. AI and security checklist
6. `tasks`
7. `analyze`
8. failing acceptance test
9. bounded implementation batch
10. deterministic tests
11. relevant AI evaluations
12. `converge`
13. human review

Every feature identifies its baseline, BMAD requirements, epic, quality gates,
and relevant project signals. A task without this chain cannot enter
implementation.

The project workflow is installed as `ai-feature-delivery`. Its `batch` input
is mandatory and is passed to Spec Kit's supported staged implementation mode;
for example, `batch=T001-T003`. Each run stops for evidence review after that
batch. Set `completion=final` only for the last planned batch so convergence
runs at the correct point.

### Change control

Classify discoveries before editing canonical artifacts:

- **Feature clarification:** affects only the active slice and does not alter
  accepted product, UX, trust, storage, or quality boundaries. Record it in the
  feature and rerun analysis.
- **Baseline change:** changes personas, outcomes, non-goals, deployment modes,
  UI authority, data-egress behavior, system-of-record ownership, consequential
  actions, or a blocking quality threshold. Create `docs/changes/CR-NNN.md`,
  assess affected requirement and feature IDs, update BMAD artifacts, rerun
  readiness, and issue a new hashed baseline.
- **Project signal:** a lesson from a course or experiment that has not been
  accepted. Record provenance and confidence; it has no authority until routed
  through a feature or baseline change.

Implementation pauses only where a baseline change invalidates the active
slice. Unaffected slices may continue.

## Gate policy

### Inception gate

The baseline can be accepted when:

- every requirement is testable and mapped to an epic;
- UX covers the canonical happy path, empty, loading, conflict, degraded,
  denial, reconnect, and recovery states;
- architecture defines ownership, trust, versioning, migration, and failure
  boundaries;
- system quality targets have datasets and measurement procedures;
- no severity-P0 risk or unresolved material ambiguity remains;
- portability and license/provenance checks pass.

### Feature entry gate

Implementation starts only when the feature has:

- a complete specification and accepted clarifications;
- contracts and data migration design where applicable;
- ordered tasks with concrete paths and tests;
- a clean cross-artifact analysis result;
- an explicit first failing acceptance test.

### Merge gate

A feature merges only when:

- deterministic test suites pass;
- applicable AI, security, accessibility, latency, and cost gates pass;
- migrations, rollback, replay, and deletion behavior are verified where
  relevant;
- generated contracts match canonical Pydantic schemas;
- traces and logs remain redacted;
- implementation learning is reconciled into the feature artifacts;
- convergence reports no critical mismatch.

Thresholds are not weakened to make a build pass. A justified change follows
the baseline-change path and preserves the prior measurement for comparison.

## Human authority

Humans accept inception baselines, approve baseline changes, resolve quality
waivers, and merge features. Automated agents may draft, analyze, test, and
implement within accepted boundaries. They may not silently broaden scope,
activate inferred memory, enable consequential connectors, publish data, or
change quality thresholds.

## Traceability

The required chain is:

`BMAD requirement → BMAD epic → Spec Kit feature → acceptance scenario → task → test or evaluation`

Quality requirements additionally map to a `QUALITY-*` gate. The bootstrap
traceability verifier rejects dangling, duplicated, or unknown identifiers.
