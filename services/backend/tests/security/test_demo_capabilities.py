from __future__ import annotations

import asyncio
import importlib
import json
import socket
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp, Message, Scope

from ai_cto_cockpit.persistence import repositories

JSON_LIMIT_BYTES = 256 * 1024
SMALL_BODY = b'{"untrusted":"payload"}'
OVERSIZED_BODY = b'{"untrusted":"' + (b"x" * JSON_LIMIT_BYTES) + b'"}'
RESERVED_ROUTES = (
    "/api/v1/sources/uploads",
    "/api/v1/connectors/local-git/sync",
    "/api/v1/connectors/github/sync",
    "/api/v1/connectors/web/sync",
)


@dataclass
class _UnreadBody:
    payload: bytes
    calls: int = 0

    async def __call__(self) -> Message:
        self.calls += 1
        raise AssertionError(
            f"reserved capability route read {len(self.payload)} request-body bytes"
        )


@dataclass(frozen=True)
class _CapturedResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class _SideEffectTripwire:
    def __init__(self) -> None:
        self.calls = {
            "repository": 0,
            "filesystem": 0,
            "network": 0,
            "qdrant": 0,
            "job_dispatch": 0,
        }

    def sync(self, channel: str) -> Callable[..., NoReturn]:
        def fail(*_args: object, **_kwargs: object) -> NoReturn:
            self.calls[channel] += 1
            raise AssertionError(f"reserved capability route invoked {channel}")

        return fail

    def async_(self, channel: str) -> Callable[..., object]:
        async def fail(*_args: object, **_kwargs: object) -> NoReturn:
            self.calls[channel] += 1
            raise AssertionError(f"reserved capability route invoked {channel}")

        return fail

    def assert_idle(self) -> None:
        assert self.calls == {
            "repository": 0,
            "filesystem": 0,
            "network": 0,
            "qdrant": 0,
            "job_dispatch": 0,
        }


def _build_app(mode: str) -> tuple[ASGIApp, ModuleType]:
    main_module = importlib.import_module("ai_cto_cockpit.main")
    settings_module = importlib.import_module("ai_cto_cockpit.settings")
    settings = settings_module.Settings(
        app_mode=mode,
        database_url="postgresql+psycopg://test:test@127.0.0.1:1/test",
        qdrant_url="http://127.0.0.1:1",
        session_signing_key="t011-test-key-with-at-least-thirty-two-bytes",
        session_signing_key_id="test-v1",
        cookie_secure=False,
        local_compose=True,
    )
    app = main_module.create_app(settings=settings)
    return cast(ASGIApp, app), main_module


def _install_side_effect_tripwires(
    monkeypatch: pytest.MonkeyPatch,
    main_module: ModuleType,
) -> _SideEffectTripwire:
    tripwire = _SideEffectTripwire()

    for repository_type in (
        repositories.DecisionRepository,
        repositories.RunRepository,
        repositories.ResetReplayRepository,
    ):
        monkeypatch.setattr(
            repository_type,
            "__init__",
            tripwire.sync("repository"),
        )
    monkeypatch.setattr(
        repositories.JobRepository,
        "__init__",
        tripwire.sync("job_dispatch"),
    )
    monkeypatch.setattr(
        AsyncSession,
        "execute",
        tripwire.async_("repository"),
    )
    monkeypatch.setattr(
        AsyncSession,
        "flush",
        tripwire.async_("repository"),
    )
    monkeypatch.setattr(
        AsyncSession,
        "commit",
        tripwire.async_("repository"),
    )
    monkeypatch.setattr(AsyncSession, "add", tripwire.sync("repository"))

    monkeypatch.setattr(Path, "open", tripwire.sync("filesystem"))
    monkeypatch.setattr(Path, "write_bytes", tripwire.sync("filesystem"))
    monkeypatch.setattr(Path, "write_text", tripwire.sync("filesystem"))

    monkeypatch.setattr(
        asyncio,
        "open_connection",
        tripwire.async_("network"),
    )
    monkeypatch.setattr(
        socket,
        "create_connection",
        tripwire.sync("network"),
    )
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        tripwire.sync("network"),
    )
    monkeypatch.setattr(
        main_module,
        "_qdrant_ready",
        tripwire.async_("qdrant"),
    )

    return tripwire


async def _direct_post(
    app: ASGIApp,
    *,
    path: str,
    payload: bytes,
    idempotency_key: bytes | None = b"t011-capability-boundary",
) -> tuple[_CapturedResponse, _UnreadBody]:
    receive = _UnreadBody(payload)
    messages: list[Message] = []

    async def send(message: Message) -> None:
        messages.append(message)

    request_headers = [
        (b"host", b"testserver"),
        (b"content-type", b"application/json"),
        (b"content-length", str(len(payload)).encode("ascii")),
    ]
    if idempotency_key is not None:
        request_headers.append((b"idempotency-key", idempotency_key))

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": request_headers,
        "client": ("127.0.0.1", 54321),
        "server": ("testserver", 80),
        "state": {},
    }

    await app(scope, receive, send)

    start = next(
        message for message in messages if message["type"] == "http.response.start"
    )
    response_headers = {
        name.decode("latin-1"): value.decode("latin-1")
        for name, value in start.get("headers", [])
    }
    response_body = b"".join(
        cast(bytes, message.get("body", b""))
        for message in messages
        if message["type"] == "http.response.body"
    )
    return (
        _CapturedResponse(
            status=cast(int, start["status"]),
            headers=response_headers,
            body=response_body,
        ),
        receive,
    )


def _assert_api_error(
    response: _CapturedResponse,
    *,
    status: int,
    code: str,
    message: str,
) -> None:
    assert response.status == status
    assert response.headers["content-type"] == "application/json"
    payload = json.loads(response.body)
    assert payload == {
        "code": code,
        "message": message,
        "correlationId": payload["correlationId"],
        "fields": [],
    }
    correlation_id = uuid.UUID(payload["correlationId"])
    assert correlation_id.version == 7


@pytest.mark.asyncio
@pytest.mark.parametrize("path", RESERVED_ROUTES)
@pytest.mark.parametrize(
    "payload",
    [SMALL_BODY, OVERSIZED_BODY],
    ids=["ordinary-body", "over-256-kib-body"],
)
async def test_public_demo_denies_reserved_capability_before_body_or_side_effects(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: bytes,
) -> None:
    app, main_module = _build_app("public-demo")
    tripwire = _install_side_effect_tripwires(monkeypatch, main_module)

    response, receive = await _direct_post(app, path=path, payload=payload)

    _assert_api_error(
        response,
        status=403,
        code="capability_disabled",
        message="This capability is not available in public-demo mode.",
    )
    assert receive.calls == 0
    tripwire.assert_idle()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", RESERVED_ROUTES)
@pytest.mark.parametrize(
    "payload",
    [SMALL_BODY, OVERSIZED_BODY],
    ids=["ordinary-body", "over-256-kib-body"],
)
async def test_local_data_reports_reserved_capability_not_implemented_pre_body(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: bytes,
) -> None:
    app, main_module = _build_app("local-data")
    tripwire = _install_side_effect_tripwires(monkeypatch, main_module)

    response, receive = await _direct_post(app, path=path, payload=payload)

    _assert_api_error(
        response,
        status=501,
        code="capability_not_implemented",
        message="This capability is not implemented in this release.",
    )
    assert receive.calls == 0
    tripwire.assert_idle()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["public-demo", "local-data"])
@pytest.mark.parametrize(
    ("path", "idempotency_key", "field_code"),
    [
        ("/api/v1/sources/uploads", None, "required"),
        (
            "/api/v1/connectors/github/sync",
            b"contains space",
            "invalid_format",
        ),
    ],
    ids=["missing", "non-visible-ascii"],
)
async def test_reserved_capabilities_validate_idempotency_header_pre_body(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    path: str,
    idempotency_key: bytes | None,
    field_code: str,
) -> None:
    app, main_module = _build_app(mode)
    tripwire = _install_side_effect_tripwires(monkeypatch, main_module)

    response, receive = await _direct_post(
        app,
        path=path,
        payload=OVERSIZED_BODY,
        idempotency_key=idempotency_key,
    )

    assert response.status == 422
    payload = json.loads(response.body)
    assert payload == {
        "code": "request_validation_failed",
        "message": "Request validation failed.",
        "correlationId": payload["correlationId"],
        "fields": [
            {
                "path": "header.Idempotency-Key",
                "code": field_code,
            }
        ],
    }
    assert uuid.UUID(payload["correlationId"]).version == 7
    assert receive.calls == 0
    tripwire.assert_idle()
