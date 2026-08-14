from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from ai_cto_cockpit.security.guest_session import (
    COOKIE_NAME,
    GuestSessionCodec,
    InvalidGuestSession,
    SessionKeyRing,
)
from ai_cto_cockpit.settings import Settings

NOW = datetime(2026, 8, 14, 12, 0, 0, 123456, tzinfo=UTC)
SESSION_ID = uuid.UUID("0198b0f0-1000-7000-8000-000000000001")
TOKEN = bytes(range(32))
CURRENT_KEY = "current-session-key-with-more-than-thirty-two-bytes"
OLD_KEY = "retained-session-key-with-more-than-thirty-two-bytes"


def _settings(
    *,
    key: str = CURRENT_KEY,
    key_id: str = "current-v1",
    retained: dict[str, str] | None = None,
    secure: bool = True,
) -> Settings:
    return Settings(
        app_mode="public-demo",
        database_url="postgresql+psycopg://test:test@127.0.0.1:1/test",
        qdrant_url="http://127.0.0.1:1",
        session_signing_key=key,
        session_signing_key_id=key_id,
        session_retained_signing_keys=retained or {},
        cookie_secure=secure,
        local_compose=not secure,
        seed_workspace_id=uuid.UUID("0198b0f0-0000-7000-8000-000000000001"),
        local_workspace_id=uuid.UUID("0198b0f0-0000-7000-8000-000000000002"),
    )


def _codec(
    settings: Settings | None = None,
    *,
    now: datetime = NOW,
) -> GuestSessionCodec:
    selected = settings or _settings()
    return GuestSessionCodec(
        SessionKeyRing.from_settings(selected),
        cookie_secure=selected.cookie_secure,
        clock=lambda: now,
    )


def _issue(codec: GuestSessionCodec):  # type: ignore[no-untyped-def]
    return codec.issue(
        session_id=SESSION_ID,
        token=TOKEN,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )


def _replace_segment(value: str, index: int, replacement: str) -> str:
    parts = value.split(".")
    parts[index] = replacement
    return ".".join(parts)


def _flip_base64url(segment: str) -> str:
    replacement = "A" if segment[-1] != "A" else "B"
    return segment[:-1] + replacement


def test_cookie_is_opaque_signed_and_contains_only_session_claims() -> None:
    codec = _codec()
    issued = _issue(codec)
    claims = codec.verify(issued.value)

    assert claims.session_id == SESSION_ID
    assert claims.token == TOKEN
    assert claims.issued_at == NOW
    assert claims.expires_at == NOW + timedelta(hours=24)
    assert claims.key_id == "current-v1"
    assert claims.profile_version == "public-demo-v1"
    assert not hasattr(claims, "workspace_id")
    assert str(SESSION_ID) not in issued.value
    assert COOKIE_NAME == "ai_cto_guest"
    assert issued.set_cookie.startswith(f"{COOKIE_NAME}=")
    assert "; Path=/" in issued.set_cookie
    assert "; HttpOnly" in issued.set_cookie
    assert "; SameSite=Lax" in issued.set_cookie
    assert "; Secure" in issued.set_cookie


def test_local_compose_cookie_omits_only_secure_attribute() -> None:
    issued = _issue(_codec(_settings(secure=False)))
    assert "; HttpOnly" in issued.set_cookie
    assert "; SameSite=Lax" in issued.set_cookie
    assert "; Secure" not in issued.set_cookie


@pytest.mark.parametrize("mutation", ["version", "payload", "signature"])
def test_cookie_tampering_fails_closed(mutation: str) -> None:
    codec = _codec()
    issued = _issue(codec)
    parts = issued.value.split(".")
    assert len(parts) == 3
    if mutation == "version":
        tampered = _replace_segment(issued.value, 0, "v2")
    elif mutation == "payload":
        tampered = _replace_segment(issued.value, 1, _flip_base64url(parts[1]))
    else:
        tampered = _replace_segment(issued.value, 2, _flip_base64url(parts[2]))
    with pytest.raises(InvalidGuestSession):
        codec.verify(tampered)
    with pytest.raises(InvalidGuestSession):
        codec.fingerprint(tampered)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "v1.only-two",
        "v1.***.***",
        "v1.e30.invalid",
        "v1..",
    ],
)
def test_malformed_cookie_fails_closed(value: str) -> None:
    with pytest.raises(InvalidGuestSession):
        _codec().verify(value)


def test_expiry_boundary_and_reset_only_verification() -> None:
    issued = _issue(_codec())
    at_expiry = _codec(now=NOW + timedelta(hours=24))
    with pytest.raises(InvalidGuestSession):
        at_expiry.verify(issued.value)
    claims = at_expiry.verify(issued.value, allow_expired=True)
    assert claims.session_id == SESSION_ID
    assert len(at_expiry.fingerprint(issued.value, allow_expired=True)) == 32


def test_retained_key_verifies_old_cookie_across_restart_and_rotation() -> None:
    old_codec = _codec(_settings(key=OLD_KEY, key_id="old-v1"))
    issued = _issue(old_codec)
    rotated = _codec(
        _settings(
            key=CURRENT_KEY,
            key_id="current-v1",
            retained={"old-v1": OLD_KEY},
        )
    )
    assert rotated.verify(issued.value).session_id == SESSION_ID
    assert rotated.fingerprint(issued.value) == old_codec.fingerprint(issued.value)


def test_retained_key_reconstructs_its_original_cookie_security_profile() -> None:
    old_settings = Settings(
        app_mode="public-demo",
        database_url="postgresql+psycopg://test:test@127.0.0.1:1/test",
        qdrant_url="http://127.0.0.1:1",
        session_signing_key=OLD_KEY,
        session_signing_key_id="old-v1",
        session_retained_signing_keys={},
        session_retained_cookie_secure={},
        cookie_secure=False,
        local_compose=True,
    )
    original_codec = _codec(old_settings)
    original = _issue(original_codec)
    claims = original_codec.verify(original.value)

    rotated_settings = Settings(
        app_mode="public-demo",
        database_url="postgresql+psycopg://test:test@127.0.0.1:1/test",
        qdrant_url="http://127.0.0.1:1",
        session_signing_key=CURRENT_KEY,
        session_signing_key_id="current-v1",
        session_retained_signing_keys={"old-v1": OLD_KEY},
        session_retained_cookie_secure={"old-v1": False},
        cookie_secure=True,
        local_compose=True,
    )
    restarted = _codec(rotated_settings)
    replayed = restarted.issue(
        session_id=claims.session_id,
        token=claims.token,
        issued_at=claims.issued_at,
        expires_at=claims.expires_at,
        key_id=claims.key_id,
    )

    assert replayed.value == original.value
    assert replayed.set_cookie == original.set_cookie
    assert "; Secure" not in replayed.set_cookie


def test_insecure_cookie_is_rejected_outside_explicit_local_compose() -> None:
    with pytest.raises(ValueError, match="local Compose"):
        Settings(
            app_mode="public-demo",
            database_url="postgresql+psycopg://test:test@127.0.0.1:1/test",
            qdrant_url="http://127.0.0.1:1",
            session_signing_key=CURRENT_KEY,
            cookie_secure=False,
        )


def test_unknown_key_identifier_and_noncanonical_payload_fail_closed() -> None:
    issued = _issue(_codec(_settings(key=OLD_KEY, key_id="old-v1")))
    with pytest.raises(InvalidGuestSession):
        _codec().verify(issued.value)

    parts = issued.value.split(".")
    payload = base64.urlsafe_b64decode(parts[1] + "==")
    noncanonical = base64.urlsafe_b64encode(b" " + payload).rstrip(b"=").decode()
    with pytest.raises(InvalidGuestSession):
        _codec(_settings(key=OLD_KEY, key_id="old-v1")).verify(
            _replace_segment(issued.value, 1, noncanonical)
        )
