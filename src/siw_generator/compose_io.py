"""Serialize / deserialize compose layout for recipe persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from siw_generator.app_paths import module_dir, recipe_dir
from siw_generator.compose_geometry import ComposeLayout, ComposePort, PlacedModule
from siw_generator.custom_io import load_module_file
from siw_generator.export_paths import resolve_recipe_stem
from siw_generator.stackup import StackupParams

COMPOSE_RECIPE_FORMAT = "siw-generator-compose-recipe"
COMPOSE_RECIPE_VERSION = 1


def _rel_module_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(module_dir().resolve()))
    except ValueError:
        return path.name


def _abs_module_path(rel: str) -> Path | None:
    text = rel.strip()
    if not text:
        return None
    candidate = module_dir() / text
    if candidate.is_file():
        return candidate
    fallback = module_dir() / Path(text).name
    return fallback if fallback.is_file() else None


def relative_module_ref(path: Path | None) -> str:
    """Relative path under module/ for persistence (filename if outside module dir)."""
    return _rel_module_path(path)


def layout_to_dict(layout: ComposeLayout, *, recipe_name: str = "", grid_vars: dict[str, str] | None = None) -> dict[str, Any]:
    grid_vars = grid_vars or {}
    return {
        "format": COMPOSE_RECIPE_FORMAT,
        "version": COMPOSE_RECIPE_VERSION,
        "recipe_name": recipe_name.strip(),
        "m_count": layout.m_count,
        "n_count": layout.n_count,
        "default_pitch_x_mm": layout.default_pitch_x_mm,
        "default_pitch_y_mm": layout.default_pitch_y_mm,
        "col_pitch_mm": list(layout.col_pitch_mm),
        "row_pitch_mm": list(layout.row_pitch_mm),
        "fill_material": layout.fill_material,
        "fill_stackup": {
            "substrate_height_mm": layout.fill_stackup.substrate_height_mm,
            "copper_thickness_um": layout.fill_stackup.copper_thickness_um,
        },
        "substrate_frame": list(layout.substrate_frame) if layout.substrate_frame else None,
        "filled_cells": [list(c) for c in sorted(layout.filled_cells)],
        "placements": [
            {
                "col": p.col,
                "row": p.row,
                "source": relative_module_ref(p.source_path),
                "label": p.label,
                "rotation_deg": p.rotation_deg,
                "mirror_x": p.mirror_x,
                "scale_x": p.scale_x,
                "scale_y": p.scale_y,
            }
            for p in layout.placements.values()
        ],
        "ports": [
            {
                "col": port.col,
                "row": port.row,
                "edge": port.edge,
                "position_mm": port.position_mm,
                "width_mm": port.width_mm,
                "via_index": port.via_index,
                "via_index_2": port.via_index_2,
                "span_a_mm": port.span_a_mm,
                "span_b_mm": port.span_b_mm,
            }
            for port in layout.ports
        ],
        "grid_vars": dict(grid_vars),
    }


def layout_from_dict(data: dict[str, Any]) -> tuple[ComposeLayout, str, dict[str, str]]:
    if data.get("format") not in (COMPOSE_RECIPE_FORMAT, None):
        raise ValueError(f"不支援的組合 recipe 格式：{data.get('format')}")
    fill = data.get("fill_stackup") or {}
    stack = StackupParams(
        substrate_height_mm=float(fill.get("substrate_height_mm", 0.127)),
        copper_thickness_mm=float(fill.get("copper_thickness_um", 15.0)) / 1000.0,
    )
    layout = ComposeLayout(
        m_count=int(data.get("m_count", 3)),
        n_count=int(data.get("n_count", 3)),
        default_pitch_x_mm=float(data.get("default_pitch_x_mm", 10.0)),
        default_pitch_y_mm=float(data.get("default_pitch_y_mm", 10.0)),
        col_pitch_mm=[float(x) for x in data.get("col_pitch_mm", [])],
        row_pitch_mm=[float(y) for y in data.get("row_pitch_mm", [])],
        filled_cells={tuple(int(c) for c in cell) for cell in data.get("filled_cells", [])},
        fill_stackup=stack,
        fill_material=str(data.get("fill_material", "rt5880_lossy")),
        ports=[],
        placements={},
    )
    frame = data.get("substrate_frame")
    if frame and len(frame) == 4:
        layout.substrate_frame = tuple(float(v) for v in frame)

    for raw in data.get("placements", []):
        col = int(raw["col"])
        row = int(raw["row"])
        src = _abs_module_path(str(raw.get("source", "")))
        if src is None:
            continue
        try:
            module = load_module_file(src)
        except (OSError, ValueError):
            continue
        layout.placements[(col, row)] = PlacedModule(
            col=col,
            row=row,
            module=module,
            source_path=src,
            label=str(raw.get("label", src.name)),
            rotation_deg=int(raw.get("rotation_deg", 0)),
            mirror_x=bool(raw.get("mirror_x", False)),
            scale_x=float(raw.get("scale_x", 1.0)),
            scale_y=float(raw.get("scale_y", 1.0)),
        )
    for raw in data.get("ports", []):
        layout.ports.append(
            ComposePort(
                col=int(raw["col"]),
                row=int(raw["row"]),
                edge=str(raw["edge"]),
                position_mm=float(raw["position_mm"]),
                width_mm=float(raw["width_mm"]),
                via_index=int(raw.get("via_index", -1)),
                via_index_2=int(raw.get("via_index_2", -1)),
                span_a_mm=float(raw.get("span_a_mm", 0.0)),
                span_b_mm=float(raw.get("span_b_mm", 0.0)),
            )
        )
    recipe_name = str(data.get("recipe_name", "")).strip()
    grid_vars = {str(k): str(v) for k, v in (data.get("grid_vars") or {}).items()}
    return layout, recipe_name, grid_vars


def compose_recipe_path(stem: str) -> Path:
    safe = resolve_recipe_stem(stem)
    return recipe_dir() / f"{safe}_compose.json"


def save_compose_recipe(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_compose_recipe(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != COMPOSE_RECIPE_FORMAT:
        raise ValueError(f"不支援的組合 recipe：{path.name}")
    return data
