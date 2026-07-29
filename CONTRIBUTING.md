# Contributing

Thank you for improving AI CTO Cockpit. Contributions should preserve its
evidence-first, user-controlled design.

## Before proposing work

- Read `AGENTS.md` and `.ai-sdlc/WORKFLOW.md`.
- Search existing Spec Kit features and change requests.
- Classify the proposal as a slice-local change or a baseline change.
- Confirm that any sample content, model, library, or data source can be
  redistributed under its stated terms.

## Change paths

Use a Spec Kit feature for behavior that stays inside the accepted product,
experience, trust, and architecture boundaries. Use a numbered baseline change
request for a new persona, deployment profile, consequential action, canonical
store, data-egress behavior, UI authority model, or blocking quality target.

Feature changes must include:

- traceability to BMAD requirement, epic, and quality identifiers;
- testable acceptance scenarios and explicit non-goals;
- contracts and migrations where interfaces or durable data change;
- a failing test before implementation;
- deterministic tests plus relevant evaluation and security cases;
- documentation of model, prompt, retriever, schema, and dataset versions when
  AI behavior changes.

## Development expectations

- Keep branches and commits focused.
- Use imperative commit subjects.
- Do not commit secrets, private source material, raw production traces, or
  generated credentials.
- Keep notebook and generated tool output out of the repository unless it is an
  intentional, reviewed artifact.
- Preserve backwards compatibility or include a tested migration and rollback
  path.
- Do not bypass deterministic constraint checks, citation validation, workspace
  scoping, or user confirmation to simplify a demonstration.

## Pull requests

A pull request should identify its Spec Kit feature, list acceptance scenarios,
show fresh verification commands and results, state any data-egress or privacy
effect, and include screenshots for visible UI changes. AI behavior changes
must attach the evaluation manifest and compare results with the accepted
baseline.

Security vulnerabilities should follow `SECURITY.md`, not a public issue.

