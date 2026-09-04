# IM-001: Walking-Skeleton Tooling Compatibility

- Status: accepted and verified
- Date: 2026-07-29
- Baseline: `IB-001`
- Delivery feature: `001-walking-skeleton`
- Authorization: accepted Whystack improvement roadmap

## Reason

The first implementation slice exposed a compatibility mismatch between ESLint
10 and the pinned Next.js 16 ESLint configuration. The same maintenance batch
makes the now-existing backend source tree installable and adds the deterministic
contract-generation YAML dependency required by T005.

The roadmap originally placed the ESLint pin immediately before T007. It is
advanced, without changing its owner, because this same pre-T005 repair makes
`make check` blocking in CI and that gate cannot load the accepted Next.js
configuration under ESLint 10. No lint rule or threshold is disabled.

This is an isolated tooling maintenance change. It does not alter product scope,
experience authority, trust boundaries, canonical storage, quality thresholds,
or the public-demo capability boundary. PostgreSQL remains canonical and Qdrant
remains derived. No BMAD implementation workflow is required or authorized.
The inception manifest's non-authoritative progress field is reconciled from
`not-started-by-design` to `feature-001-in-progress-through-t004`; no accepted
baseline scope or artifact hash is changed by that status update.

## Authorized changes

- Replace frontend `eslint==10.8.0` with `eslint==9.39.2`, retaining
  `eslint-config-next==16.2.12`, the Next.js CLI configuration, and all rules.
- Add `uv_build==0.11.16` as the backend build system and install the
  `ai_cto_cockpit` source package instead of relying on `PYTHONPATH`.
- Add direct `pyyaml==6.0.3` support for deterministic T005 contract generation
  and align the bootstrap verifier's isolated YAML dependency.
- Add a pinned `actions/setup-node` v6.4.0 action and make `make check` blocking
  in continuous integration.
- Inventory the implemented runtime and tooling paths in the source manifest.

## Before-change hashes

| Artifact | SHA-256 |
|---|---|
| `.ai-sdlc/toolchain.lock.yaml` | `e287876db48df6e761306fcc26a33d9e188851171728e3861db25e7cbb05cfa2` |
| `.ai-sdlc/source-manifest.yaml` | `5ce190d0cbd5b0915f7f8c963fd0de1e8b14ec271ddd092dd05bade81d6c7ba3` |
| `pnpm-lock.yaml` | `76360a7b9b448d3696e5e285d96888e8b6e2302807b940c250aa54a40e5fe702` |
| `services/backend/uv.lock` | `6ab4f069dc17e3d1ae8b66b2578782ff7b93d2a243d5dd9c525daffeac9875fb` |
| `apps/web/package.json` | `1ff32cc50c00894de32c21d649353ad6b3009ec5bff17a78520062ab42fb8ed4` |
| `services/backend/pyproject.toml` | `9d3c672b18275e9e52267064567591cddce6ddcf8d19d6edabea97c369f2854c` |

## Required finalization

Regenerate `pnpm-lock.yaml` and `services/backend/uv.lock` only from the changed
manifests. Then record the resulting toolchain and source-manifest hashes in
`.ai-sdlc/inception-baseline.yaml` and run the bootstrap verifier, frozen
installs, `make check`, backend import checks, and the Compose-readiness test.
The existing T004 RED evidence remains authoritative until the explicitly
scoped T005 implementation begins.

## Verification evidence

- `./scripts/verify-bootstrap.sh`: 36 verifier tests passed; packet and
  traceability validation passed.
- Frozen `pnpm` install under Node `24.18.0` and pnpm `11.17.0`: passed.
- Locked backend sync under Python `3.12.13` and uv `0.11.16`: passed and
  installed the project package.
- `make check`: Ruff lint/format, strict Pyright, ESLint, and TypeScript passed.
- Backend import without `PYTHONPATH`: passed.
- `tests/e2e/test_compose_readiness.py`: passed with the rebuilt non-editable
  backend container package.

## After-change hashes

| Artifact | SHA-256 |
|---|---|
| `.ai-sdlc/toolchain.lock.yaml` | `98162533dddfda2dc836e7dd34e3318335fcfb046d9617480ecfd2150f03deb4` |
| `.ai-sdlc/source-manifest.yaml` | `1428d4b7ba25d0310002e2fc5ff69bb64743be284d05c98b634bb5b7d3287b8e` |
| `pnpm-lock.yaml` | `1795096ef5b72bda781bb0d128a60e115b701be143313d862a1a24d6ff9f6737` |
| `services/backend/uv.lock` | `e79cba8e1eb3c050de2c0be650f3e3ba426a1d0e0d6efb302299605c3f6b3e9b` |
