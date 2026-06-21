"""Binary STL export for CST 3D import (no external dependencies)."""

from __future__ import annotations

import math
import struct
from pathlib import Path

from siw_generator.siw_geometry import SIWGeometry
from siw_generator.via_shapes import extrude_rounded_rect_triangles


def _normal(v1: tuple[float, float, float], v2: tuple[float, float, float], v3: tuple[float, float, float]) -> tuple[float, float, float]:
    ux, uy, uz = v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]
    vx, vy, vz = v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / length, ny / length, nz / length


def _box_triangles(
    cx: float,
    cy: float,
    cz: float,
    lx: float,
    ly: float,
    lz: float,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    hx, hy, hz = lx / 2.0, ly / 2.0, lz / 2.0
    corners = [
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz),
        (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz),
        (cx - hx, cy + hy, cz + hz),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    tris: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]] = []
    for i0, i1, i2, i3 in faces:
        a, b, c, d = corners[i0], corners[i1], corners[i2], corners[i3]
        tris.append((a, b, c))
        tris.append((a, c, d))
    return tris


def _cylinder_triangles(
    cx: float,
    cy: float,
    z0: float,
    z1: float,
    radius: float,
    segments: int = 24,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    tris: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]] = []
    top = (cx, cy, z1)
    bottom = (cx, cy, z0)
    ring_top: list[tuple[float, float, float]] = []
    ring_bottom: list[tuple[float, float, float]] = []

    for i in range(segments):
        angle = 2.0 * math.pi * i / segments
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        ring_top.append((x, y, z1))
        ring_bottom.append((x, y, z0))

    for i in range(segments):
        nxt = (i + 1) % segments
        tris.append((top, ring_top[i], ring_top[nxt]))
        tris.append((bottom, ring_bottom[nxt], ring_bottom[i]))
        tris.append((ring_bottom[i], ring_bottom[nxt], ring_top[nxt]))
        tris.append((ring_bottom[i], ring_top[nxt], ring_top[i]))

    return tris


def export_siw_stl(geometry: SIWGeometry, output_path: str | Path) -> Path:
    """Write substrate, copper layers, and vias as a binary STL solid."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    p = geometry.params
    stack = p.stackup
    z = stack.z_bounds_centered()

    triangles: list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]] = []

    def add_box(z0: float, z1: float) -> None:
        cz = (z0 + z1) / 2.0
        triangles.extend(
            _box_triangles(0.0, 0.0, cz, p.substrate_length_mm, p.substrate_width_mm, z1 - z0)
        )

    add_box(*z["substrate"])
    add_box(*z["bottom_copper"])
    add_box(*z["top_copper"])

    z0, z1 = z["full_stack"]
    if geometry.is_slot:
        for slot in geometry.slot_vias:
            triangles.extend(
                extrude_rounded_rect_triangles(
                    slot.x_mm,
                    slot.y_mm,
                    slot.length_mm,
                    slot.width_mm,
                    slot.corner_r_mm,
                    z0,
                    z1,
                )
            )
    else:
        radius = p.via_diameter_mm / 2.0
        for via in geometry.vias:
            triangles.extend(_cylinder_triangles(via.x_mm, via.y_mm, z0, z1, radius))

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
