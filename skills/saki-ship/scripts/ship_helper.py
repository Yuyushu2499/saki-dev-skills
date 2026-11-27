#!/usr/bin/env python3
"""saki-ship 交付前安全预检脚本：检查分支保护、改动清单、敏感文件风险与远端状态（仅使用 Python 3.10+ 标准库）。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

if sys.version_info < (3, 10):
    sys.stderr.write("错误：需要 Python 3.10 或更高版本。\n")
    raise SystemExit(2)

CONTRACT_VERSION = 1
PROTECTED_BRANCHES = {"main", "master", "production", "prod", "release"}

SENSITIVE_NAME_PATTERNS = (
    re.compile(r"(^|/)\.env($|\.(?!example$|sample$|template$))", re.IGNORECASE),
    re.compile(r"\.(pem|key|p12|pfx|jks|keystore)$", re.IGNORECASE),
    re.compile(r"(^|/)(id_rsa|id_ed25519|credentials\.json|secrets?\.(json|ya?ml|toml))$", re.IGNORECASE),
    re.compile(r"(^|/)\.DS_Store$"),
)


def _run_git(root: Path, args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotePath=false", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_porcelain_z(out: str) -> list[dict[str, str]]:
    tokens = out.split("\x00")
    entries: list[dict[str, str]] = []
    i = 0
    while i < len(tokens):
        entry = tokens[i]
        if not entry:
            i += 1
            continue
        code = entry[:2]
        path = entry[3:]
        if code[0] in ("R", "C") and i + 1 < len(tokens):
            old_path = tokens[i + 1]
            entries.append({"code": code, "path": path, "old_path": old_path})
            i += 2
        else:
            entries.append({"code": code, "path": path})
            i += 1
    return entries


def _is_sensitive_path(rel_path: str) -> bool:
    return any(p.search(rel_path) for p in SENSITIVE_NAME_PATTERNS)


def inspect_ship_status(workspace: Path) -> dict[str, Any]:
    root = workspace.expanduser().resolve()
    if not root.is_dir():
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": f"目录不存在：{root}"}

    rc, _, _ = _run_git(root, ["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": f"不是 Git 仓库：{root}"}

    rc_b, branch_out, _ = _run_git(root, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    detached = rc_b != 0
    branch = branch_out.strip() if not detached else "(detached HEAD)"
    is_protected = (not detached) and (branch.lower() in PROTECTED_BRANCHES)

    rc_up, up_out, _ = _run_git(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    upstream = up_out.strip() if rc_up == 0 else None

    ahead = 0
    behind = 0
    if upstream:
        rc_ab, ab_out, _ = _run_git(root, ["rev-list", "--left-right", "--count", f"{upstream}...HEAD"])
        if rc_ab == 0:
            parts = ab_out.strip().split()
            if len(parts) == 2:
                behind, ahead = int(parts[0]), int(parts[1])

    rc_rem, rem_out, _ = _run_git(root, ["remote"])
    remotes = [r.strip() for r in rem_out.splitlines() if r.strip()] if rc_rem == 0 else []

    rc_st, st_out, _ = _run_git(root, ["status", "--porcelain=v1", "-z", "-uall"])
    entries = _parse_porcelain_z(st_out) if rc_st == 0 else []

    staged = [e["path"] for e in entries if e["code"][0] not in (" ", "?")]
    unstaged = [e["path"] for e in entries if e["code"][1] not in (" ", "?")]
    untracked = [e["path"] for e in entries if e["code"] == "??"]
    all_changed = sorted({e["path"] for e in entries})
    sensitive_warnings = [p for p in all_changed if _is_sensitive_path(p)]

    blockers: list[str] = []
    if detached:
        blockers.append("当前处于游离 HEAD 状态，需先切到具体分支再提交推送")
    if is_protected:
        blockers.append(f"当前位于保护分支 '{branch}'，提交或推送前必须先征得用户确认")
    if behind > 0:
        blockers.append(f"当前分支落后远端 {upstream} {behind} 个提交，需先同步再推送")
    if sensitive_warnings:
        blockers.append(f"检测到疑似敏感或临时文件：{', '.join(sensitive_warnings)}")
    if not remotes:
        blockers.append("仓库未配置任何 git remote，无法推送到云端")

    can_auto_ship = (not blockers) and (bool(all_changed) or ahead > 0)
    push_command = (
        f"git push" if upstream else (f"git push -u {remotes[0]} {branch}" if remotes and not detached else None)
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "OK",
        "workspace": str(root),
        "branch": branch,
        "detached": detached,
        "is_protected_branch": is_protected,
        "remotes": remotes,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "all_changed": all_changed,
        "sensitive_warnings": sensitive_warnings,
        "blockers": blockers,
        "can_auto_ship": can_auto_ship,
        "recommended_push_command": push_command,
    }


def _print_human(report: dict[str, Any]) -> None:
    print(f"# 交付预检：{report['workspace']}")
    prot = " [保护分支]" if report["is_protected_branch"] else ""
    print(f"- 分支：{report['branch']}{prot}；远端追踪：{report['upstream'] or '未设置'}（领先 {report['ahead']} / 落后 {report['behind']}）")
    print(f"- 改动统计：已暂存 {len(report['staged'])}、未暂存 {len(report['unstaged'])}、未跟踪 {len(report['untracked'])}")
    if report["all_changed"]:
        print("\n## 变更文件")
        for p in report["all_changed"][:30]:
            mark = " [疑似敏感/临时文件]" if p in report["sensitive_warnings"] else ""
            print(f"- {p}{mark}")
    if report["blockers"]:
        print("\n## 阻塞 / 需确认项")
        for b in report["blockers"]:
            print(f"- {b}")
    else:
        status_msg = "满足自动中文提交并推送条件" if report["can_auto_ship"] else "工作区干净且无待推送提交"
        print(f"\n## 结论：{status_msg}")
        if report["recommended_push_command"]:
            print(f"- 推送命令：`{report['recommended_push_command']}`")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="saki-ship 交付前安全与分支保护预检工具")
    parser.add_argument("--workspace", default=".", help="目标 Git 仓库路径（默认当前目录）")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = inspect_ship_status(Path(args.workspace))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("status") != "OK":
        sys.stderr.write(f"错误：{report.get('error')}\n")
    else:
        _print_human(report)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
