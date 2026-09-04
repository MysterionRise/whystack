from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import NotRequired, Protocol, TypedDict, cast

from langgraph.graph import (  # pyright: ignore[reportMissingTypeStubs]
    END,
    START,
    StateGraph,
)

from ai_cto_cockpit.contracts.ui import UiEnvelope

FIXTURE_VERSION = "walking-skeleton-v1"

type JsonObject = dict[str, object]


class _FakeGraphState(TypedDict):
    run_id: uuid.UUID
    event_sequence: int
    input_snapshot: JsonObject
    option_ids: NotRequired[tuple[str, str]]
    envelope: NotRequired[JsonObject]
    complete: NotRequired[bool]


class _CompiledGraph(Protocol):
    def invoke(self, state: _FakeGraphState) -> _FakeGraphState: ...


class _GraphBuilder(Protocol):
    def add_node(
        self,
        name: str,
        action: Callable[[_FakeGraphState], JsonObject],
    ) -> object: ...

    def add_edge(self, source: str, target: str) -> object: ...

    def compile(self) -> _CompiledGraph: ...


def _load_snapshot(state: _FakeGraphState) -> JsonObject:
    """Read only the bounded option identifiers needed by the fixture."""

    raw_options = state["input_snapshot"].get("options")
    if not isinstance(raw_options, list):
        raise ValueError("A deterministic run requires at least two options")
    options = cast(list[object], raw_options)
    if len(options) < 2:
        raise ValueError("A deterministic run requires at least two options")

    identifiers: list[str] = []
    for option in options[:2]:
        if not isinstance(option, dict):
            raise ValueError("Run snapshot options must be objects")
        option_document = cast(dict[str, object], option)
        option_id = option_document.get("id")
        if not isinstance(option_id, str):
            raise ValueError("Run snapshot option IDs must be strings")
        identifiers.append(option_id)
    return {"option_ids": (identifiers[0], identifiers[1])}


def _emit_demonstration(state: _FakeGraphState) -> JsonObject:
    """Produce fixed, visibly non-authoritative demonstration output."""

    option_ids = state.get("option_ids")
    if option_ids is None:
        raise RuntimeError("The deterministic graph did not load its snapshot")
    first_option, second_option = option_ids
    return {
        "envelope": {
            "schemaVersion": "1.0",
            "component": {
                "kind": "recommendation-summary",
                "id": "recommendation",
                "title": "Demonstration recommendation",
                "status": "demonstration",
                "selectedOptionId": first_option,
                "rationale": (
                    "This fixed fixture selects the first supplied option; "
                    "it does not assess evidence or call a model provider."
                ),
                "optionScores": [
                    {"optionId": first_option, "score": 80},
                    {"optionId": second_option, "score": 65},
                ],
                "disclaimer": ("Demonstration output; no model provider was called."),
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
                "runId": str(state["run_id"]),
                "eventSequence": state["event_sequence"],
                "generatedBy": "deterministic-fixture",
                "fixtureVersion": FIXTURE_VERSION,
            },
        }
    }


def _complete_run(state: _FakeGraphState) -> JsonObject:
    del state
    return {"complete": True}


def _compile_graph() -> _CompiledGraph:
    builder = cast(_GraphBuilder, StateGraph(_FakeGraphState))
    builder.add_node("load-snapshot", _load_snapshot)
    builder.add_node("emit-demonstration", _emit_demonstration)
    builder.add_node("complete-run", _complete_run)
    builder.add_edge(START, "load-snapshot")
    builder.add_edge("load-snapshot", "emit-demonstration")
    builder.add_edge("emit-demonstration", "complete-run")
    builder.add_edge("complete-run", END)
    return builder.compile()


_GRAPH: _CompiledGraph = _compile_graph()


def deterministic_envelope(
    *,
    run_id: uuid.UUID,
    event_sequence: int,
    input_snapshot: JsonObject,
) -> JsonObject:
    """Execute the explicit three-node fake graph and return its closed envelope."""

    result = _GRAPH.invoke(
        {
            "run_id": run_id,
            "event_sequence": event_sequence,
            "input_snapshot": input_snapshot,
        }
    )
    envelope = result.get("envelope")
    if not isinstance(envelope, dict) or result.get("complete") is not True:
        raise RuntimeError("The deterministic graph did not complete")
    validated = UiEnvelope.model_validate(envelope)
    return cast(JsonObject, validated.model_dump(mode="json", by_alias=True))
