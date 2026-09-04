#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

uv run --with pyyaml==6.0.3 --with jsonschema==4.25.1 \
  --with openapi-spec-validator==0.7.2 \
  python -m unittest discover -s tests -p 'test_*.py'
uv run scripts/verify_bootstrap.py --root "$project_root"
uv run scripts/verify_traceability.py --root "$project_root"
