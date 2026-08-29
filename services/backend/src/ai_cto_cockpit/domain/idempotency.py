from __future__ import annotations

import hashlib
import hmac
import json
import uuid

_LOCK_DOMAIN = b"ai-cto-cockpit/idempotency-advisory-lock/v1\x00"


def canonical_json(document: object) -> bytes:
    """Serialize the bounded JSON profile used for hashes and exact replay."""

    return json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def normalized_request_hash(
    *,
    operation: str,
    method: str,
    path: str,
    body: dict[str, object],
    expected_revision: int | None = None,
) -> str:
    """Hash validated request semantics, excluding credentials and retry keys."""

    request: dict[str, object] = {
        "body": body,
        "method": method.upper(),
        "operation": operation,
        "path": path,
        "query": [],
        "version": 1,
    }
    if expected_revision is not None:
        request["headers"] = {"if-match": expected_revision}
    return hashlib.sha256(canonical_json(request)).hexdigest()


def advisory_lock_id(*, workspace_id: uuid.UUID, operation: str, key: str) -> int:
    """Map an idempotency tuple to PostgreSQL's signed 64-bit lock space."""

    material = b"\x00".join(
        (
            workspace_id.bytes,
            operation.encode("utf-8"),
            key.encode("utf-8"),
        )
    )
    digest = hashlib.sha256(_LOCK_DOMAIN + material).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def request_hash_matches(stored: str, candidate: str) -> bool:
    """Compare fixed-size request digests without data-dependent early exit."""

    return hmac.compare_digest(stored, candidate)
