#!/usr/bin/env python3
"""项目文档盘点（inventory）与基于 git diff 的文档影响面分析（impact）脚本（仅使用 Python 3.10+ 标准库）。"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
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

MANIFEST_NAMES = (
    "package.json",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "Package.swift",
    "Makefile",
    "justfile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "plugin.json",
)

RULE_FILES = ("AGENTS.md", "GEMINI.md", "CLAUDE.md", "DESIGN.md", "REVIEW.md")

CODE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".cs", ".scala", ".dart", ".vue", ".svelte", ".sh",
}

API_OR_SCHEMA_HINTS = (
    "api", "route", "router", "endpoint", "controller", "handler",
    "schema", "model", "migration", "proto", "openapi", "swagger", "graphql",
    "cli", "config", "settings", "plugin.json", "hooks.json",
)

DIFF_COMMON = ["--no-color", "--no-ext-diff", "--find-renames"]
STATUS_NAMES = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "typechange",
    "U": "unmerged",
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


def _list_repo_files(root: Path) -> list[str]:
    rc, out, _ = _run_git(root, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    if rc == 0:
        files = [p for p in out.split("\x00") if p]
        return sorted(set(files))
    collected: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        rel_dir = Path(dirpath).relative_to(root)
        for fname in sorted(filenames):
            rel = (rel_dir / fname).as_posix() if rel_dir != Path(".") else fname
            collected.append(rel)
    return collected


def _read_text(path: Path) -> str:
    try:
        return path.read_bytes()[:300_000].decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _top_module(rel_path: str) -> str:
    parts = Path(rel_path).parts
    if len(parts) <= 1:
        return "."
    if parts[0] in ("src", "packages", "apps", "lib", "services", "skills") and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def _is_doc_file(rel_path: str) -> bool:
    low = rel_path.lower()
    if not low.endswith((".md", ".mdx")):
        return False
    if "/" not in rel_path:
        return True
    return rel_path.startswith(("docs/", "doc/"))


def _classify_existing_docs(root: Path, files: list[str]) -> dict[str, Any]:
    root_docs: list[dict[str, Any]] = []
    docs_dir_files: list[dict[str, Any]] = []
    rule_docs: list[str] = []
    rule_set = {r.lower() for r in RULE_FILES}

    for rel in files:
        if not _is_doc_file(rel):
            continue
        full = root / rel
        if not full.is_file():
            continue
        text = _read_text(full)
        info = {
            "path": rel,
            "lines": len(text.splitlines()),
            "bytes": full.stat().st_size,
        }
        if "/" not in rel:
            root_docs.append(info)
            if rel.lower() in rule_set:
                rule_docs.append(rel)
        else:
            docs_dir_files.append(info)

    lower_all = {f.lower() for f in files}
    recommended_present = {
        "readme": any(f.lower().startswith("readme") and "/" not in f for f in files),
        "architecture": any("architecture" in f.lower() and f.lower().endswith(".md") for f in files),
        "api_or_data_model": any(
            any(k in f.lower() for k in ("api", "data-model", "schema")) and f.lower().endswith(".md")
            for f in files
        ),
        "decisions": any(
            (f.lower().startswith(("docs/decisions/", "docs/adr/")) and f.lower().endswith(".md"))
            for f in files
        ),
        "changelog": "changelog.md" in lower_all,
    }
    return {
        "root_docs": root_docs,
        "docs_dir_files": docs_dir_files,
        "rule_docs": rule_docs,
        "recommended_present": recommended_present,
    }


def collect_inventory(workspace: Path) -> dict[str, Any]:
    root = workspace.expanduser().resolve()
    if not root.is_dir():
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": f"目录不存在：{root}"}

    files = _list_repo_files(root)
    docs = _classify_existing_docs(root, files)

    manifests = [f for f in files if Path(f).name in MANIFEST_NAMES and len(Path(f).parts) <= 2]
    ci_files = [f for f in files if f.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))]

    module_counts: Counter[str] = Counter()
    api_schema_candidates: list[str] = []
    for rel in files:
        ext = Path(rel).suffix.lower()
        low = rel.lower()
        if ext in CODE_EXTS and not low.startswith(("tests/", "test/", "__tests__/")):
            module_counts[_top_module(rel)] += 1
        if any(hint in low for hint in API_OR_SCHEMA_HINTS) and not low.endswith(".md"):
            if len(api_schema_candidates) < 25:
                api_schema_candidates.append(rel)

    # 粗略检查每个代码模块是否已被现有文档提及
    all_doc_paths = [d["path"] for d in docs["root_docs"]] + [d["path"] for d in docs["docs_dir_files"]]
    combined_docs_text = "\n".join(_read_text(root / p) for p in all_doc_paths if (root / p).is_file())

    modules: list[dict[str, Any]] = []
    undocumented_modules: list[str] = []
    for mod, count in module_counts.most_common(30):
        mentioned = False
        if mod != ".":
            mentioned = (mod in combined_docs_text) or (Path(mod).name in combined_docs_text)
        else:
            mentioned = bool(docs["root_docs"])
        modules.append({"module": mod, "code_files": count, "mentioned_in_docs": mentioned})
        if mod != "." and not mentioned:
            undocumented_modules.append(mod)

    suggested_actions: list[str] = []
    pres = docs["recommended_present"]
    if not pres["readme"]:
        suggested_actions.append("新建 README.md（项目简介、快速开始、常用命令与目录概览）")
    if not pres["architecture"] and len(modules) >= 2:
        suggested_actions.append("新建 docs/architecture.md（模块职责、核心调用链与外部依赖）")
    if not pres["api_or_data_model"] and api_schema_candidates:
        suggested_actions.append("按需新建 docs/api.md 或 docs/data-model.md（检测到接口/配置/模型相关文件）")
    if undocumented_modules:
        suggested_actions.append(f"补充未在文档中提及的模块说明：{', '.join(undocumented_modules[:8])}")

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "OK",
        "mode": "inventory",
        "workspace": str(root),
        "total_files": len(files),
        "manifests": manifests,
        "ci_files": ci_files,
        "docs": docs,
        "code_modules": modules,
        "undocumented_modules": undocumented_modules,
        "api_schema_candidates": api_schema_candidates,
        "suggested_actions": suggested_actions,
    }


def _parse_name_status_z(out: str) -> list[dict[str, Any]]:
    tokens = out.split("\x00")
    entries: list[dict[str, Any]] = []
    i = 0
    while i < len(tokens):
        code = tokens[i]
        if not code:
            i += 1
            continue
        letter = code[0]
        status = STATUS_NAMES.get(letter, "modified")
        if letter in ("R", "C") and i + 2 < len(tokens):
            old_path, new_path = tokens[i + 1], tokens[i + 2]
            entries.append({"path": new_path, "old_path": old_path, "status": status})
            i += 3
        elif i + 1 < len(tokens):
            entries.append({"path": tokens[i + 1], "old_path": None, "status": status})
            i += 2
        else:
            break
    return entries


def _detect_default_base(root: Path) -> str | None:
    for candidate in ("origin/main", "main", "origin/master", "master"):
        rc, _, _ = _run_git(root, ["rev-parse", "--verify", "--quiet", candidate])
        if rc == 0:
            return candidate
    return None


def _collect_git_changes(root: Path, base: str | None) -> tuple[str, list[dict[str, Any]], str | None]:
    rc, _, _ = _run_git(root, ["rev-parse", "--is-inside-work-tree"])
    if rc != 0:
        return "none", [], "当前目录不是 Git 仓库"

    changes: dict[str, dict[str, Any]] = {}

    def merge(items: list[dict[str, Any]]) -> None:
        for item in items:
            changes[item["path"]] = item

    if base:
        rc, out, err = _run_git(root, ["diff", *DIFF_COMMON, "--name-status", "-z", f"{base}...HEAD"])
        if rc != 0:
            return "error", [], f"无法对比基准分支 {base}：{err.strip()}"
        merge(_parse_name_status_z(out))
        rc_wt, out_wt, _ = _run_git(root, ["diff", *DIFF_COMMON, "--name-status", "-z", "HEAD"])
        if rc_wt == 0:
            merge(_parse_name_status_z(out_wt))
        rc_un, out_un, _ = _run_git(root, ["ls-files", "-z", "--others", "--exclude-standard"])
        if rc_un == 0:
            for p in out_un.split("\x00"):
                if p and p not in changes:
                    changes[p] = {"path": p, "old_path": None, "status": "added"}
        return f"base:{base}+working_tree", sorted(changes.values(), key=lambda x: x["path"]), None

    # 默认先查工作区未提交修改（含暂存区与未跟踪文件）
    rc_wt, out_wt, _ = _run_git(root, ["diff", *DIFF_COMMON, "--name-status", "-z", "HEAD"])
    if rc_wt == 0:
        merge(_parse_name_status_z(out_wt))
    rc_un, out_un, _ = _run_git(root, ["ls-files", "-z", "--others", "--exclude-standard"])
    if rc_un == 0:
        for p in out_un.split("\x00"):
            if p and p not in changes:
                changes[p] = {"path": p, "old_path": None, "status": "added"}
    if changes:
        return "working_tree", sorted(changes.values(), key=lambda x: x["path"]), None

    # 工作区干净时回退到当前分支相对主干的已提交改动，或最近一次提交
    default_base = _detect_default_base(root)
    if default_base:
        rc_br, out_br, _ = _run_git(root, ["diff", *DIFF_COMMON, "--name-status", "-z", f"{default_base}...HEAD"])
        if rc_br == 0:
            merge(_parse_name_status_z(out_br))
            if changes:
                return f"committed_since:{default_base}", sorted(changes.values(), key=lambda x: x["path"]), None

    rc_last, out_last, _ = _run_git(root, ["diff", *DIFF_COMMON, "--name-status", "-z", "HEAD~1", "HEAD"])
    if rc_last == 0:
        merge(_parse_name_status_z(out_last))
        if changes:
            return "latest_commit", sorted(changes.values(), key=lambda x: x["path"]), None

    return "empty", [], None


def _find_doc_references(
    root: Path,
    doc_files: list[str],
    target_paths: list[str],
    touched_modules: list[str],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    # 只用较具区分度的路径或模块名匹配，避免单字母误报
    path_needles = sorted({p for p in target_paths if len(p) >= 4})
    mod_needles = sorted({m for m in touched_modules if m != "." and len(m) >= 3})

    for rel_doc in doc_files:
        full = root / rel_doc
        if not full.is_file():
            continue
        lines = _read_text(full).splitlines()
        matched_lines: list[dict[str, Any]] = []
        for idx, line in enumerate(lines, start=1):
            matched_tokens: list[str] = []
            for needle in path_needles:
                if needle in line:
                    matched_tokens.append(needle)
            if not matched_tokens:
                for mod in mod_needles:
                    if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(mod)}(?![A-Za-z0-9_-])", line):
                        matched_tokens.append(mod)
            if matched_tokens:
                matched_lines.append(
                    {
                        "line": idx,
                        "matched": matched_tokens[:4],
                        "snippet": line.strip()[:120],
                    }
                )
        if matched_lines:
            hits.append({"doc": rel_doc, "matches": matched_lines[:15], "total_matches": len(matched_lines)})
    return hits


def collect_impact(workspace: Path, base: str | None = None) -> dict[str, Any]:
    root = workspace.expanduser().resolve()
    if not root.is_dir():
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": f"目录不存在：{root}"}

    source, changed, err = _collect_git_changes(root, base)
    if err:
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": err}

    all_files = _list_repo_files(root)
    doc_files = [f for f in all_files if _is_doc_file(f)]

    touched_modules: set[str] = set()
    deleted_or_renamed: list[str] = []
    manifest_or_ci_changed: list[str] = []
    api_or_schema_changed: list[str] = []
    doc_files_already_changed: list[str] = []
    non_doc_changes: list[dict[str, Any]] = []
    all_target_paths: list[str] = []

    for item in changed:
        path = item["path"]
        old_path = item.get("old_path")
        status = item["status"]
        all_target_paths.append(path)
        if old_path:
            all_target_paths.append(old_path)
            deleted_or_renamed.append(f"{old_path} -> {path}")
        elif status == "deleted":
            deleted_or_renamed.append(path)

        if _is_doc_file(path):
            doc_files_already_changed.append(path)
            continue

        non_doc_changes.append(item)
        low = path.lower()
        if not low.startswith(("tests/", "test/", "__tests__/")):
            touched_modules.add(_top_module(path))
        if Path(path).name in MANIFEST_NAMES or path.startswith(".github/workflows/"):
            manifest_or_ci_changed.append(path)
        if any(hint in low for hint in API_OR_SCHEMA_HINTS):
            api_or_schema_changed.append(path)

    doc_refs = _find_doc_references(root, doc_files, all_target_paths, sorted(touched_modules))

    likely_doc_sync_needed = bool(
        deleted_or_renamed
        or manifest_or_ci_changed
        or api_or_schema_changed
        or any(item["status"] == "added" for item in non_doc_changes if not item["path"].lower().startswith(("tests/", "test/")))
        or doc_refs
    )

    reasons: list[str] = []
    if deleted_or_renamed:
        reasons.append(f"存在删除或重命名文件（{len(deleted_or_renamed)} 项），需核对文档中旧路径引用")
    if manifest_or_ci_changed:
        reasons.append(f"清单或 CI 配置有变动：{', '.join(manifest_or_ci_changed[:5])}")
    if api_or_schema_changed:
        reasons.append(f"接口/配置/模型线索文件有变动：{', '.join(api_or_schema_changed[:5])}")
    if doc_refs:
        reasons.append(f"有 {len(doc_refs)} 份现有文档直接提及了本次改动的路径或模块")
    if not reasons and non_doc_changes:
        reasons.append("仅检测到局部代码或测试改动，未命中结构/清单/接口/现有文档引用，可能无需更新文档")

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "OK",
        "mode": "impact",
        "workspace": str(root),
        "diff_source": source,
        "changed_files": changed,
        "touched_modules": sorted(touched_modules),
        "deleted_or_renamed": deleted_or_renamed,
        "manifest_or_ci_changed": manifest_or_ci_changed,
        "api_or_schema_changed": api_or_schema_changed,
        "doc_files_already_changed": doc_files_already_changed,
        "doc_references": doc_refs,
        "likely_doc_sync_needed": likely_doc_sync_needed,
        "reasons": reasons,
    }


def _print_inventory(report: dict[str, Any]) -> None:
    print(f"# 文档盘点快照：{report['workspace']}")
    print(f"- 文件总数：{report['total_files']}；清单：{', '.join(report['manifests']) or '无'}；CI：{len(report['ci_files'])} 份")
    docs = report["docs"]
    print("\n## 现有文档")
    for item in docs["root_docs"] + docs["docs_dir_files"]:
        print(f"- {item['path']}（{item['lines']} 行，{item['bytes']} B）")
    if not (docs["root_docs"] or docs["docs_dir_files"]):
        print("- （尚无 Markdown 文档）")
    print("\n## 核心代码模块覆盖")
    for m in report["code_modules"][:15]:
        mark = "已有提及" if m["mentioned_in_docs"] else "未提及"
        print(f"- {m['module']}（{m['code_files']} 个代码文件）[{mark}]")
    if report["api_schema_candidates"]:
        print("\n## 接口 / 配置 / 模型线索")
        for p in report["api_schema_candidates"][:10]:
            print(f"- {p}")
    if report["suggested_actions"]:
        print("\n## 建议动作")
        for s in report["suggested_actions"]:
            print(f"- {s}")


def _print_impact(report: dict[str, Any]) -> None:
    print(f"# 文档影响面分析：{report['workspace']}（来源：{report['diff_source']}）")
    print(f"- 改动文件数：{len(report['changed_files'])}；涉及模块：{', '.join(report['touched_modules']) or '无'}")
    print(f"- 初步判断：{'建议评估同步文档' if report['likely_doc_sync_needed'] else '可能无需更新文档'}")
    for r in report["reasons"]:
        print(f"  - {r}")
    if report["deleted_or_renamed"]:
        print("\n## 删除或重命名路径")
        for p in report["deleted_or_renamed"]:
            print(f"- {p}")
    if report["doc_references"]:
        print("\n## 命中本次改动的现有文档引用")
        for ref in report["doc_references"]:
            print(f"- {ref['doc']}（共 {ref['total_matches']} 处）：")
            for m in ref["matches"][:6]:
                print(f"  - L{m['line']}: {m['snippet']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="saki-docs 文档盘点与 git diff 影响面分析工具")
    sub = parser.add_subparsers(dest="command", required=True)

    inv = sub.add_parser("inventory", help="盘点仓库现有文档、代码模块与未覆盖区域")
    inv.add_argument("--workspace", default=".", help="目标仓库路径（默认当前目录）")
    inv.add_argument("--json", action="store_true", help="输出结构化 JSON")

    imp = sub.add_parser("impact", help="基于 git diff 分析本次改动影响哪些现有文档")
    imp.add_argument("--workspace", default=".", help="目标仓库路径（默认当前目录）")
    imp.add_argument("--base", help="对比基准分支（如 main）")
    imp.add_argument("--json", action="store_true", help="输出结构化 JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inventory":
        report = collect_inventory(Path(args.workspace))
    else:
        report = collect_impact(Path(args.workspace), base=args.base)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("status") != "OK":
        sys.stderr.write(f"错误：{report.get('error')}\n")
    elif args.command == "inventory":
        _print_inventory(report)
    else:
        _print_impact(report)
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
