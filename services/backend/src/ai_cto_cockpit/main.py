from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlsplit

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from ai_cto_cockpit.api.errors import request_validation_error_response
from ai_cto_cockpit.api.routes.capabilities import (
    AppMode,
    create_reserved_capability_router,
)
from ai_cto_cockpit.api.routes.config import (
    DatabaseClock,
    ResetResponseSerializer,
    default_reset_response_serializer,
)
from ai_cto_cockpit.api.routes.config import (
    router as config_router,
)
from ai_cto_cockpit.api.routes.decisions import router as decisions_router
from ai_cto_cockpit.persistence.session import (
    create_database_engine,
    create_session_factory,
)
from ai_cto_cockpit.security.guest_session import GuestSessionCodec, SessionKeyRing
from ai_cto_cockpit.settings import Settings

type Clock = Callable[[], datetime]
type SessionFactory = async_sessionmaker[AsyncSession]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _database_heads(connection: Connection) -> tuple[str, ...]:
    return tuple(MigrationContext.configure(connection).get_current_heads())


def _repository_heads() -> tuple[str, ...]:
    config = Config(os.environ.get("ALEMBIC_CONFIG", "alembic.ini"))
    return tuple(ScriptDirectory.from_config(config).get_heads())


async def _postgres_and_migrations_ready(
    database_url: str | None = None,
) -> tuple[bool, bool]:
    selected_url = database_url or os.environ["DATABASE_URL"]
    engine = create_database_engine(selected_url)
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


async def _qdrant_ready(qdrant_url: str | None = None) -> bool:
    selected_url = qdrant_url or os.environ["QDRANT_URL"]
    parsed = urlsplit(selected_url)
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


def _route_mode(settings: Settings | None) -> AppMode:
    if settings is not None:
        return settings.app_mode
    configured = os.environ.get("APP_MODE", "public-demo")
    if configured in {"public-demo", "local-data"}:
        return cast(AppMode, configured)
    # Full Settings validation will reject this value during process startup.
    return "public-demo"


def _install_runtime(
    application: FastAPI,
    *,
    settings: Settings,
    session_factory: SessionFactory | None,
    clock: Clock,
) -> AsyncEngine | None:
    engine: AsyncEngine | None = None
    selected_factory = session_factory
    if selected_factory is None:
        engine = create_database_engine(settings.database_url)
        selected_factory = create_session_factory(engine)
    application.state.settings = settings
    application.state.session_factory = selected_factory
    application.state.guest_session_codec = GuestSessionCodec(
        SessionKeyRing.from_settings(settings),
        cookie_secure=settings.cookie_secure,
        clock=clock,
    )
    return engine


async def liveness() -> dict[str, str]:
    return {"status": "live"}


async def readiness(request: Request) -> JSONResponse:
    resolved_settings = cast(Settings, request.app.state.settings)
    (postgres_ready, migrations_ready), qdrant_ready = await asyncio.gather(
        _postgres_and_migrations_ready(resolved_settings.database_url),
        _qdrant_ready(resolved_settings.qdrant_url),
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


def create_app(
    *,
    settings: Settings | None = None,
    session_factory: SessionFactory | None = None,
    clock: Clock | None = None,
    database_clock: DatabaseClock | None = None,
    reset_response_serializer: ResetResponseSerializer | None = None,
) -> FastAPI:
    """Build one mode-frozen application with explicit, testable dependencies."""

    selected_clock = clock or _utc_now
    selected_database_clock = database_clock
    if selected_database_clock is None and clock is not None:

        async def injected_database_clock(_session: AsyncSession) -> datetime:
            return clock()

        selected_database_clock = injected_database_clock
    route_mode = _route_mode(settings)
    owned_engine: AsyncEngine | None = None

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
        nonlocal owned_engine
        if settings is None:
            resolved = Settings()  # pyright: ignore[reportCallIssue]
            if resolved.app_mode != route_mode:
                raise RuntimeError("APP_MODE changed after application construction")
            owned_engine = _install_runtime(
                application,
                settings=resolved,
                session_factory=session_factory,
                clock=selected_clock,
            )
        try:
            yield
        finally:
            if owned_engine is not None:
                await owned_engine.dispose()

    application = FastAPI(title="AI CTO Cockpit", lifespan=lifespan)
    application.add_exception_handler(
        RequestValidationError,
        request_validation_error_response,
    )
    application.state.clock = selected_clock
    application.state.database_clock = selected_database_clock
    application.state.reset_serializer = (
        reset_response_serializer or default_reset_response_serializer
    )
    if settings is not None:
        owned_engine = _install_runtime(
            application,
            settings=settings,
            session_factory=session_factory,
            clock=selected_clock,
        )

    application.include_router(config_router)
    application.include_router(decisions_router)
    application.include_router(create_reserved_capability_router(route_mode))
    application.add_api_route("/api/v1/health/live", liveness, methods=["GET"])
    application.add_api_route("/api/v1/health/ready", readiness, methods=["GET"])

    return application


app = create_app()
