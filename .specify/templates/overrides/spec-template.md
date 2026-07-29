---
feature_id: "NNN-feature-name"
title: "Feature title"
status: "draft"
inception_baseline: "IB-001"
bmad_epics: []
bmad_requirements: []
bmad_quality_requirements: []
owners:
  product: "BMAD inception baseline"
  delivery: "Spec Kit feature"
---

# Feature Specification: Feature title

## Outcome

State the observable user or operator outcome. Describe what changes and why it
matters without selecting implementation details.

## Baseline boundary

List the accepted BMAD requirements this feature realizes. Record any baseline
interpretation. A product, experience, or cross-cutting architecture change
requires a change request and new inception baseline before this feature can
proceed.

## User journeys and acceptance scenarios

Use stable identifiers such as `AS-NNN`.

### AS-NNN — Scenario title

- Given a concrete starting state
- When the actor performs one action
- Then list independently verifiable outcomes

## Functional requirements

Use feature-local identifiers such as `F-NNN`, with links to BMAD `FR-NNN`
identifiers. Never mint a feature-local `FR-*` identifier: that namespace
belongs to the accepted BMAD baseline. Requirements describe behavior, not
implementation.

## Quality requirements

Reference BMAD `NFR-NNN` and `QUALITY-*` identifiers. Give a measurable threshold
or an explicit first-slice baseline.

## Domain rules

State invariants, authority boundaries, precedence, idempotency, and failure
semantics.

## Data and contract impact

Name affected public contracts and durable entities. The detailed representation
belongs in `data-model.md` and `contracts/`.

## Failure and recovery behavior

Cover validation, authorization, dependency failure, cancellation, reconnect,
replay, duplicate requests, stale revisions, and partial results as applicable.

## Out of scope

List adjacent capabilities deliberately deferred from this slice.

## Verification

Map each acceptance scenario to automated tests or versioned evaluations. Every
test path must be exact by the time the feature reaches `planned` status.

## Clarification record

Record decisions already resolved by the accepted baseline or feature analysis.
This section must contain no open question before planning.
