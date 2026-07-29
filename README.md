# AI CTO Cockpit

AI CTO Cockpit is a portfolio-grade, evidence-backed architecture decision
workspace. It helps a technical founder frame a decision, inspect relevant
project evidence, compare viable options, record an outcome, and see how that
outcome changes a later recommendation.

This directory is the copy-ready planning root for the future standalone
`ai-cto-cockpit` repository. It intentionally contains no application
implementation. BMAD owns the accepted product, experience, architecture, and
quality baseline; Spec Kit owns every implementation slice.

## Product promise

The product is a persistent decision workspace, not a chat wrapper:

- recommendations cite immutable source revisions and expose uncertainty;
- typed hard constraints and final scoring are enforced by deterministic code;
- the model may populate reviewed UI components but may not emit executable UI;
- accepted outcomes become durable facts, while inferred preferences require
  confirmation;
- every memory influence on a recommendation is inspectable and correctable;
- the hosted demo uses only an original synthetic corpus, while local-data mode
  can connect to real private material with explicit inference-egress disclosure.

The canonical demonstration contains two related architecture decisions. The
visitor accepts or edits the first recommendation and can then see precisely
why the second recommendation changed.

## How the lifecycle works

1. The signed inception baseline is recorded in
   [`.ai-sdlc/inception-baseline.yaml`](.ai-sdlc/inception-baseline.yaml).
2. BMAD artifacts under [`_bmad-output/`](_bmad-output/) define the product,
   user experience, architecture spine, epics, and system quality contract.
3. The Spec Kit constitution and feature directories translate that baseline
   into small, testable delivery slices.
4. A cross-cutting product, UX, or architectural discovery must become a
   baseline change request before feature work continues.
5. A slice-local implementation discovery stays within its active Spec Kit
   feature.

The complete ownership and change-control rules live in
[`.ai-sdlc/WORKFLOW.md`](.ai-sdlc/WORKFLOW.md).

## Planned system

The target system uses:

- Next.js, React, CopilotKit, and AG-UI for the controlled decision workspace;
- FastAPI, Pydantic, and an explicit LangGraph workflow for orchestration;
- PostgreSQL as the system of record and durable job/outbox store;
- Qdrant as a rebuildable vector index;
- an OpenRouter-compatible provider adapter for hosted inference;
- a separate Python worker for ingestion, indexing, and memory consolidation;
- Docker Compose as the common local and single-VM deployment contract.

The system has two deployment profiles:

- **Public demo:** a fixed synthetic corpus, signed guest workspace, disabled
  uploads and live connectors, a 24-hour overlay, reset control, and strict
  cost/rate limits.
- **Local-data mode:** persistent local stores and read-only connectors for
  repositories, documents, GitHub, and bounded web sources. Retrieved context
  may be sent to the configured remote model provider; the UI must state this
  before activation.

## Copy into a fresh repository

Prerequisites are Git, `rsync`, and `uv`. From the root of this course
collection, the following block creates a sibling repository, preserves hidden
framework directories, validates the copy, and makes the initial commit when a
Git author identity is already configured. It runs in a subshell, fails on the
first error, and refuses to copy into any path that already exists:

```bash
(
  set -eu
  source_dir="experiments/ai-cto-cockpit"
  target_dir="../ai-cto-cockpit"

  [ -d "$source_dir" ] || {
    printf 'Source packet not found: %s\n' "$source_dir" >&2
    exit 1
  }
  if [ -e "$target_dir" ]; then
    printf 'Refusing to merge into existing target: %s\n' "$target_dir" >&2
    exit 1
  fi

  mkdir -- "$target_dir"
  rsync -a --exclude '__pycache__/' --exclude '*.pyc' \
    "$source_dir/" "$target_dir/"
  cd "$target_dir"
  git init
  git symbolic-ref HEAD refs/heads/main
  ./scripts/verify-bootstrap.sh
  git add .
  if git config user.name >/dev/null 2>&1 &&
    git config user.email >/dev/null 2>&1; then
    git commit -m "Bootstrap AI CTO Cockpit"
  else
    printf '%s\n' \
      'Packet verified and staged; configure your Git identity, then commit.'
  fi
)
```

If this directory is already the root of the fresh repository, start at
`git init` followed by `git symbolic-ref HEAD refs/heads/main`. The verifier
runs its unit suite, validates all authored
JSON, JSONL, and YAML, checks every evaluation case against Draft 2020-12 JSON
Schema, resolves evidence excerpts into the synthetic corpus, verifies
framework versions and baseline hashes, confirms active templates/workflows and
runtime pins, scans project-authored files for high-confidence secrets, and
checks reciprocal end-to-end traceability.

The framework adapters are already installed for Codex and Claude. Begin with
`speckit-analyze` against `specs/001-walking-skeleton/`, resolve any critical
inconsistency, execute T001, and then preserve the recorded RED result for T002
before implementing T003. Do not rerun a BMAD implementation loop. A bounded
first-task prompt is ready to paste from
[`BOOTSTRAP_PROMPT.md`](BOOTSTRAP_PROMPT.md).

## Start here

Before implementation, read these artifacts in order:

1. [`_bmad-output/planning-artifacts/product-brief.md`](_bmad-output/planning-artifacts/product-brief.md)
2. [`_bmad-output/planning-artifacts/prd.md`](_bmad-output/planning-artifacts/prd.md)
3. [`_bmad-output/planning-artifacts/EXPERIENCE.md`](_bmad-output/planning-artifacts/EXPERIENCE.md)
4. [`_bmad-output/planning-artifacts/ARCHITECTURE-SPINE.md`](_bmad-output/planning-artifacts/ARCHITECTURE-SPINE.md)
5. [`_bmad-output/planning-artifacts/implementation-readiness.md`](_bmad-output/planning-artifacts/implementation-readiness.md)
6. [`_bmad-output/test-artifacts/ai-quality-contract.md`](_bmad-output/test-artifacts/ai-quality-contract.md)
7. The Spec Kit constitution and `specs/001-walking-skeleton/`.
8. [`BOOTSTRAP_PROMPT.md`](BOOTSTRAP_PROMPT.md) for the first coding task.

Run the repository bootstrap verifier before accepting the copied packet. The
first production change must begin with the first failing acceptance test from
the walking-skeleton task list.

## Licensing and provenance

The bootstrap packet and future original implementation are released under the
[MIT License](LICENSE). Course notebooks and lab assets are sources of learning,
not redistribution inputs. Every borrowed idea must be re-expressed in original
project code and tests; every seed artifact must have documented provenance and
permission for public use. Vendored framework notices and exact license texts
are recorded in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
