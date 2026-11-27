#!/usr/bin/env python3
"""saki-comment 代码注释扫描脚本：识别缺少文档注释的核心函数与疑似不合理注释（仅使用 Python 3.10+ 标准库）。"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

if sys.version_info < (3, 10):
    sys.stderr.write("错误：需要 Python 3.10 或更高版本。\n")
    raise SystemExit(2)

CONTRACT_VERSION = 1

SKIP_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    "out",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "coverage",
}

SUPPORTED_EXTS = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".swift": "swift",
}

AUTHOR_DATE_RE = re.compile(r"(@author|@date|\bcreated\s+(by|on)\b|\bauthor\s*:|\bdate\s*:)", re.IGNORECASE)
BANNER_RE = re.compile(r"^\s*(#|//|/\*|\*)\s*([=\-*#~_]{12,})\s*(\*/)?\s*$")
BARE_TODO_RE = re.compile(r"^\s*(#|//)\s*(TODO|FIXME|XXX)\s*:?\s*$", re.IGNORECASE)
COMMENTED_CODE_HINTS_RE = re.compile(
    r"^\s*(#|//)\s*(def\s+\w+\(|class\s+\w+|import\s+\w+|from\s+\w+\s+import|return\s+\S+|"
    r"if\s+.+[:{]|for\s+.+[:{]|const\s+\w+\s*=|let\s+\w+\s*=|var\s+\w+\s*=|func\s+\w+\(|"
    r"fn\s+\w+\(|public\s+\w+|private\s+\w+|console\.log\(|print\()",
)

# 轻量多语言函数/类声明匹配（非 Python 文件使用）
NON_PY_DECL_PATTERNS: dict[str, re.Pattern[str]] = {
    "typescript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+([A-Za-z_]\w*)|class\s+([A-Za-z_]\w*)|"
        r"(?:const|let)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::[^=]+)?=>)"
    ),
    "javascript": re.compile(
        r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+([A-Za-z_]\w*)|class\s+([A-Za-z_]\w*)|"
        r"(?:const|let)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)"
    ),
    "go": re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\("),
    "rust": re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|struct|enum|trait)\s+([A-Za-z_]\w*)"),
    "java": re.compile(
        r"^\s*(?:public|protected|private)\s+(?:static\s+)?(?:final\s+)?(?:class|interface|enum|[\w<>\[\]]+\s+)([A-Za-z_]\w*)\s*[\({]"
    ),
    "kotlin": re.compile(r"^\s*(?:(?:public|internal|private|override|suspend)\s+)*(?:fun|class|interface)\s+([A-Za-z_]\w*)"),
    "swift": re.compile(r"^\s*(?:(?:public|internal|private|open|static)\s+)*(?:func|class|struct|enum|protocol)\s+([A-Za-z_]\w*)"),
}


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


def _list_code_files(root: Path, paths: list[str], include_tests: bool) -> list[str]:
    rc, out, _ = _run_git(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    if rc == 0:
        all_files = [p for p in out.split("\x00") if p]
    else:
        all_files = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            rel_dir = Path(dirpath).relative_to(root)
            for fname in sorted(filenames):
                all_files.append((rel_dir / fname).as_posix() if rel_dir != Path(".") else fname)

    prefixes = [p.strip().strip("./").rstrip("/") for p in paths if p.strip()]
    selected: list[str] = []
    for rel in sorted(set(all_files)):
        ext = Path(rel).suffix.lower()
        if ext not in SUPPORTED_EXTS:
            continue
        if prefixes and not any(rel == pre or rel.startswith(pre + "/") for pre in prefixes):
            continue
        if not include_tests:
            low = rel.lower()
            name = Path(rel).name.lower()
            if (
                low.startswith(("tests/", "test/", "__tests__/"))
                or "/tests/" in low
                or "/test/" in low
                or name.startswith("test_")
                or name.endswith(("_test.go", ".test.ts", ".test.js", ".spec.ts", ".spec.js"))
            ):
                continue
        selected.append(rel)
    return selected


def _scan_suspicious_comments(lines: list[str]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    code_run_start: int | None = None
    code_run_len = 0

    def flush_code_run() -> None:
        nonlocal code_run_start, code_run_len
        if code_run_start is not None and code_run_len >= 3:
            issues.append(
                {
                    "line": code_run_start,
                    "kind": "commented_out_code",
                    "detail": f"连续 {code_run_len} 行疑似被注释掉的死代码",
                    "snippet": lines[code_run_start - 1].strip()[:100],
                }
            )
        code_run_start = None
        code_run_len = 0

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        is_comment_line = stripped.startswith(("#", "//", "/*", "*"))
        if is_comment_line and COMMENTED_CODE_HINTS_RE.match(line):
            if code_run_start is None:
                code_run_start = idx
                code_run_len = 1
            else:
                code_run_len += 1
        else:
            flush_code_run()

        if is_comment_line and AUTHOR_DATE_RE.search(line):
            issues.append(
                {
                    "line": idx,
                    "kind": "author_or_date_boilerplate",
                    "detail": "疑似作者/日期模板注释（建议由 git blame 记录）",
                    "snippet": stripped[:100],
                }
            )
        elif BANNER_RE.match(line):
            issues.append(
                {
                    "line": idx,
                    "kind": "divider_banner",
                    "detail": "无信息量的纯符号装饰分隔线",
                    "snippet": stripped[:100],
                }
            )
        elif BARE_TODO_RE.match(line):
            issues.append(
                {
                    "line": idx,
                    "kind": "bare_todo",
                    "detail": "缺少说明的空 TODO/FIXME 标记",
                    "snippet": stripped[:100],
                }
            )

    flush_code_run()
    return issues


def _analyze_python(text: str, lines: list[str], min_core_lines: int) -> dict[str, Any]:
    missing_docs: list[dict[str, Any]] = []
    core_without_inline: list[dict[str, Any]] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {"missing_docstrings": missing_docs, "core_functions_without_inline_comments": core_without_inline}

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", start)
        span = max(1, end - start + 1)
        has_doc = bool(ast.get_docstring(node))
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        is_private = node.name.startswith("_") and not (node.name.startswith("__") and node.name.endswith("__"))

        if not has_doc and (not is_private or span >= min_core_lines):
            missing_docs.append(
                {
                    "name": node.name,
                    "kind": kind,
                    "line": start,
                    "lines": span,
                    "priority": "high" if span >= min_core_lines else "normal",
                }
            )

        if kind == "function" and span >= min_core_lines:
            body_lines = lines[start:end]
            has_inline = any(l.strip().startswith("#") for l in body_lines)
            if not has_inline:
                core_without_inline.append({"name": node.name, "line": start, "lines": span})

    missing_docs.sort(key=lambda x: (0 if x["priority"] == "high" else 1, -x["lines"], x["line"]))
    core_without_inline.sort(key=lambda x: (-x["lines"], x["line"]))
    return {
        "missing_docstrings": missing_docs,
        "core_functions_without_inline_comments": core_without_inline,
    }


def _has_preceding_doc_comment(lines: list[str], line_idx: int) -> bool:
    """检查声明行正上方是否存在文档注释（//、/// 或 */ 结尾块注释）。"""
    j = line_idx - 1
    while j >= 0 and lines[j].strip().startswith(("@", "#[")):
        j -= 1
    if j < 0:
        return False
    prev = lines[j].strip()
    return prev.startswith(("//", "///", "/*", "*")) or prev.endswith("*/")


def _analyze_generic(lang: str, lines: list[str]) -> dict[str, Any]:
    pattern = NON_PY_DECL_PATTERNS.get(lang)
    missing_docs: list[dict[str, Any]] = []
    if not pattern:
        return {"missing_docstrings": missing_docs, "core_functions_without_inline_comments": []}
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        name = next((g for g in match.groups() if g), None)
        if not name:
            continue
        if not _has_preceding_doc_comment(lines, idx):
            missing_docs.append(
                {
                    "name": name,
                    "kind": "symbol",
                    "line": idx + 1,
                    "lines": None,
                    "priority": "normal",
                }
            )
    return {"missing_docstrings": missing_docs, "core_functions_without_inline_comments": []}


def scan_comments(
    workspace: Path,
    paths: list[str] | None = None,
    include_tests: bool = False,
    min_core_lines: int = 20,
) -> dict[str, Any]:
    root = workspace.expanduser().resolve()
    if not root.is_dir():
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": f"目录不存在：{root}"}

    files = _list_code_files(root, paths or [], include_tests=include_tests)
    file_reports: list[dict[str, Any]] = []
    total_missing = 0
    total_core_no_inline = 0
    total_suspicious = 0

    for rel in files:
        full = root / rel
        if not full.is_file():
            continue
        text = full.read_bytes()[:400_000].decode("utf-8", errors="ignore")
        lines = text.splitlines()
        lang = SUPPORTED_EXTS[full.suffix.lower()]
        if lang == "python":
            analysis = _analyze_python(text, lines, min_core_lines=min_core_lines)
        else:
            analysis = _analyze_generic(lang, lines)
        suspicious = _scan_suspicious_comments(lines)

        missing = analysis["missing_docstrings"]
        core_no_inline = analysis["core_functions_without_inline_comments"]
        if missing or core_no_inline or suspicious:
            total_missing += len(missing)
            total_core_no_inline += len(core_no_inline)
            total_suspicious += len(suspicious)
            file_reports.append(
                {
                    "path": rel,
                    "language": lang,
                    "lines": len(lines),
                    "missing_docstrings": missing[:25],
                    "core_functions_without_inline_comments": core_no_inline[:15],
                    "suspicious_comments": suspicious[:20],
                }
            )

    file_reports.sort(
        key=lambda r: (
            -(len(r["missing_docstrings"]) + len(r["core_functions_without_inline_comments"]) + len(r["suspicious_comments"])),
            r["path"],
        )
    )

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "OK",
        "workspace": str(root),
        "scanned_files": len(files),
        "files_with_findings": len(file_reports),
        "summary": {
            "missing_docstrings": total_missing,
            "core_functions_without_inline_comments": total_core_no_inline,
            "suspicious_comments": total_suspicious,
        },
        "files": file_reports,
    }


def _print_human(report: dict[str, Any]) -> None:
    s = report["summary"]
    print(f"# 代码注释扫描快照：{report['workspace']}")
    print(
        f"- 扫描代码文件：{report['scanned_files']}；发现待处理文件：{report['files_with_findings']}"
        f"（缺文档注释 {s['missing_docstrings']} 处、核心长函数缺关键行内注释 {s['core_functions_without_inline_comments']} 处、"
        f"疑似不合理注释 {s['suspicious_comments']} 处）"
    )
    for item in report["files"][:20]:
        print(f"\n## {item['path']}（{item['language']}，{item['lines']} 行）")
        if item["missing_docstrings"]:
            names = ", ".join(
                f"{m['name']}@L{m['line']}" + (f"({m['lines']}行)" if m["lines"] else "")
                for m in item["missing_docstrings"][:8]
            )
            print(f"- 缺文档注释：{names}")
        if item["core_functions_without_inline_comments"]:
            names = ", ".join(f"{c['name']}@L{c['line']}({c['lines']}行)" for c in item["core_functions_without_inline_comments"][:6])
            print(f"- 核心长函数缺行内注释：{names}")
        if item["suspicious_comments"]:
            for sp in item["suspicious_comments"][:6]:
                print(f"- 疑似不合理注释 L{sp['line']} [{sp['kind']}]：{sp['detail']} -> `{sp['snippet']}`")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="saki-comment 缺失注释与疑似不合理注释扫描工具")
    parser.add_argument("--workspace", default=".", help="目标仓库路径（默认当前目录）")
    parser.add_argument("--path", action="append", default=[], help="限定扫描的子目录或文件（可重复传入）")
    parser.add_argument("--include-tests", action="store_true", help="同时扫描测试文件（默认跳过测试）")
    parser.add_argument("--min-core-lines", type=int, default=20, help="判定核心长函数的最小行数（默认 20）")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = scan_comments(
        Path(args.workspace),
        paths=args.path,
        include_tests=args.include_tests,
        min_core_lines=args.min_core_lines,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("status") != "OK":
        sys.stderr.write(f"错误：{report.get('error')}\n")
    else:
        _print_human(report)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
