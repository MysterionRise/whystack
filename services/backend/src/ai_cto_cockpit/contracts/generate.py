from __future__ import annotations

import argparse
import difflib
import json
import sys
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, TypeAdapter

from ._base import (
    EnteredWeight,
    NormalizedWeight,
    Slug,
    Uuid7,
)
from .config import (
    Capabilities,
    Liveness,
    Readiness,
    ResetSessionResponse,
    RuntimeConfig,
)
from .decision import (
    BudgetConstraint,
    CapabilityConstraint,
    Constraint,
    ConstraintBase,
    CriterionInput,
    CriterionView,
    DeadlineConstraint,
    DecisionFrameInput,
    DecisionFrameView,
    DecisionOption,
    DecisionView,
    DeploymentModeConstraint,
    ForbiddenVendorConstraint,
    LicenseConstraint,
    ResidencyConstraint,
)
from .errors import ApiError, FieldError
from .run import (
    RunCompletedEvent,
    RunCompletedPayload,
    RunEvent,
    RunEventBase,
    RunFailedEvent,
    RunFailurePayload,
    RunQueuedEvent,
    RunQueuedPayload,
    RunStartedEvent,
    RunStartedPayload,
    RunView,
    UiEnvelopeEvent,
)
from .ui import (
    OptionScore,
    RecommendationSummary,
    UiEnvelope,
    UiEnvelopeMeta,
    ViewEvidenceAction,
)

JsonObject = dict[str, object]

OPENAPI_REF_TEMPLATE = "#/components/schemas/{model}"
UI_REF_TEMPLATE = "#/$defs/{model}"
UI_DEFINITION_NAMES = {
    "OptionScore": "optionScore",
    "RecommendationSummary": "recommendationSummary",
    "UiEnvelopeMeta": "envelopeMeta",
    "ViewEvidenceAction": "viewEvidenceAction",
}
OPENAPI_COMPONENT_NAMES = frozenset(
    {
        "ApiError",
        "BudgetConstraint",
        "Capabilities",
        "CapabilityConstraint",
        "Constraint",
        "ConstraintBase",
        "CriterionInput",
        "CriterionView",
        "DeadlineConstraint",
        "DecisionFrameInput",
        "DecisionFrameView",
        "DecisionOption",
        "DecisionView",
        "DeploymentModeConstraint",
        "EnteredWeight",
        "FieldError",
        "ForbiddenVendorConstraint",
        "LicenseConstraint",
        "Liveness",
        "NormalizedWeight",
        "OptionScore",
        "Readiness",
        "RecommendationSummary",
        "ResetSessionResponse",
        "ResidencyConstraint",
        "RunCompletedEvent",
        "RunCompletedPayload",
        "RunEvent",
        "RunEventBase",
        "RunFailedEvent",
        "RunFailurePayload",
        "RunQueuedEvent",
        "RunQueuedPayload",
        "RunStartedEvent",
        "RunStartedPayload",
        "RunView",
        "RuntimeConfig",
        "Slug",
        "UiEnvelope",
        "UiEnvelopeEvent",
        "UiEnvelopeMeta",
        "Uuid7",
        "ViewEvidenceAction",
    }
)
EVENT_SCHEMA_KEYS = frozenset(
    {"type", "additionalProperties", "properties", "required"}
)


def _repository_root() -> Path:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "specs" / "001-walking-skeleton" / "contracts").is_dir():
            return candidate
    raise RuntimeError("run contract generation from the repository checkout")


def _json_object(value: object, *, context: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(f"{context} must be an object")
    return cast(JsonObject, value)


def _normalize_schema(
    value: object,
    *,
    parent_key: str | None = None,
) -> object:
    if isinstance(value, list):
        sequence = cast(list[object], value)
        return [_normalize_schema(item, parent_key=parent_key) for item in sequence]
    if not isinstance(value, dict):
        return value

    mapping = cast(JsonObject, value)
    normalized: JsonObject = {
        key: _normalize_schema(item, parent_key=key)
        for key, item in mapping.items()
        if key != "$defs" and (key != "title" or parent_key == "properties")
    }
    if "const" in normalized:
        normalized.pop("type", None)

    nullable = normalized.get("anyOf")
    if isinstance(nullable, list):
        nullable_variants = cast(list[object], nullable)
    else:
        nullable_variants = []
    if len(nullable_variants) == 2 and any(
        isinstance(item, dict) and cast(JsonObject, item).get("type") == "null"
        for item in nullable_variants
    ):
        normalized["oneOf"] = normalized.pop("anyOf")

    return normalized


def _model_schema(model: type[BaseModel]) -> JsonObject:
    raw = model.model_json_schema(
        by_alias=True,
        ref_template=OPENAPI_REF_TEMPLATE,
    )
    return _openapi_schema_from_raw(
        _json_object(raw, context=model.__name__),
        context=model.__name__,
    )


def _adapter_schema(adapter_type: Any) -> JsonObject:
    raw = TypeAdapter(adapter_type).json_schema(
        by_alias=True,
        ref_template=OPENAPI_REF_TEMPLATE,
    )
    context = str(adapter_type)
    return _openapi_schema_from_raw(
        _json_object(raw, context=context),
        context=context,
    )


def _openapi_schema_from_raw(raw: JsonObject, *, context: str) -> JsonObject:
    definitions_value = raw.get("$defs", {})
    definitions = _json_object(
        definitions_value,
        context=f"{context} definitions",
    )
    inline_replacements = {
        f"#/components/schemas/{name}": _json_object(
            _normalize_schema(schema),
            context=f"{context}.{name}",
        )
        for name, schema in definitions.items()
        if name not in OPENAPI_COMPONENT_NAMES
    }
    normalized = _normalize_schema(raw)
    return _json_object(
        _replace_refs(normalized, inline_replacements),
        context=context,
    )


def _named_alias_schema(alias: Any, name: str) -> JsonObject:
    raw = _json_object(
        TypeAdapter(alias).json_schema(
            by_alias=True,
            ref_template=OPENAPI_REF_TEMPLATE,
        ),
        context=name,
    )
    definitions = raw.get("$defs")
    schema = (
        cast(dict[str, Any], definitions).get(name)
        if isinstance(definitions, dict)
        else raw
    )
    return _json_object(_normalize_schema(schema), context=name)


def _constraint_schema(
    model: type[BaseModel],
) -> JsonObject:
    return {
        "allOf": [
            {"$ref": "#/components/schemas/ConstraintBase"},
            _model_schema(model),
        ]
    }


def _event_schema(
    model: type[BaseModel],
    base_schema: JsonObject,
) -> JsonObject:
    generated = _model_schema(model)
    for schema_name, schema in (
        ("RunEventBase", base_schema),
        (model.__name__, generated),
    ):
        schema_keys = frozenset(schema)
        if schema_keys != EVENT_SCHEMA_KEYS:
            unsupported = sorted(schema_keys.difference(EVENT_SCHEMA_KEYS))
            missing = sorted(EVENT_SCHEMA_KEYS.difference(schema_keys))
            raise RuntimeError(
                f"{schema_name} has unsupported event schema shape: "
                f"unsupported={unsupported}, missing={missing}"
            )

    for keyword in ("type", "additionalProperties"):
        if generated.get(keyword) != base_schema.get(keyword):
            raise RuntimeError(f"{model.__name__}.{keyword} differs from RunEventBase")

    generated_required = generated.get("required")
    base_required = base_schema.get("required")
    if not isinstance(generated_required, list) or not isinstance(
        base_required,
        list,
    ):
        raise RuntimeError("event schemas must declare required fields")
    generated_required_items = cast(list[object], generated_required)
    base_required_items = cast(list[object], base_required)
    if not all(isinstance(item, str) for item in generated_required_items):
        raise RuntimeError(f"{model.__name__} has a non-string required field")
    if not all(isinstance(item, str) for item in base_required_items):
        raise RuntimeError("RunEventBase has a non-string required field")
    generated_required_names = {cast(str, item) for item in generated_required_items}
    base_required_names = {cast(str, item) for item in base_required_items}
    if generated_required_names != base_required_names:
        raise RuntimeError(f"{model.__name__} required fields differ from RunEventBase")

    properties = _json_object(
        generated.get("properties"),
        context=f"{model.__name__} properties",
    )
    base_properties = _json_object(
        base_schema.get("properties"),
        context="RunEventBase properties",
    )
    if set(properties) != set(base_properties):
        raise RuntimeError(f"{model.__name__} properties differ from RunEventBase")
    specialized_properties = {
        name: schema
        for name, schema in properties.items()
        if schema != base_properties[name]
    }
    if not specialized_properties:
        raise RuntimeError(f"{model.__name__} does not specialize RunEventBase")

    return {
        "allOf": [
            {"$ref": "#/components/schemas/RunEventBase"},
            {
                "type": "object",
                "properties": specialized_properties,
            },
        ]
    }


def _openapi_schemas() -> JsonObject:
    constraint_base = _model_schema(ConstraintBase)
    run_event_base = _model_schema(RunEventBase)

    return {
        "RuntimeConfig": _model_schema(RuntimeConfig),
        "Capabilities": _model_schema(Capabilities),
        "ResetSessionResponse": _model_schema(ResetSessionResponse),
        "DecisionFrameInput": _model_schema(DecisionFrameInput),
        "DecisionFrameView": _model_schema(DecisionFrameView),
        "DecisionOption": _model_schema(DecisionOption),
        "CriterionInput": _model_schema(CriterionInput),
        "CriterionView": _model_schema(CriterionView),
        "EnteredWeight": _named_alias_schema(EnteredWeight, "EnteredWeight"),
        "NormalizedWeight": _named_alias_schema(
            NormalizedWeight,
            "NormalizedWeight",
        ),
        "Constraint": _adapter_schema(Constraint),
        "ConstraintBase": constraint_base,
        "BudgetConstraint": _constraint_schema(BudgetConstraint),
        "DeadlineConstraint": _constraint_schema(DeadlineConstraint),
        "CapabilityConstraint": _constraint_schema(CapabilityConstraint),
        "ForbiddenVendorConstraint": _constraint_schema(ForbiddenVendorConstraint),
        "LicenseConstraint": _constraint_schema(LicenseConstraint),
        "ResidencyConstraint": _constraint_schema(ResidencyConstraint),
        "DeploymentModeConstraint": _constraint_schema(DeploymentModeConstraint),
        "DecisionView": _model_schema(DecisionView),
        "RunView": _model_schema(RunView),
        "RunEvent": _adapter_schema(RunEvent),
        "RunEventBase": run_event_base,
        "RunQueuedEvent": _event_schema(RunQueuedEvent, run_event_base),
        "RunStartedEvent": _event_schema(RunStartedEvent, run_event_base),
        "UiEnvelopeEvent": _event_schema(UiEnvelopeEvent, run_event_base),
        "RunCompletedEvent": _event_schema(RunCompletedEvent, run_event_base),
        "RunFailedEvent": _event_schema(RunFailedEvent, run_event_base),
        "RunQueuedPayload": _model_schema(RunQueuedPayload),
        "RunStartedPayload": _model_schema(RunStartedPayload),
        "RunCompletedPayload": _model_schema(RunCompletedPayload),
        "RunFailurePayload": _model_schema(RunFailurePayload),
        "UiEnvelope": _model_schema(UiEnvelope),
        "RecommendationSummary": _model_schema(RecommendationSummary),
        "OptionScore": _model_schema(OptionScore),
        "ViewEvidenceAction": _model_schema(ViewEvidenceAction),
        "UiEnvelopeMeta": _model_schema(UiEnvelopeMeta),
        "Liveness": _model_schema(Liveness),
        "Readiness": _model_schema(Readiness),
        "ApiError": _model_schema(ApiError),
        "FieldError": _model_schema(FieldError),
        "Slug": _named_alias_schema(Slug, "Slug"),
        "Uuid7": _named_alias_schema(Uuid7, "Uuid7"),
    }


def _replace_refs(
    value: object,
    replacements: Mapping[str, JsonObject],
) -> object:
    if isinstance(value, list):
        sequence = cast(list[object], value)
        return [_replace_refs(item, replacements) for item in sequence]
    if not isinstance(value, dict):
        return value

    mapping = cast(JsonObject, value)
    if set(mapping) == {"$ref"}:
        reference = mapping["$ref"]
        if isinstance(reference, str) and reference in replacements:
            return deepcopy(replacements[reference])

    return {key: _replace_refs(item, replacements) for key, item in mapping.items()}


def _rename_ui_references(value: object) -> object:
    if isinstance(value, list):
        sequence = cast(list[object], value)
        return [_rename_ui_references(item) for item in sequence]
    if not isinstance(value, dict):
        return value

    mapping = cast(JsonObject, value)
    renamed: JsonObject = {}
    for key, item in mapping.items():
        if key == "$ref" and isinstance(item, str):
            for old_name, new_name in UI_DEFINITION_NAMES.items():
                item = item.replace(
                    f"#/$defs/{old_name}",
                    f"#/$defs/{new_name}",
                )
        renamed[key] = _rename_ui_references(item)
    return renamed


def _ui_schema() -> JsonObject:
    raw = UiEnvelope.model_json_schema(
        by_alias=True,
        ref_template=UI_REF_TEMPLATE,
    )
    raw_definitions = _json_object(
        raw.pop("$defs"),
        context="UiEnvelope definitions",
    )
    scalar_replacements = {
        "#/$defs/FalseOnly": _json_object(
            _normalize_schema(raw_definitions["FalseOnly"]),
            context="FalseOnly",
        ),
        "#/$defs/Slug": _json_object(
            _normalize_schema(raw_definitions["Slug"]),
            context="Slug",
        ),
        "#/$defs/Uuid7": _json_object(
            _normalize_schema(raw_definitions["Uuid7"]),
            context="Uuid7",
        ),
    }

    root = _json_object(
        _replace_refs(_normalize_schema(raw), scalar_replacements),
        context="UiEnvelope root",
    )
    definitions = {
        UI_DEFINITION_NAMES[name]: _replace_refs(
            _normalize_schema(raw_definitions[name]),
            scalar_replacements,
        )
        for name in UI_DEFINITION_NAMES
    }
    root["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    root["$id"] = "urn:ai-cto-cockpit:ui-envelope:1.0"
    root["$defs"] = definitions
    return _json_object(
        _rename_ui_references(root),
        context="UiEnvelope schema",
    )


def _openapi_document(repository_root: Path) -> JsonObject:
    contract_path = (
        repository_root
        / "specs"
        / "001-walking-skeleton"
        / "contracts"
        / "openapi.yaml"
    )
    binding = _json_object(
        yaml.safe_load(contract_path.read_text(encoding="utf-8")),
        context=str(contract_path),
    )
    components = _json_object(binding.get("components"), context="components")
    expected_schemas = _json_object(
        components.get("schemas"),
        context="components.schemas",
    )
    generated_schemas = _openapi_schemas()
    if set(expected_schemas) != set(generated_schemas):
        missing = sorted(set(expected_schemas).difference(generated_schemas))
        unexpected = sorted(set(generated_schemas).difference(expected_schemas))
        raise RuntimeError(
            "Pydantic schema registry differs from the binding contract: "
            f"missing={missing}, unexpected={unexpected}"
        )
    components["schemas"] = generated_schemas
    return binding


def _json_bytes(value: JsonObject) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _artifacts(repository_root: Path) -> dict[Path, bytes]:
    output_directory = repository_root / "contracts" / "generated"
    return {
        output_directory / "openapi.json": _json_bytes(
            _openapi_document(repository_root)
        ),
        output_directory / "ui-envelope.schema.json": _json_bytes(_ui_schema()),
    }


def _write_artifacts(artifacts: Mapping[Path, bytes]) -> int:
    for path, content in artifacts.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(f"generated {path}")
    return 0


def _check_artifacts(artifacts: Mapping[Path, bytes]) -> int:
    drifted = False
    for path, expected in artifacts.items():
        actual = path.read_bytes() if path.is_file() else b""
        if actual == expected:
            print(f"current {path}")
            continue

        drifted = True
        print(f"contract drift: {path}", file=sys.stderr)
        diff = difflib.unified_diff(
            actual.decode(errors="replace").splitlines(),
            expected.decode().splitlines(),
            fromfile=str(path),
            tofile=f"generated:{path}",
            lineterm="",
        )
        for line in diff:
            print(line, file=sys.stderr)
    return 1 if drifted else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate canonical contracts")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)

    artifacts = _artifacts(_repository_root())
    if arguments.write:
        return _write_artifacts(artifacts)
    return _check_artifacts(artifacts)


if __name__ == "__main__":
    raise SystemExit(main())
