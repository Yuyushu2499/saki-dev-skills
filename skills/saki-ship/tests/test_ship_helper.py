from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ship_helper.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("ship_helper", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(cwd: Path, *args: str) -> None:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")


def _init_repo_with_remote(base: Path) -> Path:
    remote = base / "remote.git"
    repo = base / "repo"
    remote.mkdir()
    repo.mkdir()
    _git(remote, "init", "--bare")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "remote", "add", "origin", str(remote))
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    _git(repo, "push", "-u", "origin", "main")
    return repo


class ShipHelperTest(unittest.TestCase):
    def test_protected_main_branch_blocks_auto_ship(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = _init_repo_with_remote(Path(tmp))
            (repo / "app.py").write_text("x = 1\n", encoding="utf-8")
            report = mod.inspect_ship_status(repo)
            self.assertEqual(report["status"], "OK")
            self.assertTrue(report["is_protected_branch"])
            self.assertFalse(report["can_auto_ship"])
            self.assertTrue(any("保护分支" in b for b in report["blockers"]))

    def test_dev_branch_clean_changes_allows_auto_ship(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = _init_repo_with_remote(Path(tmp))
            _git(repo, "checkout", "-b", "dev")
            (repo / "feature.py").write_text("def hi(): return 1\n", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--workspace", str(repo), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertFalse(report["is_protected_branch"])
            self.assertTrue(report["can_auto_ship"])
            self.assertEqual(report["recommended_push_command"], "git push -u origin dev")

    def test_sensitive_env_file_blocks_auto_ship_but_env_example_allowed(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = _init_repo_with_remote(Path(tmp))
            _git(repo, "checkout", "-b", "dev")
            (repo / ".env.example").write_text("TOKEN=\n", encoding="utf-8")
            ok_report = mod.inspect_ship_status(repo)
            self.assertEqual(ok_report["sensitive_warnings"], [])
            self.assertTrue(ok_report["can_auto_ship"])

            (repo / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
            bad_report = mod.inspect_ship_status(repo)
            self.assertIn(".env", bad_report["sensitive_warnings"])
            self.assertFalse(bad_report["can_auto_ship"])


if __name__ == "__main__":
    unittest.main()
