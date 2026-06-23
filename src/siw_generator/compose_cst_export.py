"""CST VBA export for composed module layouts."""

from __future__ import annotations

import re
from pathlib import Path

from siw_generator.compose_geometry import (
    ComposeLayout,
    ComposePort,
    PlacedModule,
    cell_bounds,
    cell_center,
    cell_stackup,
    export_center_offset_mm,
    port_aperture_span,
    transform_placed_local,
)
from siw_generator.custom_geometry import CustomVia, CustomViaType, via_copper_z_range_mm
from siw_generator.cst_export import (
    _COPPER_MATERIAL,
    _fmt,
    _vba_clear_project_sub,
    _vba_ensure_material_from_library_sub,
)
from siw_generator.materials import SubstrateMaterial, get_material

_VIA_INDEX = 0
_BRICK_INDEX = 0
_RECT_EPS = 1e-4
_EXPORT_OX = 0.0
_EXPORT_OY = 0.0


def _sx(value: float) -> float:
    return value - _EXPORT_OX


def _sy(value: float) -> float:
    return value - _EXPORT_OY


def _next_via_name() -> str:
    global _VIA_INDEX  # noqa: PLW0603
    _VIA_INDEX += 1
    return f"via_{_VIA_INDEX}"


def _next_brick_name(prefix: str) -> str:
    global _BRICK_INDEX  # noqa: PLW0603
    _BRICK_INDEX += 1
    return f"{prefix}_{_BRICK_INDEX}"


def _rng(lo: float, hi: float) -> str:
    return f'"{_fmt(lo)}", "{_fmt(hi)}"'


def _z_substrate(h_mm: float) -> str:
    half = h_mm / 2.0
    return _rng(-half, half)


def _z_copper_bottom(h_mm: float, cu_mm: float) -> str:
    half = h_mm / 2.0
    return _rng(-half - cu_mm, -half)


def _z_copper_top(h_mm: float, cu_mm: float) -> str:
    half = h_mm / 2.0
    return _rng(half, half + cu_mm)


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


def _emit_stackup_bricks(
    lines: list[str],
    *,
    material: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    h_mm: float,
    cu_mm: float,
    name_prefix: str,
) -> None:
    lines.extend(
        _vba_brick_direct(
            _next_brick_name(name_prefix),
            material,
            x0,
            x1,
            y0,
            y1,
            _z_substrate(h_mm),
        )
    )
    lines.append("")
    lines.extend(
        _vba_brick_direct(
            _next_brick_name(f"{name_prefix}_cu_bot"),
            _COPPER_MATERIAL,
            x0,
            x1,
            y0,
            y1,
            _z_copper_bottom(h_mm, cu_mm),
        )
    )
    lines.append("")
    lines.extend(
        _vba_brick_direct(
            _next_brick_name(f"{name_prefix}_cu_top"),
            _COPPER_MATERIAL,
            x0,
            x1,
            y0,
            y1,
            _z_copper_top(h_mm, cu_mm),
        )
    )
    lines.append("")


def _vba_brick_direct(
    name: str,
    material: str,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z_rng: str,
    *,
    component: str = "siw",
) -> list[str]:
    return [
        "    With Brick",
        "        .Reset",
        f'        .Name "{name}"',
        f'        .Component "{component}"',
        f'        .Material "{material}"',
        f"        .Xrange {_rng(_sx(x0), _sx(x1))}",
        f"        .Yrange {_rng(_sy(y0), _sy(y1))}",
        f"        .Zrange {z_rng}",
        "        .Create",
        "    End With",
    ]


def _vba_cylinder_direct(
    name: str,
    cx: float,
    cy: float,
    radius: float,
    z_rng: str,
) -> list[str]:
    return [
        "    With Cylinder",
        "        .Reset",
        f'        .Name "{name}"',
        '        .Component "vias"',
        f'        .Material "{_COPPER_MATERIAL}"',
        '        .Axis "z"',
        f'        .Xcenter "{_fmt(_sx(cx))}"',
        f'        .Ycenter "{_fmt(_sy(cy))}"',
        '        .Zcenter "0"',
        f'        .OuterRadius "{_fmt(radius)}"',
        '        .InnerRadius "0"',
        f"        .Zrange {z_rng}",
        "        .Create",
        "    End With",
    ]


def _vba_port_direct(port_index: int, port: ComposePort, layout: ComposeLayout) -> list[str]:
    x0, y0, x1, y1 = cell_bounds(port.col, port.row, layout)
    span_lo, span_hi = port_aperture_span(port)
    if port.edge == "left":
        px = x0
        orientation = "xmin"
        x_rng = _rng(_sx(px), _sx(px))
        y_rng = _rng(_sy(span_lo), _sy(span_hi))
    elif port.edge == "right":
        px = x1
        orientation = "xmax"
        x_rng = _rng(_sx(px), _sx(px))
        y_rng = _rng(_sy(span_lo), _sy(span_hi))
    elif port.edge == "bottom":
        py = y0
        orientation = "ymin"
        x_rng = _rng(_sx(span_lo), _sx(span_hi))
        y_rng = _rng(_sy(py), _sy(py))
    else:
        py = y1
        orientation = "ymax"
        x_rng = _rng(_sx(span_lo), _sx(span_hi))
        y_rng = _rng(_sy(py), _sy(py))

    stackup = cell_stackup(layout, port.col, port.row)
    z_lo, z_hi = stackup.z_bounds_centered()["full_stack"]
    return [
        "    With Port",
        "        .Reset",
        f'        .PortNumber "{port_index}"',
        '        .NumberOfModes "1"',
        f'        .Label "Port{port_index}"',
        '        .Coordinates "Free"',
        f'        .Orientation "{orientation}"',
        '        .PortOnBound "False"',
        '        .ClipPickedPortToBound "False"',
        f"        .Xrange {x_rng}",
        f"        .Yrange {y_rng}",
        f"        .Zrange {_rng(z_lo, z_hi)}",
        "        .Create",
        "    End With",
    ]


def _is_slot_via(via: CustomVia) -> bool:
    if via.via_type == CustomViaType.SLOT:
        return True
    length = via.length_mm
    return length is not None and length > via.w_mm * 1.05 and via.corner_r_mm is not None


def _clamp_slot_corner(length: float, width: float, corner: float) -> float:
    return max(0.0, min(corner, length / 2.0, width / 2.0))


def _world_point(
    placed: PlacedModule,
    cx: float,
    cy: float,
    lx: float,
    ly: float,
) -> tuple[float, float]:
    tx, ty = transform_placed_local(placed, lx, ly)
    return cx + tx, cy + ty


def _world_aabb_from_local_rect(
    placed: PlacedModule,
    cx: float,
    cy: float,
    x0: float,
    x1: float,
    y0: float,
    y1: float,
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for lx, ly in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        wx, wy = _world_point(placed, cx, cy, lx, ly)
        xs.append(wx)
        ys.append(wy)
    return min(xs), max(xs), min(ys), max(ys)


def _vba_slot_parts_direct(
    base_name: str,
    placed: PlacedModule,
    cx: float,
    cy: float,
    via: CustomVia,
    z_lo: float,
    z_hi: float,
) -> list[str]:
    """Rounded-rectangle slot from bricks + corner cylinders (same as single-SIW AddOneSlot)."""
    length = float(via.length_mm or via.w_mm)
    width = float(via.w_mm)
    corner = via.corner_r_mm if via.corner_r_mm is not None else min(width, length) / 2.0
    radius = _clamp_slot_corner(length, width, corner)
    vx, vy = via.x_mm, via.y_mm
    half_l = length / 2.0
    half_w = width / 2.0
    z_rng = _rng(z_lo, z_hi)
    lines: list[str] = []

    if length <= 2.0 * radius + _RECT_EPS and width <= 2.0 * radius + _RECT_EPS:
        wx, wy = _world_point(placed, cx, cy, vx, vy)
        lines.extend(_vba_cylinder_direct(base_name, wx, wy, min(half_l, half_w), z_rng))
        return lines

    def brick(suffix: str, x0: float, x1: float, y0: float, y1: float) -> None:
        wx0, wx1, wy0, wy1 = _world_aabb_from_local_rect(placed, cx, cy, x0, x1, y0, y1)
        lines.extend(
            _vba_brick_direct(
                f"{base_name}{suffix}",
                _COPPER_MATERIAL,
                wx0,
                wx1,
                wy0,
                wy1,
                z_rng,
                component="vias",
            )
        )

    def cyl(suffix: str, lx: float, ly: float) -> None:
        wx, wy = _world_point(placed, cx, cy, lx, ly)
        lines.extend(_vba_cylinder_direct(f"{base_name}{suffix}", wx, wy, radius, z_rng))

    brick("_main", vx - half_l + radius, vx + half_l - radius, vy - half_w, vy + half_w)
    brick("_left", vx - half_l, vx - half_l + radius, vy - half_w + radius, vy + half_w - radius)
    brick("_right", vx + half_l - radius, vx + half_l, vy - half_w + radius, vy + half_w - radius)
    cyl("_c1", vx - half_l + radius, vy - half_w + radius)
    cyl("_c2", vx + half_l - radius, vy - half_w + radius)
    cyl("_c3", vx + half_l - radius, vy + half_w - radius)
    cyl("_c4", vx - half_l + radius, vy + half_w - radius)
    return lines


def _scale_via(via: CustomVia, scale_x: float, scale_y: float) -> CustomVia:
    scale = max(scale_x, scale_y)
    if abs(scale_x - 1.0) <= _RECT_EPS and abs(scale_y - 1.0) <= _RECT_EPS:
        return via
    length = via.length_mm * scale_x if via.length_mm is not None else None
    corner = via.corner_r_mm * scale if via.corner_r_mm is not None else None
    return CustomVia(
        x_mm=via.x_mm,
        y_mm=via.y_mm,
        via_type=via.via_type,
        via_role=via.via_role,
        w_mm=via.w_mm * scale_y if via.via_type is CustomViaType.SLOT else via.w_mm * scale,
        h_mm=via.h_mm * scale,
        length_mm=length,
        corner_r_mm=corner,
    )


def _emit_via(
    lines: list[str],
    placed: PlacedModule,
    cx: float,
    cy: float,
    via: CustomVia,
    *,
    h_mm: float,
    cu_mm: float,
) -> None:
    z_lo, z_hi = via_copper_z_range_mm(
        via.via_role,
        substrate_height_mm=h_mm,
        copper_thickness_mm=cu_mm,
    )
    z_rng = _rng(z_lo, z_hi)
    tx, ty = transform_placed_local(placed, via.x_mm, via.y_mm)
    wx, wy = cx + tx, cy + ty

    if _is_slot_via(via):
        lines.extend(_vba_slot_parts_direct(_next_via_name(), placed, cx, cy, via, z_lo, z_hi))
        lines.append("")
        return
    if via.via_type == CustomViaType.CIRCLE:
        lines.extend(_vba_cylinder_direct(_next_via_name(), wx, wy, via.w_mm / 2.0, z_rng))
        lines.append("")
        return
    if via.via_type == CustomViaType.SQUARE:
        half_w = via.w_mm / 2.0
        half_h = via.h_mm / 2.0
        corners_local = (
            (via.x_mm - half_w, via.y_mm - half_h),
            (via.x_mm + half_w, via.y_mm - half_h),
            (via.x_mm + half_w, via.y_mm + half_h),
            (via.x_mm - half_w, via.y_mm + half_h),
        )
        xs: list[float] = []
        ys: list[float] = []
        for px, py in corners_local:
            lx, ly = transform_placed_local(placed, px, py)
            xs.append(cx + lx)
            ys.append(cy + ly)
        lines.extend(
            _vba_brick_direct(
                _next_via_name(),
                _COPPER_MATERIAL,
                min(xs),
                max(xs),
                min(ys),
                max(ys),
                z_rng,
                component="vias",
            )
        )
        lines.append("")


def _emit_placed_module(lines: list[str], placed: PlacedModule, layout: ComposeLayout) -> None:
    module = placed.module
    mat = get_material(module.material)
    h = module.stackup.substrate_height_mm
    cu = module.stackup.copper_thickness_mm
    x0, y0, x1, y1 = cell_bounds(placed.col, placed.row, layout)
    cx, cy = cell_center(placed.col, placed.row, layout)
    if not _cell_in_substrate_frame(placed.col, placed.row, layout):
        _emit_stackup_bricks(
            lines,
            material=mat.cst_material_name,
            x0=x0,
            x1=x1,
            y0=y0,
            y1=y1,
            h_mm=h,
            cu_mm=cu,
            name_prefix="substrate",
        )
    for via in module.vias:
        scaled_via = _scale_via(via, placed.scale_x, placed.scale_y)
        _emit_via(lines, placed, cx, cy, scaled_via, h_mm=h, cu_mm=cu)


def _mat_sub_key(material_key: str) -> str:
    safe = re.sub(r"[^\w]", "_", material_key.strip())
    if not safe:
        safe = "default"
    if safe[0].isdigit():
        safe = f"m_{safe}"
    return safe


def _collect_materials(layout: ComposeLayout) -> dict[str, SubstrateMaterial]:
    materials: dict[str, SubstrateMaterial] = {}
    for key in (layout.fill_material,):
        mat = get_material(key)
        materials[mat.key] = mat
    for placed in layout.placements.values():
        mat = get_material(placed.module.material)
        materials[mat.key] = mat
    return materials


def _vba_define_material_literal_sub(sub_name: str, mat: SubstrateMaterial) -> list[str]:
    name = mat.cst_material_name
    er = _fmt(mat.er)
    tand = _fmt(mat.tan_delta)
    return [
        f"Sub {sub_name}()",
        "    On Error Resume Next",
        f'    Material.Delete "{name}"',
        "    On Error GoTo 0",
        "    With Material",
        "        .Reset",
        f'        .Name "{name}"',
        '        .FrqType "all"',
        '        .Type "Normal"',
        '        .MaterialUnit "Frequency", "GHz"',
        '        .MaterialUnit "Geometry", "mm"',
        f'        .Epsilon "{er}"',
        '        .Mu "1.0"',
        '        .Kappa "0.0"',
        f'        .TanD "{tand}"',
        '        .TanDFreq "10.0"',
        '        .TanDGiven "True"',
        '        .Colour "0.0", "1.0", "1.0"',
        "        .Create",
        "    End With",
        "End Sub",
        "",
    ]


def _vba_compose_main_material_calls(materials: dict[str, SubstrateMaterial]) -> list[str]:
    """Compose CST macro: copper (library-equivalent), then substrate ensure+define."""
    lines: list[str] = [
        "    Call EnsureCopperMaterial",
        "",
    ]
    for key in materials:
        safe = _mat_sub_key(key)
        lines.append(f"    Call EnsureComposeMat_{safe}")
        lines.append("")
        lines.append(f"    Call DefineComposeMat_{safe}")
        lines.append("")
    return lines


def _vba_define_compose_copper_annealed() -> list[str]:
    """Define Copper (annealed) as Lossy metal (matches CST Default material library)."""
    name = _COPPER_MATERIAL
    return [
        "Sub EnsureCopperMaterial()",
        f"    ' Compose: \"{name}\" Lossy metal, sigma=5.8e7 S/m (library-equivalent)",
        "    On Error Resume Next",
        f'    Material.Delete "{name}"',
        "    On Error GoTo 0",
        "    With Material",
        "        .Reset",
        f'        .Name "{name}"',
        '        .FrqType "all"',
        '        .Type "Lossy metal"',
        '        .MaterialUnit "Frequency", "GHz"',
        '        .MaterialUnit "Geometry", "mm"',
        '        .Mu "1.0"',
        '        .Kappa "5.8e+007"',
        '        .Rho "8930.0"',
        '        .Colour "1.0", "1.0", "0.0"',
        "        .Create",
        "    End With",
        "End Sub",
        "",
    ]


def _vba_material_helpers(materials: dict[str, SubstrateMaterial]) -> list[str]:
    lines: list[str] = []
    for key, mat in materials.items():
        safe = _mat_sub_key(key)
        define = f"DefineComposeMat_{safe}"
        ensure = f"EnsureComposeMat_{safe}"
        lines.extend(
            _vba_ensure_material_from_library_sub(
                ensure,
                mat.cst_material_name,
                fallback_call=f"Call {define}",
            )
        )
        lines.extend(_vba_define_material_literal_sub(define, mat))
    lines.extend(_vba_define_compose_copper_annealed())
    return lines


def build_compose_cst_vba_text(
    layout: ComposeLayout,
    *,
    title: str = "Compose",
    clear_existing: bool = True,
) -> str:
    global _VIA_INDEX, _BRICK_INDEX, _EXPORT_OX, _EXPORT_OY  # noqa: PLW0603
    _VIA_INDEX = 0
    _BRICK_INDEX = 0
    _EXPORT_OX, _EXPORT_OY = export_center_offset_mm(layout)

    materials = _collect_materials(layout)

    lines: list[str] = [
        "' CST VBA macro - SIW compose layout",
        f"' Compose: {title}",
        f"' Units: mm | Origin: XY centered (offset {_fmt(_EXPORT_OX)}, {_fmt(_EXPORT_OY)} mm), Z at stack center",
        "' Re-run macro to rebuild geometry",
        "",
        "Sub Main",
        "",
    ]
    if clear_existing:
        lines.extend(["    Call ClearPreviousCompose", ""])
    lines.extend(_vba_compose_main_material_calls(materials))
    lines.extend(["    Call EnsureComposeComponents", ""])

    if layout.substrate_frame is not None:
        fx0, fy0, fx1, fy1 = layout.substrate_frame
        fill_mat = get_material(layout.fill_material)
        h = layout.fill_stackup.substrate_height_mm
        cu = layout.fill_stackup.copper_thickness_mm
        _emit_stackup_bricks(
            lines,
            material=fill_mat.cst_material_name,
            x0=fx0,
            x1=fx1,
            y0=fy0,
            y1=fy1,
            h_mm=h,
            cu_mm=cu,
            name_prefix="frame",
        )

    for col, row in sorted(layout.filled_cells):
        if (col, row) in layout.placements:
            continue
        if _cell_in_substrate_frame(col, row, layout):
            continue
        x0, y0, x1, y1 = cell_bounds(col, row, layout)
        fill_mat = get_material(layout.fill_material)
        h = layout.fill_stackup.substrate_height_mm
        cu = layout.fill_stackup.copper_thickness_mm
        _emit_stackup_bricks(
            lines,
            material=fill_mat.cst_material_name,
            x0=x0,
            x1=x1,
            y0=y0,
            y1=y1,
            h_mm=h,
            cu_mm=cu,
            name_prefix="fill",
        )

    for placed in layout.placements.values():
        _emit_placed_module(lines, placed, layout)

    for idx, port in enumerate(layout.ports, start=1):
        lines.extend(_vba_port_direct(idx, port, layout))
        lines.append("")

    lines.append("    ' Geometry exported centered at XY origin; press Space in CST to fit view")
    lines.append("End Sub")
    lines.append("")
    lines.extend(_vba_material_helpers(materials))
    lines.extend(_vba_compose_helpers())
    return "\n".join(lines)


def _vba_compose_helpers() -> list[str]:
    lines = _vba_clear_project_sub("ClearPreviousCompose")
    lines.extend(
        [
            "Sub EnsureComposeComponents()",
            "    On Error Resume Next",
            '    Component.New "siw"',
            '    Component.New "vias"',
            "    On Error GoTo 0",
            "End Sub",
            "",
        ]
    )
    return lines


def export_compose_cst_package(
    layout: ComposeLayout,
    output_dir: str | Path,
    *,
    design_name: str = "Compose",
    clear_existing: bool = True,
) -> dict[str, str]:
    from siw_generator.compose_mesh_export import (
        export_compose_dxf,
        export_compose_stl,
        write_compose_import_notes,
        write_compose_parameter_report,
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    vba = build_compose_cst_vba_text(layout, title=design_name, clear_existing=clear_existing)
    macro = out / "compose_cst_macro.bas"
    macro.write_text(vba, encoding="utf-8")
    files: dict[str, str] = {
        "vba_macro": str(macro),
        "dxf": str(export_compose_dxf(layout, out / "compose_cst.dxf", design_name=design_name)),
        "stl": str(export_compose_stl(layout, out / "compose_cst.stl")),
        "import_notes": str(
            write_compose_import_notes(layout, out / "CST_IMPORT.txt", design_name=design_name)
        ),
        "params_txt": str(
            write_compose_parameter_report(layout, out / "compose_params.txt", design_name=design_name)
        ),
    }
    return files
