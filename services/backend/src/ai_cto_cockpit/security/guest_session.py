from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from types import MappingProxyType
from typing import Final, cast

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ai_cto_cockpit.settings import Settings

COOKIE_NAME: Final = "ai_cto_guest"
COOKIE_PROFILE_VERSION: Final = "public-demo-v1"

_COOKIE_FORMAT_VERSION: Final = "v1"
_TOKEN_SIZE: Final = 32
_DERIVATION_SALT: Final = b"ai-cto-cockpit/session-key-ring/v1\x00"
_SIGNING_INFO: Final = b"cookie-signing/hmac-sha-256/v1"
_FINGERPRINT_INFO: Final = b"cookie-fingerprint/hmac-sha-256/v1"
_ENCRYPTION_INFO: Final = b"reset-token-encryption/aes-256-gcm/v1"
_B64URL_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_CLAIM_NAMES: Final = ("exp", "iat", "kid", "profile", "sid", "token")


class InvalidGuestSession(ValueError):
    """A guest cookie cannot establish or identify a trusted session."""


@dataclass(frozen=True, slots=True)
class SessionKey:
    key_id: str
    signing_key: bytes
    fingerprint_key: bytes
    encryption_key: bytes
    cookie_secure: bool


class SessionKeyRing:
    """Versioned, domain-separated session keys retained across rotation."""

    def __init__(self, *, active_key_id: str, keys: Mapping[str, SessionKey]) -> None:
        copied = dict(keys)
        if active_key_id not in copied:
            raise ValueError("The active session key is unavailable")
        self._active_key_id = active_key_id
        self._keys: Mapping[str, SessionKey] = MappingProxyType(copied)

    @classmethod
    def from_settings(cls, settings: Settings) -> SessionKeyRing:
        roots = {
            settings.session_signing_key_id: settings.session_signing_key,
            **settings.session_retained_signing_keys,
        }
        keys = {
            key_id: SessionKey(
                key_id=key_id,
                signing_key=_derive_key(root, _SIGNING_INFO),
                fingerprint_key=_derive_key(root, _FINGERPRINT_INFO),
                encryption_key=_derive_key(root, _ENCRYPTION_INFO),
                cookie_secure=(
                    settings.cookie_secure
                    if key_id == settings.session_signing_key_id
                    else settings.session_retained_cookie_secure.get(
                        key_id,
                        settings.cookie_secure,
                    )
                ),
            )
            for key_id, root in roots.items()
        }
        return cls(active_key_id=settings.session_signing_key_id, keys=keys)

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    @property
    def active(self) -> SessionKey:
        return self._keys[self._active_key_id]

    def get(self, key_id: str) -> SessionKey:
        try:
            return self._keys[key_id]
        except KeyError as error:
            raise InvalidGuestSession("The guest-session key is unavailable") from error

    def encryption_key(self, key_id: str) -> bytes:
        return self.get(key_id).encryption_key


@dataclass(frozen=True, slots=True)
class GuestSessionClaims:
    session_id: uuid.UUID
    token: bytes
    issued_at: datetime
    expires_at: datetime
    key_id: str
    profile_version: str


@dataclass(frozen=True, slots=True)
class IssuedGuestCookie:
    value: str
    set_cookie: str


class GuestSessionCodec:
    """Issue and verify the repository's closed guest-cookie profile."""

    def __init__(
        self,
        key_ring: SessionKeyRing,
        *,
        cookie_secure: bool,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._key_ring = key_ring
        if cookie_secure != key_ring.active.cookie_secure:
            raise ValueError("Active cookie policy must match its signing-key profile")
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def key_ring(self) -> SessionKeyRing:
        return self._key_ring

    @property
    def active_key_id(self) -> str:
        return self._key_ring.active_key_id

    @staticmethod
    def token_hash(token: bytes) -> bytes:
        if len(token) != _TOKEN_SIZE:
            raise ValueError("Guest-session tokens must contain exactly 32 bytes")
        return hashlib.sha256(token).digest()

    def encryption_key(self, key_id: str) -> bytes:
        return self._key_ring.encryption_key(key_id)

    def issue(
        self,
        *,
        session_id: uuid.UUID,
        token: bytes,
        issued_at: datetime,
        expires_at: datetime,
        key_id: str | None = None,
    ) -> IssuedGuestCookie:
        normalized_issued_at = _normalize_datetime(issued_at)
        normalized_expires_at = _normalize_datetime(expires_at)
        if normalized_expires_at <= normalized_issued_at:
            raise ValueError("Guest-session expiry must follow its issue time")
        if session_id.version != 7:
            raise ValueError("Guest-session identity must be UUIDv7")
        if len(token) != _TOKEN_SIZE:
            raise ValueError("Guest-session tokens must contain exactly 32 bytes")

        selected_key = self._key_ring.get(key_id or self._key_ring.active_key_id)
        document = {
            "exp": _canonical_datetime(normalized_expires_at),
            "iat": _canonical_datetime(normalized_issued_at),
            "kid": selected_key.key_id,
            "profile": COOKIE_PROFILE_VERSION,
            "sid": _encode_base64url(session_id.bytes),
            "token": _encode_base64url(token),
        }
        payload = _canonical_json(document)
        encoded_payload = _encode_base64url(payload)
        signed = f"{_COOKIE_FORMAT_VERSION}.{encoded_payload}"
        signature = hmac.digest(
            selected_key.signing_key,
            signed.encode("ascii"),
            "sha256",
        )
        value = f"{signed}.{_encode_base64url(signature)}"
        return IssuedGuestCookie(
            value=value,
            set_cookie=self._serialize_set_cookie(
                value,
                normalized_expires_at,
                cookie_secure=selected_key.cookie_secure,
            ),
        )

    def verify(
        self,
        value: str,
        *,
        allow_expired: bool = False,
        now: datetime | None = None,
    ) -> GuestSessionClaims:
        version, encoded_payload, encoded_signature = _split_cookie(value)
        if version != _COOKIE_FORMAT_VERSION:
            raise InvalidGuestSession("The guest-session version is unsupported")

        payload = _decode_base64url(encoded_payload)
        signature = _decode_base64url(encoded_signature)
        if len(signature) != hashlib.sha256().digest_size:
            raise InvalidGuestSession("The guest-session signature is malformed")
        document = _decode_claims(payload)

        key = self._key_ring.get(document["kid"])
        signed = f"{version}.{encoded_payload}"
        expected_signature = hmac.digest(
            key.signing_key,
            signed.encode("ascii"),
            "sha256",
        )
        if not hmac.compare_digest(signature, expected_signature):
            raise InvalidGuestSession("The guest-session signature is invalid")

        claims = _claims_from_document(document)
        trusted_now = _normalize_datetime(now if now is not None else self._clock())
        if claims.issued_at > trusted_now:
            raise InvalidGuestSession("The guest session is not active yet")
        if not allow_expired and claims.expires_at <= trusted_now:
            raise InvalidGuestSession("The guest session has expired")
        return claims

    def fingerprint(
        self,
        value: str,
        *,
        allow_expired: bool = False,
        now: datetime | None = None,
    ) -> bytes:
        claims = self.verify(value, allow_expired=allow_expired, now=now)
        key = self._key_ring.get(claims.key_id)
        return hmac.digest(key.fingerprint_key, value.encode("ascii"), "sha256")

    def _serialize_set_cookie(
        self,
        value: str,
        expires_at: datetime,
        *,
        cookie_secure: bool,
    ) -> str:
        attributes = [
            f"{COOKIE_NAME}={value}",
            "Path=/",
            f"Expires={format_datetime(expires_at, usegmt=True)}",
            "HttpOnly",
            "SameSite=Lax",
        ]
        if cookie_secure:
            attributes.append("Secure")
        return "; ".join(attributes)


def _derive_key(root: str, info: bytes) -> bytes:
    encoded_root = root.encode("utf-8")
    if len(encoded_root) < 32:
        raise ValueError("Session signing keys need at least 32 bytes")
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_DERIVATION_SALT,
        info=info,
    ).derive(encoded_root)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Guest-session timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except (TypeError, ValueError) as error:
        raise InvalidGuestSession("A guest-session timestamp is malformed") from error
    return parsed


def _canonical_json(document: Mapping[str, str]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_base64url(value: str) -> bytes:
    if not value or not _B64URL_PATTERN.fullmatch(value):
        raise InvalidGuestSession("A guest-session segment is malformed")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as error:
        raise InvalidGuestSession("A guest-session segment is malformed") from error
    if not decoded or _encode_base64url(decoded) != value:
        raise InvalidGuestSession("A guest-session segment is noncanonical")
    return decoded


def _split_cookie(value: str) -> tuple[str, str, str]:
    if not value.isascii():
        raise InvalidGuestSession("The guest-session cookie is malformed")
    parts = value.split(".")
    if len(parts) != 3 or any(not part for part in parts):
        raise InvalidGuestSession("The guest-session cookie is malformed")
    return parts[0], parts[1], parts[2]


def _decode_claims(payload: bytes) -> dict[str, str]:
    try:
        decoded = cast(object, json.loads(payload))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InvalidGuestSession("The guest-session claims are malformed") from error
    if not isinstance(decoded, dict):
        raise InvalidGuestSession("The guest-session claim set is invalid")
    raw_document = cast(dict[object, object], decoded)
    document: dict[str, str] = {}
    for key, value in raw_document.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise InvalidGuestSession("A guest-session claim has an invalid type")
        document[key] = value
    if tuple(sorted(document)) != _CLAIM_NAMES:
        raise InvalidGuestSession("The guest-session claim set is invalid")
    if _canonical_json(document) != payload:
        raise InvalidGuestSession("The guest-session claims are noncanonical")
    return document


def _claims_from_document(document: Mapping[str, str]) -> GuestSessionClaims:
    if document["profile"] != COOKIE_PROFILE_VERSION:
        raise InvalidGuestSession("The guest-session cookie profile is unsupported")
    try:
        session_id = uuid.UUID(bytes=_decode_base64url(document["sid"]))
    except (ValueError, AttributeError) as error:
        raise InvalidGuestSession("The guest-session identity is malformed") from error
    if session_id.version != 7:
        raise InvalidGuestSession("The guest-session identity is invalid")
    token = _decode_base64url(document["token"])
    if len(token) != _TOKEN_SIZE:
        raise InvalidGuestSession("The guest-session token is malformed")
    issued_at = _parse_datetime(document["iat"])
    expires_at = _parse_datetime(document["exp"])
    if expires_at <= issued_at:
        raise InvalidGuestSession("The guest-session lifetime is invalid")
    return GuestSessionClaims(
        session_id=session_id,
        token=token,
        issued_at=issued_at,
        expires_at=expires_at,
        key_id=document["kid"],
        profile_version=document["profile"],
    )
