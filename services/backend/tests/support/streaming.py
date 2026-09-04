from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI
from starlette.types import Message, Scope


@dataclass(frozen=True, slots=True)
class AsgiStreamResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes
    client_disconnected: bool

    def header(self, name: str) -> str | None:
        normalized = name.lower()
        for header_name, value in self.headers:
            if header_name.lower() == normalized:
                return value
        return None

    def json(self) -> dict[str, object]:
        value = json.loads(self.body)
        assert isinstance(value, dict)
        return cast(dict[str, object], value)


async def asgi_stream_request(
    app: FastAPI,
    *,
    path: str,
    query: str = "",
    headers: Sequence[tuple[str, str]] = (),
    disconnect_after_body_chunks: int | None = None,
    timeout_seconds: float = 2.0,
) -> AsgiStreamResponse:
    """Collect a finite ASGI stream or disconnect after bounded body output."""

    request_sent = False
    body_chunk_count = 0
    disconnect = asyncio.Event()
    messages: list[Message] = []

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {
                "type": "http.request",
                "body": b"",
                "more_body": False,
            }
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        nonlocal body_chunk_count
        messages.append(message)
        if message["type"] != "http.response.body" or not message.get("body"):
            return
        body_chunk_count += 1
        if (
            disconnect_after_body_chunks is not None
            and body_chunk_count >= disconnect_after_body_chunks
        ):
            disconnect.set()

    encoded_headers = [(b"host", b"testserver")]
    encoded_headers.extend(
        (name.lower().encode("ascii"), value.encode("latin-1"))
        for name, value in headers
    )
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query.encode("ascii"),
        "root_path": "",
        "headers": encoded_headers,
        "client": ("127.0.0.1", 54321),
        "server": ("testserver", 443),
        "state": {},
    }
    async with asyncio.timeout(timeout_seconds):
        await app(scope, receive, send)

    start = next(item for item in messages if item["type"] == "http.response.start")
    response_headers = tuple(
        (name.decode("latin-1"), value.decode("latin-1"))
        for name, value in start.get("headers", [])
    )
    response_body = b"".join(
        cast(bytes, item.get("body", b""))
        for item in messages
        if item["type"] == "http.response.body"
    )
    return AsgiStreamResponse(
        status=cast(int, start["status"]),
        headers=response_headers,
        body=response_body,
        client_disconnected=disconnect.is_set(),
    )
