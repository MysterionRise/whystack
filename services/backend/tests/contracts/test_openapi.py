from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DESIGN_OPENAPI = (
    REPOSITORY_ROOT / "specs" / "001-walking-skeleton" / "contracts" / "openapi.yaml"
)
GENERATED_OPENAPI = REPOSITORY_ROOT / "contracts" / "generated" / "openapi.json"

PROSE_KEYS = frozenset({"description", "summary", "title"})
ORDER_INSENSITIVE_ARRAY_KEYS = frozenset(
    {"allOf", "anyOf", "enum", "oneOf", "required", "security", "tags"}
)


def _semantic_contract(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            key: _semantic_contract(item, parent_key=key)
            for key, item in sorted(value.items())
            if key not in PROSE_KEYS
        }
    if isinstance(value, list):
        items = [_semantic_contract(item) for item in value]
        if parent_key in ORDER_INSENSITIVE_ARRAY_KEYS:
            return sorted(
                items,
                key=lambda item: json.dumps(
                    item,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        return items
    return value


def test_generated_openapi_is_semantically_equivalent_to_feature_contract() -> None:
    assert GENERATED_OPENAPI.is_file(), (
        "T004 RED: generated OpenAPI is absent at contracts/generated/openapi.json"
    )

    expected = yaml.safe_load(DESIGN_OPENAPI.read_text(encoding="utf-8"))
    actual = json.loads(GENERATED_OPENAPI.read_text(encoding="utf-8"))

    assert _semantic_contract(actual) == _semantic_contract(expected)


@pytest.mark.parametrize(
    ("module_name", "model_name", "version_field", "expected_version"),
    [
        (
            "ai_cto_cockpit.contracts.config",
            "RuntimeConfig",
            "apiVersion",
            "v1",
        ),
        (
            "ai_cto_cockpit.contracts.decision",
            "DecisionFrameInput",
            "schemaVersion",
            "1.0",
        ),
        (
            "ai_cto_cockpit.contracts.decision",
            "DecisionFrameView",
            "schemaVersion",
            "1.0",
        ),
        (
            "ai_cto_cockpit.contracts.run",
            "RunEventView",
            "schemaVersion",
            "1.0",
        ),
        (
            "ai_cto_cockpit.contracts.ui",
            "UiEnvelope",
            "schemaVersion",
            "1.0",
        ),
    ],
)
def test_public_models_require_their_contract_version(
    module_name: str,
    model_name: str,
    version_field: str,
    expected_version: str,
) -> None:
    module = importlib.import_module(module_name)
    model = getattr(module, model_name)

    schema = model.model_json_schema(by_alias=True)

    assert version_field in schema["required"]
    assert schema["properties"][version_field]["const"] == expected_version
