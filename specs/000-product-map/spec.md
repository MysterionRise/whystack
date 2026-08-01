---
feature_id: "000"
title: "Product delivery map"
status: "baseline"
inception_baseline: "IB-002"
bmad_epics:
  - EPIC-001
  - EPIC-002
  - EPIC-003
  - EPIC-004
  - EPIC-005
  - EPIC-006
---

# Product Delivery Map

## Purpose

This document maps the accepted BMAD inception baseline to independently
deliverable Spec Kit features. It does not restate or replace the product brief,
PRD, experience, architecture spine, epics, or quality contract. Those BMAD
artifacts remain authoritative for product intent and cross-cutting decisions.

## Delivery sequence

| Feature | BMAD epic | Outcome | Primary requirements | Entry condition |
|---|---|---|---|---|
| `001-walking-skeleton` | `EPIC-001` | A seeded guest creates a versioned decision and receives a persisted, replayable controlled-UI response from a deterministic fake model. | `FR-001`, `FR-003`, `FR-006`, `FR-011`; `NFR-002`, `NFR-004`, `NFR-007`, `NFR-008`, `NFR-009`, `NFR-011` | `IB-002` accepted |
| `002-grounded-decision` | `EPIC-002` | The product ingests the seed corpus, retrieves authorized evidence, applies typed constraints, ranks options, and recommends or abstains with attributable evidence. | `FR-002`, `FR-004`, `FR-005`, evidence portions of `FR-012`; `NFR-001`, `NFR-002`, `NFR-003`, `NFR-004`, `NFR-005`, `NFR-006`, `NFR-008`, `NFR-009`, `NFR-011`, `NFR-012` | Feature 001 converged |
| `003-outcome-to-memory` | `EPIC-003` | Explicit outcomes become auditable events, export as cited ADR and JSON artifacts, and approved memory changes a related later decision with a visible explanation. | `FR-007`, `FR-008`, `FR-009`, memory/delta portions of `FR-012`, second-decision portion of `FR-011`; `NFR-002`, `NFR-003`, `NFR-004`, `NFR-007`, `NFR-008`, `NFR-010`, `NFR-011` | Feature 002 converged |
| `004-live-connectors` | `EPIC-004` | Local-data mode reads permitted repositories, files, GitHub resources, and bounded web sources through resumable, observable sync jobs. | `FR-002`, `FR-010`, local-mode policy from `FR-001`; `NFR-002`, `NFR-003`, `NFR-004`, `NFR-008`, `NFR-009`, `NFR-010`, `NFR-011`, `NFR-012` | Feature 003 converged |
| `005-portfolio-experience` | `EPIC-005` | The complete two-decision journey is polished, accessible, inspectable, and demonstrably explains evidence and memory influence. | `FR-006`, `FR-011`, `FR-012`; `NFR-005`, `NFR-007`, `NFR-008`, `NFR-009` | Feature 004 converged |
| `006-public-oss-release` | `EPIC-006` | A bounded public guest demo and portable local-data distribution pass security, cost, performance, durability, and provenance gates. | `FR-011`, `FR-012`; all `NFR-*`; all `QUALITY-*` | Feature 005 converged |

## Roadmap decomposition placeholders

`002-grounded-decision` and `004-live-connectors` are roadmap umbrellas, not
implementation-ready Spec Kit features. Before either reaches `plan`, `tasks`,
or `implement`, it must be decomposed into smaller vertical feature directories.
Each resulting specification must deliver one independently testable outcome,
carry its own requirement and quality traceability, and pass the normal feature
entry gate. The placeholder labels may group those slices on the roadmap, but
must never be used to authorize a broad implementation batch.

## Quality ownership

| Quality ID | Blocking outcome | First feature that establishes the harness |
|---|---|---|
| `QUALITY-RET-001` | Recall@10 is at least 0.90 on the release corpus. | 002 |
| `QUALITY-RET-002` | nDCG@5 is at least 0.80 on the release corpus. | 002 |
| `QUALITY-GRD-001` | Citation locators resolve, precision is at least 0.95, claim coverage is at least 0.90, and fabricated locators are zero. | 002 |
| `QUALITY-REC-001` | Hard-constraint violations are zero; audited quality and stateless-baseline comparison meet the quality contract. | 002 |
| `QUALITY-MEM-001` | Explicit-memory precision is 1.00; no inferred fact activates without confirmation; influence explanations and unrelated-result stability meet the quality contract. | 003 |
| `QUALITY-UI-001` | UI envelopes are schema-valid, unknown kinds fail closed, and serious or critical accessibility violations are zero. | 001 |
| `QUALITY-SEC-001` | Secret disclosure, unauthorized action, prompt-injection compromise, and cross-workspace leakage are zero in the attack suite. | 001 |
| `QUALITY-PERF-001` | First useful UI p95 is at most four seconds and completed recommendation p95 is at most fifteen seconds at the documented demo load. | 001 |
| `QUALITY-COST-001` | Ordinary-turn p95 is at most USD 0.05 and the canonical two-decision demonstration is at most USD 0.15. | 002 |
| `QUALITY-OPS-001` | Restart, replay, idempotency, readiness, index reconciliation, and deletion checks pass. | 001 |

## Feature creation rule

Each later feature starts by copying the project feature template and recording:

- the active inception baseline identifier and hash;
- one owning BMAD epic;
- the BMAD functional and non-functional requirements it realizes;
- applicable quality identifiers;
- explicit dependencies on converged features;
- acceptance scenarios, exact verification paths, and measured release gates.

A newly learned need that changes product outcome, experience authority,
cross-cutting architecture, privacy, or authorization follows the BMAD
change-request process before a feature specification is amended.

## End-to-end acceptance

The product map is complete when the synthetic public-demo user can:

1. frame an architecture decision;
2. inspect authorized, immutable evidence;
3. receive a deterministic constraint-aware recommendation, close call, or
   abstention;
4. accept, edit, dismiss, or revisit the result;
5. approve or reject inferred memory;
6. see an accepted fact influence a related second decision with a precise
   explanation;
7. export the accepted decision as Markdown and JSON;
8. reset the expiring guest workspace without leaving active data.
