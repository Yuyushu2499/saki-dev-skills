from __future__ import annotations

import importlib.util
import inspect
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
AGENTS_DIR = REPO_ROOT / "agents"
EXPECTED_SKILLS = {
    "saki-explore",
    "saki-plan",
    "saki-delegate",
    "saki-code-review",
    "saki-govern",
    "saki-bug-fix",
    "saki-docs",
    "saki-ship",
    "saki-comment",
}
EXPECTED_AGENTS = {
    "saki-explorer",
    "saki-reviewer",
    "saki-coder",
}
ALLOWED_PLUGIN_FIELDS = {
    "name",
    "displayName",
    "version",
    "description",
    "logo",
    "suggestedPrompts",
    "author",
    "homepage",
    "repository",
    "disabled",
}
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


class CollectionStructureTest(unittest.TestCase):
    def test_expected_skills_exist_with_matching_frontmatter(self) -> None:
        actual = {
            p.name
            for p in SKILLS_DIR.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        }
        self.assertEqual(actual, EXPECTED_SKILLS)
        for name in EXPECTED_SKILLS:
            skill_md = SKILLS_DIR / name / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f"Missing {skill_md}")
            text = skill_md.read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", text)

    def test_antigravity_plugin_manifest_agents_and_hooks(self) -> None:
        manifest_path = REPO_ROOT / "plugin.json"
        self.assertTrue(manifest_path.is_file(), "Missing plugin.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest.get("name"), "saki-dev-skills")
        self.assertTrue(manifest.get("description"))
        unknown = set(manifest.keys()) - ALLOWED_PLUGIN_FIELDS
        self.assertEqual(unknown, set(), f"Unknown plugin.json fields: {unknown}")
        if manifest.get("logo"):
            self.assertTrue((REPO_ROOT / manifest["logo"]).is_file(), f"Missing plugin logo: {manifest['logo']}")

        actual_agents = {p.stem for p in AGENTS_DIR.glob("*.md")}
        self.assertEqual(actual_agents, EXPECTED_AGENTS)
        for name in EXPECTED_AGENTS:
            agent_text = (AGENTS_DIR / f"{name}.md").read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", agent_text)
            self.assertIn("subagent: true", agent_text)
            self.assertIn("inheritMcp: false", agent_text)
            self.assertIn("tools:", agent_text)
            if name in ("saki-explorer", "saki-reviewer"):
                self.assertNotIn("edit_file", agent_text.split("---", 2)[1])
                self.assertNotIn("write_file", agent_text.split("---", 2)[1])

        hooks_path = REPO_ROOT / "hooks.json"
        self.assertTrue(hooks_path.is_file(), "Missing hooks.json")
        hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
        self.assertIn("saki-do-not-edit-guard", hooks)
        self.assertTrue((REPO_ROOT / "hooks" / "guard_do_not_edit.py").is_file())

        rules_path = REPO_ROOT / "rules" / "AGENTS.md"
        self.assertTrue(rules_path.is_file(), "Missing rules/AGENTS.md")
        rules_text = rules_path.read_text(encoding="utf-8")
        self.assertFalse(rules_text.lstrip().startswith("---"), "Plugin rules/AGENTS.md must not have frontmatter")
        self.assertLess(rules_path.stat().st_size, 24_000, "rules/AGENTS.md exceeds 24 KB Antigravity limit")

    def test_root_readmes_mention_all_skills_and_have_valid_local_links(self) -> None:
        for readme_name in ("README.md", "README.zh-CN.md"):
            readme = REPO_ROOT / readme_name
            self.assertTrue(readme.is_file(), f"Missing {readme_name}")
            content = readme.read_text(encoding="utf-8")
            for name in EXPECTED_SKILLS:
                self.assertIn(name, content, f"{readme_name} missing {name}")
            for match in MD_LINK_RE.finditer(content):
                target = match.group(1).strip()
                if target.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                clean = target.split("#", 1)[0]
                resolved = (REPO_ROOT / clean).resolve()
                self.assertTrue(resolved.exists(), f"Broken link in {readme_name}: {target}")

    def test_shared_entrypoint_discovery_stays_identical(self) -> None:
        """各 Skill 独立安装所以各自带一份副本；这里防止改了一边忘了另一边。"""
        sources = {}
        for name, rel in (
            ("repo_map", "saki-explore/scripts/repo_map.py"),
            ("audit_repo", "saki-govern/scripts/audit_repo.py"),
        ):
            spec = importlib.util.spec_from_file_location(f"shared_{name}", SKILLS_DIR / rel)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sources[name] = module
        left, right = sources["repo_map"], sources["audit_repo"]
        for func in ("_prioritized_package_scripts", "_collect_just_recipes", "_collect_ci_run_steps"):
            self.assertEqual(
                inspect.getsource(getattr(left, func)),
                inspect.getsource(getattr(right, func)),
                f"{func} differs between repo_map.py and audit_repo.py",
            )
        for const in ("PRIORITY_SCRIPT_HINTS", "CI_RUN_KEY_RE", "JUST_RECIPE_RE"):
            self.assertEqual(getattr(left, const), getattr(right, const), const)

    def test_shared_dev_profile_parser_stays_identical_and_reads_gemini_md(self) -> None:
        modules = {}
        for name, rel in (
            ("repo_map", "saki-explore/scripts/repo_map.py"),
            ("review_helper", "saki-code-review/scripts/review_helper.py"),
            ("audit_repo", "saki-govern/scripts/audit_repo.py"),
        ):
            spec = importlib.util.spec_from_file_location(f"profile_{name}", SKILLS_DIR / rel)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules[name] = module
        reference = modules["audit_repo"]
        for name, module in modules.items():
            self.assertEqual(
                inspect.getsource(module._load_dev_profile),
                inspect.getsource(reference._load_dev_profile),
                f"_load_dev_profile differs in {name}",
            )
            for const in (
                "DEV_PROFILE_FILES",
                "DEV_PROFILE_KEYS",
                "DEV_PROFILE_LABELS",
                "DEV_PROFILE_GLOB_KEYS",
                "DEV_PROFILE_HEADING_RE",
                "DEV_PROFILE_ITEM_RE",
                "DEV_PROFILE_CODE_RE",
            ):
                self.assertEqual(getattr(module, const), getattr(reference, const), f"{const} differs in {name}")
        self.assertEqual(
            inspect.getsource(modules["review_helper"]._matches_any),
            inspect.getsource(reference._matches_any),
        )
        self.assertIn("GEMINI.md", reference.DEV_PROFILE_FILES)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "GEMINI.md").write_text(
                "# Project\n\n## Dev profile (saki-dev)\n\n- quick-test: `pytest -q`\n- do-not-edit: `vendor/`\n",
                encoding="utf-8",
            )
            profile = reference._load_dev_profile(root)
            self.assertIsNotNone(profile)
            assert profile is not None
            self.assertEqual(profile["source"], "GEMINI.md:3")
            self.assertEqual(profile["quick_test"], ["pytest -q"])
            self.assertEqual(profile["do_not_edit"], ["vendor/"])

    def test_shared_preferences_script_stays_identical(self) -> None:
        """saki-explore 与 saki-plan 读写同一份个人偏好文件，脚本必须逐字一致。"""
        copies = [SKILLS_DIR / name / "scripts" / "preferences.py" for name in ("saki-explore", "saki-plan")]
        self.assertEqual(copies[0].read_bytes(), copies[1].read_bytes(), "preferences.py differs between saki-explore and saki-plan")

    def test_cli_entrypoints_respond_to_help(self) -> None:
        scripts = [
            REPO_ROOT / "scripts" / "verify_repo.py",
            SKILLS_DIR / "saki-explore" / "scripts" / "repo_map.py",
            SKILLS_DIR / "saki-explore" / "scripts" / "preferences.py",
            SKILLS_DIR / "saki-plan" / "scripts" / "preferences.py",
            SKILLS_DIR / "saki-delegate" / "scripts" / "delegate.py",
            SKILLS_DIR / "saki-code-review" / "scripts" / "review_helper.py",
            SKILLS_DIR / "saki-govern" / "scripts" / "audit_repo.py",
            SKILLS_DIR / "saki-docs" / "scripts" / "doc_helper.py",
            SKILLS_DIR / "saki-docs" / "scripts" / "excalidraw_icons.py",
            SKILLS_DIR / "saki-ship" / "scripts" / "ship_helper.py",
            SKILLS_DIR / "saki-comment" / "scripts" / "comment_helper.py",
        ]
        for script in scripts:
            proc = subprocess.run(
                [sys.executable, str(script), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"{script} --help failed: {proc.stderr}")


if __name__ == "__main__":
    unittest.main()
