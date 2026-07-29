from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic.config import JsonDict, JsonValue

from ._base import ContractModel, FalseOnly, JsonDateTime, TrueOnly

type DeploymentMode = Literal["public-demo", "local-data"]
type ReadinessState = Literal["ready", "not-ready"]

REQUIRED_READINESS_CHECKS = frozenset({"postgres", "migrations", "qdrant"})
REQUIRED_READINESS_SCHEMA_FIELDS: list[JsonValue] = list(
    sorted(REQUIRED_READINESS_CHECKS)
)
READINESS_CHECKS_SCHEMA: JsonDict = {
    "required": REQUIRED_READINESS_SCHEMA_FIELDS,
}


class Capabilities(ContractModel):
    can_create_decision: bool
    can_run_decision: bool
    can_replay_run: bool
    can_reset_guest_workspace: bool
    persistent_workspace: bool
    can_upload: FalseOnly
    can_use_local_git: FalseOnly
    can_use_git_hub: FalseOnly = Field(alias="canUseGitHub")
    can_use_web: FalseOnly


class RuntimeConfig(ContractModel):
    api_version: Literal["v1"]
    mode: DeploymentMode
    capabilities: Capabilities
    guest_expires_at: JsonDateTime | None


class ResetSessionResponse(ContractModel):
    reset_accepted: TrueOnly
    guest_expires_at: JsonDateTime


class Liveness(ContractModel):
    status: Literal["live"]


class Readiness(ContractModel):
    status: ReadinessState
    checks: Annotated[
        dict[str, ReadinessState],
        Field(json_schema_extra=READINESS_CHECKS_SCHEMA),
    ]

    @field_validator("checks")
    @classmethod
    def require_dependency_checks(
        cls,
        value: dict[str, ReadinessState],
    ) -> dict[str, ReadinessState]:
        missing = REQUIRED_READINESS_CHECKS.difference(value)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"missing required readiness checks: {names}")
        return value
