"""Closed upload and connector boundaries for the walking skeleton."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, assert_never

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse

from ai_cto_cockpit.api.errors import api_error_response
from ai_cto_cockpit.api.headers import IdempotencyKey
from ai_cto_cockpit.contracts import ApiError

type AppMode = Literal["public-demo", "local-data"]
type ConnectorKind = Literal["local-git", "github", "web"]


@dataclass(frozen=True)
class _CapabilityError:
    status_code: int
    code: str
    message: str


def _error_for_mode(app_mode: AppMode) -> _CapabilityError:
    if app_mode == "public-demo":
        return _CapabilityError(
            status_code=403,
            code="capability_disabled",
            message="This capability is not available in public-demo mode.",
        )
    if app_mode == "local-data":
        return _CapabilityError(
            status_code=501,
            code="capability_not_implemented",
            message="This capability is not implemented in this release.",
        )
    assert_never(app_mode)


def _response(error: _CapabilityError) -> JSONResponse:
    return api_error_response(
        error.status_code,
        code=error.code,
        message=error.message,
    )


def create_reserved_capability_router(app_mode: AppMode) -> APIRouter:
    """Create mode-frozen routes that fail before reading a request body."""

    capability_error = _error_for_mode(app_mode)
    router = APIRouter(prefix="/api/v1", tags=["demo-boundary"])
    error_responses: dict[int | str, dict[str, Any]] = {
        403: {"model": ApiError, "description": "Capability disabled"},
        501: {"model": ApiError, "description": "Capability not implemented"},
    }

    async def _deny_or_report_upload_capability(
        idempotency_key: IdempotencyKey,
    ) -> JSONResponse:
        del idempotency_key
        return _response(capability_error)

    router.add_api_route(
        "/sources/uploads",
        _deny_or_report_upload_capability,
        methods=["POST"],
        operation_id="denyOrReportUploadCapability",
        responses=error_responses,
    )

    async def _deny_or_report_connector_capability(
        connector_kind: Annotated[ConnectorKind, Path(alias="connectorKind")],
        idempotency_key: IdempotencyKey,
    ) -> JSONResponse:
        del connector_kind, idempotency_key
        return _response(capability_error)

    router.add_api_route(
        "/connectors/{connectorKind}/sync",
        _deny_or_report_connector_capability,
        methods=["POST"],
        operation_id="denyOrReportConnectorCapability",
        responses=error_responses,
    )

    return router
