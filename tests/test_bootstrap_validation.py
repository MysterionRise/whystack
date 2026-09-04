import contextlib
import hashlib
import importlib.util
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BootstrapValidatorPresenceTests(unittest.TestCase):
    def test_python_validator_exists(self) -> None:
        validator = PROJECT_ROOT / "scripts" / "verify_bootstrap.py"
        self.assertTrue(
            validator.is_file(),
            "scripts/verify_bootstrap.py must exist before the packet can be copied",
        )

    def test_validator_exposes_packet_validation_api(self) -> None:
        validator = PROJECT_ROOT / "scripts" / "verify_bootstrap.py"
        spec = importlib.util.spec_from_file_location("verify_bootstrap", validator)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertTrue(hasattr(module, "validate_packet"))
        self.assertTrue(hasattr(module, "format_issues"))
        self.assertTrue(hasattr(module, "main"))

    def test_shell_entrypoint_runs_the_python_validator_with_uv(self) -> None:
        entrypoint = PROJECT_ROOT / "scripts" / "verify-bootstrap.sh"
        self.assertTrue(entrypoint.is_file())
        text = entrypoint.read_text(encoding="utf-8")
        self.assertIn("uv run", text)
        self.assertIn("scripts/verify_bootstrap.py", text)

    def test_traceability_validator_exists(self) -> None:
        validator = PROJECT_ROOT / "scripts" / "verify_traceability.py"
        self.assertTrue(
            validator.is_file(),
            "scripts/verify_traceability.py must verify requirement coverage",
        )

    def test_shell_entrypoint_runs_traceability_validation(self) -> None:
        entrypoint = PROJECT_ROOT / "scripts" / "verify-bootstrap.sh"
        text = entrypoint.read_text(encoding="utf-8")
        self.assertIn("scripts/verify_traceability.py", text)

    def test_bootstrap_verifiers_share_the_pinned_yaml_version(self) -> None:
        entrypoint = (
            PROJECT_ROOT / "scripts" / "verify-bootstrap.sh"
        ).read_text(encoding="utf-8")
        validator = (
            PROJECT_ROOT / "scripts" / "verify_bootstrap.py"
        ).read_text(encoding="utf-8")
        traceability = (
            PROJECT_ROOT / "scripts" / "verify_traceability.py"
        ).read_text(encoding="utf-8")

        self.assertIn("--with pyyaml==6.0.3", entrypoint)
        self.assertIn('"PyYAML==6.0.3"', validator)
        self.assertIn('"PyYAML==6.0.3"', traceability)

    def test_ci_runs_check_with_the_pinned_node_action(self) -> None:
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "bootstrap-validation.yml"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "actions/setup-node@"
            "48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e",
            workflow,
        )
        self.assertIn('node-version: "24.18.0"', workflow)
        self.assertIn("run: make check", workflow)


class BootstrapValidatorBehaviorTests(unittest.TestCase):
    def _load_validator(self):
        validator = PROJECT_ROOT / "scripts" / "verify_bootstrap.py"
        spec = importlib.util.spec_from_file_location("verify_bootstrap", validator)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_reports_missing_required_file(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            issues = module.validate_packet(
                root,
                required_paths=("README.md",),
                authored_roots=(),
            )

        self.assertIn("missing-required-path", {issue.code for issue in issues})

    def test_rejects_placeholders_and_machine_specific_paths(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "plan.md").write_text(
                "TBD: copy from /Users/example/private/source\n",
                encoding="utf-8",
            )
            issues = module.validate_packet(
                root,
                required_paths=(),
                authored_roots=("docs",),
            )

        codes = {issue.code for issue in issues}
        self.assertIn("forbidden-placeholder", codes)
        self.assertIn("machine-specific-path", codes)

    def test_rejects_high_confidence_secret_material(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            (docs / "leak.txt").write_text(
                "OPENROUTER_API_KEY=" + "sk-" + ("a" * 32) + "\n",
                encoding="utf-8",
            )

            issues = module.validate_no_secrets(
                root,
                authored_roots=("docs",),
            )

        self.assertIn("suspected-secret", {issue.code for issue in issues})

    def test_rejects_invalid_json_and_jsonl(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evals = root / "evals"
            evals.mkdir()
            (evals / "schema.json").write_text("{", encoding="utf-8")
            (evals / "cases.jsonl").write_text(
                json.dumps({"id": "valid"}) + "\nnot-json\n",
                encoding="utf-8",
            )
            issues = module.validate_packet(
                root,
                required_paths=(),
                authored_roots=("evals",),
            )

        codes = {issue.code for issue in issues}
        self.assertIn("invalid-json", codes)
        self.assertIn("invalid-jsonl", codes)

    def test_rejects_invalid_yaml(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            specs = root / "specs"
            specs.mkdir()
            (specs / "contract.yaml").write_text(
                "openapi: [unterminated\n",
                encoding="utf-8",
            )
            issues = module.validate_packet(
                root,
                required_paths=(),
                authored_roots=("specs",),
            )

        self.assertIn("invalid-yaml", {issue.code for issue in issues})

    def test_live_packet_has_executable_sdlc_wiring(self) -> None:
        module = self._load_validator()

        issues = module.validate_sdlc_wiring(PROJECT_ROOT)

        self.assertEqual([], issues)

    def test_rejects_delivery_workflow_without_post_plan_checklist(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = (
                root
                / ".specify"
                / "workflows"
                / "ai-feature-delivery"
                / "workflow.yml"
            )
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                "steps:\n"
                "  - id: requirements-checklist\n"
                "    command: speckit.checklist\n"
                "  - id: plan\n"
                "    command: speckit.plan\n"
                "  - id: tasks\n"
                "    command: speckit.tasks\n",
                encoding="utf-8",
            )

            issues = module.validate_delivery_workflow_sequence(root)

        self.assertIn(
            "incomplete-workflow-checklists",
            {issue.code for issue in issues},
        )

    def test_rejects_t001_without_exact_verification_commands(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = root / "specs" / "001-walking-skeleton" / "tasks.md"
            tasks.parent.mkdir(parents=True)
            tasks.write_text(
                "- [ ] **T001 — Create locked workspace manifests**\n"
                "  - Verify: lockfile installation succeeds.\n"
                "\n"
                "- [ ] **T002 — RED: next task**\n",
                encoding="utf-8",
            )

            issues = module.validate_initial_task_commands(root)

        self.assertIn(
            "missing-exact-task-command",
            {issue.code for issue in issues},
        )

    def test_live_initial_batch_uses_locked_backend_project_commands(self) -> None:
        tasks = (
            PROJECT_ROOT
            / "specs"
            / "001-walking-skeleton"
            / "tasks.md"
        ).read_text(encoding="utf-8")
        required_commands = (
            (
                "uv lock --project services/backend --check "
                "--python 3.12.13 --managed-python"
            ),
            (
                "uv sync --project services/backend --locked "
                "--all-groups --no-install-project --python 3.12.13 "
                "--managed-python"
            ),
            (
                "uv run --project services/backend --no-sync pytest "
                "tests/e2e/test_compose_readiness.py"
            ),
        )
        for command in required_commands:
            self.assertIn(f"`{command}`", tasks)

    def test_make_gates_require_the_pinned_node_toolchain(self) -> None:
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")

        self.assertIn("NODE_VERSION := v24.18.0", makefile)
        self.assertIn("PNPM_VERSION := 11.17.0", makefile)
        for target in ("install", "check", "contracts-generate", "contracts-check"):
            declaration = next(
                line for line in makefile.splitlines() if line.startswith(f"{target}:")
            )
            self.assertIn("node-toolchain-check", declaration)

    def test_live_task_headings_use_required_stage_labels(self) -> None:
        tasks = (
            PROJECT_ROOT
            / "specs"
            / "001-walking-skeleton"
            / "tasks.md"
        ).read_text(encoding="utf-8")
        headings = re.findall(
            r"(?m)^- \[[ xX]\] \*\*T\d+ — (?P<label>[^*]+)\*\*$",
            tasks,
        )
        self.assertTrue(headings)
        invalid = [
            heading
            for heading in headings
            if re.match(r"^(?:RED|GREEN|REFACTOR|VERIFY): ", heading) is None
        ]
        self.assertEqual([], invalid)

    def test_live_toolchain_pins_every_named_t001_tool(self) -> None:
        module = self._load_validator()
        lock = module._load_yaml(
            PROJECT_ROOT / ".ai-sdlc" / "toolchain.lock.yaml"
        )
        frontend = lock["implementation_bootstrap"]["frontend"][
            "direct_development_dependencies"
        ]
        backend = lock["implementation_bootstrap"]["backend"][
            "direct_development_dependencies"
        ]
        backend_runtime = lock["implementation_bootstrap"]["backend"][
            "direct_dependencies"
        ]
        backend_build = lock["implementation_bootstrap"]["backend"][
            "build_system"
        ]
        workspace = lock["implementation_bootstrap"]["workspace"][
            "direct_development_dependencies"
        ]
        expected_frontend = {
            "vitest",
            "@playwright/test",
            "@axe-core/playwright",
            "eslint",
            "eslint-config-next",
            "typescript",
        }
        expected_backend = {
            "hypothesis",
            "pytest",
            "pytest-asyncio",
            "ruff",
        }
        expected_workspace = {"pyright"}
        self.assertTrue(expected_frontend <= set(frontend))
        self.assertTrue(expected_backend <= set(backend))
        self.assertTrue(expected_workspace <= set(workspace))
        self.assertEqual("9.39.2", frontend["eslint"])
        self.assertEqual("6.160.0", backend["hypothesis"])
        self.assertEqual("49.0.0", backend_runtime["cryptography"])
        self.assertEqual("6.0.3", backend_runtime["pyyaml"])
        self.assertEqual("2.0.51", backend_runtime["sqlalchemy[asyncio]"])
        self.assertEqual("2025.0.1", backend_runtime["uuid6"])
        self.assertEqual("0.11.16", backend_build["uv_build"])

    def test_rejects_unclassified_shipped_bmad_support_files(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            governance = root / ".ai-sdlc"
            scripts = root / "_bmad" / "scripts"
            custom = root / "_bmad" / "custom"
            governance.mkdir(parents=True)
            scripts.mkdir(parents=True)
            custom.mkdir(parents=True)
            (root / "_bmad" / "config.toml").write_text(
                "[core]\n",
                encoding="utf-8",
            )
            (custom / "config.toml").write_text("", encoding="utf-8")
            (custom / ".gitignore").write_text(
                "*.user.toml\n",
                encoding="utf-8",
            )
            (scripts / "resolve_config.py").write_text(
                "# upstream support script\n",
                encoding="utf-8",
            )
            (governance / "source-manifest.yaml").write_text(
                "framework_references:\n"
                "  - id: SRC-FRAMEWORK-001\n"
                "    vendored_paths:\n"
                "      - _bmad/core/\n",
                encoding="utf-8",
            )
            (root / "THIRD_PARTY_NOTICES.md").write_text(
                "Vendored locations: `_bmad/core/`\n",
                encoding="utf-8",
            )

            issues = module.validate_framework_provenance(root)

        self.assertIn(
            "unclassified-framework-file",
            {issue.code for issue in issues},
        )

    def test_cli_returns_nonzero_and_prints_issues_for_invalid_packet(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = module.main(["--root", directory])

        self.assertEqual(1, result)
        self.assertIn("missing-required-path", output.getvalue())

    def test_symlink_check_ignores_generated_dependency_directories(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.txt"
            target.write_text("target\n", encoding="utf-8")
            dependencies = root / "node_modules"
            dependencies.mkdir()
            (dependencies / "generated-link").symlink_to(target)
            (root / "authored-link").symlink_to(target)

            issues = module.validate_no_packet_symlinks(root)

        paths = {issue.path for issue in issues}
        self.assertIn("authored-link", paths)
        self.assertNotIn("node_modules/generated-link", paths)

    def test_rejects_eval_record_that_violates_json_schema(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evals = root / "evals"
            evals.mkdir()
            (evals / "dataset.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                        "required": ["id"],
                        "properties": {"id": {"type": "string"}},
                    }
                ),
                encoding="utf-8",
            )
            (evals / "seed-v0.jsonl").write_text("{}\n", encoding="utf-8")
            (evals / "attack-seed-v0.jsonl").write_text("", encoding="utf-8")

            issues = module.validate_eval_datasets(root)

        self.assertIn("eval-schema-violation", {issue.code for issue in issues})

    def test_rejects_duplicate_eval_ids_and_broken_evidence_quotes(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evals = root / "evals"
            fixture = root / "seed" / "sample-project"
            evals.mkdir(parents=True)
            fixture.mkdir(parents=True)
            (evals / "dataset.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                    }
                ),
                encoding="utf-8",
            )
            case = {
                "id": "duplicate",
                "expected": {
                    "required_evidence": [
                        {
                            "artifact_id": "source",
                            "path": "source.md",
                            "line_start": 1,
                            "line_end": 1,
                            "quote": "expected text",
                        }
                    ]
                },
            }
            encoded = json.dumps(case) + "\n"
            (evals / "seed-v0.jsonl").write_text(encoded, encoding="utf-8")
            (evals / "attack-seed-v0.jsonl").write_text(
                encoded,
                encoding="utf-8",
            )
            (fixture / "manifest.yaml").write_text(
                "artifacts:\n"
                "  - id: source\n"
                "    path: source.md\n",
                encoding="utf-8",
            )
            (fixture / "source.md").write_text(
                "different text\n",
                encoding="utf-8",
            )

            issues = module.validate_eval_datasets(root)

        codes = {issue.code for issue in issues}
        self.assertIn("duplicate-eval-id", codes)
        self.assertIn("evidence-quote-mismatch", codes)

    def test_accepts_exact_quote_excerpt_within_located_lines(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evals = root / "evals"
            fixture = root / "seed" / "sample-project"
            evals.mkdir(parents=True)
            fixture.mkdir(parents=True)
            (evals / "dataset.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                    }
                ),
                encoding="utf-8",
            )
            case = {
                "id": "excerpt",
                "expected": {
                    "required_evidence": [
                        {
                            "artifact_id": "source",
                            "path": "source.md",
                            "line_start": 1,
                            "line_end": 1,
                            "quote": "The production region must be in the EU.",
                        }
                    ]
                },
            }
            (evals / "seed-v0.jsonl").write_text(
                json.dumps(case) + "\n",
                encoding="utf-8",
            )
            (evals / "attack-seed-v0.jsonl").write_text("", encoding="utf-8")
            (fixture / "manifest.yaml").write_text(
                "artifacts:\n"
                "  - id: source\n"
                "    path: source.md\n",
                encoding="utf-8",
            )
            (fixture / "source.md").write_text(
                "1. The production region must be in the EU.\n",
                encoding="utf-8",
            )

            issues = module.validate_eval_datasets(root)

        self.assertNotIn(
            "evidence-quote-mismatch",
            {issue.code for issue in issues},
        )

    def test_rejects_semantically_inconsistent_eval_references(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evals = root / "evals"
            fixture = root / "seed" / "sample-project"
            evals.mkdir(parents=True)
            fixture.mkdir(parents=True)
            (evals / "dataset.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "object",
                    }
                ),
                encoding="utf-8",
            )
            case = {
                "id": "semantic-drift",
                "input": {
                    "options": [
                        {"id": "same", "label": "One"},
                        {"id": "same", "label": "Two"},
                    ],
                    "criteria": [{"id": "fit", "weight": 90}],
                    "constraints": [],
                    "history": [],
                },
                "expected": {
                    "outcome": "recommend",
                    "selected_option": "missing",
                    "required_constraint_results": [],
                    "required_memory_influences": [],
                    "must_ignore_memory": [],
                },
            }
            (evals / "seed-v0.jsonl").write_text(
                json.dumps(case) + "\n",
                encoding="utf-8",
            )
            (evals / "attack-seed-v0.jsonl").write_text("", encoding="utf-8")
            (fixture / "manifest.yaml").write_text(
                "artifacts: []\n",
                encoding="utf-8",
            )

            issues = module.validate_eval_datasets(root)

        codes = {issue.code for issue in issues}
        self.assertIn("duplicate-eval-option-id", codes)
        self.assertIn("invalid-eval-weight-total", codes)
        self.assertIn("unknown-selected-option", codes)

    def test_rejects_stale_inception_baseline_hash(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            governance = root / ".ai-sdlc"
            governance.mkdir()
            artifact = root / "artifact.md"
            artifact.write_text("current\n", encoding="utf-8")
            stale = hashlib.sha256(b"old\n").hexdigest()
            (governance / "inception-baseline.yaml").write_text(
                "artifacts:\n"
                "  - path: artifact.md\n"
                f"    sha256: {stale}\n",
                encoding="utf-8",
            )

            issues = module.validate_baseline_hashes(root)

        self.assertIn("baseline-hash-mismatch", {issue.code for issue in issues})

    def test_rejects_framework_version_drift(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            governance = root / ".ai-sdlc"
            bmad = root / "_bmad" / "_config"
            specify = root / ".specify" / "integrations"
            governance.mkdir(parents=True)
            bmad.mkdir(parents=True)
            specify.mkdir(parents=True)
            (governance / "toolchain.lock.yaml").write_text(
                "tools:\n"
                "  bmad_method:\n"
                "    version: '6.10.0'\n"
                "  bmad_tea:\n"
                "    version: '1.19.1'\n"
                "  github_spec_kit:\n"
                "    version: '0.14.2'\n",
                encoding="utf-8",
            )
            (bmad / "manifest.yaml").write_text(
                "installation:\n"
                "  version: 6.9.0\n"
                "modules:\n"
                "  - name: tea\n"
                "    version: v1.19.1\n",
                encoding="utf-8",
            )
            (specify / "speckit.manifest.json").write_text(
                json.dumps({"version": "0.14.2"}),
                encoding="utf-8",
            )

            issues = module.validate_framework_versions(root)

        self.assertIn("framework-version-drift", {issue.code for issue in issues})

    def test_rejects_invalid_openapi_and_ui_json_schema_contracts(self) -> None:
        module = self._load_validator()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            contracts = root / "specs" / "001-walking-skeleton" / "contracts"
            contracts.mkdir(parents=True)
            (contracts / "openapi.yaml").write_text(
                "openapi: 3.1.0\n"
                "info: []\n"
                "paths: {}\n",
                encoding="utf-8",
            )
            (contracts / "ui-envelope.schema.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "type": "not-a-json-schema-type",
                    }
                ),
                encoding="utf-8",
            )

            issues = module.validate_contract_schemas(root)

        codes = {issue.code for issue in issues}
        self.assertIn("invalid-openapi-contract", codes)
        self.assertIn("invalid-ui-json-schema", codes)

    def test_live_contract_has_profile_auth_and_discriminated_events(self) -> None:
        module = self._load_validator()

        issues = module.validate_contract_semantics(PROJECT_ROOT)

        self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()
