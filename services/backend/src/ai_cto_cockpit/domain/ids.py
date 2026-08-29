from __future__ import annotations

import re
import uuid

import uuid6

from ai_cto_cockpit.contracts._base import UUID7_PATTERN

_UUID7 = re.compile(UUID7_PATTERN)


def new_uuid7() -> uuid.UUID:
    """Return a server-owned, time-ordered UUIDv7."""

    return uuid6.uuid7()


def parse_uuid7(value: str) -> uuid.UUID:
    """Parse an already bounded canonical UUIDv7 string."""

    if _UUID7.fullmatch(value) is None:
        raise ValueError("Expected a canonical lowercase UUIDv7")
    parsed = uuid.UUID(value)
    if parsed.version != 7 or str(parsed) != value:
        raise ValueError("Expected a canonical lowercase UUIDv7")
    return parsed
