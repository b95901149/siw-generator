"""Module grid composition tab."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from siw_generator.compose_geometry import (
    ComposeLayout,
    PendingPlacement,
    add_port,
    apply_substrate_fill_in_rect,
    apply_substrate_frame_from_rect,
    apply_cell_fit_scales,
    cell_at_point,
    clone_layout,
    closest_cell,
    compute_leakage_substrate_frame,
    default_pitch_for_module,
    find_port_candidate,
    representative_gap,
    mirror_placed,
    move_placed_module,
    normalize_rect,
    occupied_cells_bounds,
    place_module,
    remove_placed_module,
    remove_port,
    recompute_all_port_positions,
    resolve_operation_rect,
    rotate_clockwise,
    rotate_placed,
    sync_pitch_from_placements,
    sync_layout_geometry,
)
from siw_generator.compose_io import (
    layout_from_dict,
    layout_to_dict,
)
from siw_generator.compose_preview import port_summary, render_compose_main, render_module_thumbnail
from siw_generator.combination_io import (
    apply_combination_data,
    combination_path,
    load_combination_file,
    save_combination_file,
)
from siw_generator.custom_geometry import CustomModuleDefinition
from siw_generator.custom_io import (
    KIND_CUSTOM,
    load_module_file,
    list_module_files,
)
from siw_generator.gui_preview import (
    DEFAULT_FIGSIZE_SQUARE,
    attach_zoomable_canvas,
    restore_limits,
    saved_limits,
)
from siw_generator.gui_module_panel import make_transparent_red_button
from siw_generator.materials import (
    default_substrate_display_name,
    get_material,
    resolve_material_key,
    substrate_display_names,
)
from siw_generator.operation_log import log_operation
from siw_generator.stackup import StackupParams

_COMPOSE_MODULE_ROW_PX = 300
_PORT_SECTION_MIN_PX = 140
_COMPOSE_THUMB_FIGSIZE = (2.6, 5.1)
_PORT_TREE_HEIGHT = 6
_PORT_COL_MINWIDTHS = {
    "idx": 14,
    "cell": 26,
    "edge": 18,
    "width": 29,
    "pos": 29,
}

class ComposePanel(ttk.Frame):
    """Tile modules from module/ onto an M×N grid."""

    _UNDO_LIMIT = 50

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._updating = False
        self._preview_job: str | None = None
        self._main_motion_job: str | None = None
        self._main_view = {"custom": False}
        self._thumb_view = {"custom": False}
        self._layout = ComposeLayout()
        self._undo_stack: list[ComposeLayout] = []
        self._redo_stack: list[ComposeLayout] = []
        self._operation_steps: list[dict] = []
        self._redo_steps: list[dict] = []
        self._combination_title = tk.StringVar(value="")
        self._clear_cst = tk.BooleanVar(value=True)
        self._module_paths: list[Path] = []
        self._selected_module: CustomModuleDefinition | None = None
        self._selected_path: Path | None = None
        self._ghost_cell: tuple[int, int] | None = None
        self._port_candidate = None
        self._mode = tk.StringVar(value="place")
        self._place_rotation = 0
        self._place_mirror = False
        self._selected_cell: tuple[int, int] | None = None
        self._drag_source: tuple[int, int] | None = None
        self._drag_target: tuple[int, int] | None = None
        self._pending: PendingPlacement | None = None
        self._pending_move_source: tuple[int, int] | None = None
        self._conflict_hover_cell: tuple[int, int] | None = None
        self._select_origin: tuple[float, float] | None = None
        self._selection_rect: tuple[float, float, float, float] | None = None
        self._imported_kind = KIND_CUSTOM

        self._vars = {
            "m_count": tk.StringVar(value="3"),
            "n_count": tk.StringVar(value="3"),
            "default_pitch_x": tk.StringVar(value="10.0"),
            "default_pitch_y": tk.StringVar(value="10.0"),
            "fill_height": tk.StringVar(value="0.127"),
            "fill_copper_um": tk.StringVar(value="15"),
            "fill_material": tk.StringVar(value=default_substrate_display_name()),
            "leakage_margin_factor": tk.StringVar(value="0.5"),
            "import_length": tk.StringVar(value="10.0"),
            "import_width": tk.StringVar(value="10.0"),
            "import_height": tk.StringVar(value="0.127"),
            "import_copper_um": tk.StringVar(value="15"),
        }
        self._status = tk.StringVar(value=self._mode_hint("place"))

        self._build_ui()
        self._setup_traces()
        self._update_fill_material_info()
        self.refresh_module_list()
        self._refresh_all()

    def _mode_hint(self, mode: str) -> str:
        hints = {
            "place": (
                "單擊滑鼠左鍵以放置 module；尺寸衝突時左鍵點已放置 cell 對齊 pitch、"
                "左鍵點目標 cell 或右鍵以新 module 為準；Ctrl+R/M 旋轉鏡像；Ctrl+Z 復原"
            ),
            "select": "單擊滑鼠左鍵以選取 module，拖曳後放開以移動；Ctrl+R/M 變換；Ctrl+Z 復原",
            "delete": "單擊滑鼠左鍵以刪除 cell 上的 module；Ctrl+Z 復原",
            "substrate": (
                "拖曳圈選填補；未圈選時以已放置 cell 邊界填補；"
                "「切割基板」設定紅框外框；Ctrl+Z 復原"
            ),
            "port": (
                "移近 cell 邊緣（需兩顆平行 via），單擊滑鼠左鍵以新增 Port；"
                "單擊「刪除選取 Port」移除；Ctrl+Z 復原"
            ),
        }
        return hints.get(mode, "")

    def _setup_traces(self) -> None:
        for key in ("m_count", "n_count", "default_pitch_x", "default_pitch_y", "fill_height", "fill_copper_um", "fill_material"):
            self._vars[key].trace_add("write", self._schedule_refresh)
        for key in ("import_length", "import_width", "import_height", "import_copper_um"):
            self._vars[key].trace_add("write", self._on_import_param_change)
        self._mode.trace_add("write", self._on_mode_change)

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.configure("Compose.TPanedwindow", sashwidth=8)
        style.configure("ComposeModule.TPanedwindow", sashwidth=6)

        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL, style="Compose.TPanedwindow")
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self._main_paned = paned

        preview_col = ttk.Frame(paned, padding=4)
        control_col = ttk.Frame(paned, padding=8)
        paned.add(preview_col, weight=13)
        paned.add(control_col, weight=7)

        main_wrap = ttk.Frame(preview_col)
        main_wrap.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(control_col)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(toolbar, text="M").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self._vars["m_count"], width=4).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(toolbar, text="N").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self._vars["n_count"], width=4).pack(side=tk.LEFT, padx=(4, 12))
        ttk.Label(toolbar, text="空白 pitch X").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self._vars["default_pitch_x"], width=7).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(toolbar, text="Y").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self._vars["default_pitch_y"], width=7).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Button(toolbar, text="pitch←module", command=self._apply_default_pitch_from_module).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="清空", command=self._clear_all).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(toolbar, text="重新整理", command=self.refresh_module_list).pack(side=tk.LEFT, padx=(0, 4))
        make_transparent_red_button(toolbar, text="刪除", command=self._delete_selected_module_file).pack(
            side=tk.LEFT
        )

        _MODULE_ROW_PX = _COMPOSE_MODULE_ROW_PX
        module_row_outer = tk.Frame(control_col, height=_MODULE_ROW_PX)
        module_row_outer.pack(fill=tk.X, pady=(0, 6))
        module_row_outer.pack_propagate(False)

        module_row = ttk.Panedwindow(
            module_row_outer,
            orient=tk.HORIZONTAL,
            style="ComposeModule.TPanedwindow",
        )
        module_row.pack(fill=tk.BOTH, expand=True)
        self._module_paned = module_row

        list_side = ttk.Frame(module_row, padding=(0, 0, 4, 0))
        thumb_side = ttk.LabelFrame(module_row, text="選取 module（黃色）", padding=2)
        module_row.add(list_side, weight=2)
        module_row.add(thumb_side, weight=3)
        list_side.rowconfigure(1, weight=1)
        list_side.columnconfigure(0, weight=1)

        ttk.Label(list_side, text="module/", font=("", 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 2))
        list_frame = ttk.Frame(list_side)
        list_frame.grid(row=1, column=0, sticky="nsew")
        self._listbox = tk.Listbox(list_frame, exportselection=False)
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=scroll.set)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox.bind("<<ListboxSelect>>", self._on_module_select)

        param_row = ttk.LabelFrame(list_side, text="匯入模組參數（重新參數化）", padding=4)
        param_row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        for row_i, (label, key) in enumerate(
            (("L", "import_length"), ("W", "import_width"), ("h", "import_height"), ("Cu µm", "import_copper_um"))
        ):
            cell = ttk.Frame(param_row)
            cell.grid(row=row_i // 2, column=row_i % 2, sticky="w", padx=(0, 8), pady=2)
            ttk.Label(cell, text=label).pack(side=tk.LEFT)
            ttk.Entry(cell, textvariable=self._vars[key], width=8).pack(side=tk.LEFT, padx=(4, 0))

        thumb_frame, self._figure_thumb, self._canvas_thumb, self._thumb_view = attach_zoomable_canvas(
            thumb_side,
            title="",
            figsize=_COMPOSE_THUMB_FIGSIZE,
            on_reset=self._reset_thumb_view,
            on_global_reset=self._reset_all_views,
        )
        thumb_frame.pack(fill=tk.BOTH, expand=True)

        mode_fill_row = ttk.Frame(control_col)
        mode_fill_row.pack(fill=tk.X, pady=(0, 6))
        mode_fill_row.columnconfigure(0, weight=1, uniform="modefill")
        mode_fill_row.columnconfigure(1, weight=1, uniform="modefill")
        mode_fill_row.rowconfigure(0, weight=1)

        mode_row = ttk.LabelFrame(mode_fill_row, text="模式", padding=6)
        mode_row.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        for text, value in (
            ("置入", "place"),
            ("點選（拖曳）", "select"),
            ("刪除", "delete"),
            ("基板外框", "substrate"),
            ("Port", "port"),
        ):
            ttk.Radiobutton(mode_row, text=text, value=value, variable=self._mode).pack(anchor="w")

        fill_row = ttk.LabelFrame(mode_fill_row, text="填補基板 stackup", padding=6)
        fill_row.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
        mat_line = ttk.Frame(fill_row)
        mat_line.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(mat_line, text="基板材料").pack(side=tk.LEFT)
        fill_material_combo = ttk.Combobox(
            mat_line,
            textvariable=self._vars["fill_material"],
            values=substrate_display_names(),
            state="readonly",
            width=24,
        )
        fill_material_combo.pack(side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True)
        fill_material_combo.bind("<<ComboboxSelected>>", self._on_fill_material_change)
        self._fill_material_info = tk.StringVar(value="")
        ttk.Label(
            fill_row,
            textvariable=self._fill_material_info,
            foreground="#555",
            wraplength=220,
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 4))
        stack_line = ttk.Frame(fill_row)
        stack_line.pack(fill=tk.X)
        ttk.Label(stack_line, text="h (mm)").pack(side=tk.LEFT)
        ttk.Entry(stack_line, textvariable=self._vars["fill_height"], width=7).pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(stack_line, text="Cu (µm)").pack(side=tk.LEFT)
        ttk.Entry(stack_line, textvariable=self._vars["fill_copper_um"], width=6).pack(side=tk.LEFT, padx=(4, 0))
        leak_line = ttk.Frame(fill_row)
        leak_line.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(leak_line, text="防洩漏").pack(side=tk.LEFT)
        ttk.Entry(leak_line, textvariable=self._vars["leakage_margin_factor"], width=5).pack(side=tk.LEFT, padx=(4, 0))
        btn_line = ttk.Frame(fill_row)
        btn_line.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_line, text="切割基板", command=self._cut_substrate_frame).pack(fill=tk.X, pady=(0, 3))
        ttk.Button(btn_line, text="基板 X 防洩漏", command=self._align_substrate_x_leakage).pack(fill=tk.X, pady=(0, 3))
        ttk.Button(btn_line, text="基板 Y 防洩漏", command=self._align_substrate_y_leakage).pack(fill=tk.X)

        bottom_row = ttk.Frame(control_col)
        bottom_row.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
        bottom_row.columnconfigure(0, weight=1, uniform="bottomhalf")
        bottom_row.columnconfigure(1, weight=1, uniform="bottomhalf")
        bottom_row.rowconfigure(0, weight=1, minsize=_PORT_SECTION_MIN_PX)

        port_wrap = ttk.LabelFrame(bottom_row, text="Port 列表", padding=4)
        port_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        port_wrap.rowconfigure(0, weight=1)
        port_wrap.columnconfigure(0, weight=1)
        port_tree_frame = ttk.Frame(port_wrap)
        port_tree_frame.grid(row=0, column=0, sticky="nsew")
        port_tree_frame.rowconfigure(0, weight=1)
        port_tree_frame.columnconfigure(0, weight=1)
        self._port_tree = ttk.Treeview(
            port_tree_frame,
            columns=("idx", "cell", "edge", "width", "pos"),
            show="headings",
            height=_PORT_TREE_HEIGHT,
            selectmode="browse",
        )
        for col, text in (
            ("idx", "#"),
            ("cell", "cell"),
            ("edge", "邊"),
            ("width", "W"),
            ("pos", "中心"),
        ):
            minwidth = _PORT_COL_MINWIDTHS[col]
            self._port_tree.heading(col, text=text)
            self._port_tree.column(
                col,
                width=minwidth,
                minwidth=minwidth,
                anchor="center",
                stretch=True,
            )
        port_scroll = ttk.Scrollbar(port_tree_frame, orient=tk.VERTICAL, command=self._port_tree.yview)
        self._port_tree.configure(yscrollcommand=port_scroll.set)
        self._port_tree.grid(row=0, column=0, sticky="nsew")
        port_scroll.grid(row=0, column=1, sticky="ns")
        port_tree_frame.bind("<Configure>", self._fit_port_tree_columns, add="+")
        ttk.Button(port_wrap, text="刪除選取 Port", command=self._delete_selected_port).grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        self._port_wrap = port_wrap

        output_wrap = ttk.LabelFrame(bottom_row, text="組合結果輸出存取", padding=4)
        output_wrap.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
        output_wrap.columnconfigure(0, weight=1)
        ttk.Label(output_wrap, text="組合名稱").grid(row=0, column=0, sticky="w")
        title_entry = ttk.Entry(output_wrap, textvariable=self._combination_title)
        title_entry.grid(row=1, column=0, sticky="ew", pady=(2, 4))
        output_btn_row = ttk.Frame(output_wrap)
        output_btn_row.grid(row=2, column=0, sticky="ew")
        ttk.Button(output_btn_row, text="儲存", command=self._save_combination).pack(side=tk.LEFT)
        ttk.Button(output_btn_row, text="讀取", command=self._load_combination).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(
            output_wrap,
            text="留空名稱預設 Compose\n輸出至 CST/{時間}_{名稱}/",
            foreground="#555",
            justify=tk.LEFT,
        ).grid(row=3, column=0, sticky="w", pady=(6, 2))
        ttk.Checkbutton(
            output_wrap,
            text="清除現有 component 與 port",
            variable=self._clear_cst,
        ).grid(row=4, column=0, sticky="w")
        ttk.Button(output_wrap, text="輸出 CST 套件", command=self._export_cst).grid(
            row=5, column=0, sticky="ew", pady=(4, 0)
        )
        self._output_wrap = output_wrap

        self._status_label = ttk.Label(control_col, textvariable=self._status, foreground="#444", wraplength=380)
        self._status_label.pack(anchor="w", pady=(6, 0))

        main_frame, self._figure_main, self._canvas_main, self._main_view = attach_zoomable_canvas(
            main_wrap,
            title="組合預覽 — 滾輪縮放｜工具列框選縮放／平移",
            figsize=DEFAULT_FIGSIZE_SQUARE,
            on_reset=self._reset_main_view,
            on_global_reset=self._reset_all_views,
            on_undo=self._undo,
            on_redo=self._redo,
            undo_label="上一步 Ctrl+Z",
            redo_label="下一步 Ctrl+Y",
            enable_toolbar_pan=False,
        )
        main_frame.pack(fill=tk.BOTH, expand=True)
        canvas_widget = self._canvas_main.get_tk_widget()
        canvas_widget.bind("<Control-r>", self._on_ctrl_r)
        canvas_widget.bind("<Control-R>", self._on_ctrl_r)
        canvas_widget.bind("<Control-m>", self._on_ctrl_m)
        canvas_widget.bind("<Control-M>", self._on_ctrl_m)
        canvas_widget.bind("<Control-z>", self._on_ctrl_z)
        canvas_widget.bind("<Control-Z>", self._on_ctrl_z)
        canvas_widget.bind("<Control-y>", self._on_ctrl_y)
        canvas_widget.bind("<Control-Y>", self._on_ctrl_y)
        self._canvas_main.mpl_connect("motion_notify_event", self._on_main_motion)
        self._canvas_main.mpl_connect("button_press_event", self._on_main_press)
        self._canvas_main.mpl_connect("button_release_event", self._on_main_release)
        self._canvas_main.mpl_connect("key_press_event", self._on_main_key)

        paned.bind("<Configure>", self._on_paned_configure, add="+")
        self._pending_paned_ratios: dict[str, float] | None = None
        self._paned_customized = False
        self._paned_press_sash: int | None = None
        self._bind_paned_sash_handlers()

    def _bind_paned_sash_handlers(self) -> None:
        for paned in (self._main_paned, self._module_paned):
            paned.bind("<ButtonPress-1>", self._on_paned_press, add="+")
            paned.bind("<B1-Motion>", self._on_paned_motion, add="+")
            paned.bind("<ButtonRelease-1>", self._on_paned_release, add="+")
        self._remember_sash_positions()

    def _remember_sash_positions(self) -> None:
        try:
            self._saved_main_sash = int(self._main_paned.sashpos(0))
            self._saved_module_sash = int(self._module_paned.sashpos(0))
        except tk.TclError:
            self._saved_main_sash = None
            self._saved_module_sash = None

    def _on_paned_press(self, event: tk.Event) -> None:
        self._paned_press_sash = self._sash_index_at(event.widget, event.x, event.y)

    def _on_paned_motion(self, _event: tk.Event) -> None:
        if self._paned_press_sash is not None:
            self._paned_customized = True

    def _on_paned_release(self, _event: tk.Event) -> None:
        try:
            main_pos = int(self._main_paned.sashpos(0))
            mod_pos = int(self._module_paned.sashpos(0))
            if main_pos != getattr(self, "_saved_main_sash", None):
                self._paned_customized = True
            if mod_pos != getattr(self, "_saved_module_sash", None):
                self._paned_customized = True
            self._saved_main_sash = main_pos
            self._saved_module_sash = mod_pos
        except tk.TclError:
            pass
        self._paned_press_sash = None
        self._update_status_wrap()

    def _sash_index_at(self, paned: tk.Misc, x: int, y: int) -> int | None:
        try:
            panes = paned.panes()
            orient = str(paned.cget("orient")).lower()
            horizontal = orient.startswith("h")
            for index in range(len(panes) - 1):
                coord = int(paned.sash_coord(index)[0 if horizontal else 1])
                if abs((x if horizontal else y) - coord) <= 12:
                    return index
        except (tk.TclError, TypeError, ValueError):
            pass
        return None

    def _on_paned_configure(self, _event: object = None) -> None:
        self.after_idle(self._update_status_wrap)
        self.after_idle(self._fit_port_tree_columns)

    def _fit_port_tree_columns(self, _event: object = None) -> None:
        try:
            frame = self._port_tree.master
            total = int(frame.winfo_width())
            if total <= 40:
                return
            scroll_w = 18 if self._port_tree.cget("yscrollcommand") else 0
            available = max(total - scroll_w, sum(_PORT_COL_MINWIDTHS.values()))
            weights = {"idx": 1, "cell": 2, "edge": 1, "width": 2, "pos": 2}
            weight_sum = sum(weights.values())
            for col, minwidth in _PORT_COL_MINWIDTHS.items():
                width = max(minwidth, int(available * weights[col] / weight_sum))
                self._port_tree.column(col, width=width)
        except tk.TclError:
            pass

    def _update_status_wrap(self) -> None:
        try:
            ctrl_w = self._main_paned.winfo_width() - self._main_paned.sashpos(0)
            if ctrl_w > 80:
                self._status_label.configure(wraplength=max(280, ctrl_w - 24))
        except tk.TclError:
            pass

    def export_ui_state(self) -> dict[str, float]:
        try:
            main_total = self._main_paned.winfo_width()
            mod_total = self._module_paned.winfo_width()
            if main_total <= 0 or mod_total <= 0:
                return {}
            return {
                "main_sash_ratio": self._main_paned.sashpos(0) / main_total,
                "module_sash_ratio": self._module_paned.sashpos(0) / mod_total,
            }
        except tk.TclError:
            return {}

    def apply_ui_state(self, state: dict[str, float] | None) -> None:
        if state and ("main_sash_ratio" in state or "module_sash_ratio" in state):
            self._pending_paned_ratios = dict(state)
            self._paned_customized = True
        else:
            self._pending_paned_ratios = None
            self._paned_customized = False
        self.after_idle(lambda: self._apply_pending_paned_sashes(apply_defaults=not bool(state)))

    def _apply_pending_paned_sashes(self, *, apply_defaults: bool = False) -> None:
        try:
            ratios = self._pending_paned_ratios
            main_total = self._main_paned.winfo_width()
            mod_total = self._module_paned.winfo_width()
            if ratios and main_total > 200:
                ratio = float(ratios.get("main_sash_ratio", 0.62))
                self._main_paned.sashpos(0, max(200, min(main_total - 280, int(main_total * ratio))))
            elif apply_defaults and not self._paned_customized and main_total > 200:
                self._main_paned.sashpos(0, int(main_total * 0.62))
            if ratios and mod_total > 120:
                ratio = float(ratios.get("module_sash_ratio", 0.58))
                self._module_paned.sashpos(0, max(100, min(mod_total - 100, int(mod_total * ratio))))
            elif apply_defaults and not self._paned_customized and mod_total > 120:
                self._module_paned.sashpos(0, int(mod_total * 0.58))
            if ratios:
                self._pending_paned_ratios = None
            self._remember_sash_positions()
        except tk.TclError:
            pass
        self._update_status_wrap()

    def _record_step(self, action: str, detail: str = "", **args: object) -> None:
        step = {
            "seq": len(self._operation_steps) + 1,
            "action": action,
            "detail": detail,
        }
        for key, value in args.items():
            if value is not None:
                step[key] = value
        self._operation_steps.append(step)

    def _save_combination(self) -> None:
        title = self._combination_title.get().strip()
        if not title:
            messagebox.showwarning("儲存組合", "請輸入組合名稱。")
            return
        path = combination_path(title)
        if path.is_file() and not messagebox.askyesno(
            "覆蓋確認",
            f"「{path.name}」已存在，是否要覆蓋？",
        ):
            return
        try:
            layout = self._parse_layout()
            save_combination_file(
                path,
                title=title,
                layout=layout,
                grid_vars=self._grid_vars_dict(),
                operations=self._operation_steps,
                undo_stack=self._undo_stack,
                redo_stack=self._redo_stack,
                redo_steps=self._redo_steps,
            )
            log_operation("compose", "儲存組合", path.name)
            messagebox.showinfo("已儲存", f"組合已儲存至：\n{path}")
            self._status.set(f"已儲存組合：{path.name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("儲存失敗", str(exc))

    def _load_combination(self) -> None:
        from tkinter import filedialog

        from siw_generator.app_paths import combination_dir

        chosen = filedialog.askopenfilename(
            title="讀取組合",
            initialdir=str(combination_dir()),
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if not chosen:
            return
        path = Path(chosen)
        try:
            data = load_combination_file(path)
            layout, loaded_title, grid_vars, operations, restored, undo_stack, redo_stack, redo_steps = (
                apply_combination_data(data)
            )
            self._layout = layout
            self._undo_stack = undo_stack
            self._redo_stack = redo_stack
            self._operation_steps = list(operations)
            self._redo_steps = list(redo_steps)
            self._apply_grid_vars(grid_vars)
            self._combination_title.set(loaded_title or path.stem)
            self._cancel_pending()
            self._selected_cell = None
            self._drag_source = None
            self._drag_target = None
            self._selection_rect = None
            self._port_candidate = None
            self.refresh_module_list()
            self._refresh_port_tree()
            self._refresh_all()
            detail = path.name
            if restored:
                detail += f"；還原模組 {len(restored)} 個"
            log_operation("compose", "讀取組合", detail)
            msg = f"已載入組合：\n{path}"
            if restored:
                msg += "\n\n已還原至 module/：\n" + "\n".join(restored)
            messagebox.showinfo("已讀取", msg)
            self._status.set(f"已讀取組合：{path.name}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("讀取失敗", str(exc))

    def export_state(self) -> dict:
        return layout_to_dict(
            self._layout,
            recipe_name="",
            grid_vars=self._grid_vars_dict(),
        )

    def current_layout(self) -> ComposeLayout:
        return self._parse_layout()

    def combination_design_name(self) -> str:
        from siw_generator.export_paths import sanitize_design_name

        title = self._combination_title.get().strip()
        return sanitize_design_name(title) if title else "Compose"

    def clear_existing_cst(self) -> bool:
        return bool(self._clear_cst.get())

    def _export_cst(self) -> None:
        from siw_generator.app_paths import app_project_root
        from siw_generator.generator import generate_compose_cst

        try:
            layout = self.current_layout()
            if not layout.placements and not layout.filled_cells and not layout.ports:
                raise ValueError("組合為空，請先放置 module 或填補基板")
            name = self.combination_design_name()
            result = generate_compose_cst(
                layout,
                project_root=app_project_root(),
                design_name=name,
                clear_existing=self.clear_existing_cst(),
            )
            folder = result["output"]
            log_operation(
                "compose",
                "輸出 CST 套件",
                f"{name} | module {result['module_count']} | Port {result['port_count']}",
            )
            messagebox.showinfo(
                "輸出完成",
                f"已輸出至：\n{folder}\n\n"
                f"組合名稱：{name}\n"
                f"module {result['module_count']} | Port {result['port_count']}\n"
                f"含 DXF / STL / VBA / compose_params.txt",
            )
            self._status.set(f"已輸出 CST 至 {folder}")
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc))
            self._status.set(f"錯誤：{exc}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("輸出失敗", str(exc))
            self._status.set(f"錯誤：{exc}")

    def apply_state(self, state: dict | None) -> bool:
        if not state:
            return False
        try:
            layout, _recipe_name, grid_vars = layout_from_dict(state)
        except (ValueError, KeyError, TypeError):
            return False
        self._layout = layout
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._operation_steps.clear()
        self._redo_steps.clear()
        self._apply_grid_vars(grid_vars)
        from siw_generator.custom_io import material_display_for_key

        self._updating = True
        try:
            self._vars["fill_material"].set(material_display_for_key(layout.fill_material))
        finally:
            self._updating = False
        self._update_fill_material_info()
        self._refresh_port_tree()
        self._refresh_all()
        return True

    def _grid_vars_dict(self) -> dict[str, str]:
        keys = (
            "m_count", "n_count", "default_pitch_x", "default_pitch_y",
            "fill_height", "fill_copper_um", "fill_material", "leakage_margin_factor",
            "import_length", "import_width", "import_height", "import_copper_um",
        )
        return {k: self._vars[k].get() for k in keys}

    def _apply_grid_vars(self, grid_vars: dict[str, str]) -> None:
        self._updating = True
        try:
            for key, value in grid_vars.items():
                if key in self._vars:
                    self._vars[key].set(value)
        finally:
            self._updating = False

    def _on_import_param_change(self, *_args: object) -> None:
        if self._updating or self._selected_module is None:
            return
        try:
            module = self._module_from_import_fields(self._selected_module)
        except ValueError:
            return
        self._selected_module = module
        self._refresh_thumb()
        self._refresh_main()

    def _sync_import_fields_from_module(self, module: CustomModuleDefinition) -> None:
        self._updating = True
        self._vars["import_length"].set(f"{module.substrate_length_mm:.4f}")
        self._vars["import_width"].set(f"{module.substrate_width_mm:.4f}")
        self._vars["import_height"].set(f"{module.stackup.substrate_height_mm:.4f}")
        self._vars["import_copper_um"].set(f"{module.stackup.copper_thickness_um:.4f}")
        self._updating = False

    def _module_from_import_fields(self, base: CustomModuleDefinition) -> CustomModuleDefinition:
        length = float(self._vars["import_length"].get().strip())
        width = float(self._vars["import_width"].get().strip())
        height = float(self._vars["import_height"].get().strip())
        cu_um = float(self._vars["import_copper_um"].get().strip())
        if min(length, width, height, cu_um) <= 0:
            raise ValueError("模組參數須大於 0")
        return CustomModuleDefinition(
            substrate_length_mm=length,
            substrate_width_mm=width,
            stackup=StackupParams(substrate_height_mm=height, copper_thickness_mm=cu_um / 1000.0),
            material=base.material,
            center_freq_ghz=base.center_freq_ghz,
            siw_width_mm=base.siw_width_mm,
            via_diameter_mm=base.via_diameter_mm,
            via_pitch_mm=base.via_pitch_mm,
            slot_width_mm=base.slot_width_mm,
            slot_length_mm=base.slot_length_mm,
            slot_corner_r_mm=base.slot_corner_r_mm,
            slot_pitch_mm=base.slot_pitch_mm,
            vias=list(base.vias),
            kind=base.kind,
        )

    def _reset_all_views(self) -> None:
        self._main_view["custom"] = False
        self._thumb_view["custom"] = False
        self._refresh_main()
        self._refresh_thumb()

    def _push_undo(self) -> None:
        self._undo_stack.append(clone_layout(self._layout))
        if len(self._undo_stack) > self._UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._redo_steps.clear()

    def _apply_layout_snapshot(self, layout: ComposeLayout, *, status: str) -> None:
        self._layout = layout
        self._cancel_pending()
        self._selected_cell = None
        self._drag_source = None
        self._drag_target = None
        self._selection_rect = None
        self._port_candidate = None
        self._refresh_port_tree()
        self._status.set(status)
        self._refresh_all()

    def _undo(self) -> None:
        if not self._undo_stack:
            self._status.set("無可復原操作")
            return
        self._redo_stack.append(clone_layout(self._layout))
        if len(self._redo_stack) > self._UNDO_LIMIT:
            self._redo_stack.pop(0)
        if self._operation_steps:
            step = self._operation_steps.pop()
            self._redo_steps.append(step)
        self._apply_layout_snapshot(self._undo_stack.pop(), status="已回到上一步")

    def _redo(self) -> None:
        if not self._redo_stack:
            self._status.set("無可重做操作")
            return
        self._undo_stack.append(clone_layout(self._layout))
        if len(self._undo_stack) > self._UNDO_LIMIT:
            self._undo_stack.pop(0)
        if self._redo_steps:
            self._operation_steps.append(self._redo_steps.pop())
        self._apply_layout_snapshot(self._redo_stack.pop(), status="已前進下一步")

    def _on_ctrl_z(self, _event: object = None) -> None:
        self._undo()

    def _on_ctrl_y(self, _event: object = None) -> None:
        self._redo()

    def _on_mode_change(self, *_args: object) -> None:
        self._cancel_pending()
        self._drag_source = None
        self._drag_target = None
        self._selected_cell = None
        self._select_origin = None
        self._selection_rect = None
        self._port_candidate = None
        self._status.set(self._mode_hint(self._mode.get()))
        self._refresh_main()

    def _cancel_pending(self) -> None:
        self._pending = None
        self._pending_move_source = None
        self._conflict_hover_cell = None

    def _in_pitch_conflict(self) -> bool:
        return self._pending is not None

    def _conflict_status_hint(self) -> str:
        pending = self._pending
        if pending is None:
            return ""
        target = f"({pending.col},{pending.row})"
        action = "移動" if self._pending_move_source is not None else "置入"
        return (
            f"{action}尺寸衝突 @ cell {target}："
            f"左鍵點已放置 module 的 cell 對齊其 pitch；"
            f"左鍵點目標 cell {target} 或任意處右鍵 → 以新 module 尺寸為準"
        )

    def _notify_pitch_conflict(self) -> None:
        pending = self._pending
        if pending is None:
            return
        self._ghost_cell = None
        self._conflict_hover_cell = None
        target = f"({pending.col},{pending.row})"
        action = "移動" if self._pending_move_source is not None else "置入"
        messagebox.showinfo(
            "尺寸衝突",
            f"{action}至 cell {target} 時，module 尺寸與同列／同行 pitch 不合。\n\n"
            f"請選擇基準：\n"
            f"• 左鍵點「已放置 module」的 cell → 對齊該 module 的 pitch\n"
            f"• 左鍵點目標 cell {target} 或按右鍵 → 以新 module 尺寸更新 pitch\n\n"
            f"移入 cell 時會以邊框顏色提示；目標 cell 以藍框標示。",
        )
        self._status.set(self._conflict_status_hint())

    def refresh_module_list(self) -> None:
        self._module_paths = list_module_files()
        self._listbox.delete(0, tk.END)
        for path in self._module_paths:
            self._listbox.insert(tk.END, path.name)
        if not self._module_paths:
            self._listbox.insert(tk.END, "（module/ 尚無 JSON）")

    def _delete_selected_module_file(self) -> None:
        if not self._module_paths:
            messagebox.showwarning("刪除模組", "module/ 尚無可刪除的檔案")
            return
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showwarning("刪除模組", "請先在清單中選取要刪除的模組")
            return
        idx = int(sel[0])
        if idx >= len(self._module_paths):
            return
        path = self._module_paths[idx]
        in_use = sum(
            1
            for placed in self._layout.placements.values()
            if placed.source_path is not None and placed.source_path.resolve() == path.resolve()
        )
        msg = f"確定刪除 module/ 中的\n\n{path.name}？"
        if in_use:
            msg += f"\n\n（目前組合版面仍有 {in_use} 個 cell 使用此 module，刪除後無法重新放置）"
        if not messagebox.askyesno("刪除模組", msg):
            return
        try:
            path.unlink()
        except OSError as exc:
            messagebox.showerror("刪除失敗", str(exc))
            return
        if self._selected_path is not None and self._selected_path.resolve() == path.resolve():
            self._selected_module = None
            self._selected_path = None
            self._imported_kind = None
        log_operation("compose", "刪除 module 檔", path.name)
        self.refresh_module_list()
        self._refresh_thumb()
        self._status.set(f"已刪除 {path.name}")

    def _fill_stackup(self) -> StackupParams:
        h = float(self._vars["fill_height"].get().strip())
        cu_um = float(self._vars["fill_copper_um"].get().strip())
        if h <= 0 or cu_um <= 0:
            raise ValueError("填補基板 h、Cu 須大於 0")
        return StackupParams(substrate_height_mm=h, copper_thickness_mm=cu_um / 1000.0)

    def _fill_material_key(self) -> str:
        return resolve_material_key(self._vars["fill_material"].get())

    def _update_fill_material_info(self) -> None:
        try:
            mat = get_material(self._fill_material_key())
            tand = f"{mat.tan_delta:g}" if mat.tan_delta else "0"
            self._fill_material_info.set(
                f"εr={mat.er:g}  |  tanδ={tand}  |  CST：{mat.cst_material_name}"
            )
        except ValueError:
            self._fill_material_info.set("")

    def _on_fill_material_change(self, *_args: object) -> None:
        if self._updating:
            return
        self._update_fill_material_info()
        self._schedule_refresh()

    def _parse_leakage_margin_factor(self) -> float:
        from siw_generator.siw_geometry import DEFAULT_LEAKAGE_MARGIN_FACTOR, clamp_leakage_margin_factor

        text = self._vars["leakage_margin_factor"].get().strip()
        if not text:
            return DEFAULT_LEAKAGE_MARGIN_FACTOR
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError("防洩漏倍數請輸入有效數字") from exc
        return clamp_leakage_margin_factor(value)

    def _cut_substrate_frame(self) -> None:
        try:
            if self._selection_rect is not None:
                x0, y0, x1, y1 = self._selection_rect
            else:
                bounds = occupied_cells_bounds(self._layout)
                if bounds is None:
                    self._status.set("請圈選範圍，或先放置 module")
                    return
                x0, y0, x1, y1 = bounds
            self._push_undo()
            frame = apply_substrate_frame_from_rect(self._layout, x0, y0, x1, y1)
            self._selection_rect = None
            log_operation("compose", "切割基板", f"({frame[0]:.2f},{frame[1]:.2f})–({frame[2]:.2f},{frame[3]:.2f})")
            self._record_step(
                "cut_substrate",
                f"frame {frame[0]:.2f},{frame[1]:.2f}–{frame[2]:.2f},{frame[3]:.2f}",
                frame=list(frame),
            )
            self._status.set(
                f"已設定外框（已補齊至含所有 module）"
                f" X=[{frame[0]:.2f},{frame[2]:.2f}] Y=[{frame[1]:.2f},{frame[3]:.2f}] mm"
            )
            self._refresh_port_tree()
            self._refresh_main()
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")

    def _align_substrate_x_leakage(self) -> None:
        try:
            factor = self._parse_leakage_margin_factor()
            pitch, feature = representative_gap(self._layout, "x")
            margin = factor * (pitch - feature) if pitch > feature else factor * feature
            frame = compute_leakage_substrate_frame(self._layout, axis="x", margin_factor=factor)
            self._push_undo()
            self._layout.substrate_frame = frame
            recompute_all_port_positions(self._layout)
            log_operation("compose", "基板 X 防洩漏", f"margin={margin:.4f} mm")
            self._record_step("leakage_x", f"margin={margin:.4f} mm", margin_factor=factor, frame=list(frame))
            self._status.set(
                f"基板 X 防洩漏：依 left/right Port 外擴 {margin:.4f} mm；"
                f"X=[{frame[0]:.2f},{frame[2]:.2f}] mm"
            )
            self._refresh_main()
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")

    def _align_substrate_y_leakage(self) -> None:
        try:
            factor = self._parse_leakage_margin_factor()
            pitch, feature = representative_gap(self._layout, "y")
            margin = factor * (pitch - feature) if pitch > feature else factor * feature
            frame = compute_leakage_substrate_frame(self._layout, axis="y", margin_factor=factor)
            self._push_undo()
            self._layout.substrate_frame = frame
            recompute_all_port_positions(self._layout)
            log_operation("compose", "基板 Y 防洩漏", f"margin={margin:.4f} mm")
            self._record_step("leakage_y", f"margin={margin:.4f} mm", margin_factor=factor, frame=list(frame))
            self._status.set(
                f"基板 Y 防洩漏：依 top/bottom Port 外擴 {margin:.4f} mm；"
                f"Y=[{frame[1]:.2f},{frame[3]:.2f}] mm"
            )
            self._refresh_main()
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")

    def _parse_layout(self) -> ComposeLayout:
        try:
            m = int(self._vars["m_count"].get().strip())
            n = int(self._vars["n_count"].get().strip())
            dpx = float(self._vars["default_pitch_x"].get().strip())
            dpy = float(self._vars["default_pitch_y"].get().strip())
            fill_stackup = self._fill_stackup()
        except ValueError as exc:
            raise ValueError("M/N 須為整數，pitch／填補 stackup 須為有效數字") from exc
        if m < 1 or n < 1:
            raise ValueError("M、N 須 ≥ 1")
        if dpx <= 0 or dpy <= 0:
            raise ValueError("預設 pitch 須大於 0")

        kept: dict = {}
        for key, placed in self._layout.placements.items():
            col, row = key
            if col < m and row < n:
                kept[key] = placed
        kept_fills = {c for c in self._layout.filled_cells if c[0] < m and c[1] < n and c not in kept}
        kept_ports = [p for p in self._layout.ports if p.col < m and p.row < n]

        layout = ComposeLayout(
            m_count=m,
            n_count=n,
            default_pitch_x_mm=dpx,
            default_pitch_y_mm=dpy,
            col_pitch_mm=list(self._layout.col_pitch_mm),
            row_pitch_mm=list(self._layout.row_pitch_mm),
            placements=kept,
            filled_cells=kept_fills,
            fill_stackup=fill_stackup,
            fill_material=self._fill_material_key(),
            ports=kept_ports,
            substrate_frame=self._layout.substrate_frame,
        )
        sync_layout_geometry(layout)
        return layout

    def _apply_default_pitch_from_module(self) -> None:
        if self._selected_module is None:
            self._status.set("請先選取左側 module")
            return
        px, py = default_pitch_for_module(self._selected_module)
        self._updating = True
        self._vars["default_pitch_x"].set(f"{px:.4f}")
        self._vars["default_pitch_y"].set(f"{py:.4f}")
        self._updating = False
        self._schedule_refresh()

    def _on_module_select(self, _event: object = None) -> None:
        sel = self._listbox.curselection()
        if not sel or not self._module_paths:
            return
        idx = sel[0]
        if idx >= len(self._module_paths):
            return
        path = self._module_paths[idx]
        try:
            module = load_module_file(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("載入失敗", str(exc))
            return
        self._selected_module = module
        self._selected_path = path
        self._imported_kind = module.kind
        self._sync_import_fields_from_module(module)
        self._place_rotation = 0
        self._place_mirror = False
        if self._mode.get() == "place":
            self._status.set(f"已選 {path.name} — 移入主預覽左鍵放置")
        self._refresh_thumb()
        self._refresh_main()

    def _schedule_main_motion_refresh(self) -> None:
        if self._main_motion_job is not None:
            return
        self._main_motion_job = self.after(40, self._run_main_motion_refresh)

    def _run_main_motion_refresh(self) -> None:
        self._main_motion_job = None
        self._refresh_main()

    def _schedule_refresh(self, *_args: object) -> None:
        if self._updating:
            return
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(100, self._run_scheduled_refresh)

    def _run_scheduled_refresh(self) -> None:
        self._preview_job = None
        self._refresh_all()

    def _refresh_all(self) -> None:
        try:
            self._layout = self._parse_layout()
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")
            return
        self._refresh_port_tree()
        self._refresh_main()
        self._refresh_thumb()

    def _reset_main_view(self) -> None:
        self._main_view["custom"] = False
        self._refresh_main()

    def _reset_thumb_view(self) -> None:
        self._thumb_view["custom"] = False
        self._refresh_thumb()

    def _refresh_port_tree(self) -> None:
        for item in self._port_tree.get_children():
            self._port_tree.delete(item)
        for idx, port in enumerate(self._layout.ports):
            self._port_tree.insert("", tk.END, iid=str(idx), values=port_summary(port, idx))

    def _placed_at_event(self, event) -> tuple[int, int] | None:
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return None
        cell = cell_at_point(float(event.xdata), float(event.ydata), self._layout)
        if cell is None:
            cell = closest_cell(float(event.xdata), float(event.ydata), self._layout)
        if cell in self._layout.placements:
            return cell
        return None

    def _cell_at_event(self, event) -> tuple[int, int] | None:
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return None
        cell = cell_at_point(float(event.xdata), float(event.ydata), self._layout)
        if cell is None:
            return closest_cell(float(event.xdata), float(event.ydata), self._layout)
        return cell

    def _refresh_main(self) -> None:
        try:
            layout = self._layout if hasattr(self, "_layout") else self._parse_layout()
            limits = saved_limits(self._figure_main, self._main_view["custom"])
            drag_module = self._layout.placements.get(self._drag_source) if self._drag_source else None
            in_conflict = self._in_pitch_conflict()
            render_compose_main(
                layout,
                self._figure_main,
                ghost_module=(
                    self._selected_module
                    if self._mode.get() == "place" and not in_conflict
                    else None
                ),
                ghost_cell=(
                    self._ghost_cell if self._mode.get() == "place" and not in_conflict else None
                ),
                ghost_rotation_deg=self._place_rotation,
                ghost_mirror_x=self._place_mirror,
                selected_cell=self._selected_cell if self._mode.get() == "select" else None,
                drag_target_cell=self._drag_target,
                drag_module=drag_module,
                selection_rect=self._selection_rect,
                port_candidate=self._port_candidate,
                pending_cell=(self._pending.col, self._pending.row) if self._pending else None,
                hover_cell=self._conflict_hover_cell if in_conflict else None,
            )
            restore_limits(self._figure_main, limits)
            self._canvas_main.draw_idle()
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")

    def _refresh_thumb(self) -> None:
        limits = saved_limits(self._figure_thumb, self._thumb_view["custom"])
        self._figure_thumb.clear()
        if self._selected_module is not None and self._selected_path is not None:
            rot = self._place_rotation
            mirror = self._place_mirror
            if self._mode.get() == "select" and self._selected_cell is not None:
                placed = self._layout.placements.get(self._selected_cell)
                if placed is not None:
                    rot = placed.rotation_deg
                    mirror = placed.mirror_x
            render_module_thumbnail(
                self._selected_module,
                self._figure_thumb,
                title=self._selected_path.name,
                rotation_deg=rot,
                mirror_x=mirror,
            )
        restore_limits(self._figure_thumb, limits)
        self._canvas_thumb.draw_idle()

    def _on_main_motion(self, event) -> None:
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            changed = False
            if self._ghost_cell is not None:
                self._ghost_cell = None
                changed = True
            if self._drag_target is not None:
                self._drag_target = None
                changed = True
            if self._port_candidate is not None:
                self._port_candidate = None
                changed = True
            if self._conflict_hover_cell is not None:
                self._conflict_hover_cell = None
                changed = True
            if changed:
                self._schedule_main_motion_refresh()
            return

        mode = self._mode.get()
        x, y = float(event.xdata), float(event.ydata)

        if self._in_pitch_conflict():
            cell = self._cell_at_event(event)
            if cell != self._conflict_hover_cell:
                self._conflict_hover_cell = cell
                self._schedule_main_motion_refresh()
            return

        if mode == "substrate" and self._select_origin is not None:
            x0, y0 = self._select_origin
            self._selection_rect = normalize_rect(x0, y0, x, y)
            self._refresh_main()
            return

        cell = self._cell_at_event(event)
        if mode == "place" and self._selected_module is not None and cell is not None and not self._in_pitch_conflict():
            if self._ghost_cell != cell:
                self._ghost_cell = cell
                self._schedule_main_motion_refresh()
        elif mode == "select" and self._drag_source is not None and cell is not None:
            if self._drag_target != cell:
                self._drag_target = cell
                self._schedule_main_motion_refresh()
        elif mode == "port":
            candidate = find_port_candidate(x, y, self._layout)
            if candidate != self._port_candidate:
                self._port_candidate = candidate
                self._schedule_main_motion_refresh()

    def _on_main_press(self, event) -> None:
        self._canvas_main.get_tk_widget().focus_set()
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            return

        if self._pending is not None or self._pending_move_source is not None:
            if event.button == 1:
                self._resolve_with_reference(event, use_new_module=False)
            elif event.button == 3:
                self._resolve_with_reference(event, use_new_module=True)
            return

        mode = self._mode.get()

        if mode == "substrate" and event.button == 1:
            self._select_origin = (float(event.xdata), float(event.ydata))
            self._selection_rect = None
            return

        if mode == "port" and event.button == 1:
            if self._port_candidate is None:
                self._status.set("請移近有 module 的 cell 邊緣（需兩顆平行 via）")
                return
            self._push_undo()
            add_port(self._layout, self._port_candidate)
            self._refresh_port_tree()
            self._status.set(f"已新增 Port — 共 {len(self._layout.ports)} 個")
            log_operation("compose", "新增 Port", f"cell ({self._port_candidate.col},{self._port_candidate.row})")
            self._record_step(
                "add_port",
                f"cell ({self._port_candidate.col},{self._port_candidate.row}) {self._port_candidate.edge}",
                col=self._port_candidate.col,
                row=self._port_candidate.row,
                edge=self._port_candidate.edge,
            )
            self._refresh_main()
            return

        if event.button != 1:
            return

        cell = self._cell_at_event(event)

        if mode == "delete":
            if cell is not None and cell in self._layout.placements:
                self._push_undo()
                remove_placed_module(self._layout, cell[0], cell[1])
                if self._selected_cell == cell:
                    self._selected_cell = None
                self._status.set(f"已刪除 cell {cell}")
                log_operation("compose", "刪除 module", f"cell {cell}")
                self._record_step("remove_module", f"cell {cell}", col=cell[0], row=cell[1])
                self._refresh_main()
            return

        if mode == "select":
            placed_cell = self._placed_at_event(event)
            if placed_cell is not None:
                self._selected_cell = placed_cell
                self._drag_source = placed_cell
                self._drag_target = placed_cell
                placed = self._layout.placements[placed_cell]
                self._selected_module = placed.module
                self._selected_path = placed.source_path
                self._status.set(f"已選 cell {placed_cell} — 拖曳移動")
                self._refresh_thumb()
                self._refresh_main()
            elif cell is not None:
                self._selected_cell = None
                self._refresh_main()
            return

        if mode == "place":
            if self._selected_module is None:
                self._status.set("請先選取左側 module")
                return
            if cell is None:
                return
            col, row = cell
            label = self._selected_path.name if self._selected_path else ""
            self._push_undo()
            conflicts = place_module(
                self._layout,
                col,
                row,
                self._selected_module,
                source_path=self._selected_path,
                label=label,
                rotation_deg=self._place_rotation,
                mirror_x=self._place_mirror,
            )
            if conflicts:
                self._undo_stack.pop()
                self._pending = PendingPlacement(
                    col=col,
                    row=row,
                    module=self._selected_module,
                    source_path=self._selected_path,
                    label=label,
                    rotation_deg=self._place_rotation,
                    mirror_x=self._place_mirror,
                    conflicts=list(conflicts),
                )
                self._notify_pitch_conflict()
                self._refresh_main()
                return
            self._status.set(f"已放置 ({col},{row}) — 共 {len(self._layout.placements)}")
            log_operation("compose", "放置 module", f"cell ({col},{row})")
            self._record_step(
                "place_module",
                f"cell ({col},{row}) {label}",
                col=col,
                row=row,
                source=label,
                rotation_deg=self._place_rotation,
                mirror_x=self._place_mirror,
            )
            self._refresh_main()

    def _on_main_release(self, event) -> None:
        mode = self._mode.get()

        if mode == "substrate" and event.button == 1 and self._select_origin is not None:
            if event.inaxes is None or event.xdata is None or event.ydata is None:
                self._select_origin = None
                self._selection_rect = None
                self._refresh_main()
                return
            x0, y0 = self._select_origin
            x1, y1 = float(event.xdata), float(event.ydata)
            self._select_origin = None
            try:
                fx0, fy0, fx1, fy1 = resolve_operation_rect(x0, y0, x1, y1, self._layout)
            except ValueError as exc:
                self._status.set(str(exc))
                self._selection_rect = None
                self._refresh_main()
                return
            self._selection_rect = (fx0, fy0, fx1, fy1)
            self._push_undo()
            try:
                self._layout.fill_stackup = self._fill_stackup()
            except ValueError as exc:
                self._undo_stack.pop()
                self._status.set(str(exc))
                self._selection_rect = None
                self._refresh_main()
                return
            count = apply_substrate_fill_in_rect(self._layout, fx0, fy0, fx1, fy1)
            self._record_step(
                "fill_substrate",
                f"rect {fx0:.2f},{fy0:.2f}–{fx1:.2f},{fy1:.2f} count={count}",
                rect=[fx0, fy0, fx1, fy1],
                count=count,
            )
            self._status.set(f"已填補 {count} 個空白 cell（基板＋雙面銅）")
            self._refresh_main()
            return

        if event.button != 1 or mode != "select":
            return
        if self._drag_source is None:
            return
        if event.inaxes is None or event.xdata is None or event.ydata is None:
            self._drag_source = None
            self._drag_target = None
            self._refresh_main()
            return

        target = self._cell_at_event(event)
        source = self._drag_source
        self._drag_source = None
        self._drag_target = None
        if target is None or target == source:
            self._refresh_main()
            return
        if target in self._layout.placements:
            self._status.set("目標 cell 已有 module")
            self._refresh_main()
            return

        self._push_undo()
        conflicts = move_placed_module(self._layout, source, target)
        if conflicts:
            self._undo_stack.pop()
            self._pending_move_source = source
            placed = self._layout.placements[source]
            self._pending = PendingPlacement(
                col=target[0],
                row=target[1],
                module=placed.module,
                source_path=placed.source_path,
                label=placed.label,
                rotation_deg=placed.rotation_deg,
                mirror_x=placed.mirror_x,
                conflicts=list(conflicts),
            )
            self._notify_pitch_conflict()
            self._refresh_main()
            return

        self._selected_cell = target
        self._record_step(
            "move_module",
            f"{source} → {target}",
            from_col=source[0],
            from_row=source[1],
            to_col=target[0],
            to_row=target[1],
        )
        self._status.set(f"已移動至 {target}")
        self._refresh_main()

    def _resolve_with_reference(self, event, *, use_new_module: bool) -> None:
        pending = self._pending
        if pending is None:
            return

        target_cell = (pending.col, pending.row)
        if not use_new_module:
            cell = self._cell_at_event(event)
            if cell == target_cell:
                use_new_module = True

        if use_new_module:
            self._push_undo()
            if self._pending_move_source is not None:
                source = self._pending_move_source
                conflicts = move_placed_module(
                    self._layout,
                    source,
                    (pending.col, pending.row),
                    use_new_module_pitch=True,
                )
                if conflicts:
                    self._undo_stack.pop()
                    self._status.set("移動失敗")
                    return
                self._selected_cell = (pending.col, pending.row)
                self._record_step(
                    "move_module",
                    f"{source} → ({pending.col},{pending.row}) new_pitch",
                    from_col=source[0],
                    from_row=source[1],
                    to_col=pending.col,
                    to_row=pending.row,
                    pitch_mode="new_module",
                )
                self._status.set(f"已移動至 ({pending.col},{pending.row})（以新 module 為準）")
            else:
                place_module(
                    self._layout,
                    pending.col,
                    pending.row,
                    pending.module,
                    source_path=pending.source_path,
                    label=pending.label,
                    rotation_deg=pending.rotation_deg,
                    mirror_x=pending.mirror_x,
                    use_new_module_pitch=True,
                )
                self._record_step(
                    "place_module",
                    f"cell ({pending.col},{pending.row}) {pending.label} new_pitch",
                    col=pending.col,
                    row=pending.row,
                    source=pending.label,
                    rotation_deg=pending.rotation_deg,
                    mirror_x=pending.mirror_x,
                    pitch_mode="new_module",
                )
                self._status.set(f"已放置 ({pending.col},{pending.row})（以新 module 為準）")
            self._cancel_pending()
            self._refresh_main()
            return

        ref_cell = self._placed_at_event(event)
        if ref_cell is None:
            self._status.set(self._conflict_status_hint())
            return
        reference = self._layout.placements.get(ref_cell)
        if reference is None:
            return

        self._push_undo()
        if self._pending_move_source is not None:
            source = self._pending_move_source
            conflicts = move_placed_module(
                self._layout,
                source,
                (pending.col, pending.row),
                reference=reference,
                reference_conflicts=pending.conflicts,
            )
            if conflicts:
                self._undo_stack.pop()
                self._status.set("移動失敗")
                return
            self._selected_cell = (pending.col, pending.row)
            self._record_step(
                "move_module",
                f"{source} → ({pending.col},{pending.row}) ref {ref_cell}",
                from_col=source[0],
                from_row=source[1],
                to_col=pending.col,
                to_row=pending.row,
                ref_col=ref_cell[0],
                ref_row=ref_cell[1],
            )
            self._status.set(f"已移動（參照 {ref_cell}）")
        else:
            place_module(
                self._layout,
                pending.col,
                pending.row,
                pending.module,
                source_path=pending.source_path,
                label=pending.label,
                rotation_deg=pending.rotation_deg,
                mirror_x=pending.mirror_x,
                reference=reference,
                reference_conflicts=pending.conflicts,
            )
            self._record_step(
                "place_module",
                f"cell ({pending.col},{pending.row}) {pending.label} ref {ref_cell}",
                col=pending.col,
                row=pending.row,
                source=pending.label,
                rotation_deg=pending.rotation_deg,
                mirror_x=pending.mirror_x,
                ref_col=ref_cell[0],
                ref_row=ref_cell[1],
            )
            self._status.set(f"已放置（參照 {ref_cell}）")

        self._cancel_pending()
        self._refresh_main()

    def _delete_selected_port(self) -> None:
        sel = self._port_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self._push_undo()
        remove_port(self._layout, idx)
        self._refresh_port_tree()
        self._record_step("remove_port", f"index {idx}", index=idx)
        self._status.set(f"已刪除 Port — 剩 {len(self._layout.ports)} 個")
        self._refresh_main()

    def _on_main_key(self, event) -> None:
        key = (event.key or "").lower()
        if "ctrl" in key and key.endswith("r"):
            self._on_ctrl_r()
        elif "ctrl" in key and key.endswith("m"):
            self._on_ctrl_m()
        elif "ctrl" in key and key.endswith("z"):
            self._undo()

    def _on_ctrl_r(self, _event: object = None) -> None:
        mode = self._mode.get()
        if mode == "select" and self._selected_cell is not None:
            placed = self._layout.placements.get(self._selected_cell)
            if placed is None:
                return
            self._push_undo()
            rotate_placed(placed)
            apply_cell_fit_scales(placed, self._layout)
            self._record_step(
                "rotate_module",
                f"cell {self._selected_cell} {placed.rotation_deg}°",
                col=self._selected_cell[0],
                row=self._selected_cell[1],
                rotation_deg=placed.rotation_deg,
            )
            self._status.set(f"旋轉 {placed.rotation_deg}°")
            self._refresh_thumb()
            self._refresh_main()
        elif mode == "place":
            self._place_rotation = rotate_clockwise(self._place_rotation)
            self._status.set(f"置入旋轉 {self._place_rotation}°")
            self._refresh_thumb()
            self._refresh_main()

    def _on_ctrl_m(self, _event: object = None) -> None:
        mode = self._mode.get()
        if mode == "select" and self._selected_cell is not None:
            placed = self._layout.placements.get(self._selected_cell)
            if placed is None:
                return
            self._push_undo()
            mirror_placed(placed)
            self._record_step(
                "mirror_module",
                f"cell {self._selected_cell} mirror={placed.mirror_x}",
                col=self._selected_cell[0],
                row=self._selected_cell[1],
                mirror_x=placed.mirror_x,
            )
            self._status.set(f"鏡像 {'開' if placed.mirror_x else '關'}")
            self._refresh_thumb()
            self._refresh_main()
        elif mode == "place":
            self._place_mirror = not self._place_mirror
            self._status.set(f"鏡像 {'開' if self._place_mirror else '關'}")
            self._refresh_thumb()
            self._refresh_main()

    def _clear_all(self) -> None:
        if not self._layout.placements and not self._layout.filled_cells and not self._layout.ports:
            return
        self._push_undo()
        self._layout.placements.clear()
        self._layout.filled_cells.clear()
        self._layout.ports.clear()
        self._layout.substrate_frame = None
        self._cancel_pending()
        self._selected_cell = None
        self._drag_source = None
        self._drag_target = None
        self._selection_rect = None
        sync_pitch_from_placements(self._layout)
        self._refresh_port_tree()
        self._status.set("已清空組合預覽")
        log_operation("compose", "清空組合", "")
        self._record_step("clear_layout", "清空組合")
        self._reset_main_view()

    def on_tab_show(self) -> None:
        self.refresh_module_list()
        self._refresh_all()
        self._canvas_main.get_tk_widget().focus_set()
        self.after_idle(self._update_status_wrap)
        self.after_idle(self._fit_port_tree_columns)
