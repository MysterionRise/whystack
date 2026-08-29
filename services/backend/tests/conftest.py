from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.persistence.session import (
    create_database_engine,
    create_session_factory,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
POSTGRES_IMAGE = (
    "postgres:17.10-bookworm@"
    "sha256:4f736ae292687621d4dbe0d499ffd024a36bd2ee7d8ca6f2ccd4c800f047b394"
)


def _run(command_line: Sequence[str], *, timeout: int = 90) -> str:
    result = subprocess.run(
        list(command_line),
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout,
    )
    assert result.returncode == 0, (
        f"Command exited {result.returncode}: {' '.join(command_line)}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result.stdout.strip()


@pytest.fixture(scope="session")
def t010_postgres_url() -> Iterator[str]:
    assert shutil.which("docker"), "Docker CLI is required for T010 API tests"
    _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    container = f"cockpit_t010_{uuid.uuid4().hex[:12]}"
    password = uuid.uuid4().hex
    _run(
        [
            "docker",
            "run",
            "--detach",
            "--rm",
            "--name",
            container,
            "--env",
            "POSTGRES_DB=ai_cto",
            "--env",
            "POSTGRES_USER=ai_cto",
            "--env",
            f"POSTGRES_PASSWORD={password}",
            "--health-cmd",
            "pg_isready -U ai_cto -d ai_cto",
            "--health-interval",
            "1s",
            "--health-timeout",
            "3s",
            "--health-retries",
            "60",
            "--publish",
            "127.0.0.1::5432",
            POSTGRES_IMAGE,
        ],
        timeout=120,
    )
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            state = json.loads(
                _run(["docker", "inspect", container, "--format", "{{json .State}}"])
            )
            if state.get("Health", {}).get("Status") == "healthy":
                break
            time.sleep(0.5)
        else:
            raise AssertionError("T010 PostgreSQL container did not become healthy")

        port_json = _run(
            [
                "docker",
                "inspect",
                container,
                "--format",
                '{{json (index .NetworkSettings.Ports "5432/tcp")}}',
            ]
        )
        raw_bindings: object = json.loads(port_json)
        assert isinstance(raw_bindings, list) and raw_bindings
        bindings = cast(list[object], raw_bindings)
        first_binding = bindings[0]
        assert isinstance(first_binding, dict)
        binding = cast(dict[object, object], first_binding)
        host_port = binding.get("HostPort")
        assert isinstance(host_port, str)
        port = int(host_port)
        database_url = f"postgresql+psycopg://ai_cto:{password}@127.0.0.1:{port}/ai_cto"

        previous_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
        try:
            config = Config(str(REPOSITORY_ROOT / "services/backend/alembic.ini"))
            command.upgrade(config, "head")
        finally:
            if previous_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_url
        yield database_url
    finally:
        subprocess.run(
            ["docker", "stop", container],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )


@pytest_asyncio.fixture
async def t010_session_factory(
    t010_postgres_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_database_engine(t010_postgres_url)
    factory = create_session_factory(engine)
    table_names = (
        "reset_replay_receipts",
        "deletion_completions",
        "idempotency_records",
        "jobs",
        "run_events",
        "runs",
        "decision_revisions",
        "decisions",
        "guest_sessions",
        "workspaces",
    )
    async with engine.begin() as connection:
        await connection.execute(
            text(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE")
        )
    try:
        yield factory
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE"
                )
            )
        await engine.dispose()
