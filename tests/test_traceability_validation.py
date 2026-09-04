from pathlib import Path
import importlib.util
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class TraceabilityValidatorTests(unittest.TestCase):
    def _load_validator(self):
        validator = PROJECT_ROOT / "scripts" / "verify_traceability.py"
        spec = importlib.util.spec_from_file_location(
            "verify_traceability",
            validator,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _write_minimal_packet(self, root: Path) -> None:
        planning = root / "_bmad-output" / "planning-artifacts"
        quality = root / "_bmad-output" / "test-artifacts"
        feature = root / "specs" / "001-walking-skeleton"
        governance = root / ".ai-sdlc"
        planning.mkdir(parents=True)
        quality.mkdir(parents=True)
        feature.mkdir(parents=True)
        governance.mkdir(parents=True)

        (planning / "prd.md").write_text(
            "### FR-001 — One\n\n### NFR-001 — One\n",
            encoding="utf-8",
        )
        (planning / "epics.md").write_text(
            "## EPIC-001 — One\n",
            encoding="utf-8",
        )
        (quality / "ai-quality-contract.md").write_text(
            "## QUALITY-OPS-001 — One\n",
            encoding="utf-8",
        )
        (feature / "spec.md").write_text(
            "### AS-001 — One\n",
            encoding="utf-8",
        )
        (feature / "tasks.md").write_text(
            "- [ ] **T001 — RED: One**\n",
            encoding="utf-8",
        )
        (governance / "traceability.yaml").write_text(
            "active_feature:\n"
            "  id: 001-walking-skeleton\n"
            "  epic: EPIC-001\n"
            "functional_requirements:\n"
            "  FR-001:\n"
            "    active_scenarios: [AS-001]\n"
            "    active_tasks: [T001]\n"
            "nonfunctional_requirements:\n"
            "  NFR-001:\n"
            "    active_scenarios: [AS-001]\n"
            "quality_requirements:\n"
            "  QUALITY-OPS-001:\n"
            "    scenarios: [AS-001]\n"
            "acceptance_scenarios:\n"
            "  AS-001:\n"
            "    baseline_requirements: [FR-001, NFR-001, QUALITY-OPS-001]\n"
            "    tasks: [T001]\n"
            "task_index:\n"
            "  T001:\n"
            "    scenarios: [AS-001]\n",
            encoding="utf-8",
        )

    def test_accepts_matching_canonical_documents_and_map(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_packet(root)
            issues = module.validate_traceability(root)

        self.assertEqual([], issues)

    def test_accepts_completed_task_definition(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_packet(root)
            tasks = root / "specs" / "001-walking-skeleton" / "tasks.md"
            tasks.write_text(
                tasks.read_text(encoding="utf-8").replace("- [ ]", "- [X]"),
                encoding="utf-8",
            )

            issues = module.validate_traceability(root)

        self.assertEqual([], issues)

    def test_rejects_missing_canonical_requirement_mapping(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_packet(root)
            traceability = root / ".ai-sdlc" / "traceability.yaml"
            text = traceability.read_text(encoding="utf-8")
            traceability.write_text(
                text.replace("  FR-001:\n", "  FR-002:\n", 1),
                encoding="utf-8",
            )
            issues = module.validate_traceability(root)

        self.assertIn(
            "canonical-id-set-mismatch",
            {issue.code for issue in issues},
        )

    def test_rejects_dangling_task_reference(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_packet(root)
            traceability = root / ".ai-sdlc" / "traceability.yaml"
            text = traceability.read_text(encoding="utf-8")
            traceability.write_text(
                text.replace("[T001]", "[T999]", 1),
                encoding="utf-8",
            )
            issues = module.validate_traceability(root)

        self.assertIn(
            "dangling-traceability-reference",
            {issue.code for issue in issues},
        )

    def test_rejects_duplicate_task_definition(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_packet(root)
            tasks = root / "specs" / "001-walking-skeleton" / "tasks.md"
            tasks.write_text(
                tasks.read_text(encoding="utf-8")
                + "- [ ] **T001 — GREEN: Duplicate**\n",
                encoding="utf-8",
            )
            issues = module.validate_traceability(root)

        self.assertIn(
            "duplicate-canonical-id",
            {issue.code for issue in issues},
        )

    def test_rejects_scenario_task_mapping_that_is_not_reciprocal(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_packet(root)
            traceability = root / ".ai-sdlc" / "traceability.yaml"
            text = traceability.read_text(encoding="utf-8")
            traceability.write_text(
                text.replace(
                    "    baseline_requirements: [FR-001, NFR-001, QUALITY-OPS-001]\n"
                    "    tasks: [T001]\n",
                    "    baseline_requirements: [FR-001, NFR-001, QUALITY-OPS-001]\n"
                    "    tasks: []\n",
                ),
                encoding="utf-8",
            )
            issues = module.validate_traceability(root)

        self.assertIn(
            "asymmetric-traceability",
            {issue.code for issue in issues},
        )

    def test_rejects_requirement_scenario_mapping_that_is_not_reciprocal(
        self,
    ) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_minimal_packet(root)
            traceability = root / ".ai-sdlc" / "traceability.yaml"
            text = traceability.read_text(encoding="utf-8")
            traceability.write_text(
                text.replace(
                    "    active_scenarios: [AS-001]\n",
                    "    active_scenarios: []\n",
                    1,
                ),
                encoding="utf-8",
            )
            issues = module.validate_traceability(root)

        self.assertIn(
            "asymmetric-traceability",
            {issue.code for issue in issues},
        )


if __name__ == "__main__":
    unittest.main()
