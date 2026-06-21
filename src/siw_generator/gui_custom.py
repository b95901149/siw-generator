"""Custom via placement tab."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from siw_generator.app_paths import module_dir
from siw_generator.custom_geometry import (
    VIA_ROLE_LABELS,
    VIA_ROLE_NAMES,
    VIA_TYPE_LABELS,
    VIA_TYPE_NAMES,
    CustomModuleDefinition,
    CustomVia,
    CustomViaType,
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


class CustomViaPanel(ttk.Frame):
    """Interactive custom via placement with hole list editing (scribeDXF style)."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._updating_fields = False
        self._holes: list[CustomVia] = []
        self._selected_idx: int | None = None
        self._ghost_xy: tuple[float, float] | None = None
        self._preview_job: str | None = None
        self._ghost_job: str | None = None
        self._preview_renderer: CustomPreviewRenderer | None = None
        self._view_state = {"custom": False}
        self._cell_editor: tk.Widget | None = None
        self._drag_iid: str | None = None
        self._loaded_kind = KIND_CUSTOM
        self._loaded_module: CustomModuleDefinition | None = None

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
            "click_add": tk.BooleanVar(value=True),
        }
        self._status = tk.StringVar(
            value="單擊滑鼠左鍵於預覽圖以放置 Via；單擊孔位列表儲存格以編輯"
        )

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
        ttk.Checkbutton(left, text="點擊預覽新增孔", variable=self._vars["click_add"]).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(4, 2)
        )
        row += 1
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
            selectmode="browse",
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
            fill=tk.X, pady=(2, 12)
        )
        ttk.Label(
            center,
            text="儲存／匯出 → module/\n(ctm- / RSIW- / SSIW-)\n載入亦從 module/",
            foreground="#555",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 12))

        ttk.Button(center, text="儲存模組", command=self._save_module).pack(fill=tk.X, pady=4)
        ttk.Button(center, text="載入模組", command=self._load_module_dialog).pack(fill=tk.X, pady=4)
        ttk.Button(center, text="更新預覽", command=self._refresh_preview).pack(fill=tk.X, pady=(12, 4))

        xy_frame, self._figure, self._canvas, self._view_state = attach_zoomable_canvas(
            right,
            title="XY 平面 — 滾輪縮放｜工具列框選縮放／平移",
            figsize=DEFAULT_FIGSIZE_SQUARE,
            on_reset=self._reset_view,
            on_global_reset=self._reset_view,
        )
        self._preview_renderer = CustomPreviewRenderer(self._figure)
        xy_frame.pack(fill=tk.BOTH, expand=True)
        self._canvas.mpl_connect("motion_notify_event", self._on_canvas_motion)
        self._canvas.mpl_connect("button_press_event", self._on_canvas_click)

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
        selected = self._tree.selection()
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
        if selected and selected[0] in self._tree.get_children(""):
            self._tree.selection_set(selected[0])
        elif not self._holes:
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
                renderer.set_ghost(self._ghost_via())
            else:
                module = self._build_module()
                renderer.draw_static(module, selected_hole_index=self._selected_idx)
                renderer.set_ghost(self._ghost_via())
                kind_note = ""
                if self._loaded_kind in (KIND_RSIW, KIND_SSIW):
                    kind_note = f" | 來源 {PREFIX_BY_KIND[self._loaded_kind]}"
                self._status.set(
                    f"Via {len(self._holes)} 個 | L={module.substrate_length_mm} mm{kind_note}"
                )
            restore_limits(self._figure, limits)
            self._canvas.draw_idle()
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")

    def _on_canvas_motion(self, event) -> None:
        if not self._vars["click_add"].get() or event.inaxes is None:
            if self._ghost_xy is not None:
                self._ghost_xy = None
                self._schedule_ghost_preview()
            return
        if event.xdata is None or event.ydata is None:
            return
        self._ghost_xy = (float(event.xdata), float(event.ydata))
        self._schedule_ghost_preview()

    def _on_canvas_click(self, event) -> None:
        if not self._vars["click_add"].get() or event.button != 1 or event.inaxes is None:
            return
        if event.xdata is None or event.ydata is None:
            return
        try:
            hole = self._parse_new_via(x_mm=float(event.xdata), y_mm=float(event.ydata))
        except (ValueError, KeyError) as exc:
            self._status.set(str(exc))
            return
        self._holes.append(hole)
        self._sync_loaded_module_vias()
        self._selected_idx = len(self._holes) - 1
        self._updating_fields = True
        self._vars["hole_x"].set(f"{hole.x_mm:.4f}")
        self._vars["hole_y"].set(f"{hole.y_mm:.4f}")
        self._updating_fields = False
        self._refresh_tree()
        self._tree.selection_set(str(self._selected_idx))
        self._refresh_preview()

    def _add_hole(self) -> None:
        try:
            hole = self._parse_new_via()
            self._holes.append(hole)
            self._sync_loaded_module_vias()
            self._selected_idx = len(self._holes) - 1
            self._refresh_tree()
            self._tree.selection_set(str(self._selected_idx))
            self._refresh_preview()
        except (ValueError, KeyError) as exc:
            self._status.set(str(exc))

    def _delete_hole(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        del self._holes[idx]
        self._sync_loaded_module_vias()
        self._selected_idx = None
        self._refresh_tree()
        self._refresh_preview()

    def _clear_holes(self) -> None:
        self._holes.clear()
        self._sync_loaded_module_vias()
        self._selected_idx = None
        self._ghost_xy = None
        self._cancel_editor()
        self._refresh_tree()
        self._refresh_preview()

    def _on_select(self, _event: object = None) -> None:
        sel = self._tree.selection()
        if not sel:
            self._selected_idx = None
            self._refresh_preview()
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._holes):
            self._selected_idx = idx
            hole = self._holes[idx]
            self._updating_fields = True
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
            self._updating_fields = False
            self._refresh_preview()
            return
        self._selected_idx = None
        self._refresh_preview()

    def _cancel_editor(self) -> None:
        if self._cell_editor is not None:
            self._cell_editor.destroy()
            self._cell_editor = None

    def _replace_hole(self, idx: int, via: CustomVia) -> None:
        self._holes[idx] = via
        self._sync_loaded_module_vias()
        self._selected_idx = idx
        self._refresh_tree()
        self._tree.selection_set(str(idx))
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
            self._selected_idx = b
            self._refresh_tree()
            self._tree.selection_set(str(b))
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
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc))
        except OSError as exc:
            messagebox.showerror("儲存失敗", str(exc))

    def _load_module_dialog(self) -> None:
        path_str = filedialog.askopenfilename(
            title="載入模組 (ctm- / RSIW- / SSIW-)",
            initialdir=str(module_dir()),
            filetypes=[("JSON 模組", "*.json"), ("所有檔案", "*.*")],
        )
        if not path_str:
            return
        self._load_module_path(Path(path_str))

    def _load_module_path(self, path: Path) -> None:
        try:
            module = load_module_file(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("載入失敗", str(exc))
            return

        self._loaded_module = module
        self._invalidate_preview()
        self._updating_fields = True
        try:
            self._holes = list(module.vias)
            self._loaded_kind = module.kind
            self._selected_idx = None
            self._vars["substrate_length"].set(f"{module.substrate_length_mm:.4f}")
            self._vars["substrate_width"].set(f"{module.substrate_width_mm:.4f}")
            self._vars["substrate_height"].set(f"{module.stackup.substrate_height_mm:.4f}")
            self._vars["copper_thickness_um"].set(f"{module.copper_thickness_um:.0f}")
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

            log_operation("module", "載入模組", path.name)
        finally:
            self._updating_fields = False

        self._update_material_info()
        self._refresh_tree()
        self._refresh_preview()
        kind_label = PREFIX_BY_KIND.get(module.kind, module.kind)
        self._status.set(f"已載入 {path.name}（{len(self._holes)} 個孔，{kind_label}）")
