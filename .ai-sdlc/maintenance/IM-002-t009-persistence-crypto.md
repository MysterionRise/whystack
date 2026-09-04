# IM-002: T009 persistence cryptography locks

- Status: accepted and verified
- Date: 2026-08-01
- Baseline: `IB-002`
- Delivery feature: `001-walking-skeleton`
- Owning task: `T009`
- Authorization: accepted Whystack improvement roadmap

## Reason

T009 stores the replacement guest token needed for the ten-minute exact-reset
replay window. The accepted task requires UUIDv7 generation and AES-256-GCM
authenticated encryption before persistence production code begins.

This isolated maintenance packet adds only the task-owned direct dependencies
`uuid6==2025.0.1` and `cryptography==49.0.0`. It does not change product scope,
experience authority, deployment profiles, canonical storage, the bounded
reset-replay trust boundary, or any quality threshold. PostgreSQL remains
canonical and Qdrant remains derived and readiness-only in feature 001.

## Authorized changes

- Add `uuid6==2025.0.1` for server-generated canonical UUIDv7 identifiers.
- Add `cryptography==49.0.0` for AES-256-GCM using a fresh random 96-bit nonce
  and the exact associated data in `data-model.md`.
- Regenerate only `services/backend/uv.lock` from the backend manifest.
- Record both direct pins in `.ai-sdlc/toolchain.lock.yaml` and enforce them in
  the bootstrap verifier.
- Update only the changed toolchain hash in active baseline `IB-002`.

## Before-change hashes

| Artifact | SHA-256 |
|---|---|
| `.ai-sdlc/inception-baseline.yaml` | `d0c402bc372cf188f3f8f8283f605cb3e6d1685c4c77ccbb27a26324015842d6` |
| `.ai-sdlc/toolchain.lock.yaml` | `c93843daabfa0fe5f932c90703cc0e9c33e8b375068399ab897d24e4805197d4` |
| `.ai-sdlc/source-manifest.yaml` | `3d8645ce1d7cee7e40399c4a7c646c3409b28eadba51e893a661a8a05c6961ea` |
| `services/backend/pyproject.toml` | `4dc0fe445371265127758917cd548ec111b8501c04664862e8245306d9acf3d9` |
| `services/backend/uv.lock` | `e79cba8e1eb3c050de2c0be650f3e3ba426a1d0e0d6efb302299605c3f6b3e9b` |

## Verification evidence

- `uv lock --project services/backend --python 3.12.13 --managed-python`:
  resolved 62 packages and added only the approved direct packages plus their
  `cffi` and `pycparser` transitive requirements.
- `uv lock --project services/backend --check --python 3.12.13
  --managed-python`: passed.
- `uv sync --project services/backend --locked --all-groups --python 3.12.13
  --managed-python`: passed and installed the exact direct versions.
- `./scripts/verify-bootstrap.sh`: 36 verifier tests passed; packet and
  traceability validation passed.
- The unchanged T008 command still fails only because
  `ai_cto_cockpit.persistence` and migration `0001` are absent. Both test files
  are collected and fail with `ModuleNotFoundError`; the RED evidence is
  preserved across maintenance.
- `pnpm-lock.yaml` remains unchanged at
  `1795096ef5b72bda781bb0d128a60e115b701be143313d862a1a24d6ff9f6737`.

## After-change hashes

| Artifact | SHA-256 |
|---|---|
| `.ai-sdlc/inception-baseline.yaml` | `f528e8d379983c940ae80eff2f268b0256ea37706406a98180042e625a204368` |
| `.ai-sdlc/toolchain.lock.yaml` | `00ebc40a56f38b826dd7d58cddcc5c773e8c2321f979633ffc1494d52a7e659d` |
| `.ai-sdlc/source-manifest.yaml` | `3d8645ce1d7cee7e40399c4a7c646c3409b28eadba51e893a661a8a05c6961ea` |
| `services/backend/pyproject.toml` | `62a52cb86fa2b46bed040b07ba05d3e0274603ca43f0ac19c4296c816f27a0c7` |
| `services/backend/uv.lock` | `11c31561d2706467b4d9a0db58c6f53d12c945c4683c56ab9ac1a9be2eecc63f` |
