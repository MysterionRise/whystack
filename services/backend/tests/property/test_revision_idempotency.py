from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_UP, Context, localcontext
from typing import Literal, cast

import pytest
from fastapi import FastAPI
from hypothesis import (
    HealthCheck,
    Phase,
    example,
    given,
)
from hypothesis import (
    settings as hypothesis_settings,
)
from hypothesis import (
    strategies as st,
)
from hypothesis.strategies import DrawFn
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
from ai_cto_cockpit.settings import Settings
from tests.support.asgi import AsgiResponse, asgi_request

NOW = datetime(2026, 8, 16, 10, 0, 0, 123456, tzinfo=UTC)
SIGNING_KEY = "t014-session-signing-key-with-more-than-thirty-two-bytes"
SEED_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000001")
LOCAL_ID = uuid.UUID("0198b0f0-0000-7000-8000-000000000002")
NORMALIZED_UNITS = 1_000_000
HIGH_PRECISION_WEIGHT = "90071992.54740993"

type JsonObject = dict[str, object]
type SessionFactory = async_sessionmaker[AsyncSession]
type SequenceAction = Literal[
    "fresh",
    "replay",
    "body-mismatch",
    "if-match-mismatch",
    "stale",
]
type ConcurrencyScenario = Literal[
    "identical-key-identical-request",
    "identical-key-distinct-request",
    "distinct-key-identical-revision",
]
type WeightEntry = tuple[str, str]
type WeightCase = tuple[tuple[WeightEntry, ...], tuple[WeightEntry, ...]]


@dataclass(frozen=True, slots=True)
class AcceptedRevisionRequest:
    key: str
    frame: JsonObject
    expected_revision: int
    response: AsgiResponse


@dataclass(frozen=True, slots=True)
class StoredRevision:
    id: uuid.UUID
    revision: int
    schema_version: str
    question: str
    context: str
    options: str
    criteria: str
    constraints: str
    snapshot_hash: str
    created_at: datetime


def _settings(database_url: str) -> Settings:
    return Settings(
        app_mode="public-demo",
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


def _criterion(criterion_id: str, entered_weight: str) -> JsonObject:
    return {
        "id": criterion_id,
        "label": f"Criterion {criterion_id}",
        "enteredWeight": entered_weight,
    }


def _frame(
    *,
    question: str,
    criteria: tuple[WeightEntry, ...] = (("cost", "1.0000"),),
) -> JsonObject:
    return {
        "schemaVersion": "1.0",
        "question": question,
        "context": "Generated T014 decision property context.",
        "options": [
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
        "criteria": [
            _criterion(criterion_id, entered_weight)
            for criterion_id, entered_weight in criteria
        ],
        "constraints": [],
    }


def _json_body(payload: JsonObject, *, semantic_variant: bool = False) -> bytes:
    if semantic_variant:
        reversed_fields = dict(reversed(tuple(payload.items())))
        return json.dumps(
            reversed_fields,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


async def _json_request(
    app: FastAPI,
    *,
    path: str,
    payload: JsonObject,
    cookie: str,
    idempotency_key: str,
    expected_revision: int | None = None,
    semantic_variant: bool = False,
) -> AsgiResponse:
    headers = [
        ("Content-Type", "application/json"),
        ("Cookie", f"ai_cto_guest={cookie}"),
        ("Idempotency-Key", idempotency_key),
    ]
    if expected_revision is not None:
        headers.append(("If-Match", str(expected_revision)))
    return await asgi_request(
        app,
        method="POST",
        path=path,
        headers=headers,
        body=_json_body(payload, semantic_variant=semantic_variant),
    )


async def _create_decision(
    app: FastAPI,
    *,
    cookie: str,
    key: str,
    frame: JsonObject,
    semantic_variant: bool = False,
) -> AsgiResponse:
    return await _json_request(
        app,
        path="/api/v1/decisions",
        payload=frame,
        cookie=cookie,
        idempotency_key=key,
        semantic_variant=semantic_variant,
    )


async def _revise_decision(
    app: FastAPI,
    decision_id: str,
    *,
    cookie: str,
    key: str,
    frame: JsonObject,
    expected_revision: int,
    semantic_variant: bool = False,
) -> AsgiResponse:
    return await _json_request(
        app,
        path=f"/api/v1/decisions/{decision_id}/revisions",
        payload=frame,
        cookie=cookie,
        idempotency_key=key,
        expected_revision=expected_revision,
        semantic_variant=semantic_variant,
    )


async def _public_app_and_guest(
    database_url: str,
    factory: SessionFactory,
) -> tuple[FastAPI, str, uuid.UUID]:
    app = create_app(
        settings=_settings(database_url),
        session_factory=factory,
        clock=lambda: NOW,
    )
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
    return app, cookie, workspace_id


def _decision_id(response: AsgiResponse) -> str:
    value = response.json().get("id")
    assert isinstance(value, str)
    parsed = uuid.UUID(value)
    assert parsed.version == 7
    return value


def _current_revision(response: AsgiResponse) -> int:
    value = response.json().get("currentRevision")
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _assert_error(response: AsgiResponse, *, code: str) -> None:
    assert response.status == 409
    payload = response.json()
    assert payload.get("code") == code
    assert set(payload) == {"code", "message", "correlationId", "fields"}


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


async def _revision_snapshot(
    factory: SessionFactory,
    *,
    workspace_id: uuid.UUID,
    decision_id: str,
) -> tuple[StoredRevision, ...]:
    async with factory() as session:
        revisions = list(
            (
                await session.scalars(
                    select(DecisionRevision)
                    .where(
                        DecisionRevision.workspace_id == workspace_id,
                        DecisionRevision.decision_id == uuid.UUID(decision_id),
                    )
                    .order_by(DecisionRevision.revision)
                )
            ).all()
        )
    return tuple(
        StoredRevision(
            id=revision.id,
            revision=revision.revision,
            schema_version=revision.frame_schema_version,
            question=revision.question,
            context=revision.context,
            options=_canonical_json(revision.options),
            criteria=_canonical_json(revision.criteria),
            constraints=_canonical_json(revision.constraints),
            snapshot_hash=revision.snapshot_hash,
            created_at=revision.created_at,
        )
        for revision in revisions
    )


async def _workspace_counts(
    factory: SessionFactory,
    workspace_id: uuid.UUID,
) -> tuple[int, int, int]:
    async with factory() as session:
        decisions = await session.scalar(
            select(func.count(Decision.id)).where(Decision.workspace_id == workspace_id)
        )
        revisions = await session.scalar(
            select(func.count(DecisionRevision.id)).where(
                DecisionRevision.workspace_id == workspace_id
            )
        )
        records = await session.scalar(
            select(func.count(IdempotencyRecord.id)).where(
                IdempotencyRecord.workspace_id == workspace_id
            )
        )
    return int(decisions or 0), int(revisions or 0), int(records or 0)


def _response_criteria(response: AsgiResponse) -> dict[str, tuple[str, str]]:
    raw_frame = response.json().get("frame")
    assert isinstance(raw_frame, dict)
    frame = cast(JsonObject, raw_frame)
    raw_criteria = frame.get("criteria")
    assert isinstance(raw_criteria, list)
    criteria = cast(list[object], raw_criteria)
    result: dict[str, tuple[str, str]] = {}
    for raw_item in criteria:
        assert isinstance(raw_item, dict)
        item = cast(JsonObject, raw_item)
        criterion_id = item.get("id")
        entered = item.get("enteredWeight")
        normalized = item.get("normalizedWeight")
        assert isinstance(criterion_id, str)
        assert isinstance(entered, str)
        assert isinstance(normalized, str)
        result[criterion_id] = (entered, normalized)
    return result


def _stored_criteria(criteria: list[dict[str, object]]) -> dict[str, tuple[str, str]]:
    result: dict[str, tuple[str, str]] = {}
    for item in criteria:
        criterion_id = item.get("id")
        entered = item.get("enteredWeight")
        normalized = item.get("normalizedWeight")
        assert isinstance(criterion_id, str)
        assert isinstance(entered, str)
        assert isinstance(normalized, str)
        result[criterion_id] = (entered, normalized)
    return result


def _fractional_scale(value: str) -> int:
    separator = value.find(".")
    return 0 if separator < 0 else len(value) - separator - 1


def _coefficient(value: str, common_scale: int) -> int:
    whole, separator, fraction = value.partition(".")
    lexical_scale = len(fraction) if separator else 0
    return int(whole) * 10**common_scale + int(fraction or "0") * 10 ** (
        common_scale - lexical_scale
    )


def _format_normalized(units: int) -> str:
    return f"{units // 10_000}.{units % 10_000:04d}"


def _normalized_units(value: str) -> int:
    whole, fraction = value.split(".", 1)
    assert len(fraction) == 4
    return int(whole) * 10_000 + int(fraction)


def _normalization_oracle(entries: tuple[WeightEntry, ...]) -> dict[str, str]:
    common_scale = max(_fractional_scale(value) for _, value in entries)
    coefficients = {
        criterion_id: _coefficient(value, common_scale)
        for criterion_id, value in entries
    }
    total = sum(coefficients.values())
    allocations: dict[str, int] = {}
    remainders: dict[str, int] = {}
    for criterion_id, coefficient in coefficients.items():
        allocations[criterion_id], remainders[criterion_id] = divmod(
            coefficient * NORMALIZED_UNITS,
            total,
        )
    unallocated = NORMALIZED_UNITS - sum(allocations.values())
    ranked = sorted(
        allocations,
        key=lambda criterion_id: (-remainders[criterion_id], criterion_id),
    )
    for criterion_id in ranked[:unallocated]:
        allocations[criterion_id] += 1
    assert sum(allocations.values()) == NORMALIZED_UNITS
    return {
        criterion_id: _format_normalized(units)
        for criterion_id, units in allocations.items()
    }


@st.composite
def _valid_weight(draw: DrawFn) -> str:
    scale = draw(st.integers(min_value=0, max_value=8))
    multiplier = 10**scale
    maximum = 9_999_999_999 * multiplier + multiplier - 1
    coefficient = draw(st.integers(min_value=1, max_value=maximum))
    if scale == 0:
        return str(coefficient)
    whole, fraction = divmod(coefficient, multiplier)
    return f"{whole}.{fraction:0{scale}d}"


@st.composite
def _weight_cases(draw: DrawFn) -> WeightCase:
    count = draw(st.integers(min_value=2, max_value=10))
    criterion_ids = draw(
        st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8),
            min_size=count,
            max_size=count,
            unique=True,
        )
    )
    weights = draw(st.lists(_valid_weight(), min_size=count, max_size=count))
    weights[draw(st.integers(min_value=0, max_value=count - 1))] = HIGH_PRECISION_WEIGHT
    entries = tuple(zip(criterion_ids, weights, strict=True))
    offset = draw(st.integers(min_value=1, max_value=count - 1))
    permutation = entries[offset:] + entries[:offset]
    return entries, permutation


def _equal_weight_case(count: int, offset: int) -> WeightCase:
    entries = tuple(
        (f"criterion-{chr(ord('a') + index)}", "1.00000000") for index in range(count)
    )
    permutation = entries[offset:] + entries[:offset]
    return entries, permutation


@st.composite
def _equal_weight_cases(draw: DrawFn) -> WeightCase:
    count = draw(st.sampled_from((3, 6, 7, 9)))
    offset = draw(st.integers(min_value=1, max_value=count - 1))
    return _equal_weight_case(count, offset)


_SEQUENCE_ACTIONS: tuple[SequenceAction, ...] = (
    "fresh",
    "replay",
    "body-mismatch",
    "if-match-mismatch",
    "stale",
)


@pytest.mark.asyncio
@hypothesis_settings(
    max_examples=10,
    deadline=None,
    derandomize=True,
    database=None,
    phases=(Phase.explicit, Phase.generate, Phase.shrink),
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@example(
    actions=[
        "fresh",
        "replay",
        "body-mismatch",
        "if-match-mismatch",
        "stale",
    ]
)
@given(
    actions=st.lists(
        st.sampled_from(_SEQUENCE_ACTIONS),
        min_size=1,
        max_size=8,
    )
)
async def test_sequential_revision_and_idempotency_sequences_are_atomic(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
    actions: list[SequenceAction],
) -> None:
    app, cookie, workspace_id = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    created = await _create_decision(
        app,
        cookie=cookie,
        key="sequence-create-014",
        frame=_frame(question="Initial sequential decision?"),
    )
    assert created.status == 201
    decision_id = _decision_id(created)

    seed_frame = _frame(question="Seed sequential revision?")
    seed = await _revise_decision(
        app,
        decision_id,
        cookie=cookie,
        key="sequence-seed-014",
        frame=seed_frame,
        expected_revision=1,
    )
    assert seed.status == 201
    current_revision = 2
    accepted = [
        AcceptedRevisionRequest(
            key="sequence-seed-014",
            frame=seed_frame,
            expected_revision=1,
            response=seed,
        )
    ]

    for index, action in enumerate(actions):
        before = await _revision_snapshot(
            t010_session_factory,
            workspace_id=workspace_id,
            decision_id=decision_id,
        )
        before_counts = await _workspace_counts(t010_session_factory, workspace_id)
        accepted_this_action = False

        if action == "fresh":
            frame = _frame(question=f"Accepted generated revision {index}?")
            key = f"sequence-fresh-{index:02d}-014"
            response = await _revise_decision(
                app,
                decision_id,
                cookie=cookie,
                key=key,
                frame=frame,
                expected_revision=current_revision,
            )
            assert response.status == 201
            current_revision += 1
            assert _current_revision(response) == current_revision
            accepted.append(
                AcceptedRevisionRequest(
                    key=key,
                    frame=frame,
                    expected_revision=current_revision - 1,
                    response=response,
                )
            )
            accepted_this_action = True
        else:
            anchor = accepted[index % len(accepted)]
            if action == "replay":
                response = await _revise_decision(
                    app,
                    decision_id,
                    cookie=cookie,
                    key=anchor.key,
                    frame=anchor.frame,
                    expected_revision=anchor.expected_revision,
                    semantic_variant=True,
                )
                assert response.status == anchor.response.status == 201
                assert response.body == anchor.response.body
            elif action == "body-mismatch":
                response = await _revise_decision(
                    app,
                    decision_id,
                    cookie=cookie,
                    key=anchor.key,
                    frame=_frame(question=f"Conflicting generated body {index}?"),
                    expected_revision=anchor.expected_revision,
                )
                _assert_error(response, code="idempotency_conflict")
            elif action == "if-match-mismatch":
                response = await _revise_decision(
                    app,
                    decision_id,
                    cookie=cookie,
                    key=anchor.key,
                    frame=anchor.frame,
                    expected_revision=anchor.expected_revision + 10_000,
                )
                _assert_error(response, code="idempotency_conflict")
            else:
                response = await _revise_decision(
                    app,
                    decision_id,
                    cookie=cookie,
                    key=f"sequence-stale-{index:02d}-014",
                    frame=_frame(question=f"Fresh-key stale revision {index}?"),
                    expected_revision=current_revision - 1,
                )
                _assert_error(response, code="revision_conflict")

        after = await _revision_snapshot(
            t010_session_factory,
            workspace_id=workspace_id,
            decision_id=decision_id,
        )
        after_counts = await _workspace_counts(t010_session_factory, workspace_id)
        if accepted_this_action:
            assert after[: len(before)] == before
            assert len(after) == len(before) + 1
            assert after_counts == (
                before_counts[0],
                before_counts[1] + 1,
                before_counts[2] + 1,
            )
        else:
            assert after == before
            assert after_counts == before_counts

    final = await _revision_snapshot(
        t010_session_factory,
        workspace_id=workspace_id,
        decision_id=decision_id,
    )
    assert [item.revision for item in final] == list(range(1, current_revision + 1))
    assert len({item.id for item in final}) == current_revision
    assert await _workspace_counts(t010_session_factory, workspace_id) == (
        1,
        current_revision,
        current_revision,
    )


async def _released_revision_requests(
    app: FastAPI,
    decision_id: str,
    *,
    cookie: str,
    expected_revision: int,
    requests: tuple[tuple[str, JsonObject], ...],
) -> tuple[AsgiResponse, ...]:
    release = asyncio.Event()

    async def issue(key: str, frame: JsonObject) -> AsgiResponse:
        await release.wait()
        return await _revise_decision(
            app,
            decision_id,
            cookie=cookie,
            key=key,
            frame=frame,
            expected_revision=expected_revision,
        )

    pending = [asyncio.create_task(issue(key, frame)) for key, frame in requests]
    await asyncio.sleep(0)
    release.set()
    try:
        async with asyncio.timeout(10):
            return tuple(await asyncio.gather(*pending))
    finally:
        for task in pending:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    (
        "identical-key-identical-request",
        "identical-key-distinct-request",
        "distinct-key-identical-revision",
    ),
)
@hypothesis_settings(
    max_examples=10,
    deadline=None,
    derandomize=True,
    database=None,
    phases=(Phase.generate, Phase.shrink),
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@given(
    fanout=st.integers(min_value=2, max_value=4),
    rounds=st.integers(min_value=1, max_value=3),
)
async def test_concurrent_revision_fanout_has_one_winner_per_round(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
    scenario: ConcurrencyScenario,
    fanout: int,
    rounds: int,
) -> None:
    app, cookie, workspace_id = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    created = await _create_decision(
        app,
        cookie=cookie,
        key="concurrent-create-014",
        frame=_frame(question="Initial concurrent decision?"),
    )
    assert created.status == 201
    decision_id = _decision_id(created)
    current_revision = 1

    for round_index in range(rounds):
        before = await _revision_snapshot(
            t010_session_factory,
            workspace_id=workspace_id,
            decision_id=decision_id,
        )
        if scenario == "identical-key-identical-request":
            common_frame = _frame(question=f"Concurrent identical round {round_index}?")
            requests = tuple(
                (f"concurrent-identical-{round_index}-014", common_frame)
                for _ in range(fanout)
            )
        elif scenario == "identical-key-distinct-request":
            requests = tuple(
                (
                    f"concurrent-conflict-{round_index}-014",
                    _frame(
                        question=(
                            f"Concurrent same-key round {round_index} "
                            f"candidate {index}?"
                        )
                    ),
                )
                for index in range(fanout)
            )
        else:
            requests = tuple(
                (
                    f"concurrent-stale-{round_index}-{index}-014",
                    _frame(
                        question=(
                            f"Concurrent distinct-key round {round_index} candidate "
                            f"{index}?"
                        )
                    ),
                )
                for index in range(fanout)
            )

        responses = await _released_revision_requests(
            app,
            decision_id,
            cookie=cookie,
            expected_revision=current_revision,
            requests=requests,
        )
        successes = [response for response in responses if response.status == 201]
        conflicts = [response for response in responses if response.status == 409]
        if scenario == "identical-key-identical-request":
            assert len(successes) == fanout
            assert not conflicts
            assert len({response.body for response in successes}) == 1
        else:
            assert len(successes) == 1
            assert len(conflicts) == fanout - 1
            expected_code = (
                "idempotency_conflict"
                if scenario == "identical-key-distinct-request"
                else "revision_conflict"
            )
            for conflict in conflicts:
                _assert_error(conflict, code=expected_code)

        winner = successes[0]
        current_revision += 1
        assert _current_revision(winner) == current_revision
        winning_question = cast(JsonObject, winner.json()["frame"])["question"]
        requested_questions = {cast(str, frame["question"]) for _, frame in requests}
        assert winning_question in requested_questions

        after = await _revision_snapshot(
            t010_session_factory,
            workspace_id=workspace_id,
            decision_id=decision_id,
        )
        assert after[: len(before)] == before
        assert len(after) == len(before) + 1
        assert [item.revision for item in after] == list(range(1, current_revision + 1))

    assert await _workspace_counts(t010_session_factory, workspace_id) == (
        1,
        current_revision,
        current_revision,
    )


@pytest.mark.asyncio
@hypothesis_settings(
    max_examples=12,
    deadline=None,
    derandomize=True,
    database=None,
    phases=(Phase.explicit, Phase.generate, Phase.shrink),
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@example(
    weight_case=(
        (
            ("maximum", "9999999999.99999999"),
            ("precision", HIGH_PRECISION_WEIGHT),
            ("minimum", "0.00000001"),
        ),
        (
            ("minimum", "0.00000001"),
            ("maximum", "9999999999.99999999"),
            ("precision", HIGH_PRECISION_WEIGHT),
        ),
    )
)
@given(weight_case=_weight_cases())
async def test_weight_normalization_is_exact_across_permutations_and_contexts(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
    weight_case: WeightCase,
) -> None:
    entries, permutation = weight_case
    expected = _normalization_oracle(entries)
    assert expected == _normalization_oracle(permutation)
    assert sum(_normalized_units(value) for value in expected.values()) == (
        NORMALIZED_UNITS
    )
    high_coefficient = _coefficient(HIGH_PRECISION_WEIGHT, 8)
    assert high_coefficient > 2**53
    assert format(float(HIGH_PRECISION_WEIGHT), ".8f") != HIGH_PRECISION_WEIGHT

    app, cookie, workspace_id = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    with localcontext(Context(prec=3, rounding=ROUND_DOWN)):
        original = await _create_decision(
            app,
            cookie=cookie,
            key="normalization-original-014",
            frame=_frame(question="Original normalization order?", criteria=entries),
        )
    assert original.status == 201

    with localcontext(Context(prec=50, rounding=ROUND_UP)):
        permuted = await _create_decision(
            app,
            cookie=cookie,
            key="normalization-permuted-014",
            frame=_frame(
                question="Permuted normalization order?",
                criteria=permutation,
            ),
        )
    assert permuted.status == 201

    submitted = dict(entries)
    for response in (original, permuted):
        criteria = _response_criteria(response)
        assert {item_id: value[0] for item_id, value in criteria.items()} == submitted
        assert {item_id: value[1] for item_id, value in criteria.items()} == expected
        assert sum(_normalized_units(value[1]) for value in criteria.values()) == (
            NORMALIZED_UNITS
        )

    async with t010_session_factory() as session:
        stored_revisions = list(
            (
                await session.scalars(
                    select(DecisionRevision)
                    .where(DecisionRevision.workspace_id == workspace_id)
                    .order_by(DecisionRevision.created_at, DecisionRevision.id)
                )
            ).all()
        )
    assert len(stored_revisions) == 2
    for stored_revision in stored_revisions:
        stored = _stored_criteria(stored_revision.criteria)
        assert {item_id: value[0] for item_id, value in stored.items()} == submitted
        assert {item_id: value[1] for item_id, value in stored.items()} == expected
    assert await _workspace_counts(t010_session_factory, workspace_id) == (2, 2, 2)


@pytest.mark.asyncio
@hypothesis_settings(
    max_examples=8,
    deadline=None,
    derandomize=True,
    database=None,
    phases=(Phase.explicit, Phase.generate, Phase.shrink),
    suppress_health_check=(HealthCheck.function_scoped_fixture,),
)
@example(weight_case=_equal_weight_case(3, 1))
@example(weight_case=_equal_weight_case(6, 2))
@example(weight_case=_equal_weight_case(7, 3))
@example(weight_case=_equal_weight_case(9, 4))
@given(weight_case=_equal_weight_cases())
async def test_equal_remainder_units_go_to_ascending_criterion_ids(
    t010_postgres_url: str,
    t010_session_factory: SessionFactory,
    weight_case: WeightCase,
) -> None:
    entries, permutation = weight_case
    expected = _normalization_oracle(entries)
    count = len(entries)
    base, remainder_count = divmod(NORMALIZED_UNITS, count)
    ordered_ids = sorted(criterion_id for criterion_id, _ in entries)
    expected_units = {
        criterion_id: base + (1 if index < remainder_count else 0)
        for index, criterion_id in enumerate(ordered_ids)
    }
    assert expected == {
        criterion_id: _format_normalized(units)
        for criterion_id, units in expected_units.items()
    }

    app, cookie, workspace_id = await _public_app_and_guest(
        t010_postgres_url,
        t010_session_factory,
    )
    response = await _create_decision(
        app,
        cookie=cookie,
        key="equal-remainder-tie-014",
        frame=_frame(
            question="Which criterion wins the remainder tie?", criteria=permutation
        ),
    )
    assert response.status == 201
    criteria = _response_criteria(response)
    assert {item_id: value[1] for item_id, value in criteria.items()} == expected

    async with t010_session_factory() as session:
        stored_revision = await session.scalar(
            select(DecisionRevision).where(
                DecisionRevision.workspace_id == workspace_id
            )
        )
    assert stored_revision is not None
    stored = _stored_criteria(stored_revision.criteria)
    assert {item_id: value[0] for item_id, value in stored.items()} == dict(entries)
    assert {item_id: value[1] for item_id, value in stored.items()} == expected
