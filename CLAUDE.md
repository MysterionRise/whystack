# AI CTO Cockpit Context

AI CTO Cockpit is a portfolio flagship for evidence-backed technical decisions.
The primary user is a technical founder who needs a defensible architecture
choice rather than a conversational answer.

## Read order

Read `AGENTS.md`, `.ai-sdlc/WORKFLOW.md`, the accepted baseline manifest,
`_bmad-output/project-context.md`, and the active Spec Kit feature before
changing files.

## Non-negotiable boundaries

- BMAD defines product intent, UX, architecture, epics, readiness, and the
  system quality contract. It does not implement features.
- Spec Kit defines and executes one vertical feature slice at a time.
- PostgreSQL is the system of record; Qdrant is derived.
- LLM output is untrusted. Typed validation and deterministic policy decide
  what can be shown or persisted.
- React renders only reviewed components from a versioned UI envelope.
- Explicit decisions may become active memory. Inferences remain proposals
  until a user confirms them.
- Recommendations must expose evidence, uncertainty, constraint outcomes,
  version fingerprints, and relevant memory influences.
- Public-demo mode cannot ingest user material or activate live connectors.
- Local-data mode discloses that selected context leaves the machine for
  remote inference.

## Change classification

Use the current Spec Kit feature for clarifications that do not affect other
features. Open a baseline change request for new personas, altered product
outcomes, new deployment modes, UI authority changes, storage ownership
changes, new data-egress behavior, or altered blocking quality thresholds.

Application code starts only after the bootstrap packet validates and the
walking-skeleton feature has a failing acceptance test.

