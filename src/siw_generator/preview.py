"""Matplotlib preview for SIW via layout."""

from __future__ import annotations

import matplotlib

matplotlib.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon, Rectangle

from siw_generator.siw_geometry import SIWGeometry
from siw_generator.via_shapes import slot_outline


def render_preview(
    geometry: SIWGeometry,
    figure: Figure | None = None,
    *,
    overlay_slot_geometry: SIWGeometry | None = None,
) -> Figure:
    """Draw substrate outline, vias, and waveguide ports."""
    if figure is None:
        figure = Figure(figsize=(6, 6), dpi=100)

    figure.clear()
    ax = figure.add_subplot(111)
    p = geometry.params

    corners = geometry.substrate_corners_mm
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

    siw_w = geometry.siw_width_mm
    half_l = p.substrate_length_mm / 2.0
    ax.axvline(0.0, color="#9e9e9e", linestyle=":", linewidth=0.8, alpha=0.6, label="X=0")
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

    for via in geometry.vias:
        ax.add_patch(
            Circle(
                (via.x_mm, via.y_mm),
                via.diameter_mm / 2.0,
                fill=True,
                facecolor="#c62828",
                edgecolor="#8e0000",
                linewidth=0.4,
            )
        )

    for slot in geometry.slot_vias:
        outline = slot_outline(
            slot.x_mm, slot.y_mm, slot.length_mm, slot.width_mm, slot.corner_r_mm
        )
        ax.add_patch(
            Polygon(
                outline,
                closed=True,
                fill=False,
                facecolor="#c62828",
                edgecolor="#c62828",
                linewidth=1.2,
            )
        )

    if overlay_slot_geometry:
        overlay_corners = overlay_slot_geometry.substrate_corners_mm
        ax.add_patch(
            Polygon(
                overlay_corners,
                closed=True,
                fill=False,
                edgecolor="#ef6c00",
                linewidth=1.6,
                linestyle="--",
                label="Slot 基板",
            )
        )
        for slot in overlay_slot_geometry.slot_vias:
            outline = slot_outline(
                slot.x_mm, slot.y_mm, slot.length_mm, slot.width_mm, slot.corner_r_mm
            )
            ax.add_patch(
                Polygon(
                    outline,
                    closed=True,
                    fill=False,
                    edgecolor="#ef6c00",
                    linewidth=1.4,
                    linestyle="--",
                    label="Slot 疊圖",
                )
            )

    port_colors = {"Port1": "#6a1b9a", "Port2": "#4527a0"}
    for port in geometry.ports:
        if not port.enabled:
            continue
        height = port.y_max_mm - port.y_min_mm
        # YZ plane projected on XY view: vertical segment at X
        ax.plot(
            [port.x_mm, port.x_mm],
            [port.y_min_mm, port.y_max_mm],
            color=port_colors.get(port.name, "#7b1fa2"),
            linewidth=3.0,
            solid_capstyle="butt",
            label=f"{port.name} (YZ)",
        )
        ax.annotate(
            f"{port.name}\nYZ\nW={port.width_mm:.2f}",
            (port.x_mm, port.y_max_mm + siw_w * 0.06),
            ha="center",
            fontsize=8,
            color=port_colors.get(port.name, "#4a148c"),
        )

    x_min, x_max = corners[0][0], corners[1][0]
    y_min, y_max = corners[0][1], corners[2][1]
    if overlay_slot_geometry:
        oc = overlay_slot_geometry.substrate_corners_mm
        x_min = min(x_min, oc[0][0])
        x_max = max(x_max, oc[1][0])
        y_min = min(y_min, oc[0][1])
        y_max = max(y_max, oc[2][1])
    pad = max(x_max - x_min, y_max - y_min) * 0.08
    ax.set_xlim(x_min - pad, x_max + pad)
    ax.set_ylim(y_min - pad, y_max + pad)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", alpha=0.4)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Y (mm)")
    port_info = ", ".join(f"{pt.name} YZ@{pt.x_mm:.2f}" for pt in geometry.ports if pt.enabled)
    clip = " [截掉超出]" if geometry.via_count_clipped else ""
    via_label = "slots" if geometry.is_slot else "vias"
    ax.set_title(
        f"SIW {'Slot' if geometry.is_slot else 'Via'} 預覽 | {geometry.via_count} {via_label}{clip} | "
        f"孔距 {geometry.via_pitch_mm:.3f} mm\n{port_info}"
    )
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc="upper right", fontsize=8)
    figure.tight_layout()
    return figure


def render_preview_yz(geometry: SIWGeometry, figure: Figure | None = None) -> Figure:
    """YZ-plane cross-section focused on Port aperture and via sidewalls."""
    if figure is None:
        figure = Figure(figsize=(6, 4), dpi=100)

    figure.clear()
    ax = figure.add_subplot(111)
    p = geometry.params
    stack = p.stackup
    z_layers = stack.z_bounds_centered()
    siw_w = geometry.siw_width_mm
    y_bot = -siw_w / 2.0
    y_top = siw_w / 2.0
    via_r = p.via_diameter_mm / 2.0
    z0, z1 = z_layers["full_stack"]

    ports = [pt for pt in geometry.ports if pt.enabled]
    if not ports:
        ax.text(0.5, 0.5, "無 Port", ha="center", va="center", transform=ax.transAxes)
        return figure

    pt = ports[0]
    port_w = pt.width_mm
    port_h = pt.height_mm
    y_c = (pt.y_min_mm + pt.y_max_mm) / 2.0
    z_c = (pt.z_min_mm + pt.z_max_mm) / 2.0

    # View spans ~2.5× port size (within 2~3× range)
    zoom = 2.5
    half_y = port_w * zoom / 2.0
    half_z = port_h * zoom / 2.0
    y_lo, y_hi = y_c - half_y, y_c + half_y
    z_lo, z_hi = z_c - half_z, z_c + half_z

    def _clip_y(y0: float, y1: float) -> tuple[float, float] | None:
        a, b = max(y0, y_lo), min(y1, y_hi)
        return (a, b) if a < b else None

    def _clip_z(z0v: float, z1v: float) -> tuple[float, float] | None:
        a, b = max(z0v, z_lo), min(z1v, z_hi)
        return (a, b) if a < b else None

    half_w_sub = p.substrate_width_mm / 2.0
    sub_y = _clip_y(-half_w_sub, half_w_sub)
    sub_z = _clip_z(z0, z1)
    if sub_y and sub_z:
        ax.add_patch(
            Rectangle(
                (sub_y[0], sub_z[0]),
                sub_y[1] - sub_y[0],
                sub_z[1] - sub_z[0],
                facecolor="#e8f5e9",
                edgecolor="#2e7d32",
                linewidth=1.0,
                alpha=0.5,
                label="基板",
            )
        )

    for layer_key, color in (("bottom_copper", "#ffe082"), ("top_copper", "#ffe082")):
        z_band = z_layers[layer_key]
        cy = _clip_y(-half_w_sub, half_w_sub)
        cz = _clip_z(z_band[0], z_band[1])
        if cy and cz:
            ax.add_patch(
                Rectangle(
                    (cy[0], cz[0]),
                    cy[1] - cy[0],
                    cz[1] - cz[0],
                    facecolor=color,
                    edgecolor="#f9a825",
                    linewidth=0.8,
                    alpha=0.7,
                ),
            )

    port_colors = {"Port1": "#6a1b9a", "Port2": "#4527a0"}
    for port in ports:
        ax.add_patch(
            Rectangle(
                (port.y_min_mm, port.z_min_mm),
                port.width_mm,
                port.height_mm,
                facecolor=port_colors.get(port.name, "#7b1fa2"),
                edgecolor="#4a148c",
                alpha=0.25,
                linewidth=1.8,
                label=f"{port.name}",
            ),
        )

    # Via / Slot cross-section at sidewall Y positions
    if geometry.is_slot:
        for slot in geometry.slot_vias:
            y_c_via = slot.y_mm
            via_y0, via_y1 = y_c_via - slot.width_mm / 2.0, y_c_via + slot.width_mm / 2.0
            cy = _clip_y(via_y0, via_y1)
            cz = _clip_z(z0, z1)
            if cy and cz:
                ax.add_patch(
                    Rectangle(
                        (cy[0], cz[0]),
                        cy[1] - cy[0],
                        cz[1] - cz[0],
                        facecolor="#ffcdd2",
                        edgecolor="#c62828",
                        linewidth=1.0,
                        hatch="///",
                        alpha=0.85,
                        label="Slot" if slot is geometry.slot_vias[0] else None,
                    ),
                )
            ax.plot(y_c_via, z_c, marker="+", markersize=9, markeredgewidth=1.8, color="#b71c1c", zorder=5)
    else:
        for y_c_via, tag in ((y_bot, "Via下排"), (y_top, "Via上排")):
            via_y0, via_y1 = y_c_via - via_r, y_c_via + via_r
            cy = _clip_y(via_y0, via_y1)
            cz = _clip_z(z0, z1)
            if cy and cz:
                ax.add_patch(
                    Rectangle(
                        (cy[0], cz[0]),
                        cy[1] - cy[0],
                        cz[1] - cz[0],
                        facecolor="#ffcdd2",
                        edgecolor="#c62828",
                        linewidth=1.0,
                        hatch="///",
                        alpha=0.85,
                        label=tag if y_c_via == y_bot else None,
                    ),
                )
            ax.plot(y_c_via, z_c, marker="+", markersize=9, markeredgewidth=1.8, color="#b71c1c", zorder=5)

    ax.plot([y_bot, y_top], [z_c, z_c], color="#1565c0", linestyle="--", linewidth=0.9, label="SIW 寬 w")

    # Dimension arrows in margin band (away from port center)
    ax.annotate(
        "",
        xy=(pt.y_min_mm, z_lo + half_z * 0.05),
        xytext=(pt.y_max_mm, z_lo + half_z * 0.05),
        arrowprops=dict(arrowstyle="<->", color="#4a148c", lw=1.0),
    )
    ax.annotate(
        "",
        xy=(y_lo + half_y * 0.05, pt.z_min_mm),
        xytext=(y_lo + half_y * 0.05, pt.z_max_mm),
        arrowprops=dict(arrowstyle="<->", color="#4a148c", lw=1.0),
    )

    ax.set_xlim(y_lo, y_hi)
    ax.set_ylim(z_lo, z_hi)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, linestyle=":", alpha=0.3)

    # Labels outside data area (avoid covering geometry)
    fig = figure
    fig.text(
        0.5, 0.02,
        f"W_port={port_w:.2f} mm   H_port={port_h:.3f} mm   "
        f"{'Slot' if geometry.is_slot else 'Via'}中心 Y=±{siw_w/2:.3f} mm",
        ha="center", va="bottom", fontsize=11, color="#222",
    )
    ax.set_xlabel("Y (mm)", fontsize=10)
    ax.set_ylabel("Z (mm)", fontsize=10)
    port_names = " / ".join(pt.name for pt in ports)
    ax.set_title(f"YZ 截面 — {port_names}", fontsize=11)

    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc="upper left", fontsize=9, framealpha=0.9)
    figure.subplots_adjust(bottom=0.16)
    return figure
