from __future__ import annotations

from typing import Annotated

from pydantic import Field

from ._base import ContractModel, ErrorCode, Uuid7


class FieldError(ContractModel):
    path: Annotated[str, Field(min_length=1, max_length=240)]
    code: ErrorCode


class ApiError(ContractModel):
    code: ErrorCode
    message: Annotated[str, Field(min_length=1, max_length=240)]
    correlation_id: Uuid7
    fields: Annotated[list[FieldError], Field(max_length=50)]
