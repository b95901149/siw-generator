"""DXF / STL export for composed module layouts."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import ezdxf
from ezdxf import units

from siw_generator.compose_cst_export import (
    _RECT_EPS,
    _is_slot_via,
    _scale_via,
    _world_point,
)
from siw_generator.compose_geometry import (
    ComposeLayout,
    PlacedModule,
    cell_bounds,
    cell_center,
    grid_bounds,
)
from siw_generator.custom_geometry import CustomVia, CustomViaType, via_copper_z_range_mm
from siw_generator.materials import get_material
from siw_generator.stackup import StackupParams
from siw_generator.stl_export import _box_triangles, _cylinder_triangles, _normal
from siw_generator.via_shapes import slot_outline


def _extrude_polygon_tris(
    outline: list[tuple[float, float]],
    z0: float,
    z1: float,
) -> list[
    tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
]:
    if len(outline) < 3:
        return []
    n = len(outline)
    top = [(x, y, z1) for x, y in outline]
    bottom = [(x, y, z0) for x, y in outline]
    tris: list[
        tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
    ] = []
    for i in range(1, n - 1):
        tris.append((top[0], top[i], top[i + 1]))
        tris.append((bottom[0], bottom[i + 1], bottom[i]))
    for i in range(n):
        j = (i + 1) % n
        tris.append((bottom[i], bottom[j], top[j]))
        tris.append((bottom[i], top[j], top[i]))
    return tris


@dataclass(frozen=True)
class _StackupRect:
    x0: float
    x1: float
    y0: float
    y1: float
    stackup: StackupParams
    material_key: str


@dataclass(frozen=True)
class _PortSegment:
    x0: float
    y0: float
    x1: float
    y1: float
    label: str


def _rect_contained(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    ix0, iy0, ix1, iy1 = inner
    ox0, oy0, ox1, oy1 = outer
    return (
        ix0 >= ox0 - _RECT_EPS
        and iy0 >= oy0 - _RECT_EPS
        and ix1 <= ox1 + _RECT_EPS
        and iy1 <= oy1 + _RECT_EPS
    )


def _cell_in_substrate_frame(col: int, row: int, layout: ComposeLayout) -> bool:
    if layout.substrate_frame is None:
        return False
    return _rect_contained(cell_bounds(col, row, layout), layout.substrate_frame)


def iter_compose_stackup_rects(layout: ComposeLayout) -> list[_StackupRect]:
    rects: list[_StackupRect] = []

    if layout.substrate_frame is not None:
        fx0, fy0, fx1, fy1 = layout.substrate_frame
        rects.append(
            _StackupRect(
                fx0,
                fx1,
                fy0,
                fy1,
                layout.fill_stackup,
                layout.fill_material,
            )
        )

    for col, row in sorted(layout.filled_cells):
        if (col, row) in layout.placements:
            continue
        if _cell_in_substrate_frame(col, row, layout):
            continue
        x0, y0, x1, y1 = cell_bounds(col, row, layout)
        rects.append(_StackupRect(x0, x1, y0, y1, layout.fill_stackup, layout.fill_material))

    for placed in layout.placements.values():
        if _cell_in_substrate_frame(placed.col, placed.row, layout):
            continue
        x0, y0, x1, y1 = cell_bounds(placed.col, placed.row, layout)
        rects.append(
            _StackupRect(
                x0,
                x1,
                y0,
                y1,
                placed.module.stackup,
                placed.module.material,
            )
        )
    return rects


def iter_compose_port_segments(layout: ComposeLayout) -> list[_PortSegment]:
    segments: list[_PortSegment] = []
    for idx, port in enumerate(layout.ports, start=1):
        x0, y0, x1, y1 = cell_bounds(port.col, port.row, layout)
        half_w = port.width_mm / 2.0
        label = f"PORT{idx}"
        if port.edge == "left":
            px = x0
            segments.append(
                _PortSegment(px, port.position_mm - half_w, px, port.position_mm + half_w, label)
            )
        elif port.edge == "right":
            px = x1
            segments.append(
                _PortSegment(px, port.position_mm - half_w, px, port.position_mm + half_w, label)
            )
        elif port.edge == "bottom":
            py = y0
            segments.append(
                _PortSegment(port.position_mm - half_w, py, port.position_mm + half_w, py, label)
            )
        else:
            py = y1
            segments.append(
                _PortSegment(port.position_mm - half_w, py, port.position_mm + half_w, py, label)
            )
    return segments


def _world_slot_outline(
    placed: PlacedModule,
    cx: float,
    cy: float,
    via: CustomVia,
) -> list[tuple[float, float]]:
    length = float(via.length_mm or via.w_mm)
    width = float(via.w_mm)
    corner = via.corner_r_mm if via.corner_r_mm is not None else min(width, length) / 2.0
    outline = slot_outline(via.x_mm, via.y_mm, length, width, corner)
    return [_world_point(placed, cx, cy, px, py) for px, py in outline]


def _world_square_corners(
    placed: PlacedModule,
    cx: float,
    cy: float,
    via: CustomVia,
) -> list[tuple[float, float]]:
    half_w = via.w_mm / 2.0
    half_h = via.h_mm / 2.0
    corners = (
        (via.x_mm - half_w, via.y_mm - half_h),
        (via.x_mm + half_w, via.y_mm - half_h),
        (via.x_mm + half_w, via.y_mm + half_h),
        (via.x_mm - half_w, via.y_mm + half_h),
    )
    return [_world_point(placed, cx, cy, px, py) for px, py in corners]


def _add_rect(msp, corners: tuple[tuple[float, float], ...], layer: str) -> None:
    msp.add_lwpolyline(
        [(*pt, 0.0) for pt in corners],
        close=True,
        dxfattribs={"layer": layer},
    )


def export_compose_dxf(
    layout: ComposeLayout,
    output_path: str | Path,
    *,
    design_name: str = "Compose",
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new("R2010", units=units.MM)
    msp = doc.modelspace()
    doc.layers.add("DIELECTRIC_BOUNDARY", color=3)
    doc.layers.add("COPPER_TOP", color=5)
    doc.layers.add("COPPER_BOTTOM", color=5)
    doc.layers.add("VIA_HOLE", color=1)
    doc.layers.add("INFO", color=8)

    for rect in iter_compose_stackup_rects(layout):
        corners = (
            (rect.x0, rect.y0),
            (rect.x1, rect.y0),
            (rect.x1, rect.y1),
            (rect.x0, rect.y1),
        )
        _add_rect(msp, corners, "DIELECTRIC_BOUNDARY")
        _add_rect(msp, corners, "COPPER_TOP")
        _add_rect(msp, corners, "COPPER_BOTTOM")

    for placed in layout.placements.values():
        cx, cy = cell_center(placed.col, placed.row, layout)
        module = placed.module
        for via in module.vias:
            scaled = _scale_via(via, placed.scale_x, placed.scale_y)
            if _is_slot_via(scaled):
                outline = _world_slot_outline(placed, cx, cy, scaled)
                msp.add_lwpolyline(
                    [(*pt, 0.0) for pt in outline],
                    close=True,
                    dxfattribs={"layer": "VIA_HOLE"},
                )
            elif scaled.via_type is CustomViaType.CIRCLE:
                wx, wy = _world_point(placed, cx, cy, scaled.x_mm, scaled.y_mm)
                msp.add_circle(
                    center=(wx, wy),
                    radius=scaled.w_mm / 2.0,
                    dxfattribs={"layer": "VIA_HOLE"},
                )
            elif scaled.via_type is CustomViaType.SQUARE:
                corners = _world_square_corners(placed, cx, cy, scaled)
                msp.add_lwpolyline(
                    [(*pt, 0.0) for pt in corners],
                    close=True,
                    dxfattribs={"layer": "VIA_HOLE"},
                )

    for seg in iter_compose_port_segments(layout):
        if seg.label not in doc.layers:
            doc.layers.add(seg.label, color=6)
        msp.add_line(
            (seg.x0, seg.y0),
            (seg.x1, seg.y1),
            dxfattribs={"layer": seg.label},
        )

    gx0, gy0, gx1, gy1 = grid_bounds(layout)
    stack = layout.fill_stackup
    info_lines = [
        "CST_IMPORT=1 units=mm origin=grid_center",
        f"design={design_name}",
        f"grid_mm={layout.total_width_mm}x{layout.total_height_mm}",
        f"modules={len(layout.placements)}",
        f"ports={len(layout.ports)}",
        f"fill_material={layout.fill_material}",
        f"substrate_height_mm={stack.substrate_height_mm}",
        f"copper_thickness_um={stack.copper_thickness_um:.0f}",
    ]
    if layout.substrate_frame is not None:
        fx0, fy0, fx1, fy1 = layout.substrate_frame
        info_lines.append(f"substrate_frame={fx0:.4f},{fy0:.4f},{fx1:.4f},{fy1:.4f}")

    for idx, line in enumerate(info_lines):
        msp.add_text(
            line,
            height=0.15,
            dxfattribs={"layer": "INFO"},
        ).set_placement((gx0, gy1 + 0.4 + idx * 0.2))

    doc.saveas(output)
    return output


def _append_square_via_tris(
    triangles: list,
    placed: PlacedModule,
    cx: float,
    cy: float,
    via: CustomVia,
    z0: float,
    z1: float,
) -> None:
    corners = _world_square_corners(placed, cx, cy, via)
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    cz = (z0 + z1) / 2.0
    triangles.extend(_box_triangles((x0 + x1) / 2.0, (y0 + y1) / 2.0, cz, x1 - x0, y1 - y0, z1 - z0))


def export_compose_stl(layout: ComposeLayout, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    triangles: list[
        tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]
    ] = []

    for rect in iter_compose_stackup_rects(layout):
        z = rect.stackup.z_bounds_centered()
        cx = (rect.x0 + rect.x1) / 2.0
        cy = (rect.y0 + rect.y1) / 2.0
        lx = rect.x1 - rect.x0
        ly = rect.y1 - rect.y0
        for key in ("substrate", "bottom_copper", "top_copper"):
            z0, z1 = z[key]
            triangles.extend(_box_triangles(cx, cy, (z0 + z1) / 2.0, lx, ly, z1 - z0))

    for placed in layout.placements.values():
        cx, cy = cell_center(placed.col, placed.row, layout)
        module = placed.module
        for via in module.vias:
            scaled = _scale_via(via, placed.scale_x, placed.scale_y)
            z0, z1 = via_copper_z_range_mm(
                scaled.via_role,
                substrate_height_mm=module.stackup.substrate_height_mm,
                copper_thickness_mm=module.stackup.copper_thickness_mm,
            )
            if _is_slot_via(scaled):
                outline = _world_slot_outline(placed, cx, cy, scaled)
                triangles.extend(_extrude_polygon_tris(outline, z0, z1))
            elif scaled.via_type is CustomViaType.CIRCLE:
                wx, wy = _world_point(placed, cx, cy, scaled.x_mm, scaled.y_mm)
                radius = scaled.w_mm / 2.0 * max(placed.scale_x, placed.scale_y)
                triangles.extend(_cylinder_triangles(wx, wy, z0, z1, radius))
            elif scaled.via_type is CustomViaType.SQUARE:
                _append_square_via_tris(triangles, placed, cx, cy, scaled, z0, z1)

    with output.open("wb") as fh:
        fh.write(b"\0" * 80)
        fh.write(struct.pack("<I", len(triangles)))
        for v1, v2, v3 in triangles:
            nx, ny, nz = _normal(v1, v2, v3)
            fh.write(struct.pack("<3f", nx, ny, nz))
            fh.write(struct.pack("<3f", *v1))
            fh.write(struct.pack("<3f", *v2))
            fh.write(struct.pack("<3f", *v3))
            fh.write(struct.pack("<H", 0))

    return output


def write_compose_parameter_report(
    layout: ComposeLayout,
    output_path: str | Path,
    *,
    design_name: str = "Compose",
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stack = layout.fill_stackup
    gx0, gy0, gx1, gy1 = grid_bounds(layout)
    fill_mat = get_material(layout.fill_material)

    lines = [
        "SIW 組合版面參數紀錄",
        "=" * 50,
        f"產生時間   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"設計名稱   : {design_name}",
        "",
        "[組合網格]",
        f"  M × N      : {layout.m_count} × {layout.n_count}",
        f"  總寬 (X)   : {layout.total_width_mm} mm",
        f"  總高 (Y)   : {layout.total_height_mm} mm",
        f"  網格邊界   : X [{gx0:.4f}, {gx1:.4f}]  Y [{gy0:.4f}, {gy1:.4f}]",
        f"  已放置 module : {len(layout.placements)}",
        f"  填補 cell  : {len(layout.filled_cells)}",
        f"  Port 數    : {len(layout.ports)}",
        "",
        "[填補基板]",
        f"  材料       : {fill_mat.name}",
        f"  εr         : {fill_mat.er}",
        f"  tan δ      : {fill_mat.tan_delta}",
        f"  基板厚度 h : {stack.substrate_height_mm} mm",
        f"  銅厚       : {stack.copper_thickness_um:.0f} µm（每面）",
    ]
    if layout.substrate_frame is not None:
        fx0, fy0, fx1, fy1 = layout.substrate_frame
        lines.extend(
            [
                "",
                "[切割基板外框]",
                f"  X [{fx0:.4f}, {fx1:.4f}]  Y [{fy0:.4f}, {fy1:.4f}]",
            ]
        )

    lines.append("")
    lines.append("[已放置 module]")
    for (col, row), placed in sorted(layout.placements.items()):
        mod = placed.module
        mat = get_material(mod.material)
        lines.append(
            f"  ({col},{row}) {placed.label or mod.kind} | "
            f"{mod.substrate_length_mm:.3f}×{mod.substrate_width_mm:.3f} mm | "
            f"{mat.name} | via {len(mod.vias)} | rot {placed.rotation_deg}°"
        )

    if layout.ports:
        lines.extend(["", "[Port]"])
        for idx, port in enumerate(layout.ports, start=1):
            lines.append(
                f"  Port{idx}: cell=({port.col},{port.row}) edge={port.edge} "
                f"pos={port.position_mm:.4f} mm W={port.width_mm:.4f} mm"
            )

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def write_compose_import_notes(
    layout: ComposeLayout,
    output_path: str | Path,
    *,
    design_name: str = "Compose",
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stack = layout.fill_stackup
    fill_mat = get_material(layout.fill_material)
    z = stack.z_bounds_centered()

    text = f"""CST Studio Suite 匯入說明 - SIW Compose
========================================
組合名稱：{design_name}
網格：{layout.m_count}×{layout.n_count}，總尺寸 {layout.total_width_mm}×{layout.total_height_mm} mm
原點：組合網格中心，Z 在堆疊中心

建議流程
--------
1) 執行 compose_cst_macro.bas（Macro > Run Macro）
2) 或匯入 compose_cst.stl / compose_cst.dxf 後指派材料

套件檔案
--------
  compose_cst_macro.bas  — VBA 巨集（基板、via、Port 一次建立）
  compose_cst.dxf        — 2D 圖層（DIELECTRIC_BOUNDARY / COPPER / VIA_HOLE / PORT*）
  compose_cst.stl        — 3D 實體（基板、銅箔、via）
  compose_params.txt     — 組合參數紀錄

幾何摘要
--------
  module 數   : {len(layout.placements)}
  填補 cell   : {len(layout.filled_cells)}
  Port 數     : {len(layout.ports)}
  填補材料    : {fill_mat.cst_material_name}
  基板厚度 h  : {stack.substrate_height_mm} mm
  銅厚（每面）: {stack.copper_thickness_mm} mm
  Z 基板      : {z['substrate'][0]:.4f} .. {z['substrate'][1]:.4f} mm

Slot Via
------
  圓角矩形 Slot 以 3 Brick + 4 Cylinder 建立（與單一 SIW AddOneSlot 相同）

清除選項
--------
  若巨集含 ClearPreviousCompose，Run Macro 前會刪除既有 siw / vias 元件與全部 Port
"""
    output.write_text(text, encoding="utf-8")
    return output
