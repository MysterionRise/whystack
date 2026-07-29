PNPM := corepack pnpm
PYTHON_VERSION := 3.12.13
UV := uv

.PHONY: install test-compose-readiness toolchain-check

install:
	$(PNPM) install --frozen-lockfile
	$(UV) sync --project services/backend --locked --all-groups --no-install-project --python $(PYTHON_VERSION) --managed-python

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
