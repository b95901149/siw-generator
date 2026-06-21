"""Export SIW geometry to DXF (including CST 2D import layers)."""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf import units

from siw_generator.siw_geometry import SIWGeometry
from siw_generator.via_shapes import rounded_rect_outline, slot_outline


def _add_rect(msp, corners: list[tuple[float, float]], layer: str) -> None:
    msp.add_lwpolyline(
        [(*pt, 0.0) for pt in corners],
        close=True,
        dxfattribs={"layer": layer},
    )


def export_siw_dxf(
    geometry: SIWGeometry,
    output_path: str | Path,
    *,
    cst_mode: bool = False,
) -> Path:
    """Write substrate outline and via circles to a DXF file."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new("R2010", units=units.MM)
    msp = doc.modelspace()
    corners = geometry.substrate_corners_mm
    p = geometry.params
    mat = p.substrate_material
    stack = p.stackup

    if cst_mode:
        doc.layers.add("DIELECTRIC_BOUNDARY", color=3)
        doc.layers.add("COPPER_TOP", color=5)
        doc.layers.add("COPPER_BOTTOM", color=5)
        doc.layers.add("VIA_HOLE", color=1)
        doc.layers.add("PORT1", color=6)
        doc.layers.add("PORT2", color=6)
        doc.layers.add("INFO", color=8)

        _add_rect(msp, corners, "DIELECTRIC_BOUNDARY")
        _add_rect(msp, corners, "COPPER_TOP")
        _add_rect(msp, corners, "COPPER_BOTTOM")
        via_layer = "VIA_HOLE"
    else:
        doc.layers.add("SUBSTRATE", color=3)
        doc.layers.add("VIAS", color=1)
        doc.layers.add("INFO", color=8)
        _add_rect(msp, corners, "SUBSTRATE")
        via_layer = "VIAS"

    for via in geometry.vias:
        msp.add_circle(
            center=(via.x_mm, via.y_mm),
            radius=via.diameter_mm / 2.0,
            dxfattribs={"layer": via_layer},
        )

    for slot in geometry.slot_vias:
        outline = slot_outline(
            slot.x_mm, slot.y_mm, slot.length_mm, slot.width_mm, slot.corner_r_mm
        )
        msp.add_lwpolyline(
            [(*pt, 0.0) for pt in outline],
            close=True,
            dxfattribs={"layer": via_layer},
        )

    for port in geometry.ports:
        if not port.enabled:
            continue
        layer = "PORT1" if port.name == "Port1" else "PORT2"
        msp.add_line(
            (port.x_mm, port.y_min_mm),
            (port.x_mm, port.y_max_mm),
            dxfattribs={"layer": layer},
        )

    z = stack.z_bounds_centered()
    info_lines = [
        f"material={mat.name}",
        f"center_freq_ghz={p.center_freq_ghz}",
        f"via_diameter_mm={p.via_diameter_mm}",
        f"substrate_xy_mm={p.substrate_length_mm}x{p.substrate_width_mm}",
        f"substrate_height_mm={stack.substrate_height_mm}",
        f"copper_thickness_um={stack.copper_thickness_um:.0f}",
        f"total_thickness_mm={stack.total_thickness_mm:.4f}",
        f"siw_width_mm={geometry.siw_width_mm:.4f}",
        f"via_pitch_mm={geometry.via_pitch_mm:.4f}",
        f"via_count={geometry.via_count}",
        f"er={p.er}",
        f"tan_delta={mat.tan_delta}",
        f"z_substrate_mm={z['substrate'][0]:.4f}..{z['substrate'][1]:.4f}",
    ]
    if geometry.is_slot and geometry.slot_params is not None:
        sp = geometry.slot_params
        info_lines.extend(
            [
                "via_type=rounded_rect_slot",
                f"slot_width_mm={sp.slot_width_mm}",
                f"slot_length_mm={sp.slot_length_mm}",
                f"slot_corner_r_mm={sp.slot_corner_r_mm}",
                f"slot_pitch_mm={sp.slot_pitch_mm}",
            ]
        )
    if cst_mode:
        info_lines.insert(0, "CST_IMPORT=1 units=mm origin=stack_center")

    for idx, line in enumerate(info_lines):
        msp.add_text(
            line,
            height=0.15,
            dxfattribs={"layer": "INFO"},
        ).set_placement(
            (-p.substrate_length_mm / 2.0, p.substrate_width_mm / 2.0 + 0.4 + idx * 0.2)
        )

    doc.saveas(output)
    return output
