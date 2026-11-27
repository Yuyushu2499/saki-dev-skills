from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "delegate.py"
SPEC = importlib.util.spec_from_file_location("delegate_under_test", SCRIPT_PATH)
DELEGATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DELEGATE)
RUNNERS = ("claude", "workbuddy", "antigravity", "codex", "opencode", "dsh", "grok", "kimi", "cursor")

FAKE_CLI = r'''#!{python}
import json
import os
import sys
import time

runner = {runner!r}
args = sys.argv[1:]
if os.environ.get("FAKE_CALL_LOG"):
    with open(os.environ["FAKE_CALL_LOG"], "a", encoding="utf-8") as handle:
        handle.write(json.dumps({{"runner": runner, "argv": args}}) + "\n")
if "--version" in args:
    print("fake-" + runner + "-1.0")
    raise SystemExit(0)
if args == ["models"] or "--list-models" in args:
    if os.environ.get("FAKE_MODELS_FAIL") == "1":
        sys.stderr.write("models listing failed\n")
        raise SystemExit(2)
    if runner == "antigravity":
        sys.stderr.write("Fetching available models...\n")
        print("gemini-4-carbon-medium\tGemini 4 Carbon (Medium)")
        print("gemini-4-carbon-high\tGemini 4 Carbon (High)")
        raise SystemExit(0)
    if runner == "grok":
        print("Default model: grok-4.6\n\nAvailable models:\n  * grok-4.6 (default)\n  - grok-4.5")
        raise SystemExit(0)
    if runner == "opencode":
        print("anthropic/claude-sonnet-4-5\nopenai/gpt-5")
        raise SystemExit(0)
    if runner == "cursor":
        if os.environ.get("FAKE_CURSOR_NO_MODELS") == "1":
            print("No models available for this account.")
        else:
            print("Available models:\n  - gpt-5 (default)\n  - sonnet-4-thinking")
        raise SystemExit(0)
if runner == "dsh" and "--help" in args:
    if os.environ.get("FAKE_DSH_LEGACY") == "1":
        print("--json --session-id")
    else:
        print("--json --session-id --permission-mode --approval-policy")
    raise SystemExit(0)
stdin_text = sys.stdin.read()
record = os.environ.get("FAKE_RECORD")
if record:
    with open(record, "w", encoding="utf-8") as handle:
        json.dump({{
            "runner": runner,
            "argv": args,
            "stdin": stdin_text,
            "cwd": os.getcwd(),
            "permission": os.environ.get("OPENCODE_PERMISSION"),
            "dsh_mode": os.environ.get("DSH_PERMISSION_MODE"),
            "disable_background": os.environ.get("CODEBUDDY_CODE_DISABLE_BACKGROUND_TASKS"),
            "codebuddy_sandbox": os.environ.get("CODEBUDDY_IS_SANDBOX"),
        }}, handle)
if os.environ.get("FAKE_SLEEP"):
    time.sleep(float(os.environ["FAKE_SLEEP"]))
if os.environ.get("FAKE_FAIL") == "1":
    sys.stderr.write("fake failure\n")
    raise SystemExit(2)

session = None
for flag in ("--resume", "--conversation", "--session", "--session-id", "-S"):
    if flag in args:
        session = args[args.index(flag) + 1]
if runner == "codex" and "resume" in args:
    session = args[-2]
session = session or ("fake-" + runner + "-session")

if os.environ.get("FAKE_DSH_BAD_FINAL") == "1":
    print(json.dumps({{"type": "session", "sessionId": session}}))
    print(json.dumps({{"type": "final", "sessionId": session, "text": "", "reason": {{"kind": "error", "error": {{"message": "bad final"}}}}}}))
    raise SystemExit(0)

if os.environ.get("FAKE_CURSOR_BAD_SUBTYPE") == "1":
    print(json.dumps({{"type": "result", "subtype": "error_during_execution", "is_error": False, "result": "partial", "session_id": session}}))
    raise SystemExit(0)

if os.environ.get("FAKE_EMPTY") == "1":
    if runner in ("claude", "workbuddy", "cursor"):
        print(json.dumps({{"type": "result", "subtype": "success", "session_id": session, "result": "", "is_error": False}}))
    elif runner == "antigravity":
        print(json.dumps({{"conversation_id": session, "status": "SUCCESS", "response": ""}}))
    elif runner == "grok":
        print(json.dumps({{"text": "", "stopReason": "end_turn", "sessionId": session}}))
    elif runner == "kimi":
        print(json.dumps({{"type": "session.resume_hint", "session_id": session}}))
    elif runner == "codex":
        print(json.dumps({{"type": "thread.started", "thread_id": session}}))
    elif runner == "opencode":
        print(json.dumps({{"type": "init", "sessionID": session}}))
    elif runner == "dsh":
        print(json.dumps({{"type": "session", "sessionId": session}}))
        print(json.dumps({{"type": "status", "phase": "turn_end", "reason": {{"kind": "completed"}}}}))
        print(json.dumps({{"type": "final", "text": ""}}))
    raise SystemExit(0)

if os.environ.get("FAKE_CODEX_FAIL_NO_DETAIL") == "1":
    print(json.dumps({{"type": "thread.started", "thread_id": session}}))
    print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": "partial"}}}}))
    print(json.dumps({{"type": "turn.failed"}}))
    raise SystemExit(0)

if runner in ("claude", "workbuddy", "cursor"):
    print(json.dumps({{"type": "result", "subtype": "success", "session_id": session, "result": "fake response", "is_error": False}}))
elif runner == "antigravity":
    print(json.dumps({{"conversation_id": session, "status": "SUCCESS", "response": "fake response"}}))
elif runner == "grok":
    print(json.dumps({{"text": "fake response", "stopReason": "end_turn", "sessionId": session, "requestId": "fake-request"}}))
elif runner == "kimi":
    print(json.dumps({{"role": "assistant", "content": "fake response"}}))
    print(json.dumps({{"type": "session.resume_hint", "session_id": session}}))
elif runner == "codex":
    print(json.dumps({{"type": "thread.started", "thread_id": session}}))
    print(json.dumps({{"type": "item.completed", "item": {{"type": "agent_message", "text": "fake response"}}}}))
elif runner == "opencode":
    print(json.dumps({{"type": "text", "sessionID": session, "part": {{"text": "fake response"}}}}))
elif runner == "dsh":
    print(json.dumps({{"type": "session", "sessionId": session}}))
    print(json.dumps({{"type": "text", "text": "fake response"}}))
    print(json.dumps({{"type": "status", "phase": "turn_end", "reason": {{"kind": "completed"}}}}))
    print(json.dumps({{"type": "final", "text": "fake response"}}))
'''


class DelegateTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name).resolve()
        self.state_dir = self.root / "state"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        self.binaries = {runner: self.make_fake_cli(runner) for runner in RUNNERS}

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def make_fake_cli(self, runner: str) -> Path:
        path = self.bin_dir / runner
        path.write_text(FAKE_CLI.format(python=sys.executable, runner=runner), encoding="utf-8")
        path.chmod(0o755)
        return path

    def base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["SAKI_DELEGATE_HOME"] = str(self.state_dir)
        # Every data root points into the fixture, including official CLI subprocesses.
        env["HOME"] = str(self.root / "home")
        env["CODEX_HOME"] = str(self.root / "codex-home")
        env["KIMI_CODE_HOME"] = str(self.root / "kimi-home")
        env["CLAUDE_CONFIG_DIR"] = str(self.root / "claude-home")
        for key in list(env):
            if key.startswith("FAKE_"):
                env.pop(key, None)
        for runner, path in self.binaries.items():
            env[f"SAKI_DELEGATE_{runner.upper()}_BIN"] = str(path)
        return env

    def run_cli(
        self,
        *args: str,
        extra_env: dict[str, str] | None = None,
        remove_env: list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = self.base_env()
        for key in remove_env or []:
            env.pop(key, None)
        env.update(extra_env or {})
        return subprocess.run(
            [sys.executable, str(SCRIPT_PATH), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

    def onboard_all(self) -> None:
        result = self.run_cli(
            "onboard",
            "--enable",
            ",".join(RUNNERS),
            "--default-runner",
            "ask",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def run_task(
        self,
        runner: str,
        mode: str = "read",
        session: str | None = None,
        extra_env: dict[str, str] | None = None,
        timeout: str = "20",
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "run",
            "--runner",
            runner,
            "--workspace",
            str(self.workspace),
            "--mode",
            mode,
            "--prompt",
            "inspect the fixture",
            "--timeout",
            timeout,
        ]
        if session:
            args.extend(["--session", session])
        return self.run_cli(*args, extra_env=extra_env)

    def result_of(self, proc: subprocess.CompletedProcess[str]) -> dict:
        self.assertIn("result_path=", proc.stdout, msg=proc.stdout + proc.stderr)
        values = dict(
            line.split("=", 1)
            for line in proc.stdout.splitlines()
            if "=" in line
        )
        return json.loads(Path(values["result_path"]).read_text(encoding="utf-8"))

    def record_of(self) -> dict:
        return json.loads((self.root / "record.json").read_text(encoding="utf-8"))

    def test_scan_is_read_only_and_reports_nine_runners(self) -> None:
        result = self.run_cli("onboard", "--scan")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "NEEDS_ONBOARDING")
        self.assertEqual(set(payload["installed_runners"]), set(RUNNERS))
        self.assertTrue(payload["detected_runners"]["dsh"]["capabilities"]["json"])
        self.assertTrue(payload["detected_runners"]["dsh"]["capabilities"]["resume"])
        self.assertTrue(payload["detected_runners"]["dsh"]["capabilities"]["permission_flag"])
        self.assertFalse((self.state_dir / "config.json").exists())

    def test_onboarding_choice_alias_default_and_merge(self) -> None:
        record_path = self.root / "record.json"
        direct = self.run_task("cc", extra_env={"FAKE_RECORD": str(record_path)})
        self.assertEqual(direct.returncode, 0, msg=direct.stderr)
        self.assertEqual(self.result_of(direct)["runner"], "claude")
        self.assertFalse((self.state_dir / "config.json").exists())
        record_path.unlink()

        missing_before = self.run_cli(
            "run",
            "--runner",
            "opencode",
            "--workspace",
            str(self.workspace),
            "--prompt",
            "inspect",
            remove_env=["SAKI_DELEGATE_OPENCODE_BIN"],
        )
        self.assertEqual(missing_before.returncode, 1)
        self.assertIn("Command not found", missing_before.stderr)

        before = self.run_cli(
            "run",
            "--workspace",
            str(self.workspace),
            "--mode",
            "read",
            "--prompt",
            "inspect",
            extra_env={"FAKE_RECORD": str(record_path)},
        )
        self.assertEqual(before.returncode, 10)
        before_payload = json.loads(before.stdout)
        self.assertEqual(before_payload["status"], "NEEDS_ONBOARDING")
        self.assertEqual(set(before_payload["installed_runners"]), set(RUNNERS))
        self.assertIn("detected_runners", before_payload)
        self.assertFalse((self.state_dir / "config.json").exists())
        self.assertFalse(record_path.exists())

        onboard = self.run_cli("onboard", "--enable", "claude,dsh", "--default-runner", "ask")
        self.assertEqual(onboard.returncode, 0, msg=onboard.stderr)
        choice = self.run_cli(
            "run",
            "--workspace",
            str(self.workspace),
            "--mode",
            "read",
            "--prompt",
            "inspect",
        )
        self.assertEqual(choice.returncode, 11)
        self.assertEqual(json.loads(choice.stdout)["status"], "NEEDS_RUNNER_CHOICE")

        configured = self.run_cli("config", "--set-default-runner", "agy")
        self.assertEqual(configured.returncode, 0, msg=configured.stderr)
        self.assertEqual(json.loads(configured.stdout)["default_runner"], "antigravity")
        default_run = self.run_cli(
            "run",
            "--workspace",
            str(self.workspace),
            "--mode",
            "read",
            "--prompt",
            "inspect",
        )
        self.assertEqual(default_run.returncode, 0, msg=default_run.stderr)
        self.assertEqual(self.result_of(default_run)["runner"], "antigravity")

        config_path = self.state_dir / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["future_field"] = {"keep": True}
        config_path.write_text(json.dumps(config), encoding="utf-8")
        again = self.run_cli(
            "onboard",
            "--enable",
            "claude,codebuddy,deepseek-harness,agy,claude",
            "--default-runner",
            "claude-code",
        )
        self.assertEqual(again.returncode, 0, msg=again.stderr)
        merged = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(merged["future_field"], {"keep": True})
        self.assertEqual(merged["default_runner"], "claude")
        self.assertEqual(len(merged["enabled_runners"]), len(set(merged["enabled_runners"])))

    def test_short_aliases_work_in_onboarding_run_and_config(self) -> None:
        onboard = self.run_cli(
            "onboard",
            "--enable",
            "cc,wb,agy,dsh,claude,grok-build,kimi-code,cursor-cli",
            "--default-runner",
            "CC",
        )
        self.assertEqual(onboard.returncode, 0, msg=onboard.stderr)
        payload = json.loads(onboard.stdout)
        self.assertEqual(
            payload["enabled_runners"],
            ["claude", "workbuddy", "antigravity", "dsh", "grok", "kimi", "cursor"],
        )
        self.assertEqual(payload["default_runner"], "claude")
        self.assertIn("cc", payload["detected_runners"]["claude"]["aliases"])
        self.assertIn("wb", payload["detected_runners"]["workbuddy"]["aliases"])
        self.assertIn("anti", payload["detected_runners"]["antigravity"]["aliases"])
        self.assertIn("grok-build", payload["detected_runners"]["grok"]["aliases"])
        self.assertIn("kimi-code", payload["detected_runners"]["kimi"]["aliases"])
        self.assertIn("cursor-agent", payload["detected_runners"]["cursor"]["aliases"])
        self.assertIn("cursor-cli", payload["detected_runners"]["cursor"]["aliases"])

        for alias, canonical in (
            ("wb", "workbuddy"),
            ("kimi-code", "kimi"),
            ("anti", "antigravity"),
            ("cursor-agent", "cursor"),
            ("cursor-cli", "cursor"),
        ):
            with self.subTest(alias=alias):
                proc = self.run_task(alias, mode="write")
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                self.assertEqual(self.result_of(proc)["runner"], canonical)

        configured = self.run_cli("config", "--set-default-runner", "WB")
        self.assertEqual(configured.returncode, 0, msg=configured.stderr)
        self.assertEqual(json.loads(configured.stdout)["default_runner"], "workbuddy")

        binary = self.run_cli("config", "--set-bin", f"CC={self.binaries['claude']}")
        self.assertEqual(binary.returncode, 0, msg=binary.stderr)
        config_path = self.state_dir / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["runner_paths"]["claude"], str(self.binaries["claude"]))
        cleared = self.run_cli("config", "--clear-bin", "cc")
        self.assertEqual(cleared.returncode, 0, msg=cleared.stderr)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertNotIn("claude", config["runner_paths"])

    def test_disabled_runner_is_not_silently_substituted(self) -> None:
        onboard = self.run_cli("onboard", "--enable", "claude", "--default-runner", "claude")
        self.assertEqual(onboard.returncode, 0, msg=onboard.stderr)
        result = self.run_task("codex")
        self.assertEqual(result.returncode, 1)
        self.assertIn("not enabled", result.stderr)

    def test_all_runner_modes_and_resume(self) -> None:
        self.onboard_all()
        expected_read = {
            "claude": ["--permission-mode", "plan"],
            "workbuddy": ["--permission-mode", "plan"],
            "antigravity": ["--mode", "plan"],
            "codex": ["--sandbox", "read-only"],
            "opencode": ["--agent", "plan"],
            "dsh": ["--permission-mode", "read-only"],
            "grok": ["--permission-mode", "plan"],
            "cursor": ["--mode", "plan"],
        }
        expected_write = {
            "claude": ["--dangerously-skip-permissions"],
            "workbuddy": ["--permission-mode", "bypassPermissions"],
            "antigravity": ["--dangerously-skip-permissions"],
            "codex": ["--dangerously-bypass-approvals-and-sandbox"],
            "opencode": [],
            "dsh": ["--permission-mode", "danger-full-access"],
            "grok": ["--always-approve"],
            "kimi": [],
            "cursor": ["--force"],
        }
        resume_flags = {
            "claude": "--resume",
            "workbuddy": "--resume",
            "antigravity": "--conversation",
            "codex": "resume",
            "opencode": "--session",
            "dsh": "--session-id",
            "grok": "--resume",
            "kimi": "-S",
            "cursor": "--resume",
        }

        for runner in RUNNERS:
            if runner == "kimi":
                with self.subTest(runner=runner, mode="read_unsupported"):
                    proc = self.run_task(runner)
                    self.assertEqual(proc.returncode, 1)
                    self.assertIn("cannot guarantee read-only", proc.stderr)
            else:
                with self.subTest(runner=runner, mode="read"):
                    record_path = self.root / "record.json"
                    proc = self.run_task(runner, extra_env={"FAKE_RECORD": str(record_path)})
                    self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                    result = self.result_of(proc)
                    record = self.record_of()
                    self.assertEqual(result["status"], "completed")
                    self.assertEqual(result["response"], "fake response")
                    self.assertEqual(result["session_id"], f"fake-{runner}-session")
                    self.assertEqual(record["cwd"], str(self.workspace))
                    self.assertIn(expected_read[runner], [record["argv"][i:i + len(expected_read[runner])] for i in range(len(record["argv"]))])
                    self.assertFalse(any("inspect the fixture" in part for part in result["command"]))
                    if runner in ("codex", "dsh"):
                        self.assertEqual(result["command"][-1], "-")
                    elif runner == "cursor":
                        self.assertIn("--trust", record["argv"])
                        self.assertNotIn("--force", record["argv"])
                        self.assertIn("inspect the fixture", record["stdin"])
                    else:
                        self.assertIn("<prompt>", result["command"])
                    for artifact in (result["output_path"], result["events_path"], result["raw_stdout_path"], result["stderr_path"]):
                        self.assertTrue(Path(artifact).is_file())
                    if runner == "opencode":
                        self.assertEqual(json.loads(record["permission"])["edit"], "deny")
                        self.assertEqual(json.loads(record["permission"])["bash"], "deny")
                    if runner == "workbuddy":
                        self.assertEqual(record["disable_background"], "1")

            with self.subTest(runner=runner, mode="write"):
                record_path = self.root / "record.json"
                proc = self.run_task(runner, mode="write", extra_env={"FAKE_RECORD": str(record_path)})
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                write_result = self.result_of(proc)
                record = self.record_of()
                if expected_write[runner]:
                    flags = expected_write[runner]
                    self.assertIn(flags, [record["argv"][i:i + len(flags)] for i in range(len(record["argv"]))])
                if runner == "opencode":
                    self.assertEqual(json.loads(record["permission"])["edit"], "allow")
                    self.assertEqual(json.loads(record["permission"])["bash"], "allow")
                    self.assertEqual(json.loads(record["permission"])["external_directory"], "allow")
                if runner == "dsh":
                    self.assertIn("--approval-policy", record["argv"])
                    self.assertIn("never", record["argv"])
                if runner == "workbuddy":
                    self.assertEqual(record["codebuddy_sandbox"], "1")
                if runner == "kimi":
                    self.assertNotIn("--auto", record["argv"])
                    self.assertIn("stream-json", record["argv"])
                if runner == "cursor":
                    self.assertIn("--trust", record["argv"])
                    self.assertIn("inspect the fixture", record["stdin"])

            with self.subTest(runner=runner, mode="resume"):
                record_path = self.root / "record.json"
                proc = self.run_task(
                    runner,
                    mode="write" if runner == "kimi" else "read",
                    session=write_result["session_id"],
                    extra_env={"FAKE_RECORD": str(record_path)},
                )
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                resumed = self.result_of(proc)
                record = self.record_of()
                self.assertEqual(resumed["session_id"], write_result["session_id"])
                self.assertIn(resume_flags[runner], record["argv"])
                if runner == "codex":
                    self.assertIn('sandbox_mode="read-only"', record["argv"])

    def test_default_mode_is_full_access(self) -> None:
        # The parser leaves --mode empty so a role can supply its own mode; a plain run still writes.
        args = DELEGATE.build_parser().parse_args(["run", "--prompt", "inspect"])
        self.assertIsNone(args.mode)

        self.onboard_all()
        record_path = self.root / "record.json"
        proc = self.run_cli(
            "run",
            "--runner",
            "grok",
            "--workspace",
            str(self.workspace),
            "--prompt",
            "use default permissions",
            extra_env={"FAKE_RECORD": str(record_path)},
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertEqual(self.result_of(proc)["mode"], "write")
        record = self.record_of()
        self.assertIn("--always-approve", record["argv"])

    def run_role(self, role: str, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "run",
            "--role",
            role,
            "--workspace",
            str(self.workspace),
            "--prompt",
            "review the fixture",
            *extra,
            extra_env=env,
        )

    def test_role_is_asked_once_then_saved_and_review_roles_force_read_mode(self) -> None:
        self.onboard_all()
        asked = self.run_role("review", "--dry-run")
        self.assertEqual(asked.returncode, DELEGATE.EXIT_NEEDS_ROLE_CHOICE, msg=asked.stderr)
        payload = json.loads(asked.stdout)
        self.assertEqual(payload["status"], "NEEDS_ROLE_CHOICE")
        self.assertEqual(payload["mode"], "read")
        self.assertEqual(payload["candidates"][0], "host")
        self.assertNotIn("kimi", payload["candidates"])
        self.assertIn("kimi", json.loads(self.run_role("implement", "--dry-run").stdout)["candidates"])

        rejected = self.run_cli("config", "--set-role", "review=kimi")
        self.assertEqual(rejected.returncode, 1)
        self.assertIn("read-only", rejected.stderr)

        saved = self.run_cli("config", "--set-role", "review=cc")
        self.assertEqual(saved.returncode, 0, msg=saved.stderr)
        self.assertEqual(json.loads(saved.stdout)["roles"], {"review": ["claude"]})

        record_path = self.root / "record.json"
        proc = self.run_role("review", env={"FAKE_RECORD": str(record_path)})
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        result = self.result_of(proc)
        self.assertEqual((result["runner"], result["role"], result["mode"]), ("claude", "review", "read"))
        self.assertIn("plan", self.record_of()["argv"])

        conflict = self.run_role("review", "--mode", "write")
        self.assertEqual(conflict.returncode, 1)
        self.assertIn("always runs in read mode", conflict.stderr)

        # An explicitly named runner wins over the saved one, but the role still decides the mode.
        explicit = self.run_role("review", "--runner", "codex", "--dry-run")
        self.assertEqual(
            (json.loads(explicit.stdout)["runner"], json.loads(explicit.stdout)["mode"]), ("codex", "read")
        )

    def test_host_role_and_diagnose_slots(self) -> None:
        # Host-only preferences work without onboarding or any installed runner.
        self.assertEqual(self.run_cli("config", "--set-role", "critique=host").returncode, 0)
        host = self.run_role("critique")
        self.assertEqual(host.returncode, DELEGATE.EXIT_USE_HOST, msg=host.stderr)
        self.assertEqual(json.loads(host.stdout)["status"], "USE_HOST")
        self.assertFalse((self.state_dir / "runs").exists())

        for bad in ("diagnose=codex", "diagnose=codex,codex", "review=claude,codex", "triage=codex"):
            with self.subTest(bad=bad):
                self.assertEqual(self.run_cli("config", "--set-role", bad).returncode, 1)

        self.assertEqual(self.run_cli("config", "--set-role", "diagnose=host,codex").returncode, 0)
        self.assertEqual(self.run_role("diagnose").returncode, DELEGATE.EXIT_USE_HOST)
        second = self.run_role("diagnose", "--role-slot", "2", "--dry-run")
        self.assertEqual(second.returncode, 0, msg=second.stderr)
        self.assertEqual(json.loads(second.stdout)["runner"], "codex")
        self.assertEqual(self.run_role("diagnose", "--role-slot", "3", "--dry-run").returncode, 1)

    def test_role_warnings_reset_and_disabled_runner_cleanup(self) -> None:
        self.onboard_all()
        same = self.run_cli("config", "--set-role", "implement=codex", "--set-role", "review=codex")
        self.assertEqual(same.returncode, 0, msg=same.stderr)
        self.assertIn("same runner", json.loads(same.stdout)["warnings"][0])

        self.run_cli("config", "--set-role", "critique=host")
        self.assertEqual(self.run_cli("config", "--set-role", "review=ask").returncode, 0)
        roles = json.loads(self.run_cli("config").stdout)["roles"]
        self.assertEqual(roles, {"implement": ["codex"], "critique": ["host"]})

        narrowed = self.run_cli("config", "--set-enabled-runners", "claude")
        self.assertEqual(json.loads(narrowed.stdout)["roles"], {"critique": ["host"]})

    def test_dsh_legacy_permission_flags_use_environment(self) -> None:
        self.onboard_all()
        for mode, expected in (("read", "read-only"), ("write", "danger-full-access")):
            with self.subTest(mode=mode):
                record_path = self.root / "record.json"
                proc = self.run_task(
                    "dsh",
                    mode=mode,
                    extra_env={"FAKE_RECORD": str(record_path), "FAKE_DSH_LEGACY": "1"},
                )
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                record = self.record_of()
                self.assertEqual(record["dsh_mode"], expected)
                self.assertNotIn("--permission-mode", record["argv"])

    def test_prompt_does_not_forbid_git_operations(self) -> None:
        prompt = DELEGATE.compose_prompt("inspect", self.workspace, "write", [])
        self.assertNotIn("Do not run git add", prompt)
        self.assertNotIn("git commit", prompt)
        self.assertNotIn("git push", prompt)
        self.assertNotIn("publish", prompt)
        self.assertIn("Final report", prompt)

    def test_dry_run_has_no_process_or_run_artifacts(self) -> None:
        self.onboard_all()
        record_path = self.root / "record.json"
        result = self.run_cli(
            "run",
            "--runner",
            "claude",
            "--workspace",
            str(self.workspace),
            "--mode",
            "read",
            "--prompt",
            "do not execute",
            "--dry-run",
            extra_env={"FAKE_RECORD": str(record_path)},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "DRY_RUN")
        self.assertFalse(record_path.exists())
        self.assertFalse((self.state_dir / "runs").exists())

    def test_failure_timeout_and_dsh_bad_final(self) -> None:
        self.onboard_all()
        failed = self.run_task("claude", extra_env={"FAKE_FAIL": "1"})
        self.assertEqual(failed.returncode, 2)
        failed_result = self.result_of(failed)
        self.assertEqual(failed_result["status"], "failed")
        self.assertIn("fake failure", failed_result["error"])

        timed = self.run_task(
            "antigravity",
            timeout="1",
            extra_env={"FAKE_SLEEP": "3"},
        )
        self.assertEqual(timed.returncode, 124)
        self.assertEqual(self.result_of(timed)["status"], "failed")

        bad_final = self.run_task("dsh", extra_env={"FAKE_DSH_BAD_FINAL": "1"})
        self.assertEqual(bad_final.returncode, 1)
        bad_result = self.result_of(bad_final)
        self.assertEqual(bad_result["status"], "failed")
        self.assertIn("bad final", bad_result["error"])

    def test_json_output_contract_and_resume_commands(self) -> None:
        self.onboard_all()
        # Fake CLIs live at custom paths, so only the arguments after the executable are compared.
        expected = {
            "claude": "--resume fake-claude-session",
            "antigravity": "--conversation fake-antigravity-session",
            "codex": "resume fake-codex-session",
            "opencode": "--session fake-opencode-session",
            "dsh": "tui --resume fake-dsh-session",
            "grok": "--resume fake-grok-session",
            "kimi": "-S fake-kimi-session",
            "cursor": "--resume fake-cursor-session",
        }
        for runner, command in expected.items():
            mode = "write" if runner == "kimi" else "read"
            proc = self.run_cli(
                "run", "--runner", runner, "--workspace", str(self.workspace), "--mode", mode,
                "--prompt", "inspect", "--json",
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["contract_version"], 1)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["runner"], runner)
            self.assertTrue(payload["resume_command"].endswith(" " + command), msg=payload["resume_command"])
            stored = json.loads(Path(payload["result_path"]).read_text(encoding="utf-8"))
            self.assertEqual(stored["resume_command"], payload["resume_command"])

        dry = json.loads(
            self.run_cli(
                "run", "--runner", "agy", "--workspace", str(self.workspace), "--prompt", "x",
                "--dry-run", "--json",
            ).stdout
        )
        self.assertEqual((dry["status"], dry["runner"], dry["contract_version"]), ("DRY_RUN", "antigravity", 1))

    def test_json_mode_reports_errors_and_keeps_exit_codes(self) -> None:
        self.onboard_all()
        refused = self.run_cli(
            "run", "--runner", "kimi", "--workspace", str(self.workspace), "--mode", "read",
            "--prompt", "x", "--dry-run", "--json",
        )
        self.assertEqual(refused.returncode, 1)
        payload = json.loads(refused.stdout)
        self.assertEqual(payload["status"], "ERROR")
        self.assertTrue(payload["error"])

        timed = self.run_cli(
            "run", "--runner", "claude", "--workspace", str(self.workspace), "--prompt", "x",
            "--timeout", "1", "--json", extra_env={"FAKE_SLEEP": "3"},
        )
        self.assertEqual(timed.returncode, 124)
        self.assertEqual(json.loads(timed.stdout)["status"], "failed")

        choice = self.run_cli("run", "--workspace", str(self.workspace), "--prompt", "x", "--json")
        self.assertEqual(choice.returncode, 11)
        self.assertEqual(json.loads(choice.stdout)["status"], "NEEDS_RUNNER_CHOICE")

    def test_parallel_runs_use_distinct_result_paths(self) -> None:
        self.onboard_all()
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "run",
                    "--runner",
                    "claude",
                    "--workspace",
                    str(self.workspace),
                    "--mode",
                    "read",
                    "--prompt",
                    f"task {index}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self.base_env(),
            )
            for index in range(2)
        ]
        results = []
        for proc in processes:
            stdout, stderr = proc.communicate(timeout=20)
            self.assertEqual(proc.returncode, 0, msg=stderr)
            values = dict(line.split("=", 1) for line in stdout.splitlines() if "=" in line)
            results.append(values["result_path"])
        self.assertNotEqual(results[0], results[1])
        self.assertTrue(all(Path(path).is_file() for path in results))

    def test_secret_environment_is_not_copied_into_result(self) -> None:
        self.onboard_all()
        sentinel = "saki-delegate-test-sentinel"
        proc = self.run_task("dsh", extra_env={"DEEPSEEK_API_KEY": sentinel})
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        result = self.result_of(proc)
        self.assertNotIn(sentinel, json.dumps(result))
        self.assertNotIn(sentinel, Path(result["events_path"]).read_text(encoding="utf-8"))

    def test_entry_file_is_validated_and_included_only_in_prompt(self) -> None:
        self.onboard_all()
        missing = self.run_cli(
            "run",
            "--runner",
            "claude",
            "--workspace",
            str(self.workspace),
            "--mode",
            "read",
            "--prompt",
            "inspect",
            "--file",
            "missing.py",
        )
        self.assertEqual(missing.returncode, 1)
        entry = self.workspace / "entry.py"
        entry.write_text("print('ok')\n", encoding="utf-8")
        record_path = self.root / "record.json"
        valid = self.run_cli(
            "run",
            "--runner",
            "claude",
            "--workspace",
            str(self.workspace),
            "--mode",
            "read",
            "--prompt",
            "inspect",
            "--file",
            "entry.py",
            extra_env={"FAKE_RECORD": str(record_path)},
        )
        self.assertEqual(valid.returncode, 0, msg=valid.stderr)
        record = self.record_of()
        self.assertIn(str(entry), record["stdin"] + " ".join(record["argv"]))
        result = self.result_of(valid)
        self.assertNotIn(str(entry), " ".join(result["command"]))

    def test_empty_responses_are_failures_for_all_runners(self) -> None:
        self.onboard_all()
        for runner in RUNNERS:
            with self.subTest(runner=runner):
                proc = self.run_task(
                    runner,
                    mode="write" if runner == "kimi" else "read",
                    extra_env={"FAKE_EMPTY": "1"},
                )
                self.assertNotEqual(proc.returncode, 0)
                result = self.result_of(proc)
                self.assertEqual(result["status"], "failed")
                self.assertTrue(result["error"])

    def test_codex_failure_without_detail_is_not_success(self) -> None:
        self.onboard_all()
        proc = self.run_task("codex", extra_env={"FAKE_CODEX_FAIL_NO_DETAIL": "1"})
        self.assertNotEqual(proc.returncode, 0)
        result = self.result_of(proc)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Codex turn failed", result["error"])

    def test_codex_prefers_macos_chatgpt_app_before_path(self) -> None:
        app_codex = self.root / "ChatGPT.app" / "Contents" / "Resources" / "codex-cli" / "bin" / "codex"
        app_codex.parent.mkdir(parents=True)
        app_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        app_codex.chmod(0o755)
        path_dir = self.root / "path-codex"
        path_dir.mkdir()
        path_codex = path_dir / "codex"
        path_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path_codex.chmod(0o755)

        with mock.patch.dict(os.environ, {"PATH": str(path_dir)}, clear=True):
            with mock.patch.object(DELEGATE.sys, "platform", "darwin"):
                with mock.patch.object(DELEGATE, "chatgpt_codex_candidates", return_value=(app_codex,)):
                    detected = DELEGATE.detect_binary("codex", DELEGATE.default_config())
                    self.assertEqual(detected["source"], "chatgpt-app")
                    self.assertEqual(detected["path"], str(app_codex))
                    configured = DELEGATE.detect_binary(
                        "codex",
                        {**DELEGATE.default_config(), "runner_paths": {"codex": str(path_codex)}},
                    )
                    self.assertEqual(configured["source"], "config")
                    self.assertEqual(configured["path"], str(path_codex.resolve()))
                with mock.patch.object(DELEGATE, "chatgpt_codex_candidates", return_value=(self.root / "missing",)):
                    fallback = DELEGATE.detect_binary("codex", DELEGATE.default_config())
                    self.assertEqual(fallback["source"], "PATH")
                    self.assertEqual(Path(fallback["path"]).resolve(), path_codex.resolve())
        resumed = DELEGATE.resume_command("codex", str(app_codex), "sid-1", source="chatgpt-app")
        self.assertEqual(resumed, f"{shlex.quote(str(app_codex))} resume sid-1")

    def test_set_bin_and_default_runner_in_same_request(self) -> None:
        missing = self.run_cli(
            "config",
            "--set-default-runner",
            "opencode",
            remove_env=["SAKI_DELEGATE_OPENCODE_BIN"],
        )
        self.assertEqual(missing.returncode, 1)
        self.assertFalse((self.state_dir / "config.json").exists())

        configured = self.run_cli(
            "config",
            "--set-bin",
            f"opencode={self.binaries['opencode']}",
            "--set-default-runner",
            "opencode",
            remove_env=["SAKI_DELEGATE_OPENCODE_BIN"],
        )
        self.assertEqual(configured.returncode, 0, msg=configured.stderr)
        payload = json.loads(configured.stdout)
        self.assertEqual(payload["default_runner"], "opencode")
        config = json.loads((self.state_dir / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["runner_paths"]["opencode"], str(self.binaries["opencode"]))

    def test_config_and_runner_choice_skip_version_probes(self) -> None:
        call_log = self.root / "calls.jsonl"
        self.run_cli("onboard", "--enable", ",".join(RUNNERS), "--default-runner", "ask", extra_env={"FAKE_CALL_LOG": str(call_log)})
        call_log.unlink()

        configured = self.run_cli("config")
        self.assertEqual(configured.returncode, 0, msg=configured.stderr)
        self.assertFalse(call_log.exists())

        choice = self.run_cli("run", "--workspace", str(self.workspace), "--prompt", "x")
        self.assertEqual(choice.returncode, 11)
        self.assertFalse(call_log.exists())

    def test_stdout_aliases_share_one_file_and_no_timeout_config(self) -> None:
        self.onboard_all()
        proc = self.run_task("claude")
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        result = self.result_of(proc)
        self.assertEqual(result["events_path"], result["raw_stdout_path"])
        self.assertTrue(Path(result["events_path"]).is_file())
        self.assertNotIn("run_timeout_seconds", DELEGATE.default_config())

    def test_cursor_bad_subtype_and_binary_isolation(self) -> None:
        self.onboard_all()
        bad_subtype = self.run_task("cursor", extra_env={"FAKE_CURSOR_BAD_SUBTYPE": "1"})
        self.assertEqual(bad_subtype.returncode, 1)
        bad_result = self.result_of(bad_subtype)
        self.assertEqual(bad_result["status"], "failed")
        self.assertTrue(bad_result["error"])

        isolated_dir = self.root / "ide-only-bin"
        isolated_dir.mkdir()
        for decoy_name in ("cursor", "agent"):
            decoy = isolated_dir / decoy_name
            decoy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            decoy.chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(isolated_dir)}, clear=True):
            with mock.patch.object(Path, "home", return_value=self.root / "empty-home"):
                detected = DELEGATE.detect_binary("cursor", DELEGATE.default_config())
        self.assertFalse(detected["installed"])
        self.assertIn("cursor-agent", detected["error"])

    def test_model_passthrough_for_all_nine_runners_new_and_resume(self) -> None:
        self.onboard_all()
        record_path = self.root / "record.json"
        sample_models = {
            "claude": "claude-opus-4-6",
            "workbuddy": "glm-5.1",
            "antigravity": "gemini-4-carbon-high",
            "codex": "gpt-5.4",
            "opencode": "anthropic/claude-sonnet-4-5",
            "grok": "grok-4.6",
            "kimi": "kimi-k3.1-pro",
            "cursor": "sonnet-4-thinking",
        }
        for runner, model_id in sample_models.items():
            mode = "write" if runner == "kimi" else "read"
            with self.subTest(runner=runner, phase="dry_run"):
                dry = self.run_cli(
                    "run",
                    "--runner",
                    runner,
                    "--model",
                    model_id,
                    "--workspace",
                    str(self.workspace),
                    "--mode",
                    mode,
                    "--prompt",
                    "preview model flag",
                    "--dry-run",
                    "--json",
                )
                self.assertEqual(dry.returncode, 0, msg=dry.stderr)
                dry_payload = json.loads(dry.stdout)
                self.assertEqual((dry_payload["model"], dry_payload["model_source"]), (model_id, "flag"))
                self.assertIn(
                    ["--model", model_id],
                    [dry_payload["command"][i:i + 2] for i in range(len(dry_payload["command"]) - 1)],
                )

            with self.subTest(runner=runner, phase="new"):
                proc = self.run_cli(
                    "run",
                    "--runner",
                    runner,
                    "--model",
                    model_id,
                    "--workspace",
                    str(self.workspace),
                    "--mode",
                    mode,
                    "--prompt",
                    "run with model",
                    extra_env={"FAKE_RECORD": str(record_path)},
                )
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                kv = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
                self.assertEqual((kv["model"], kv["model_source"]), (model_id, "flag"))
                result = self.result_of(proc)
                self.assertEqual((result["model"], result["model_source"]), (model_id, "flag"))
                argv = self.record_of()["argv"]
                self.assertIn(["--model", model_id], [argv[i:i + 2] for i in range(len(argv) - 1)])

            with self.subTest(runner=runner, phase="resume"):
                resumed_model = model_id + "-next"
                resumed_proc = self.run_cli(
                    "run",
                    "--runner",
                    runner,
                    "--model",
                    resumed_model,
                    "--session",
                    result["session_id"],
                    "--workspace",
                    str(self.workspace),
                    "--mode",
                    mode,
                    "--prompt",
                    "resume with switched model",
                    "--json",
                    extra_env={"FAKE_RECORD": str(record_path)},
                )
                self.assertEqual(resumed_proc.returncode, 0, msg=resumed_proc.stdout + resumed_proc.stderr)
                resumed_payload = json.loads(resumed_proc.stdout)
                self.assertEqual((resumed_payload["model"], resumed_payload["model_source"]), (resumed_model, "flag"))
                self.assertEqual(resumed_payload["session_id"], result["session_id"])
                argv = self.record_of()["argv"]
                self.assertIn(["--model", resumed_model], [argv[i:i + 2] for i in range(len(argv) - 1)])
                if runner == "codex":
                    self.assertLess(argv.index("--model"), argv.index(result["session_id"]))

        record_path.unlink(missing_ok=True)
        for extra_flags in (["--dry-run", "--json"], []):
            with self.subTest(runner="dsh", flags=extra_flags):
                rejected = self.run_cli(
                    "run",
                    "--runner",
                    "dsh",
                    "--model",
                    "deepseek-reasoner",
                    "--workspace",
                    str(self.workspace),
                    "--prompt",
                    "must reject",
                    *extra_flags,
                    extra_env={"FAKE_RECORD": str(record_path)},
                )
                self.assertEqual(rejected.returncode, 1)
                combined = rejected.stdout + rejected.stderr
                self.assertIn("--model", combined)
                self.assertFalse(record_path.exists())

    def test_model_priority_flag_over_config_over_cli_default_and_clear(self) -> None:
        self.onboard_all()
        record_path = self.root / "record.json"

        baseline = self.run_cli(
            "run",
            "--runner",
            "agy",
            "--workspace",
            str(self.workspace),
            "--prompt",
            "baseline default",
            extra_env={"FAKE_RECORD": str(record_path)},
        )
        self.assertEqual(baseline.returncode, 0, msg=baseline.stderr)
        base_kv = dict(line.split("=", 1) for line in baseline.stdout.splitlines() if "=" in line)
        self.assertEqual((base_kv["model"], base_kv["model_source"]), ("", "cli-default"))
        base_result = self.result_of(baseline)
        self.assertIsNone(base_result["model"])
        self.assertEqual(base_result["model_source"], "cli-default")
        self.assertNotIn("--model", self.record_of()["argv"])

        saved = self.run_cli("config", "--set-model", "AGY=gemini-4-argon-medium")
        self.assertEqual(saved.returncode, 0, msg=saved.stderr)
        self.assertEqual(json.loads(saved.stdout)["runner_models"], {"antigravity": "gemini-4-argon-medium"})
        viewed = json.loads(self.run_cli("config").stdout)
        self.assertEqual(viewed["runner_models"], {"antigravity": "gemini-4-argon-medium"})

        from_config = self.run_cli(
            "run",
            "--runner",
            "antigravity",
            "--workspace",
            str(self.workspace),
            "--prompt",
            "use saved config model",
            extra_env={"FAKE_RECORD": str(record_path)},
        )
        self.assertEqual(from_config.returncode, 0, msg=from_config.stderr)
        cfg_result = self.result_of(from_config)
        self.assertEqual((cfg_result["model"], cfg_result["model_source"]), ("gemini-4-argon-medium", "config"))
        self.assertIn(
            ["--model", "gemini-4-argon-medium"],
            [self.record_of()["argv"][i:i + 2] for i in range(len(self.record_of()["argv"]) - 1)],
        )

        overridden = self.run_cli(
            "run",
            "--runner",
            "agy",
            "--model",
            "gemini-4-carbon-high",
            "--workspace",
            str(self.workspace),
            "--prompt",
            "override saved model",
            extra_env={"FAKE_RECORD": str(record_path)},
        )
        self.assertEqual(overridden.returncode, 0, msg=overridden.stderr)
        flag_result = self.result_of(overridden)
        self.assertEqual((flag_result["model"], flag_result["model_source"]), ("gemini-4-carbon-high", "flag"))
        self.assertIn(
            ["--model", "gemini-4-carbon-high"],
            [self.record_of()["argv"][i:i + 2] for i in range(len(self.record_of()["argv"]) - 1)],
        )

        cleared = self.run_cli("config", "--set-model", "agy=default")
        self.assertEqual(cleared.returncode, 0, msg=cleared.stderr)
        self.assertEqual(json.loads(cleared.stdout)["runner_models"], {})

        after_clear = self.run_cli(
            "run",
            "--runner",
            "agy",
            "--workspace",
            str(self.workspace),
            "--prompt",
            "back to cli default",
            extra_env={"FAKE_RECORD": str(record_path)},
        )
        self.assertEqual(after_clear.returncode, 0, msg=after_clear.stderr)
        cleared_result = self.result_of(after_clear)
        self.assertEqual((cleared_result["model"], cleared_result["model_source"]), (None, "cli-default"))
        self.assertNotIn("--model", self.record_of()["argv"])

        self.assertEqual(self.run_cli("config", "--set-model", "dsh=default").returncode, 0)
        for bad in ("dsh=deepseek-chat", "codex=", "codex", "unknown=gpt-5"):
            with self.subTest(bad_set_model=bad):
                self.assertEqual(self.run_cli("config", "--set-model", bad).returncode, 1)
        blank_flag = self.run_cli(
            "run", "--runner", "codex", "--model", "   ", "--workspace", str(self.workspace), "--prompt", "x"
        )
        self.assertEqual(blank_flag.returncode, 1)

    def test_effort_passthrough_priority_and_unsupported_rejection(self) -> None:
        self.onboard_all()
        expected_effort_flags = {
            "claude": ["--effort", "high"],
            "workbuddy": ["--effort", "high"],
            "antigravity": ["--effort", "high"],
            "codex": ["-c", 'model_reasoning_effort="high"'],
            "opencode": ["--variant", "high"],
            "grok": ["--effort", "high"],
        }
        for runner, expected in expected_effort_flags.items():
            with self.subTest(runner=runner):
                dry = self.run_cli(
                    "run",
                    "--runner",
                    runner,
                    "--effort",
                    "high",
                    "--workspace",
                    str(self.workspace),
                    "--prompt",
                    "effort preview",
                    "--dry-run",
                    "--json",
                )
                self.assertEqual(dry.returncode, 0, msg=dry.stderr)
                payload = json.loads(dry.stdout)
                self.assertEqual((payload["effort"], payload["effort_source"]), ("high", "flag"))
                self.assertIn(
                    expected,
                    [payload["command"][i:i + 2] for i in range(len(payload["command"]) - 1)],
                )

        self.assertEqual(self.run_cli("config", "--set-effort", "codex=xhigh").returncode, 0)
        cfg_dry = json.loads(
            self.run_cli(
                "run", "--runner", "codex", "--workspace", str(self.workspace),
                "--prompt", "x", "--dry-run", "--json",
            ).stdout
        )
        self.assertEqual((cfg_dry["effort"], cfg_dry["effort_source"]), ("xhigh", "config"))
        self.assertIn('model_reasoning_effort="xhigh"', cfg_dry["command"])
        self.assertEqual(self.run_cli("config", "--set-effort", "codex=default").returncode, 0)

        for unsupported in ("dsh", "kimi", "cursor"):
            with self.subTest(unsupported_effort=unsupported):
                self.assertEqual(self.run_cli("config", "--set-effort", f"{unsupported}=high").returncode, 1)
                mode = "write" if unsupported == "kimi" else "read"
                rejected = self.run_cli(
                    "run", "--runner", unsupported, "--effort", "high", "--mode", mode,
                    "--workspace", str(self.workspace), "--prompt", "x", "--dry-run",
                )
                self.assertEqual(rejected.returncode, 1)
                self.assertIn("--effort", rejected.stderr)

    def test_models_subcommand_for_all_nine_runners(self) -> None:
        self.run_cli("config", "--set-model", "agy=gemini-4-carbon-high")
        agy = self.run_cli("models", "--runner", "agy", "--json")
        self.assertEqual(agy.returncode, 0, msg=agy.stderr)
        agy_payload = json.loads(agy.stdout)
        self.assertEqual(agy_payload["status"], "OK")
        self.assertEqual(agy_payload["runner"], "antigravity")
        self.assertTrue(agy_payload["list_supported"])
        self.assertEqual(agy_payload["configured_model"], "gemini-4-carbon-high")
        self.assertEqual(
            agy_payload["models"],
            [
                {"id": "gemini-4-carbon-medium", "label": "Gemini 4 Carbon (Medium)"},
                {"id": "gemini-4-carbon-high", "label": "Gemini 4 Carbon (High)"},
            ],
        )

        agy_text = self.run_cli("models", "--runner", "antigravity")
        self.assertEqual(agy_text.returncode, 0, msg=agy_text.stderr)
        self.assertIn("model=gemini-4-carbon-high\tGemini 4 Carbon (High)", agy_text.stdout)

        grok_payload = json.loads(self.run_cli("models", "--runner", "grok", "--json").stdout)
        self.assertEqual(grok_payload["cli_default_model"], "grok-4.6")
        self.assertEqual([m["id"] for m in grok_payload["models"]], ["grok-4.6", "grok-4.5"])
        self.assertTrue(grok_payload["models"][0]["is_default"])

        opencode_payload = json.loads(self.run_cli("models", "--runner", "opencode", "--json").stdout)
        self.assertEqual([m["id"] for m in opencode_payload["models"]], ["anthropic/claude-sonnet-4-5", "openai/gpt-5"])

        cursor_payload = json.loads(self.run_cli("models", "--runner", "cursor-cli", "--json").stdout)
        self.assertEqual([m["id"] for m in cursor_payload["models"]], ["gpt-5", "sonnet-4-thinking"])

        cursor_empty = json.loads(
            self.run_cli("models", "--runner", "cursor", "--json", extra_env={"FAKE_CURSOR_NO_MODELS": "1"}).stdout
        )
        self.assertEqual(cursor_empty["status"], "OK")
        self.assertEqual(cursor_empty["models"], [])
        self.assertIn("No models available", cursor_empty["note"])

        failed_list = self.run_cli("models", "--runner", "agy", "--json", extra_env={"FAKE_MODELS_FAIL": "1"})
        self.assertEqual(failed_list.returncode, 1)
        self.assertEqual(json.loads(failed_list.stdout)["status"], "ERROR")

        missing_bin = self.run_cli(
            "models", "--runner", "opencode", "--json", remove_env=["SAKI_DELEGATE_OPENCODE_BIN"]
        )
        self.assertEqual(missing_bin.returncode, 1)

        call_log = self.root / "models_calls.jsonl"
        for runner in ("claude", "workbuddy", "codex", "kimi"):
            with self.subTest(no_list_runner=runner):
                proc = self.run_cli("models", "--runner", runner, "--json", extra_env={"FAKE_CALL_LOG": str(call_log)})
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                payload = json.loads(proc.stdout)
                self.assertEqual(payload["status"], "NO_MODEL_LIST_COMMAND")
                self.assertTrue(payload["supports_model_flag"])
                self.assertFalse(payload["list_supported"])
                self.assertEqual(payload["models"], [])
                self.assertTrue(payload["docs_url"].startswith("https://"))
                self.assertTrue(payload["hint"])
        self.assertFalse(call_log.exists())

        dsh_models = json.loads(self.run_cli("models", "--runner", "deepseek", "--json").stdout)
        self.assertEqual(dsh_models["status"], "MODEL_FLAG_UNSUPPORTED")
        self.assertFalse(dsh_models["supports_model_flag"])
        self.assertFalse(dsh_models["list_supported"])
        self.assertEqual(dsh_models["models"], [])
        self.assertTrue(dsh_models["docs_url"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
