from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from ._base import ContractModel, JsonDateTime, Uuid7
from .ui import UiEnvelope

type RunStatus = Literal["queued", "running", "completed", "failed"]
type RunEventKind = Literal[
    "run.queued",
    "run.started",
    "ui.envelope",
    "run.completed",
    "run.failed",
]


class RunView(ContractModel):
    id: Uuid7
    decision_id: Uuid7
    decision_revision: Annotated[int, Field(ge=1)]
    status: RunStatus
    last_event_sequence: Annotated[int, Field(ge=0)]
    fixture_version: Literal["walking-skeleton-v1"]
    created_at: JsonDateTime
    started_at: JsonDateTime | None
    completed_at: JsonDateTime | None
    error_code: Annotated[str, Field(min_length=1, max_length=80)] | None


class RunQueuedPayload(ContractModel):
    status: Literal["queued"]


class RunStartedPayload(ContractModel):
    status: Literal["running"]


class RunCompletedPayload(ContractModel):
    status: Literal["completed"]


class RunFailurePayload(ContractModel):
    status: Literal["failed"]
    error_code: Annotated[str, Field(min_length=1, max_length=80)]


class RunEventBase(ContractModel):
    run_id: Uuid7
    sequence: Annotated[int, Field(ge=1)]
    kind: RunEventKind
    schema_version: Literal["1.0"]
    payload: dict[str, object]
    created_at: JsonDateTime


class RunQueuedEvent(ContractModel):
    run_id: Uuid7
    sequence: Annotated[int, Field(ge=1)]
    kind: Literal["run.queued"]
    schema_version: Literal["1.0"]
    payload: RunQueuedPayload
    created_at: JsonDateTime


class RunStartedEvent(ContractModel):
    run_id: Uuid7
    sequence: Annotated[int, Field(ge=1)]
    kind: Literal["run.started"]
    schema_version: Literal["1.0"]
    payload: RunStartedPayload
    created_at: JsonDateTime


class UiEnvelopeEvent(ContractModel):
    run_id: Uuid7
    sequence: Annotated[int, Field(ge=1)]
    kind: Literal["ui.envelope"]
    schema_version: Literal["1.0"]
    payload: UiEnvelope
    created_at: JsonDateTime


class RunCompletedEvent(ContractModel):
    run_id: Uuid7
    sequence: Annotated[int, Field(ge=1)]
    kind: Literal["run.completed"]
    schema_version: Literal["1.0"]
    payload: RunCompletedPayload
    created_at: JsonDateTime


class RunFailedEvent(ContractModel):
    run_id: Uuid7
    sequence: Annotated[int, Field(ge=1)]
    kind: Literal["run.failed"]
    schema_version: Literal["1.0"]
    payload: RunFailurePayload
    created_at: JsonDateTime


type RunEvent = Annotated[
    RunQueuedEvent
    | RunStartedEvent
    | UiEnvelopeEvent
    | RunCompletedEvent
    | RunFailedEvent,
    Field(discriminator="kind"),
]
