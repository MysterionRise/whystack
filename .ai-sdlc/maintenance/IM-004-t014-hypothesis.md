# IM-004: T014 Hypothesis property-test lock

- Status: accepted and verified
- Date: 2026-08-29
- Baseline: `IB-002`
- Delivery feature: `001-walking-skeleton`
- Owning task: `T014`
- Authorization: accepted Whystack improvement roadmap

## Reason

T014 introduces generative checks for immutable decision revisions,
idempotency, concurrency, and lossless integer weight normalization. The
accepted task requires Hypothesis immediately before those property tests are
written.

This isolated maintenance packet adds only the task-owned direct development
dependency `hypothesis==6.160.0`. It does not add application behavior or
change product scope, experience authority, canonical storage, workspace
scope, the public-demo capability boundary, or any quality threshold.
PostgreSQL remains canonical and Qdrant remains derived and readiness-only in
feature 001.

## Authorized changes

- Add `hypothesis==6.160.0` to the backend development dependency group.
- Regenerate only `services/backend/uv.lock` from the backend manifest.
- Record the direct pin in `.ai-sdlc/toolchain.lock.yaml` and enforce it in the
  bootstrap verifier and its behavioral test.
- Update only the changed toolchain hash in active baseline `IB-002`.

## Before-change hashes

| Artifact | SHA-256 |
|---|---|
| `.ai-sdlc/inception-baseline.yaml` | `b527669fe34b6311a893c8db00a68f18a507530f005ad9f5d79040a3f1e81bce` |
| `.ai-sdlc/toolchain.lock.yaml` | `c44ae82ef68369cfa87cc0d8708ee5231069afa3cecacd1830d7c0bcc29927d1` |
| `.ai-sdlc/source-manifest.yaml` | `3d8645ce1d7cee7e40399c4a7c646c3409b28eadba51e893a661a8a05c6961ea` |
| `services/backend/pyproject.toml` | `fd5f68a4e63f7523983979046ffbfa62ae1cac2693cbdc851520b16d68534822` |
| `services/backend/uv.lock` | `9eae0491ff6c2e8a983760cf892ad897acc67c18c235ae22f40552a52627ddff` |
| `scripts/verify_bootstrap.py` | `dc4e23684faa5683abd6aea976b5627739b0e0d14729c53e346bc966a5ff6a8b` |
| `tests/test_bootstrap_validation.py` | `b7648e29f1ac227869f3fffd3066a0e4bce3ced1adbff3ebb210a6da7d1ca71b` |

## Verification evidence

- Pinned uv `0.11.16` with Python `3.12.13` regenerated the backend lock:
  64 packages resolved, adding only Hypothesis `6.160.0` and its required
  `sortedcontainers==2.4.0` transitive dependency.
- `uv lock --project services/backend --check --python 3.12.13
  --managed-python`: passed.
- `uv sync --project services/backend --locked --all-groups --python 3.12.13
  --managed-python`: passed.
- Locked runtime import reported `hypothesis=6.160.0`.
- `./scripts/verify-bootstrap.sh`: all 37 verifier tests passed; packet and
  traceability validation passed.
- The unchanged T013 focused suite still reached migrated disposable
  PostgreSQL and failed all 63 cases only at the absent decision routes with
  HTTP 404. No application behavior entered this maintenance packet.
- `pnpm-lock.yaml` remains unchanged at
  `1795096ef5b72bda781bb0d128a60e115b701be143313d862a1a24d6ff9f6737`.

## After-change hashes

| Artifact | SHA-256 |
|---|---|
| `.ai-sdlc/inception-baseline.yaml` | `faed8d775061abd4fe3782cd12f02e6b5d7a72bd05880212fc147dacd52a4944` |
| `.ai-sdlc/toolchain.lock.yaml` | `56634cc2e9b2a93fb08bca66141f00aa4438cb52403baeadfbf3c923ba01e101` |
| `.ai-sdlc/source-manifest.yaml` | `3d8645ce1d7cee7e40399c4a7c646c3409b28eadba51e893a661a8a05c6961ea` |
| `services/backend/pyproject.toml` | `f6b9fafecda2f56bd6b5fffeeef739831d2d17ffd7fc225b08528c3da08ff89b` |
| `services/backend/uv.lock` | `b94fde74332da628e42286c25ff44ec5d8bef69f93ee22c73758d5cf2cb8ce0c` |
| `scripts/verify_bootstrap.py` | `569655f617b07671ac98048d4c0d4f7ef9e6452cdda9babcfcc9d207d48ff8b6` |
| `tests/test_bootstrap_validation.py` | `e690482be3137968ac0f1234157f147bfc26b205d484e7f586a2e693908f1906` |

These hashes define the isolated T014 dependency-maintenance boundary. The
property-test packet that follows is a separate Spec Kit delivery commit.
