"""Save/load compose combinations with embedded modules and operation steps."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from siw_generator.app_paths import combination_dir, module_dir
from siw_generator.compose_geometry import ComposeLayout
from siw_generator.compose_io import layout_from_dict, layout_to_dict, relative_module_ref
from siw_generator.custom_io import module_from_dict, module_to_dict, save_module_file
from siw_generator.export_paths import resolve_recipe_stem

COMBINATION_FORMAT = "siw-generator-combination"
COMBINATION_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def combination_path(title: str) -> Path:
    stem = resolve_recipe_stem(title)
    return combination_dir() / f"{stem}.json"


def list_combination_files() -> list[Path]:
    folder = combination_dir()
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def collect_embedded_modules(layout: ComposeLayout) -> dict[str, dict[str, Any]]:
    modules: dict[str, dict[str, Any]] = {}
    for placed in layout.placements.values():
        ref = relative_module_ref(placed.source_path) or placed.label.strip()
        if not ref:
            ref = f"ctm-{placed.col}_{placed.row}.json"
        ref = ref.replace("\\", "/")
        modules[ref] = module_to_dict(placed.module, title=Path(ref).stem)
    return modules


def collect_all_embedded_modules(
    layout: ComposeLayout,
    undo_stack: list[ComposeLayout] | None = None,
    redo_stack: list[ComposeLayout] | None = None,
) -> dict[str, dict[str, Any]]:
    modules: dict[str, dict[str, Any]] = {}
    for item in (layout, *(undo_stack or []), *(redo_stack or [])):
        modules.update(collect_embedded_modules(item))
    return modules


def layout_snapshot_to_dict(layout: ComposeLayout) -> dict[str, Any]:
    return layout_to_dict(layout, recipe_name="", grid_vars={})


def layout_snapshot_from_dict(data: dict[str, Any]) -> ComposeLayout:
    layout, _, _ = layout_from_dict(data)
    return layout


def build_combination_payload(
    *,
    title: str,
    layout: ComposeLayout,
    grid_vars: dict[str, str],
    operations: list[dict[str, Any]],
    undo_stack: list[ComposeLayout] | None = None,
    redo_stack: list[ComposeLayout] | None = None,
    redo_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    undo_stack = undo_stack or []
    redo_stack = redo_stack or []
    redo_steps = redo_steps or []
    return {
        "format": COMBINATION_FORMAT,
        "version": COMBINATION_VERSION,
        "saved_at": _now_iso(),
        "title": title.strip(),
        "layout": layout_to_dict(layout, recipe_name=title, grid_vars=grid_vars),
        "modules": collect_all_embedded_modules(layout, undo_stack, redo_stack),
        "operations": list(operations),
        "undo_snapshots": [layout_snapshot_to_dict(item) for item in undo_stack],
        "redo_snapshots": [layout_snapshot_to_dict(item) for item in redo_stack],
        "redo_steps": list(redo_steps),
    }


def save_combination_file(
    path: Path,
    *,
    title: str,
    layout: ComposeLayout,
    grid_vars: dict[str, str],
    operations: list[dict[str, Any]],
    undo_stack: list[ComposeLayout] | None = None,
    redo_stack: list[ComposeLayout] | None = None,
    redo_steps: list[dict[str, Any]] | None = None,
) -> Path:
    payload = build_combination_payload(
        title=title,
        layout=layout,
        grid_vars=grid_vars,
        operations=operations,
        undo_stack=undo_stack,
        redo_stack=redo_stack,
        redo_steps=redo_steps,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_combination_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != COMBINATION_FORMAT:
        raise ValueError(f"不支援的組合檔格式：{data.get('format')}")
    return data


def restore_missing_modules(modules: dict[str, Any]) -> list[str]:
    """Write embedded module JSON into module/ when the file is missing."""
    restored: list[str] = []
    for rel, raw in modules.items():
        if not isinstance(raw, dict):
            continue
        rel_path = str(rel).replace("\\", "/").strip()
        if not rel_path:
            continue
        target = module_dir() / rel_path
        if target.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        module = module_from_dict(raw)
        save_module_file(module, target, title=target.stem)
        restored.append(rel_path)
    return restored


def apply_combination_data(
    data: dict[str, Any],
) -> tuple[
    ComposeLayout,
    str,
    dict[str, str],
    list[dict[str, Any]],
    list[str],
    list[ComposeLayout],
    list[ComposeLayout],
    list[dict[str, Any]],
]:
    layout_data = data.get("layout")
    if not isinstance(layout_data, dict):
        raise ValueError("組合檔缺少 layout 區塊")
    modules = data.get("modules") or {}
    if not isinstance(modules, dict):
        modules = {}
    restored = restore_missing_modules(modules)
    layout, recipe_name, grid_vars = layout_from_dict(layout_data)
    title = str(data.get("title", recipe_name)).strip()
    operations = data.get("operations") or []
    if not isinstance(operations, list):
        operations = []
    undo_stack: list[ComposeLayout] = []
    for raw in data.get("undo_snapshots") or []:
        if isinstance(raw, dict):
            try:
                undo_stack.append(layout_snapshot_from_dict(raw))
            except (ValueError, KeyError, TypeError):
                pass
    redo_stack: list[ComposeLayout] = []
    for raw in data.get("redo_snapshots") or []:
        if isinstance(raw, dict):
            try:
                redo_stack.append(layout_snapshot_from_dict(raw))
            except (ValueError, KeyError, TypeError):
                pass
    redo_steps = data.get("redo_steps") or []
    if not isinstance(redo_steps, list):
        redo_steps = []
    return layout, title, grid_vars, operations, restored, undo_stack, redo_stack, redo_steps
