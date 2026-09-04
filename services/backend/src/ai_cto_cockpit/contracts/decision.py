from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from ._base import (
    ContractModel,
    EnteredWeight,
    JsonDate,
    JsonDateTime,
    NormalizedWeight,
    Slug,
    Uuid7,
)

type ConstraintSeverity = Literal["hard", "advisory"]
type DeploymentTarget = Literal["managed", "self-hosted", "on-device"]

DECISION_QUESTION_PATTERN = r"^[\s\S]*\S[\s\S]*$"


def _require_unique_strings(values: list[str]) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError("values must be unique")
    return values


class DecisionOption(ContractModel):
    id: Slug
    label: Annotated[str, Field(min_length=1, max_length=120)]
    description: Annotated[str, Field(max_length=1000)]


class CriterionInput(ContractModel):
    id: Slug
    label: Annotated[str, Field(min_length=1, max_length=120)]
    entered_weight: EnteredWeight


class CriterionView(ContractModel):
    id: Slug
    label: Annotated[str, Field(min_length=1, max_length=120)]
    entered_weight: EnteredWeight
    normalized_weight: NormalizedWeight


class ConstraintBase(ContractModel):
    model_config = ConfigDict(extra="ignore")

    id: Slug
    kind: str
    label: Annotated[str, Field(min_length=1, max_length=120)]
    severity: ConstraintSeverity


class BudgetConstraint(ContractModel):
    id: Slug
    kind: Literal["budget"]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    severity: ConstraintSeverity
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    maximum: Annotated[float, Field(ge=0)]


class DeadlineConstraint(ContractModel):
    id: Slug
    kind: Literal["deadline"]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    severity: ConstraintSeverity
    date: JsonDate


class CapabilityConstraint(ContractModel):
    id: Slug
    kind: Literal["capability"]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    severity: ConstraintSeverity
    capability: Slug


class ForbiddenVendorConstraint(ContractModel):
    id: Slug
    kind: Literal["forbidden-vendor"]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    severity: ConstraintSeverity
    vendor: Annotated[str, Field(min_length=1, max_length=120)]


class LicenseConstraint(ContractModel):
    id: Slug
    kind: Literal["license"]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    severity: ConstraintSeverity
    allowed_spdx: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=80)]],
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]

    _unique_allowed_spdx = field_validator("allowed_spdx")(_require_unique_strings)


class ResidencyConstraint(ContractModel):
    id: Slug
    kind: Literal["residency"]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    severity: ConstraintSeverity
    allowed_countries: Annotated[
        list[Annotated[str, Field(pattern=r"^[A-Z]{2}$")]],
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]

    _unique_allowed_countries = field_validator("allowed_countries")(
        _require_unique_strings
    )


class DeploymentModeConstraint(ContractModel):
    id: Slug
    kind: Literal["deployment-mode"]
    label: Annotated[str, Field(min_length=1, max_length=120)]
    severity: ConstraintSeverity
    allowed_modes: Annotated[
        list[DeploymentTarget],
        Field(min_length=1, json_schema_extra={"uniqueItems": True}),
    ]

    _unique_allowed_modes = field_validator("allowed_modes")(_require_unique_strings)


type Constraint = Annotated[
    BudgetConstraint
    | DeadlineConstraint
    | CapabilityConstraint
    | ForbiddenVendorConstraint
    | LicenseConstraint
    | ResidencyConstraint
    | DeploymentModeConstraint,
    Field(discriminator="kind"),
]


class DecisionFrameInput(ContractModel):
    schema_version: Literal["1.0"]
    question: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            pattern=DECISION_QUESTION_PATTERN,
        ),
    ]
    context: Annotated[str, Field(max_length=10000)]
    options: Annotated[list[DecisionOption], Field(min_length=2, max_length=8)]
    criteria: Annotated[list[CriterionInput], Field(min_length=1, max_length=10)]
    constraints: Annotated[list[Constraint], Field(max_length=20)]

    @model_validator(mode="after")
    def require_unique_ids(self) -> Self:
        self._check_unique_ids()
        return self

    def _check_unique_ids(self) -> None:
        for name, values in (
            ("option", [item.id for item in self.options]),
            ("criterion", [item.id for item in self.criteria]),
            ("constraint", [item.id for item in self.constraints]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} ids must be unique")


class DecisionFrameView(ContractModel):
    schema_version: Literal["1.0"]
    question: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            pattern=DECISION_QUESTION_PATTERN,
        ),
    ]
    context: Annotated[str, Field(max_length=10000)]
    options: Annotated[list[DecisionOption], Field(min_length=2, max_length=8)]
    criteria: Annotated[list[CriterionView], Field(min_length=1, max_length=10)]
    constraints: Annotated[list[Constraint], Field(max_length=20)]

    @model_validator(mode="after")
    def require_unique_ids(self) -> Self:
        for name, values in (
            ("option", [item.id for item in self.options]),
            ("criterion", [item.id for item in self.criteria]),
            ("constraint", [item.id for item in self.constraints]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name} ids must be unique")
        return self


class DecisionView(ContractModel):
    id: Uuid7
    current_revision: Annotated[int, Field(ge=1)]
    frame: DecisionFrameView
    created_at: JsonDateTime
    updated_at: JsonDateTime
