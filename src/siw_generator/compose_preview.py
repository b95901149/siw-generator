"""Matplotlib preview for module grid composition."""

from __future__ import annotations

import matplotlib

matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon, Rectangle

from siw_generator.compose_geometry import (
    ComposeLayout,
    ComposePort,
    PlacedModule,
    PortCandidate,
    cell_bounds,
    cell_center,
    column_boundaries,
    port_aperture_span,
    row_boundaries,
    transform_local,
)
from siw_generator.custom_geometry import CustomModuleDefinition, CustomVia, CustomViaType, via_preview_style
from siw_generator.via_shapes import slot_outline

_EDGE_LABELS = {"left": "左", "right": "右", "bottom": "下", "top": "上"}


def _draw_via(
    ax,
    via: CustomVia,
    ox: float,
    oy: float,
    *,
    rotation_deg: int = 0,
    mirror_x: bool = False,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    face: str,
    edge: str,
    alpha: float,
    lw: float = 0.6,
    ls: str = "-",
) -> None:
    if via.via_type is CustomViaType.CIRCLE:
        tx, ty = transform_local(
            via.x_mm * scale_x,
            via.y_mm * scale_y,
            rotation_deg=rotation_deg,
            mirror_x=mirror_x,
        )
        radius = via.w_mm * 0.5 * max(scale_x, scale_y)
        ax.add_patch(
            Circle(
                (ox + tx, oy + ty),
                radius,
                fill=True,
                facecolor=face,
                edgecolor=edge,
                linewidth=lw,
                linestyle=ls,
                alpha=alpha,
            )
        )
    elif via.via_type is CustomViaType.SQUARE:
        half_w = via.w_mm * scale_x / 2.0
        half_h = via.h_mm * scale_y / 2.0
        corners = [
            transform_local(
                via.x_mm * scale_x + dx,
                via.y_mm * scale_y + dy,
                rotation_deg=rotation_deg,
                mirror_x=mirror_x,
            )
            for dx, dy in [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)]
        ]
        ax.add_patch(
            Polygon(
                [(ox + x, oy + y) for x, y in corners],
                closed=True,
                fill=True,
                facecolor=face,
                edgecolor=edge,
                linewidth=lw,
                linestyle=ls,
                alpha=alpha,
            )
        )
    else:
        length = (via.length_mm or via.w_mm) * scale_x
        width = via.w_mm * scale_y
        corner = via.corner_r_mm or min(via.w_mm, via.length_mm or via.w_mm) / 2.0
        corner *= max(scale_x, scale_y)
        outline = slot_outline(via.x_mm * scale_x, via.y_mm * scale_y, length, width, corner)
        transformed = [
            (
                ox + transform_local(px, py, rotation_deg=rotation_deg, mirror_x=mirror_x)[0],
                oy + transform_local(px, py, rotation_deg=rotation_deg, mirror_x=mirror_x)[1],
            )
            for px, py in outline
        ]
        ax.add_patch(
            Polygon(
                transformed,
                closed=True,
                fill=True,
                facecolor=face,
                edgecolor=edge,
                linewidth=max(lw, 0.8),
                linestyle=ls,
                alpha=alpha,
            )
        )


def draw_module_at(
    ax,
    module: CustomModuleDefinition,
    center_x: float,
    center_y: float,
    *,
    rotation_deg: int = 0,
    mirror_x: bool = False,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    substrate_face: str,
    substrate_edge: str,
    via_face: str,
    via_edge: str,
    substrate_alpha: float,
    via_alpha: float,
    edge_lw: float = 1.0,
    draw_siw: bool = True,
) -> None:
    half_l = module.substrate_length_mm * scale_x / 2.0
    half_w = module.substrate_width_mm * scale_y / 2.0
    local_corners = [
        (-half_l, -half_w),
        (half_l, -half_w),
        (half_l, half_w),
        (-half_l, half_w),
    ]
    corners = [
        (
            center_x + transform_local(x, y, rotation_deg=rotation_deg, mirror_x=mirror_x)[0],
            center_y + transform_local(x, y, rotation_deg=rotation_deg, mirror_x=mirror_x)[1],
        )
        for x, y in local_corners
    ]
    ax.add_patch(
        Polygon(
            corners,
            closed=True,
            fill=True,
            facecolor=substrate_face,
            edgecolor=substrate_edge,
            linewidth=edge_lw,
            alpha=substrate_alpha,
        )
    )
    if draw_siw and module.siw_width_mm is not None:
        siw_w = module.siw_width_mm * scale_y
        for sign in (-1.0, 1.0):
            line = [
                transform_local(
                    x * scale_x,
                    sign * siw_w / 2.0,
                    rotation_deg=rotation_deg,
                    mirror_x=mirror_x,
                )
                for x in (-module.substrate_length_mm / 2.0, module.substrate_length_mm / 2.0)
            ]
            ax.plot(
                [center_x + line[0][0], center_x + line[1][0]],
                [center_y + line[0][1], center_y + line[1][1]],
                color="#1565c0",
                linestyle="--",
                linewidth=0.6,
                alpha=min(1.0, via_alpha + 0.15),
            )
    for via in module.vias:
        face, edge, alpha, lw, ls = via_preview_style(via)
        _draw_via(
            ax,
            via,
            center_x,
            center_y,
            rotation_deg=rotation_deg,
            mirror_x=mirror_x,
            scale_x=scale_x,
            scale_y=scale_y,
            face=face,
            edge=edge,
            alpha=alpha,
            lw=lw,
            ls=ls,
        )


def _draw_filled_cell(ax, layout: ComposeLayout, col: int, row: int) -> None:
    x0, y0, x1, y1 = cell_bounds(col, row, layout)
    ax.add_patch(
        Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            facecolor="#a5d6a7",
            edgecolor="#66bb6a",
            linewidth=0.8,
            alpha=0.45,
        )
    )


def _draw_substrate_frame_fill(ax, frame: tuple[float, float, float, float]) -> None:
    fx0, fy0, fx1, fy1 = frame
    ax.add_patch(
        Rectangle(
            (fx0, fy0),
            fx1 - fx0,
            fy1 - fy0,
            facecolor="#c8e6c9",
            edgecolor="none",
            alpha=0.42,
            zorder=0.8,
        )
    )


def _draw_substrate_frame_outline(ax, frame: tuple[float, float, float, float]) -> None:
    fx0, fy0, fx1, fy1 = frame
    ax.add_patch(
        Rectangle(
            (fx0, fy0),
            fx1 - fx0,
            fy1 - fy0,
            fill=False,
            edgecolor="#d32f2f",
            linewidth=2.0,
            linestyle="-",
            alpha=0.95,
            zorder=8.0,
        )
    )


def _draw_port(ax, layout: ComposeLayout, port: ComposePort) -> None:
    x0, y0, x1, y1 = cell_bounds(port.col, port.row, layout)
    span_lo, span_hi = port_aperture_span(port)
    if port.edge == "left":
        xs = [x0, x0]
        ys = [span_lo, span_hi]
    elif port.edge == "right":
        xs = [x1, x1]
        ys = [span_lo, span_hi]
    elif port.edge == "bottom":
        xs = [span_lo, span_hi]
        ys = [y0, y0]
    else:
        xs = [span_lo, span_hi]
        ys = [y1, y1]
    ax.plot(xs, ys, color="#7b1fa2", linewidth=3.0, solid_capstyle="butt", alpha=0.9)


def _draw_port_ghost(ax, candidate: PortCandidate) -> None:
    ax.plot(
        [candidate.line_x0, candidate.line_x1],
        [candidate.line_y0, candidate.line_y1],
        color="#ce93d8",
        linewidth=2.5,
        linestyle="--",
        alpha=0.85,
    )


def _draw_grid(ax, layout: ComposeLayout) -> None:
    grid_color = "#4fc3f7"
    for x in column_boundaries(layout):
        ax.axvline(x, color=grid_color, linestyle="--", linewidth=0.9, alpha=0.75)
    for y in row_boundaries(layout):
        ax.axhline(y, color=grid_color, linestyle="--", linewidth=0.9, alpha=0.75)


def _draw_cell_highlight(ax, layout: ComposeLayout, col: int, row: int, *, color: str, lw: float) -> None:
    x0, y0, x1, y1 = cell_bounds(col, row, layout)
    ax.add_patch(
        Rectangle(
            (x0, y0),
            x1 - x0,
            y1 - y0,
            fill=False,
            edgecolor=color,
            linewidth=lw,
        )
    )


def port_summary(port: ComposePort, index: int) -> tuple[str, ...]:
    edge = _EDGE_LABELS.get(port.edge, port.edge)
    return (
        str(index + 1),
        f"({port.col},{port.row})",
        edge,
        f"{port.width_mm:.4f}",
        f"{port.position_mm:.3f}",
    )


def render_compose_main(
    layout: ComposeLayout,
    figure: Figure | None = None,
    *,
    ghost_module: CustomModuleDefinition | None = None,
    ghost_cell: tuple[int, int] | None = None,
    ghost_rotation_deg: int = 0,
    ghost_mirror_x: bool = False,
    selected_cell: tuple[int, int] | None = None,
    drag_target_cell: tuple[int, int] | None = None,
    drag_module: PlacedModule | None = None,
    selection_rect: tuple[float, float, float, float] | None = None,
    port_candidate: PortCandidate | None = None,
    pending_cell: tuple[int, int] | None = None,
    hover_cell: tuple[int, int] | None = None,
) -> Figure:
    if figure is None:
        figure = Figure(figsize=(7, 7), dpi=100)

    figure.clear()
    ax = figure.add_subplot(111)

    if layout.substrate_frame is not None:
        _draw_substrate_frame_fill(ax, layout.substrate_frame)
    else:
        _draw_grid(ax, layout)

    for col, row in layout.filled_cells:
        if (col, row) not in layout.placements:
            _draw_filled_cell(ax, layout, col, row)

    for placed in layout.placements.values():
        cx, cy = cell_center(placed.col, placed.row, layout)
        draw_module_at(
            ax,
            placed.module,
            cx,
            cy,
            rotation_deg=placed.rotation_deg,
            mirror_x=placed.mirror_x,
            scale_x=placed.scale_x,
            scale_y=placed.scale_y,
            substrate_face="#c8e6c9",
            substrate_edge="#66bb6a",
            via_face="#fff59d",
            via_edge="#f9a825",
            substrate_alpha=0.45,
            via_alpha=0.55,
            edge_lw=0.9,
        )

    for port in layout.ports:
        _draw_port(ax, layout, port)

    if ghost_module is not None and ghost_cell is not None:
        col, row = ghost_cell
        cx, cy = cell_center(col, row, layout)
        draw_module_at(
            ax,
            ghost_module,
            cx,
            cy,
            rotation_deg=ghost_rotation_deg,
            mirror_x=ghost_mirror_x,
            substrate_face="#a5d6a7",
            substrate_edge="#43a047",
            via_face="#fff9c4",
            via_edge="#fbc02d",
            substrate_alpha=0.28,
            via_alpha=0.38,
            edge_lw=1.0,
        )

    if drag_module is not None and drag_target_cell is not None:
        col, row = drag_target_cell
        cx, cy = cell_center(col, row, layout)
        draw_module_at(
            ax,
            drag_module.module,
            cx,
            cy,
            rotation_deg=drag_module.rotation_deg,
            mirror_x=drag_module.mirror_x,
            scale_x=drag_module.scale_x,
            scale_y=drag_module.scale_y,
            substrate_face="#ffe082",
            substrate_edge="#ffa000",
            via_face="#fff8e1",
            via_edge="#ff8f00",
            substrate_alpha=0.35,
            via_alpha=0.45,
            edge_lw=1.0,
        )

    if port_candidate is not None:
        _draw_port_ghost(ax, port_candidate)

    if pending_cell is not None:
        pc, pr = pending_cell
        _draw_cell_highlight(ax, layout, pc, pr, color="#1976d2", lw=2.4)

    if hover_cell is not None:
        hc, hr = hover_cell
        hover_color = "#ffb74d" if hover_cell == pending_cell else "#ff9800"
        hover_lw = 2.6 if hover_cell == pending_cell else 2.0
        _draw_cell_highlight(ax, layout, hc, hr, color=hover_color, lw=hover_lw)

    if layout.substrate_frame is not None:
        _draw_substrate_frame_outline(ax, layout.substrate_frame)

    if selection_rect is not None:
        sx0, sy0, sx1, sy1 = selection_rect
        ax.add_patch(
            Rectangle(
                (sx0, sy0),
                sx1 - sx0,
                sy1 - sy0,
                fill=False,
                edgecolor="#ff5722",
                linewidth=1.2,
                linestyle="--",
                alpha=0.9,
            )
        )

    if selected_cell is not None:
        col, row = selected_cell
        if (col, row) in layout.placements:
            _draw_cell_highlight(ax, layout, col, row, color="#ff9800", lw=2.2)

    half_w = layout.total_width_mm / 2.0
    half_h = layout.total_height_mm / 2.0
    margin = max(layout.default_pitch_x_mm, layout.default_pitch_y_mm) * 0.15 + 0.5
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    fill_n = len([c for c in layout.filled_cells if c not in layout.placements])
    ax.set_title(
        f"組合 — {layout.m_count}×{layout.n_count} | module {len(layout.placements)} | "
        f"填補 {fill_n} | Port {len(layout.ports)}"
    )
    ax.set_xlim(-half_w - margin, half_w + margin)
    ax.set_ylim(-half_h - margin, half_h + margin)
    ax.grid(False)
    figure.subplots_adjust(left=0.10, right=0.98, top=0.92, bottom=0.10)
    return figure


def render_module_thumbnail(
    module: CustomModuleDefinition,
    figure: Figure | None = None,
    *,
    title: str = "",
    rotation_deg: int = 0,
    mirror_x: bool = False,
) -> Figure:
    if figure is None:
        figure = Figure(figsize=(3.5, 3.5), dpi=100)

    figure.clear()
    ax = figure.add_subplot(111)
    draw_module_at(
        ax,
        module,
        0.0,
        0.0,
        rotation_deg=rotation_deg,
        mirror_x=mirror_x,
        substrate_face="#fff9c4",
        substrate_edge="#f9a825",
        via_face="#ffeb3b",
        via_edge="#f57f17",
        substrate_alpha=0.55,
        via_alpha=0.85,
        edge_lw=1.2,
    )
    half_l = module.substrate_length_mm / 2.0
    half_w = module.substrate_width_mm / 2.0
    if rotation_deg in (90, 270):
        half_l, half_w = half_w, half_l
    margin = max(half_l, half_w) * 0.12 + 0.3
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title or "Module", fontsize=9)
    ax.set_xlim(-half_l - margin, half_l + margin)
    ax.set_ylim(-half_w - margin, half_w + margin)
    ax.grid(True, alpha=0.2)
    figure.subplots_adjust(left=0.12, right=0.96, top=0.88, bottom=0.12)
    return figure
