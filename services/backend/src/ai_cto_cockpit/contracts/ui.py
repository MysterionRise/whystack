from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from ._base import ContractModel, FalseOnly, Slug, Uuid7


class OptionScore(ContractModel):
    option_id: Slug
    score: Annotated[float, Field(ge=0, le=100)]


class RecommendationSummary(ContractModel):
    kind: Literal["recommendation-summary"]
    id: Slug
    title: Annotated[str, Field(min_length=1, max_length=160)]
    status: Literal["demonstration"]
    selected_option_id: Slug
    rationale: Annotated[str, Field(min_length=1, max_length=1200)]
    option_scores: Annotated[
        list[OptionScore],
        Field(
            min_length=2,
            max_length=8,
            json_schema_extra={"uniqueItems": True},
        ),
    ]
    disclaimer: Annotated[str, Field(min_length=1, max_length=240)]

    @model_validator(mode="after")
    def require_unique_scores(self) -> Self:
        score_keys = {(item.option_id, item.score) for item in self.option_scores}
        if len(score_keys) != len(self.option_scores):
            raise ValueError("option scores must be unique")
        return self


class ViewEvidenceAction(ContractModel):
    kind: Literal["view-evidence"]
    id: Slug
    label: Annotated[str, Field(min_length=1, max_length=80)]
    enabled: FalseOnly


class UiEnvelopeMeta(ContractModel):
    run_id: Uuid7
    event_sequence: Annotated[int, Field(ge=1)]
    generated_by: Literal["deterministic-fixture"]
    fixture_version: Literal["walking-skeleton-v1"]


class UiEnvelope(ContractModel):
    schema_version: Literal["1.0"]
    component: RecommendationSummary
    actions: Annotated[list[ViewEvidenceAction], Field(max_length=1)]
    meta: UiEnvelopeMeta
