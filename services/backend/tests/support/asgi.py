from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

from fastapi import FastAPI
from starlette.types import Message, Scope


@dataclass(frozen=True, slots=True)
class AsgiResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

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


async def asgi_request(
    app: FastAPI,
    *,
    method: str,
    path: str,
    query: str = "",
    headers: Sequence[tuple[str, str]] = (),
    body: bytes = b"",
) -> AsgiResponse:
    request_sent = False
    messages: list[Message] = []

    async def receive() -> Message:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        messages.append(message)

    encoded_headers = [(b"host", b"testserver")]
    encoded_headers.extend(
        (name.lower().encode("ascii"), value.encode("latin-1"))
        for name, value in headers
    )
    if body and not any(name.lower() == "content-length" for name, _ in headers):
        encoded_headers.append((b"content-length", str(len(body)).encode("ascii")))

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
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
    return AsgiResponse(
        status=cast(int, start["status"]),
        headers=response_headers,
        body=response_body,
    )
