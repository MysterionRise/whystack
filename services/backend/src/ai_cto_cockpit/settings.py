from __future__ import annotations

import re
import uuid
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppMode = Literal["public-demo", "local-data"]

_KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_DEFAULT_SEED_WORKSPACE_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000001")
_DEFAULT_LOCAL_WORKSPACE_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000002")


class Settings(BaseSettings):
    """Process settings read once and kept immutable for the process lifetime."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_prefix="",
        extra="forbid",
        frozen=True,
    )

    app_mode: AppMode = "public-demo"
    database_url: str
    qdrant_url: str
    session_signing_key: str = Field(min_length=32, repr=False)
    session_signing_key_id: str = "cookie-key-v1"
    session_retained_signing_keys: dict[str, str] = Field(
        default_factory=dict,
        repr=False,
    )
    session_retained_cookie_secure: dict[str, bool] = Field(default_factory=dict)
    cookie_secure: bool = True
    local_compose: bool = False
    seed_workspace_id: uuid.UUID = _DEFAULT_SEED_WORKSPACE_ID
    local_workspace_id: uuid.UUID = _DEFAULT_LOCAL_WORKSPACE_ID

    @model_validator(mode="after")
    def validate_session_keys_and_workspace_ids(self) -> Self:
        if not _KEY_ID_PATTERN.fullmatch(self.session_signing_key_id):
            raise ValueError("Session signing key ID is invalid")
        if self.session_signing_key_id in self.session_retained_signing_keys:
            raise ValueError("The active session signing key cannot also be retained")

        for key_id, key in self.session_retained_signing_keys.items():
            if not _KEY_ID_PATTERN.fullmatch(key_id):
                raise ValueError("A retained session signing key ID is invalid")
            if len(key.encode("utf-8")) < 32:
                raise ValueError("Retained session signing keys need at least 32 bytes")

        unknown_profiles = set(self.session_retained_cookie_secure).difference(
            self.session_retained_signing_keys
        )
        if unknown_profiles:
            raise ValueError("A retained cookie profile has no retained signing key")
        if not self.cookie_secure and not self.local_compose:
            raise ValueError("Only the explicit local Compose profile may omit Secure")
        if (
            not self.local_compose
            and False in self.session_retained_cookie_secure.values()
        ):
            raise ValueError(
                "Only the explicit local Compose profile may retain insecure cookies"
            )

        if len(self.session_signing_key.encode("utf-8")) < 32:
            raise ValueError("The active session signing key needs at least 32 bytes")
        if self.seed_workspace_id.version != 7:
            raise ValueError("The seed workspace identity must be UUIDv7")
        if self.local_workspace_id.version != 7:
            raise ValueError("The local workspace identity must be UUIDv7")
        if self.seed_workspace_id == self.local_workspace_id:
            raise ValueError("Seed and local workspace identities must differ")
        return self
