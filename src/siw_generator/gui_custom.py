"""Custom via placement tab."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from siw_generator.custom_dxf_import import DxfImportData, dxf_shapes_to_vias, load_dxf_shapes
from siw_generator.custom_geometry import (
    VIA_ROLE_LABELS,
    VIA_ROLE_NAMES,
    VIA_TYPE_LABELS,
    VIA_TYPE_NAMES,
    CustomModuleDefinition,
    CustomVia,
    CustomViaRole,
    CustomViaType,
    make_vias_along_line,
    normalize_rect,
    pick_via_index,
    pick_vias_in_rect,
)
from siw_generator.custom_io import (
    KIND_CUSTOM,
    KIND_RSIW,
    KIND_SSIW,
    PREFIX_BY_KIND,
    load_module_file,
    module_path,
    save_module_file,
)
from siw_generator.custom_preview import CustomPreviewRenderer
from siw_generator.gui_preview import (
    DEFAULT_FIGSIZE_SQUARE,
    attach_zoomable_canvas,
    restore_limits,
    saved_limits,
)
from siw_generator.materials import (
    default_substrate_display_name,
    get_material,
    resolve_material_key,
    substrate_display_names,
)
from siw_generator.stackup import StackupParams

_CUSTOM_MODE_FONT = ("", 10)
_CUSTOM_PLACE_MODES = (
    ("置入", "click_add"),
    ("點選（拖曳）", "canvas_pick"),
    ("線段 Via", "line_via"),
    ("DXF", "dxf_place"),
)
_MIN_SELECT_BOX_MM = 0.12
_DXF_SCALE_STEP = 1.08
_DXF_SCALE_MIN = 0.02
_DXF_SCALE_MAX = 50.0
_DXF_CLICK_TOL_MM = 0.35


class CustomViaPanel(ttk.Frame):
    """Interactive custom via placement with hole list editing (scribeDXF style)."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._updating_fields = False
        self._holes: list[CustomVia] = []
        self._selected_idx: int | None = None
        self._selected_indices: set[int] = set()
        self._select_origin: tuple[float, float] | None = None
        self._selection_rect: tuple[float, float, float, float] | None = None
        self._move_preview_active = False
        self._move_anchor_xy: tuple[float, float] | None = None
        self._move_cursor_xy: tuple[float, float] | None = None
        self._move_base_positions: dict[int, tuple[float, float]] = {}
        self._ghost_xy: tuple[float, float] | None = None
        self._line_start_xy: tuple[float, float] | None = None
        self._line_end_xy: tuple[float, float] | None = None
        self._dxf_import: DxfImportData | None = None
        self._dxf_scale: float = 1.0
        self._dxf_ghost_xy: tuple[float, float] | None = None
        self._dxf_press_xy: tuple[float, float] | None = None
        self._preview_job: str | None = None
        self._ghost_job: str | None = None
        self._preview_renderer: CustomPreviewRenderer | None = None
        self._view_state = {"custom": False}
        self._cell_editor: tk.Widget | None = None
        self._drag_iid: str | None = None
        self._loaded_kind = KIND_CUSTOM
        self._loaded_module: CustomModuleDefinition | None = None
        self._module_panel = None

        self._vars = {
            "module_title": tk.StringVar(value=""),
            "substrate_length": tk.StringVar(value="5.0"),
            "substrate_width": tk.StringVar(value="5.0"),
            "substrate_height": tk.StringVar(value="0.127"),
            "copper_thickness_um": tk.StringVar(value="15"),
            "substrate_material": tk.StringVar(value=default_substrate_display_name()),
            "hole_type": tk.StringVar(value="圓形"),
            "hole_role": tk.StringVar(value="貫孔"),
            "hole_x": tk.StringVar(value=""),
            "hole_y": tk.StringVar(value=""),
            "hole_w": tk.StringVar(value="0.15"),
            "hole_h": tk.StringVar(value="0.15"),
            "via_pitch": tk.StringVar(value="0.28"),
            "place_mode": tk.StringVar(value="click_add"),
        }
        self._status = tk.StringVar(value="單擊預覽圖放置 Via")

        self._build_ui()
        self._setup_traces()
        self._refresh_preview()

    def _setup_traces(self) -> None:
        for name in (
            "substrate_length",
            "substrate_width",
            "substrate_height",
            "copper_thickness_um",
        ):
            self._vars[name].trace_add("write", self._schedule_preview)
        self._vars["substrate_material"].trace_add("write", self._on_material_change)

    def _build_ui(self) -> None:
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(paned, padding=8)
        center = ttk.Frame(paned, padding=8)
        right = ttk.Frame(paned, padding=4)
        paned.add(left, weight=2)
        paned.add(center, weight=1)
        paned.add(right, weight=3)

        row = 0
        ttk.Label(left, text="Custom Via", font=("", 11, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )
        row += 1

        for label, key in (
            ("SIW 長度 L (mm)", "substrate_length"),
            ("基板寬度 W (mm)", "substrate_width"),
            ("基板厚度 h (mm)", "substrate_height"),
            ("銅厚 (µm)", "copper_thickness_um"),
        ):
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(left, textvariable=self._vars[key], width=14).grid(
                row=row, column=1, sticky="ew", pady=2, padx=(6, 0)
            )
            row += 1

        ttk.Label(left, text="基板材料").grid(row=row, column=0, sticky="w", pady=2)
        ttk.Combobox(
            left,
            textvariable=self._vars["substrate_material"],
            values=substrate_display_names(),
            state="readonly",
            width=22,
        ).grid(row=row, column=1, sticky="ew", pady=2, padx=(6, 0))
        row += 1

        self._material_info = tk.StringVar(value="")
        ttk.Label(
            left,
            textvariable=self._material_info,
            wraplength=260,
            foreground="#555",
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(4, 8))
        row += 1
        left.columnconfigure(1, weight=1)

        ttk.Separator(left).grid(row=row, column=0, columnspan=2, sticky="ew", pady=6)
        row += 1
        ttk.Label(left, text="孔位列表", font=("", 10, "bold")).grid(
            row=row, column=0, columnspan=2, sticky="w"
        )
        row += 1

        mode_style = ttk.Style(self)
        mode_style.configure("CustomMode.TLabelframe.Label", font=_CUSTOM_MODE_FONT)
        mode_style.configure("CustomMode.TRadiobutton", font=_CUSTOM_MODE_FONT)

        mode_frame = ttk.LabelFrame(left, text="模式", padding=6, style="CustomMode.TLabelframe")
        mode_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(4, 4))
        row += 1

        mode_row = ttk.Frame(mode_frame)
        mode_row.pack(fill=tk.X)
        for text, value in _CUSTOM_PLACE_MODES:
            ttk.Radiobutton(
                mode_row,
                text=text,
                value=value,
                variable=self._vars["place_mode"],
                command=self._on_place_mode_change,
                style="CustomMode.TRadiobutton",
            ).pack(side=tk.LEFT, padx=(0, 10))

        pitch_row = ttk.Frame(mode_frame)
        pitch_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(pitch_row, text="Via pitch (mm)", font=_CUSTOM_MODE_FONT).pack(side=tk.LEFT)
        ttk.Entry(pitch_row, textvariable=self._vars["via_pitch"], width=8, font=_CUSTOM_MODE_FONT).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        dxf_row = ttk.Frame(mode_frame)
        dxf_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(
            dxf_row,
            text="匯入 DXF…",
            command=self._import_dxf_dialog,
        ).pack(side=tk.LEFT)
        self._dxf_scale_label = ttk.Label(dxf_row, text="", font=_CUSTOM_MODE_FONT, foreground="#444")
        self._dxf_scale_label.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            left,
            text="單擊孔位列表儲存格以編輯 X/Y/外型；拖曳列可調序",
            foreground="#666",
            wraplength=280,
        ).grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 4))
        row += 1
        ttk.Label(left, text="可載入 ctm-/RSIW-/SSIW- 模組", foreground="#666").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        row += 1

        tree_frame = ttk.Frame(left)
        tree_frame.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        row += 1
        self._tree = ttk.Treeview(
            tree_frame,
            columns=("idx", "type", "shape", "x", "y", "w", "h"),
            show="headings",
            height=7,
            selectmode="extended",
        )
        for col, text, width in (
            ("idx", "#", 30),
            ("type", "type", 44),
            ("shape", "外型", 48),
            ("x", "X", 56),
            ("y", "Y", 56),
            ("w", "L/W", 48),
            ("h", "H", 48),
        ):
            self._tree.heading(col, text=text)
            anchor = "center" if col in ("idx", "type", "shape", "w", "h") else "e"
            self._tree.column(col, width=width, anchor=anchor)
        scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<ButtonPress-1>", self._on_tree_press, add="+")
        self._tree.bind("<ButtonRelease-1>", self._on_tree_release, add="+")

        ttk.Label(left, text="新增孔", foreground="#555").grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        add_row = ttk.Frame(left)
        add_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        row += 1
        ttk.Label(add_row, text="type").pack(side=tk.LEFT)
        ttk.Combobox(
            add_row,
            textvariable=self._vars["hole_role"],
            values=list(VIA_ROLE_LABELS),
            state="readonly",
            width=7,
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(add_row, text="外型").pack(side=tk.LEFT)
        ttk.Combobox(
            add_row,
            textvariable=self._vars["hole_type"],
            values=list(VIA_TYPE_LABELS),
            state="readonly",
            width=6,
        ).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(add_row, text="X").pack(side=tk.LEFT)
        ttk.Entry(add_row, textvariable=self._vars["hole_x"], width=7).pack(side=tk.LEFT, padx=(2, 6))
        ttk.Label(add_row, text="Y").pack(side=tk.LEFT)
        ttk.Entry(add_row, textvariable=self._vars["hole_y"], width=7).pack(side=tk.LEFT, padx=(2, 6))
        ttk.Label(add_row, text="L/W").pack(side=tk.LEFT)
        ttk.Entry(add_row, textvariable=self._vars["hole_w"], width=6).pack(side=tk.LEFT, padx=(2, 6))
        ttk.Label(add_row, text="H").pack(side=tk.LEFT)
        ttk.Entry(add_row, textvariable=self._vars["hole_h"], width=6).pack(side=tk.LEFT, padx=(2, 6))
        ttk.Button(add_row, text="加入", command=self._add_hole).pack(side=tk.LEFT, padx=(6, 0))

        btn_row = ttk.Frame(left)
        btn_row.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        row += 1
        ttk.Button(btn_row, text="刪除選取", command=self._delete_hole).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="清除全部", command=self._clear_holes).pack(side=tk.LEFT)
        ttk.Label(left, textvariable=self._status, wraplength=280, foreground="#444").grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

        self._update_material_info()

        ttk.Label(center, text="模組", font=("", 11, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(center, text="標題 (儲存前綴 ctm-)").pack(anchor="w")
        ttk.Entry(center, textvariable=self._vars["module_title"], width=18).pack(
            fill=tk.X, pady=(2, 8)
        )

        from siw_generator.gui_module_panel import ModuleFilePanel

        self._module_panel = ModuleFilePanel(
            center,
            kind=KIND_CUSTOM,
            on_import=self._apply_imported_module,
            on_export=self._export_module_from_panel,
        )
        self._module_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        ttk.Button(center, text="更新預覽", command=self._refresh_preview).pack(fill=tk.X, pady=(4, 4))

        xy_frame, self._figure, self._canvas, self._view_state = attach_zoomable_canvas(
            right,
            title="XY 平面 — 滾輪縮放｜DXF 模式滾輪調倍率",
            figsize=DEFAULT_FIGSIZE_SQUARE,
            on_reset=self._reset_view,
            on_global_reset=self._reset_view,
            on_scroll=self._on_canvas_scroll,
            enable_toolbar_pan=False,
        )
        self._preview_renderer = CustomPreviewRenderer(self._figure)
        xy_frame.pack(fill=tk.BOTH, expand=True)
        self._canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        self._canvas.mpl_connect("button_press_event", self._on_canvas_press)
        self._canvas.mpl_connect("button_release_event", self._on_canvas_release)
        self._bind_delete_key()
        self._canvas.get_tk_widget().bind("<Escape>", self._on_escape_key)
        self._vars["via_pitch"].trace_add("write", self._schedule_ghost_preview)

    def _bind_delete_key(self) -> None:
        for widget in (self, self._canvas.get_tk_widget(), self._tree):
            widget.bind("<Delete>", self._on_delete_key)

    def _deactivate_toolbar_navigation(self) -> None:
        toolbar = getattr(self._canvas, "_nav_toolbar", None)
        if toolbar is None:
            return
        mode = getattr(toolbar, "mode", "")
        if mode == "pan":
            toolbar.pan()
        elif mode == "zoom":
            toolbar.zoom()

    def _event_xy_mm(self, event) -> tuple[float, float] | None:
        if event.xdata is not None and event.ydata is not None and event.inaxes is not None:
            return float(event.xdata), float(event.ydata)
        if not self._figure.axes:
            return None
        ax = self._figure.axes[0]
        try:
            display_x, display_y = event.x, event.y
            data_x, data_y = ax.transData.inverted().transform((display_x, display_y))
        except (AttributeError, ValueError, TypeError):
            return None
        return float(data_x), float(data_y)

    def _dxf_placement_active(self) -> bool:
        return self._dxf_import is not None and self._place_mode_is("dxf_place")

    def _clear_dxf_import(self) -> None:
        self._dxf_import = None
        self._dxf_ghost_xy = None
        self._dxf_press_xy = None
        self._dxf_scale = 1.0
        self._update_dxf_scale_label()

    def _update_dxf_scale_label(self) -> None:
        if self._dxf_import is not None and self._place_mode_is("dxf_place"):
            self._dxf_scale_label.set(f"倍率 {self._dxf_scale:.2f}x")
        else:
            self._dxf_scale_label.set("")

    def _dxf_status_text(self) -> str:
        if self._dxf_import is None:
            return "請匯入 DXF 檔案"
        return (
            f"DXF {self._dxf_import.path.name} — {self._dxf_import.count} 個圖元；"
            f"倍率 {self._dxf_scale:.2f}x；滾輪調整；點擊放置"
        )

    def _dxf_via_role(self) -> CustomViaRole:
        return VIA_ROLE_LABELS.get(self._vars["hole_role"].get(), CustomViaRole.THROUGH)

    def _dxf_preview_vias(self) -> list[CustomVia]:
        if (
            not self._place_mode_is("dxf_place")
            or self._dxf_import is None
            or self._dxf_ghost_xy is None
        ):
            return []
        return dxf_shapes_to_vias(
            self._dxf_import,
            origin_x_mm=self._dxf_ghost_xy[0],
            origin_y_mm=self._dxf_ghost_xy[1],
            scale=self._dxf_scale,
            via_role=self._dxf_via_role(),
        )

    def _import_dxf_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="匯入 DXF",
            filetypes=[("DXF", "*.dxf"), ("所有檔案", "*.*")],
        )
        if not path:
            return
        try:
            data = load_dxf_shapes(path)
        except (ValueError, OSError) as exc:
            messagebox.showerror("匯入 DXF", str(exc))
            return
        self._dxf_import = data
        self._dxf_scale = 1.0
        self._dxf_ghost_xy = None
        self._dxf_press_xy = None
        self._clear_pick_state()
        self._clear_line_placement()
        self._vars["place_mode"].set("dxf_place")
        self._deactivate_toolbar_navigation()
        self._update_dxf_scale_label()
        self._status.set(self._dxf_status_text())
        self._refresh_preview()

    def _on_canvas_scroll(self, event) -> bool:
        if not self._place_mode_is("dxf_place") or self._dxf_import is None:
            return False
        if event.button == "up":
            self._dxf_scale = min(_DXF_SCALE_MAX, self._dxf_scale * _DXF_SCALE_STEP)
        elif event.button == "down":
            self._dxf_scale = max(_DXF_SCALE_MIN, self._dxf_scale / _DXF_SCALE_STEP)
        else:
            return False
        self._update_dxf_scale_label()
        self._status.set(self._dxf_status_text())
        self._schedule_ghost_preview()
        return True

    def _place_dxf_at(self, x_mm: float, y_mm: float) -> None:
        if self._dxf_import is None:
            self._status.set("請先匯入 DXF")
            return
        try:
            new_vias = dxf_shapes_to_vias(
                self._dxf_import,
                origin_x_mm=x_mm,
                origin_y_mm=y_mm,
                scale=self._dxf_scale,
                via_role=self._dxf_via_role(),
            )
        except ValueError as exc:
            self._status.set(str(exc))
            return
        start = len(self._holes)
        self._holes.extend(new_vias)
        self._sync_loaded_module_vias()
        self._set_selection(set(range(start, len(self._holes))))
        self._invalidate_preview()
        self._refresh_tree()
        self._status.set(f"已放置 {len(new_vias)} 個圖元 — {self._dxf_status_text()}")
        self._refresh_preview()

    def _clear_pick_state(self) -> None:
        self._select_origin = None
        self._selection_rect = None
        self._cancel_move_preview()

    def _cancel_move_preview(self) -> None:
        self._move_preview_active = False
        self._move_anchor_xy = None
        self._move_cursor_xy = None
        self._move_base_positions = {}

    def _start_move_preview(self, anchor_x: float, anchor_y: float) -> None:
        if not self._selected_indices:
            return
        self._move_preview_active = True
        self._move_anchor_xy = (anchor_x, anchor_y)
        self._move_cursor_xy = (anchor_x, anchor_y)
        self._move_base_positions = {
            idx: (self._holes[idx].x_mm, self._holes[idx].y_mm)
            for idx in self._selected_indices
            if 0 <= idx < len(self._holes)
        }

    def _move_preview_vias(self) -> list[CustomVia]:
        if (
            not self._move_preview_active
            or self._move_anchor_xy is None
            or self._move_cursor_xy is None
        ):
            return []
        dx = self._move_cursor_xy[0] - self._move_anchor_xy[0]
        dy = self._move_cursor_xy[1] - self._move_anchor_xy[1]
        previews: list[CustomVia] = []
        for idx in sorted(self._selected_indices):
            base = self._move_base_positions.get(idx)
            if base is None or idx >= len(self._holes):
                continue
            hole = self._holes[idx]
            previews.append(
                CustomVia(
                    x_mm=base[0] + dx,
                    y_mm=base[1] + dy,
                    via_type=hole.via_type,
                    via_role=hole.via_role,
                    w_mm=hole.w_mm,
                    h_mm=hole.h_mm,
                    length_mm=hole.length_mm,
                    corner_r_mm=hole.corner_r_mm,
                )
            )
        return previews

    def _commit_move_preview(self) -> None:
        if not self._move_preview_active:
            return
        dx = dy = 0.0
        if self._move_anchor_xy is not None and self._move_cursor_xy is not None:
            dx = self._move_cursor_xy[0] - self._move_anchor_xy[0]
            dy = self._move_cursor_xy[1] - self._move_anchor_xy[1]
        for idx, (bx, by) in self._move_base_positions.items():
            if 0 <= idx < len(self._holes):
                self._holes[idx].x_mm = bx + dx
                self._holes[idx].y_mm = by + dy
        self._cancel_move_preview()
        self._sync_loaded_module_vias()

    def _clear_selection(self) -> None:
        self._cancel_move_preview()
        self._selected_indices = set()
        self._selected_idx = None
        self._tree.selection_remove(self._tree.selection())

    def _set_selection(self, indices: set[int] | list[int]) -> None:
        self._selected_indices = set(indices)
        self._selected_idx = (
            next(iter(self._selected_indices)) if len(self._selected_indices) == 1 else None
        )
        self._updating_fields = True
        self._sync_tree_selection()
        self._update_selection_fields()
        self._updating_fields = False

    def _sync_tree_selection(self) -> None:
        self._tree.selection_remove(self._tree.selection())
        if self._selected_indices:
            self._tree.selection_set(tuple(str(i) for i in sorted(self._selected_indices)))

    def _update_selection_fields(self) -> None:
        if len(self._selected_indices) != 1:
            return
        idx = next(iter(self._selected_indices))
        if idx < 0 or idx >= len(self._holes):
            return
        hole = self._holes[idx]
        if hole.via_type in VIA_TYPE_NAMES and hole.via_type is not CustomViaType.SLOT:
            self._vars["hole_type"].set(VIA_TYPE_NAMES[hole.via_type])
        self._vars["hole_role"].set(VIA_ROLE_NAMES.get(hole.via_role, "貫孔"))
        self._vars["hole_x"].set(f"{hole.x_mm:.4f}")
        self._vars["hole_y"].set(f"{hole.y_mm:.4f}")
        self._vars["hole_w"].set(f"{hole.w_mm:.4f}")
        if hole.via_type is CustomViaType.SLOT:
            length = hole.length_mm if hole.length_mm is not None else hole.h_mm
            self._vars["hole_h"].set(f"{length:.4f}")
        else:
            self._vars["hole_h"].set(f"{hole.h_mm:.4f}")

    def _pick_status_text(self) -> str:
        n = len(self._selected_indices)
        if self._move_preview_active:
            return f"已選 {n} 個 Via — 移動游標預覽；再點擊放置；Delete 刪除"
        if n > 0:
            return f"已選 {n} 個 Via — 移動游標預覽；再點擊放置；Delete 刪除"
        return "框選或點選 Via；移動游標預覽；再點擊放置；Delete 刪除"

    def _on_escape_key(self, _event: tk.Event) -> str | None:
        if self._place_mode_is("dxf_place") and self._dxf_import is not None:
            self._clear_dxf_import()
            self._vars["place_mode"].set("click_add")
            self._status.set("單擊預覽圖放置 Via")
            self._refresh_preview()
            return "break"
        if self._place_mode_is("canvas_pick") and self._move_preview_active:
            self._cancel_move_preview()
            self._status.set(self._pick_status_text())
            self._refresh_preview()
            return "break"
        if self._place_mode_is("line_via") and self._line_start_xy is not None:
            self._cancel_line_placement()
            return "break"
        return None

    def _place_mode_is(self, mode: str) -> bool:
        return self._vars["place_mode"].get() == mode

    def _clear_line_placement(self) -> None:
        self._line_start_xy = None
        self._line_end_xy = None

    def _cancel_line_placement(self) -> None:
        if self._line_start_xy is None:
            return
        self._clear_line_placement()
        self._status.set("已取消線段放置；點選起點，再點終點以沿線段放置 Via")
        self._refresh_preview()

    def _on_place_mode_change(self) -> None:
        mode = self._vars["place_mode"].get()
        self._clear_pick_state()
        if mode != "line_via":
            self._clear_line_placement()
        if mode != "dxf_place":
            self._dxf_ghost_xy = None
            self._update_dxf_scale_label()
        if mode == "click_add":
            self._status.set("單擊預覽圖放置 Via")
        elif mode == "canvas_pick":
            self._status.set(self._pick_status_text())
        elif mode == "dxf_place":
            self._deactivate_toolbar_navigation()
            self._update_dxf_scale_label()
            self._status.set(self._dxf_status_text())
        else:
            self._status.set("點選起點，再點終點以沿線段放置 Via（Esc 取消）")
        self._refresh_preview()

    def _on_delete_key(self, _event: tk.Event) -> str:
        self._delete_hole()
        return "break"

    def _on_material_change(self, *_args: object) -> None:
        if self._updating_fields:
            return
        self._update_material_info()
        self._schedule_preview()

    def _update_material_info(self) -> None:
        try:
            mat = get_material(resolve_material_key(self._vars["substrate_material"].get()))
            self._material_info.set(f"εr={mat.er}  tanδ={mat.tan_delta}")
        except ValueError:
            self._material_info.set("")

    def _stackup(self) -> StackupParams:
        h = self._parse_float("substrate_height", "基板厚度")
        cu_um = self._parse_float("copper_thickness_um", "銅厚")
        return StackupParams(
            substrate_height_mm=h,
            copper_thickness_mm=cu_um / 1000.0,
        )

    def _parse_float(self, key: str, label: str) -> float:
        text = self._vars[key].get().strip()
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} 請輸入有效數字") from exc
        if value <= 0:
            raise ValueError(f"{label} 必須大於 0")
        return value

    def _parse_new_via(self, *, x_mm: float | None = None, y_mm: float | None = None) -> CustomVia:
        vtype = VIA_TYPE_LABELS[self._vars["hole_type"].get()]
        vrole = VIA_ROLE_LABELS[self._vars["hole_role"].get()]
        x = float(self._vars["hole_x"].get()) if x_mm is None else x_mm
        y = float(self._vars["hole_y"].get()) if y_mm is None else y_mm
        w = float(self._vars["hole_w"].get())
        h = float(self._vars["hole_h"].get()) if vtype is CustomViaType.SQUARE else w
        if w <= 0 or h <= 0:
            raise ValueError("L/W、H 必須大於 0")
        return CustomVia(x_mm=x, y_mm=y, via_type=vtype, via_role=vrole, w_mm=w, h_mm=h)

    def _parse_via_template(self) -> CustomVia:
        return self._parse_new_via(x_mm=0.0, y_mm=0.0)

    def _parse_line_pitch(self) -> float:
        text = self._vars["via_pitch"].get().strip()
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError("Via pitch 請輸入有效數字") from exc
        if value <= 0:
            raise ValueError("Via pitch 必須大於 0")
        return value

    def _placement_overlay_kwargs(self) -> dict:
        line_start = self._line_start_xy if self._place_mode_is("line_via") else None
        line_end = self._line_end_xy if line_start is not None else None
        line_template = None
        line_pitch = None
        if line_start is not None and line_end is not None:
            try:
                line_template = self._parse_via_template()
                line_pitch = self._parse_line_pitch()
            except (ValueError, KeyError):
                pass
        ghost = None
        if self._place_mode_is("click_add"):
            ghost = self._ghost_via()
        move_preview = None
        if self._place_mode_is("canvas_pick") and self._move_preview_active:
            move_preview = self._move_preview_vias()
        dxf_preview = self._dxf_preview_vias() if self._place_mode_is("dxf_place") else None
        return {
            "ghost_via": ghost,
            "line_start": line_start,
            "line_end": line_end,
            "line_template": line_template,
            "line_pitch_mm": line_pitch,
            "selection_rect": self._selection_rect if self._place_mode_is("canvas_pick") else None,
            "move_preview_vias": move_preview,
            "dxf_preview_vias": dxf_preview,
        }

    def _apply_placement_overlay(self, renderer: CustomPreviewRenderer) -> None:
        renderer.set_placement_overlay(**self._placement_overlay_kwargs())

    def _build_module(self) -> CustomModuleDefinition:
        base = self._loaded_module
        return CustomModuleDefinition(
            substrate_length_mm=self._parse_float("substrate_length", "SIW 長度"),
            substrate_width_mm=self._parse_float("substrate_width", "基板寬度"),
            stackup=self._stackup(),
            material=resolve_material_key(self._vars["substrate_material"].get()),
            center_freq_ghz=base.center_freq_ghz if base else 120.0,
            siw_width_mm=base.siw_width_mm if base else None,
            via_diameter_mm=base.via_diameter_mm if base else None,
            via_pitch_mm=base.via_pitch_mm if base else None,
            slot_width_mm=base.slot_width_mm if base else None,
            slot_length_mm=base.slot_length_mm if base else None,
            slot_corner_r_mm=base.slot_corner_r_mm if base else None,
            slot_pitch_mm=base.slot_pitch_mm if base else None,
            vias=list(self._holes),
            kind=self._loaded_kind,
        )

    def _hole_display_h(self, via: CustomVia) -> str:
        if via.via_type is CustomViaType.CIRCLE:
            return "—"
        if via.via_type is CustomViaType.SLOT:
            length = via.length_mm if via.length_mm is not None else via.h_mm
            return f"{length:.4f}"
        return f"{via.h_mm:.4f}"

    def _sync_loaded_module_vias(self) -> None:
        if self._loaded_module is not None:
            self._loaded_module.vias = list(self._holes)

    def _refresh_tree(self) -> None:
        self._updating_fields = True
        for item in self._tree.get_children():
            self._tree.delete(item)
        for idx, via in enumerate(self._holes):
            self._tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=(
                    str(idx + 1),
                    VIA_ROLE_NAMES.get(via.via_role, via.via_role.value),
                    VIA_TYPE_NAMES.get(via.via_type, via.via_type.value),
                    f"{via.x_mm:.4f}",
                    f"{via.y_mm:.4f}",
                    f"{via.w_mm:.4f}",
                    self._hole_display_h(via),
                ),
            )
        valid = {str(i) for i in self._selected_indices if i < len(self._holes)}
        if valid:
            self._tree.selection_set(tuple(sorted(valid, key=int)))
        else:
            self._tree.selection_remove(self._tree.selection())
        self._updating_fields = False

    def _ghost_via(self) -> CustomVia | None:
        if self._ghost_xy is None:
            return None
        try:
            return self._parse_new_via(x_mm=self._ghost_xy[0], y_mm=self._ghost_xy[1])
        except ValueError:
            return None

    def _invalidate_preview(self) -> None:
        if self._preview_renderer is not None:
            self._preview_renderer.invalidate()

    def _schedule_preview(self, *_args: object) -> None:
        if self._updating_fields:
            return
        self._invalidate_preview()
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(120, self._run_scheduled_preview)

    def _schedule_ghost_preview(self) -> None:
        if self._ghost_job is not None:
            return
        self._ghost_job = self.after(16, self._run_ghost_preview)

    def _run_ghost_preview(self) -> None:
        self._ghost_job = None
        self._refresh_preview(ghost_only=True)

    def _run_scheduled_preview(self) -> None:
        self._preview_job = None
        self._refresh_preview()

    def _reset_view(self) -> None:
        self._view_state["custom"] = False
        self._invalidate_preview()
        self._refresh_preview()

    def _refresh_preview(self, *, ghost_only: bool = False) -> None:
        try:
            limits = saved_limits(self._figure, self._view_state["custom"])
            renderer = self._preview_renderer
            if renderer is None:
                return
            if ghost_only and renderer.has_static:
                self._apply_placement_overlay(renderer)
            else:
                module = self._build_module()
                hidden = (
                    frozenset(self._selected_indices)
                    if self._move_preview_active
                    else frozenset()
                )
                selected_static = (
                    frozenset()
                    if self._move_preview_active
                    else frozenset(self._selected_indices)
                )
                renderer.draw_static(
                    module,
                    selected_hole_indices=selected_static,
                    hidden_hole_indices=hidden,
                )
                self._apply_placement_overlay(renderer)
                kind_note = ""
                if self._loaded_kind in (KIND_RSIW, KIND_SSIW):
                    kind_note = f" | 來源 {PREFIX_BY_KIND[self._loaded_kind]}"
                if self._place_mode_is("canvas_pick") and (
                    self._move_preview_active
                    or self._select_origin is not None
                    or self._selected_indices
                ):
                    self._status.set(self._pick_status_text())
                elif self._place_mode_is("dxf_place"):
                    self._status.set(self._dxf_status_text())
                else:
                    self._status.set(
                        f"Via {len(self._holes)} 個 | L={module.substrate_length_mm} mm{kind_note}"
                    )
            restore_limits(self._figure, limits)
            self._canvas.draw_idle()
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")

    def _on_canvas_motion(self, event) -> None:
        if self._place_mode_is("line_via") and self._line_start_xy is not None:
            if event.inaxes is None or event.xdata is None or event.ydata is None:
                if self._line_end_xy is not None:
                    self._line_end_xy = None
                    self._schedule_ghost_preview()
                return
            self._line_end_xy = (float(event.xdata), float(event.ydata))
            self._schedule_ghost_preview()
            return

        if self._place_mode_is("canvas_pick"):
            self._on_canvas_pick_motion(event)
            return

        if self._dxf_placement_active():
            xy = self._event_xy_mm(event)
            if xy is None:
                if self._dxf_ghost_xy is not None:
                    self._dxf_ghost_xy = None
                    self._schedule_ghost_preview()
                return
            self._dxf_ghost_xy = xy
            self._schedule_ghost_preview()
            return

        if not self._place_mode_is("click_add"):
            if self._ghost_xy is not None:
                self._ghost_xy = None
                self._schedule_ghost_preview()
            return
        if event.inaxes is None:
            if self._ghost_xy is not None:
                self._ghost_xy = None
                self._schedule_ghost_preview()
            return
        if event.xdata is None or event.ydata is None:
            return
        self._ghost_xy = (float(event.xdata), float(event.ydata))
        self._schedule_ghost_preview()

    def _on_canvas_pick_motion(self, event) -> None:
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return
        x_mm = float(event.xdata)
        y_mm = float(event.ydata)
        if self._select_origin is not None:
            x0, y0 = self._select_origin
            self._selection_rect = normalize_rect(x0, y0, x_mm, y_mm)
            self._schedule_ghost_preview()
            return
        if self._move_preview_active:
            self._move_cursor_xy = (x_mm, y_mm)
            self._schedule_ghost_preview()

    def _on_canvas_press(self, event) -> None:
        if event.button != 1:
            return
        self._canvas.get_tk_widget().focus_set()
        xy = self._event_xy_mm(event)
        if xy is None:
            return
        x_mm, y_mm = xy

        if self._dxf_placement_active():
            self._dxf_press_xy = (x_mm, y_mm)
            self._dxf_ghost_xy = (x_mm, y_mm)
            self._schedule_ghost_preview()
            return

        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return

        if self._place_mode_is("line_via"):
            self._handle_line_via_click(x_mm, y_mm)
            return

        if self._place_mode_is("canvas_pick"):
            if self._move_preview_active:
                self._commit_move_preview()
                self._refresh_tree()
                self._update_selection_fields()

            picked = pick_via_index(x_mm, y_mm, self._holes)
            if picked is not None:
                self._set_selection({picked})
                self._start_move_preview(x_mm, y_mm)
            else:
                self._select_origin = (x_mm, y_mm)
                self._selection_rect = None
            self._status.set(self._pick_status_text())
            self._refresh_preview()
            return

        picked = pick_via_index(x_mm, y_mm, self._holes)
        if picked is not None:
            self._set_selection({picked})
            return
        if not self._place_mode_is("click_add"):
            return
        try:
            hole = self._parse_new_via(x_mm=x_mm, y_mm=y_mm)
        except (ValueError, KeyError) as exc:
            self._status.set(str(exc))
            return
        self._holes.append(hole)
        self._sync_loaded_module_vias()
        self._set_selection({len(self._holes) - 1})
        self._updating_fields = True
        self._vars["hole_x"].set(f"{hole.x_mm:.4f}")
        self._vars["hole_y"].set(f"{hole.y_mm:.4f}")
        self._updating_fields = False
        self._refresh_tree()
        self._refresh_preview()

    def _on_canvas_release(self, event) -> None:
        if event.button == 1 and self._dxf_placement_active():
            xy = self._event_xy_mm(event)
            press = self._dxf_press_xy
            self._dxf_press_xy = None
            if press is None:
                return
            if xy is not None:
                dx = xy[0] - press[0]
                dy = xy[1] - press[1]
                if (dx * dx + dy * dy) ** 0.5 <= _DXF_CLICK_TOL_MM:
                    self._place_dxf_at(xy[0], xy[1])
            else:
                self._place_dxf_at(press[0], press[1])
            return

        if not self._place_mode_is("canvas_pick") or event.button != 1:
            return
        if self._select_origin is None:
            return
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            self._select_origin = None
            self._selection_rect = None
            self._refresh_preview()
            return
        x0, y0 = self._select_origin
        x1 = float(event.xdata)
        y1 = float(event.ydata)
        rect = normalize_rect(x0, y0, x1, y1)
        width = rect[2] - rect[0]
        height = rect[3] - rect[1]
        self._select_origin = None
        self._selection_rect = None
        if width >= _MIN_SELECT_BOX_MM or height >= _MIN_SELECT_BOX_MM:
            picked = pick_vias_in_rect(x0, y0, x1, y1, self._holes)
            if picked:
                self._set_selection(picked)
                self._start_move_preview(x1, y1)
            else:
                self._clear_selection()
        else:
            self._clear_selection()
        self._status.set(self._pick_status_text())
        self._refresh_preview()

    def _handle_line_via_click(self, x_mm: float, y_mm: float) -> None:
        if self._line_start_xy is None:
            self._line_start_xy = (x_mm, y_mm)
            self._line_end_xy = (x_mm, y_mm)
            self._status.set("已設定起點，點選終點（Esc 取消）")
            self._refresh_preview()
            return
        try:
            template = self._parse_via_template()
            pitch = self._parse_line_pitch()
            new_vias = make_vias_along_line(
                self._line_start_xy[0],
                self._line_start_xy[1],
                x_mm,
                y_mm,
                template,
                pitch,
            )
        except (ValueError, KeyError) as exc:
            self._status.set(str(exc))
            return
        self._holes.extend(new_vias)
        self._sync_loaded_module_vias()
        self._clear_line_placement()
        self._set_selection({len(self._holes) - 1})
        self._refresh_tree()
        self._status.set(f"已沿線段新增 {len(new_vias)} 個 Via")
        self._refresh_preview()

    def _add_hole(self) -> None:
        try:
            hole = self._parse_new_via()
            self._holes.append(hole)
            self._sync_loaded_module_vias()
            self._set_selection({len(self._holes) - 1})
            self._refresh_tree()
            self._refresh_preview()
        except (ValueError, KeyError) as exc:
            self._status.set(str(exc))

    def _delete_hole(self) -> None:
        if self._move_preview_active:
            self._cancel_move_preview()
        if not self._selected_indices and self._selected_idx is not None:
            self._selected_indices = {self._selected_idx}
        if not self._selected_indices:
            sel = self._tree.selection()
            if sel:
                self._selected_indices = {int(s) for s in sel}
        if not self._selected_indices:
            return
        for idx in sorted(self._selected_indices, reverse=True):
            if 0 <= idx < len(self._holes):
                del self._holes[idx]
        self._sync_loaded_module_vias()
        self._clear_selection()
        self._clear_pick_state()
        self._refresh_tree()
        self._refresh_preview()

    def _clear_hole_selection(self) -> None:
        self._clear_selection()
        self._refresh_preview()

    def _select_hole_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._holes):
            return
        self._set_selection({idx})
        self._refresh_preview()

    def _clear_holes(self) -> None:
        self._holes.clear()
        self._sync_loaded_module_vias()
        self._clear_selection()
        self._ghost_xy = None
        self._clear_pick_state()
        self._cancel_editor()
        self._refresh_tree()
        self._refresh_preview()

    def _on_select(self, _event: object = None) -> None:
        if self._updating_fields:
            return
        sel = self._tree.selection()
        if not sel:
            self._selected_indices = set()
            self._selected_idx = None
            self._refresh_preview()
            return
        indices = {int(s) for s in sel if int(s) < len(self._holes)}
        self._selected_indices = indices
        self._selected_idx = next(iter(indices)) if len(indices) == 1 else None
        if len(indices) == 1:
            self._update_selection_fields()
        self._refresh_preview()

    def _cancel_editor(self) -> None:
        if self._cell_editor is not None:
            self._cell_editor.destroy()
            self._cell_editor = None

    def _replace_hole(self, idx: int, via: CustomVia) -> None:
        self._holes[idx] = via
        self._sync_loaded_module_vias()
        self._set_selection({idx})
        self._refresh_tree()
        self._refresh_preview()

    def _edit_tree_cell(self, event: tk.Event) -> None:
        self._drag_iid = None
        self._cancel_editor()
        if self._tree.identify_region(event.x, event.y) != "cell":
            return
        col_id = self._tree.identify_column(event.x)
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        idx = int(iid)
        hole = self._holes[idx]

        if col_id == "#2":
            bbox = self._tree.bbox(iid, "type")
            if not bbox:
                return
            bx, by, bw, bh = bbox
            combo = ttk.Combobox(
                self._tree,
                values=list(VIA_ROLE_LABELS),
                state="readonly",
                width=max(4, bw // 8),
            )
            combo.set(self._tree.set(iid, "type"))
            combo.place(x=bx, y=by, width=bw, height=bh)
            combo.focus()
            self._cell_editor = combo

            def commit_role(_e: object = None) -> None:
                if self._cell_editor is None:
                    return
                label = combo.get().strip()
                self._cancel_editor()
                role = VIA_ROLE_LABELS.get(label)
                if role is None:
                    return
                h = self._holes[idx]
                self._replace_hole(
                    idx,
                    CustomVia(
                        h.x_mm,
                        h.y_mm,
                        h.via_type,
                        role,
                        h.w_mm,
                        h.h_mm,
                        h.length_mm,
                        h.corner_r_mm,
                    ),
                )

            combo.bind("<<ComboboxSelected>>", commit_role)
            combo.bind("<FocusOut>", commit_role)
            return

        if col_id == "#3":
            if hole.via_type is CustomViaType.SLOT:
                return
            bbox = self._tree.bbox(iid, "shape")
            if not bbox:
                return
            bx, by, bw, bh = bbox
            combo = ttk.Combobox(
                self._tree,
                values=list(VIA_TYPE_LABELS),
                state="readonly",
                width=max(4, bw // 8),
            )
            combo.set(self._tree.set(iid, "shape"))
            combo.place(x=bx, y=by, width=bw, height=bh)
            combo.focus()
            self._cell_editor = combo

            def commit_shape(_e: object = None) -> None:
                if self._cell_editor is None:
                    return
                label = combo.get().strip()
                self._cancel_editor()
                vtype = VIA_TYPE_LABELS.get(label)
                if vtype is None:
                    return
                h = self._holes[idx]
                nh = h.w_mm if vtype is CustomViaType.CIRCLE else h.h_mm
                self._replace_hole(
                    idx,
                    CustomVia(
                        h.x_mm,
                        h.y_mm,
                        vtype,
                        h.via_role,
                        h.w_mm,
                        nh,
                        h.length_mm,
                        h.corner_r_mm,
                    ),
                )

            combo.bind("<<ComboboxSelected>>", commit_shape)
            combo.bind("<FocusOut>", commit_shape)
            return

        col_map = {"#4": "x", "#5": "y", "#6": "w", "#7": "h"}
        col_name = col_map.get(col_id)
        if not col_name:
            return
        if col_name == "h" and hole.via_type is CustomViaType.CIRCLE:
            return
        bbox = self._tree.bbox(iid, col_name)
        if not bbox:
            return
        bx, by, bw, bh = bbox
        entry = ttk.Entry(self._tree)
        entry.insert(0, self._tree.set(iid, col_name).replace("—", ""))
        entry.place(x=bx, y=by, width=bw, height=bh)
        entry.focus()
        self._cell_editor = entry

        def commit(_e: object = None) -> None:
            if not self._cell_editor:
                return
            text = entry.get().strip()
            self._cancel_editor()
            try:
                value = float(text)
            except ValueError:
                self._status.set("請輸入有效數字")
                return
            if value <= 0:
                self._status.set("數值必須大於 0")
                return
            h = self._holes[idx]
            if col_name == "x":
                via = CustomVia(
                    value, h.y_mm, h.via_type, h.via_role, h.w_mm, h.h_mm, h.length_mm, h.corner_r_mm
                )
            elif col_name == "y":
                via = CustomVia(
                    h.x_mm, value, h.via_type, h.via_role, h.w_mm, h.h_mm, h.length_mm, h.corner_r_mm
                )
            elif col_name == "w":
                if h.via_type is CustomViaType.CIRCLE:
                    via = CustomVia(
                        h.x_mm, h.y_mm, h.via_type, h.via_role, value, value, h.length_mm, h.corner_r_mm
                    )
                elif h.via_type is CustomViaType.SLOT:
                    via = CustomVia(
                        h.x_mm, h.y_mm, h.via_type, h.via_role, value, h.h_mm, h.length_mm, h.corner_r_mm
                    )
                else:
                    via = CustomVia(
                        h.x_mm, h.y_mm, h.via_type, h.via_role, value, h.h_mm, h.length_mm, h.corner_r_mm
                    )
            elif h.via_type is CustomViaType.SLOT:
                via = CustomVia(
                    h.x_mm, h.y_mm, h.via_type, h.via_role, h.w_mm, value, value, h.corner_r_mm
                )
            else:
                via = CustomVia(
                    h.x_mm, h.y_mm, h.via_type, h.via_role, h.w_mm, value, h.length_mm, h.corner_r_mm
                )
            self._replace_hole(idx, via)

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", lambda _e: self._cancel_editor())
        entry.bind("<FocusOut>", commit)

    def _on_tree_press(self, event: tk.Event) -> None:
        if self._tree.identify_region(event.x, event.y) == "cell":
            iid = self._tree.identify_row(event.y)
            if iid:
                self._drag_iid = iid

    def _on_tree_release(self, event: tk.Event) -> None:
        from_iid = self._drag_iid
        self._drag_iid = None
        target = self._tree.identify_row(event.y)
        if from_iid and target and target != from_iid:
            a, b = int(from_iid), int(target)
            item = self._holes.pop(a)
            self._holes.insert(b, item)
            self._sync_loaded_module_vias()
            self._set_selection({b})
            self._refresh_tree()
            self._refresh_preview()
            return
        if from_iid and self._tree.identify_region(event.x, event.y) == "cell":
            self._edit_tree_cell(event)

    def _save_module(self) -> None:
        try:
            module = self._build_module()
            module.kind = KIND_CUSTOM
            self._loaded_kind = KIND_CUSTOM
            self._loaded_module = None
            title = self._vars["module_title"].get().strip()
            if not title:
                messagebox.showwarning("儲存模組", "請輸入模組標題")
                return
            path = module_path(KIND_CUSTOM, title)
            if path.exists() and not messagebox.askyesno(
                "覆蓋確認",
                f"{path.name} 已存在，是否覆蓋？",
            ):
                return
            save_module_file(module, path, title=path.stem)
            from siw_generator.operation_log import log_operation

            log_operation("module", "儲存模組", path.name)
            messagebox.showinfo("儲存完成", f"已儲存至：\n{path}")
            self._status.set(f"已儲存 {path.name}")
            if self._module_panel is not None:
                self._module_panel.refresh_list()
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc))
        except OSError as exc:
            messagebox.showerror("儲存失敗", str(exc))

    def _export_module_from_panel(self) -> None:
        self._save_module()

    def _apply_imported_module(self, module: CustomModuleDefinition, path: Path) -> None:
        self._loaded_module = module
        self._invalidate_preview()
        self._updating_fields = True
        try:
            self._holes = list(module.vias)
            self._loaded_kind = module.kind
            self._clear_selection()
            self._clear_pick_state()
            self._vars["substrate_length"].set(f"{module.substrate_length_mm:.4f}")
            self._vars["substrate_width"].set(f"{module.substrate_width_mm:.4f}")
            self._vars["substrate_height"].set(f"{module.stackup.substrate_height_mm:.4f}")
            self._vars["copper_thickness_um"].set(f"{module.stackup.copper_thickness_um:.0f}")
            mat = get_material(module.material)
            self._vars["substrate_material"].set(mat.cst_material_name)
            stem = path.stem
            title = stem
            for prefix in (PREFIX_BY_KIND[KIND_CUSTOM], PREFIX_BY_KIND[KIND_RSIW], PREFIX_BY_KIND[KIND_SSIW]):
                if stem.lower().startswith(prefix.lower()):
                    title = stem[len(prefix) :]
                    break
            self._vars["module_title"].set(title)
            from siw_generator.operation_log import log_operation

            log_operation("module", "匯入模組", path.name)
        finally:
            self._updating_fields = False

        self._update_material_info()
        self._refresh_tree()
        self._refresh_preview()
        kind_label = PREFIX_BY_KIND.get(module.kind, module.kind)
        self._status.set(f"已載入 {path.name}（{len(self._holes)} 個孔，{kind_label}）")
