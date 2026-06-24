"""Custom via placement module geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from siw_generator.stackup import StackupParams


class CustomViaType(str, Enum):
    CIRCLE = "circle"
    SQUARE = "square"
    SLOT = "slot"


class CustomViaRole(str, Enum):
    """Copper cut / plating role (Custom tab type column)."""

    THROUGH = "through"
    TOP_CU = "top_cu"
    BOT_CU = "bot_cu"


VIA_TYPE_LABELS = {"圓形": CustomViaType.CIRCLE, "方形": CustomViaType.SQUARE}
VIA_TYPE_NAMES = {CustomViaType.CIRCLE: "圓形", CustomViaType.SQUARE: "方形", CustomViaType.SLOT: "Slot"}

VIA_ROLE_LABELS = {
    "貫孔": CustomViaRole.THROUGH,
    "top金屬孔": CustomViaRole.TOP_CU,
    "bot金屬孔": CustomViaRole.BOT_CU,
}
VIA_ROLE_NAMES = {
    CustomViaRole.THROUGH: "貫孔",
    CustomViaRole.TOP_CU: "top金屬孔",
    CustomViaRole.BOT_CU: "bot金屬孔",
}


def via_preview_style(
    via: "CustomVia",
    *,
    ghost: bool = False,
    selected: bool = False,
    moving: bool = False,
) -> tuple[str, str, float, float, str]:
    """Return face, edge, alpha, linewidth, linestyle for matplotlib preview."""
    if moving:
        return "#ff9800", "#e65100", 0.55, 1.4, "--"
    if ghost:
        return "#64b5f6", "#1976d2", 0.45, 1.2, "--"
    if selected:
        return "#ff9800", "#e65100", 0.85, 1.4, "-"
    if via.via_role is CustomViaRole.TOP_CU:
        return "#a5d6a7", "#388e3c", 1.0, 0.6, "-"
    if via.via_role is CustomViaRole.BOT_CU:
        return "#f48fb1", "#c2185b", 1.0, 0.6, "-"
    return "#c62828", "#8e0000", 1.0, 0.6, "-"


def via_copper_z_range_mm(
    via_role: CustomViaRole,
    *,
    substrate_height_mm: float,
    copper_thickness_mm: float,
) -> tuple[float, float]:
    """Z range (mm) for copper geometry in CST / STL export."""
    half = substrate_height_mm / 2.0
    cu = copper_thickness_mm
    if via_role is CustomViaRole.TOP_CU:
        return half, half + cu
    if via_role is CustomViaRole.BOT_CU:
        return -half - cu, -half
    return -half - cu, half + cu


@dataclass
class CustomVia:
    x_mm: float
    y_mm: float
    via_type: CustomViaType = CustomViaType.CIRCLE
    via_role: CustomViaRole = CustomViaRole.THROUGH
    w_mm: float = 0.15
    h_mm: float = 0.15
    length_mm: float | None = None
    corner_r_mm: float | None = None


def _point_in_polygon(x_mm: float, y_mm: float, outline: list[tuple[float, float]]) -> bool:
    if len(outline) < 3:
        return False
    inside = False
    n = len(outline)
    for i in range(n):
        x0, y0 = outline[i]
        x1, y1 = outline[(i + 1) % n]
        if (y0 > y_mm) != (y1 > y_mm):
            x_cross = (x1 - x0) * (y_mm - y0) / (y1 - y0) + x0
            if x_mm < x_cross:
                inside = not inside
    return inside


def via_hit_test(x_mm: float, y_mm: float, via: CustomVia) -> bool:
    """Return True if (x_mm, y_mm) lies inside the via footprint on XY plane."""
    if via.via_type is CustomViaType.CIRCLE:
        radius = via.w_mm / 2.0
        dx = x_mm - via.x_mm
        dy = y_mm - via.y_mm
        return dx * dx + dy * dy <= radius * radius + 1e-12
    if via.via_type is CustomViaType.SQUARE:
        half_w = via.w_mm / 2.0
        half_h = via.h_mm / 2.0
        return abs(x_mm - via.x_mm) <= half_w and abs(y_mm - via.y_mm) <= half_h
    from siw_generator.via_shapes import slot_outline

    length = float(via.length_mm if via.length_mm is not None else via.w_mm)
    width = float(via.w_mm)
    corner = via.corner_r_mm if via.corner_r_mm is not None else min(width, length) / 2.0
    outline = slot_outline(via.x_mm, via.y_mm, length, width, corner)
    return _point_in_polygon(x_mm, y_mm, outline)


def pick_via_index(x_mm: float, y_mm: float, vias: list[CustomVia]) -> int | None:
    """Pick topmost via index at (x_mm, y_mm), or None."""
    for idx in range(len(vias) - 1, -1, -1):
        if via_hit_test(x_mm, y_mm, vias[idx]):
            return idx
    return None


def normalize_rect(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def via_bounds(via: CustomVia) -> tuple[float, float, float, float]:
    """Axis-aligned bounding box (x_min, y_min, x_max, y_max) for a via footprint."""
    if via.via_type is CustomViaType.CIRCLE:
        radius = via.w_mm / 2.0
        return via.x_mm - radius, via.y_mm - radius, via.x_mm + radius, via.y_mm + radius
    if via.via_type is CustomViaType.SQUARE:
        half_w = via.w_mm / 2.0
        half_h = via.h_mm / 2.0
        return via.x_mm - half_w, via.y_mm - half_h, via.x_mm + half_w, via.y_mm + half_h
    from siw_generator.via_shapes import slot_outline

    length = float(via.length_mm if via.length_mm is not None else via.w_mm)
    width = float(via.w_mm)
    corner = via.corner_r_mm if via.corner_r_mm is not None else min(width, length) / 2.0
    outline = slot_outline(via.x_mm, via.y_mm, length, width, corner)
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    return min(xs), min(ys), max(xs), max(ys)


def via_intersects_rect(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    via: CustomVia,
) -> bool:
    """Return True if the via footprint overlaps the normalized selection rectangle."""
    rx0, ry0, rx1, ry1 = normalize_rect(x0, y0, x1, y1)
    vx0, vy0, vx1, vy1 = via_bounds(via)
    return not (vx1 < rx0 or vx0 > rx1 or vy1 < ry0 or vy0 > ry1)


def pick_vias_in_rect(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    vias: list[CustomVia],
) -> list[int]:
    """Return indices of vias whose footprints overlap the selection rectangle."""
    return [idx for idx, via in enumerate(vias) if via_intersects_rect(x0, y0, x1, y1, via)]


def line_via_positions(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    pitch_mm: float,
    *,
    tol: float = 1e-6,
) -> list[tuple[float, float]]:
    """Return via centers along the segment from (x0, y0) to (x1, y1) at pitch_mm spacing."""
    if pitch_mm <= 0:
        raise ValueError("pitch_mm must be positive")
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length < tol:
        return [(x0, y0)]
    ux = dx / length
    uy = dy / length
    points: list[tuple[float, float]] = [(x0, y0)]
    dist = pitch_mm
    while dist < length - tol:
        points.append((x0 + ux * dist, y0 + uy * dist))
        dist += pitch_mm
    ex, ey = x1, y1
    if math.hypot(ex - points[-1][0], ey - points[-1][1]) > tol:
        points.append((ex, ey))
    return points


def make_vias_along_line(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    template: CustomVia,
    pitch_mm: float,
) -> list[CustomVia]:
    """Create vias along a line using shape/role/size from template."""
    return [
        CustomVia(
            x_mm=x,
            y_mm=y,
            via_type=template.via_type,
            via_role=template.via_role,
            w_mm=template.w_mm,
            h_mm=template.h_mm,
            length_mm=template.length_mm,
            corner_r_mm=template.corner_r_mm,
        )
        for x, y in line_via_positions(x0, y0, x1, y1, pitch_mm)
    ]


@dataclass
class CustomModuleDefinition:
    """Parametric custom module (manual placement or exported from SIW)."""

    substrate_length_mm: float = 5.0
    substrate_width_mm: float = 5.0
    stackup: StackupParams = field(default_factory=StackupParams)
    material: str = "rt5880_lossy"
    center_freq_ghz: float = 120.0
    siw_width_mm: float | None = None
    via_diameter_mm: float | None = None
    via_pitch_mm: float | None = None
    slot_width_mm: float | None = None
    slot_length_mm: float | None = None
    slot_corner_r_mm: float | None = None
    slot_pitch_mm: float | None = None
    vias: list[CustomVia] = field(default_factory=list)
    kind: str = "custom"

    @property
    def copper_thickness_um(self) -> float:
        return self.stackup.copper_thickness_um
