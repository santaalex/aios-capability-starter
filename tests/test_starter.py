from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aios_capability_starter import (  # noqa: E402
    CapabilityPackError,
    TaskBundleError,
    build_pack,
    init_pack_source,
    load_result,
    load_task,
    validate_result,
    validate_task,
    verify_pack,
)


class StarterTests(unittest.TestCase):
    def test_template_initializes_and_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            shutil.copytree(ROOT / "template", repo / "template")
            initialized = init_pack_source(
                "sample-capability",
                display_name="示例工程能力",
                repo_root=repo,
            )
            result = build_pack(
                Path(initialized["source_manifest"]),
                repo_root=repo,
            )

            self.assertEqual(
                "sample-capability", verify_pack(Path(result["path"]))["capability_id"]
            )
            self.assertEqual(9, result["components"])

    def test_invalid_json_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            shutil.copytree(ROOT / "template", repo / "template")
            initialized = init_pack_source(
                "invalid-demo",
                display_name="错误示例",
                repo_root=repo,
            )
            source = Path(initialized["source_manifest"])
            (source.parent / "schemas" / "input.json").write_text(
                "[]\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                CapabilityPackError, "JSON component must contain an object"
            ):
                build_pack(source, repo_root=repo)

    def test_fictional_example_is_deterministic_and_matches_golden(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = ROOT / "examples" / "fictional-demo" / "capability.source.json"
            first = temporary / "first.zip"
            second = temporary / "second.zip"

            one = build_pack(source, repo_root=ROOT, output_path=first)
            two = build_pack(source, repo_root=ROOT, output_path=second)
            self.assertEqual(one["artifact_sha256"], two["artifact_sha256"])
            self.assertEqual(first.read_bytes(), second.read_bytes())

            golden = json.loads(
                (
                    ROOT / "examples" / "fictional-demo" / "golden" / "minimal.json"
                ).read_text(encoding="utf-8")
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "examples" / "fictional-demo" / "runtime" / "main.py"),
                ],
                input=json.dumps(golden["input"], ensure_ascii=False),
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(golden["expected"], json.loads(completed.stdout))

    def test_public_task_bundle_examples_validate(self) -> None:
        capability_task = load_task(
            ROOT
            / "examples"
            / "task-bundles"
            / "capability-development"
            / "task.json"
        )
        deployment_task = load_task(
            ROOT
            / "examples"
            / "task-bundles"
            / "device-deployment-pack-only"
            / "task.json"
        )
        template_task = load_task(ROOT / "task-template" / "task.json")
        capability_result = load_result(
            ROOT
            / "examples"
            / "task-bundles"
            / "capability-development"
            / "result.example.json",
            task=capability_task,
        )

        self.assertEqual(
            "CapabilityDevelopment", validate_task(capability_task)["kind"]
        )
        self.assertEqual("pack-only", validate_task(deployment_task)["impact"])
        self.assertEqual("CapabilityDevelopment", validate_task(template_task)["kind"])
        self.assertEqual("NEEDS_ATTENTION", capability_result["status"]["outcome"])

    def test_task_driven_cli_initializes_builds_and_validates_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            shutil.copytree(ROOT / "template", repo / "template")
            task_path = repo / "task.json"
            task_path.write_text(
                json.dumps(
                    _capability_task(
                        capability_id="portable-batch-summary",
                        display_name="便携批次汇总",
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            tool = ROOT / "tools" / "aios-capability"

            initialized = subprocess.run(
                [
                    sys.executable,
                    str(tool),
                    "init",
                    "--task",
                    str(task_path),
                    "--repo-root",
                    str(repo),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            initialized_result = json.loads(initialized.stdout)
            self.assertEqual(
                "develop-portable-batch-summary", initialized_result["task_id"]
            )

            built = subprocess.run(
                [
                    sys.executable,
                    str(tool),
                    "build",
                    "--task",
                    str(task_path),
                    "--repo-root",
                    str(repo),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            built_result = json.loads(built.stdout)
            result_path = Path(built_result["task_result"])
            task = load_task(task_path)
            result = load_result(result_path, task=task)

            self.assertEqual("NEEDS_ATTENTION", result["status"]["outcome"])
            self.assertEqual(1, result["metadata"]["observed_generation"])
            self.assertEqual(
                built_result["artifact_sha256"],
                result["delivery"]["artifacts"][0]["sha256"],
            )
            self.assertEqual(
                ["task-contract", "pack-build", "pack-verify"],
                [
                    check["name"]
                    for check in result["delivery"]["validation"][
                        "performed_checks"
                    ]
                ],
            )
            self.assertEqual(
                [
                    "task-contract",
                    "pack-build",
                    "pack-verify",
                    "one-minimal-golden",
                ],
                result["delivery"]["validation"]["declared_required_checks"],
            )

            validated = subprocess.run(
                [
                    sys.executable,
                    str(tool),
                    "result-validate",
                    str(result_path),
                    "--task",
                    str(task_path),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual("VALID", json.loads(validated.stdout)["status"])

    def test_result_generation_must_match_task(self) -> None:
        task = _capability_task(
            capability_id="generation-check",
            display_name="代次检查",
        )
        result = {
            "api_version": "task-result.aios.fuinno.cn/v0.1alpha1",
            "kind": "CapabilityDevelopmentResult",
            "metadata": {
                "task_id": "develop-generation-check",
                "observed_generation": 2,
                "completed_at": "2026-09-03T00:00:00Z",
            },
            "status": {
                "outcome": "COMPLETED",
                "summary": "Built.",
                "conditions": [
                    {
                        "type": "PackBuilt",
                        "status": "True",
                        "reason": "Completed",
                        "message": "Built.",
                    }
                ],
            },
            "delivery": {
                "capability": {
                    "capability_id": "generation-check",
                    "version": "0.1.0",
                    "display_name": "代次检查",
                },
                "artifacts": [],
                "validation": {
                    "performed_checks": [
                        {"name": "pack-build", "status": "PASS"}
                    ],
                    "declared_required_checks": [],
                },
                "adapter_required": False,
                "known_limitations": [],
            },
        }

        with self.assertRaisesRegex(TaskBundleError, "observed_generation"):
            validate_result(result, task=task)

        result["metadata"]["observed_generation"] = 1
        result["delivery"]["validation"]["declared_required_checks"] = [
            "required-golden"
        ]
        with self.assertRaisesRegex(TaskBundleError, "required-golden"):
            validate_result(result, task=task)

        result["status"]["outcome"] = "NEEDS_ATTENTION"
        with self.assertRaisesRegex(TaskBundleError, "task acceptance"):
            validate_result(result, task=task)

    def test_task_mismatch_is_rejected_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            shutil.copytree(ROOT / "template", repo / "template")
            initialized = init_pack_source(
                "actual-capability",
                display_name="实际能力",
                repo_root=repo,
            )
            task_path = repo / "task.json"
            task_path.write_text(
                json.dumps(
                    _capability_task(
                        capability_id="expected-capability",
                        display_name="预期能力",
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "aios-capability"),
                    "build",
                    initialized["source_manifest"],
                    "--task",
                    str(task_path),
                    "--repo-root",
                    str(repo),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("does not match task", completed.stderr)
            self.assertFalse((repo / "dist").exists())


def _capability_task(*, capability_id: str, display_name: str) -> dict[str, object]:
    return {
        "api_version": "task.aios.fuinno.cn/v0.1alpha1",
        "kind": "CapabilityDevelopment",
        "metadata": {
            "task_id": f"develop-{capability_id}",
            "generation": 1,
            "created_at": "2026-09-03T00:00:00Z",
        },
        "spec": {
            "objective": f"开发{display_name}并交付标准候选包。",
            "non_goals": ["不签名、发布或部署。"],
            "impact": "pack-only",
            "target": {
                "environment": "development",
                "repository": "https://github.com/santaalex/aios-capability-starter",
            },
            "capability": {
                "capability_id": capability_id,
                "version": "0.1.0",
                "display_name": display_name,
                "source_manifest": (
                    f"capabilities/{capability_id}/0.1.0/capability.source.json"
                ),
                "adapter_required": False,
                "known_limitations": ["仅使用脱敏最小样本。"],
            },
            "artifacts": [],
            "human_actions": [],
            "acceptance": {
                "required_checks": [
                    "task-contract",
                    "pack-build",
                    "pack-verify",
                    "one-minimal-golden",
                ],
                "deliverables": ["capability-pack-zip", "task-result-json"],
                "forbidden_changes": ["control-plane", "customer-device"],
            },
            "secrets_policy": {
                "bundle_must_not_contain": [
                    "customer-files",
                    "api-keys",
                    "activation-codes",
                    "device-credentials",
                    "signing-keys",
                ]
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
