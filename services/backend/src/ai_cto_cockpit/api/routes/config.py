from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from urllib.parse import parse_qsl

from cryptography.exceptions import InvalidTag
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.api.dependencies.context import (
    WorkspaceContextUnauthorized,
    resolve_workspace_context,
)
from ai_cto_cockpit.api.errors import api_error_response
from ai_cto_cockpit.api.headers import IdempotencyKey
from ai_cto_cockpit.contracts.config import ResetSessionResponse, RuntimeConfig
from ai_cto_cockpit.persistence.models import (
    GuestSession,
    Job,
    JobKind,
    JobStatus,
    ResetReplayReceipt,
    Workspace,
    WorkspaceKind,
    WorkspaceStatus,
    new_uuid7,
)
from ai_cto_cockpit.persistence.repositories import (
    ResetReplayAad,
    ResetReplayIntegrityError,
    ResetReplayRepository,
    decrypt_replacement_token,
    encrypt_replacement_token,
    hash_reset_replay_idempotency_key,
    sha256_bytes,
)
from ai_cto_cockpit.security.guest_session import (
    COOKIE_NAME,
    GuestSessionCodec,
    InvalidGuestSession,
)
from ai_cto_cockpit.settings import Settings

router = APIRouter()

_RESET_OPERATION = "reset-guest-session-v1"
_AAD_VERSION = "reset-replay-aad-v1"
_COOKIE_PROFILE = "public-demo-v1"
_SERIALIZER_VERSION = "canonical-json-v1"
_CONTENT_TYPE = "application/json"

type DatabaseClock = Callable[[AsyncSession], Awaitable[datetime]]
type ResetResponseSerializer = Callable[[ResetSessionResponse], bytes]
type SessionFactory = async_sessionmaker[AsyncSession]


class ResetReplayFailure(ValueError):
    """A stored reset receipt cannot safely reproduce its original response."""


@dataclass(frozen=True, slots=True)
class ResetReplayResult:
    status: int
    content_type: str
    body: bytes
    set_cookie: str


async def _database_time(
    session: AsyncSession,
    provider: DatabaseClock | None,
) -> datetime:
    value = (
        await provider(session)
        if provider is not None
        else await session.scalar(select(func.clock_timestamp()))
    )
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        raise RuntimeError("PostgreSQL must supply a timezone-aware timestamp")
    return value


def _canonical_json(document: dict[str, object]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def default_reset_response_serializer(response: ResetSessionResponse) -> bytes:
    document = response.model_dump(mode="json", by_alias=True)
    return _canonical_json(cast(dict[str, object], document))


def canonical_reset_request_hash(
    *,
    method: str,
    path: str,
    query_string: str,
) -> str:
    """Hash the versioned normalized reset request without credential headers."""

    query = sorted(
        parse_qsl(query_string, keep_blank_values=True, strict_parsing=False)
    )
    canonical = _canonical_json(
        {
            "body": {},
            "method": method.upper(),
            "operation": _RESET_OPERATION,
            "path": path,
            "query": [[name, value] for name, value in query],
            "version": 1,
        }
    )
    return hashlib.sha256(canonical).hexdigest()


def _receipt_aad(receipt: ResetReplayReceipt) -> ResetReplayAad:
    return ResetReplayAad(
        id=receipt.id,
        old_session_fingerprint=receipt.old_session_fingerprint,
        operation=receipt.operation,
        key_hash=receipt.key_hash,
        request_hash=receipt.request_hash,
        replacement_session_id=receipt.replacement_session_id,
        replacement_token_hash=receipt.replacement_token_hash,
        encryption_key_id=receipt.encryption_key_id,
        aad_version=receipt.aad_version,
        cookie_profile_version=receipt.cookie_profile_version,
        cookie_signing_key_id=receipt.cookie_signing_key_id,
        cookie_issued_at=receipt.cookie_issued_at,
        cookie_expires_at=receipt.cookie_expires_at,
        response_status=receipt.response_status,
        response_content_type=receipt.response_content_type,
        response_serializer_version=receipt.response_serializer_version,
        response_body_hash=receipt.response_body_hash,
        created_at=receipt.created_at,
        expires_at=receipt.expires_at,
    )


def replay_reset_receipt(
    receipt: ResetReplayReceipt,
    replacement_session: GuestSession,
    codec: GuestSessionCodec,
) -> ResetReplayResult:
    """Authenticate every stored field before reconstructing replacement access."""

    try:
        if receipt.cookie_profile_version != _COOKIE_PROFILE:
            raise ResetReplayFailure("Reset replay integrity check failed")
        if replacement_session.id != receipt.replacement_session_id:
            raise ResetReplayFailure("Reset replay integrity check failed")
        if not hmac.compare_digest(
            replacement_session.token_hash,
            receipt.replacement_token_hash,
        ):
            raise ResetReplayFailure("Reset replay integrity check failed")
        token = decrypt_replacement_token(
            receipt.replacement_token_ciphertext,
            key=codec.encryption_key(receipt.encryption_key_id),
            aad=_receipt_aad(receipt),
            expected_token_hash=replacement_session.token_hash,
            response_body_bytes=receipt.response_body_bytes,
        )
        issued = codec.issue(
            session_id=receipt.replacement_session_id,
            token=token,
            issued_at=receipt.cookie_issued_at,
            expires_at=receipt.cookie_expires_at,
            key_id=receipt.cookie_signing_key_id,
        )
    except (
        InvalidGuestSession,
        InvalidTag,
        KeyError,
        ResetReplayIntegrityError,
    ) as error:
        raise ResetReplayFailure("Reset replay integrity check failed") from error
    except ValueError as error:
        if isinstance(error, ResetReplayFailure):
            raise
        raise ResetReplayFailure("Reset replay integrity check failed") from error

    return ResetReplayResult(
        status=receipt.response_status,
        content_type=receipt.response_content_type,
        body=receipt.response_body_bytes,
        set_cookie=issued.set_cookie,
    )


def _runtime_config(
    *, settings: Settings, expires_at: datetime | None
) -> dict[str, object]:
    public_demo = settings.app_mode == "public-demo"
    contract = RuntimeConfig.model_validate(
        {
            "apiVersion": "v1",
            "mode": settings.app_mode,
            "capabilities": {
                "canCreateDecision": True,
                "canRunDecision": True,
                "canReplayRun": True,
                "canResetGuestWorkspace": public_demo,
                "persistentWorkspace": not public_demo,
                "canUpload": False,
                "canUseLocalGit": False,
                "canUseGitHub": False,
                "canUseWeb": False,
            },
            "guestExpiresAt": expires_at,
        }
    )
    return cast(dict[str, object], contract.model_dump(mode="json", by_alias=True))


def _api_error(status: int, *, code: str, message: str) -> JSONResponse:
    return api_error_response(status, code=code, message=message)


def _response(result: ResetReplayResult) -> Response:
    return Response(
        content=result.body,
        status_code=result.status,
        headers={
            "content-type": result.content_type,
            "set-cookie": result.set_cookie,
        },
    )


async def _ensure_shell(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    kind: WorkspaceKind,
    now: datetime,
) -> Workspace:
    await session.execute(
        postgresql_insert(Workspace)
        .values(
            id=workspace_id,
            kind=kind,
            status=WorkspaceStatus.ACTIVE,
            seed_parent_id=None,
            expires_at=None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=[Workspace.id])
    )
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise RuntimeError("Configured workspace shell could not be bootstrapped")
    if workspace.kind != kind or workspace.status != WorkspaceStatus.ACTIVE:
        raise RuntimeError("Configured workspace shell conflicts with canonical state")
    return workspace


async def _create_guest(
    session: AsyncSession,
    *,
    settings: Settings,
    codec: GuestSessionCodec,
    now: datetime,
) -> tuple[GuestSession, bytes]:
    await _ensure_shell(
        session,
        workspace_id=settings.seed_workspace_id,
        kind=WorkspaceKind.SEED,
        now=now,
    )
    expires_at = now + timedelta(hours=24)
    workspace = Workspace(
        id=new_uuid7(),
        kind=WorkspaceKind.GUEST,
        status=WorkspaceStatus.ACTIVE,
        seed_parent_id=settings.seed_workspace_id,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    # The models intentionally expose no ORM relationship. Flush the parent
    # explicitly so SQLAlchemy cannot order the independent INSERTs incorrectly.
    await session.flush()
    token = secrets.token_bytes(32)
    guest_session = GuestSession(
        id=new_uuid7(),
        workspace_id=workspace.id,
        token_hash=codec.token_hash(token),
        expires_at=expires_at,
        revoked_at=None,
        created_at=now,
    )
    session.add(guest_session)
    await session.flush()
    return guest_session, token


async def _get_runtime_config(request: Request) -> Response:
    settings = cast(Settings, request.app.state.settings)
    session_factory = cast(SessionFactory, request.app.state.session_factory)
    codec = cast(GuestSessionCodec, request.app.state.guest_session_codec)
    database_clock = cast(DatabaseClock | None, request.app.state.database_clock)

    if settings.app_mode == "local-data":
        async with session_factory.begin() as session:
            now = await _database_time(session, database_clock)
            await _ensure_shell(
                session,
                workspace_id=settings.local_workspace_id,
                kind=WorkspaceKind.LOCAL,
                now=now,
            )
        return JSONResponse(content=_runtime_config(settings=settings, expires_at=None))

    cookie_value = request.cookies.get(COOKIE_NAME)
    if cookie_value:
        async with session_factory() as session:
            now = await _database_time(session, database_clock)
        try:
            context = await resolve_workspace_context(
                cookie_value=cookie_value,
                settings=settings,
                session_factory=session_factory,
                codec=codec,
                now=now,
            )
        except WorkspaceContextUnauthorized:
            pass
        else:
            return JSONResponse(
                content=_runtime_config(
                    settings=settings,
                    expires_at=context.expires_at,
                )
            )

    async with session_factory.begin() as session:
        now = await _database_time(session, database_clock)
        guest_session, token = await _create_guest(
            session,
            settings=settings,
            codec=codec,
            now=now,
        )
    issued = codec.issue(
        session_id=guest_session.id,
        token=token,
        issued_at=now,
        expires_at=guest_session.expires_at,
    )
    return JSONResponse(
        content=_runtime_config(
            settings=settings,
            expires_at=guest_session.expires_at,
        ),
        headers={"set-cookie": issued.set_cookie},
    )


@router.get("/api/v1/config")
async def get_runtime_config(request: Request) -> Response:
    try:
        return await _get_runtime_config(request)
    except SQLAlchemyError:
        return _api_error(
            503,
            code="service_unavailable",
            message="A required service is unavailable.",
        )


async def _load_replay(
    session: AsyncSession,
    *,
    fingerprint: bytes,
    key_hash: bytes,
    request_hash: str,
    now: datetime,
    codec: GuestSessionCodec,
) -> Response | None:
    receipt = await ResetReplayRepository(session).get(
        old_session_fingerprint=fingerprint,
        operation=_RESET_OPERATION,
        key_hash=key_hash,
        now=now,
    )
    if receipt is None:
        return None
    if not hmac.compare_digest(receipt.request_hash, request_hash):
        return _api_error(
            409,
            code="idempotency_conflict",
            message="The idempotency key was used for a different request.",
        )
    replacement = await session.get(GuestSession, receipt.replacement_session_id)
    if replacement is None:
        return _api_error(
            401,
            code="session_unauthorized",
            message="A valid guest session is required.",
        )
    try:
        result = replay_reset_receipt(receipt, replacement, codec)
    except ResetReplayFailure:
        return _api_error(
            401,
            code="session_unauthorized",
            message="A valid guest session is required.",
        )
    return _response(result)


@router.post("/api/v1/session/reset")
async def reset_guest_session(
    request: Request,
    idempotency_key: IdempotencyKey,
) -> Response:
    settings = cast(Settings, request.app.state.settings)
    if settings.app_mode != "public-demo":
        return _api_error(
            403,
            code="capability_disabled",
            message="This capability is not available in local-data mode.",
        )

    cookie_value = request.cookies.get(COOKIE_NAME)
    if not cookie_value:
        return _api_error(
            401,
            code="session_unauthorized",
            message="A valid guest session is required.",
        )

    session_factory = cast(SessionFactory, request.app.state.session_factory)
    codec = cast(GuestSessionCodec, request.app.state.guest_session_codec)
    database_clock = cast(DatabaseClock | None, request.app.state.database_clock)
    serializer = cast(ResetResponseSerializer, request.app.state.reset_serializer)
    try:
        key_hash = hash_reset_replay_idempotency_key(idempotency_key)
    except ValueError:
        return _api_error(
            401,
            code="session_unauthorized",
            message="A valid guest session is required.",
        )
    request_hash = canonical_reset_request_hash(
        method=request.method,
        path=request.url.path,
        query_string=request.url.query,
    )

    result: ResetReplayResult | None = None
    async with session_factory.begin() as session:
        now = await _database_time(session, database_clock)
        try:
            claims = codec.verify(cookie_value, allow_expired=True, now=now)
            fingerprint = codec.fingerprint(
                cookie_value,
                allow_expired=True,
                now=now,
            )
        except InvalidGuestSession:
            return _api_error(
                401,
                code="session_unauthorized",
                message="A valid guest session is required.",
            )
        repository = ResetReplayRepository(session)
        await repository.purge_expired(now=now)
        replay = await _load_replay(
            session,
            fingerprint=fingerprint,
            key_hash=key_hash,
            request_hash=request_hash,
            now=now,
            codec=codec,
        )
        if replay is not None:
            return replay

        old_session = await session.scalar(
            select(GuestSession)
            .where(GuestSession.id == claims.session_id)
            .with_for_update()
        )
        now = await _database_time(session, database_clock)
        try:
            claims = codec.verify(cookie_value, allow_expired=True, now=now)
        except InvalidGuestSession:
            return _api_error(
                401,
                code="session_unauthorized",
                message="A valid guest session is required.",
            )
        if old_session is None or not hmac.compare_digest(
            old_session.token_hash,
            codec.token_hash(claims.token),
        ):
            return _api_error(
                401,
                code="session_unauthorized",
                message="A valid guest session is required.",
            )

        if old_session.revoked_at is not None:
            replay = await _load_replay(
                session,
                fingerprint=fingerprint,
                key_hash=key_hash,
                request_hash=request_hash,
                now=now,
                codec=codec,
            )
            if replay is not None:
                return replay
            return _api_error(
                401,
                code="session_unauthorized",
                message="A valid guest session is required.",
            )
        old_workspace = await session.get(
            Workspace,
            old_session.workspace_id,
            with_for_update=True,
        )
        now = await _database_time(session, database_clock)
        if (
            old_workspace is None
            or old_workspace.kind != WorkspaceKind.GUEST
            or old_workspace.status != WorkspaceStatus.ACTIVE
            or old_workspace.expires_at is None
            or old_session.expires_at <= now
            or old_workspace.expires_at <= now
        ):
            return _api_error(
                401,
                code="session_unauthorized",
                message="A valid guest session is required.",
            )

        replacement_session, replacement_token = await _create_guest(
            session,
            settings=settings,
            codec=codec,
            now=now,
        )
        issued = codec.issue(
            session_id=replacement_session.id,
            token=replacement_token,
            issued_at=now,
            expires_at=replacement_session.expires_at,
        )
        response_contract = ResetSessionResponse.model_validate(
            {
                "resetAccepted": True,
                "guestExpiresAt": replacement_session.expires_at,
            }
        )
        response_body = serializer(response_contract)
        response_hash = hashlib.sha256(response_body).hexdigest()

        old_session.revoked_at = now
        old_workspace.status = WorkspaceStatus.DELETING
        old_workspace.updated_at = now
        session.add(
            Job(
                id=new_uuid7(),
                workspace_id=old_workspace.id,
                kind=JobKind.DELETE_WORKSPACE,
                payload={"workspaceId": str(old_workspace.id)},
                status=JobStatus.AVAILABLE,
                available_at=now,
                lease_owner=None,
                lease_expires_at=None,
                attempt_count=0,
                last_error_code=None,
                created_at=now,
                updated_at=now,
                completed_at=None,
            )
        )

        receipt = ResetReplayReceipt(
            id=new_uuid7(),
            old_session_fingerprint=fingerprint,
            operation=_RESET_OPERATION,
            key_hash=key_hash,
            request_hash=request_hash,
            replacement_session_id=replacement_session.id,
            replacement_token_hash=sha256_bytes(replacement_token),
            replacement_token_ciphertext=b"",
            encryption_key_id=codec.active_key_id,
            aad_version=_AAD_VERSION,
            cookie_profile_version=_COOKIE_PROFILE,
            cookie_signing_key_id=codec.active_key_id,
            cookie_issued_at=now,
            cookie_expires_at=replacement_session.expires_at,
            response_status=202,
            response_content_type=_CONTENT_TYPE,
            response_serializer_version=_SERIALIZER_VERSION,
            response_body_bytes=response_body,
            response_body_hash=response_hash,
            created_at=now,
            expires_at=now + timedelta(minutes=10),
        )
        receipt.replacement_token_ciphertext = encrypt_replacement_token(
            replacement_token,
            key=codec.encryption_key(receipt.encryption_key_id),
            aad=_receipt_aad(receipt),
        )
        session.add(receipt)
        result = ResetReplayResult(
            status=202,
            content_type=_CONTENT_TYPE,
            body=response_body,
            set_cookie=issued.set_cookie,
        )

    assert result is not None
    return _response(result)
