from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ai_cto_cockpit.contracts.run import (
    RunEvent,
    RunEventBase,
    RunQueuedEvent,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
DESIGN_OPENAPI = (
    REPOSITORY_ROOT / "specs" / "001-walking-skeleton" / "contracts" / "openapi.yaml"
)
GENERATED_OPENAPI = REPOSITORY_ROOT / "contracts" / "generated" / "openapi.json"

PROSE_KEYS = frozenset({"description", "summary", "title"})
ORDER_INSENSITIVE_ARRAY_KEYS = frozenset(
    {"allOf", "anyOf", "enum", "oneOf", "required", "security", "tags"}
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


def _property_contracts(
    value: object,
    property_name: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        properties = mapping.get("properties")
        if isinstance(properties, dict) and property_name in properties:
            contract = cast(dict[str, object], properties)[property_name]
            if isinstance(contract, dict):
                matches.append(cast(dict[str, Any], contract))
        for item in mapping.values():
            matches.extend(_property_contracts(item, property_name))
    elif isinstance(value, list):
        for item in cast(list[object], value):
            matches.extend(_property_contracts(item, property_name))
    return matches


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
    model = cast(type[BaseModel], getattr(module, model_name))

    schema = model.model_json_schema(by_alias=True)
    contracts = _property_contracts(schema, version_field)

    assert contracts
    assert all(contract.get("const") == expected_version for contract in contracts)


def test_run_events_require_their_contract_version() -> None:
    schema = TypeAdapter(RunEvent).json_schema(by_alias=True)
    contracts = _property_contracts(schema, "schemaVersion")

    assert contracts
    assert all(contract.get("const") == "1.0" for contract in contracts)


def _valid_run_event() -> dict[str, Any]:
    return {
        "runId": "01890f9a-7bcd-7abc-8def-0123456789ab",
        "sequence": 1,
        "kind": "run.queued",
        "schemaVersion": "1.0",
        "payload": {"status": "queued"},
        "createdAt": "2026-07-29T12:00:00Z",
    }


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"status": "failed"},
        {"status": "queued", "unexpected": "closed-contract"},
    ],
)
def test_run_event_rejects_mismatched_or_open_payloads(
    invalid_payload: dict[str, object],
) -> None:
    module = importlib.import_module("ai_cto_cockpit.contracts.run")
    adapter = TypeAdapter(module.RunEvent)
    payload = deepcopy(_valid_run_event())
    payload["payload"] = invalid_payload

    with pytest.raises(ValidationError):
        adapter.validate_python(payload)


def test_event_generation_rejects_unhandled_semantic_keywords() -> None:
    class EventWithUnhandledKeyword(RunQueuedEvent):
        model_config = ConfigDict(json_schema_extra={"minProperties": 7})

    module = importlib.import_module("ai_cto_cockpit.contracts.generate")
    module_symbols = vars(module)
    model_schema = cast(
        Callable[[type[BaseModel]], dict[str, object]],
        module_symbols["_model_schema"],
    )
    event_schema = cast(
        Callable[
            [type[BaseModel], dict[str, object]],
            dict[str, object],
        ],
        module_symbols["_event_schema"],
    )

    with pytest.raises(RuntimeError, match="unsupported event schema shape"):
        event_schema(
            EventWithUnhandledKeyword,
            model_schema(RunEventBase),
        )


def test_public_temporal_contracts_require_rfc3339_aware_values() -> None:
    config_module = importlib.import_module("ai_cto_cockpit.contracts.config")
    decision_module = importlib.import_module("ai_cto_cockpit.contracts.decision")
    payload = {
        "apiVersion": "v1",
        "mode": "public-demo",
        "capabilities": {
            "canCreateDecision": True,
            "canRunDecision": True,
            "canReplayRun": True,
            "canResetGuestWorkspace": True,
            "persistentWorkspace": False,
            "canUpload": False,
            "canUseLocalGit": False,
            "canUseGitHub": False,
            "canUseWeb": False,
        },
        "guestExpiresAt": "2026-07-29T12:00:00Z",
    }

    parsed = config_module.RuntimeConfig.model_validate(payload)
    serialized = parsed.model_dump(mode="json")

    assert serialized["apiVersion"] == "v1"
    assert "api_version" not in serialized

    naive = deepcopy(payload)
    naive["guestExpiresAt"] = "2026-07-29T12:00:00"
    with pytest.raises(ValidationError):
        config_module.RuntimeConfig.model_validate(naive)

    deadline: dict[str, object] = {
        "id": "delivery-date",
        "kind": "deadline",
        "label": "Delivery date",
        "severity": "hard",
        "date": "2026-08-31",
    }
    parsed_deadline = decision_module.DeadlineConstraint.model_validate(deadline)
    assert parsed_deadline.model_dump(mode="json")["date"] == "2026-08-31"

    deadline["date"] = 1_787_875_200
    with pytest.raises(ValidationError):
        decision_module.DeadlineConstraint.model_validate(deadline)


def test_boolean_literals_reject_numeric_substitutes() -> None:
    module = importlib.import_module("ai_cto_cockpit.contracts.config")

    with pytest.raises(ValidationError):
        module.ResetSessionResponse.model_validate(
            {
                "resetAccepted": 1,
                "guestExpiresAt": "2026-07-29T12:00:00Z",
            }
        )
