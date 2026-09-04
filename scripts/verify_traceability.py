#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "PyYAML==6.0.3",
# ]
# ///
"""Verify BMAD-to-Spec-Kit requirement traceability."""

import argparse
from collections import Counter
from pathlib import Path
import re
from typing import NamedTuple, Sequence

import yaml


class TraceabilityIssue(NamedTuple):
    code: str
    path: str
    message: str


CANONICAL_DOCUMENTS = {
    "functional_requirements": (
        "_bmad-output/planning-artifacts/prd.md",
        re.compile(r"(?m)^### (FR-\d{3})\b"),
    ),
    "nonfunctional_requirements": (
        "_bmad-output/planning-artifacts/prd.md",
        re.compile(r"(?m)^### (NFR-\d{3})\b"),
    ),
    "epics": (
        "_bmad-output/planning-artifacts/epics.md",
        re.compile(r"(?m)^## (EPIC-\d{3})\b"),
    ),
    "quality_requirements": (
        "_bmad-output/test-artifacts/ai-quality-contract.md",
        re.compile(r"(?m)^## (QUALITY-[A-Z]+-\d{3})\b"),
    ),
    "acceptance_scenarios": (
        "specs/001-walking-skeleton/spec.md",
        re.compile(r"(?m)^### (AS-\d{3})\b"),
    ),
    "task_index": (
        "specs/001-walking-skeleton/tasks.md",
        re.compile(r"(?m)^- \[[ xX]\] \*\*(T\d{3})\b"),
    ),
}
REFERENCE_PATTERNS = {
    "functional_requirements": re.compile(r"\bFR-\d{3}\b"),
    "nonfunctional_requirements": re.compile(r"\bNFR-\d{3}\b"),
    "epics": re.compile(r"\bEPIC-\d{3}\b"),
    "quality_requirements": re.compile(r"\bQUALITY-[A-Z]+-\d{3}\b"),
    "acceptance_scenarios": re.compile(r"\bAS-\d{3}\b"),
    "task_index": re.compile(r"\bT\d{3}\b"),
}


def _format_set(values: set[str]) -> str:
    return ", ".join(sorted(values)) if values else "none"


def _reference_issue(
    issues: list[TraceabilityIssue],
    path: str,
    value,
    allowed: set[str],
    kind: str,
) -> None:
    if isinstance(value, str) and value not in allowed:
        issues.append(
            TraceabilityIssue(
                "dangling-traceability-reference",
                path,
                f"Unknown {kind} reference {value!r}",
            )
        )


def _reference_list_issues(
    issues: list[TraceabilityIssue],
    path: str,
    values,
    allowed: set[str],
    kind: str,
) -> None:
    if not isinstance(values, list):
        return
    for index, value in enumerate(values):
        _reference_issue(
            issues,
            f"{path}[{index}]",
            value,
            allowed,
            kind,
        )


def validate_traceability(root: Path) -> list[TraceabilityIssue]:
    root = Path(root)
    issues: list[TraceabilityIssue] = []
    declarations: dict[str, set[str]] = {}

    for kind, (relative, pattern) in CANONICAL_DOCUMENTS.items():
        path = root / relative
        try:
            matches = pattern.findall(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            issues.append(
                TraceabilityIssue(
                    "missing-canonical-document",
                    relative,
                    f"Canonical {kind} document does not exist",
                )
            )
            declarations[kind] = set()
            continue
        counts = Counter(matches)
        declarations[kind] = set(matches)
        for identifier, count in counts.items():
            if count > 1:
                issues.append(
                    TraceabilityIssue(
                        "duplicate-canonical-id",
                        relative,
                        f"{identifier} is declared {count} times",
                    )
                )

    trace_path = root / ".ai-sdlc" / "traceability.yaml"
    try:
        trace = yaml.safe_load(trace_path.read_text(encoding="utf-8")) or {}
    except (FileNotFoundError, yaml.YAMLError) as error:
        issues.append(
            TraceabilityIssue(
                "invalid-traceability-map",
                ".ai-sdlc/traceability.yaml",
                str(error),
            )
        )
        return issues

    for kind in (
        "functional_requirements",
        "nonfunctional_requirements",
        "quality_requirements",
        "acceptance_scenarios",
        "task_index",
    ):
        mapped = trace.get(kind)
        if not isinstance(mapped, dict):
            issues.append(
                TraceabilityIssue(
                    "missing-traceability-section",
                    ".ai-sdlc/traceability.yaml",
                    f"{kind} must be a mapping",
                )
            )
            mapped_ids: set[str] = set()
        else:
            mapped_ids = set(mapped)
        expected_ids = declarations[kind]
        if mapped_ids != expected_ids:
            issues.append(
                TraceabilityIssue(
                    "canonical-id-set-mismatch",
                    f".ai-sdlc/traceability.yaml:{kind}",
                    (
                        f"missing [{_format_set(expected_ids - mapped_ids)}]; "
                        f"unexpected [{_format_set(mapped_ids - expected_ids)}]"
                    ),
                )
            )

    fr_ids = declarations["functional_requirements"]
    nfr_ids = declarations["nonfunctional_requirements"]
    epic_ids = declarations["epics"]
    quality_ids = declarations["quality_requirements"]
    scenario_ids = declarations["acceptance_scenarios"]
    task_ids = declarations["task_index"]
    requirement_ids = fr_ids | nfr_ids | quality_ids

    active = trace.get("active_feature", {})
    if isinstance(active, dict):
        _reference_issue(
            issues,
            ".ai-sdlc/traceability.yaml:active_feature.epic",
            active.get("epic"),
            epic_ids,
            "epic",
        )
        for key in ("specification", "plan", "tasks"):
            relative = active.get(key)
            if isinstance(relative, str) and not (root / relative).is_file():
                issues.append(
                    TraceabilityIssue(
                        "missing-active-feature-artifact",
                        relative,
                        f"Active feature {key} does not exist",
                    )
                )
        contracts = active.get("contract", [])
        if isinstance(contracts, list):
            for relative in contracts:
                if isinstance(relative, str) and not (root / relative).is_file():
                    issues.append(
                        TraceabilityIssue(
                            "missing-active-feature-artifact",
                            relative,
                            "Active feature contract does not exist",
                        )
                    )

    for section_name in ("functional_requirements", "nonfunctional_requirements"):
        section = trace.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for identifier, mapping in section.items():
            if not isinstance(mapping, dict):
                continue
            base = f".ai-sdlc/traceability.yaml:{section_name}.{identifier}"
            _reference_list_issues(
                issues,
                f"{base}.epics",
                mapping.get("epics"),
                epic_ids,
                "epic",
            )
            _reference_list_issues(
                issues,
                f"{base}.active_scenarios",
                mapping.get("active_scenarios"),
                scenario_ids,
                "acceptance scenario",
            )
            _reference_list_issues(
                issues,
                f"{base}.active_tasks",
                mapping.get("active_tasks"),
                task_ids,
                "task",
            )
            if "active_quality_gate" in mapping:
                _reference_issue(
                    issues,
                    f"{base}.active_quality_gate",
                    mapping.get("active_quality_gate"),
                    quality_ids,
                    "quality requirement",
                )

    quality_section = trace.get("quality_requirements", {})
    if isinstance(quality_section, dict):
        for identifier, mapping in quality_section.items():
            if not isinstance(mapping, dict):
                continue
            base = (
                ".ai-sdlc/traceability.yaml:"
                f"quality_requirements.{identifier}"
            )
            _reference_list_issues(
                issues,
                f"{base}.scenarios",
                mapping.get("scenarios"),
                scenario_ids,
                "acceptance scenario",
            )
            _reference_list_issues(
                issues,
                f"{base}.tasks",
                mapping.get("tasks"),
                task_ids,
                "task",
            )

    scenario_section = trace.get("acceptance_scenarios", {})
    if isinstance(scenario_section, dict):
        for identifier, mapping in scenario_section.items():
            if not isinstance(mapping, dict):
                continue
            base = (
                ".ai-sdlc/traceability.yaml:"
                f"acceptance_scenarios.{identifier}"
            )
            _reference_list_issues(
                issues,
                f"{base}.baseline_requirements",
                mapping.get("baseline_requirements"),
                requirement_ids,
                "baseline requirement",
            )
            _reference_list_issues(
                issues,
                f"{base}.tasks",
                mapping.get("tasks"),
                task_ids,
                "task",
            )

    task_section = trace.get("task_index", {})
    if isinstance(task_section, dict):
        for identifier, mapping in task_section.items():
            if not isinstance(mapping, dict):
                continue
            _reference_list_issues(
                issues,
                (
                    ".ai-sdlc/traceability.yaml:"
                    f"task_index.{identifier}.scenarios"
                ),
                mapping.get("scenarios"),
                scenario_ids,
                "acceptance scenario",
            )

    requirement_scenario_pairs: set[tuple[str, str]] = set()
    for section_name in (
        "functional_requirements",
        "nonfunctional_requirements",
    ):
        section = trace.get(section_name, {})
        if not isinstance(section, dict):
            continue
        for requirement_id, mapping in section.items():
            if not isinstance(mapping, dict):
                continue
            scenarios = mapping.get("active_scenarios")
            tasks = mapping.get("active_tasks")
            if isinstance(scenarios, list):
                requirement_scenario_pairs.update(
                    (requirement_id, scenario_id)
                    for scenario_id in scenarios
                    if isinstance(scenario_id, str)
                )
            if isinstance(tasks, list) and tasks and not scenarios:
                issues.append(
                    TraceabilityIssue(
                        "incomplete-traceability-chain",
                        (
                            ".ai-sdlc/traceability.yaml:"
                            f"{section_name}.{requirement_id}"
                        ),
                        "Active tasks require at least one active scenario",
                    )
                )
    if isinstance(quality_section, dict):
        for requirement_id, mapping in quality_section.items():
            if not isinstance(mapping, dict):
                continue
            scenarios = mapping.get("scenarios")
            tasks = mapping.get("tasks")
            if isinstance(scenarios, list):
                requirement_scenario_pairs.update(
                    (requirement_id, scenario_id)
                    for scenario_id in scenarios
                    if isinstance(scenario_id, str)
                )
            if isinstance(tasks, list) and tasks and not scenarios:
                issues.append(
                    TraceabilityIssue(
                        "incomplete-traceability-chain",
                        (
                            ".ai-sdlc/traceability.yaml:"
                            f"quality_requirements.{requirement_id}"
                        ),
                        "Quality tasks require at least one acceptance scenario",
                    )
                )

    scenario_requirement_pairs: set[tuple[str, str]] = set()
    scenario_task_pairs: set[tuple[str, str]] = set()
    if isinstance(scenario_section, dict):
        for scenario_id, mapping in scenario_section.items():
            if not isinstance(mapping, dict):
                continue
            requirements = mapping.get("baseline_requirements")
            tasks = mapping.get("tasks")
            if not isinstance(requirements, list) or not requirements:
                issues.append(
                    TraceabilityIssue(
                        "incomplete-traceability-chain",
                        (
                            ".ai-sdlc/traceability.yaml:"
                            f"acceptance_scenarios.{scenario_id}"
                        ),
                        "Acceptance scenario requires baseline requirements",
                    )
                )
            else:
                scenario_requirement_pairs.update(
                    (requirement_id, scenario_id)
                    for requirement_id in requirements
                    if isinstance(requirement_id, str)
                )
            if not isinstance(tasks, list) or not tasks:
                issues.append(
                    TraceabilityIssue(
                        "incomplete-traceability-chain",
                        (
                            ".ai-sdlc/traceability.yaml:"
                            f"acceptance_scenarios.{scenario_id}"
                        ),
                        "Acceptance scenario requires at least one task",
                    )
                )
            else:
                scenario_task_pairs.update(
                    (scenario_id, task_id)
                    for task_id in tasks
                    if isinstance(task_id, str)
                )

    task_scenario_pairs: set[tuple[str, str]] = set()
    if isinstance(task_section, dict):
        for task_id, mapping in task_section.items():
            scenarios = (
                mapping.get("scenarios") if isinstance(mapping, dict) else None
            )
            if not isinstance(scenarios, list) or not scenarios:
                issues.append(
                    TraceabilityIssue(
                        "incomplete-traceability-chain",
                        (
                            ".ai-sdlc/traceability.yaml:"
                            f"task_index.{task_id}"
                        ),
                        "Every implementation task requires a scenario",
                    )
                )
            else:
                task_scenario_pairs.update(
                    (scenario_id, task_id)
                    for scenario_id in scenarios
                    if isinstance(scenario_id, str)
                )

    for requirement_id, scenario_id in sorted(
        requirement_scenario_pairs ^ scenario_requirement_pairs
    ):
        owner = (
            "requirement mapping"
            if (requirement_id, scenario_id) in requirement_scenario_pairs
            else "acceptance scenario"
        )
        issues.append(
            TraceabilityIssue(
                "asymmetric-traceability",
                ".ai-sdlc/traceability.yaml",
                (
                    f"{requirement_id} ↔ {scenario_id} appears only in the "
                    f"{owner}"
                ),
            )
        )

    for scenario_id, task_id in sorted(
        scenario_task_pairs ^ task_scenario_pairs
    ):
        owner = (
            "acceptance scenario"
            if (scenario_id, task_id) in scenario_task_pairs
            else "task index"
        )
        issues.append(
            TraceabilityIssue(
                "asymmetric-traceability",
                ".ai-sdlc/traceability.yaml",
                f"{scenario_id} ↔ {task_id} appears only in the {owner}",
            )
        )

    for relative in (
        "specs/001-walking-skeleton/spec.md",
        "specs/001-walking-skeleton/tasks.md",
    ):
        path = root / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for kind, pattern in REFERENCE_PATTERNS.items():
            allowed = declarations[kind]
            for identifier in set(pattern.findall(text)):
                if identifier not in allowed:
                    issues.append(
                        TraceabilityIssue(
                            "unknown-canonical-reference",
                            relative,
                            f"{identifier} has no canonical {kind} definition",
                        )
                    )

    authorities = trace.get("authorities", {})
    if isinstance(authorities, dict):
        for owner, relative in authorities.items():
            if isinstance(relative, str) and not (root / relative).is_file():
                issues.append(
                    TraceabilityIssue(
                        "missing-authority-artifact",
                        relative,
                        f"Authority artifact for {owner} does not exist",
                    )
                )

    return issues


def format_issues(issues: Sequence[TraceabilityIssue]) -> str:
    return "\n".join(
        f"{issue.code}: {issue.path}: {issue.message}" for issue in issues
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify BMAD-to-Spec-Kit requirement traceability."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Packet root; defaults to the parent of scripts/.",
    )
    arguments = parser.parse_args(argv)
    issues = validate_traceability(arguments.root)
    if issues:
        print(format_issues(issues))
        return 1
    print("Traceability validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
