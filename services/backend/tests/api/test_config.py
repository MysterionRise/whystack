from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from conftest import AsgiResponse, asgi_request
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.main import create_app
from ai_cto_cockpit.persistence.models import GuestSession, Workspace, WorkspaceKind
from ai_cto_cockpit.settings import AppMode, Settings

NOW = datetime(2026, 8, 14, 12, 0, 0, 123456, tzinfo=UTC)
SIGNING_KEY = "t010-session-signing-key-with-more-than-thirty-two-bytes"
SEED_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000001")
LOCAL_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000002")


def _settings(database_url: str, *, mode: AppMode) -> Settings:
    return Settings(
        app_mode=mode,
        database_url=database_url,
        qdrant_url="http://127.0.0.1:6333",
        session_signing_key=SIGNING_KEY,
        session_signing_key_id="cookie-key-v1",
        session_retained_signing_keys={},
        cookie_secure=False,
        local_compose=True,
        seed_workspace_id=SEED_ID,
        local_workspace_id=LOCAL_ID,
    )


def _cookie_value(set_cookie: str) -> str:
    pair = set_cookie.split(";", 1)[0]
    name, value = pair.split("=", 1)
    assert name == "ai_cto_guest"
    return value


def _assert_api_error(
    response: AsgiResponse,
    *,
    status: int,
    code: str,
    message: str,
    fields: list[dict[str, str]],
) -> None:
    assert response.status == status
    payload = response.json()
    assert payload == {
        "code": code,
        "message": message,
        "correlationId": payload["correlationId"],
        "fields": fields,
    }
    assert uuid.UUID(cast(str, payload["correlationId"])).version == 7


async def _counts(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int, int, int]:
    async with factory() as session:
        total_workspaces = await session.scalar(select(func.count(Workspace.id)))
        seed_workspaces = await session.scalar(
            select(func.count(Workspace.id)).where(Workspace.kind == WorkspaceKind.SEED)
        )
        local_workspaces = await session.scalar(
            select(func.count(Workspace.id)).where(
                Workspace.kind == WorkspaceKind.LOCAL
            )
        )
        sessions = await session.scalar(select(func.count(GuestSession.id)))
    return (
        int(total_workspaces or 0),
        int(seed_workspaces or 0),
        int(local_workspaces or 0),
        int(sessions or 0),
    )


@pytest.mark.asyncio
async def test_public_demo_config_creates_and_reuses_server_scoped_guest(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings(t010_postgres_url, mode="public-demo")
    app = create_app(
        settings=settings,
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )

    first = await asgi_request(
        app,
        method="GET",
        path="/api/v1/config",
        query="workspaceId=attacker-selected&mode=local-data",
        headers=(("X-Workspace-Id", "attacker-selected"),),
    )

    assert first.status == 200
    assert first.json() == {
        "apiVersion": "v1",
        "mode": "public-demo",
        "capabilities": {
            "canCreateDecision": True,
            "canRunDecision": True,
            "canReplayRun": True,
            "canResetGuestWorkspace": True,
            "persistentWorkspace": False,
            "canUpload": False,
            "canUseLocalGit": False,
            "canUseGitHub": False,
            "canUseWeb": False,
        },
        "guestExpiresAt": "2026-08-15T12:00:00.123456Z",
    }
    first_cookie_header = first.header("set-cookie")
    assert first_cookie_header is not None
    assert "HttpOnly" in first_cookie_header
    assert "SameSite=Lax" in first_cookie_header
    assert "Secure" not in first_cookie_header
    assert await _counts(t010_session_factory) == (2, 1, 0, 1)

    cookie_value = _cookie_value(first_cookie_header)
    second = await asgi_request(
        app,
        method="GET",
        path="/api/v1/config",
        headers=(("Cookie", f"ai_cto_guest={cookie_value}"),),
    )
    assert second.status == 200
    assert second.json() == first.json()
    assert await _counts(t010_session_factory) == (2, 1, 0, 1)

    async with t010_session_factory() as session:
        guest = await session.scalar(
            select(Workspace).where(Workspace.kind == WorkspaceKind.GUEST)
        )
        guest_session = await session.scalar(select(GuestSession))
        assert guest is not None and guest_session is not None
        assert guest.seed_parent_id == SEED_ID
        assert guest.expires_at == NOW + timedelta(hours=24)
        assert guest_session.expires_at == guest.expires_at
        assert guest_session.workspace_id == guest.id


@pytest.mark.asyncio
async def test_invalid_public_cookie_starts_fresh_without_deriving_old_scope(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(
        settings=_settings(t010_postgres_url, mode="public-demo"),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    response = await asgi_request(
        app,
        method="GET",
        path="/api/v1/config",
        headers=(("Cookie", "ai_cto_guest=tampered.attacker.cookie"),),
    )
    assert response.status == 200
    assert response.header("set-cookie") is not None
    assert await _counts(t010_session_factory) == (2, 1, 0, 1)


@pytest.mark.asyncio
async def test_local_data_config_uses_stable_singleton_without_guest_cookie(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    settings = _settings(t010_postgres_url, mode="local-data")
    first_app = create_app(
        settings=settings,
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    first = await asgi_request(first_app, method="GET", path="/api/v1/config")
    second_app = create_app(
        settings=settings,
        session_factory=t010_session_factory,
        clock=lambda: NOW + timedelta(minutes=5),
    )
    second = await asgi_request(second_app, method="GET", path="/api/v1/config")

    expected = {
        "apiVersion": "v1",
        "mode": "local-data",
        "capabilities": {
            "canCreateDecision": True,
            "canRunDecision": True,
            "canReplayRun": True,
            "canResetGuestWorkspace": False,
            "persistentWorkspace": True,
            "canUpload": False,
            "canUseLocalGit": False,
            "canUseGitHub": False,
            "canUseWeb": False,
        },
        "guestExpiresAt": None,
    }
    assert first.status == second.status == 200
    assert first.json() == second.json() == expected
    assert first.header("set-cookie") is None
    assert second.header("set-cookie") is None
    assert await _counts(t010_session_factory) == (1, 0, 1, 0)
    async with t010_session_factory() as session:
        workspace = await session.scalar(select(Workspace))
        assert workspace is not None
        assert workspace.id == LOCAL_ID


@pytest.mark.asyncio
async def test_config_never_exposes_workspace_or_configured_secrets(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    app = create_app(
        settings=_settings(t010_postgres_url, mode="public-demo"),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    response = await asgi_request(app, method="GET", path="/api/v1/config")
    lowered = response.body.lower()
    forbidden = (
        b"workspaceid",
        b"workspace_id",
        str(SEED_ID).encode("ascii"),
        str(LOCAL_ID).encode("ascii"),
        SIGNING_KEY.encode("ascii"),
        t010_postgres_url.encode("ascii"),
        b"openrouter",
    )
    assert all(value.lower() not in lowered for value in forbidden)


@pytest.mark.asyncio
async def test_database_time_is_canonical_when_process_clock_is_skewed(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def database_clock(_session: AsyncSession) -> datetime:
        return NOW

    app = create_app(
        settings=_settings(t010_postgres_url, mode="public-demo"),
        session_factory=t010_session_factory,
        clock=lambda: NOW + timedelta(hours=2),
        database_clock=database_clock,
    )
    response = await asgi_request(app, method="GET", path="/api/v1/config")

    assert response.status == 200
    assert response.json()["guestExpiresAt"] == "2026-08-15T12:00:00.123456Z"
    async with t010_session_factory() as session:
        workspace = await session.scalar(
            select(Workspace).where(Workspace.kind == WorkspaceKind.GUEST)
        )
        guest_session = await session.scalar(select(GuestSession))
        assert workspace is not None and guest_session is not None
        assert workspace.created_at == NOW
        assert workspace.expires_at == NOW + timedelta(hours=24)
        assert guest_session.created_at == NOW


@pytest.mark.asyncio
async def test_config_maps_database_failure_to_contracted_service_unavailable(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def unavailable_database_clock(_session: AsyncSession) -> datetime:
        raise SQLAlchemyError("simulated dependency failure")

    app = create_app(
        settings=_settings(t010_postgres_url, mode="public-demo"),
        session_factory=t010_session_factory,
        database_clock=unavailable_database_clock,
    )

    response = await asgi_request(app, method="GET", path="/api/v1/config")

    _assert_api_error(
        response,
        status=503,
        code="service_unavailable",
        message="A required service is unavailable.",
        fields=[],
    )
    assert response.header("set-cookie") is None
    assert await _counts(t010_session_factory) == (0, 0, 0, 0)


@pytest.mark.asyncio
async def test_concurrent_first_config_requests_bootstrap_one_seed_shell(
    t010_postgres_url: str,
    t010_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with t010_session_factory.begin() as session:
        await session.execute(
            text(
                """
                CREATE FUNCTION t010_delay_workspace_insert()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    PERFORM pg_sleep(0.2);
                    RETURN NEW;
                END;
                $$
                """
            )
        )
        await session.execute(
            text(
                """
                CREATE TRIGGER t010_delay_workspace_insert
                BEFORE INSERT ON workspaces
                FOR EACH ROW EXECUTE FUNCTION t010_delay_workspace_insert()
                """
            )
        )

    app = create_app(
        settings=_settings(t010_postgres_url, mode="public-demo"),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    try:
        first, second = await asyncio.gather(
            asgi_request(app, method="GET", path="/api/v1/config"),
            asgi_request(app, method="GET", path="/api/v1/config"),
        )
    finally:
        async with t010_session_factory.begin() as session:
            await session.execute(
                text("DROP TRIGGER IF EXISTS t010_delay_workspace_insert ON workspaces")
            )
            await session.execute(
                text("DROP FUNCTION IF EXISTS t010_delay_workspace_insert()")
            )

    assert first.status == second.status == 200
    first_cookie = first.header("set-cookie")
    second_cookie = second.header("set-cookie")
    assert first_cookie is not None and second_cookie is not None
    assert first_cookie != second_cookie
    assert await _counts(t010_session_factory) == (3, 1, 0, 2)


def test_settings_reject_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        _settings(
            "postgresql+psycopg://test:test@localhost/test",
            mode=cast(AppMode, "attacker"),
        )
