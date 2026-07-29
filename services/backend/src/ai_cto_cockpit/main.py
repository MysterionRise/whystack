from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

app = FastAPI(title="AI CTO Cockpit")


def _database_heads(connection: Connection) -> tuple[str, ...]:
    return tuple(MigrationContext.configure(connection).get_current_heads())


def _repository_heads() -> tuple[str, ...]:
    config = Config(os.environ.get("ALEMBIC_CONFIG", "alembic.ini"))
    return tuple(ScriptDirectory.from_config(config).get_heads())


async def _postgres_and_migrations_ready() -> tuple[bool, bool]:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            database_heads = await connection.run_sync(_database_heads)
    except (OSError, SQLAlchemyError):
        return False, False
    finally:
        await engine.dispose()

    try:
        repository_heads = _repository_heads()
    except (OSError, RuntimeError):
        return True, False

    return True, sorted(database_heads) == sorted(repository_heads)


async def _qdrant_ready() -> bool:
    parsed = urlsplit(os.environ["QDRANT_URL"])
    if parsed.scheme != "http" or not parsed.hostname:
        return False

    port = parsed.port or 80
    path = f"{parsed.path.rstrip('/')}/readyz"
    writer: asyncio.StreamWriter | None = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(parsed.hostname, port),
            timeout=3,
        )
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(request.encode("ascii"))
        await writer.drain()
        status_line = await asyncio.wait_for(reader.readline(), timeout=3)
        return status_line.startswith(b"HTTP/1.1 200")
    except (OSError, TimeoutError, ValueError):
        return False
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


@app.get("/api/v1/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "live"}


@app.get("/api/v1/health/ready")
async def readiness() -> JSONResponse:
    (postgres_ready, migrations_ready), qdrant_ready = await asyncio.gather(
        _postgres_and_migrations_ready(),
        _qdrant_ready(),
    )
    checks = {
        "postgres": "ready" if postgres_ready else "not-ready",
        "migrations": "ready" if migrations_ready else "not-ready",
        "qdrant": "ready" if qdrant_ready else "not-ready",
    }
    ready = all(result == "ready" for result in checks.values())
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "status": "ready" if ready else "not-ready",
            "checks": checks,
        },
    )
