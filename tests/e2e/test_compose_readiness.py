"""Acceptance test for the Phase A Compose process topology."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPOSITORY_ROOT / "infra" / "compose.yaml"
EXPECTED_SERVICES = {"api", "postgres", "qdrant", "web", "worker"}


def _redact(value: str, secrets: Sequence[str]) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


def _run(
    command: Sequence[str],
    *,
    secrets: Sequence[str] = (),
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            cwd=REPOSITORY_ROOT,
            env=os.environ.copy(),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        output = _redact(
            f"{error.stdout or ''}\n{error.stderr or ''}",
            secrets,
        )
        raise AssertionError(
            f"Command timed out after {timeout}s: {' '.join(command)}\n{output}"
        ) from error

    if result.returncode != 0:
        output = _redact(
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            secrets,
        )
        raise AssertionError(
            f"Command exited {result.returncode}: {' '.join(command)}\n{output}"
        )
    return result


def _parse_compose_ps(output: str) -> list[dict[str, object]]:
    stripped = output.strip()
    if not stripped:
        return []

    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        decoded = [json.loads(line) for line in stripped.splitlines()]

    if isinstance(decoded, dict):
        return [cast(dict[str, object], decoded)]
    assert isinstance(decoded, list), "Compose ps JSON must be an object or array"
    decoded_list = cast(list[object], decoded)
    assert all(isinstance(item, dict) for item in decoded_list)
    return [cast(dict[str, object], item) for item in decoded_list]


def _parse_last_json_line(output: str) -> dict[str, object]:
    lines = [line for line in output.splitlines() if line.strip()]
    assert lines, "Expected a JSON result from the Compose probe"
    decoded = json.loads(lines[-1])
    assert isinstance(decoded, dict), "Compose probe must return a JSON object"
    return cast(dict[str, object], decoded)


def test_compose_topology_is_ready(tmp_path: Path) -> None:
    assert COMPOSE_FILE.is_file(), (
        "T002 RED: Compose topology is absent at infra/compose.yaml"
    )

    assert shutil.which("docker"), "Docker CLI is required for Compose readiness"
    _run(["docker", "compose", "version"])
    _run(["docker", "info", "--format", "{{.ServerVersion}}"])

    project = f"cockpit_t002_{uuid.uuid4().hex[:12]}"
    database_password = uuid.uuid4().hex
    signing_key = uuid.uuid4().hex + uuid.uuid4().hex
    secrets = (database_password, signing_key)
    env_file = tmp_path / "compose.env"
    env_file.write_text(
        textwrap.dedent(
            f"""\
            APP_MODE=public-demo
            WEB_PORT=0
            API_PORT=0
            POSTGRES_DB=ai_cto
            POSTGRES_USER=ai_cto
            POSTGRES_PASSWORD={database_password}
            DATABASE_URL=postgresql+psycopg://ai_cto:{database_password}@postgres:5432/ai_cto
            QDRANT_URL=http://qdrant:6333
            SESSION_SIGNING_KEY={signing_key}
            """
        ),
        encoding="utf-8",
    )

    compose = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "--file",
        str(COMPOSE_FILE),
        "--project-name",
        project,
    ]

    try:
        _run(
            [*compose, "up", "--build", "--wait", "--wait-timeout", "240"],
            secrets=secrets,
            timeout=300,
        )

        ps = _parse_compose_ps(
            _run([*compose, "ps", "--all", "--format", "json"]).stdout
        )
        services = {str(container.get("Service")): container for container in ps}
        assert set(services) == EXPECTED_SERVICES
        for service, container in services.items():
            assert container.get("State") == "running", (
                f"{service} is not running: {container}"
            )
            assert container.get("Health") == "healthy", (
                f"{service} is not healthy: {container}"
            )

        api_probe = textwrap.dedent(
            """\
            import json
            import os
            from pathlib import Path
            from urllib.parse import urlsplit
            from urllib.request import urlopen

            from alembic.config import Config
            from alembic.migration import MigrationContext
            from alembic.script import ScriptDirectory
            from sqlalchemy import create_engine, text
            from sqlalchemy.engine import make_url


            def get_json(path):
                with urlopen(f"http://127.0.0.1:8000{path}", timeout=5) as response:
                    return response.status, json.load(response)


            database_url = os.environ["DATABASE_URL"]
            parsed_database_url = make_url(database_url)
            assert parsed_database_url.host == "postgres"
            engine = create_engine(database_url)
            with engine.connect() as connection:
                postgres_value = connection.execute(text("SELECT 1")).scalar_one()
                database_heads = sorted(
                    MigrationContext.configure(connection).get_current_heads()
                )
            engine.dispose()

            alembic_path = Path("/app/services/backend/alembic.ini")
            alembic_config = Config(str(alembic_path))
            repository_heads = sorted(
                ScriptDirectory.from_config(alembic_config).get_heads()
            )

            qdrant_url = os.environ["QDRANT_URL"].rstrip("/")
            parsed_qdrant_url = urlsplit(qdrant_url)
            assert parsed_qdrant_url.hostname == "qdrant"
            with urlopen(f"{qdrant_url}/readyz", timeout=5) as response:
                qdrant_status = response.status

            live_status, live_body = get_json("/api/v1/health/live")
            ready_status, ready_body = get_json("/api/v1/health/ready")
            print(
                json.dumps(
                    {
                        "database_heads": database_heads,
                        "live": {"body": live_body, "status": live_status},
                        "postgres_value": postgres_value,
                        "provider_key_configured": bool(
                            os.environ.get("OPENROUTER_API_KEY")
                        ),
                        "qdrant_status": qdrant_status,
                        "ready": {"body": ready_body, "status": ready_status},
                        "repository_heads": repository_heads,
                    },
                    sort_keys=True,
                )
            )
            """
        )
        api_result = _parse_last_json_line(
            _run(
                [*compose, "exec", "-T", "api", "python", "-c", api_probe],
                secrets=secrets,
            ).stdout
        )
        assert api_result == {
            "database_heads": ["0001_walking_skeleton"],
            "live": {"body": {"status": "live"}, "status": 200},
            "postgres_value": 1,
            "provider_key_configured": False,
            "qdrant_status": 200,
            "ready": {
                "body": {
                    "checks": {
                        "migrations": "ready",
                        "postgres": "ready",
                        "qdrant": "ready",
                    },
                    "status": "ready",
                },
                "status": 200,
            },
            "repository_heads": ["0001_walking_skeleton"],
        }

        worker_result = _parse_last_json_line(
            _run(
                [
                    *compose,
                    "exec",
                    "-T",
                    "worker",
                    "python",
                    "-c",
                    (
                        "import json, os; "
                        "print(json.dumps({'provider_key_configured': "
                        "bool(os.environ.get('OPENROUTER_API_KEY'))}))"
                    ),
                ],
                secrets=secrets,
            ).stdout
        )
        assert worker_result == {"provider_key_configured": False}
    finally:
        subprocess.run(
            [*compose, "down", "--volumes", "--remove-orphans"],
            cwd=REPOSITORY_ROOT,
            env=os.environ.copy(),
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
