# ADR 0001: Bound BMAD to Inception and Spec Kit to Delivery

- Status: Accepted
- Date: 2026-07-27
- Baseline: IB-001
- Decision owners: Product and engineering

## Context

AI CTO Cockpit needs more product discovery than a feature-only workflow provides, while
also needing implementation artifacts that remain traceable to tests and evaluations.
BMAD and Spec Kit both contain planning and delivery concepts. Running their complete
workflows over the same change would create two competing specifications, duplicated
status, and ambiguous approval authority.

## Decision

BMAD owns inception:

1. Product brief and PRD.
2. Experience and visual design.
3. Architecture spine and cross-cutting non-functional requirements.
4. Epics, system-level test design, and implementation-readiness review.

An accepted, hashed inception bundle becomes an immutable baseline such as `IB-001`.

Spec Kit owns delivery:

1. A constitution derived from the accepted baseline.
2. One feature specification for each vertical slice.
3. Clarification, technical planning, tasks, consistency analysis, implementation, and
   convergence.
4. Traceability from baseline requirements to acceptance tests and AI evaluations.

BMAD implementation stories, sprint automation, quick-development flows, and unattended
coding loops are disabled. Spec Kit cannot silently redefine product intent, experience,
or cross-cutting architecture.

## Change Boundary

A discovery made within a feature remains in the active Spec Kit package when it changes
only that slice. A change to product outcomes, user experience, data boundaries, security
posture, or cross-cutting architecture requires a numbered change request in
`docs/changes/`, a BMAD baseline revision, and another readiness review.

## Consequences

- There is one authority for each artifact and one implementation task list.
- Framework upgrades are explicit and independently pinned.
- Product decisions remain visible instead of being rediscovered inside prompts.
- The handoff adds a baseline and traceability check, which is intentional process cost.
- AI quality still requires a project-specific evaluation contract; neither framework is
  treated as a substitute for retrieval, memory, recommendation, or safety evaluation.

## Rejected Alternatives

- **BMAD alone:** strong inception coverage, but its delivery loop would become the only
  source of feature traceability and would couple the project to a broader workflow.
- **Spec Kit alone:** strong feature execution, but insufficient structure for the
  product, experience, and adversarial inception work required by this flagship.
- **Both complete workflows:** rejected because duplicate specs and task systems make
  drift more likely than additional ceremony makes correctness.

