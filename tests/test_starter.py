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
    build_pack,
    init_pack_source,
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


if __name__ == "__main__":
    unittest.main()
