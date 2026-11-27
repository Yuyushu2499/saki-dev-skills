#!/usr/bin/env python3
"""Antigravity PreToolUse 钩子：在写入前拦截命中 saki-dev 开发约定禁改目录（do-not-edit）的文件修改。

仅使用 Python 3.10+ 标准库；未配置 saki-dev 约定或无法解析目标路径时默认放行（fail-open），避免误伤正常编辑。
"""

from __future__ import annotations

import fnmatch
import json
import re
import sys
from pathlib import Path
from typing import Any

DEV_PROFILE_FILES = ("AGENTS.md", "GEMINI.md", "CLAUDE.md")
DEV_PROFILE_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
DEV_PROFILE_ITEM_RE = re.compile(r"^\s*[-*+]\s+([^:：]+?)\s*[:：]\s*(.*)$")
DEV_PROFILE_CODE_RE = re.compile(r"`([^`]+)`")
DO_NOT_EDIT_KEYS = {"禁改", "禁改目录", "do-not-edit"}
PATH_ARG_KEYS = ("Path", "path", "TargetFile", "file_path")


def _matches_any(path: str, patterns: list[str]) -> bool:
    for raw in patterns:
        pattern = raw.strip().lstrip("./")
        if not pattern:
            continue
        if pattern.endswith("/"):
            if path.startswith(pattern) or path == pattern.rstrip("/"):
                return True
        elif pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif fnmatch.fnmatch(path, pattern):
            return True
    return False


def _load_do_not_edit(root: Path) -> tuple[str | None, list[str]]:
    """读取仓库根目录 AGENTS.md / GEMINI.md / CLAUDE.md 中标题含 saki-dev 小节的禁改目录列表。"""
    for name in DEV_PROFILE_FILES:
        path = root / name
        if not path.is_file() or path.is_symlink():
            continue
        lines = path.read_bytes()[:200_000].decode("utf-8", errors="ignore").splitlines()
        level = 0
        start_line = 0
        in_fence = False
        patterns: list[str] = []
        for line_no, line in enumerate(lines, start=1):
            if line.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            heading = DEV_PROFILE_HEADING_RE.match(line)
            if heading:
                depth = len(heading.group(1))
                if start_line and depth <= level:
                    break
                if not start_line and "saki-dev" in heading.group(2).lower():
                    level, start_line = depth, line_no
                continue
            item = DEV_PROFILE_ITEM_RE.match(line) if start_line else None
            if not item:
                continue
            key = re.sub(r"[*`_]", "", item.group(1)).strip().lower()
            if key not in DO_NOT_EDIT_KEYS:
                continue
            raw = item.group(2).strip()
            found = DEV_PROFILE_CODE_RE.findall(raw)
            if not found and raw:
                found = re.split(r"[、,，]", raw)
            patterns.extend(v.strip() for v in found if v.strip())
        if start_line:
            return f"{name}:{start_line}", patterns
    return None, []


def _extract_target_path(payload: dict[str, Any]) -> Path | None:
    tool_call = payload.get("toolCall")
    if not isinstance(tool_call, dict):
        return None
    args = tool_call.get("args")
    if not isinstance(args, dict):
        return None
    raw_path = None
    for key in PATH_ARG_KEYS:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            raw_path = val.strip()
            break
    if not raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        base = payload.get("cwd")
        if not isinstance(base, str) or not base.strip():
            ws = payload.get("workspacePaths")
            base = ws[0] if isinstance(ws, list) and ws and isinstance(ws[0], str) else ""
        if not base:
            return None
        candidate = Path(base).expanduser() / candidate
    try:
        return candidate.resolve()
    except OSError:
        return candidate


def _resolve_repo_root(target: Path, payload: dict[str, Any]) -> Path | None:
    workspace_roots: list[Path] = []
    raw_ws = payload.get("workspacePaths")
    if isinstance(raw_ws, list):
        for item in raw_ws:
            if isinstance(item, str) and item.strip():
                try:
                    workspace_roots.append(Path(item).expanduser().resolve())
                except OSError:
                    pass
    raw_cwd = payload.get("cwd")
    if isinstance(raw_cwd, str) and raw_cwd.strip():
        try:
            cwd_path = Path(raw_cwd).expanduser().resolve()
            if cwd_path not in workspace_roots:
                workspace_roots.append(cwd_path)
        except OSError:
            pass

    # 优先从目标文件的父目录向上寻找 .git 仓库根
    cur = target.parent
    for parent in (cur, *cur.parents):
        if (parent / ".git").exists():
            return parent
        if any(parent == ws for ws in workspace_roots):
            return parent

    # 回退到包含目标文件的最深 workspace root
    containing = [ws for ws in workspace_roots if target.is_relative_to(ws)]
    if containing:
        return max(containing, key=lambda p: len(p.parts))
    return None


def evaluate_hook(payload: dict[str, Any]) -> dict[str, Any]:
    target = _extract_target_path(payload)
    if target is None:
        return {"decision": "allow"}
    repo_root = _resolve_repo_root(target, payload)
    if repo_root is None or not target.is_relative_to(repo_root):
        return {"decision": "allow"}

    source, patterns = _load_do_not_edit(repo_root)
    if not source or not patterns:
        return {"decision": "allow"}

    rel_path = target.relative_to(repo_root).as_posix()
    if _matches_any(rel_path, patterns):
        return {
            "decision": "deny",
            "reason": (
                f"已被 saki-dev 禁改目录守卫拦截：'{rel_path}' 命中 {source} 中声明的禁改规则 "
                f"({', '.join(patterns)})。如需修改，请先获得用户明确确认或更新 saki-dev 开发约定。"
            ),
        }
    return {"decision": "allow"}


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps({"decision": "allow"}))
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"decision": "allow"}))
        return 0
    if not isinstance(payload, dict):
        print(json.dumps({"decision": "allow"}))
        return 0
    result = evaluate_hook(payload)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
