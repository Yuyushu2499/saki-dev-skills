from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "doc_helper.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("doc_helper", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> None:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")


def _init_repo(root: Path) -> None:
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "Test")
    _git(root, "config", "user.email", "test@example.com")


class DocHelperTest(unittest.TestCase):
    def test_inventory_detects_docs_undocumented_modules_and_api_hints(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# Demo\n\n介绍 `src/core` 模块。\n", encoding="utf-8")
            (root / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
            (root / "src" / "core").mkdir(parents=True)
            (root / "src" / "core" / "engine.py").write_text("def run(): pass\n", encoding="utf-8")
            (root / "src" / "billing").mkdir(parents=True)
            (root / "src" / "billing" / "api.py").write_text("def charge(): pass\n", encoding="utf-8")

            report = mod.collect_inventory(root)
            self.assertEqual(report["status"], "OK")
            self.assertTrue(report["docs"]["recommended_present"]["readme"])
            self.assertFalse(report["docs"]["recommended_present"]["architecture"])
            self.assertIn("src/billing", report["undocumented_modules"])
            self.assertNotIn("src/core", report["undocumented_modules"])
            self.assertIn("src/billing/api.py", report["api_schema_candidates"])

    def test_impact_finds_doc_references_for_deleted_and_modified_files(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "docs").mkdir()
            (root / "docs" / "architecture.md").write_text(
                "# 架构\n\n导出入口在 `src/export/old_runner.py`。\n", encoding="utf-8"
            )
            (root / "src" / "export").mkdir(parents=True)
            (root / "src" / "export" / "old_runner.py").write_text("print('hi')\n", encoding="utf-8")
            _git(root, "add", ".")
            _git(root, "commit", "-m", "init")

            # 重命名文件
            (root / "src" / "export" / "old_runner.py").rename(root / "src" / "export" / "new_runner.py")
            _git(root, "add", "-A")

            report = mod.collect_impact(root)
            self.assertEqual(report["status"], "OK")
            self.assertTrue(report["likely_doc_sync_needed"])
            self.assertTrue(any("old_runner.py" in item for item in report["deleted_or_renamed"]))
            self.assertEqual(len(report["doc_references"]), 1)
            self.assertEqual(report["doc_references"][0]["doc"], "docs/architecture.md")
            self.assertEqual(report["doc_references"][0]["matches"][0]["line"], 3)

    def test_impact_clean_working_tree_falls_back_to_branch_commits_and_cli_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "README.md").write_text("# App\n", encoding="utf-8")
            (root / "app.py").write_text("x = 1\n", encoding="utf-8")
            _git(root, "add", ".")
            _git(root, "commit", "-m", "init")

            _git(root, "checkout", "-b", "feat/config")
            (root / "config.py").write_text("TIMEOUT = 10\n", encoding="utf-8")
            _git(root, "add", ".")
            _git(root, "commit", "-m", "add config")

            proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "impact", "--workspace", str(root), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["diff_source"], "committed_since:main")
            self.assertIn("config.py", payload["api_or_schema_changed"])
            self.assertTrue(payload["likely_doc_sync_needed"])

    def test_impact_internal_only_test_edit_does_not_flag_sync(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_repo(root)
            (root / "tests").mkdir()
            (root / "tests" / "test_demo.py").write_text("assert True\n", encoding="utf-8")
            _git(root, "add", ".")
            _git(root, "commit", "-m", "init")

            (root / "tests" / "test_demo.py").write_text("assert 1 + 1 == 2\n", encoding="utf-8")
            report = mod.collect_impact(root)
            self.assertEqual(report["status"], "OK")
            self.assertFalse(report["likely_doc_sync_needed"])


if __name__ == "__main__":
    unittest.main()
