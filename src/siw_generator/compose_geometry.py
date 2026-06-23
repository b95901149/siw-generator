"""M×N grid composition of custom modules."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path

from siw_generator.custom_geometry import CustomModuleDefinition, CustomVia, CustomViaType
from siw_generator.stackup import StackupParams

_PITCH_EPS = 1e-4
_EDGE_SNAP_FRAC = 0.18


@dataclass
class PlacedModule:
    col: int
    row: int
    module: CustomModuleDefinition
    source_path: Path | None = None
    label: str = ""
    rotation_deg: int = 0
    mirror_x: bool = False
    scale_x: float = 1.0
    scale_y: float = 1.0


@dataclass
class ComposePort:
    col: int
    row: int
    edge: str
    position_mm: float
    width_mm: float
    via_index: int = -1
    via_index_2: int = -1
    span_a_mm: float = 0.0
    span_b_mm: float = 0.0


@dataclass
class PortCandidate:
    col: int
    row: int
    edge: str
    position_mm: float
    width_mm: float
    via_index: int
    via_index_2: int
    span_a_mm: float
    span_b_mm: float
    line_x0: float
    line_y0: float
    line_x1: float
    line_y1: float


@dataclass
class ComposeLayout:
    m_count: int = 3
    n_count: int = 3
    default_pitch_x_mm: float = 10.0
    default_pitch_y_mm: float = 10.0
    col_pitch_mm: list[float] = field(default_factory=list)
    row_pitch_mm: list[float] = field(default_factory=list)
    placements: dict[tuple[int, int], PlacedModule] = field(default_factory=dict)
    filled_cells: set[tuple[int, int]] = field(default_factory=set)
    fill_stackup: StackupParams = field(default_factory=StackupParams)
    fill_material: str = "rt5880_lossy"
    ports: list[ComposePort] = field(default_factory=list)
    substrate_frame: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        self._ensure_pitch_arrays()

    def _ensure_pitch_arrays(self) -> None:
        while len(self.col_pitch_mm) < self.m_count:
            self.col_pitch_mm.append(self.default_pitch_x_mm)
        while len(self.row_pitch_mm) < self.n_count:
            self.row_pitch_mm.append(self.default_pitch_y_mm)
        del self.col_pitch_mm[self.m_count :]
        del self.row_pitch_mm[self.n_count :]

    @property
    def pitch_x_mm(self) -> float:
        return self.col_pitch_mm[0] if self.col_pitch_mm else self.default_pitch_x_mm

    @property
    def pitch_y_mm(self) -> float:
        return self.row_pitch_mm[0] if self.row_pitch_mm else self.default_pitch_y_mm

    @property
    def total_width_mm(self) -> float:
        return sum(self.col_pitch_mm)

    @property
    def total_height_mm(self) -> float:
        return sum(self.row_pitch_mm)


@dataclass
class PendingPlacement:
    col: int
    row: int
    module: CustomModuleDefinition
    source_path: Path | None
    label: str
    rotation_deg: int
    mirror_x: bool
    conflicts: list[str] = field(default_factory=list)


def clone_layout(layout: ComposeLayout) -> ComposeLayout:
    return copy.deepcopy(layout)


def normalize_rotation(rotation_deg: int) -> int:
    return int(rotation_deg) % 360


def rotate_clockwise(rotation_deg: int) -> int:
    return normalize_rotation(rotation_deg + 90)


def footprint_for_module(
    module: CustomModuleDefinition,
    *,
    rotation_deg: int = 0,
    mirror_x: bool = False,
) -> tuple[float, float]:
    del mirror_x
    length = module.substrate_length_mm
    width = module.substrate_width_mm
    if normalize_rotation(rotation_deg) in (90, 270):
        length, width = width, length
    return length, width


def footprint_for_placed(placed: PlacedModule) -> tuple[float, float]:
    return footprint_for_module(
        placed.module,
        rotation_deg=placed.rotation_deg,
        mirror_x=placed.mirror_x,
    )


def transform_placed_local(placed: PlacedModule, x_mm: float, y_mm: float) -> tuple[float, float]:
    return transform_local(
        x_mm * placed.scale_x,
        y_mm * placed.scale_y,
        rotation_deg=placed.rotation_deg,
        mirror_x=placed.mirror_x,
    )


def apply_cell_fit_scales(placed: PlacedModule, layout: ComposeLayout) -> None:
    """Set scale factors so module geometry fits the cell pitch."""
    layout._ensure_pitch_arrays()
    native_x, native_y = footprint_for_placed(placed)
    cell_x = layout.col_pitch_mm[placed.col]
    cell_y = layout.row_pitch_mm[placed.row]
    placed.scale_x = cell_x / native_x if native_x > _PITCH_EPS else 1.0
    placed.scale_y = cell_y / native_y if native_y > _PITCH_EPS else 1.0


def transform_local(x: float, y: float, *, rotation_deg: int, mirror_x: bool) -> tuple[float, float]:
    if mirror_x:
        x = -x
    rot = normalize_rotation(rotation_deg)
    if rot == 0:
        return x, y
    if rot == 90:
        return y, -x
    if rot == 180:
        return -x, -y
    if rot == 270:
        return -y, x
    raise ValueError(f"unsupported rotation {rotation_deg}")


def via_opening_width(via: CustomVia) -> float:
    if via.via_type is CustomViaType.SQUARE:
        return max(via.w_mm, via.h_mm)
    return via.w_mm


def column_boundaries(layout: ComposeLayout) -> list[float]:
    layout._ensure_pitch_arrays()
    half_w = layout.total_width_mm / 2.0
    xs = [-half_w]
    for pitch in layout.col_pitch_mm:
        xs.append(xs[-1] + pitch)
    return xs


def row_boundaries(layout: ComposeLayout) -> list[float]:
    layout._ensure_pitch_arrays()
    half_h = layout.total_height_mm / 2.0
    ys = [-half_h]
    for pitch in layout.row_pitch_mm:
        ys.append(ys[-1] + pitch)
    return ys


def cell_bounds(col: int, row: int, layout: ComposeLayout) -> tuple[float, float, float, float]:
    xs = column_boundaries(layout)
    ys = row_boundaries(layout)
    return xs[col], ys[row], xs[col + 1], ys[row + 1]


def cell_center(col: int, row: int, layout: ComposeLayout) -> tuple[float, float]:
    x0, y0, x1, y1 = cell_bounds(col, row, layout)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def cell_stackup(layout: ComposeLayout, col: int, row: int) -> StackupParams:
    """Stackup for a grid cell: placed module stackup, else fill stackup."""
    placed = layout.placements.get((col, row))
    if placed is not None:
        return placed.module.stackup
    return layout.fill_stackup


def cell_at_point(x_mm: float, y_mm: float, layout: ComposeLayout) -> tuple[int, int] | None:
    xs = column_boundaries(layout)
    ys = row_boundaries(layout)
    if x_mm < xs[0] - _PITCH_EPS or x_mm > xs[-1] + _PITCH_EPS:
        return None
    if y_mm < ys[0] - _PITCH_EPS or y_mm > ys[-1] + _PITCH_EPS:
        return None

    col = layout.m_count - 1
    for c in range(layout.m_count):
        right = xs[c + 1]
        if c == layout.m_count - 1:
            if xs[c] <= x_mm <= right + _PITCH_EPS:
                col = c
                break
        elif xs[c] <= x_mm < right:
            col = c
            break

    row = layout.n_count - 1
    for r in range(layout.n_count):
        bottom = ys[r + 1]
        if r == layout.n_count - 1:
            if ys[r] <= y_mm <= bottom + _PITCH_EPS:
                row = r
                break
        elif ys[r] <= y_mm < bottom:
            row = r
            break
    return col, row


def closest_cell(x_mm: float, y_mm: float, layout: ComposeLayout) -> tuple[int, int]:
    hit = cell_at_point(x_mm, y_mm, layout)
    if hit is not None:
        return hit
    best_col, best_row = 0, 0
    best_d = float("inf")
    for row in range(layout.n_count):
        for col in range(layout.m_count):
            cx, cy = cell_center(col, row, layout)
            d = (x_mm - cx) ** 2 + (y_mm - cy) ** 2
            if d < best_d:
                best_d = d
                best_col, best_row = col, row
    return best_col, best_row


def default_pitch_for_module(module: CustomModuleDefinition) -> tuple[float, float]:
    return module.substrate_length_mm, module.substrate_width_mm


def pitch_conflicts(
    layout: ComposeLayout,
    col: int,
    row: int,
    size_x: float,
    size_y: float,
    *,
    exclude: tuple[int, int] | None = None,
) -> list[str]:
    conflicts: list[str] = []
    for key, placed in layout.placements.items():
        if exclude is not None and key == exclude:
            continue
        px, py = footprint_for_placed(placed)
        if placed.col == col and abs(px - size_x) > _PITCH_EPS:
            if "col" not in conflicts:
                conflicts.append("col")
        if placed.row == row and abs(py - size_y) > _PITCH_EPS:
            if "row" not in conflicts:
                conflicts.append("row")
    return conflicts


def apply_reference_pitch(
    layout: ComposeLayout,
    col: int,
    row: int,
    reference: PlacedModule,
    *,
    conflicts: list[str] | None = None,
) -> None:
    ref_col, ref_row = reference.col, reference.row
    layout._ensure_pitch_arrays()
    update_col = conflicts is None or "col" in conflicts
    update_row = conflicts is None or "row" in conflicts
    if update_col:
        layout.col_pitch_mm[col] = layout.col_pitch_mm[ref_col]
    if update_row:
        layout.row_pitch_mm[row] = layout.row_pitch_mm[ref_row]


def apply_new_module_pitch(
    layout: ComposeLayout,
    col: int,
    row: int,
    module: CustomModuleDefinition,
    *,
    rotation_deg: int = 0,
    mirror_x: bool = False,
) -> None:
    sx, sy = footprint_for_module(module, rotation_deg=rotation_deg, mirror_x=mirror_x)
    layout.col_pitch_mm[col] = sx
    layout.row_pitch_mm[row] = sy


def sync_pitch_from_placements(layout: ComposeLayout) -> None:
    layout._ensure_pitch_arrays()
    for col in range(layout.m_count):
        sizes = [footprint_for_placed(p)[0] for p in layout.placements.values() if p.col == col]
        layout.col_pitch_mm[col] = sizes[0] if sizes else layout.default_pitch_x_mm
    for row in range(layout.n_count):
        sizes = [footprint_for_placed(p)[1] for p in layout.placements.values() if p.row == row]
        layout.row_pitch_mm[row] = sizes[0] if sizes else layout.default_pitch_y_mm


def place_module(
    layout: ComposeLayout,
    col: int,
    row: int,
    module: CustomModuleDefinition,
    *,
    source_path: Path | None = None,
    label: str = "",
    rotation_deg: int = 0,
    mirror_x: bool = False,
    reference: PlacedModule | None = None,
    use_new_module_pitch: bool = False,
    reference_conflicts: list[str] | None = None,
) -> list[str]:
    size_x, size_y = footprint_for_module(module, rotation_deg=rotation_deg, mirror_x=mirror_x)
    pitch_locked = False
    if use_new_module_pitch:
        apply_new_module_pitch(layout, col, row, module, rotation_deg=rotation_deg, mirror_x=mirror_x)
        pitch_locked = True
    elif reference is not None:
        apply_reference_pitch(
            layout,
            col,
            row,
            reference,
            conflicts=reference_conflicts,
        )
        pitch_locked = True
    else:
        conflicts = pitch_conflicts(layout, col, row, size_x, size_y)
        if conflicts:
            return conflicts

    placed = PlacedModule(
        col=col,
        row=row,
        module=module,
        source_path=source_path,
        label=label,
        rotation_deg=normalize_rotation(rotation_deg),
        mirror_x=mirror_x,
    )
    layout.placements[(col, row)] = placed
    layout.filled_cells.discard((col, row))
    apply_cell_fit_scales(placed, layout)
    if not pitch_locked:
        sync_pitch_from_placements(layout)
        apply_cell_fit_scales(placed, layout)
    return []


def move_placed_module(
    layout: ComposeLayout,
    source: tuple[int, int],
    target: tuple[int, int],
    *,
    reference: PlacedModule | None = None,
    use_new_module_pitch: bool = False,
    reference_conflicts: list[str] | None = None,
) -> list[str]:
    if source == target:
        return []
    placed = layout.placements.pop(source, None)
    if placed is None:
        return []
    placed.col, placed.row = target
    size_x, size_y = footprint_for_placed(placed)
    pitch_locked = False
    if use_new_module_pitch:
        apply_new_module_pitch(
            layout,
            target[0],
            target[1],
            placed.module,
            rotation_deg=placed.rotation_deg,
            mirror_x=placed.mirror_x,
        )
        pitch_locked = True
    elif reference is not None:
        apply_reference_pitch(
            layout,
            target[0],
            target[1],
            reference,
            conflicts=reference_conflicts,
        )
        pitch_locked = True
    else:
        conflicts = pitch_conflicts(
            layout, target[0], target[1], size_x, size_y, exclude=target
        )
        if conflicts:
            layout.placements[source] = placed
            placed.col, placed.row = source
            return conflicts

    layout.placements[target] = placed
    apply_cell_fit_scales(placed, layout)
    if not pitch_locked:
        sync_pitch_from_placements(layout)
        apply_cell_fit_scales(placed, layout)
    return []


def remove_placed_module(layout: ComposeLayout, col: int, row: int) -> None:
    layout.placements.pop((col, row), None)
    sync_pitch_from_placements(layout)


def rotate_placed(placed: PlacedModule) -> None:
    placed.rotation_deg = rotate_clockwise(placed.rotation_deg)


def mirror_placed(placed: PlacedModule) -> None:
    placed.mirror_x = not placed.mirror_x


def normalize_rect(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def cells_in_rect(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    layout: ComposeLayout,
) -> list[tuple[int, int]]:
    rx0, ry0, rx1, ry1 = normalize_rect(x0, y0, x1, y1)
    hits: list[tuple[int, int]] = []
    for row in range(layout.n_count):
        for col in range(layout.m_count):
            cx, cy = cell_center(col, row, layout)
            if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
                hits.append((col, row))
    return hits


def apply_substrate_fill_in_rect(
    layout: ComposeLayout,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> int:
    """Mark empty cells in rect as substrate fill; return count filled."""
    count = 0
    for cell in cells_in_rect(x0, y0, x1, y1, layout):
        if cell in layout.placements:
            continue
        layout.filled_cells.add(cell)
        count += 1
    return count


def apply_substrate_frame_from_rect(
    layout: ComposeLayout,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> tuple[float, float, float, float]:
    """Set compose outer substrate frame; expand to include occupied cells (no clipping)."""
    frame = merge_substrate_frame_with_content(layout, normalize_rect(x0, y0, x1, y1))
    layout.substrate_frame = frame
    recompute_all_port_positions(layout)
    return frame


def grid_bounds(layout: ComposeLayout) -> tuple[float, float, float, float]:
    xs = column_boundaries(layout)
    ys = row_boundaries(layout)
    return xs[0], ys[0], xs[-1], ys[-1]


def export_geometry_bounds(layout: ComposeLayout) -> tuple[float, float, float, float]:
    """Bounding box used to center CST/STL/DXF exports at XY origin."""
    if layout.substrate_frame is not None:
        return layout.substrate_frame
    bounds = occupied_cells_bounds(layout)
    if bounds is not None:
        return bounds
    return grid_bounds(layout)


def export_center_offset_mm(layout: ComposeLayout) -> tuple[float, float]:
    """Shift to subtract so export geometry is centered at (0, 0)."""
    x0, y0, x1, y1 = export_geometry_bounds(layout)
    return (x0 + x1) / 2.0, (y0 + y1) / 2.0


def occupied_cells_bounds(layout: ComposeLayout) -> tuple[float, float, float, float] | None:
    """Bounding box of all placed modules and filled substrate cells."""
    cells = set(layout.placements.keys()) | layout.filled_cells
    if not cells:
        return None
    x_min = y_min = float("inf")
    x_max = y_max = float("-inf")
    for col, row in cells:
        x0, y0, x1, y1 = cell_bounds(col, row, layout)
        x_min = min(x_min, x0)
        y_min = min(y_min, y0)
        x_max = max(x_max, x1)
        y_max = max(y_max, y1)
    return normalize_rect(x_min, y_min, x_max, y_max)


def merge_substrate_frame_with_content(
    layout: ComposeLayout,
    frame: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Expand frame minimally so no placed/filled cell is clipped."""
    fx0, fy0, fx1, fy1 = frame
    occupied = set(layout.placements.keys()) | layout.filled_cells
    for col, row in occupied:
        cx0, cy0, cx1, cy1 = cell_bounds(col, row, layout)
        if cx1 <= fx0 + _PITCH_EPS or cx0 >= fx1 - _PITCH_EPS:
            continue
        if cy1 <= fy0 + _PITCH_EPS or cy0 >= fy1 - _PITCH_EPS:
            continue
        fx0 = min(fx0, cx0)
        fy0 = min(fy0, cy0)
        fx1 = max(fx1, cx1)
        fy1 = max(fy1, cy1)
    content = occupied_cells_bounds(layout)
    if content is not None:
        cx0, cy0, cx1, cy1 = content
        fx0 = min(fx0, cx0)
        fy0 = min(fy0, cy0)
        fx1 = max(fx1, cx1)
        fy1 = max(fy1, cy1)
    return normalize_rect(fx0, fy0, fx1, fy1)


_MIN_DRAG_MM = 0.8


def resolve_operation_rect(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    layout: ComposeLayout,
) -> tuple[float, float, float, float]:
    """Use drag rect when large enough; otherwise fall back to occupied cell bounds."""
    rect = normalize_rect(x0, y0, x1, y1)
    if (rect[2] - rect[0]) >= _MIN_DRAG_MM and (rect[3] - rect[1]) >= _MIN_DRAG_MM:
        return rect
    bounds = occupied_cells_bounds(layout)
    if bounds is None:
        raise ValueError("請圈選範圍，或先放置／填補 module")
    return bounds


def representative_gap(layout: ComposeLayout, axis: str) -> tuple[float, float]:
    pitch = layout.pitch_x_mm if axis == "x" else layout.pitch_y_mm
    feature = 0.15
    for placed in layout.placements.values():
        module = placed.module
        if axis == "x":
            if module.via_diameter_mm is not None:
                feature = module.via_diameter_mm
                break
            if module.slot_length_mm is not None:
                feature = module.slot_length_mm
                break
            feature = max(feature, module.substrate_length_mm * 0.05)
        else:
            if module.via_diameter_mm is not None:
                feature = module.via_diameter_mm
                break
            if module.slot_width_mm is not None:
                feature = module.slot_width_mm
                break
            feature = max(feature, module.substrate_width_mm * 0.05)
    return pitch, feature


def compute_leakage_substrate_frame(
    layout: ComposeLayout,
    *,
    axis: str,
    margin_factor: float,
) -> tuple[float, float, float, float]:
    """Extend substrate frame for leakage margin along X or Y based on port edges."""
    from siw_generator.siw_geometry import clamp_leakage_margin_factor

    axis = axis.lower()
    if axis not in ("x", "y"):
        raise ValueError("axis 須為 x 或 y")

    if layout.substrate_frame is not None:
        x0, y0, x1, y1 = layout.substrate_frame
    else:
        x0, y0, x1, y1 = grid_bounds(layout)

    factor = clamp_leakage_margin_factor(margin_factor)
    pitch, feature = representative_gap(layout, axis)
    margin = factor * (pitch - feature) if pitch > feature else factor * feature

    if axis == "x":
        has_left = any(p.edge == "left" for p in layout.ports)
        has_right = any(p.edge == "right" for p in layout.ports)
        if not has_left and not has_right:
            raise ValueError("無 left/right Port，無法計算 X 防洩漏（請先新增左右側 Port）")
        if has_left:
            x0 -= margin
        if has_right:
            x1 += margin
    else:
        has_bottom = any(p.edge == "bottom" for p in layout.ports)
        has_top = any(p.edge == "top" for p in layout.ports)
        if not has_bottom and not has_top:
            raise ValueError("無 top/bottom Port，無法計算 Y 防洩漏（請先新增上下側 Port）")
        if has_bottom:
            y0 -= margin
        if has_top:
            y1 += margin

    return merge_substrate_frame_with_content(layout, normalize_rect(x0, y0, x1, y1))


def port_aperture_span(port: ComposePort) -> tuple[float, float]:
    """Along-edge span (lo, hi) in world mm; prefers stored via span when available."""
    if port.via_index_2 >= 0 and abs(port.span_b_mm - port.span_a_mm) > _PITCH_EPS:
        return sorted((port.span_a_mm, port.span_b_mm))
    half_w = port.width_mm / 2.0
    return port.position_mm - half_w, port.position_mm + half_w


def recompute_port_geometry(port: ComposePort, layout: ComposeLayout) -> bool:
    """Refresh port world coordinates from stored via indices and current cell transform."""
    key = (port.col, port.row)
    placed = layout.placements.get(key)
    if placed is None:
        return False
    if port.via_index < 0 or port.via_index_2 < 0:
        return False
    vias = placed.module.vias
    if port.via_index >= len(vias) or port.via_index_2 >= len(vias):
        return False

    x0, y0, x1, y1 = cell_bounds(port.col, port.row, layout)
    via_pos = {idx: (wx, wy) for idx, wx, wy, _ in _world_vias(placed, layout)}
    if port.via_index not in via_pos or port.via_index_2 not in via_pos:
        return False
    wx1, wy1 = via_pos[port.via_index]
    wx2, wy2 = via_pos[port.via_index_2]

    if port.edge in ("left", "right"):
        span_a, span_b = wy1, wy2
    else:
        span_a, span_b = wx1, wx2

    lo, hi = sorted((span_a, span_b))
    if hi - lo <= _PITCH_EPS:
        return False

    port.span_a_mm = lo
    port.span_b_mm = hi
    port.position_mm = (lo + hi) / 2.0
    port.width_mm = hi - lo
    return True


def recompute_all_port_positions(layout: ComposeLayout) -> None:
    for port in layout.ports:
        recompute_port_geometry(port, layout)


def sync_layout_geometry(layout: ComposeLayout) -> None:
    """Reconcile pitch, module scales, and port coordinates after layout edits."""
    sync_pitch_from_placements(layout)
    for placed in layout.placements.values():
        apply_cell_fit_scales(placed, layout)
    recompute_all_port_positions(layout)


def add_port(layout: ComposeLayout, candidate: PortCandidate) -> ComposePort:
    port = ComposePort(
        col=candidate.col,
        row=candidate.row,
        edge=candidate.edge,
        position_mm=candidate.position_mm,
        width_mm=candidate.width_mm,
        via_index=candidate.via_index,
        via_index_2=candidate.via_index_2,
        span_a_mm=candidate.span_a_mm,
        span_b_mm=candidate.span_b_mm,
    )
    layout.ports.append(port)
    return port


def remove_port(layout: ComposeLayout, index: int) -> None:
    if 0 <= index < len(layout.ports):
        layout.ports.pop(index)


def _nearest_edge(x_mm: float, y_mm: float, col: int, row: int, layout: ComposeLayout) -> str | None:
    x0, y0, x1, y1 = cell_bounds(col, row, layout)
    w = x1 - x0
    h = y1 - y0
    thresh = max(min(w, h) * _EDGE_SNAP_FRAC, 0.4)
    dists = {
        "left": abs(x_mm - x0),
        "right": abs(x_mm - x1),
        "bottom": abs(y_mm - y0),
        "top": abs(y_mm - y1),
    }
    edge = min(dists, key=dists.get)
    if dists[edge] > thresh:
        return None
    return edge


def _world_vias(placed: PlacedModule, layout: ComposeLayout) -> list[tuple[int, float, float, CustomVia]]:
    cx, cy = cell_center(placed.col, placed.row, layout)
    out: list[tuple[int, float, float, CustomVia]] = []
    for idx, via in enumerate(placed.module.vias):
        tx, ty = transform_placed_local(placed, via.x_mm, via.y_mm)
        out.append((idx, cx + tx, cy + ty, via))
    return out


def _vias_near_edge(
    edge: str,
    vias: list[tuple[int, float, float, CustomVia]],
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> list[tuple[int, float, float, CustomVia]]:
    w = x1 - x0
    h = y1 - y0
    tol = max(min(w, h) * 0.28, 0.45)
    near: list[tuple[int, float, float, CustomVia]] = []
    for item in vias:
        idx, wx, wy, via = item
        if edge == "left" and abs(wx - x0) <= tol and y0 - _PITCH_EPS <= wy <= y1 + _PITCH_EPS:
            near.append(item)
        elif edge == "right" and abs(wx - x1) <= tol and y0 - _PITCH_EPS <= wy <= y1 + _PITCH_EPS:
            near.append(item)
        elif edge == "bottom" and abs(wy - y0) <= tol and x0 - _PITCH_EPS <= wx <= x1 + _PITCH_EPS:
            near.append(item)
        elif edge == "top" and abs(wy - y1) <= tol and x0 - _PITCH_EPS <= wx <= x1 + _PITCH_EPS:
            near.append(item)
    return near


def _best_via_pair_for_edge(
    edge: str,
    near: list[tuple[int, float, float, CustomVia]],
    cursor_x: float,
    cursor_y: float,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> PortCandidate | None:
    if len(near) < 2:
        return None

    best: PortCandidate | None = None
    best_d = float("inf")
    for i in range(len(near)):
        for j in range(i + 1, len(near)):
            idx1, wx1, wy1, _via1 = near[i]
            idx2, wx2, wy2, _via2 = near[j]
            if edge in ("left", "right"):
                span_a, span_b = wy1, wy2
                cursor = cursor_y
                edge_x = x0 if edge == "left" else x1
                line = (edge_x, span_a, edge_x, span_b)
            else:
                span_a, span_b = wx1, wx2
                cursor = cursor_x
                edge_y = y0 if edge == "bottom" else y1
                line = (span_a, edge_y, span_b, edge_y)
            if abs(span_b - span_a) <= _PITCH_EPS:
                continue
            mid = (span_a + span_b) / 2.0
            d = abs(mid - cursor)
            if d >= best_d:
                continue
            best_d = d
            lo, hi = sorted((span_a, span_b))
            best = PortCandidate(
                col=0,
                row=0,
                edge=edge,
                position_mm=mid,
                width_mm=hi - lo,
                via_index=idx1,
                via_index_2=idx2,
                span_a_mm=lo,
                span_b_mm=hi,
                line_x0=line[0],
                line_y0=line[1],
                line_x1=line[2],
                line_y1=line[3],
            )
    return best


def find_port_candidate(x_mm: float, y_mm: float, layout: ComposeLayout) -> PortCandidate | None:
    cell = cell_at_point(x_mm, y_mm, layout)
    if cell is None:
        cell = closest_cell(x_mm, y_mm, layout)
    if cell not in layout.placements:
        return None
    col, row = cell
    edge = _nearest_edge(x_mm, y_mm, col, row, layout)
    if edge is None:
        return None

    placed = layout.placements[cell]
    x0, y0, x1, y1 = cell_bounds(col, row, layout)
    near = _vias_near_edge(edge, _world_vias(placed, layout), x0, y0, x1, y1)
    candidate = _best_via_pair_for_edge(edge, near, x_mm, y_mm, x0, y0, x1, y1)
    if candidate is None:
        return None
    candidate.col = col
    candidate.row = row
    return candidate
