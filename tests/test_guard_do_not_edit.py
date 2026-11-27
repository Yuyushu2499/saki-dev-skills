from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_SCRIPT = REPO_ROOT / "hooks" / "guard_do_not_edit.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("guard_do_not_edit", GUARD_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GuardDoNotEditTest(unittest.TestCase):
    def _run_hook(self, payload: dict) -> dict:
        proc = subprocess.run(
            [sys.executable, str(GUARD_SCRIPT)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_denies_edit_matching_agents_md_do_not_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text(
                "# Rules\n\n## 开发约定（saki-dev）\n\n- 禁改：`vendor/`、`src/generated/**`\n",
                encoding="utf-8",
            )
            blocked = self._run_hook(
                {
                    "toolCall": {"name": "edit_file", "args": {"Path": str(root / "vendor" / "lib.py")}},
                    "workspacePaths": [str(root)],
                    "cwd": str(root),
                }
            )
            self.assertEqual(blocked["decision"], "deny")
            self.assertIn("vendor/lib.py", blocked["reason"])

            allowed = self._run_hook(
                {
                    "toolCall": {"name": "edit_file", "args": {"Path": str(root / "src" / "app.py")}},
                    "workspacePaths": [str(root)],
                    "cwd": str(root),
                }
            )
            self.assertEqual(allowed["decision"], "allow")

    def test_supports_gemini_md_dev_profile_and_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".git").mkdir()
            (root / "GEMINI.md").write_text(
                "# Rules\n\n## Dev profile (saki-dev)\n\n- do-not-edit: `dist/**`\n",
                encoding="utf-8",
            )
            blocked = self._run_hook(
                {
                    "toolCall": {"name": "write_file", "args": {"Path": "dist/bundle.js"}},
                    "workspacePaths": [str(root)],
                    "cwd": str(root),
                }
            )
            self.assertEqual(blocked["decision"], "deny")
            self.assertIn("GEMINI.md", blocked["reason"])

    def test_ignores_old_oil_dev_heading_and_fenced_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text(
                "```markdown\n## 开发约定（saki-dev）\n- 禁改：`vendor/`\n```\n\n"
                "## 开发约定（oil-dev）\n- 禁改：`vendor/`\n",
                encoding="utf-8",
            )
            res = self._run_hook(
                {
                    "toolCall": {"name": "edit_file", "args": {"Path": str(root / "vendor" / "x.py")}},
                    "workspacePaths": [str(root)],
                    "cwd": str(root),
                }
            )
            self.assertEqual(res["decision"], "allow")

    def test_fails_open_when_profile_missing_or_payload_malformed(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(GUARD_SCRIPT)],
            input="{not-json",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
