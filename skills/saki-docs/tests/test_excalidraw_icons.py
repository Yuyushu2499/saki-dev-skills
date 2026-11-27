from __future__ import annotations

import base64
import importlib.util
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "excalidraw_icons.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("excalidraw_icons", SCRIPT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _minimal_png(width: int, height: int) -> bytes:
    """构造带合法 IHDR 尺寸头的最小 PNG 字节流，用于测试宽高解析。"""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
    return sig + ihdr


class ExcalidrawIconsTest(unittest.TestCase):
    def test_replace_placeholders_embeds_png_and_svg_and_preserves_arrow_binding(self) -> None:
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            icons_dir = root / "icons"
            icons_dir.mkdir()
            (icons_dir / "github.png").write_bytes(_minimal_png(200, 100))
            (icons_dir / "feishu.svg").write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="24"/></svg>',
                encoding="utf-8",
            )

            scene = {
                "type": "excalidraw",
                "version": 2,
                "elements": [
                    {
                        "id": "box-gh",
                        "type": "rectangle",
                        "x": 100,
                        "y": 100,
                        "width": 80,
                        "height": 80,
                        "boundElements": [
                            {"id": "txt-gh", "type": "text"},
                            {"id": "arr-1", "type": "arrow"},
                        ],
                    },
                    {
                        "id": "txt-gh",
                        "type": "text",
                        "containerId": "box-gh",
                        "text": "icon:github",
                    },
                    {
                        "id": "arr-1",
                        "type": "arrow",
                        "startBinding": {"elementId": "box-gh"},
                    },
                    {
                        "id": "icon:feishu",
                        "type": "rectangle",
                        "x": 100,
                        "y": 240,
                        "width": 64,
                        "height": 64,
                        "boundElements": [{"id": "txt-feishu-wrapped", "type": "text"}],
                    },
                    {
                        "id": "txt-feishu-wrapped",
                        "type": "text",
                        "containerId": "icon:feishu",
                        "text": "icon:fei\nshu",
                        "originalText": "icon:feishu",
                    },
                ],
                "files": {},
            }
            scene_file = root / "arch.excalidraw"
            scene_file.write_text(json.dumps(scene), encoding="utf-8")

            report = mod.replace_placeholders(scene_file, [icons_dir], {})
            self.assertEqual(report["status"], "OK")
            self.assertEqual(len(report["replaced"]), 2)
            self.assertEqual(report["missing"], [])

            updated = json.loads(scene_file.read_text(encoding="utf-8"))
            by_id = {e["id"]: e for e in updated["elements"]}
            self.assertNotIn("txt-gh", by_id)
            self.assertNotIn("txt-feishu-wrapped", by_id)
            gh = by_id["box-gh"]
            self.assertEqual(gh["type"], "image")
            # 200x100 等比放进 80x80 占位框应为 80x40 且垂直居中 (y = 120)
            self.assertEqual(gh["width"], 80.0)
            self.assertEqual(gh["height"], 40.0)
            self.assertEqual(gh["y"], 120.0)
            self.assertEqual(gh["boundElements"], [{"id": "arr-1", "type": "arrow"}])
            self.assertIn(gh["fileId"], updated["files"])
            self.assertTrue(updated["files"][gh["fileId"]]["dataURL"].startswith("data:image/png;base64,"))

            fs = by_id["icon:feishu"]
            self.assertEqual(fs["type"], "image")
            self.assertTrue(updated["files"][fs["fileId"]]["dataURL"].startswith("data:image/svg+xml;base64,"))

    def test_place_icon_cli_and_list_icons(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            icon = root / "logo.png"
            icon.write_bytes(_minimal_png(128, 128))
            scene = root / "empty.excalidraw"
            scene.write_text(json.dumps({"type": "excalidraw", "version": 2, "elements": [], "files": {}}), encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "place",
                    str(scene),
                    "--icon",
                    str(icon),
                    "--x",
                    "50",
                    "--y",
                    "60",
                    "--width",
                    "64",
                    "--height",
                    "64",
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            res = json.loads(proc.stdout)
            self.assertEqual(res["status"], "OK")
            updated = json.loads(scene.read_text(encoding="utf-8"))
            self.assertEqual(len(updated["elements"]), 1)
            self.assertEqual(updated["elements"][0]["type"], "image")
            self.assertIn(res["file_id"], updated["files"])
            b64_payload = updated["files"][res["file_id"]]["dataURL"].split(",", 1)[1]
            self.assertEqual(base64.b64decode(b64_payload), icon.read_bytes())


if __name__ == "__main__":
    unittest.main()
