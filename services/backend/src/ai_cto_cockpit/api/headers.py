from __future__ import annotations

from typing import Annotated

from fastapi import Header

type IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[\x21-\x7E]+$",
    ),
]
