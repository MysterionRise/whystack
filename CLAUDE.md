# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

AI CTO Cockpit is an evidence-backed architecture-decision workspace: a
technical founder frames a decision, inspects cited project evidence, compares
options under deterministic constraint/scoring rules, records an outcome, and
sees how that outcome changes a later recommendation. It is not a chat wrapper
— the model may populate reviewed UI components but cannot emit executable UI,
and constraint enforcement, scoring, and persistence are all deterministic
application code, not model output.

## Governance: read this before editing

The repo runs two frameworks with a strict handoff, defined in full in
`AGENTS.md` and `.ai-sdlc/WORKFLOW.md`:

- **BMAD** owns product intent, UX, architecture, epics, and the quality
  contract (`_bmad-output/planning-artifacts/`, `_bmad-output/test-artifacts/`).
  It does not implement features.
- **Spec Kit** owns one vertical feature slice at a time
  (`specs/<feature>/{spec,plan,tasks}.md`). Running a BMAD implementation loop
  for a Spec Kit slice is prohibited — the adapters for it are deliberately
  absent from `.agents/skills/` and `.claude/skills/`.
- Before changing files, read (in order): `AGENTS.md`, `.ai-sdlc/WORKFLOW.md`,
  `.ai-sdlc/inception-baseline.yaml` (the accepted baseline), and the active
  feature under `specs/`. The current slice is `specs/001-walking-skeleton/`;
  check its `tasks.md` for the next unstarted task rather than assuming a
  number here.
- A slice-local discovery amends the active feature. A change to persona,
  product outcomes, deployment modes, UI authority, storage ownership,
  data-egress behavior, or a blocking quality threshold requires a numbered
  baseline change request under `docs/changes/` first.

Non-negotiable invariants (see `AGENTS.md` for the complete list):

- PostgreSQL is the system of record; Qdrant is a derived, rebuildable index.
- `workspace_id` is always derived from authenticated/signed server context,
  never accepted from model output or client input.
- LLM output is untrusted: typed validation and deterministic policy decide
  what can be shown or persisted; only a versioned, reviewed UI envelope may
  render.
- Explicit user decisions become durable memory; inferred preferences remain
  proposals until confirmed.
- Public-demo mode never ingests user material or activates live connectors;
  local-data mode must disclose when selected context leaves the machine for
  remote inference.
- Mutations require idempotency keys and expected revisions.

## Commands

Requires Node.js `24.18.0` + Corepack pnpm `11.17.0` and Python `3.12.13`
(pinned in `.node-version`, `.python-version`, `.ai-sdlc/toolchain.lock.yaml`);
`make` targets fail fast if the active toolchain doesn't match. Docker Compose
v2 is required for the topology test.

```bash
make install              # pnpm install --frozen-lockfile + uv sync (locked, all groups)
./scripts/verify-bootstrap.sh   # bootstrap packet verifier — run before any batch
make check                 # ruff check + ruff format --check + pyright + web check (eslint+tsc)
make contracts-generate     # regenerate backend OpenAPI/JSON Schema, then frontend bindings
make contracts-check        # verify generated contracts are byte-identical / semantically equal
make test-compose-readiness # self-cleaning e2e: build+wait all 5 processes, check Postgres/Alembic/Qdrant readiness
make toolchain-check         # print/verify every pinned tool version
```

Single-suite / single-test invocations:

```bash
# frontend (vitest), from apps/web
corepack pnpm --dir apps/web test -- ui-envelope-contract.test.ts

# backend (pytest), from repo root, via uv against services/backend
uv run --project services/backend --locked pytest services/backend/tests/api/test_decisions.py
uv run --project services/backend --locked pytest services/backend/tests/property/test_revision_idempotency.py -k <name>
```

Root `pnpm test` / `pnpm test:e2e` proxy to `apps/web`'s vitest / playwright.

## Architecture

**Processes** (`infra/compose.yaml`, five services): `web` (Next.js, health
endpoint) → `api` (FastAPI, separate liveness/readiness endpoints) → `worker`
(non-HTTP Python process; leases jobs from Postgres with attempt fencing, so
it's restart-safe) → `postgres` (canonical store) → `qdrant` (derived,
rebuildable, readiness-only at this stage — no retrieval is implemented yet).

**Contracts flow one direction**: canonical Pydantic models in
`services/backend/src/ai_cto_cockpit/contracts/` are the source of truth.
`contracts/generate.py` writes deterministic `contracts/generated/openapi.json`
and `ui-envelope.schema.json`; `apps/web/scripts/generate-contracts.mjs`
derives TypeScript types (`apps/web/src/contracts/generated.ts`) plus a
fail-closed runtime parser (`ui-envelope.ts`) that only accepts known,
versioned envelope shapes (e.g. `recommendation-summary@1.0`) — anything else
is rejected rather than rendered. Never hand-edit generated contract files;
change the Pydantic source and run `make contracts-generate`.

**Backend layout** (`services/backend/src/ai_cto_cockpit/`): `api/routes/`
(config, decisions, runs, capabilities) sit on `api/dependencies/context.py`
for trusted, server-derived request context; `domain/` holds pure logic
(revision normalization, idempotency, ID generation); `persistence/` holds
SQLAlchemy models/repositories and Alembic migrations
(`services/backend/migrations/versions/`, currently head
`0001_walking_skeleton`); `runs/` holds the run lifecycle (`service.py`,
`jobs.py` for the Postgres-backed lease queue, `fake_graph.py` — an explicit
three-node LangGraph fixture used until real retrieval/inference lands);
`security/guest_session.py` implements opaque, signed, workspace-scoped guest
sessions with atomic reset/replay.

**Runs and streaming**: run creation is atomic and idempotent, bound to an
immutable decision revision; it commits a queued event and an execute-run job
together. The worker executes the graph and persists a closed
`recommendation-summary@1.0` envelope plus a terminal event. Clients replay
via workspace-scoped, Postgres-backed SSE with persisted sequence IDs,
`Last-Event-ID` recovery, and heartbeats — this must survive API or worker
restart.

**Seed/eval fixtures**: `seed/sample-project/` is the synthetic "Northstar
Relay" corpus the public demo is built on; `evals/` holds the deterministic
acceptance corpus (`seed-v0.jsonl`, `attack-seed-v0.jsonl` for prompt-injection
cases) validated against `evals/dataset.schema.json`.
