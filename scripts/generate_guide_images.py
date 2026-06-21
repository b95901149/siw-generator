"""Generate README / USER_GUIDE screenshots and update README intro."""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

DOCS_IMAGES = ROOT / "docs" / "images"
README = ROOT / "README.md"
MARKER_START = "<!-- AUTO_SCREENSHOTS_START -->"
MARKER_END = "<!-- AUTO_SCREENSHOTS_END -->"


def _ensure_dir() -> None:
    DOCS_IMAGES.mkdir(parents=True, exist_ok=True)


def _save_figure(figure, path: Path, *, dpi: int = 120) -> None:
    _ensure_dir()
    figure.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white", pad_inches=0.08)


def _render_circular_preview() -> None:
    from matplotlib.figure import Figure

    from siw_generator.preview import render_preview
    from siw_generator.siw_geometry import SIWParams, build_siw_geometry
    from siw_generator.stackup import StackupParams

    params = SIWParams(
        substrate_length_mm=10.0,
        substrate_width_mm=10.0,
        center_freq_ghz=120.0,
        via_diameter_mm=0.15,
        siw_width_mm=1.2745,
        via_pitch_mm=0.28,
        via_count_target=54,
        stackup=StackupParams(substrate_height_mm=0.127, copper_thickness_mm=0.015),
        material="rt5880",
    )
    geometry = build_siw_geometry(params)
    fig = render_preview(geometry, Figure(figsize=(5.2, 4.6), dpi=120))
    _save_figure(fig, DOCS_IMAGES / "step2_circular_preview.png")


def _render_slot_preview() -> None:
    from matplotlib.figure import Figure

    from siw_generator.preview import render_preview
    from siw_generator.slot_geometry import SlotSIWParams, build_slot_siw_geometry
    from siw_generator.stackup import StackupParams

    params = SlotSIWParams(
        substrate_length_mm=10.0,
        substrate_width_mm=10.0,
        center_freq_ghz=120.0,
        slot_width_mm=0.15,
        slot_length_mm=1.0,
        slot_corner_r_mm=0.015,
        slot_pitch_mm=1.05,
        via_count_target=8,
        siw_width_mm=1.2745,
        stackup=StackupParams(substrate_height_mm=0.127, copper_thickness_mm=0.015),
        material="rt5880",
    )
    geometry = build_slot_siw_geometry(params)
    fig = render_preview(geometry, Figure(figsize=(5.2, 4.6), dpi=120))
    _save_figure(fig, DOCS_IMAGES / "readme_slot_preview.png")


def _render_custom_preview() -> None:
    from matplotlib.figure import Figure

    from siw_generator.custom_geometry import (
        CustomVia,
        CustomViaRole,
        CustomViaType,
        CustomModuleDefinition,
    )
    from siw_generator.custom_io import load_module_file
    from siw_generator.custom_preview import render_custom_preview
    from siw_generator.stackup import StackupParams

    module_path = ROOT / "module" / "ctm-randomDot.json"
    if module_path.is_file():
        module = load_module_file(module_path)
    else:
        module = CustomModuleDefinition(
            substrate_length_mm=5.0,
            substrate_width_mm=5.0,
            stackup=StackupParams(substrate_height_mm=0.127, copper_thickness_mm=0.015),
            vias=[],
        )
    roles = {v.via_role for v in module.vias}
    if CustomViaRole.TOP_CU not in roles:
        module.vias.append(CustomVia(1.2, 0.8, CustomViaType.CIRCLE, CustomViaRole.TOP_CU, 0.15, 0.15))
    if CustomViaRole.BOT_CU not in roles:
        module.vias.append(CustomVia(-1.2, -0.8, CustomViaType.SQUARE, CustomViaRole.BOT_CU, 0.2, 0.2))
    fig = render_custom_preview(module, Figure(figsize=(5.2, 4.6), dpi=120))
    _save_figure(fig, DOCS_IMAGES / "readme_custom_preview.png")


def _render_compose_preview() -> None:
    from matplotlib.figure import Figure

    from siw_generator.combination_io import apply_combination_data, load_combination_file
    from siw_generator.compose_preview import render_compose_main

    combo_path = ROOT / "combination" / "tripleSIW2.json"
    if not combo_path.is_file():
        combo_path = ROOT / "combination" / "tripleSIW.json"
    if not combo_path.is_file():
        print("  (skip compose preview: no combination JSON)")
        return
    data = load_combination_file(combo_path)
    layout, *_rest = apply_combination_data(data)
    fig = render_compose_main(layout, Figure(figsize=(5.6, 5.0), dpi=120))
    _save_figure(fig, DOCS_IMAGES / "readme_compose_preview.png")


def _capture_tk_window(window, path: Path) -> bool:
    try:
        from PIL import ImageGrab
    except ImportError:
        print("  (skip GUI capture: Pillow not installed)")
        return False

    window.update_idletasks()
    window.update()
    time.sleep(0.35)
    x = window.winfo_rootx()
    y = window.winfo_rooty()
    w = window.winfo_width()
    h = window.winfo_height()
    if w <= 1 or h <= 1:
        return False
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    _ensure_dir()
    img.save(path)
    return True


def _capture_gui_screenshots() -> None:
    try:
        import tkinter as tk
    except ImportError:
        print("  (skip GUI capture: tkinter unavailable)")
        return

    from siw_generator.gui import SIWGeneratorApp

    def _fixed_geometry(self) -> None:
        self.geometry("1280x780+40+20")

    SIWGeneratorApp._maximize_window = _fixed_geometry  # type: ignore[method-assign]

    app = SIWGeneratorApp()
    app.update_idletasks()
    app.update()
    app.after(800, lambda: None)
    app.update()
    time.sleep(0.5)

    if _capture_tk_window(app, DOCS_IMAGES / "step1_recipe_bar.png"):
        print("  saved step1_recipe_bar.png (GUI)")

    tabs = [
        ("圓形 Via", "readme_gui_circular.png"),
        ("Custom", "readme_gui_custom.png"),
        ("組合", "readme_gui_compose.png"),
    ]
    notebook = app._notebook
    for tab_text, filename in tabs:
        for idx in range(notebook.index("end")):
            if notebook.tab(idx, "text") == tab_text:
                notebook.select(idx)
                app.update_idletasks()
                app.update()
                time.sleep(0.45)
                if _capture_tk_window(app, DOCS_IMAGES / filename):
                    print(f"  saved {filename} ({tab_text})")
                break

    try:
        app.destroy()
    except tk.TclError:
        pass


def _screenshots_markdown() -> str:
    from siw_generator import __version__

    def img(name: str, alt: str) -> str:
        rel = f"docs/images/{name}"
        if (DOCS_IMAGES / name).is_file():
            return f"![{alt}]({rel})"
        return f"<!-- missing: {rel} -->"

    lines = [
        f"**版本 {__version__}** — 圖形化設計 SIW Via 圍牆、Custom 模組與 M×N 組合版面，"
        "可輸出 **CST**（DXF / STL / VBA）、**HFSS** VBScript 與參數報告。",
        "",
        "| 分頁 | 功能 |",
        "|------|------|",
        "| **圓形 Via** | 圓柱 Via 圍牆、Port、XY/YZ 預覽、CST 輸出 |",
        "| **圓角矩形 Slot Via** | 跑道形 Slot 孔 SIW 設計 |",
        "| **Custom** | 滑鼠放置圓/方/Slot 孔；貫孔 / top金屬 / bot金屬；模組存於 `module/` |",
        "| **組合** | 平鋪模組、填補、Port、組合級 CST 套件 |",
        "| **CST VBA / HFSS** | 預覽與複製模擬巨集 |",
        "",
        "### 主視窗 — Recipe 與分頁",
        "",
        img("step1_recipe_bar.png", "主視窗 Recipe 列與分頁"),
        "",
        "頂部 **Recipe** 列可儲存／讀取全部參數；分頁切換圓形、Slot、Custom、組合與模擬輸出。",
        "",
        "### 圓形 Via — XY 預覽",
        "",
        img("step2_circular_preview.png", "圓形 Via XY 預覽"),
        "",
        "依頻率、孔徑、孔距與 SIW 寬度自動排列圓柱 Via，並顯示 Port 位置。",
        "",
        "### 圓角矩形 Slot Via",
        "",
        img("readme_slot_preview.png", "Slot Via XY 預覽"),
        "",
        "圓角矩形 Slot 孔沿 X 排列，適用於 Slot 型 SIW 側壁。",
        "",
        "### Custom Via 模組",
        "",
        img("readme_custom_preview.png", "Custom Via 預覽"),
        "",
        "自由放置 Via；**貫孔**（紅）、**top金屬孔**（淺綠）、**bot金屬孔**（粉紅）可區分銅層挖孔。",
        "",
        "### 組合版面",
        "",
        img("readme_compose_preview.png", "組合 M×N 預覽"),
        "",
        "將 `module/` 模組平鋪至網格，支援旋轉、鏡射、填補與 Port 定義。",
        "",
        "> 截圖由 `python scripts/generate_guide_images.py` 自動產生。",
        "",
    ]
    return "\n".join(lines)


def _update_readme() -> None:
    content = README.read_text(encoding="utf-8")
    block = f"{MARKER_START}\n{_screenshots_markdown()}{MARKER_END}"
    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        re.DOTALL,
    )
    if pattern.search(content):
        content = pattern.sub(block, content)
    else:
        # Insert after first heading block
        insert_at = content.find("\n## ")
        if insert_at == -1:
            content = content.rstrip() + "\n\n" + block + "\n"
        else:
            content = content[:insert_at] + "\n\n" + block + content[insert_at:]
    README.write_text(content, encoding="utf-8")
    print(f"Updated {README.relative_to(ROOT)}")


def main() -> None:
    os.environ.setdefault("MPLBACKEND", "Agg")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
    print("Generating matplotlib previews...")
    _render_circular_preview()
    print("  step2_circular_preview.png")
    _render_slot_preview()
    print("  readme_slot_preview.png")
    _render_custom_preview()
    print("  readme_custom_preview.png")
    _render_compose_preview()
    print("  readme_compose_preview.png")

    print("Capturing GUI screenshots...")
    _capture_gui_screenshots()

    print("Updating README...")
    _update_readme()
    print("Done.")


if __name__ == "__main__":
    main()
