"""SIW via-wall geometry and parameter calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from siw_generator.materials import DEFAULT_SUBSTRATE_KEY, get_material
from siw_generator.stackup import StackupParams

SPEED_OF_LIGHT_M_S = 299_792_458.0
# TE10 fc ≈ 0.65~0.75 × f0；120 GHz 時 fc=85 GHz → 85/120
DEFAULT_FC_RATIO = 85.0 / 120.0
VIA_PITCH_SAFETY_MARGIN = 0.02  # mm under 2d limit (e.g. 0.28 for d=0.15)


@dataclass
class SIWParams:
    """Parametric SIW via pattern definition."""

    substrate_length_mm: float = 10.0
    substrate_width_mm: float = 10.0
    center_freq_ghz: float = 120.0
    via_diameter_mm: float = 0.15
    material: str = DEFAULT_SUBSTRATE_KEY
    er: float | None = None
    stackup: StackupParams = field(default_factory=StackupParams)
    edge_margin_mm: float = 0.0
    siw_width_mm: float | None = None
    via_pitch_mm: float | None = None
    via_count_target: int | None = None
    port1_x_mm: float | None = None
    port2_x_mm: float | None = None
    port1_enabled: bool = True
    port2_enabled: bool = True
    port_height_factor: float = 1.0  # H_port = factor × h；預設 (h+t_cu)/h
    port_width_factor: float = 1.0   # W_port = factor × w；預設 1×w
    fc_ratio: float = DEFAULT_FC_RATIO

    def __post_init__(self) -> None:
        if self.er is None:
            self.er = get_material(self.material).er

    @property
    def substrate_material(self):
        return get_material(self.material)

    def wavelength_mm(self) -> float:
        freq_hz = self.center_freq_ghz * 1e9
        return (SPEED_OF_LIGHT_M_S / freq_hz) * 1e3

    def guided_wavelength_mm(self) -> float:
        assert self.er is not None
        return self.wavelength_mm() / math.sqrt(self.er)

    def default_fc_ghz(self) -> float:
        """Cutoff frequency for TE10 equivalent rectangular waveguide."""
        return self.center_freq_ghz * self.fc_ratio

    def equivalent_waveguide_width_mm(self) -> float:
        """a_eff from fc = c / (2 · a_eff · sqrt(er))."""
        assert self.er is not None
        fc_hz = self.default_fc_ghz() * 1e9
        return (SPEED_OF_LIGHT_M_S / (2.0 * fc_hz * math.sqrt(self.er))) * 1e3

    def via_width_correction_mm(self, pitch_mm: float | None = None) -> float:
        """Via fence correction: d² / (0.95 · p)."""
        p = pitch_mm if pitch_mm is not None else self.default_via_pitch_mm()
        d = self.via_diameter_mm
        return (d * d) / (0.95 * p)

    def default_siw_width_mm(self, pitch_mm: float | None = None) -> float:
        """Center spacing a = a_eff + d²/(0.95·p)."""
        p = pitch_mm if pitch_mm is not None else self.default_via_pitch_mm()
        return self.equivalent_waveguide_width_mm() + self.via_width_correction_mm(p)

    def max_allowed_via_pitch_mm(self) -> float:
        """Upper bound: min(2d, λg/4) with small safety margin."""
        d = self.via_diameter_mm
        cap_2d = 2.0 * d - VIA_PITCH_SAFETY_MARGIN
        cap_lg4 = self.guided_wavelength_mm() / 4.0
        return max(min(cap_2d, cap_lg4 * 0.98), d * 1.05)

    def default_via_pitch_mm(self) -> float:
        """Pitch within p < 2d and p < λg/4 (e.g. 0.28 mm for d=0.15 @ 120 GHz)."""
        return self.max_allowed_via_pitch_mm()

    def radius_limit_x_mm(self) -> float:
        """Max |X| for via center (via outer edge may touch substrate edge)."""
        half_l = self.substrate_length_mm / 2.0
        return half_l - self.via_diameter_mm / 2.0 - self.edge_margin_mm

    def max_via_columns(self) -> int:
        """Max via columns fitting on substrate (centered at X=0)."""
        limit = self.radius_limit_x_mm()
        if limit <= 0:
            return 0
        pitch = self.resolved_via_pitch_mm()
        return len(_centered_x_positions(limit, pitch, 10_000))

    def default_via_count(self) -> int:
        """Max vias (two rows) that fit with centered X placement."""
        n_cols = self.max_via_columns()
        return max(n_cols * 2, 4) if n_cols >= 2 else 4

    def resolved_via_pitch_mm(self) -> float:
        if self.via_pitch_mm is not None:
            return self.via_pitch_mm
        return self.default_via_pitch_mm()

    def computed_siw_width_mm(self) -> float:
        if self.siw_width_mm is not None:
            return self.siw_width_mm
        return self.default_siw_width_mm(self.resolved_via_pitch_mm())

    def computed_via_pitch_mm(self) -> float:
        return self.resolved_via_pitch_mm()

    def validate(self) -> None:
        if self.substrate_length_mm <= 0 or self.substrate_width_mm <= 0:
            raise ValueError("Substrate dimensions must be positive.")
        if self.via_diameter_mm <= 0:
            raise ValueError("Via diameter must be positive.")
        pitch = self.resolved_via_pitch_mm()
        if pitch <= self.via_diameter_mm:
            raise ValueError(
                "Via 孔距必須大於 Via 直徑。請增大孔距或減小直徑。"
            )
        if pitch >= 2.0 * self.via_diameter_mm:
            raise ValueError(
                f"Via 孔距 ({pitch:.3f} mm) 須小於 2×直徑 "
                f"({2.0 * self.via_diameter_mm:.3f} mm) 以防電磁洩漏。"
            )
        lg4 = self.guided_wavelength_mm() / 4.0
        if pitch >= lg4:
            raise ValueError(
                f"Via 孔距 ({pitch:.3f} mm) 須小於 λg/4 ({lg4:.3f} mm)。"
            )
        siw_w = self.computed_siw_width_mm()
        usable_y = self.substrate_width_mm - 2.0 * self.edge_margin_mm
        if siw_w >= usable_y:
            raise ValueError(
                f"SIW 寬度 ({siw_w:.3f} mm) 超過基板可用寬度 "
                f"({usable_y:.3f} mm)。請加大基板或降低頻率。"
            )
        if self.via_count_target is not None:
            if self.via_count_target % 2 != 0:
                raise ValueError("Via 總數須為偶數（上下兩排各一半）")
            if self.via_count_target < 4:
                raise ValueError("Via 總數至少為 4")
        if self.port_height_factor <= 0:
            raise ValueError("Port 高度倍數必須大於 0")
        if self.port_width_factor <= 0:
            raise ValueError("Port 寬度倍數必須大於 0")


@dataclass
class Via:
    x_mm: float
    y_mm: float
    diameter_mm: float


@dataclass
class SlotVia:
    x_mm: float
    y_mm: float
    width_mm: float
    length_mm: float
    corner_r_mm: float


@dataclass
class PortDef:
    """Waveguide port on YZ plane (fixed X, spans Y and Z)."""

    name: str
    x_mm: float
    y_min_mm: float
    y_max_mm: float
    z_min_mm: float
    z_max_mm: float
    width_mm: float
    height_mm: float
    enabled: bool = True
    side: str = "left"  # left = Port1 (-X), right = Port2 (+X)
    plane: str = "YZ"


@dataclass
class PortAperture:
    """Computed port opening: W_port centered on Y=0, H_port from bottom ground up."""

    y_min_mm: float
    y_max_mm: float
    z_min_mm: float
    z_max_mm: float
    width_mm: float
    height_mm: float


def default_port_height_factor(stackup: StackupParams) -> float:
    """H_port = h + 2×t_cu（含上下銅層）→ factor × h."""
    h = stackup.substrate_height_mm
    if h <= 0:
        return 1.0
    return (h + 2.0 * stackup.copper_thickness_mm) / h


def default_port_height_mm(stackup: StackupParams) -> float:
    """Port height covering substrate and both copper cladding layers."""
    return stackup.substrate_height_mm + 2.0 * stackup.copper_thickness_mm


def default_port_width_factor() -> float:
    """W_port = SIW width → 1×w."""
    return 1.0


DEFAULT_LEAKAGE_MARGIN_FACTOR = 0.5


def clamp_leakage_margin_factor(value: float) -> float:
    if value < 0.0 or value > 2.0:
        raise ValueError("防洩漏倍數須在 0 ~ 2 之間")
    return value


def outermost_column_x_mm(pitch_mm: float, n_cols: int) -> float:
    """Outermost via/slot column |X| for centered placement (ignore substrate length)."""
    if n_cols < 1:
        return 0.0
    positions = _centered_x_positions(1e9, pitch_mm, n_cols)
    if not positions:
        return 0.0
    return max(abs(x) for x in positions)


def compute_leakage_safe_substrate_length_circular(
    *,
    pitch_mm: float,
    via_diameter_mm: float,
    via_count: int,
    margin_factor: float = DEFAULT_LEAKAGE_MARGIN_FACTOR,
) -> float:
    """Substrate X length: end margin = margin_factor × (pitch − diameter)."""
    if pitch_mm <= via_diameter_mm:
        raise ValueError("Via 孔距必須大於直徑才能計算防洩漏基板長度")
    factor = clamp_leakage_margin_factor(margin_factor)
    margin = factor * (pitch_mm - via_diameter_mm)
    n_cols = max(via_count // 2, 1)
    for _ in range(32):
        x_max = outermost_column_x_mm(pitch_mm, n_cols)
        half_l = x_max + via_diameter_mm / 2.0 + margin
        limit = half_l - via_diameter_mm / 2.0
        n_fit = len(_centered_x_positions(limit, pitch_mm, 10_000))
        if n_fit >= n_cols:
            return 2.0 * half_l
        if n_fit < 1:
            raise ValueError("SIW 長度過短，無法放置 via")
        n_cols = n_fit
    raise ValueError("無法收斂防洩漏基板長度，請檢查孔距與 Via 個數")


def compute_port_aperture(params: SIWParams, siw_width_mm: float) -> PortAperture:
    """H_port = port_height_factor × h; W_port = port_width_factor × w (Y-centered)."""
    h = params.stackup.substrate_height_mm
    h_port = params.port_height_factor * h
    w_port = params.port_width_factor * siw_width_mm
    z_bottom = params.stackup.z_bounds_centered()["full_stack"][0]
    half_w = w_port / 2.0
    return PortAperture(
        y_min_mm=-half_w,
        y_max_mm=half_w,
        z_min_mm=z_bottom,
        z_max_mm=z_bottom + h_port,
        width_mm=w_port,
        height_mm=h_port,
    )


@dataclass
class SIWGeometry:
    params: SIWParams
    vias: list[Via] = field(default_factory=list)
    slot_vias: list[SlotVia] = field(default_factory=list)
    via_type: str = "circular"
    slot_params: object | None = None
    substrate_corners_mm: list[tuple[float, float]] = field(default_factory=list)
    ports: list[PortDef] = field(default_factory=list)
    x_positions_mm: list[float] = field(default_factory=list)
    via_count_requested: int = 0

    @property
    def is_slot(self) -> bool:
        return self.via_type == "slot"

    @property
    def siw_width_mm(self) -> float:
        return self.params.computed_siw_width_mm()

    @property
    def via_pitch_mm(self) -> float:
        return self.params.resolved_via_pitch_mm()

    @property
    def via_count(self) -> int:
        return len(self.slot_vias) if self.is_slot else len(self.vias)

    @property
    def via_count_clipped(self) -> bool:
        return self.via_count_requested > self.via_count


def resolve_centered_column_count(n_cols_requested: int, n_cols_max: int) -> int:
    """Clip column count to fit substrate; keep odd count when a center column is required."""
    n_cols = min(n_cols_requested, n_cols_max)
    if n_cols_requested % 2 == 1 and n_cols % 2 == 0:
        n_cols = max(1, n_cols - 1)
    return n_cols


def _centered_x_positions(limit: float, pitch: float, n_cols: int) -> list[float]:
    """Place via columns at X=0 and expand symmetrically along ±X."""
    if n_cols < 1 or limit <= 0:
        return []

    if n_cols % 2 == 1:
        positions = [0.0]
        k = 1
        while len(positions) < n_cols:
            placed = False
            for sign in (-1, 1):
                x = sign * k * pitch
                if abs(x) > limit + 1e-9:
                    continue
                positions.append(x)
                placed = True
                if len(positions) >= n_cols:
                    break
            if not placed:
                break
            k += 1
        return sorted(positions)

    positions: list[float] = []
    for i in range(n_cols // 2):
        offset = (i * 2 + 1) * pitch / 2.0
        if offset > limit + 1e-9:
            break
        positions.extend([-offset, offset])
    return sorted(positions)


def _x_positions(params: SIWParams) -> list[float]:
    """Centered at X=0, fixed pitch, clip at substrate edges, respect count."""
    limit = params.radius_limit_x_mm()
    if limit <= 0:
        raise ValueError("SIW 長度過短，無法放置 via")

    pitch = params.resolved_via_pitch_mm()
    n_cols_max = len(_centered_x_positions(limit, pitch, 10_000))

    if params.via_count_target is not None:
        n_cols_requested = params.via_count_target // 2
        n_cols = resolve_centered_column_count(n_cols_requested, n_cols_max)
    else:
        n_cols = n_cols_max

    positions = _centered_x_positions(limit, pitch, n_cols)

    if len(positions) < 2:
        raise ValueError(
            "沿傳播方向 via 不足。請增加 SIW 長度、減少孔距，或減少 via 個數。"
        )
    return positions


def _default_port_x(params: SIWParams, side: str) -> float:
    """Port on YZ plane at SIW substrate end face."""
    half_l = params.substrate_length_mm / 2.0
    return -half_l if side == "left" else half_l


def build_siw_geometry(params: SIWParams) -> SIWGeometry:
    """Build sidewall via positions, YZ-plane ports, and substrate outline."""
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
    aperture = compute_port_aperture(params, siw_width)

    x_positions = _x_positions(params)
    via_count_requested = params.via_count_target or (len(x_positions) * 2)

    vias: list[Via] = []
    for x in x_positions:
        vias.append(Via(x_mm=x, y_mm=y_bottom, diameter_mm=params.via_diameter_mm))
        vias.append(Via(x_mm=x, y_mm=y_top, diameter_mm=params.via_diameter_mm))

    ports: list[PortDef] = []
    if params.port1_enabled:
        p1x = params.port1_x_mm if params.port1_x_mm is not None else _default_port_x(
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
        p2x = params.port2_x_mm if params.port2_x_mm is not None else _default_port_x(
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

    return SIWGeometry(
        params=params,
        vias=vias,
        substrate_corners_mm=corners,
        ports=ports,
        x_positions_mm=x_positions,
        via_count_requested=via_count_requested,
    )
