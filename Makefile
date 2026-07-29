PNPM := corepack pnpm
PYTHON_VERSION := 3.12.13
UV := uv

.PHONY: check contracts-check contracts-generate install test-compose-readiness toolchain-check

install:
	$(PNPM) install --frozen-lockfile
	$(UV) sync --project services/backend --locked --all-groups --python $(PYTHON_VERSION) --managed-python

check:
	$(UV) run --project services/backend --no-sync ruff check services/backend/src services/backend/tests tests/e2e
	$(UV) run --project services/backend --no-sync ruff format --check services/backend/src services/backend/tests tests/e2e
	$(PNPM) exec pyright
	$(PNPM) --dir apps/web check

contracts-generate:
	$(UV) run --project services/backend --locked python -m ai_cto_cockpit.contracts.generate --write

contracts-check:
	$(UV) run --project services/backend --locked python -m ai_cto_cockpit.contracts.generate --check
	$(UV) run --project services/backend --locked pytest services/backend/tests/contracts

toolchain-check:
	node --version
	$(UV) --version
	$(PNPM) --version
	$(UV) run --project services/backend --no-sync pytest --version
	$(UV) run --project services/backend --no-sync ruff --version
	$(PNPM) exec pyright --version
	$(PNPM) --dir apps/web exec vitest --version
	$(PNPM) --dir apps/web exec playwright --version
	$(PNPM) --dir apps/web exec eslint --version
	$(PNPM) --dir apps/web exec tsc --version

test-compose-readiness:
	$(UV) run --project services/backend --no-sync pytest tests/e2e/test_compose_readiness.py
