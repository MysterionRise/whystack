from __future__ import annotations

import hashlib
import re
from typing import cast

from ai_cto_cockpit.contracts._base import ENTERED_WEIGHT_PATTERN
from ai_cto_cockpit.contracts.decision import DecisionFrameInput, DecisionFrameView
from ai_cto_cockpit.domain.idempotency import canonical_json

_ENTERED_WEIGHT = re.compile(ENTERED_WEIGHT_PATTERN)
_NORMALIZED_UNITS = 1_000_000
type JsonObject = dict[str, object]


def _fractional_scale(value: str) -> int:
    _whole, separator, fractional = value.partition(".")
    return len(fractional) if separator else 0


def _coefficient(value: str, *, scale: int) -> int:
    """Expand one validated decimal string at a bounded common scale."""

    if _ENTERED_WEIGHT.fullmatch(value) is None:
        raise ValueError("Entered weight is outside the canonical grammar")
    whole, separator, fractional = value.partition(".")
    if whole == "0" and separator and set(fractional) <= {"0"}:
        raise ValueError("Entered weight must be greater than zero")
    coefficient = int(whole + fractional.ljust(scale, "0"))
    if coefficient <= 0:
        raise ValueError("Entered weight must be greater than zero")
    return coefficient


def _format_units(units: int) -> str:
    whole, fractional = divmod(units, 10_000)
    return f"{whole}.{fractional:04d}"


def normalize_frame(frame: DecisionFrameInput) -> DecisionFrameView:
    """Normalize criteria with integer-only largest-remainder allocation."""

    entered = [(criterion.id, criterion.entered_weight) for criterion in frame.criteria]
    scale = max(_fractional_scale(value) for _criterion_id, value in entered)
    coefficients = {
        criterion_id: _coefficient(value, scale=scale)
        for criterion_id, value in entered
    }
    total = sum(coefficients.values())
    allocations: dict[str, int] = {}
    remainders: dict[str, int] = {}
    for criterion_id, coefficient in coefficients.items():
        allocations[criterion_id], remainders[criterion_id] = divmod(
            coefficient * _NORMALIZED_UNITS,
            total,
        )

    remaining = _NORMALIZED_UNITS - sum(allocations.values())
    ranked = sorted(remainders, key=lambda item: (-remainders[item], item))
    for criterion_id in ranked[:remaining]:
        allocations[criterion_id] += 1

    document = cast(
        JsonObject,
        frame.model_dump(mode="json", by_alias=True),
    )
    criteria = cast(list[JsonObject], document["criteria"])
    for criterion in criteria:
        criterion_id = cast(str, criterion["id"])
        criterion["normalizedWeight"] = _format_units(allocations[criterion_id])
    return DecisionFrameView.model_validate(document)


def snapshot_hash(frame: DecisionFrameView) -> str:
    """Hash the exact normalized immutable frame representation."""

    document = frame.model_dump(mode="json", by_alias=True)
    return hashlib.sha256(canonical_json(document)).hexdigest()
