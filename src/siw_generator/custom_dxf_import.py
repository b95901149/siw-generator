"""Import DXF geometry for Custom via placement."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import ezdxf
from ezdxf.entities import LWPolyline

from siw_generator.custom_geometry import CustomVia, CustomViaRole, CustomViaType

_CLOSE_TOL_MM = 1e-3
_FULL_ARC_TOL = 1e-2
_SKIP_ENTITY_TYPES = frozenset(
    {
        "TEXT",
        "MTEXT",
        "DIMENSION",
        "LEADER",
        "INSERT",
        "POINT",
        "VIEWPORT",
        "IMAGE",
        "RAY",
        "XLINE",
        "ATTDEF",
        "ATTRIB",
        "HATCH",
        "SOLID",
        "3DFACE",
    }
)


@dataclass(frozen=True)
class DxfShapeTemplate:
    """Single imported shape in local coordinates (origin at import centroid)."""

    via_type: CustomViaType
    local_x_mm: float
    local_y_mm: float
    w_mm: float
    h_mm: float
    length_mm: float | None = None
    corner_r_mm: float | None = None


@dataclass
class DxfImportData:
    path: Path
    shapes: list[DxfShapeTemplate]

    @property
    def count(self) -> int:
        return len(self.shapes)


def _polyline_points(entity: LWPolyline) -> list[tuple[float, float]]:
    return [(float(x), float(y)) for x, y, *_ in entity.get_points(format="xy")]


def _points_geometrically_closed(points: list[tuple[float, float]]) -> bool:
    if len(points) < 3:
        return False
    x0, y0 = points[0]
    x1, y1 = points[-1]
    return math.hypot(x1 - x0, y1 - y1) <= _CLOSE_TOL_MM


def _is_closed_polyline(points: list[tuple[float, float]], *, flagged_closed: bool) -> bool:
    if len(points) < 3:
        return False
    if flagged_closed:
        return True
    return _points_geometrically_closed(points)


def _shape_from_circle(cx: float, cy: float, radius: float) -> tuple[float, float, DxfShapeTemplate]:
    diameter = max(radius, 0.0) * 2.0
    if diameter <= 0:
        raise ValueError("circle radius must be positive")
    return cx, cy, DxfShapeTemplate(
        via_type=CustomViaType.CIRCLE,
        local_x_mm=0.0,
        local_y_mm=0.0,
        w_mm=diameter,
        h_mm=diameter,
    )


def _shape_from_polyline(points: list[tuple[float, float]]) -> tuple[float, float, DxfShapeTemplate]:
    if len(points) < 3:
        raise ValueError("polyline needs at least 3 points")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    width = x1 - x0
    height = y1 - y0
    if width <= 0 or height <= 0:
        raise ValueError("degenerate polyline bounds")
    if len(points) == 4 and abs(width - height) < 1e-3:
        side = (width + height) / 2.0
        return cx, cy, DxfShapeTemplate(
            via_type=CustomViaType.SQUARE,
            local_x_mm=0.0,
            local_y_mm=0.0,
            w_mm=side,
            h_mm=side,
        )
    if len(points) == 4:
        return cx, cy, DxfShapeTemplate(
            via_type=CustomViaType.SQUARE,
            local_x_mm=0.0,
            local_y_mm=0.0,
            w_mm=width,
            h_mm=height,
        )
    length = max(width, height)
    slot_w = min(width, height)
    corner = min(slot_w, length) / 2.0
    return cx, cy, DxfShapeTemplate(
        via_type=CustomViaType.SLOT,
        local_x_mm=0.0,
        local_y_mm=0.0,
        w_mm=slot_w,
        h_mm=slot_w,
        length_mm=length,
        corner_r_mm=corner,
    )


def _shape_from_ellipse(entity) -> tuple[float, float, DxfShapeTemplate]:
    cx = float(entity.dxf.center.x)
    cy = float(entity.dxf.center.y)
    major = float(entity.dxf.major_axis.magnitude)
    ratio = float(entity.dxf.ratio)
    minor = major * ratio
    if major <= 0 or minor <= 0:
        raise ValueError("degenerate ellipse")
    if abs(major - minor) <= _CLOSE_TOL_MM:
        return _shape_from_circle(cx, cy, (major + minor) / 2.0)
    width = major * 2.0
    height = minor * 2.0
    return cx, cy, DxfShapeTemplate(
        via_type=CustomViaType.SQUARE,
        local_x_mm=0.0,
        local_y_mm=0.0,
        w_mm=width,
        h_mm=height,
    )


def _is_full_arc(entity) -> bool:
    start = float(entity.dxf.start_angle) % (2.0 * math.pi)
    end = float(entity.dxf.end_angle) % (2.0 * math.pi)
    span = (end - start) % (2.0 * math.pi)
    return span <= _FULL_ARC_TOL or abs(span - 2.0 * math.pi) <= _FULL_ARC_TOL


def _shape_from_entity(entity) -> tuple[float, float, DxfShapeTemplate] | None:
    dxftype = entity.dxftype()
    if dxftype == "CIRCLE":
        cx = float(entity.dxf.center.x)
        cy = float(entity.dxf.center.y)
        return _shape_from_circle(cx, cy, float(entity.dxf.radius))
    if dxftype == "ARC" and _is_full_arc(entity):
        cx = float(entity.dxf.center.x)
        cy = float(entity.dxf.center.y)
        return _shape_from_circle(cx, cy, float(entity.dxf.radius))
    if dxftype == "ELLIPSE":
        return _shape_from_ellipse(entity)
    if dxftype == "LWPOLYLINE":
        points = _polyline_points(entity)
        if not _is_closed_polyline(points, flagged_closed=bool(entity.closed)):
            return None
        return _shape_from_polyline(points)
    if dxftype == "POLYLINE":
        points = [(float(v.dxf.location.x), float(v.dxf.location.y)) for v in entity.vertices]
        if not _is_closed_polyline(points, flagged_closed=bool(entity.is_closed)):
            return None
        return _shape_from_polyline(points)
    if dxftype == "SPLINE":
        flagged = bool(getattr(entity, "closed", False))
        points = [(float(p.x), float(p.y)) for p in entity.flattening(0.05)]
        if not _is_closed_polyline(points, flagged_closed=flagged):
            return None
        return _shape_from_polyline(points)
    return None


def _collect_world_shapes(msp) -> list[tuple[float, float, DxfShapeTemplate]]:
    world: list[tuple[float, float, DxfShapeTemplate]] = []
    for entity in msp:
        if entity.dxftype() in _SKIP_ENTITY_TYPES:
            continue
        try:
            parsed = _shape_from_entity(entity)
        except (ValueError, AttributeError, TypeError):
            continue
        if parsed is not None:
            world.append(parsed)
    return world


def load_dxf_shapes(path: str | Path) -> DxfImportData:
    """Parse closed curves (any layer) from a DXF file."""
    src = Path(path)
    if not src.is_file():
        raise FileNotFoundError(f"找不到 DXF：{src}")
    try:
        doc = ezdxf.readfile(src)
    except ezdxf.DXFError as exc:
        raise ValueError(f"無法讀取 DXF：{exc}") from exc

    world = _collect_world_shapes(doc.modelspace())
    if not world:
        raise ValueError("DXF 中找不到可匯入的封閉曲線（圓、封閉多段線、橢圓等）")

    origin_x = sum(item[0] for item in world) / len(world)
    origin_y = sum(item[1] for item in world) / len(world)
    shapes: list[DxfShapeTemplate] = []
    for cx, cy, template in world:
        shapes.append(
            DxfShapeTemplate(
                via_type=template.via_type,
                local_x_mm=(cx - origin_x),
                local_y_mm=(cy - origin_y),
                w_mm=template.w_mm,
                h_mm=template.h_mm,
                length_mm=template.length_mm,
                corner_r_mm=template.corner_r_mm,
            )
        )
    return DxfImportData(path=src, shapes=shapes)


def dxf_shapes_to_vias(
    data: DxfImportData,
    *,
    origin_x_mm: float,
    origin_y_mm: float,
    scale: float,
    via_role: CustomViaRole,
) -> list[CustomVia]:
    """Place imported DXF shapes at world origin with scale."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    vias: list[CustomVia] = []
    for shape in data.shapes:
        vias.append(
            CustomVia(
                x_mm=origin_x_mm + shape.local_x_mm * scale,
                y_mm=origin_y_mm + shape.local_y_mm * scale,
                via_type=shape.via_type,
                via_role=via_role,
                w_mm=shape.w_mm * scale,
                h_mm=shape.h_mm * scale,
                length_mm=shape.length_mm * scale if shape.length_mm is not None else None,
                corner_r_mm=shape.corner_r_mm * scale if shape.corner_r_mm is not None else None,
            )
        )
    return vias
