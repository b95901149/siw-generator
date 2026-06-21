"""Rounded-rectangle slot via SIW geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from siw_generator.materials import DEFAULT_SUBSTRATE_KEY, get_material
from siw_generator.siw_geometry import (
    DEFAULT_LEAKAGE_MARGIN_FACTOR,
    PortDef,
    SIWGeometry,
    SIWParams,
    SlotVia,
    SPEED_OF_LIGHT_M_S,
    _centered_x_positions,
    clamp_leakage_margin_factor,
    compute_port_aperture,
    outermost_column_x_mm,
    resolve_centered_column_count,
)
from siw_generator.stackup import StackupParams


@dataclass
class SlotSIWParams:
    """SIW sidewall with rounded-rectangle slot vias."""

    substrate_length_mm: float = 10.0
    substrate_width_mm: float = 10.0
    center_freq_ghz: float = 120.0
    slot_width_mm: float = 0.15
    slot_length_mm: float = 1.0
    slot_corner_r_mm: float = 0.015
    slot_pitch_mm: float = 1.05
    material: str = DEFAULT_SUBSTRATE_KEY
    er: float | None = None
    stackup: StackupParams = field(default_factory=StackupParams)
    edge_margin_mm: float = 0.0
    siw_width_mm: float | None = None
    via_count_target: int | None = None
    port1_x_mm: float | None = None
    port2_x_mm: float | None = None
    port1_enabled: bool = True
    port2_enabled: bool = True
    port_height_factor: float = 1.0
    port_width_factor: float = 1.0
    fc_ratio: float = 0.82

    def __post_init__(self) -> None:
        if self.er is None:
            self.er = get_material(self.material).er

    @property
    def substrate_material(self):
        return get_material(self.material)

    def default_siw_width_mm(self) -> float:
        """Rectangular waveguide TE10 cutoff approximation."""
        assert self.er is not None
        freq_hz = self.center_freq_ghz * 1e9
        fc_hz = freq_hz * self.fc_ratio
        return (SPEED_OF_LIGHT_M_S / (2.0 * fc_hz * math.sqrt(self.er))) * 1e3

    def computed_siw_width_mm(self) -> float:
        if self.siw_width_mm is not None:
            return self.siw_width_mm
        return self.default_siw_width_mm()

    def length_limit_x_mm(self) -> float:
        half_l = self.substrate_length_mm / 2.0
        return half_l - self.slot_length_mm / 2.0 - self.edge_margin_mm

    def max_slot_columns(self) -> int:
        limit = self.length_limit_x_mm()
        if limit <= 0:
            return 0
        return len(_centered_x_positions(limit, self.slot_pitch_mm, 10_000))

    def default_slot_count(self) -> int:
        n_cols = self.max_slot_columns()
        if n_cols < 1:
            return 2
        return max(n_cols * 2, 2)

    def validate(self) -> None:
        if self.substrate_length_mm <= 0 or self.substrate_width_mm <= 0:
            raise ValueError("基板尺寸必須大於 0")
        if self.slot_width_mm <= 0 or self.slot_length_mm <= 0:
            raise ValueError("Slot 寬度與長度必須大於 0")
        if self.slot_corner_r_mm < 0:
            raise ValueError("Slot R 角半徑不可為負")
        if self.slot_width_mm >= self.slot_length_mm:
            raise ValueError("Slot 長度 L 必須大於寬度 W（obround 外形）")
        if not _is_continuous_wall(self):
            if self.slot_pitch_mm <= self.slot_length_mm:
                raise ValueError("Slot pitch 必須大於 Slot 長度 L")
        siw_w = self.computed_siw_width_mm()
        usable_y = self.substrate_width_mm - 2.0 * self.edge_margin_mm
        if siw_w >= usable_y:
            raise ValueError(
                f"SIW 寬度 ({siw_w:.3f} mm) 超過基板可用寬度 ({usable_y:.3f} mm)"
            )
        if siw_w <= self.slot_width_mm:
            raise ValueError("SIW 寬度必須大於 Slot 寬度 W")
        if self.via_count_target is not None:
            if self.via_count_target % 2 != 0:
                raise ValueError("Slot 總數須為偶數（上下兩排各一半）")
            if self.via_count_target < 2:
                raise ValueError("Slot 總數至少為 2")
        if self.port_height_factor <= 0 or self.port_width_factor <= 0:
            raise ValueError("Port 倍數必須大於 0")


def _is_continuous_wall(params: SlotSIWParams) -> bool:
    """Two slots at X=0 (top/bottom): continuous sidewall, pitch not used."""
    return params.via_count_target == 2


def compute_leakage_safe_substrate_length_slot(
    *,
    pitch_mm: float,
    slot_length_mm: float,
    slot_count: int,
    slot_width_mm: float | None = None,
    margin_factor: float = DEFAULT_LEAKAGE_MARGIN_FACTOR,
) -> float:
    """Substrate X length for fixed slot count.

    Normal mode: end margin = margin_factor × (pitch − L).
    Continuous wall (count=2): center slot only; margin = margin_factor × W.
    """
    if slot_count % 2 != 0:
        raise ValueError("Slot 總數須為偶數（上下兩排各一半）")
    if slot_count < 2:
        raise ValueError("Slot 總數至少為 2")
    factor = clamp_leakage_margin_factor(margin_factor)
    if slot_count == 2:
        width = slot_width_mm if slot_width_mm is not None else slot_length_mm
        margin = factor * width
        return slot_length_mm + 2.0 * margin
    if pitch_mm <= slot_length_mm:
        raise ValueError("Slot pitch 必須大於 L 才能計算防洩漏基板長度")
    margin = factor * (pitch_mm - slot_length_mm)
    n_cols = slot_count // 2
    x_max = outermost_column_x_mm(pitch_mm, n_cols)
    half_l = x_max + slot_length_mm / 2.0 + margin
    return 2.0 * half_l


def _default_port_x_slot(params: SlotSIWParams, side: str) -> float:
    half_l = params.substrate_length_mm / 2.0
    return -half_l if side == "left" else half_l


def _slot_x_positions(params: SlotSIWParams) -> list[float]:
    if _is_continuous_wall(params):
        half_l = params.substrate_length_mm / 2.0
        need = params.slot_length_mm / 2.0 + params.edge_margin_mm
        if half_l < need - 1e-9:
            raise ValueError(
                f"SIW 長度不足以容納中央 Slot（需 X 半長 ≥ {need:.4f} mm，目前 {half_l:.4f} mm）"
            )
        return [0.0]

    limit = params.length_limit_x_mm()
    if limit <= 0:
        raise ValueError("SIW 長度過短，無法放置 Slot")

    pitch = params.slot_pitch_mm
    n_cols_max = len(_centered_x_positions(limit, pitch, 10_000))

    if params.via_count_target is not None:
        n_cols_requested = params.via_count_target // 2
        n_cols = resolve_centered_column_count(n_cols_requested, n_cols_max)
    else:
        n_cols = n_cols_max

    positions = _centered_x_positions(limit, pitch, n_cols)
    if not positions or len(positions) < n_cols:
        raise ValueError("沿傳播方向 Slot 不足。請增加 SIW 長度、減少 pitch 或減少個數。")
    return positions


def build_slot_siw_geometry(params: SlotSIWParams) -> SIWGeometry:
    """Build SIW geometry with rounded-rectangle slot vias."""
    params.validate()

    half_l = params.substrate_length_mm / 2.0
    half_w = params.substrate_width_mm / 2.0
    corners = [
        (-half_l, -half_w),
        (half_l, -half_w),
        (half_l, half_w),
        (-half_l, half_w),
    ]

    siw_width = params.computed_siw_width_mm()
    y_bottom = -siw_width / 2.0
    y_top = siw_width / 2.0
    adapter = SIWParams(
        stackup=params.stackup,
        port_height_factor=params.port_height_factor,
        port_width_factor=params.port_width_factor,
        siw_width_mm=siw_width,
        center_freq_ghz=params.center_freq_ghz,
        material=params.material,
        er=params.er,
    )
    aperture = compute_port_aperture(adapter, siw_width)

    x_positions = _slot_x_positions(params)
    slot_count_requested = params.via_count_target or (len(x_positions) * 2)

    slot_vias: list[SlotVia] = []
    for x in x_positions:
        length_mm = params.slot_length_mm
        corner_r = min(params.slot_corner_r_mm, length_mm / 2.0, params.slot_width_mm / 2.0)
        for y in (y_bottom, y_top):
            slot_vias.append(
                SlotVia(
                    x_mm=x,
                    y_mm=y,
                    width_mm=params.slot_width_mm,
                    length_mm=length_mm,
                    corner_r_mm=corner_r,
                )
            )

    ports: list[PortDef] = []
    if params.port1_enabled:
        p1x = params.port1_x_mm if params.port1_x_mm is not None else _default_port_x_slot(
            params, "left"
        )
        ports.append(
            PortDef(
                name="Port1",
                x_mm=p1x,
                y_min_mm=aperture.y_min_mm,
                y_max_mm=aperture.y_max_mm,
                z_min_mm=aperture.z_min_mm,
                z_max_mm=aperture.z_max_mm,
                width_mm=aperture.width_mm,
                height_mm=aperture.height_mm,
                enabled=True,
                side="left",
            )
        )
    if params.port2_enabled:
        p2x = params.port2_x_mm if params.port2_x_mm is not None else _default_port_x_slot(
            params, "right"
        )
        ports.append(
            PortDef(
                name="Port2",
                x_mm=p2x,
                y_min_mm=aperture.y_min_mm,
                y_max_mm=aperture.y_max_mm,
                z_min_mm=aperture.z_min_mm,
                z_max_mm=aperture.z_max_mm,
                width_mm=aperture.width_mm,
                height_mm=aperture.height_mm,
                enabled=True,
                side="right",
            )
        )

    if params.port1_enabled and params.port2_enabled:
        p1 = next(pt for pt in ports if pt.name == "Port1")
        p2 = next(pt for pt in ports if pt.name == "Port2")
        if p1.x_mm >= p2.x_mm:
            raise ValueError("Port1（左側）X 座標必須小於 Port2（右側）")

    legacy_params = SIWParams(
        substrate_length_mm=params.substrate_length_mm,
        substrate_width_mm=params.substrate_width_mm,
        center_freq_ghz=params.center_freq_ghz,
        via_diameter_mm=params.slot_width_mm,
        material=params.material,
        er=params.er,
        stackup=params.stackup,
        edge_margin_mm=params.edge_margin_mm,
        siw_width_mm=params.siw_width_mm,
        via_pitch_mm=params.slot_pitch_mm,
        via_count_target=params.via_count_target,
        port1_x_mm=params.port1_x_mm,
        port2_x_mm=params.port2_x_mm,
        port1_enabled=params.port1_enabled,
        port2_enabled=params.port2_enabled,
        port_height_factor=params.port_height_factor,
        port_width_factor=params.port_width_factor,
        fc_ratio=params.fc_ratio,
    )

    return SIWGeometry(
        params=legacy_params,
        vias=[],
        slot_vias=slot_vias,
        via_type="slot",
        slot_params=params,
        substrate_corners_mm=corners,
        ports=ports,
        x_positions_mm=x_positions,
        via_count_requested=slot_count_requested,
    )
