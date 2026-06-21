"""Custom via placement module geometry."""

from __future__ import annotations

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
) -> tuple[str, str, float, float, str]:
    """Return face, edge, alpha, linewidth, linestyle for matplotlib preview."""
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
