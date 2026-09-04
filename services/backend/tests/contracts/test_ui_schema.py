from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DESIGN_UI_SCHEMA = (
    REPOSITORY_ROOT
    / "specs"
    / "001-walking-skeleton"
    / "contracts"
    / "ui-envelope.schema.json"
)
GENERATED_UI_SCHEMA = (
    REPOSITORY_ROOT / "contracts" / "generated" / "ui-envelope.schema.json"
)

PROSE_KEYS = frozenset({"description", "summary", "title"})
ORDER_INSENSITIVE_ARRAY_KEYS = frozenset(
    {"allOf", "anyOf", "enum", "oneOf", "required"}
)


def _semantic_contract(value: object, *, parent_key: str | None = None) -> object:
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        return {
            key: _semantic_contract(item, parent_key=key)
            for key, item in sorted(mapping.items())
            if key not in PROSE_KEYS or parent_key == "properties"
        }
    if isinstance(value, list):
        sequence = cast(list[object], value)
        items = [_semantic_contract(item) for item in sequence]
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


def _ui_envelope_model() -> type[Any]:
    module = importlib.import_module("ai_cto_cockpit.contracts.ui")
    return module.UiEnvelope


def _valid_envelope() -> dict[str, Any]:
    return {
        "schemaVersion": "1.0",
        "component": {
            "kind": "recommendation-summary",
            "id": "recommendation",
            "title": "Demonstration recommendation",
            "status": "demonstration",
            "selectedOptionId": "option-a",
            "rationale": "Option A has the highest deterministic fixture score.",
            "optionScores": [
                {"optionId": "option-a", "score": 80},
                {"optionId": "option-b", "score": 65},
            ],
            "disclaimer": "Demonstration output; no model provider was called.",
        },
        "actions": [
            {
                "kind": "view-evidence",
                "id": "view-evidence",
                "label": "View evidence",
                "enabled": False,
            }
        ],
        "meta": {
            "runId": "01890f9a-7bcd-7abc-8def-0123456789ab",
            "eventSequence": 3,
            "generatedBy": "deterministic-fixture",
            "fixtureVersion": "walking-skeleton-v1",
        },
    }


def _nested_value(payload: Any, path: tuple[str | int, ...]) -> Any:
    value = payload
    for segment in path:
        value = value[segment]
    return value


def test_generated_ui_schema_is_semantically_equivalent_to_feature_contract() -> None:
    assert GENERATED_UI_SCHEMA.is_file(), (
        "T004 RED: generated UI schema is absent at "
        "contracts/generated/ui-envelope.schema.json"
    )

    expected = json.loads(DESIGN_UI_SCHEMA.read_text(encoding="utf-8"))
    actual = json.loads(GENERATED_UI_SCHEMA.read_text(encoding="utf-8"))

    assert _semantic_contract(actual) == _semantic_contract(expected)


def test_generated_ui_schema_keeps_the_public_title_property() -> None:
    schema = cast(
        dict[str, Any],
        json.loads(GENERATED_UI_SCHEMA.read_text(encoding="utf-8")),
    )
    definitions = cast(dict[str, Any], schema["$defs"])
    recommendation = cast(
        dict[str, Any],
        definitions["recommendationSummary"],
    )
    properties = cast(dict[str, Any], recommendation["properties"])

    assert "title" in properties
    assert "title" in recommendation["required"]


def test_ui_envelope_accepts_the_closed_versioned_fixture() -> None:
    model = _ui_envelope_model()

    parsed = model.model_validate(_valid_envelope())

    assert parsed.model_dump(by_alias=True, mode="json") == _valid_envelope()
    serialized = json.loads(parsed.model_dump_json())
    assert serialized == _valid_envelope()
    assert "schema_version" not in serialized


@pytest.mark.parametrize(
    "object_path",
    [
        (),
        ("component",),
        ("component", "optionScores", 0),
        ("actions", 0),
        ("meta",),
    ],
)
def test_ui_envelope_rejects_unknown_fields_at_every_boundary(
    object_path: tuple[str | int, ...],
) -> None:
    model = _ui_envelope_model()
    payload = deepcopy(_valid_envelope())
    target = _nested_value(payload, object_path)
    target["unexpected"] = "must-fail-closed"

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("field_path", "invalid_value"),
    [
        (("schemaVersion",), "2.0"),
        (("component", "kind"), "arbitrary-html"),
        (("actions", 0, "kind"), "open-url"),
    ],
)
def test_ui_envelope_rejects_unknown_versions_components_and_actions(
    field_path: tuple[str | int, ...],
    invalid_value: str,
) -> None:
    model = _ui_envelope_model()
    payload = deepcopy(_valid_envelope())
    container = _nested_value(payload, field_path[:-1])
    container[field_path[-1]] = invalid_value

    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_ui_envelope_requires_schema_version() -> None:
    model = _ui_envelope_model()
    payload = _valid_envelope()
    del payload["schemaVersion"]

    with pytest.raises(ValidationError):
        model.model_validate(payload)

    schema = model.model_json_schema(by_alias=True)
    assert "schemaVersion" in schema["required"]
    assert schema["properties"]["schemaVersion"]["const"] == "1.0"


def test_ui_envelope_rejects_internal_python_field_names() -> None:
    model = _ui_envelope_model()
    payload = _valid_envelope()
    payload["schema_version"] = payload.pop("schemaVersion")

    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize(
    ("field_path", "invalid_value"),
    [
        (("component", "optionScores", 0, "score"), "80"),
        (("actions", 0, "enabled"), 0),
        (("meta", "eventSequence"), "3"),
    ],
)
def test_ui_envelope_rejects_scalar_type_coercion(
    field_path: tuple[str | int, ...],
    invalid_value: object,
) -> None:
    model = _ui_envelope_model()
    payload = _valid_envelope()
    container = _nested_value(payload, field_path[:-1])
    container[field_path[-1]] = invalid_value

    with pytest.raises(ValidationError):
        model.model_validate(payload)
