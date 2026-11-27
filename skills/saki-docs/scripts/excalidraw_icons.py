#!/usr/bin/env python3
"""向 .excalidraw 文件嵌入本地 PNG/SVG 图标，或按占位标记（icon:<名称>）原地替换并保留箭头绑定（仅使用 Python 3.10+ 标准库）。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
import sys
import time
from pathlib import Path
from typing import Any

if sys.version_info < (3, 10):
    sys.stderr.write("错误：需要 Python 3.10 或更高版本。\n")
    raise SystemExit(2)

CONTRACT_VERSION = 1
SUPPORTED_ICON_EXTS = {
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
PLACEHOLDER_RE = re.compile(r"^\s*icon\s*[:：]\s*([A-Za-z0-9._-]+)\s*$", re.IGNORECASE)
SVG_VIEWBOX_RE = re.compile(r'viewBox\s*=\s*["\']\s*[-+\d.]+\s+[-+\d.]+\s+([\d.]+)\s+([\d.]+)\s*["\']', re.IGNORECASE)
SVG_WIDTH_RE = re.compile(r'\bwidth\s*=\s*["\']\s*([\d.]+)', re.IGNORECASE)
SVG_HEIGHT_RE = re.compile(r'\bheight\s*=\s*["\']\s*([\d.]+)', re.IGNORECASE)


def _read_image_size(path: Path) -> tuple[float, float]:
    """解析 PNG 或 SVG 的原始宽高，解析失败时回退 1:1 比例。"""
    ext = path.suffix.lower()
    raw = path.read_bytes()
    if ext == ".png" and len(raw) >= 24 and raw[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", raw[16:24])
        if width > 0 and height > 0:
            return float(width), float(height)
    elif ext == ".svg":
        text = raw[:65_536].decode("utf-8", errors="ignore")
        vb = SVG_VIEWBOX_RE.search(text)
        if vb:
            w, h = float(vb.group(1)), float(vb.group(2))
            if w > 0 and h > 0:
                return w, h
        wm, hm = SVG_WIDTH_RE.search(text), SVG_HEIGHT_RE.search(text)
        if wm and hm:
            w, h = float(wm.group(1)), float(hm.group(1))
            if w > 0 and h > 0:
                return w, h
    return 100.0, 100.0


def _fit_box(box_x: float, box_y: float, box_w: float, box_h: float, img_w: float, img_h: float) -> tuple[float, float, float, float]:
    """在目标占位框内等比缩放并居中摆放图标，防止拉伸变形。"""
    if box_w <= 0 or box_h <= 0 or img_w <= 0 or img_h <= 0:
        return box_x, box_y, max(box_w, 48.0), max(box_h, 48.0)
    scale = min(box_w / img_w, box_h / img_h)
    final_w = round(img_w * scale, 2)
    final_h = round(img_h * scale, 2)
    final_x = round(box_x + (box_w - final_w) / 2.0, 2)
    final_y = round(box_y + (box_h - final_h) / 2.0, 2)
    return final_x, final_y, final_w, final_h


def _make_file_entry(icon_path: Path) -> tuple[str, dict[str, Any]]:
    ext = icon_path.suffix.lower()
    mime = SUPPORTED_ICON_EXTS.get(ext)
    if not mime:
        raise ValueError(f"不支持的图标格式：{icon_path.name}（支持：{', '.join(sorted(SUPPORTED_ICON_EXTS))}）")
    raw = icon_path.read_bytes()
    file_id = hashlib.sha1(raw).hexdigest()[:20]
    b64 = base64.b64encode(raw).decode("ascii")
    now_ms = int(time.time() * 1000)
    entry = {
        "mimeType": mime,
        "id": file_id,
        "dataURL": f"data:{mime};base64,{b64}",
        "created": now_ms,
        "lastRetrieved": now_ms,
    }
    return file_id, entry


def _make_image_element(
    elem_id: str,
    file_id: str,
    x: float,
    y: float,
    width: float,
    height: float,
    group_ids: list[str] | None = None,
    bound_elements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    seed = int(hashlib.sha1(f"{elem_id}:{file_id}".encode("utf-8")).hexdigest()[:8], 16)
    return {
        "type": "image",
        "version": 1,
        "versionNonce": seed,
        "isDeleted": False,
        "id": elem_id,
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "angle": 0,
        "x": x,
        "y": y,
        "strokeColor": "transparent",
        "backgroundColor": "transparent",
        "width": width,
        "height": height,
        "seed": seed,
        "groupIds": list(group_ids or []),
        "frameId": None,
        "roundness": None,
        "boundElements": list(bound_elements) if bound_elements else None,
        "updated": now_ms,
        "link": None,
        "locked": False,
        "status": "saved",
        "fileId": file_id,
        "scale": [1, 1],
    }


def discover_icons(icon_dirs: list[Path]) -> dict[str, Path]:
    """按优先级扫描图标目录，返回 小写stem -> 图标路径 映射（先扫描的目录优先，同目录内 PNG 优先于 SVG）。"""
    found: dict[str, Path] = {}
    ext_rank = {".png": 0, ".svg": 1, ".webp": 2, ".jpg": 3, ".jpeg": 4}
    for directory in icon_dirs:
        resolved = directory.expanduser().resolve()
        if not resolved.is_dir():
            continue
        candidates = sorted(
            (p for p in resolved.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_ICON_EXTS),
            key=lambda p: (ext_rank.get(p.suffix.lower(), 9), p.as_posix()),
        )
        for path in candidates:
            key = path.stem.lower()
            found.setdefault(key, path)
    return found


def _parse_explicit_map(raw_maps: list[str]) -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for item in raw_maps:
        if "=" not in item:
            raise ValueError(f"--map 参数格式应为 key=path：{item!r}")
        key, raw_path = item.split("=", 1)
        clean_key = key.strip().lower()
        target = Path(raw_path.strip()).expanduser().resolve()
        if not target.is_file():
            raise ValueError(f"图标文件不存在：{target}")
        mapping[clean_key] = target
    return mapping


def replace_placeholders(
    scene_path: Path,
    icon_dirs: list[Path],
    explicit_map: dict[str, Path],
    output_path: Path | None = None,
) -> dict[str, Any]:
    """查找画布中标注为 icon:<名称> 的占位元素，原地替换为等比缩放的真实 image 元素并保持箭头绑定。"""
    src = scene_path.expanduser().resolve()
    if not src.is_file():
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": f"文件不存在：{src}"}

    data = json.loads(src.read_text(encoding="utf-8"))
    elements: list[dict[str, Any]] = data.get("elements", [])
    files: dict[str, Any] = data.setdefault("files", {})

    catalog = {**discover_icons(icon_dirs), **explicit_map}
    by_id = {e.get("id"): e for e in elements if isinstance(e, dict) and e.get("id")}

    # 预先按 containerId 索引所有绑定文字，防止 Excalidraw 自动折行导致占位文字残留
    bound_texts_by_container: dict[str, set[str]] = {}
    for elem in elements:
        if isinstance(elem, dict) and not elem.get("isDeleted") and elem.get("type") == "text":
            cid = elem.get("containerId")
            tid = elem.get("id")
            if cid and tid:
                bound_texts_by_container.setdefault(str(cid), set()).add(str(tid))

    # 识别占位符：支持（1）容器内绑定文本为 icon:<key>（含 originalText / 折行文本）；（2）独立文本为 icon:<key>；（3）元素 id 为 icon:<key>
    targets: dict[str, tuple[str, set[str]]] = {}  # target_elem_id -> (icon_key, drop_text_ids)
    for elem in elements:
        if not isinstance(elem, dict) or elem.get("isDeleted"):
            continue
        eid = str(elem.get("id") or "")
        etype = elem.get("type")
        if etype == "text":
            raw_text = str(elem.get("originalText") or elem.get("text") or "")
            collapsed = re.sub(r"\s+", "", raw_text)
            m = PLACEHOLDER_RE.match(raw_text) or PLACEHOLDER_RE.match(collapsed)
            if m:
                key = m.group(1).lower()
                container_id = elem.get("containerId")
                if container_id and container_id in by_id:
                    targets[container_id] = (key, bound_texts_by_container.get(str(container_id), {eid}))
                else:
                    targets[eid] = (key, set())
        elif eid.lower().startswith("icon:"):
            key = eid.split(":", 1)[1].strip().lower()
            if key and eid not in targets:
                targets[eid] = (key, set(bound_texts_by_container.get(eid, set())))

    replaced: list[dict[str, Any]] = []
    missing: list[str] = []
    drop_ids: set[str] = set()
    replacements: dict[str, dict[str, Any]] = {}

    for target_id, (key, text_ids) in targets.items():
        icon_path = catalog.get(key)
        if not icon_path:
            missing.append(key)
            continue
        orig = by_id[target_id]
        file_id, file_entry = _make_file_entry(icon_path)
        files[file_id] = file_entry
        img_w, img_h = _read_image_size(icon_path)
        x, y, w, h = _fit_box(
            float(orig.get("x", 0)),
            float(orig.get("y", 0)),
            float(orig.get("width", 64)),
            float(orig.get("height", 64)),
            img_w,
            img_h,
        )
        # 保留原有箭头绑定，移除指向已删除占位文字的 text 绑定
        orig_bound = orig.get("boundElements") or []
        kept_bound = [b for b in orig_bound if isinstance(b, dict) and b.get("id") not in text_ids]
        # 复用原容器 id，保证画布中指向它的所有 arrow startBinding / endBinding 无需改 id 即自动保持绑定
        img_elem = _make_image_element(
            elem_id=target_id,
            file_id=file_id,
            x=x,
            y=y,
            width=w,
            height=h,
            group_ids=orig.get("groupIds") or [],
            bound_elements=kept_bound or None,
        )
        replacements[target_id] = img_elem
        drop_ids.update(text_ids)
        replaced.append({"id": target_id, "icon": key, "source": str(icon_path), "file_id": file_id})

    new_elements: list[dict[str, Any]] = []
    for elem in elements:
        eid = elem.get("id") if isinstance(elem, dict) else None
        if eid in drop_ids:
            continue
        if eid in replacements:
            new_elements.append(replacements[eid])
        else:
            new_elements.append(elem)
    data["elements"] = new_elements

    dst = output_path.expanduser().resolve() if output_path else src
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "contract_version": CONTRACT_VERSION,
        "status": "OK",
        "scene": str(dst),
        "replaced": replaced,
        "missing": sorted(set(missing)),
    }


def place_icon(
    scene_path: Path,
    icon_path: Path,
    x: float,
    y: float,
    width: float,
    height: float,
    elem_id: str | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """在 .excalidraw 画布指定坐标放入一枚真实 PNG/SVG 图标（自动保持原图宽高比）。"""
    src = scene_path.expanduser().resolve()
    icon = icon_path.expanduser().resolve()
    if not src.is_file():
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": f"场景文件不存在：{src}"}
    if not icon.is_file():
        return {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": f"图标文件不存在：{icon}"}

    data = json.loads(src.read_text(encoding="utf-8"))
    elements: list[dict[str, Any]] = data.setdefault("elements", [])
    files: dict[str, Any] = data.setdefault("files", {})

    file_id, file_entry = _make_file_entry(icon)
    files[file_id] = file_entry
    img_w, img_h = _read_image_size(icon)
    fx, fy, fw, fh = _fit_box(x, y, width, height, img_w, img_h)
    final_id = elem_id or f"img-{icon.stem}-{file_id[:6]}"
    elements.append(_make_image_element(final_id, file_id, fx, fy, fw, fh))

    dst = output_path.expanduser().resolve() if output_path else src
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "OK",
        "scene": str(dst),
        "element_id": final_id,
        "file_id": file_id,
        "rect": {"x": fx, "y": fy, "width": fw, "height": fh},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Excalidraw 图标嵌入与占位替换工具（支持 PNG/SVG）")
    sub = parser.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("list-icons", help="列出图标目录中可用的本地图标名称与路径")
    ls.add_argument("--icon-dir", action="append", default=[], help="图标目录（默认包含 ~/.saki-dev/icons）")
    ls.add_argument("--json", action="store_true", help="输出结构化 JSON")

    rep = sub.add_parser("replace-placeholders", help="把画布中标注为 icon:<名称> 的占位框替换为真实 PNG/SVG 图标")
    rep.add_argument("scene", help="目标 .excalidraw 文件路径")
    rep.add_argument("--icon-dir", action="append", default=[], help="图标搜索目录（可重复传入，默认附带 ~/.saki-dev/icons）")
    rep.add_argument("--map", dest="maps", action="append", default=[], help="显式映射 key=path（优先级最高）")
    rep.add_argument("--output", help="可选输出路径（默认原地覆盖）")
    rep.add_argument("--json", action="store_true", help="输出结构化 JSON")

    pl = sub.add_parser("place", help="在指定坐标框内插入一枚本地 PNG/SVG 图标")
    pl.add_argument("scene", help="目标 .excalidraw 文件路径")
    pl.add_argument("--icon", required=True, help="本地 PNG/SVG 图标路径")
    pl.add_argument("--x", type=float, required=True, help="左上角 X 坐标")
    pl.add_argument("--y", type=float, required=True, help="左上角 Y 坐标")
    pl.add_argument("--width", type=float, default=64.0, help="目标框宽度（默认 64）")
    pl.add_argument("--height", type=float, default=64.0, help="目标框高度（默认 64）")
    pl.add_argument("--id", dest="elem_id", help="可选自定义元素 ID")
    pl.add_argument("--output", help="可选输出路径（默认原地覆盖）")
    pl.add_argument("--json", action="store_true", help="输出结构化 JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    default_home_icons = Path.home() / ".saki-dev" / "icons"

    try:
        if args.command == "list-icons":
            dirs = [Path(d) for d in args.icon_dir] + [default_home_icons]
            catalog = discover_icons(dirs)
            report = {
                "contract_version": CONTRACT_VERSION,
                "status": "OK",
                "count": len(catalog),
                "icons": {k: str(v) for k, v in sorted(catalog.items())},
            }
        elif args.command == "replace-placeholders":
            dirs = [Path(d) for d in args.icon_dir] + [default_home_icons]
            explicit = _parse_explicit_map(args.maps)
            report = replace_placeholders(
                Path(args.scene),
                icon_dirs=dirs,
                explicit_map=explicit,
                output_path=Path(args.output) if args.output else None,
            )
        else:
            report = place_icon(
                Path(args.scene),
                icon_path=Path(args.icon),
                x=args.x,
                y=args.y,
                width=args.width,
                height=args.height,
                elem_id=args.elem_id,
                output_path=Path(args.output) if args.output else None,
            )
    except ValueError as exc:
        report = {"contract_version": CONTRACT_VERSION, "status": "ERROR", "error": str(exc)}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("status") != "OK":
        sys.stderr.write(f"错误：{report.get('error')}\n")
    elif args.command == "list-icons":
        print(f"找到 {report['count']} 个本地图标：")
        for k, v in report["icons"].items():
            print(f"- {k}: {v}")
    elif args.command == "replace-placeholders":
        print(f"已更新：{report['scene']}（替换 {len(report['replaced'])} 处，缺失 {len(report['missing'])} 处）")
        if report["missing"]:
            print(f"- 未找到对应图标：{', '.join(report['missing'])}")
    else:
        print(f"已插入图标 {report['element_id']} 到 {report['scene']}")
    return 0 if report.get("status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
