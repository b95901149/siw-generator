"""2D/3D geometry for slot (rounded-rectangle) vias."""

from __future__ import annotations

import math


def _arc_points(
    xc: float,
    yc: float,
    radius: float,
    a0: float,
    a1: float,
    segments: int,
) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(segments + 1):
        a = a0 + (a1 - a0) * i / segments
        pts.append((xc + radius * math.cos(a), yc + radius * math.sin(a)))
    return pts


def _clamp_corner_r(length_x: float, width_y: float, corner_r: float) -> float:
    return max(0.0, min(corner_r, length_x / 2.0, width_y / 2.0))


def slot_outline(
    cx: float,
    cy: float,
    length_x: float,
    width_y: float,
    corner_r: float = 0.0,
    *,
    segments_per_arc: int = 16,
) -> list[tuple[float, float]]:
    """
    Rounded-rectangle slot along +X.

    Total length = length_x, width = width_y, corner fillet radius = corner_r
    (clamped to min(L, W) / 2). When R = W/2 the profile matches a standard obround.
    """
    length_x = float(length_x)
    width_y = float(width_y)
    if length_x <= 0 or width_y <= 0:
        return []

    radius = _clamp_corner_r(length_x, width_y, corner_r)
    half_l = length_x / 2.0
    half_w = width_y / 2.0

    if radius <= 1e-9:
        return [
            (cx - half_l, cy - half_w),
            (cx + half_l, cy - half_w),
            (cx + half_l, cy + half_w),
            (cx - half_l, cy + half_w),
        ]

    if length_x <= 2.0 * radius + 1e-9 and width_y <= 2.0 * radius + 1e-9:
        return _arc_points(
            cx, cy, min(half_l, half_w), 0.0, 2.0 * math.pi, segments_per_arc * 2
        )

    inner_l = cx - half_l + radius
    inner_r = cx + half_l - radius
    inner_b = cy - half_w + radius
    inner_t = cy + half_w - radius
    outline: list[tuple[float, float]] = []

    outline.extend(
        _arc_points(inner_l, inner_b, radius, math.pi, 1.5 * math.pi, segments_per_arc)[1:]
    )
    outline.append((inner_r, cy - half_w))
    outline.extend(
        _arc_points(inner_r, inner_b, radius, 1.5 * math.pi, 2.0 * math.pi, segments_per_arc)[
            1:
        ]
    )
    outline.append((cx + half_l, inner_t))
    outline.extend(
        _arc_points(inner_r, inner_t, radius, 0.0, 0.5 * math.pi, segments_per_arc)[1:]
    )
    outline.append((inner_l, cy + half_w))
    outline.extend(
        _arc_points(inner_l, inner_t, radius, 0.5 * math.pi, math.pi, segments_per_arc)[1:]
    )
    outline.append((cx - half_l, inner_b))
    return outline


def rounded_rect_outline(
    cx: float,
    cy: float,
    length_x: float,
    width_y: float,
    corner_r: float,
    *,
    segments_per_arc: int = 16,
) -> list[tuple[float, float]]:
    """Alias for rounded-rectangle slot outline (L along X, W along Y)."""
    return slot_outline(
        cx, cy, length_x, width_y, corner_r, segments_per_arc=segments_per_arc
    )


def extrude_rounded_rect_triangles(
    cx: float,
    cy: float,
    length_x: float,
    width_y: float,
    corner_r: float,
    z0: float,
    z1: float,
    *,
    segments_per_arc: int = 16,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
    """Extrude a slot profile through Z."""
    outline = slot_outline(
        cx, cy, length_x, width_y, corner_r, segments_per_arc=segments_per_arc
    )
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
