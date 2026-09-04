from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ai_cto_cockpit.main import create_app
from ai_cto_cockpit.persistence.models import (
    Decision,
    DecisionRevision,
    GuestSession,
    IdempotencyRecord,
)
from ai_cto_cockpit.security.guest_session import GuestSessionCodec
from ai_cto_cockpit.settings import AppMode, Settings

from ..support.asgi import AsgiResponse, asgi_request

NOW = datetime(2026, 8, 15, 9, 30, 0, 123456, tzinfo=UTC)
SIGNING_KEY = "t013-session-signing-key-with-more-than-thirty-two-bytes"
SEED_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000001")
LOCAL_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000002")
MISSING_DECISION_ID = "0198b0f0-0000-7000-8000-00000000d013"
LOWERCASE_SHA256 = re.compile(r"^[0-9a-f]{64}$")

type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]


def _settings(database_url: str, *, mode: AppMode = "public-demo") -> Settings:
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
    name, value = set_cookie.split(";", 1)[0].split("=", 1)
    assert name == "ai_cto_guest"
    return value


def _criterion(
    criterion_id: str,
    entered_weight: object,
    *,
    label: str | None = None,
) -> JsonObject:
    return {
        "id": criterion_id,
        "label": label or criterion_id.replace("-", " ").title(),
        "enteredWeight": entered_weight,
    }


def _all_constraints() -> list[JsonObject]:
    return [
        {
            "id": "budget-cap",
            "kind": "budget",
            "label": "Budget cap",
            "severity": "hard",
            "currency": "GBP",
            "maximum": 125000.5,
        },
        {
            "id": "delivery-date",
            "kind": "deadline",
            "label": "Delivery date",
            "severity": "hard",
            "date": "2026-12-31",
        },
        {
            "id": "audit-export",
            "kind": "capability",
            "label": "Audit export",
            "severity": "advisory",
            "capability": "audit-export",
        },
        {
            "id": "blocked-vendor",
            "kind": "forbidden-vendor",
            "label": "Blocked vendor",
            "severity": "hard",
            "vendor": "Example Vendor",
        },
        {
            "id": "approved-licenses",
            "kind": "license",
            "label": "Approved licenses",
            "severity": "hard",
            "allowedSpdx": ["Apache-2.0", "MIT"],
        },
        {
            "id": "data-residency",
            "kind": "residency",
            "label": "Data residency",
            "severity": "hard",
            "allowedCountries": ["GB", "DE"],
        },
        {
            "id": "deployment-targets",
            "kind": "deployment-mode",
            "label": "Deployment targets",
            "severity": "advisory",
            "allowedModes": ["managed", "self-hosted", "on-device"],
        },
    ]


def _frame(
    *,
    question: str = "Which architecture should we choose?",
    context: str = "A bounded architecture decision.",
    options: list[JsonObject] | None = None,
    criteria: list[JsonObject] | None = None,
    constraints: list[JsonObject] | None = None,
) -> JsonObject:
    return {
        "schemaVersion": "1.0",
        "question": question,
        "context": context,
        "options": options
        or [
            {
                "id": "managed-platform",
                "label": "Managed platform",
                "description": "Prefer managed operations.",
            },
            {
                "id": "self-hosted",
                "label": "Self hosted",
                "description": "Retain operational control.",
            },
        ],
        "criteria": criteria
        or [
            _criterion("cost", "1.00"),
            _criterion("operability", "2.0000"),
        ],
        "constraints": constraints or [],
    }


def _maximum_frame() -> JsonObject:
    return _frame(
        question="q" * 500,
        context="c" * 10000,
        options=[
            {
                "id": f"option-{index}",
                "label": f"Option {index}",
                "description": "d" * 1000,
            }
            for index in range(1, 9)
        ],
        criteria=[
            _criterion(f"criterion-{index}", "1", label="l" * 120)
            for index in range(1, 11)
        ],
        constraints=[
            {
                "id": f"constraint-{index}",
                "kind": "capability",
                "label": f"Capability {index}",
                "severity": "advisory",
                "capability": f"capability-{index}",
            }
            for index in range(1, 21)
        ],
    )


def _object_list(frame: JsonObject, key: str) -> list[JsonObject]:
    value = frame[key]
    assert isinstance(value, list)
    return cast(list[JsonObject], value)


def _json_body(payload: JsonObject) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


async def _json_request(
    app: FastAPI,
    *,
    method: str,
    path: str,
    payload: JsonObject,
    cookie: str | None,
    idempotency_key: str | None = None,
    if_match: int | str | None = None,
) -> AsgiResponse:
    headers: list[tuple[str, str]] = [("Content-Type", "application/json")]
    if cookie is not None:
        headers.append(("Cookie", f"ai_cto_guest={cookie}"))
    if idempotency_key is not None:
        headers.append(("Idempotency-Key", idempotency_key))
    if if_match is not None:
        headers.append(("If-Match", str(if_match)))
    return await asgi_request(
        app,
        method=method,
        path=path,
        headers=headers,
        body=_json_body(payload),
    )


async def _get_decision(
    app: FastAPI,
    decision_id: str,
    *,
    cookie: str | None,
) -> AsgiResponse:
    headers = () if cookie is None else (("Cookie", f"ai_cto_guest={cookie}"),)
    return await asgi_request(
        app,
        method="GET",
        path=f"/api/v1/decisions/{decision_id}",
        headers=headers,
    )


async def _new_guest(
    app: FastAPI,
    factory: SessionFactory,
) -> tuple[str, uuid.UUID]:
    response = await asgi_request(app, method="GET", path="/api/v1/config")
    assert response.status == 200
    set_cookie = response.header("set-cookie")
    assert set_cookie is not None
    cookie = _cookie_value(set_cookie)
    codec = cast(GuestSessionCodec, app.state.guest_session_codec)
    claims = codec.verify(cookie, now=NOW)
    async with factory() as session:
        guest_session = await session.get(GuestSession, claims.session_id)
        assert guest_session is not None
        workspace_id = guest_session.workspace_id
    return cookie, workspace_id


async def _public_app_and_guest(
    database_url: str,
    factory: SessionFactory,
) -> tuple[FastAPI, str, uuid.UUID]:
    app = create_app(
        settings=_settings(database_url),
        session_factory=factory,
        clock=lambda: NOW,
    )
    cookie, workspace_id = await _new_guest(app, factory)
    return app, cookie, workspace_id


def _uuid7(value: object) -> uuid.UUID:
    assert isinstance(value, str)
    parsed = uuid.UUID(value)
    assert parsed.version == 7
    assert str(parsed) == value
    return parsed


def _parse_timestamp(value: object) -> datetime:
    assert isinstance(value, str)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    return parsed


def _assert_api_error(
    response: AsgiResponse,
    *,
    status: int,
    code: str,
    message: str | None = None,
) -> JsonObject:
    assert response.status == status
    payload = response.json()
    assert set(payload) == {"code", "message", "correlationId", "fields"}
    assert payload["code"] == code
    if message is None:
        assert isinstance(payload["message"], str)
        assert 1 <= len(payload["message"]) <= 240
    else:
        assert payload["message"] == message
    _uuid7(payload["correlationId"])
    assert isinstance(payload["fields"], list)
    return payload


def _assert_validation_error(
    response: AsgiResponse,
    *,
    path_suffix: str | None = None,
) -> None:
    payload = _assert_api_error(
        response,
        status=422,
        code="request_validation_failed",
        message="Request validation failed.",
    )
    fields = cast(list[JsonObject], payload["fields"])
    assert fields
    if path_suffix is not None:
        assert any(
            isinstance(field.get("path"), str)
            and cast(str, field["path"]).endswith(path_suffix)
            for field in fields
        )


def _assert_not_found(response: AsgiResponse) -> JsonObject:
    payload = _assert_api_error(
        response,
        status=404,
        code="resource_not_found",
        message="The requested resource was not found.",
    )
    assert payload["fields"] == []
    return payload


async def _decision_counts(factory: SessionFactory) -> tuple[int, int, int]:
    async with factory() as session:
        decisions = await session.scalar(select(func.count(Decision.id)))
        revisions = await session.scalar(select(func.count(DecisionRevision.id)))
        idempotency = await session.scalar(select(func.count(IdempotencyRecord.id)))
    return int(decisions or 0), int(revisions or 0), int(idempotency or 0)


def _criteria_by_id(frame_view: JsonObject) -> dict[str, JsonObject]:
    criteria = frame_view["criteria"]
    assert isinstance(criteria, list)
    typed = cast(list[JsonObject], criteria)
    return {cast(str, item["id"]): item for item in typed}


@pytest.mark.asyncio
async def test_create_get_and_revise_persist_scoped_immutable_revisions(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, workspace_id = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    original = _frame(
        criteria=[
            _criterion("alpha", "1.0000"),
            _criterion("beta", "2.00000000"),
            _criterion("gamma", "3.0"),
        ],
        constraints=_all_constraints(),
    )

    created = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=original,
        cookie=cookie,
        idempotency_key="create-decision-013",
    )

    assert created.status == 201
    created_payload = created.json()
    decision_id = _uuid7(created_payload["id"])
    assert created_payload["currentRevision"] == 1
    assert "workspaceId" not in created.body.decode("utf-8")
    created_frame = cast(JsonObject, created_payload["frame"])
    assert created_frame["constraints"] == original["constraints"]
    created_criteria = _criteria_by_id(created_frame)
    assert {
        criterion_id: criterion["enteredWeight"]
        for criterion_id, criterion in created_criteria.items()
    } == {"alpha": "1.0000", "beta": "2.00000000", "gamma": "3.0"}
    assert {
        criterion_id: criterion["normalizedWeight"]
        for criterion_id, criterion in created_criteria.items()
    } == {"alpha": "16.6667", "beta": "33.3333", "gamma": "50.0000"}
    assert sum(
        Decimal(cast(str, criterion["normalizedWeight"]))
        for criterion in created_criteria.values()
    ) == Decimal("100.0000")

    fetched_revision_one = await _get_decision(
        app,
        str(decision_id),
        cookie=cookie,
    )
    assert fetched_revision_one.status == 200
    assert fetched_revision_one.json() == created_payload

    revised_input = _frame(
        question="Which architecture should we standardize on?",
        context="The reviewed context for revision two.",
        criteria=[
            _criterion("gamma", "1"),
            _criterion("alpha", "1"),
            _criterion("beta", "1"),
        ],
        constraints=_all_constraints(),
    )
    revised = await _json_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/revisions",
        payload=revised_input,
        cookie=cookie,
        idempotency_key="revise-decision-013",
        if_match=1,
    )

    assert revised.status == 201
    revised_payload = revised.json()
    assert revised_payload["id"] == str(decision_id)
    assert revised_payload["currentRevision"] == 2
    revised_frame = cast(JsonObject, revised_payload["frame"])
    assert revised_frame["question"] == revised_input["question"]
    assert {
        item_id: item["normalizedWeight"]
        for item_id, item in _criteria_by_id(revised_frame).items()
    } == {"alpha": "33.3334", "beta": "33.3333", "gamma": "33.3333"}

    fetched_revision_two = await _get_decision(
        app,
        str(decision_id),
        cookie=cookie,
    )
    assert fetched_revision_two.status == 200
    assert fetched_revision_two.json() == revised_payload

    async with t010_session_factory() as session:
        decision = await session.scalar(
            select(Decision).where(
                Decision.id == decision_id,
                Decision.workspace_id == workspace_id,
            )
        )
        revisions = list(
            (
                await session.scalars(
                    select(DecisionRevision)
                    .where(
                        DecisionRevision.decision_id == decision_id,
                        DecisionRevision.workspace_id == workspace_id,
                    )
                    .order_by(DecisionRevision.revision)
                )
            ).all()
        )
        assert decision is not None
        assert decision.current_revision == 2
        assert len(revisions) == 2
        first, second = revisions
        assert first.id != second.id
        assert [first.revision, second.revision] == [1, 2]
        assert first.question == original["question"]
        assert first.context == original["context"]
        assert first.options == original["options"]
        assert first.criteria == created_frame["criteria"]
        assert first.constraints == original["constraints"]
        assert second.question == revised_input["question"]
        assert second.criteria == revised_frame["criteria"]
        assert all(LOWERCASE_SHA256.fullmatch(item.snapshot_hash) for item in revisions)
        assert _parse_timestamp(created_payload["createdAt"]) == decision.created_at
        assert _parse_timestamp(revised_payload["updatedAt"]) == decision.updated_at


@pytest.mark.asyncio
async def test_equal_fraction_remainder_uses_ascending_criterion_id(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    frame = _frame(
        criteria=[
            _criterion("gamma", "1"),
            _criterion("beta", "1"),
            _criterion("alpha", "1"),
        ]
    )

    response = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=frame,
        cookie=cookie,
        idempotency_key="equal-weight-tie-013",
    )

    assert response.status == 201
    response_frame = cast(JsonObject, response.json()["frame"])
    criteria = _criteria_by_id(response_frame)
    assert {
        item_id: item["normalizedWeight"] for item_id, item in criteria.items()
    } == {"alpha": "33.3334", "beta": "33.3333", "gamma": "33.3333"}


@pytest.mark.asyncio
async def test_accepts_exact_weight_lexical_boundaries(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, workspace_id = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    frame = _frame(
        criteria=[
            _criterion("minimum", "0.00000001"),
            _criterion("maximum", "9999999999.99999999"),
        ]
    )

    response = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=frame,
        cookie=cookie,
        idempotency_key="weight-boundaries-013",
    )

    assert response.status == 201
    response_frame = cast(JsonObject, response.json()["frame"])
    criteria = _criteria_by_id(response_frame)
    assert criteria["minimum"]["enteredWeight"] == "0.00000001"
    assert criteria["maximum"]["enteredWeight"] == "9999999999.99999999"
    assert criteria["minimum"]["normalizedWeight"] == "0.0000"
    assert criteria["maximum"]["normalizedWeight"] == "100.0000"
    async with t010_session_factory() as session:
        stored = await session.scalar(
            select(DecisionRevision).where(
                DecisionRevision.workspace_id == workspace_id
            )
        )
        assert stored is not None
        assert stored.criteria == response_frame["criteria"]


@pytest.mark.parametrize(
    "invalid_weight",
    [
        "0",
        "0.0",
        "0.00000000",
        "+1",
        "-1",
        "1e2",
        "1E2",
        "01",
        "00.1",
        "10000000000",
        "10000000000.0",
        "0.123456789",
        1,
        0.5,
        True,
        None,
    ],
    ids=[
        "integer-zero",
        "decimal-zero",
        "eight-place-zero",
        "positive-sign",
        "negative-sign",
        "lowercase-exponent",
        "uppercase-exponent",
        "leading-zero-integer",
        "leading-zero-decimal",
        "eleven-integer-digits",
        "eleven-digits-with-fraction",
        "nine-fractional-digits",
        "integer-json",
        "float-json",
        "boolean-json",
        "null-json",
    ],
)
@pytest.mark.asyncio
async def test_rejects_invalid_weight_before_persistence(
    invalid_weight: object,
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    frame = _frame(criteria=[_criterion("invalid", invalid_weight)])

    response = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=frame,
        cookie=cookie,
        idempotency_key="invalid-weight-013",
    )

    _assert_validation_error(
        response,
        path_suffix="criteria[0].enteredWeight",
    )
    assert await _decision_counts(t010_session_factory) == (0, 0, 0)


def _invalid_limit_frame(case: str) -> JsonObject:
    frame = _frame()
    if case == "empty-question":
        frame["question"] = ""
    elif case == "blank-question":
        frame["question"] = " \t "
    elif case == "question-too-long":
        frame["question"] = "q" * 501
    elif case == "context-too-long":
        frame["context"] = "c" * 10001
    elif case == "too-few-options":
        frame["options"] = _object_list(frame, "options")[:1]
    elif case == "too-many-options":
        frame["options"] = [
            {
                "id": f"option-{index}",
                "label": f"Option {index}",
                "description": "",
            }
            for index in range(1, 10)
        ]
    elif case == "no-criteria":
        frame["criteria"] = []
    elif case == "too-many-criteria":
        frame["criteria"] = [
            _criterion(f"criterion-{index}", "1") for index in range(1, 12)
        ]
    elif case == "too-many-constraints":
        frame["constraints"] = [
            {
                "id": f"constraint-{index}",
                "kind": "capability",
                "label": f"Constraint {index}",
                "severity": "hard",
                "capability": f"capability-{index}",
            }
            for index in range(1, 22)
        ]
    elif case == "option-label-too-long":
        _object_list(frame, "options")[0]["label"] = "l" * 121
    elif case == "option-description-too-long":
        _object_list(frame, "options")[0]["description"] = "d" * 1001
    elif case == "criterion-label-too-long":
        _object_list(frame, "criteria")[0]["label"] = "l" * 121
    elif case == "invalid-schema-version":
        frame["schemaVersion"] = "2.0"
    elif case == "unknown-frame-property":
        frame["workspaceId"] = str(SEED_ID)
    elif case == "unknown-option-property":
        _object_list(frame, "options")[0]["score"] = 100
    elif case == "normalized-weight-in-input":
        _object_list(frame, "criteria")[0]["normalizedWeight"] = "50.0000"
    else:  # pragma: no cover - parametrization is a closed list
        raise AssertionError(f"Unknown invalid limit case: {case}")
    return frame


@pytest.mark.parametrize(
    "case",
    [
        "empty-question",
        "blank-question",
        "question-too-long",
        "context-too-long",
        "too-few-options",
        "too-many-options",
        "no-criteria",
        "too-many-criteria",
        "too-many-constraints",
        "option-label-too-long",
        "option-description-too-long",
        "criterion-label-too-long",
        "invalid-schema-version",
        "unknown-frame-property",
        "unknown-option-property",
        "normalized-weight-in-input",
    ],
)
@pytest.mark.asyncio
async def test_rejects_decision_frame_limit_or_closed_contract_violation(
    case: str,
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )

    response = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=_invalid_limit_frame(case),
        cookie=cookie,
        idempotency_key=f"limit-{case}-013",
    )

    _assert_validation_error(response)
    assert await _decision_counts(t010_session_factory) == (0, 0, 0)


@pytest.mark.asyncio
async def test_accepts_every_declared_frame_maximum(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    maximum = _maximum_frame()

    response = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=maximum,
        cookie=cookie,
        idempotency_key="maximum-frame-013",
    )

    assert response.status == 201
    response_frame = cast(JsonObject, response.json()["frame"])
    assert response_frame["question"] == maximum["question"]
    assert response_frame["context"] == maximum["context"]
    assert len(cast(list[object], response_frame["options"])) == 8
    assert len(cast(list[object], response_frame["criteria"])) == 10
    assert len(cast(list[object], response_frame["constraints"])) == 20


def _invalid_slug_or_uniqueness_frame(case: str) -> JsonObject:
    frame = _frame(constraints=_all_constraints()[:2])
    if case == "uppercase-option":
        _object_list(frame, "options")[0]["id"] = "Invalid"
    elif case == "underscore-criterion":
        _object_list(frame, "criteria")[0]["id"] = "not_valid"
    elif case == "leading-hyphen-constraint":
        _object_list(frame, "constraints")[0]["id"] = "-invalid"
    elif case == "slug-too-long":
        _object_list(frame, "options")[0]["id"] = "a" * 65
    elif case == "duplicate-option":
        _object_list(frame, "options")[1]["id"] = cast(
            str, _object_list(frame, "options")[0]["id"]
        )
    elif case == "duplicate-criterion":
        _object_list(frame, "criteria")[1]["id"] = cast(
            str, _object_list(frame, "criteria")[0]["id"]
        )
    elif case == "duplicate-constraint":
        _object_list(frame, "constraints")[1]["id"] = cast(
            str, _object_list(frame, "constraints")[0]["id"]
        )
    else:  # pragma: no cover - parametrization is a closed list
        raise AssertionError(f"Unknown slug case: {case}")
    return frame


@pytest.mark.parametrize(
    "case",
    [
        "uppercase-option",
        "underscore-criterion",
        "leading-hyphen-constraint",
        "slug-too-long",
        "duplicate-option",
        "duplicate-criterion",
        "duplicate-constraint",
    ],
)
@pytest.mark.asyncio
async def test_rejects_invalid_or_duplicate_collection_slugs(
    case: str,
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )

    response = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=_invalid_slug_or_uniqueness_frame(case),
        cookie=cookie,
        idempotency_key=f"slug-{case}-013",
    )

    _assert_validation_error(response)
    assert await _decision_counts(t010_session_factory) == (0, 0, 0)


def _invalid_constraint(case: str) -> JsonObject:
    constraints = _all_constraints()
    by_kind = {cast(str, item["kind"]): item for item in constraints}
    if case == "budget-currency":
        by_kind["budget"]["currency"] = "gbp"
    elif case == "budget-negative":
        by_kind["budget"]["maximum"] = -0.01
    elif case == "deadline-date":
        by_kind["deadline"]["date"] = "2026-02-30"
    elif case == "capability-slug":
        by_kind["capability"]["capability"] = "Not Valid"
    elif case == "empty-vendor":
        by_kind["forbidden-vendor"]["vendor"] = ""
    elif case == "empty-license-list":
        by_kind["license"]["allowedSpdx"] = []
    elif case == "duplicate-license":
        by_kind["license"]["allowedSpdx"] = ["MIT", "MIT"]
    elif case == "invalid-country":
        by_kind["residency"]["allowedCountries"] = ["gb"]
    elif case == "duplicate-country":
        by_kind["residency"]["allowedCountries"] = ["GB", "GB"]
    elif case == "invalid-deployment-mode":
        by_kind["deployment-mode"]["allowedModes"] = ["bare-metal"]
    elif case == "duplicate-deployment-mode":
        by_kind["deployment-mode"]["allowedModes"] = ["managed", "managed"]
    elif case == "invalid-severity":
        by_kind["budget"]["severity"] = "blocking"
    elif case == "unknown-kind":
        by_kind["budget"]["kind"] = "unknown"
    elif case == "unknown-variant-property":
        by_kind["budget"]["workspaceId"] = str(SEED_ID)
    else:  # pragma: no cover - parametrization is a closed list
        raise AssertionError(f"Unknown constraint case: {case}")
    return _frame(constraints=constraints)


@pytest.mark.parametrize(
    "case",
    [
        "budget-currency",
        "budget-negative",
        "deadline-date",
        "capability-slug",
        "empty-vendor",
        "empty-license-list",
        "duplicate-license",
        "invalid-country",
        "duplicate-country",
        "invalid-deployment-mode",
        "duplicate-deployment-mode",
        "invalid-severity",
        "unknown-kind",
        "unknown-variant-property",
    ],
)
@pytest.mark.asyncio
async def test_rejects_invalid_typed_constraint(
    case: str,
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )

    response = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=_invalid_constraint(case),
        cookie=cookie,
        idempotency_key=f"constraint-{case}-013",
    )

    _assert_validation_error(response)
    assert await _decision_counts(t010_session_factory) == (0, 0, 0)


@pytest.mark.asyncio
async def test_mutations_require_idempotency_and_expected_revision_headers(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    frame = _frame()
    missing_create_key = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=frame,
        cookie=cookie,
    )
    _assert_validation_error(
        missing_create_key,
        path_suffix="header.Idempotency-Key",
    )
    assert await _decision_counts(t010_session_factory) == (0, 0, 0)

    created = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=frame,
        cookie=cookie,
        idempotency_key="header-create-013",
    )
    assert created.status == 201
    decision_id = cast(str, created.json()["id"])

    missing_revision_key = await _json_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/revisions",
        payload=frame,
        cookie=cookie,
        if_match=1,
    )
    _assert_validation_error(
        missing_revision_key,
        path_suffix="header.Idempotency-Key",
    )
    missing_if_match = await _json_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/revisions",
        payload=frame,
        cookie=cookie,
        idempotency_key="missing-if-match-013",
    )
    _assert_validation_error(missing_if_match, path_suffix="header.If-Match")
    for invalid_if_match in (0, "not-an-integer"):
        response = await _json_request(
            app,
            method="POST",
            path=f"/api/v1/decisions/{decision_id}/revisions",
            payload=frame,
            cookie=cookie,
            idempotency_key=f"invalid-if-match-{invalid_if_match}-013",
            if_match=invalid_if_match,
        )
        _assert_validation_error(response, path_suffix="header.If-Match")
    assert await _decision_counts(t010_session_factory) == (1, 1, 1)


@pytest.mark.asyncio
async def test_identical_create_and_revision_replays_return_original_results(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    frame = _frame()
    create_key = "replay-create-013"
    first_create = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=frame,
        cookie=cookie,
        idempotency_key=create_key,
    )
    replayed_create = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=frame,
        cookie=cookie,
        idempotency_key=create_key,
    )
    assert first_create.status == replayed_create.status == 201
    assert first_create.body == replayed_create.body
    decision_id = cast(str, first_create.json()["id"])

    revised_frame = _frame(question="Revised question?")
    revision_key = "replay-revision-013"
    first_revision = await _json_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/revisions",
        payload=revised_frame,
        cookie=cookie,
        idempotency_key=revision_key,
        if_match=1,
    )
    replayed_revision = await _json_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/revisions",
        payload=revised_frame,
        cookie=cookie,
        idempotency_key=revision_key,
        if_match=1,
    )
    assert first_revision.status == replayed_revision.status == 201
    assert first_revision.body == replayed_revision.body
    assert await _decision_counts(t010_session_factory) == (1, 2, 2)


@pytest.mark.asyncio
async def test_conflicting_idempotency_key_reuse_is_409_without_mutation(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, workspace_id = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    key = "conflicting-create-013"
    accepted = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=_frame(),
        cookie=cookie,
        idempotency_key=key,
    )
    assert accepted.status == 201
    changed = _frame(question="A different normalized request?")

    conflict = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=changed,
        cookie=cookie,
        idempotency_key=key,
    )

    payload = _assert_api_error(
        conflict,
        status=409,
        code="idempotency_conflict",
    )
    assert payload["fields"] == []
    assert await _decision_counts(t010_session_factory) == (1, 1, 1)
    async with t010_session_factory() as session:
        record = await session.scalar(select(IdempotencyRecord))
        guest = await session.scalar(
            select(GuestSession).where(GuestSession.workspace_id == workspace_id)
        )
        assert record is not None and guest is not None
        assert record.workspace_id == workspace_id
        assert record.key == key
        assert LOWERCASE_SHA256.fullmatch(record.request_hash)
        assert record.response_status == 201
        assert record.response_body == accepted.json()
        assert record.resource_id == uuid.UUID(cast(str, accepted.json()["id"]))
        assert record.expires_at >= guest.expires_at


@pytest.mark.asyncio
async def test_stale_if_match_is_409_and_current_revision_is_recoverable(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app, cookie, _ = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    created = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=_frame(),
        cookie=cookie,
        idempotency_key="stale-create-013",
    )
    assert created.status == 201
    decision_id = cast(str, created.json()["id"])
    accepted_revision = await _json_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/revisions",
        payload=_frame(question="Accepted revision?"),
        cookie=cookie,
        idempotency_key="stale-accepted-013",
        if_match=1,
    )
    assert accepted_revision.status == 201

    stale = await _json_request(
        app,
        method="POST",
        path=f"/api/v1/decisions/{decision_id}/revisions",
        payload=_frame(question="Stale revision?"),
        cookie=cookie,
        idempotency_key="stale-rejected-013",
        if_match=1,
    )

    payload = _assert_api_error(
        stale,
        status=409,
        code="revision_conflict",
    )
    assert payload["fields"] == []
    current = await _get_decision(app, decision_id, cookie=cookie)
    assert current.status == 200
    assert current.json()["currentRevision"] == 2
    assert await _decision_counts(t010_session_factory) == (1, 2, 2)


@pytest.mark.asyncio
async def test_missing_and_cross_workspace_resources_share_uniform_404(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app = create_app(
        settings=_settings(t010_postgres_url),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    cookie_a, workspace_a = await _new_guest(app, t010_session_factory)
    cookie_b, workspace_b = await _new_guest(app, t010_session_factory)
    assert workspace_a != workspace_b
    created = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=_frame(),
        cookie=cookie_a,
        idempotency_key="isolation-create-013",
    )
    assert created.status == 201
    decision_id = cast(str, created.json()["id"])

    responses = [
        await _get_decision(app, decision_id, cookie=cookie_b),
        await _get_decision(app, MISSING_DECISION_ID, cookie=cookie_b),
        await _json_request(
            app,
            method="POST",
            path=f"/api/v1/decisions/{decision_id}/revisions",
            payload=_frame(question="Cross-workspace mutation?"),
            cookie=cookie_b,
            idempotency_key="isolation-existing-013",
            if_match=1,
        ),
        await _json_request(
            app,
            method="POST",
            path=f"/api/v1/decisions/{MISSING_DECISION_ID}/revisions",
            payload=_frame(question="Missing mutation?"),
            cookie=cookie_b,
            idempotency_key="isolation-missing-013",
            if_match=1,
        ),
    ]
    normalized: list[JsonObject] = []
    for response in responses:
        payload = _assert_not_found(response)
        normalized.append(
            {key: value for key, value in payload.items() if key != "correlationId"}
        )
    assert normalized == [normalized[0]] * len(normalized)
    assert (await _get_decision(app, decision_id, cookie=cookie_a)).status == 200
    assert await _decision_counts(t010_session_factory) == (1, 1, 1)


@pytest.mark.asyncio
async def test_local_data_decision_scope_is_server_derived_without_cookie(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
) -> None:
    app = create_app(
        settings=_settings(t010_postgres_url, mode="local-data"),
        session_factory=t010_session_factory,
        clock=lambda: NOW,
    )
    config = await asgi_request(app, method="GET", path="/api/v1/config")
    assert config.status == 200
    assert config.header("set-cookie") is None

    created = await _json_request(
        app,
        method="POST",
        path="/api/v1/decisions",
        payload=_frame(),
        cookie=None,
        idempotency_key="local-decision-013",
    )

    assert created.status == 201
    decision_id = uuid.UUID(cast(str, created.json()["id"]))
    async with t010_session_factory() as session:
        decision = await session.get(Decision, decision_id)
        assert decision is not None
        assert decision.workspace_id == LOCAL_ID
