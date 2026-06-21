"""Shared matplotlib preview zoom helpers for GUI panels."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

# Default figure sizes chosen so toolbar remains visible at typical window sizes.
DEFAULT_FIGSIZE_SQUARE = (4.2, 4.2)
DEFAULT_FIGSIZE_WIDE = (4.6, 3.0)
DEFAULT_FIGSIZE_TALL = (4.8, 6.2)
DEFAULT_FIGSIZE_STRIP = (4.8, 2.2)
DEFAULT_FIGSIZE_THUMB = (2.8, 2.8)


def attach_zoomable_canvas(
    parent: tk.Misc,
    *,
    title: str,
    figsize: tuple[float, float],
    on_reset: Callable[[], None],
    on_global_reset: Callable[[], None] | None = None,
    on_undo: Callable[[], None] | None = None,
    on_redo: Callable[[], None] | None = None,
    undo_label: str = "復原",
    redo_label: str = "下一步",
    enable_toolbar_pan: bool = True,
) -> tuple[ttk.LabelFrame, Figure, FigureCanvasTkAgg, dict[str, bool]]:
    """Create a label-framed preview with toolbar, scroll zoom, and reset."""
    frame = ttk.LabelFrame(parent, text=title, padding=2)
    figure = Figure(figsize=figsize, dpi=100)

    ctrl = ttk.Frame(frame)
    ctrl.pack(side=tk.BOTTOM, fill=tk.X)
    btn_row = ttk.Frame(ctrl)
    btn_row.pack(side=tk.RIGHT, fill=tk.Y)
    action_row = ttk.Frame(btn_row)
    action_row.pack(side=tk.TOP, fill=tk.X)
    ttk.Button(action_row, text="重設視野", command=on_reset).pack(side=tk.LEFT, padx=(4, 2), pady=2)
    if on_undo is not None:
        ttk.Button(action_row, text=undo_label, command=on_undo).pack(side=tk.LEFT, padx=2, pady=2)
    if on_redo is not None:
        ttk.Button(action_row, text=redo_label, command=on_redo).pack(side=tk.LEFT, padx=(2, 4), pady=2)
    if on_global_reset is not None:
        ttk.Button(btn_row, text="重設全局 FOV", command=on_global_reset).pack(side=tk.TOP, padx=4, pady=2)

    canvas = FigureCanvasTkAgg(figure, master=frame)
    try:
        toolbar = NavigationToolbar2Tk(canvas, ctrl, pack_toolbar=False)
    except TypeError:
        toolbar = NavigationToolbar2Tk(canvas, ctrl)
    toolbar.pack(side=tk.LEFT, fill=tk.X, expand=True)
    toolbar.update()
    if not enable_toolbar_pan:
        for attr in ("_id_press", "_id_release", "_id_drag"):
            cid = getattr(toolbar, attr, None)
            if cid is not None:
                canvas.mpl_disconnect(cid)
                setattr(toolbar, attr, None)
    canvas.get_tk_widget().configure(takefocus=True)
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    state = {"custom": False}

    def _on_scroll(event) -> None:
        ax = figure.axes[0] if figure.axes else None
        if ax is None or event.inaxes != ax or event.xdata is None or event.ydata is None:
            return
        scale = 0.85 if event.button == "up" else 1.15
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        x, y = event.xdata, event.ydata
        new_w = (xlim[1] - xlim[0]) * scale
        new_h = (ylim[1] - ylim[0]) * scale
        relx = (xlim[1] - x) / (xlim[1] - xlim[0])
        rely = (ylim[1] - y) / (ylim[1] - ylim[0])
        ax.set_xlim(x - new_w * (1 - relx), x + new_w * relx)
        ax.set_ylim(y - new_h * (1 - rely), y + new_h * rely)
        state["custom"] = True
        canvas.draw_idle()

    def _on_view_changed(_event) -> None:
        if figure.axes:
            state["custom"] = True

    canvas.mpl_connect("scroll_event", _on_scroll)
    canvas.mpl_connect("button_release_event", _on_view_changed)
    return frame, figure, canvas, state


def saved_limits(figure: Figure, custom: bool) -> tuple[tuple[float, float], tuple[float, float]] | None:
    if not custom or not figure.axes:
        return None
    ax = figure.axes[0]
    return ax.get_xlim(), ax.get_ylim()


def restore_limits(figure: Figure, limits: tuple[tuple[float, float], tuple[float, float]] | None) -> None:
    if limits and figure.axes:
        ax = figure.axes[0]
        ax.set_xlim(limits[0])
        ax.set_ylim(limits[1])
