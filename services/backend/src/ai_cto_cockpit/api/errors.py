from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import uuid6
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ai_cto_cockpit.contracts.errors import ApiError

_VALIDATION_CODES = {
    "missing": "required",
    "string_pattern_mismatch": "invalid_format",
    "string_too_long": "too_long",
    "string_too_short": "too_short",
}


def api_error_response(
    status: int,
    *,
    code: str,
    message: str,
    fields: Sequence[dict[str, str]] = (),
) -> JSONResponse:
    """Return the closed, user-safe error contract for every API failure."""

    error = ApiError.model_validate(
        {
            "code": code,
            "message": message,
            "correlationId": str(uuid6.uuid7()),
            "fields": list(fields),
        }
    )
    return JSONResponse(
        status_code=status,
        content=error.model_dump(mode="json", by_alias=True),
    )


def _field_path(location: Sequence[str | int]) -> str:
    parts: list[str] = []
    for component in location:
        if isinstance(component, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{component}]"
            else:
                parts.append(f"[{component}]")
        else:
            parts.append(component)
    path = ".".join(parts) or "request"
    return path[:240]


async def request_validation_error_response(
    _request: Request,
    error: Exception,
) -> JSONResponse:
    """Map framework validation details to stable codes without echoing input."""

    if not isinstance(error, RequestValidationError):
        raise error
    fields: list[dict[str, str]] = []
    for detail in error.errors()[:50]:
        location = cast(tuple[str | int, ...], detail.get("loc", ()))
        detail_type = str(detail.get("type", ""))
        fields.append(
            {
                "path": _field_path(location),
                "code": _VALIDATION_CODES.get(detail_type, "invalid"),
            }
        )
    return api_error_response(
        422,
        code="request_validation_failed",
        message="Request validation failed.",
        fields=fields,
    )
