"""Physical PCB stackup (dielectric + copper cladding)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StackupParams:
    """Layer thicknesses for 3D/CST export (units: mm)."""

    substrate_height_mm: float = 0.127
    copper_thickness_mm: float = 0.015  # 15 µm per side

    @property
    def copper_thickness_um(self) -> float:
        return self.copper_thickness_mm * 1000.0

    @property
    def total_thickness_mm(self) -> float:
        return self.substrate_height_mm + 2.0 * self.copper_thickness_mm

    def z_bounds_centered(self) -> dict[str, tuple[float, float]]:
        """Z ranges with origin at stack center (CST-friendly)."""
        half = self.total_thickness_mm / 2.0
        cu = self.copper_thickness_mm
        h = self.substrate_height_mm
        return {
            "bottom_copper": (-half, -half + cu),
            "substrate": (-half + cu, half - cu),
            "top_copper": (half - cu, half),
            "full_stack": (-half, half),
        }
