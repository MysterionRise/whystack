---
artifact: project-context
baseline: IB-001
status: accepted
date: 2026-07-27
---

# AI CTO Cockpit Project Context

## One-sentence definition

AI CTO Cockpit is an evidence-backed workspace in which a technical founder
frames an architecture decision, receives a constrained and cited comparison,
records an outcome, and can inspect how that outcome influences a later
decision.

## Primary user and job

The primary user is a technical founder or hands-on engineering leader in a
small AI product team. They need to make consequential technical choices with
limited research time and limited specialist support. They want a concise
answer, but they also need to defend it later and adapt it when constraints or
preferences change.

The job is: “Given my project evidence, constraints, and prior accepted
decisions, help me choose a viable architecture and leave an audit trail I can
inspect, correct, and export.”

## Canonical demonstration

The public demo uses an original fictional company and a fixed source corpus.
The visitor:

1. frames a technical architecture decision;
2. inspects retrieved evidence and alternatives;
3. accepts or edits a recommendation;
4. reviews the resulting durable fact;
5. opens a related decision;
6. sees a changed ranking and a precise explanation of the memory influence;
7. exports the accepted result as Markdown ADR and JSON.

The demonstration must remain useful without live credentials.

## Product principles

- Evidence is inspectable and revision-pinned.
- Hard constraints are typed and enforced outside the model.
- Recommendation scoring is deterministic and can abstain.
- Memory is provenance-backed, correctable, and under user authority.
- The UI is adaptive but bounded to reviewed components and actions.
- System-of-record state and model context are separate concerns.
- “Local data” describes storage, not fully local inference.
- Quality claims are tied to versioned datasets and reproducible manifests.

## Deployment profiles

### Public demo

- fixed synthetic sources;
- signed server-derived guest workspace;
- 24-hour decision and memory overlay;
- reset control;
- uploads and live connectors denied;
- five requests per minute, fifty turns per day, two concurrent runs;
- bounded daily provider spend.

### Local-data mode

- persistent PostgreSQL, Qdrant, and file data;
- read-only local repository, file, GitHub, and bounded web connectors;
- user-supplied server-side provider and connector credentials;
- disclosure before retrieved context is sent to remote inference;
- deletion and index reconciliation controls.

## Target architecture

- Next.js and React own layout, accessibility, navigation, and actions.
- CopilotKit and AG-UI carry versioned controlled UI envelopes.
- FastAPI and Pydantic own the external API and schemas.
- LangGraph expresses an explicit decision workflow, not authorization.
- PostgreSQL owns sources, revisions, decisions, events, memories, runs, jobs,
  and citation text.
- Qdrant holds rebuildable vectors with scoped identifiers.
- A Python worker handles ingestion, indexing, and memory consolidation.
- OpenRouter-compatible inference is behind a provider adapter.
- Docker Compose is the portable development and initial deployment contract.

## Safety boundaries

The system cannot make code changes, write to GitHub, execute repository
content, browse arbitrary private-network URLs, activate inferred preferences,
or render arbitrary model-generated code. A user explicitly commits outcomes
and memory changes.

## Quality posture

The release is blocked by provenance failures, fabricated locators, hard
constraint violations, unconfirmed active memory, unsafe UI envelopes, secret
leakage, cross-workspace access, or loss of durable outcomes. Retrieval,
recommendation quality, memory behavior, latency, and cost have numerical gates
defined in the AI quality contract.

## Lifecycle boundary

BMAD artifacts define the accepted product baseline through readiness. Spec Kit
features are the sole unit of delivery. Product-level discoveries return to a
numbered baseline change; implementation discoveries flow back into the active
feature.

