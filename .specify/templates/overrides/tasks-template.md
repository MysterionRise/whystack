---
description: "Traceable RED-GREEN task plan for a bounded feature"
---

# Tasks: [FEATURE NAME]

**Inputs**: `spec.md`, `plan.md`, `research.md`, `data-model.md`,
`contracts/`, `quickstart.md`, the accepted inception baseline, and the
project constitution.

**Testing policy**: Tests are mandatory. Every production-behavior task MUST
be preceded by a task that introduces the smallest automated test which fails
for the expected reason. Record that RED evidence before changing production
behavior, then implement only enough for GREEN and refactor under the same
passing test.

## Required task format

`- [ ] **TNNN — RED|GREEN|REFACTOR|VERIFY: description**`

Every task MUST:

- name exact repository paths;
- link at least one acceptance scenario and its BMAD `FR-*`, `NFR-*`, or
  `QUALITY-*` baseline requirement;
- identify dependencies and whether it can run in parallel;
- name the exact verification command or versioned evaluation;
- fit in one reviewable implementation batch.

Use `[P]` only when tasks touch different files and have no data, migration,
contract, or ordering dependency. Do not replace stable task IDs after they
have verification evidence.

## Phase 1: Reproducible setup

**Goal**: establish the smallest locked environment needed by the first test.

- [ ] **T001 — VERIFY: [setup outcome]** in `[exact paths]`; traces
  `[AS-NNN]`, `[FR-NNN/NFR-NNN/QUALITY-*]`; run `[exact command]`.

**Checkpoint**: a clean clone can reproduce the toolchain and the expected
pre-implementation state.

## Phase 2: Foundational RED-GREEN pairs

**Goal**: introduce only foundations directly required by an acceptance
scenario.

- [ ] **T002 — RED: [observable behavior]** in `[test path]`; traces
  `[AS-NNN]`, `[baseline IDs]`; run `[exact command]` and preserve the expected
  failure.
- [ ] **T003 — GREEN: [smallest behavior]** in `[implementation paths]`;
  depends on `T002`; rerun `[exact command]`.
- [ ] **T004 — REFACTOR: [structural improvement, if necessary]** in
  `[exact paths]`; depends on `T003`; rerun `[exact command]`.

**Checkpoint**: the RED failure was observed, the paired GREEN behavior passes,
and no unapproved behavior was added.

## Phase 3+: Acceptance-scenario slices

Create one independently demonstrable phase per acceptance scenario or small
cohesive scenario group:

### Scenario [AS-NNN] — [title]

**Outcome**: [observable user/operator outcome]

- [ ] **TNNN — RED: [contract/unit/integration/e2e behavior]** in
  `[test path]`; traces `[AS-NNN]`, `[baseline IDs]`; run `[exact command]`.
- [ ] **TNNN — GREEN: [minimal implementation]** in `[implementation paths]`;
  depends on the preceding RED task; run `[exact command]`.
- [ ] **TNNN — VERIFY: [relevant deterministic, security, accessibility,
  latency, cost, or AI-evaluation gate]** using `[exact command/dataset]`;
  depends on the GREEN task.

**Checkpoint**: the scenario is independently testable, contracts and
migrations agree, and applicable quality gates pass.

## Final phase: convergence and handoff

- [ ] **TNNN — VERIFY: run all deterministic suites and applicable versioned
  evaluations** using `[exact commands]`; traces all active scenarios.
- [ ] **TNNN — VERIFY: reconcile specification, contracts, generated types,
  observability, migrations, rollback, deletion, and documentation** in
  `[exact paths]`.
- [ ] **TNNN — VERIFY: run Spec Kit convergence and obtain human review**;
  append any discovered gap as a new task instead of silently broadening an
  existing task.

## Dependencies and bounded execution

- Execute setup before its dependent RED task.
- Execute each RED task and preserve its expected failure before the paired
  GREEN task.
- Do not begin a later scenario while its blocking contract, migration, trust,
  or tenancy prerequisite is incomplete.
- Invoke `speckit.implement` with an explicit reviewed task ID or phase range.
  Never use an unscoped implementation run for a multi-phase feature.
- Stop after the approved batch, run its verification, and request review.
- Run `speckit.converge` only after the final planned batch; if it appends
  tasks, execute those as new bounded RED-GREEN batches.

## Prohibited task shapes

- behavior without a preceding failing automated test;
- vague paths, implicit verification, or unresolved placeholders;
- task IDs without scenario and baseline links;
- model-generated authorization, arbitrary executable UI, or unscoped data
  access;
- an implementation task broad enough to consume the entire feature without a
  review checkpoint.
