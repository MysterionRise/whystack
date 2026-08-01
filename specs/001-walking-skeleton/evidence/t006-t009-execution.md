# T006–T009 execution evidence

Status: retained from the live Spec Kit task-batch transcript on 2026-08-01.

Implementation snapshots:

- T006–T007: `74d7ca6c1e39b490d0c83b7f94320e5861bc55b8`
- T008–T009 base: `87ed59ec10a13d87b8aa0d9e58dde02741f067aa`
- T009 privacy/durability correction:
  `5b501c5ad44f957c75a418a3dab8e626721220f0`

Final commands ran on macOS arm64 with Node.js `24.18.0`, Corepack pnpm
`11.17.0`, Python `3.12.13`, uv `0.11.16`, Docker Engine `29.6.2`, and Docker
Compose `5.3.1`. The governance/docs snapshot is the commit containing this
evidence file.

This file is a structured record of the commands and observed results from the
active implementation run. The RED commands were not rerun after production
behavior existed. Where the original command was not redirected to a raw log,
the result below is intentionally described rather than presented as a verbatim
stdout transcript.

## T006 RED — closed frontend contract parser absent

Command:

```console
pnpm --dir apps/web test -- ui-envelope-contract.test.ts
```

This historical RED invocation used the shell's then-available pnpm shim. The
repository-canonical command is now `corepack pnpm --dir apps/web test --
ui-envelope-contract.test.ts`; the RED result is not recreated after GREEN.

Observed result: exit 1. Vitest found the new test file, then collection failed
because `../src/contracts/ui-envelope` did not exist. This was the expected
absence proving the parser and generated frontend contracts had not yet been
implemented.

Two later regressions also produced authentic RED results before their fixes:

- canonical object-identity fuzzing: 1 of 20 tests failed because nested object
  shapes could collide;
- hostile proxy fuzzing: 2 of 23 tests failed because reflection could escape
  the parser's closed failure result.

## T007 GREEN — generated frontend contracts

Commands:

```console
corepack pnpm --dir apps/web test -- ui-envelope-contract.test.ts
corepack pnpm --dir apps/web check
make contracts-check
```

Observed result: the parser suite passed 23 of 23 tests, frontend lint and type
checking passed, and the combined drift check passed 27 backend contract tests.
Two consecutive generations produced these identical SHA-256 values:

- canonical OpenAPI: `046b74d99b7993dd6327e328229538205103a353653e859b5f6daf55fe403175`
- canonical UI schema: `f35fbb1ed7e9035949912aa12f9396c3a43be09130ecc0d212637e840e713170`
- generated TypeScript: `c4dc447571034d9439d1ae5fcd675e83f37388367779f7cb85ec00dc85395905`

## T008 RED — persistence package and migration absent

Command:

```console
uv run --directory services/backend pytest \
  tests/unit/test_persistence_models.py \
  tests/integration/test_migrations.py -q
```

Observed result: exit 1. Both test modules were collected and failed with
`ModuleNotFoundError: ai_cto_cockpit.persistence`, proving migration `0001`,
models, repositories, and transaction helpers were absent.

The expanded async transaction tests later produced a second authentic RED:
four tests passed and two failed because SQLAlchemy's required `greenlet`
runtime was not installed. `IM-003` records that isolated tooling repair.

The final semantic audit then exposed the accepted operations gate's missing
non-sensitive deletion-completion record. Before adding that production schema,
the correction began with this focused test:

```console
uv run --directory services/backend pytest \
  tests/unit/test_persistence_models.py -q
```

Observed result: exit 1 during collection with `ImportError: cannot import name
'DeletionCompletion' from 'ai_cto_cockpit.persistence.models'`. The model and
migration were added only after that RED. The subsequent locked GREEN suite
also proves the completion row survives workspace/job cascade and enforces its
non-sensitive field and uniqueness boundaries.

## T009 GREEN — canonical persistence

Fresh results after the privacy-boundary correction:

```console
uv run --directory services/backend --locked pytest \
  tests/unit/test_persistence_models.py \
  tests/integration/test_migrations.py -q
make check
make contracts-check
./scripts/verify-bootstrap.sh
make test-compose-readiness
```

- combined persistence suite: 52 of 52 passed;
- `make check`: Ruff lint and formatting, Pyright, frontend ESLint, and
  TypeScript all passed;
- `make contracts-check`: generated backend/frontend artifacts were current and
  27 of 27 backend contract tests passed;
- bootstrap verifier: 37 of 37 tests, packet validation, and traceability
  validation passed;
- Compose readiness: 1 of 1 passed, including exact database/repository head
  equality at `0001_walking_skeleton`.

The final Make gates ran with the repository-pinned Node.js `24.18.0` and
Corepack pnpm `11.17.0`. `make node-toolchain-check` is now an explicit
prerequisite of installation, quality, and contract targets.
