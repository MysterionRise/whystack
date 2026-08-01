# IM-003: T009 SQLAlchemy asyncio runtime extra

- Status: accepted and verified
- Date: 2026-08-01
- Baseline: `IB-002`
- Delivery feature: `001-walking-skeleton`
- Owning task: `T009`
- Authorization: implementation discovery within the accepted T009 transaction boundary

## Reason

T009 implements caller-owned transactions with SQLAlchemy `AsyncSession`.
The locked `sqlalchemy==2.0.51` version was correct, but its required `asyncio`
extra was not selected. On macOS arm64, the base package does not install
`greenlet`, so the behavioral transaction tests failed before database work
with `ValueError: the greenlet library is required`.

This maintenance packet retains SQLAlchemy `2.0.51` and changes only its
installation form to `sqlalchemy[asyncio]==2.0.51`. The regenerated lock selects
the exact transitive `greenlet==3.5.4`. It changes no product scope, persistence
authority, security boundary, quality threshold, or accepted application
behavior.

## Authorized changes

- Select the official SQLAlchemy `asyncio` extra without changing the pinned
  SQLAlchemy version.
- Regenerate only `services/backend/uv.lock` from the backend manifest.
- Record the extra in `.ai-sdlc/toolchain.lock.yaml` and enforce that exact
  governance key in the bootstrap verifier.
- Update only the changed toolchain hash in active baseline `IB-002`.

## Before-change hashes

| Artifact | SHA-256 |
|---|---|
| `.ai-sdlc/inception-baseline.yaml` | `f528e8d379983c940ae80eff2f268b0256ea37706406a98180042e625a204368` |
| `.ai-sdlc/toolchain.lock.yaml` | `00ebc40a56f38b826dd7d58cddcc5c773e8c2321f979633ffc1494d52a7e659d` |
| `.ai-sdlc/source-manifest.yaml` | `3d8645ce1d7cee7e40399c4a7c646c3409b28eadba51e893a661a8a05c6961ea` |
| `services/backend/pyproject.toml` | `62a52cb86fa2b46bed040b07ba05d3e0274603ca43f0ac19c4296c816f27a0c7` |
| `services/backend/uv.lock` | `11c31561d2706467b4d9a0db58c6f53d12c945c4683c56ab9ac1a9be2eecc63f` |

## Verification evidence

- Pre-change expanded T009 integration suite: four passed and two transaction
  tests failed because `greenlet` was absent.
- `uv lock --project services/backend --python 3.12.13 --managed-python`:
  resolved 62 packages with SQLAlchemy's official `asyncio` extra.
- `uv sync --project services/backend --locked --all-groups --python 3.12.13
  --managed-python`: passed.
- Locked runtime import: `greenlet=3.5.4 sqlalchemy=2.0.51`.
- `./scripts/verify-bootstrap.sh`: 36 verifier tests passed; packet and
  traceability validation passed.
- Expanded T008 suite against disposable PostgreSQL: 46 tests passed,
  including transaction commit/rollback, workspace isolation, and exact
  migration-head behavior.
- `make check` and `make contracts-check`: passed.
- `make test-compose-readiness`: passed with all five services healthy and
  exact database/repository head equality at `0001_walking_skeleton`.

## After-change hashes

| Artifact | SHA-256 |
|---|---|
| `.ai-sdlc/inception-baseline.yaml` | `ac27717f0708753d8c2c6e8b4812dfc9f54aea7a740527f3f9bb8502be34e3e1` |
| `.ai-sdlc/toolchain.lock.yaml` | `c44ae82ef68369cfa87cc0d8708ee5231069afa3cecacd1830d7c0bcc29927d1` |
| `.ai-sdlc/source-manifest.yaml` | `3d8645ce1d7cee7e40399c4a7c646c3409b28eadba51e893a661a8a05c6961ea` |
| `services/backend/pyproject.toml` | `fd5f68a4e63f7523983979046ffbfa62ae1cac2693cbdc851520b16d68534822` |
| `services/backend/uv.lock` | `9eae0491ff6c2e8a983760cf892ad897acc67c18c235ae22f40552a52627ddff` |

These are the hashes at the isolated maintenance boundary. Later delivery-only
updates such as advancing `application_status` do not rewrite this historical
record.
