"""Matplotlib preview for custom via modules."""

from __future__ import annotations

import matplotlib

matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Polygon, Rectangle
from matplotlib.artist import Artist

from siw_generator.custom_geometry import (
    CustomModuleDefinition,
    CustomVia,
    CustomViaType,
    line_via_positions,
    via_preview_style,
)
from siw_generator.via_shapes import slot_outline

_PREVIEW_MARGINS = dict(left=0.14, right=0.96, top=0.90, bottom=0.12)


def _via_signature(via: CustomVia) -> tuple:
    return (
        via.x_mm,
        via.y_mm,
        via.via_type,
        via.via_role,
        via.w_mm,
        via.h_mm,
        via.length_mm,
        via.corner_r_mm,
    )


def _static_signature(
    module: CustomModuleDefinition,
    selected_hole_indices: frozenset[int],
    hidden_hole_indices: frozenset[int],
) -> tuple:
    return (
        module.substrate_length_mm,
        module.substrate_width_mm,
        module.siw_width_mm,
        selected_hole_indices,
        hidden_hole_indices,
        tuple(_via_signature(v) for v in module.vias),
    )


def _draw_via(
    ax: Axes,
    via: CustomVia,
    *,
    ghost: bool = False,
    selected: bool = False,
    moving: bool = False,
) -> list[Artist]:
    face, edge, alpha, lw, ls = via_preview_style(via, ghost=ghost, selected=selected, moving=moving)
    artists: list[Artist] = []

    if via.via_type is CustomViaType.CIRCLE:
        patch = Circle(
            (via.x_mm, via.y_mm),
            via.w_mm / 2.0,
            fill=True,
            facecolor=face,
            edgecolor=edge,
            linewidth=lw,
            linestyle=ls,
            alpha=alpha,
        )
        ax.add_patch(patch)
        artists.append(patch)
    elif via.via_type is CustomViaType.SQUARE:
        patch = Rectangle(
            (via.x_mm - via.w_mm / 2.0, via.y_mm - via.h_mm / 2.0),
            via.w_mm,
            via.h_mm,
            fill=True,
            facecolor=face,
            edgecolor=edge,
            linewidth=lw,
            linestyle=ls,
            alpha=alpha,
        )
        ax.add_patch(patch)
        artists.append(patch)
    else:
        length = via.length_mm or via.w_mm
        width = via.w_mm
        corner = via.corner_r_mm or min(width, length) / 2.0
        outline = slot_outline(via.x_mm, via.y_mm, length, width, corner)
        patch = Polygon(
            outline,
            closed=True,
            fill=not ghost,
            facecolor=face if not ghost else "none",
            edgecolor=edge,
            linewidth=1.2 if not ghost else lw,
            linestyle=ls,
            alpha=alpha,
        )
        ax.add_patch(patch)
        artists.append(patch)
    return artists


def _draw_static(
    ax: Axes,
    module: CustomModuleDefinition,
    selected_hole_indices: frozenset[int],
    hidden_hole_indices: frozenset[int],
) -> None:
    half_l = module.substrate_length_mm / 2.0
    half_w = module.substrate_width_mm / 2.0
    corners = [
        (-half_l, -half_w),
        (half_l, -half_w),
        (half_l, half_w),
        (-half_l, half_w),
    ]
    ax.add_patch(
        Polygon(
            corners,
            closed=True,
            fill=False,
            edgecolor="#2e7d32",
            linewidth=1.5,
            label="基板",
        )
    )
    ax.axvline(0.0, color="#9e9e9e", linestyle=":", linewidth=0.8, alpha=0.6)

    if module.siw_width_mm is not None:
        siw_w = module.siw_width_mm
        ax.plot(
            [-half_l, half_l],
            [-siw_w / 2.0, -siw_w / 2.0],
            color="#1565c0",
            linestyle="--",
            linewidth=0.8,
            alpha=0.7,
        )
        ax.plot(
            [-half_l, half_l],
            [siw_w / 2.0, siw_w / 2.0],
            color="#1565c0",
            linestyle="--",
            linewidth=0.8,
            alpha=0.7,
            label="SIW 側壁",
        )

    for idx, via in enumerate(module.vias):
        if idx in hidden_hole_indices or idx in selected_hole_indices:
            continue
        _draw_via(ax, via, ghost=False)

    for idx in sorted(selected_hole_indices):
        if idx in hidden_hole_indices:
            continue
        if 0 <= idx < len(module.vias):
            _draw_via(ax, module.vias[idx], ghost=False, selected=True)

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    ax.set_title(f"Custom Via — {len(module.vias)} 個")
    ax.grid(True, alpha=0.25)
    margin = max(module.substrate_length_mm, module.substrate_width_mm) * 0.08 + 0.5
    ax.set_xlim(-half_l - margin, half_l + margin)
    ax.set_ylim(-half_w - margin, half_w + margin)
    ax.legend(loc="upper right", fontsize=8)


class CustomPreviewRenderer:
    """Cache static preview; only redraw ghost overlay on pointer motion."""

    def __init__(self, figure: Figure) -> None:
        self.figure = figure
        self._ax: Axes | None = None
        self._static_key: tuple | None = None
        self._ghost_artists: list[Artist] = []
        self._line_artists: list[Artist] = []

    @property
    def has_static(self) -> bool:
        return self._ax is not None and self._static_key is not None

    def invalidate(self) -> None:
        self._static_key = None
        self._ax = None
        self._ghost_artists = []
        self._line_artists = []

    def _clear_ghost(self) -> None:
        if not self._ghost_artists or self._ax is None:
            self._ghost_artists = []
            return
        for artist in self._ghost_artists:
            artist.remove()
        self._ghost_artists = []

    def _clear_line(self) -> None:
        if not self._line_artists or self._ax is None:
            self._line_artists = []
            return
        for artist in self._line_artists:
            artist.remove()
        self._line_artists = []

    def draw_static(
        self,
        module: CustomModuleDefinition,
        *,
        selected_hole_indices: frozenset[int] | None = None,
        hidden_hole_indices: frozenset[int] | None = None,
    ) -> None:
        selected = selected_hole_indices if selected_hole_indices is not None else frozenset()
        hidden = hidden_hole_indices if hidden_hole_indices is not None else frozenset()
        key = _static_signature(module, selected, hidden)
        if key == self._static_key and self._ax is not None:
            return
        self._static_key = key
        self._clear_ghost()
        self._clear_line()
        self.figure.clear()
        self._ax = self.figure.add_subplot(111)
        _draw_static(self._ax, module, selected, hidden)
        self.figure.subplots_adjust(**_PREVIEW_MARGINS)

    def set_ghost(self, ghost_via: CustomVia | None) -> None:
        self.set_placement_overlay(ghost_via=ghost_via)

    def set_placement_overlay(
        self,
        *,
        ghost_via: CustomVia | None = None,
        line_start: tuple[float, float] | None = None,
        line_end: tuple[float, float] | None = None,
        line_template: CustomVia | None = None,
        line_pitch_mm: float | None = None,
        selection_rect: tuple[float, float, float, float] | None = None,
        move_preview_vias: list[CustomVia] | None = None,
        dxf_preview_vias: list[CustomVia] | None = None,
    ) -> None:
        self._clear_ghost()
        self._clear_line()
        if self._ax is None:
            return
        ax = self._ax
        if move_preview_vias:
            for via in move_preview_vias:
                self._ghost_artists.extend(_draw_via(ax, via, ghost=False, moving=True))
        if dxf_preview_vias:
            for via in dxf_preview_vias:
                self._ghost_artists.extend(_draw_via(ax, via, ghost=True))
        if ghost_via is not None:
            self._ghost_artists.extend(_draw_via(ax, ghost_via, ghost=True))
        if selection_rect is not None:
            sx0, sy0, sx1, sy1 = selection_rect
            patch = Rectangle(
                (sx0, sy0),
                sx1 - sx0,
                sy1 - sy0,
                fill=False,
                edgecolor="#ff5722",
                linewidth=1.2,
                linestyle="--",
                alpha=0.9,
            )
            ax.add_patch(patch)
            self._line_artists.append(patch)
        if (
            line_start is not None
            and line_end is not None
            and line_template is not None
            and line_pitch_mm is not None
            and line_pitch_mm > 0
        ):
            line = Line2D(
                [line_start[0], line_end[0]],
                [line_start[1], line_end[1]],
                color="#1976d2",
                linestyle="--",
                linewidth=1.2,
                alpha=0.7,
            )
            ax.add_line(line)
            self._line_artists.append(line)
            for x, y in line_via_positions(
                line_start[0],
                line_start[1],
                line_end[0],
                line_end[1],
                line_pitch_mm,
            ):
                ghost = CustomVia(
                    x_mm=x,
                    y_mm=y,
                    via_type=line_template.via_type,
                    via_role=line_template.via_role,
                    w_mm=line_template.w_mm,
                    h_mm=line_template.h_mm,
                    length_mm=line_template.length_mm,
                    corner_r_mm=line_template.corner_r_mm,
                )
                self._line_artists.extend(_draw_via(ax, ghost, ghost=True))


def render_custom_preview(
    module: CustomModuleDefinition,
    figure: Figure | None = None,
    *,
    ghost_via: CustomVia | None = None,
    selected_hole_indices: frozenset[int] | None = None,
) -> Figure:
    if figure is None:
        figure = Figure(figsize=(6, 6), dpi=100)
    renderer = CustomPreviewRenderer(figure)
    renderer.draw_static(module, selected_hole_indices=selected_hole_indices)
    renderer.set_ghost(ghost_via)
    return figure
