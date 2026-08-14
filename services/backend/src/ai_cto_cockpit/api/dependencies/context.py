from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.persistence.models import (
    GuestSession,
    Workspace,
    WorkspaceKind,
    WorkspaceStatus,
)
from ai_cto_cockpit.security.guest_session import (
    GuestSessionCodec,
    InvalidGuestSession,
)
from ai_cto_cockpit.settings import Settings


class WorkspaceContextUnauthorized(ValueError):
    """A request cannot derive an active workspace from trusted server state."""


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    workspace_id: uuid.UUID
    kind: WorkspaceKind
    expires_at: datetime | None


async def resolve_workspace_context(
    *,
    cookie_value: str | None,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    codec: GuestSessionCodec,
    now: datetime,
) -> WorkspaceContext:
    """Resolve scope from frozen settings or a verified, persisted guest session."""

    if settings.app_mode == "local-data":
        async with session_factory() as session:
            workspace = await session.scalar(
                select(Workspace).where(
                    Workspace.id == settings.local_workspace_id,
                    Workspace.kind == WorkspaceKind.LOCAL,
                    Workspace.status == WorkspaceStatus.ACTIVE,
                )
            )
        if workspace is None:
            raise WorkspaceContextUnauthorized("Local workspace is unavailable")
        return WorkspaceContext(
            workspace_id=workspace.id,
            kind=workspace.kind,
            expires_at=None,
        )

    if not cookie_value:
        raise WorkspaceContextUnauthorized("A guest session is required")
    try:
        claims = codec.verify(cookie_value, now=now)
    except InvalidGuestSession as error:
        raise WorkspaceContextUnauthorized("A guest session is required") from error

    async with session_factory() as session:
        guest_session = await session.get(GuestSession, claims.session_id)
        if guest_session is None:
            raise WorkspaceContextUnauthorized("A guest session is required")
        if not hmac.compare_digest(
            guest_session.token_hash,
            codec.token_hash(claims.token),
        ):
            raise WorkspaceContextUnauthorized("A guest session is required")
        if guest_session.revoked_at is not None or guest_session.expires_at <= now:
            raise WorkspaceContextUnauthorized("A guest session is required")
        workspace = await session.scalar(
            select(Workspace).where(
                Workspace.id == guest_session.workspace_id,
                Workspace.kind == WorkspaceKind.GUEST,
                Workspace.status == WorkspaceStatus.ACTIVE,
                Workspace.expires_at > now,
            )
        )
        if workspace is None:
            raise WorkspaceContextUnauthorized("A guest session is required")

    return WorkspaceContext(
        workspace_id=workspace.id,
        kind=workspace.kind,
        expires_at=workspace.expires_at,
    )
