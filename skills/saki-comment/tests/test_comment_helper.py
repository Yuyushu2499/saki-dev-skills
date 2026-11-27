from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "comment_helper.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("comment_helper", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CommentHelperTest(unittest.TestCase):
    def test_python_detects_missing_docstring_long_core_fn_and_suspicious_comments(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = "\n".join(
                [
                    "# @author someone",
                    "# ============================",
                    "# TODO",
                    "# def legacy_a():",
                    "#     return 1",
                    "# if old_flag:",
                    "#     print('dead')",
                    "",
                    "def undocumented_core(x):",
                    *[f"    x += {i}" for i in range(1, 22)],
                    "    return x",
                    "",
                    "def documented_fn(x):",
                    '    """已注释的函数。"""',
                    "    return x + 1",
                ]
            )
            (root / "core.py").write_text(code + "\n", encoding="utf-8")

            report = mod.scan_comments(root)
            self.assertEqual(report["status"], "OK")
            self.assertEqual(report["files_with_findings"], 1)
            f = report["files"][0]
            missing_names = [m["name"] for m in f["missing_docstrings"]]
            self.assertIn("undocumented_core", missing_names)
            self.assertNotIn("documented_fn", missing_names)
            core_names = [c["name"] for c in f["core_functions_without_inline_comments"]]
            self.assertIn("undocumented_core", core_names)
            kinds = {s["kind"] for s in f["suspicious_comments"]}
            self.assertIn("author_or_date_boilerplate", kinds)
            self.assertIn("divider_banner", kinds)
            self.assertIn("bare_todo", kinds)
            self.assertIn("commented_out_code", kinds)

    def test_typescript_detects_undocumented_and_documented_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "service.ts").write_text(
                "/** 已注释的导出函数 */\nexport function okFn() { return 1; }\n\nexport function bareFn() { return 2; }\n",
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--workspace", str(root), "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            names = [m["name"] for m in report["files"][0]["missing_docstrings"]]
            self.assertIn("bareFn", names)
            self.assertNotIn("okFn", names)


if __name__ == "__main__":
    unittest.main()
