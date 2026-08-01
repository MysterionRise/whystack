#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "jsonschema==4.25.1",
#   "openapi-spec-validator==0.7.2",
#   "PyYAML==6.0.3",
# ]
# ///
"""Validate the portable AI CTO Cockpit bootstrap packet."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, NamedTuple, Sequence

import yaml


class ValidationIssue(NamedTuple):
    code: str
    path: str
    message: str


TEXT_SUFFIXES = {
    "",
    ".csv",
    ".env",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
GENERATED_SYMLINK_DIRECTORIES = frozenset(
    {
        ".git",
        ".next",
        ".pnpm-store",
        ".venv",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
        "playwright-report",
        "test-results",
        "venv",
    }
)
FORBIDDEN_PLACEHOLDER = re.compile(
    r"\b(?:TODO|TBD|CHANGEME|FIXME)\b|\[(?:PLACEHOLDER|INSERT [^\]]+)\]",
    re.IGNORECASE,
)
MACHINE_SPECIFIC_PATH = re.compile(
    r"(?:/Users/[^/\s]+|/home/[^/\s]+|/private/tmp)(?:/[^\s`\"']*)?"
)
DEFAULT_REQUIRED_PATHS = (
    "README.md",
    "BOOTSTRAP_PROMPT.md",
    "LICENSE",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    ".gitignore",
    ".env.example",
    ".ai-sdlc/WORKFLOW.md",
    ".ai-sdlc/toolchain.lock.yaml",
    ".ai-sdlc/inception-baseline.yaml",
    ".ai-sdlc/traceability.yaml",
    ".ai-sdlc/source-manifest.yaml",
    "_bmad/_config/manifest.yaml",
    "_bmad-output/planning-artifacts/product-brief.md",
    "_bmad-output/planning-artifacts/prd.md",
    "_bmad-output/planning-artifacts/DESIGN.md",
    "_bmad-output/planning-artifacts/EXPERIENCE.md",
    "_bmad-output/planning-artifacts/ARCHITECTURE-SPINE.md",
    "_bmad-output/planning-artifacts/epics.md",
    "_bmad-output/planning-artifacts/implementation-readiness.md",
    "_bmad-output/test-artifacts/system-test-design.md",
    "_bmad-output/test-artifacts/ai-quality-contract.md",
    "_bmad-output/project-context.md",
    ".specify/init-options.json",
    ".specify/memory/constitution.md",
    ".specify/templates/overrides/spec-template.md",
    ".specify/templates/overrides/tasks-template.md",
    ".specify/workflows/ai-feature-delivery/workflow.yml",
    ".specify/workflows/workflow-registry.json",
    "specs/000-product-map/spec.md",
    "specs/001-walking-skeleton/spec.md",
    "specs/001-walking-skeleton/plan.md",
    "specs/001-walking-skeleton/research.md",
    "specs/001-walking-skeleton/data-model.md",
    "specs/001-walking-skeleton/contracts/openapi.yaml",
    "specs/001-walking-skeleton/contracts/ui-envelope.schema.json",
    "specs/001-walking-skeleton/checklists/requirements.md",
    "specs/001-walking-skeleton/quickstart.md",
    "specs/001-walking-skeleton/tasks.md",
    "docs/adr/0001-bounded-bmad-speckit.md",
    "docs/architecture/system-context.md",
    "docs/security/threat-model.md",
    "docs/provenance.md",
    "docs/changes/README.md",
    "evals/README.md",
    "evals/dataset.schema.json",
    "evals/seed-v0.jsonl",
    "evals/attack-seed-v0.jsonl",
    "seed/sample-project/manifest.yaml",
    "scripts/verify-bootstrap.sh",
    "scripts/verify_bootstrap.py",
    "scripts/verify_traceability.py",
    "tests/test_bootstrap_validation.py",
    "tests/test_traceability_validation.py",
    ".github/workflows/bootstrap-validation.yml",
    "third_party/licenses/BMAD-METHOD-LICENSE.txt",
    "third_party/licenses/BMAD-TEA-LICENSE.txt",
    "third_party/licenses/SPEC-KIT-LICENSE.txt",
    ".agents/skills/bmad-prd/SKILL.md",
    ".agents/skills/speckit-specify/SKILL.md",
    ".claude/skills/bmad-prd/SKILL.md",
    ".claude/skills/speckit-specify/SKILL.md",
)
DEFAULT_AUTHORED_ROOTS = (
    "README.md",
    "BOOTSTRAP_PROMPT.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    ".env.example",
    ".github",
    ".ai-sdlc",
    "_bmad-output",
    ".specify/memory",
    ".specify/templates/overrides",
    ".specify/workflows/ai-feature-delivery",
    "specs",
    "docs",
    "evals",
    "seed",
)
DEFAULT_SECRET_SCAN_ROOTS = DEFAULT_AUTHORED_ROOTS + (
    "scripts",
    "tests",
)
EXPECTED_SEED_CATEGORIES = Counter(
    {
        "retrieval_citation": 5,
        "constraint_conflict": 3,
        "memory_sequence": 2,
    }
)
EXPECTED_ATTACK_CATEGORIES = Counter({"prompt_injection": 2})
FORBIDDEN_BMAD_ADAPTERS = (
    "bmad-agent-dev",
    "bmad-code-review",
    "bmad-correct-course",
    "bmad-create-story",
    "bmad-dev-auto",
    "bmad-dev-story",
    "bmad-qa-generate-e2e-tests",
    "bmad-quick-dev",
    "bmad-retrospective",
    "bmad-spec",
    "bmad-sprint-planning",
    "bmad-sprint-status",
)
ALLOWED_SPECKIT_WORKFLOW_COMMANDS = {
    "speckit.analyze",
    "speckit.checklist",
    "speckit.clarify",
    "speckit.converge",
    "speckit.implement",
    "speckit.plan",
    "speckit.specify",
    "speckit.tasks",
}
HIGH_CONFIDENCE_SECRET_PATTERNS = (
    re.compile(
        r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----"
    ),
    re.compile(
        r"\b(?:"
        r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"
        r"|gh[pousr]_[A-Za-z0-9]{30,}"
        r"|AKIA[0-9A-Z]{16}"
        r"|xox[baprs]-[A-Za-z0-9-]{20,}"
        r")\b"
    ),
    re.compile(
        r"(?i)\b(?:"
        r"OPENAI_API_KEY|OPENROUTER_API_KEY|ANTHROPIC_API_KEY|"
        r"AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|SLACK_TOKEN|"
        r"DATABASE_PASSWORD"
        r")\s*[:=]\s*[\"']?[A-Za-z0-9/+_.-]{16,}"
    ),
)


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_jsonl(
    path: Path,
    issues: list[ValidationIssue],
) -> list[tuple[int, dict]]:
    records: list[tuple[int, dict]] = []
    if not path.is_file():
        issues.append(
            ValidationIssue(
                "missing-eval-file",
                path.as_posix(),
                "Required evaluation dataset does not exist",
            )
        )
        return records
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            issues.append(
                ValidationIssue(
                    "invalid-jsonl",
                    f"{path.as_posix()}:{line_number}",
                    str(error),
                )
            )
            continue
        if not isinstance(value, dict):
            issues.append(
                ValidationIssue(
                    "eval-record-not-object",
                    f"{path.as_posix()}:{line_number}",
                    "Each JSONL record must be an object",
                )
            )
            continue
        records.append((line_number, value))
    return records


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def validate_eval_datasets(root: Path) -> list[ValidationIssue]:
    """Validate eval schemas, distribution, IDs, and evidence locators."""
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError

    root = Path(root)
    issues: list[ValidationIssue] = []
    eval_root = root / "evals"
    schema_path = eval_root / "dataset.schema.json"
    seed_path = eval_root / "seed-v0.jsonl"
    attack_path = eval_root / "attack-seed-v0.jsonl"

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [
            ValidationIssue(
                "missing-eval-schema",
                "evals/dataset.schema.json",
                "Evaluation schema does not exist",
            )
        ]
    except json.JSONDecodeError as error:
        return [
            ValidationIssue(
                "invalid-json",
                "evals/dataset.schema.json",
                str(error),
            )
        ]

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        return [
            ValidationIssue(
                "invalid-json-schema",
                "evals/dataset.schema.json",
                error.message,
            )
        ]
    validator = Draft202012Validator(schema)

    datasets = (
        ("seed", seed_path, EXPECTED_SEED_CATEGORIES),
        ("attack", attack_path, EXPECTED_ATTACK_CATEGORIES),
    )
    all_records: list[tuple[Path, int, dict]] = []
    for dataset_name, path, expected_categories in datasets:
        records = _load_jsonl(path, issues)
        categories = Counter(
            record.get("category")
            for _, record in records
            if isinstance(record.get("category"), str)
        )
        if categories != expected_categories:
            issues.append(
                ValidationIssue(
                    "eval-distribution-mismatch",
                    path.relative_to(root).as_posix()
                    if path.is_relative_to(root)
                    else path.as_posix(),
                    (
                        f"{dataset_name} categories are {dict(categories)}; "
                        f"expected {dict(expected_categories)}"
                    ),
                )
            )
        for line_number, record in records:
            all_records.append((path, line_number, record))
            for error in sorted(
                validator.iter_errors(record),
                key=lambda item: tuple(str(part) for part in item.path),
            ):
                location = ".".join(str(part) for part in error.path) or "$"
                issues.append(
                    ValidationIssue(
                        "eval-schema-violation",
                        (
                            f"{path.relative_to(root).as_posix()}:"
                            f"{line_number}:{location}"
                        ),
                        error.message,
                    )
                )

    seen_ids: dict[str, str] = {}
    for path, line_number, record in all_records:
        record_id = record.get("id")
        if not isinstance(record_id, str):
            continue
        location = f"{path.relative_to(root).as_posix()}:{line_number}"
        if record_id in seen_ids:
            issues.append(
                ValidationIssue(
                    "duplicate-eval-id",
                    location,
                    f"{record_id!r} was already declared at {seen_ids[record_id]}",
                )
            )
        else:
            seen_ids[record_id] = location

    fixture_root = root / "seed" / "sample-project"
    manifest_path = fixture_root / "manifest.yaml"
    try:
        manifest = _load_yaml(manifest_path) or {}
    except (FileNotFoundError, UnicodeError, yaml.YAMLError) as error:
        issues.append(
            ValidationIssue(
                "invalid-seed-manifest",
                "seed/sample-project/manifest.yaml",
                str(error),
            )
        )
        return issues

    artifact_map: dict[str, str] = {}
    for index, artifact in enumerate(manifest.get("artifacts", [])):
        if not isinstance(artifact, dict):
            issues.append(
                ValidationIssue(
                    "invalid-seed-artifact",
                    f"seed/sample-project/manifest.yaml:artifacts[{index}]",
                    "Artifact entry must be an object",
                )
            )
            continue
        artifact_id = artifact.get("id")
        artifact_path = artifact.get("path")
        if not isinstance(artifact_id, str) or not isinstance(artifact_path, str):
            issues.append(
                ValidationIssue(
                    "invalid-seed-artifact",
                    f"seed/sample-project/manifest.yaml:artifacts[{index}]",
                    "Artifact requires string id and path",
                )
            )
            continue
        if artifact_id in artifact_map:
            issues.append(
                ValidationIssue(
                    "duplicate-seed-artifact-id",
                    "seed/sample-project/manifest.yaml",
                    f"Duplicate artifact id {artifact_id!r}",
                )
            )
            continue
        artifact_map[artifact_id] = artifact_path
        resolved = (fixture_root / artifact_path).resolve()
        if not resolved.is_relative_to(fixture_root.resolve()):
            issues.append(
                ValidationIssue(
                    "seed-path-escape",
                    artifact_path,
                    "Seed artifact path escapes the fixture root",
                )
            )
        elif not resolved.is_file():
            issues.append(
                ValidationIssue(
                    "missing-seed-artifact",
                    artifact_path,
                    "Manifest artifact does not exist",
                )
            )

    quality_contract = (
        root / "_bmad-output" / "test-artifacts" / "ai-quality-contract.md"
    )
    quality_ids = (
        set(re.findall(r"(?m)^## (QUALITY-[A-Z]+-\d{3})\b", quality_contract.read_text(encoding="utf-8")))
        if quality_contract.is_file()
        else set()
    )

    for path, line_number, record in all_records:
        location = f"{path.relative_to(root).as_posix()}:{line_number}"
        if quality_ids:
            for quality_id in record.get("quality_ids", []):
                if quality_id not in quality_ids:
                    issues.append(
                        ValidationIssue(
                            "unknown-eval-quality-id",
                            location,
                            f"Unknown quality requirement {quality_id!r}",
                        )
                    )
        input_data = record.get("input")
        expected = record.get("expected")
        if isinstance(input_data, dict):
            identifier_groups = (
                ("option", input_data.get("options"), "id"),
                ("criterion", input_data.get("criteria"), "id"),
                ("constraint", input_data.get("constraints"), "id"),
                ("memory-event", input_data.get("history"), "event_id"),
            )
            known_ids: dict[str, set[str]] = {}
            for kind, values, id_key in identifier_groups:
                identifiers = [
                    item.get(id_key)
                    for item in values
                    if isinstance(item, dict)
                    and isinstance(item.get(id_key), str)
                ] if isinstance(values, list) else []
                known_ids[kind] = set(identifiers)
                for identifier, count in Counter(identifiers).items():
                    if count > 1:
                        issues.append(
                            ValidationIssue(
                                f"duplicate-eval-{kind}-id",
                                location,
                                f"{identifier!r} is declared {count} times",
                            )
                        )

            criteria = input_data.get("criteria")
            weights = [
                criterion.get("weight")
                for criterion in criteria
                if isinstance(criterion, dict)
            ] if isinstance(criteria, list) else []
            if (
                weights
                and all(
                    isinstance(weight, int) and not isinstance(weight, bool)
                    for weight in weights
                )
                and sum(weights) != 100
            ):
                issues.append(
                    ValidationIssue(
                        "invalid-eval-weight-total",
                        location,
                        f"Criterion weights total {sum(weights)}; expected 100",
                    )
                )

            if isinstance(expected, dict):
                outcome = expected.get("outcome")
                selected = expected.get("selected_option")
                option_ids = known_ids["option"]
                if isinstance(selected, str) and selected not in option_ids:
                    issues.append(
                        ValidationIssue(
                            "unknown-selected-option",
                            location,
                            f"Selected option {selected!r} is not an input option",
                        )
                    )
                if outcome == "recommend" and not isinstance(selected, str):
                    issues.append(
                        ValidationIssue(
                            "missing-selected-option",
                            location,
                            "A recommend outcome requires selected_option",
                        )
                    )
                if outcome == "abstain" and selected is not None:
                    issues.append(
                        ValidationIssue(
                            "invalid-abstention-selection",
                            location,
                            "An abstain outcome cannot select an option",
                        )
                    )

                seen_constraint_results: set[tuple[str, str]] = set()
                constraint_results = expected.get(
                    "required_constraint_results",
                    [],
                )
                if not isinstance(constraint_results, list):
                    constraint_results = []
                for result_index, result in enumerate(constraint_results):
                    if not isinstance(result, dict):
                        continue
                    result_location = (
                        f"{location}:constraint-result[{result_index}]"
                    )
                    option_id = result.get("option_id")
                    constraint_id = result.get("constraint_id")
                    if option_id not in option_ids:
                        issues.append(
                            ValidationIssue(
                                "unknown-constraint-result-option",
                                result_location,
                                f"Unknown option {option_id!r}",
                            )
                        )
                    if constraint_id not in known_ids["constraint"]:
                        issues.append(
                            ValidationIssue(
                                "unknown-constraint-result-constraint",
                                result_location,
                                f"Unknown constraint {constraint_id!r}",
                            )
                        )
                    pair = (str(option_id), str(constraint_id))
                    if pair in seen_constraint_results:
                        issues.append(
                            ValidationIssue(
                                "duplicate-constraint-result",
                                result_location,
                                f"Duplicate option/constraint pair {pair!r}",
                            )
                        )
                    seen_constraint_results.add(pair)

                required_values = expected.get(
                    "required_memory_influences",
                    [],
                )
                ignored_values = expected.get("must_ignore_memory", [])
                required_memory = {
                    value
                    for value in required_values
                    if isinstance(value, str)
                } if isinstance(required_values, list) else set()
                ignored_memory = {
                    value
                    for value in ignored_values
                    if isinstance(value, str)
                } if isinstance(ignored_values, list) else set()
                history_by_id = {
                    item.get("event_id"): item
                    for item in input_data.get("history", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("event_id"), str)
                }
                for memory_id in sorted(required_memory | ignored_memory):
                    if memory_id not in history_by_id:
                        issues.append(
                            ValidationIssue(
                                "unknown-memory-event-reference",
                                location,
                                f"Unknown memory event {memory_id!r}",
                            )
                        )
                for memory_id in sorted(required_memory):
                    event = history_by_id.get(memory_id)
                    if event is None:
                        continue
                    if (
                        event.get("status") != "active"
                        or event.get("provenance") != "user_explicit"
                        or event.get("event_type")
                        not in {"decision_accepted", "preference_confirmed"}
                    ):
                        issues.append(
                            ValidationIssue(
                                "ineligible-memory-influence",
                                location,
                                (
                                    f"{memory_id!r} is not an active, explicit, "
                                    "accepted or confirmed memory"
                                ),
                            )
                        )
                for memory_id in sorted(required_memory & ignored_memory):
                    issues.append(
                        ValidationIssue(
                            "conflicting-memory-expectation",
                            location,
                            f"{memory_id!r} is both required and ignored",
                        )
                    )

            untrusted_ids = input_data.get("untrusted_artifact_ids", [])
            if not isinstance(untrusted_ids, list):
                untrusted_ids = []
            for artifact_id in untrusted_ids:
                if artifact_id not in artifact_map:
                    issues.append(
                        ValidationIssue(
                            "unknown-untrusted-artifact",
                            location,
                            f"Unknown untrusted artifact {artifact_id!r}",
                        )
                    )
        if not isinstance(expected, dict):
            continue
        for evidence_index, evidence in enumerate(
            expected.get("required_evidence", [])
        ):
            if not isinstance(evidence, dict):
                continue
            evidence_location = f"{location}:evidence[{evidence_index}]"
            artifact_id = evidence.get("artifact_id")
            evidence_path = evidence.get("path")
            if artifact_id not in artifact_map:
                issues.append(
                    ValidationIssue(
                        "unknown-evidence-artifact",
                        evidence_location,
                        f"Unknown artifact id {artifact_id!r}",
                    )
                )
                continue
            if evidence_path != artifact_map[artifact_id]:
                issues.append(
                    ValidationIssue(
                        "evidence-path-mismatch",
                        evidence_location,
                        (
                            f"Evidence path {evidence_path!r} does not match "
                            f"manifest path {artifact_map[artifact_id]!r}"
                        ),
                    )
                )
                continue
            source_path = fixture_root / artifact_map[artifact_id]
            if not source_path.is_file():
                continue
            start = evidence.get("line_start")
            end = evidence.get("line_end")
            quote = evidence.get("quote")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or not isinstance(quote, str)
                or start < 1
                or end < start
            ):
                issues.append(
                    ValidationIssue(
                        "invalid-evidence-locator",
                        evidence_location,
                        "Evidence requires valid line_start, line_end, and quote",
                    )
                )
                continue
            lines = source_path.read_text(encoding="utf-8").splitlines()
            if end > len(lines):
                issues.append(
                    ValidationIssue(
                        "evidence-line-out-of-range",
                        evidence_location,
                        f"Line {end} exceeds {len(lines)} source lines",
                    )
                )
                continue
            selected = "\n".join(lines[start - 1 : end])
            if _normalized_text(quote) not in _normalized_text(selected):
                issues.append(
                    ValidationIssue(
                        "evidence-quote-mismatch",
                        evidence_location,
                        "Evidence quote is not an exact excerpt of located lines",
                    )
                )
    return issues


def validate_contract_schemas(root: Path) -> list[ValidationIssue]:
    """Semantically validate the active OpenAPI and controlled-UI contracts."""
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError
    from openapi_spec_validator import validate
    from openapi_spec_validator.validation.exceptions import (
        OpenAPIValidationError,
        OpenAPISpecValidatorError,
    )

    root = Path(root)
    contracts = root / "specs" / "001-walking-skeleton" / "contracts"
    openapi_path = contracts / "openapi.yaml"
    ui_schema_path = contracts / "ui-envelope.schema.json"
    issues: list[ValidationIssue] = []

    try:
        openapi = _load_yaml(openapi_path)
        validate(openapi)
    except (
        FileNotFoundError,
        UnicodeError,
        yaml.YAMLError,
        OpenAPISpecValidatorError,
        OpenAPIValidationError,
    ) as error:
        issues.append(
            ValidationIssue(
                "invalid-openapi-contract",
                "specs/001-walking-skeleton/contracts/openapi.yaml",
                str(error),
            )
        )

    try:
        ui_schema = json.loads(ui_schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(ui_schema)
    except (FileNotFoundError, UnicodeError, json.JSONDecodeError, SchemaError) as error:
        issues.append(
            ValidationIssue(
                "invalid-ui-json-schema",
                (
                    "specs/001-walking-skeleton/contracts/"
                    "ui-envelope.schema.json"
                ),
                str(error),
            )
        )

    return issues


def validate_contract_semantics(root: Path) -> list[ValidationIssue]:
    """Check project-specific semantics that generic OpenAPI validation cannot."""
    root = Path(root)
    relative = "specs/001-walking-skeleton/contracts/openapi.yaml"
    try:
        openapi = _load_yaml(root / relative) or {}
    except (FileNotFoundError, UnicodeError, yaml.YAMLError) as error:
        return [
            ValidationIssue(
                "invalid-openapi-contract",
                relative,
                str(error),
            )
        ]

    issues: list[ValidationIssue] = []
    config_operation = (
        openapi.get("paths", {}).get("/config", {}).get("get", {})
    )
    if config_operation.get("security") != []:
        issues.append(
            ValidationIssue(
                "invalid-config-auth-contract",
                relative,
                "/config must be unauthenticated so it can establish a guest session",
            )
        )

    security = openapi.get("security")
    if (
        not isinstance(security, list)
        or {} not in security
        or {"guestSession": []} not in security
    ):
        issues.append(
            ValidationIssue(
                "invalid-profile-auth-contract",
                relative,
                (
                    "Global security must model either a public-demo guest "
                    "cookie or credential-free local-data mode"
                ),
            )
        )
    profile_security = openapi.get("x-runtime-security")
    if (
        not isinstance(profile_security, dict)
        or set(profile_security) != {"public-demo", "local-data"}
    ):
        issues.append(
            ValidationIssue(
                "missing-profile-auth-documentation",
                relative,
                "x-runtime-security must document both deployment profiles",
            )
        )

    schemas = openapi.get("components", {}).get("schemas", {})

    def resolved_schema(value):
        if (
            isinstance(value, dict)
            and set(value) == {"$ref"}
            and isinstance(value.get("$ref"), str)
            and value["$ref"].startswith("#/components/schemas/")
        ):
            return schemas.get(value["$ref"].rsplit("/", 1)[-1], {})
        return value

    run_event = schemas.get("RunEvent", {})
    discriminator = (
        run_event.get("discriminator") if isinstance(run_event, dict) else None
    )
    variants = run_event.get("oneOf") if isinstance(run_event, dict) else None
    if (
        not isinstance(discriminator, dict)
        or discriminator.get("propertyName") != "kind"
        or not isinstance(discriminator.get("mapping"), dict)
        or not isinstance(variants, list)
        or len(variants) != 5
    ):
        issues.append(
            ValidationIssue(
                "uncoupled-run-event-payload",
                relative,
                "RunEvent must be a five-kind discriminated union on kind",
            )
        )

    for schema_name in ("CriterionInput", "CriterionView"):
        schema = schemas.get(schema_name, {})
        entered = (
            schema.get("properties", {}).get("enteredWeight", {})
            if isinstance(schema, dict)
            else {}
        )
        entered = resolved_schema(entered)
        if (
            entered.get("type") != "string"
            or not isinstance(entered.get("pattern"), str)
        ):
            issues.append(
                ValidationIssue(
                    "lossy-entered-weight-contract",
                    relative,
                    f"{schema_name}.enteredWeight must be a bounded decimal string",
                )
            )
    normalized = (
        schemas.get("CriterionView", {})
        .get("properties", {})
        .get("normalizedWeight", {})
    )
    normalized = resolved_schema(normalized)
    if (
        normalized.get("type") != "string"
        or normalized.get("readOnly") is not True
    ):
        issues.append(
            ValidationIssue(
                "invalid-normalized-weight-contract",
                relative,
                "CriterionView.normalizedWeight must be a read-only decimal string",
            )
        )

    return issues


def _workflow_steps(steps) -> Iterable[dict]:
    if not isinstance(steps, list):
        return
    for step in steps:
        if not isinstance(step, dict):
            continue
        yield step
        for key in ("then", "else", "steps", "default"):
            yield from _workflow_steps(step.get(key))
        cases = step.get("cases")
        if isinstance(cases, dict):
            for nested in cases.values():
                yield from _workflow_steps(nested)
        template = step.get("step")
        if isinstance(template, dict):
            yield template


def validate_delivery_workflow_sequence(root: Path) -> list[ValidationIssue]:
    """Require both checklist gates in the documented delivery-stage order."""
    root = Path(root)
    relative = ".specify/workflows/ai-feature-delivery/workflow.yml"
    try:
        workflow = _load_yaml(root / relative) or {}
    except (FileNotFoundError, UnicodeError, yaml.YAMLError) as error:
        return [
            ValidationIssue(
                "invalid-project-workflow",
                relative,
                str(error),
            )
        ]

    steps = workflow.get("steps", [])
    top_level_steps = (
        [step for step in steps if isinstance(step, dict)]
        if isinstance(steps, list)
        else []
    )
    command_steps = [
        step
        for step in top_level_steps
        if isinstance(step.get("command"), str)
    ]
    commands = [step["command"] for step in command_steps]
    checklist_steps = [
        step
        for step in command_steps
        if step["command"] == "speckit.checklist"
    ]
    issues: list[ValidationIssue] = []

    if len(checklist_steps) != 2:
        issues.append(
            ValidationIssue(
                "incomplete-workflow-checklists",
                relative,
                "Delivery requires one pre-plan requirements checklist and "
                "one post-plan AI/security checklist",
            )
        )

    expected_order = (
        "speckit.specify",
        "speckit.clarify",
        "speckit.checklist",
        "speckit.plan",
        "speckit.checklist",
        "speckit.tasks",
        "speckit.analyze",
        "speckit.implement",
    )
    cursor = 0
    for command in commands:
        if cursor < len(expected_order) and command == expected_order[cursor]:
            cursor += 1
    if cursor != len(expected_order):
        issues.append(
            ValidationIssue(
                "invalid-workflow-stage-order",
                relative,
                "Top-level command stages must preserve the documented "
                "specify-to-implement order with checklists around plan",
            )
        )

    if len(checklist_steps) == 2:
        first_args = checklist_steps[0].get("input", {}).get("args", "")
        second_args = checklist_steps[1].get("input", {}).get("args", "")
        if (
            not isinstance(first_args, str)
            or "requirement" not in first_args.lower()
        ):
            issues.append(
                ValidationIssue(
                    "invalid-requirements-checklist",
                    relative,
                    "The pre-plan checklist must explicitly review requirements",
                )
            )
        if (
            not isinstance(second_args, str)
            or "ai" not in second_args.lower()
            or "security" not in second_args.lower()
        ):
            issues.append(
                ValidationIssue(
                    "invalid-ai-security-checklist",
                    relative,
                    "The post-plan checklist must explicitly review AI and security",
                )
            )

    return issues


def validate_initial_task_commands(root: Path) -> list[ValidationIssue]:
    """Ensure the first bootstrap task names deterministic install commands."""
    root = Path(root)
    relative = "specs/001-walking-skeleton/tasks.md"
    try:
        text = (root / relative).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeError) as error:
        return [
            ValidationIssue(
                "missing-exact-task-command",
                relative,
                str(error),
            )
        ]

    match = re.search(
        r"(?ms)\*\*T001\b(?P<body>.*?)(?=\n- \[[ xX]\] \*\*T002\b)",
        text,
    )
    if match is None:
        return [
            ValidationIssue(
                "missing-exact-task-command",
                relative,
                "Could not locate the T001 task block",
            )
        ]

    task = match.group("body")
    required_commands = (
        "corepack pnpm install --frozen-lockfile",
        "uv lock --project services/backend --check "
        "--python 3.12.13 --managed-python",
        "uv sync --project services/backend --locked --all-groups "
        "--no-install-project --python 3.12.13 --managed-python",
    )
    missing = [
        command for command in required_commands if f"`{command}`" not in task
    ]
    issues: list[ValidationIssue] = []
    if missing:
        issues.append(
            ValidationIssue(
                "missing-exact-task-command",
                relative,
                "T001 must name exact frozen-install commands: "
                + ", ".join(missing),
            )
        )

    compose_test = (
        "uv run --project services/backend --no-sync pytest "
        "tests/e2e/test_compose_readiness.py"
    )
    if text.count(f"`{compose_test}`") < 2:
        issues.append(
            ValidationIssue(
                "missing-exact-task-command",
                relative,
                "T002 and T003 must use the locked backend project environment",
            )
        )

    headings = re.findall(
        r"(?m)^- \[[ xX]\] \*\*T\d+ — (?P<label>[^*]+)\*\*$",
        text,
    )
    invalid_headings = [
        heading
        for heading in headings
        if re.match(r"^(?:RED|GREEN|REFACTOR|VERIFY): ", heading) is None
    ]
    if not headings or invalid_headings:
        issues.append(
            ValidationIssue(
                "invalid-task-stage-label",
                relative,
                "Every task heading must use RED, GREEN, REFACTOR, or VERIFY",
            )
        )
    return issues


def validate_framework_provenance(root: Path) -> list[ValidationIssue]:
    """Require shipped BMAD support files to have an explicit ownership class."""
    root = Path(root)
    manifest_relative = ".ai-sdlc/source-manifest.yaml"
    notices_relative = "THIRD_PARTY_NOTICES.md"
    try:
        manifest = _load_yaml(root / manifest_relative) or {}
        notices = (root / notices_relative).read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeError, yaml.YAMLError) as error:
        return [
            ValidationIssue(
                "unclassified-framework-file",
                manifest_relative,
                str(error),
            )
        ]

    bmad = next(
        (
            reference
            for reference in manifest.get("framework_references", [])
            if isinstance(reference, dict)
            and reference.get("id") == "SRC-FRAMEWORK-001"
        ),
        {},
    )
    classifications = {
        "_bmad/config.toml": "installer_managed_paths",
        "_bmad/scripts/": "installer_managed_paths",
        "_bmad/custom/": "project_managed_scaffolding",
    }
    issues: list[ValidationIssue] = []
    for path, field in classifications.items():
        shipped = (
            (root / path).is_file()
            if not path.endswith("/")
            else (root / path).is_dir()
        )
        classified = (
            isinstance(bmad.get(field), list)
            and path in bmad.get(field, [])
        )
        noticed = f"`{path}`" in notices
        if shipped and (not classified or not noticed):
            missing_parts = []
            if not classified:
                missing_parts.append(f"{field} classification")
            if not noticed:
                missing_parts.append("third-party notice")
            issues.append(
                ValidationIssue(
                    "unclassified-framework-file",
                    path,
                    "Missing " + " and ".join(missing_parts),
                )
            )
    return issues


def validate_sdlc_wiring(root: Path) -> list[ValidationIssue]:
    """Verify that the bounded BMAD-to-Spec-Kit loop is actually discoverable."""
    root = Path(root)
    issues = validate_delivery_workflow_sequence(root)
    issues.extend(validate_initial_task_commands(root))
    overrides = root / ".specify" / "templates" / "overrides"
    spec_template = overrides / "spec-template.md"
    tasks_template = overrides / "tasks-template.md"

    if (overrides / "feature-spec.md").exists():
        issues.append(
            ValidationIssue(
                "inactive-speckit-template",
                ".specify/templates/overrides/feature-spec.md",
                "Spec Kit resolves spec-template.md, not feature-spec.md",
            )
        )
    try:
        spec_text = spec_template.read_text(encoding="utf-8")
        if "Never mint a feature-local `FR-*`" not in spec_text:
            issues.append(
                ValidationIssue(
                    "unsafe-speckit-spec-template",
                    ".specify/templates/overrides/spec-template.md",
                    "Template must reserve FR-* identifiers for BMAD",
                )
            )
    except FileNotFoundError:
        issues.append(
            ValidationIssue(
                "inactive-speckit-template",
                ".specify/templates/overrides/spec-template.md",
                "Active project spec template is missing",
            )
        )

    try:
        tasks_text = tasks_template.read_text(encoding="utf-8")
        required_phrases = (
            "Tests are mandatory",
            "RED",
            "GREEN",
            "explicit reviewed task ID or phase range",
        )
        for phrase in required_phrases:
            if phrase not in tasks_text:
                issues.append(
                    ValidationIssue(
                        "unsafe-speckit-tasks-template",
                        ".specify/templates/overrides/tasks-template.md",
                        f"Mandatory task policy phrase is missing: {phrase!r}",
                    )
                )
        if re.search(r"tests? (?:are|is) optional", tasks_text, re.IGNORECASE):
            issues.append(
                ValidationIssue(
                    "unsafe-speckit-tasks-template",
                    ".specify/templates/overrides/tasks-template.md",
                    "Project task template must never make tests optional",
                )
            )
    except FileNotFoundError:
        issues.append(
            ValidationIssue(
                "inactive-speckit-template",
                ".specify/templates/overrides/tasks-template.md",
                "Active project tasks template is missing",
            )
        )

    workflow_path = (
        root
        / ".specify"
        / "workflows"
        / "ai-feature-delivery"
        / "workflow.yml"
    )
    registry_path = (
        root / ".specify" / "workflows" / "workflow-registry.json"
    )
    try:
        workflow = _load_yaml(workflow_path) or {}
    except (FileNotFoundError, UnicodeError, yaml.YAMLError) as error:
        issues.append(
            ValidationIssue(
                "invalid-project-workflow",
                ".specify/workflows/ai-feature-delivery/workflow.yml",
                str(error),
            )
        )
        workflow = {}
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        entry = registry.get("workflows", {}).get("ai-feature-delivery")
        if not isinstance(entry, dict):
            issues.append(
                ValidationIssue(
                    "unregistered-project-workflow",
                    ".specify/workflows/workflow-registry.json",
                    "ai-feature-delivery is not installed",
                )
            )
    except (FileNotFoundError, UnicodeError, json.JSONDecodeError) as error:
        issues.append(
            ValidationIssue(
                "invalid-workflow-registry",
                ".specify/workflows/workflow-registry.json",
                str(error),
            )
        )

    metadata = workflow.get("workflow", {})
    if not isinstance(metadata, dict) or metadata.get("id") != "ai-feature-delivery":
        issues.append(
            ValidationIssue(
                "invalid-project-workflow",
                ".specify/workflows/ai-feature-delivery/workflow.yml",
                "workflow.id must be ai-feature-delivery",
            )
        )
    workflow_inputs = workflow.get("inputs", {})
    batch_input = (
        workflow_inputs.get("batch")
        if isinstance(workflow_inputs, dict)
        else None
    )
    if not isinstance(batch_input, dict) or batch_input.get("required") is not True:
        issues.append(
            ValidationIssue(
                "unbounded-project-workflow",
                ".specify/workflows/ai-feature-delivery/workflow.yml",
                "A reviewed batch input must be required",
            )
        )

    seen_commands: set[str] = set()
    bounded_implement = False
    for step in _workflow_steps(workflow.get("steps")):
        command = step.get("command")
        if not isinstance(command, str):
            continue
        seen_commands.add(command)
        if command not in ALLOWED_SPECKIT_WORKFLOW_COMMANDS:
            issues.append(
                ValidationIssue(
                    "unavailable-workflow-command",
                    ".specify/workflows/ai-feature-delivery/workflow.yml",
                    f"Command {command!r} has no pinned Spec Kit adapter",
                )
            )
        if command == "speckit.implement":
            input_data = step.get("input", {})
            args = (
                input_data.get("args", "")
                if isinstance(input_data, dict)
                else ""
            )
            bounded_implement = (
                isinstance(args, str)
                and "{{ inputs.batch }}" in args
                and re.search(r"\bonly\b", args, re.IGNORECASE) is not None
            )
    required_commands = {
        "speckit.specify",
        "speckit.clarify",
        "speckit.checklist",
        "speckit.plan",
        "speckit.tasks",
        "speckit.analyze",
        "speckit.implement",
        "speckit.converge",
    }
    missing_commands = required_commands - seen_commands
    if missing_commands:
        issues.append(
            ValidationIssue(
                "incomplete-project-workflow",
                ".specify/workflows/ai-feature-delivery/workflow.yml",
                f"Missing commands: {', '.join(sorted(missing_commands))}",
            )
        )
    if not bounded_implement:
        issues.append(
            ValidationIssue(
                "unbounded-project-workflow",
                ".specify/workflows/ai-feature-delivery/workflow.yml",
                "speckit.implement must be restricted to inputs.batch",
            )
        )

    for integration_root in (".agents/skills", ".claude/skills"):
        for adapter in FORBIDDEN_BMAD_ADAPTERS:
            relative = f"{integration_root}/{adapter}"
            if (root / relative).exists():
                issues.append(
                    ValidationIssue(
                        "prohibited-bmad-adapter",
                        relative,
                        "BMAD implementation-loop adapter must not be discoverable",
                    )
                )

    env_path = root / ".env.example"
    try:
        env_text = env_path.read_text(encoding="utf-8")
        mode_match = re.search(r"(?m)^APP_MODE=(.+)$", env_text)
        if mode_match is None or mode_match.group(1).strip() != "public-demo":
            issues.append(
                ValidationIssue(
                    "runtime-mode-drift",
                    ".env.example",
                    "APP_MODE must default to the public-demo contract value",
                )
            )
        if "public_demo" in env_text or "local_data" in env_text:
            issues.append(
                ValidationIssue(
                    "runtime-mode-drift",
                    ".env.example",
                    "Underscore runtime-mode aliases are not part of the contract",
                )
            )
    except FileNotFoundError:
        issues.append(
            ValidationIssue(
                "runtime-mode-drift",
                ".env.example",
                "Runtime configuration example is missing",
            )
        )

    try:
        toolchain = _load_yaml(
            root / ".ai-sdlc" / "toolchain.lock.yaml"
        ) or {}
        bootstrap = toolchain.get("implementation_bootstrap", {})
        bmad_lock = toolchain.get("tools", {}).get("bmad_method", {})
        locked_adapters = set(bmad_lock.get("excluded_agent_adapters", []))
        if locked_adapters != set(FORBIDDEN_BMAD_ADAPTERS):
            issues.append(
                ValidationIssue(
                    "incomplete-bmad-adapter-denylist",
                    ".ai-sdlc/toolchain.lock.yaml",
                    "The recorded excluded adapters must match the verifier denylist",
                )
            )

        required_pins = {
            "runtimes.nodejs.version": (
                bootstrap.get("runtimes", {}).get("nodejs", {}).get("version")
            ),
            "runtimes.python.version": (
                bootstrap.get("runtimes", {}).get("python", {}).get("version")
            ),
            "package_managers.pnpm.version": (
                bootstrap.get("package_managers", {})
                .get("pnpm", {})
                .get("version")
            ),
            "package_managers.uv.version": (
                bootstrap.get("package_managers", {})
                .get("uv", {})
                .get("version")
            ),
        }
        frontend = bootstrap.get("frontend", {})
        for name in (
            "next",
            "react",
            "react-dom",
            "@copilotkit/react-core",
            "@copilotkit/react-ui",
            "@ag-ui/client",
            "@ag-ui/core",
            "zod",
        ):
            required_pins[f"frontend.{name}"] = (
                frontend.get("direct_dependencies", {}).get(name)
            )
        frontend_development = frontend.get(
            "direct_development_dependencies",
            {},
        )
        for name in (
            "typescript",
            "@types/react",
            "@types/react-dom",
            "vitest",
            "@playwright/test",
            "@axe-core/playwright",
            "eslint",
            "eslint-config-next",
        ):
            required_pins[f"frontend.dev.{name}"] = (
                frontend_development.get(name)
            )
        backend_configuration = bootstrap.get("backend", {})
        backend = backend_configuration.get(
            "direct_dependencies",
            {},
        )
        for name in (
            "cryptography",
            "fastapi",
            "pydantic",
            "pydantic-settings",
            "langgraph",
            "sqlalchemy[asyncio]",
            "alembic",
            "psycopg[binary]",
            "pyyaml",
            "uuid6",
            "uvicorn",
        ):
            required_pins[f"backend.{name}"] = backend.get(name)
        required_pins["backend.build_system.uv_build"] = (
            backend_configuration.get("build_system", {}).get("uv_build")
        )
        backend_development = (
            backend_configuration.get("direct_development_dependencies", {})
        )
        for name in ("pytest", "pytest-asyncio", "ruff"):
            required_pins[f"backend.dev.{name}"] = (
                backend_development.get(name)
            )
        workspace_development = (
            bootstrap.get("workspace", {})
            .get("direct_development_dependencies", {})
        )
        required_pins["workspace.dev.pyright"] = (
            workspace_development.get("pyright")
        )

        for pin_name, value in required_pins.items():
            if (
                not isinstance(value, str)
                or not value
                or value.startswith(("^", "~", ">", "<", "="))
                or "*" in value
            ):
                issues.append(
                    ValidationIssue(
                        "missing-runtime-pin",
                        ".ai-sdlc/toolchain.lock.yaml",
                        f"{pin_name} must be an exact non-empty version",
                    )
                )

        services = bootstrap.get("services", {})
        for service in ("postgresql", "qdrant"):
            definition = services.get(service, {})
            digest = (
                definition.get("digest")
                if isinstance(definition, dict)
                else None
            )
            if (
                not isinstance(definition, dict)
                or not isinstance(definition.get("version"), str)
                or not isinstance(definition.get("image"), str)
                or not isinstance(digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
            ):
                issues.append(
                    ValidationIssue(
                        "missing-service-pin",
                        ".ai-sdlc/toolchain.lock.yaml",
                        f"{service} requires version, image, and sha256 digest",
                    )
                )
    except (FileNotFoundError, UnicodeError, yaml.YAMLError) as error:
        issues.append(
            ValidationIssue(
                "invalid-toolchain-lock",
                ".ai-sdlc/toolchain.lock.yaml",
                str(error),
            )
        )

    return issues


def validate_baseline_hashes(root: Path) -> list[ValidationIssue]:
    """Confirm that accepted inception artifacts still match their hashes."""
    root = Path(root)
    baseline_path = root / ".ai-sdlc" / "inception-baseline.yaml"
    try:
        baseline = _load_yaml(baseline_path) or {}
    except Exception as error:
        return [
            ValidationIssue(
                "invalid-inception-baseline",
                ".ai-sdlc/inception-baseline.yaml",
                str(error),
            )
        ]

    issues: list[ValidationIssue] = []
    for index, artifact in enumerate(baseline.get("artifacts", [])):
        if not isinstance(artifact, dict):
            continue
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        location = f".ai-sdlc/inception-baseline.yaml:artifacts[{index}]"
        if not isinstance(relative, str) or not isinstance(expected, str):
            issues.append(
                ValidationIssue(
                    "invalid-baseline-entry",
                    location,
                    "Baseline artifact requires path and sha256 strings",
                )
            )
            continue
        path = root / relative
        if not path.is_file():
            issues.append(
                ValidationIssue(
                    "baseline-artifact-missing",
                    relative,
                    "Accepted baseline artifact does not exist",
                )
            )
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            issues.append(
                ValidationIssue(
                    "baseline-hash-mismatch",
                    relative,
                    f"Expected {expected}; calculated {actual}",
                )
            )
    return issues


def validate_no_packet_symlinks(root: Path) -> list[ValidationIssue]:
    """Reject authored symlinks while ignoring generated dependency trees."""
    root = Path(root)
    issues: list[ValidationIssue] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if GENERATED_SYMLINK_DIRECTORIES.intersection(relative.parts):
            continue
        if path.is_symlink():
            issues.append(
                ValidationIssue(
                    "symlink-in-packet",
                    relative.as_posix(),
                    "Bootstrap packet must not depend on symlink targets",
                )
            )
    return issues


def _normalized_version(value) -> str:
    return str(value or "").removeprefix("v")


def validate_framework_versions(root: Path) -> list[ValidationIssue]:
    """Compare the governance lock with both generated framework manifests."""
    root = Path(root)
    try:
        lock = _load_yaml(root / ".ai-sdlc" / "toolchain.lock.yaml") or {}
        bmad_manifest = (
            _load_yaml(root / "_bmad" / "_config" / "manifest.yaml") or {}
        )
        spec_manifest = json.loads(
            (
                root
                / ".specify"
                / "integrations"
                / "speckit.manifest.json"
            ).read_text(encoding="utf-8")
        )
    except Exception as error:
        return [
            ValidationIssue(
                "invalid-framework-manifest",
                ".ai-sdlc/toolchain.lock.yaml",
                str(error),
            )
        ]

    tools = lock.get("tools", {})
    expected_bmad = _normalized_version(
        tools.get("bmad_method", {}).get("version")
    )
    expected_tea = _normalized_version(tools.get("bmad_tea", {}).get("version"))
    expected_spec = _normalized_version(
        tools.get("github_spec_kit", {}).get("version")
    )
    actual_bmad = _normalized_version(
        bmad_manifest.get("installation", {}).get("version")
    )
    tea_module = next(
        (
            module
            for module in bmad_manifest.get("modules", [])
            if module.get("name") == "tea"
        ),
        {},
    )
    actual_tea = _normalized_version(tea_module.get("version"))
    actual_spec = _normalized_version(spec_manifest.get("version"))
    comparisons = (
        ("BMAD Method", expected_bmad, actual_bmad),
        ("BMAD TEA", expected_tea, actual_tea),
        ("GitHub Spec Kit", expected_spec, actual_spec),
    )

    issues: list[ValidationIssue] = []
    for name, expected, actual in comparisons:
        if not expected:
            issues.append(
                ValidationIssue(
                    "missing-framework-lock",
                    ".ai-sdlc/toolchain.lock.yaml",
                    f"{name} has no locked version",
                )
            )
        elif expected != actual:
            issues.append(
                ValidationIssue(
                    "framework-version-drift",
                    ".ai-sdlc/toolchain.lock.yaml",
                    f"{name} is locked to {expected} but installed as {actual}",
                )
            )
    return issues


def _authored_files(root: Path, authored_roots: Sequence[str]) -> Iterable[Path]:
    for relative in authored_roots:
        candidate = root / relative
        if candidate.is_file():
            yield candidate
        elif candidate.is_dir():
            for path in sorted(candidate.rglob("*")):
                if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                    yield path


def validate_packet(
    root: Path,
    *,
    required_paths: Sequence[str] = (),
    authored_roots: Sequence[str] = (),
) -> list[ValidationIssue]:
    root = Path(root)
    issues: list[ValidationIssue] = []

    for relative in required_paths:
        if not (root / relative).exists():
            issues.append(
                ValidationIssue(
                    "missing-required-path",
                    relative,
                    "Required packet path does not exist",
                )
            )

    for path in _authored_files(root, authored_roots):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            issues.append(
                ValidationIssue(
                    "non-utf8-authored-file",
                    relative,
                    "Project-authored text must be UTF-8",
                )
            )
            continue

        if FORBIDDEN_PLACEHOLDER.search(text):
            issues.append(
                ValidationIssue(
                    "forbidden-placeholder",
                    relative,
                    "Unresolved placeholder marker found",
                )
            )
        if MACHINE_SPECIFIC_PATH.search(text):
            issues.append(
                ValidationIssue(
                    "machine-specific-path",
                    relative,
                    "Machine-specific absolute path found",
                )
            )

        if path.suffix.lower() == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as error:
                issues.append(
                    ValidationIssue("invalid-json", relative, str(error))
                )
        elif path.suffix.lower() == ".jsonl":
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except json.JSONDecodeError as error:
                    issues.append(
                        ValidationIssue(
                            "invalid-jsonl",
                            f"{relative}:{line_number}",
                            str(error),
                        )
                    )
        elif path.suffix.lower() in {".yaml", ".yml"}:
            try:
                yaml.safe_load(text)
            except yaml.YAMLError as error:
                issues.append(
                    ValidationIssue("invalid-yaml", relative, str(error))
                )

    return issues


def validate_no_secrets(
    root: Path,
    *,
    authored_roots: Sequence[str] = DEFAULT_SECRET_SCAN_ROOTS,
) -> list[ValidationIssue]:
    """Reject high-confidence credential and private-key material."""
    root = Path(root)
    issues: list[ValidationIssue] = []
    for path in _authored_files(root, authored_roots):
        relative = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(lines, start=1):
            if any(pattern.search(line) for pattern in HIGH_CONFIDENCE_SECRET_PATTERNS):
                issues.append(
                    ValidationIssue(
                        "suspected-secret",
                        f"{relative}:{line_number}",
                        "High-confidence credential or private-key pattern found",
                    )
                )
    return issues


def format_issues(issues: Sequence[ValidationIssue]) -> str:
    return "\n".join(
        f"{issue.code}: {issue.path}: {issue.message}" for issue in issues
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the copy-ready AI CTO Cockpit bootstrap packet."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Packet root; defaults to the parent of scripts/.",
    )
    arguments = parser.parse_args(argv)
    issues = validate_packet(
        arguments.root,
        required_paths=DEFAULT_REQUIRED_PATHS,
        authored_roots=DEFAULT_AUTHORED_ROOTS,
    )
    issues.extend(validate_eval_datasets(arguments.root))
    issues.extend(validate_contract_schemas(arguments.root))
    issues.extend(validate_contract_semantics(arguments.root))
    issues.extend(validate_sdlc_wiring(arguments.root))
    issues.extend(validate_framework_provenance(arguments.root))
    issues.extend(validate_no_secrets(arguments.root))
    issues.extend(validate_baseline_hashes(arguments.root))
    issues.extend(validate_framework_versions(arguments.root))

    forbidden_local_state = (
        "_bmad/config.user.toml",
        "_bmad/custom/config.user.toml",
        ".claude/settings.local.json",
    )
    for relative in forbidden_local_state:
        if (arguments.root / relative).exists():
            issues.append(
                ValidationIssue(
                    "forbidden-local-state",
                    relative,
                    "Machine/user-specific generated state must not ship",
                )
            )
    issues.extend(validate_no_packet_symlinks(arguments.root))

    if issues:
        print(format_issues(issues))
        return 1
    print("Bootstrap packet validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
