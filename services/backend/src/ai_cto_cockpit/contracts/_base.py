from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
)
from pydantic.alias_generators import to_camel

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
UUID7_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
ERROR_CODE_PATTERN = r"^[a-z0-9]+(?:_[a-z0-9]+)*$"
ENTERED_WEIGHT_PATTERN = r"^(?:0\.[0-9]{1,8}|[1-9][0-9]{0,9}(?:\.[0-9]{1,8})?)$"
ZERO_WEIGHT_PATTERN = r"^0\.0{1,8}$"
NORMALIZED_WEIGHT_PATTERN = r"^(?:100\.0000|(?:0|[1-9][0-9]?)\.[0-9]{4})$"


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        allow_inf_nan=False,
        extra="forbid",
        serialize_by_alias=True,
        strict=True,
        validate_by_alias=True,
        validate_by_name=False,
    )


def _require_boolean(value: object) -> object:
    if type(value) is not bool:
        raise ValueError("value must be a JSON boolean")
    return value


def _require_date(value: object) -> object:
    if isinstance(value, str) or type(value) is date:
        return value
    raise ValueError("value must be an ISO date string")


def _require_datetime(value: object) -> object:
    if isinstance(value, (str, datetime)):
        return value
    raise ValueError("value must be an RFC 3339 date-time string")


def _reject_zero_weight(value: str) -> str:
    integer, separator, fractional = value.partition(".")
    if integer == "0" and separator and set(fractional) <= {"0"}:
        raise ValueError("entered weight must be greater than zero")
    return value


type Slug = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=SLUG_PATTERN,
    ),
]

type Uuid7 = Annotated[
    str,
    StringConstraints(pattern=UUID7_PATTERN),
    Field(json_schema_extra={"format": "uuid"}),
]

type ErrorCode = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=80,
        pattern=ERROR_CODE_PATTERN,
    ),
]

type EnteredWeight = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=19,
        pattern=ENTERED_WEIGHT_PATTERN,
    ),
    AfterValidator(_reject_zero_weight),
    Field(
        json_schema_extra={
            "examples": ["1", "0.12500000", "9999999999.99999999"],
            "not": {"pattern": ZERO_WEIGHT_PATTERN},
        }
    ),
]

type NormalizedWeight = Annotated[
    str,
    StringConstraints(pattern=NORMALIZED_WEIGHT_PATTERN),
    Field(
        json_schema_extra={
            "examples": ["33.3334"],
            "readOnly": True,
        }
    ),
]

type JsonDate = Annotated[
    date,
    BeforeValidator(_require_date),
    Field(strict=False),
]

type JsonDateTime = Annotated[
    AwareDatetime,
    BeforeValidator(_require_datetime),
    Field(strict=False),
]

type FalseOnly = Annotated[
    Literal[False],
    BeforeValidator(_require_boolean),
]

type TrueOnly = Annotated[
    Literal[True],
    BeforeValidator(_require_boolean),
]
