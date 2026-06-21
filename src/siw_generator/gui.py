"""Tkinter GUI for SIW via pattern design."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from siw_generator.app_paths import app_project_root, recipe_dir
from siw_generator import __version__
from siw_generator.export_paths import sanitize_design_name
from siw_generator.generator import generate_siw_cst
from siw_generator.gui_preview import (
    DEFAULT_FIGSIZE_SQUARE,
    DEFAULT_FIGSIZE_WIDE,
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
from siw_generator.preview import render_preview, render_preview_yz
from siw_generator.siw_geometry import (
    SIWParams,
    build_siw_geometry,
    compute_leakage_safe_substrate_length_circular,
    default_port_height_factor,
    default_port_height_mm,
    default_port_width_factor,
)
from siw_generator.stackup import StackupParams
from siw_generator.gui_slot import SlotViaPanel
from siw_generator.gui_cst_vba import CSTVbaPanel

PROJECT_ROOT = app_project_root()


class CircularViaPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)

        self._updating_fields = False

        self._vars = {
            "design_name": tk.StringVar(value="SIW"),
            "freq_ghz": tk.StringVar(value="120.0"),
            "via_diameter": tk.StringVar(value="0.15"),
            "siw_length": tk.StringVar(value="10.0"),
            "substrate_width": tk.StringVar(value="10.0"),
            "substrate_height": tk.StringVar(value="0.127"),
            "copper_thickness_um": tk.StringVar(value="15"),
            "substrate_material": tk.StringVar(value=default_substrate_display_name()),
            "siw_width": tk.StringVar(value="1.2745"),
            "via_pitch": tk.StringVar(value="0.28"),
            "via_count": tk.StringVar(value="54"),
            "leakage_margin_factor": tk.StringVar(value="0.5"),
            "port1_x": tk.StringVar(value=""),
            "port2_x": tk.StringVar(value=""),
            "port1_enabled": tk.BooleanVar(value=True),
            "port2_enabled": tk.BooleanVar(value=True),
            "port_height_factor": tk.StringVar(value=""),
            "port_width_factor": tk.StringVar(value=""),
        }
        self._status = tk.StringVar(value="就緒")
        self._geometry = None
        self._preview_job: str | None = None
        self._xy_view_state = {"custom": False}
        self._yz_view_state = {"custom": False}
        self._slot_panel: SlotViaPanel | None = None
        self._cst_panel = None
        self._cst_refresh_job: str | None = None
        self._hfss_panel = None
        self._hfss_refresh_job: str | None = None
        self._overlay_var = tk.BooleanVar(value=False)
        self._module_panel = None

        self._build_ui()
        self._setup_traces()

    def _setup_traces(self) -> None:
        for name in ("freq_ghz", "via_diameter", "siw_length", "substrate_height"):
            self._vars[name].trace_add("write", self._on_primary_param_change)
        for name in ("substrate_width", "design_name", "siw_width"):
            self._vars[name].trace_add("write", self._on_secondary_param_change)
        self._vars["via_count"].trace_add("write", self._on_secondary_param_change)
        self._vars["via_pitch"].trace_add("write", self._on_secondary_param_change)
        for name in ("port1_x", "port2_x"):
            self._vars[name].trace_add("write", self._on_port_param_change)
        self._vars["port1_enabled"].trace_add("write", self._on_port_param_change)
        self._vars["port2_enabled"].trace_add("write", self._on_port_param_change)
        self._vars["port_height_factor"].trace_add("write", self._on_port_param_change)
        self._vars["port_width_factor"].trace_add("write", self._on_port_param_change)
        self._vars["substrate_height"].trace_add("write", self._on_port_param_change)
        self._vars["copper_thickness_um"].trace_add("write", self._on_port_param_change)
        self._vars["substrate_material"].trace_add("write", self._on_material_change)

    def attach_cst_panel(self, panel) -> None:
        self._cst_panel = panel

    def attach_hfss_panel(self, panel) -> None:
        self._hfss_panel = panel

    def export_state(self) -> dict:
        from siw_generator.gui_state import export_panel_vars

        return export_panel_vars(self._vars)

    def apply_state(self, state: dict | None) -> bool:
        from siw_generator.gui_state import apply_panel_vars

        self._updating_fields = True
        try:
            ok = apply_panel_vars(self._vars, state)
        finally:
            self._updating_fields = False
        if ok:
            self._update_material_info()
        return ok

    def finish_init(self, *, apply_defaults: bool = True) -> None:
        if apply_defaults:
            self._apply_defaults(
                update_fields=True,
                include_siw_width=True,
                include_port_factors=True,
                include_via_layout=True,
            )
        else:
            self._update_material_info()
            self._apply_defaults(update_fields=False)
        self._refresh_preview()

    def _build_ui(self) -> None:
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(paned, padding=8)
        center = ttk.Frame(paned, padding=8)
        right = ttk.Frame(paned, padding=4)
        paned.add(left, weight=2)
        paned.add(center, weight=1)
        paned.add(right, weight=3)

        ttk.Label(left, text="SIW 參數", font=("", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        fields = [
            ("中心頻率 (GHz)", "freq_ghz"),
            ("Via 直徑 (mm)", "via_diameter"),
            ("SIW 長度 (mm)", "siw_length"),
            ("防洩漏倍數 (0~2)", "leakage_margin_factor"),
            ("基板寬度 (mm)", "substrate_width"),
            ("基板厚度 h (mm)", "substrate_height"),
            ("銅厚 t_cu (µm)", "copper_thickness_um"),
            ("SIW 寬度 w (mm，可調)", "siw_width"),
            ("Via 個數 (總數)", "via_count"),
            ("Via 孔距 p (mm，可調)", "via_pitch"),
        ]
        field_start = 2
        for row, (label, key) in enumerate(fields, start=field_start):
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w", pady=4)
            entry = ttk.Entry(left, textvariable=self._vars[key], width=14)
            entry.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
            if key == "siw_width":
                entry.bind("<KeyRelease>", self._on_secondary_param_change)
                entry.bind("<FocusOut>", self._on_secondary_param_change)

        ttk.Label(left, text="基板材料").grid(row=1, column=0, sticky="w", pady=4)
        material_combo = ttk.Combobox(
            left,
            textvariable=self._vars["substrate_material"],
            values=substrate_display_names(),
            state="readonly",
            width=28,
        )
        material_combo.grid(row=1, column=1, sticky="ew", pady=4, padx=(8, 0))
        material_combo.bind("<<ComboboxSelected>>", self._on_material_change)

        hint_row = field_start + len(fields)
        self._siw_width_hint = tk.StringVar(value="")
        ttk.Label(
            left,
            textvariable=self._siw_width_hint,
            foreground="#555",
            wraplength=240,
        ).grid(row=hint_row, column=0, columnspan=2, sticky="w", pady=(0, 2))

        port_section = hint_row + 1
        ttk.Label(left, text="Port 設定", font=("", 10, "bold")).grid(
            row=port_section, column=0, columnspan=2, sticky="w", pady=(12, 4)
        )

        for idx, (label, key) in enumerate(
            [("埠高度 ×h", "port_height_factor"), ("埠寬度 ×w", "port_width_factor")]
        ):
            ttk.Label(left, text=label).grid(row=port_section + 1 + idx, column=0, sticky="w", pady=2)
            entry = ttk.Entry(left, textvariable=self._vars[key], width=14)
            entry.grid(row=port_section + 1 + idx, column=1, sticky="ew", pady=2, padx=(8, 0))
            entry.bind("<KeyRelease>", self._on_port_param_change)
            entry.bind("<FocusOut>", self._on_port_param_change)

        self._port_hint = tk.StringVar(value="")
        ttk.Label(
            left,
            textvariable=self._port_hint,
            foreground="#555",
            wraplength=240,
        ).grid(row=port_section + 3, column=0, columnspan=2, sticky="w", pady=(2, 4))

        port1_row = ttk.Frame(left)
        port1_row.grid(row=port_section + 4, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        ttk.Checkbutton(port1_row, text="Port1 左側", variable=self._vars["port1_enabled"]).pack(
            side=tk.LEFT
        )
        ttk.Label(port1_row, text="YZ X").pack(side=tk.LEFT, padx=(8, 2))
        port1_entry = ttk.Entry(port1_row, textvariable=self._vars["port1_x"], width=8)
        port1_entry.pack(side=tk.LEFT)
        port1_entry.bind("<KeyRelease>", self._on_port_param_change)
        port1_entry.bind("<FocusOut>", self._on_port_param_change)

        port2_row = ttk.Frame(left)
        port2_row.grid(row=port_section + 5, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Checkbutton(port2_row, text="Port2 右側", variable=self._vars["port2_enabled"]).pack(
            side=tk.LEFT
        )
        ttk.Label(port2_row, text="YZ X").pack(side=tk.LEFT, padx=(8, 2))
        port2_entry = ttk.Entry(port2_row, textvariable=self._vars["port2_x"], width=8)
        port2_entry.pack(side=tk.LEFT)
        port2_entry.bind("<KeyRelease>", self._on_port_param_change)
        port2_entry.bind("<FocusOut>", self._on_port_param_change)

        port_btn_row = ttk.Frame(left)
        port_btn_row.grid(row=port_section + 6, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Button(port_btn_row, text="Port 還原預設", command=self._restore_port_defaults).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(port_btn_row, text="基板 X 防洩漏", command=self._align_substrate_x_leakage).pack(
            side=tk.LEFT
        )

        left.columnconfigure(1, weight=1)

        self._material_info = tk.StringVar(value="")
        ttk.Label(
            left,
            textvariable=self._material_info,
            wraplength=240,
            foreground="#555",
        ).grid(row=port_section + 7, column=0, columnspan=2, sticky="w", pady=(12, 4))
        self._update_material_info()

        btn_row = ttk.Frame(left)
        btn_row.grid(row=port_section + 8, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        ttk.Checkbutton(
            btn_row,
            text="Slot 疊圖",
            variable=self._overlay_var,
            command=self._on_slot_overlay_toggle,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="還原建議值", command=self._restore_defaults).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        ttk.Button(btn_row, text="更新預覽", command=self._refresh_preview).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="Port 自動定位", command=self._auto_ports).pack(side=tk.LEFT)

        # Center column
        ttk.Label(center, text="輸出 / 模組", font=("", 11, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(center, text="名稱").pack(anchor="w")
        ttk.Entry(center, textvariable=self._vars["design_name"], width=18).pack(
            fill=tk.X, pady=(2, 8)
        )

        from siw_generator.custom_io import KIND_RSIW
        from siw_generator.gui_module_panel import ModuleFilePanel

        self._module_panel = ModuleFilePanel(
            center,
            kind=KIND_RSIW,
            on_import=self._apply_imported_module,
            on_export=self._export_custom_module,
        )
        self._module_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        ttk.Label(
            center,
            text="留空名稱預設 SIW\n輸出至 CST/{時間}_{名稱}/",
            foreground="#555",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Button(center, text="輸出 CST 套件", command=self._export_cst).pack(fill=tk.X, pady=4)

        ttk.Label(center, textvariable=self._status, wraplength=200, foreground="#444").pack(
            anchor="w", pady=(12, 0)
        )

        # Right: dual preview
        preview_paned = ttk.Panedwindow(right, orient=tk.VERTICAL)
        preview_paned.pack(fill=tk.BOTH, expand=True)

        xy_frame, self._figure_xy, self._canvas_xy, self._xy_view_state = attach_zoomable_canvas(
            preview_paned,
            title="XY 平面 — Via 俯視（滾輪縮放、工具列平移）",
            figsize=DEFAULT_FIGSIZE_SQUARE,
            on_reset=self._reset_xy_view,
        )
        yz_frame, self._figure_yz, self._canvas_yz, self._yz_view_state = attach_zoomable_canvas(
            preview_paned,
            title="YZ 平面 — Port / Via（滾輪縮放、工具列平移）",
            figsize=DEFAULT_FIGSIZE_WIDE,
            on_reset=self._reset_yz_view,
        )
        preview_paned.add(xy_frame, weight=3)
        preview_paned.add(yz_frame, weight=2)

    def _design_name(self) -> str:
        return sanitize_design_name(self._vars["design_name"].get())

    def design_name(self) -> str:
        return self._design_name()

    def _stackup(self) -> StackupParams:
        h = self._parse_float("substrate_height", "基板厚度")
        cu_um = self._parse_float("copper_thickness_um", "銅厚")
        return StackupParams(
            substrate_height_mm=h,
            copper_thickness_mm=cu_um / 1000.0,
        )

    def _on_primary_param_change(self, *_args: object) -> None:
        self._apply_defaults(update_fields=True, include_siw_width=False)
        self._refresh_preview()

    def _on_secondary_param_change(self, *_args: object) -> None:
        if self._updating_fields:
            return
        self._update_port_hint()
        self._schedule_preview_refresh()

    def _on_port_param_change(self, *_args: object) -> None:
        if self._updating_fields:
            return
        self._update_port_hint()
        self._schedule_preview_refresh()

    def _update_port_hint(self, *, siw_width: float | None = None) -> None:
        try:
            stack = self._stackup()
            h = stack.substrate_height_mm
            h_port_default = default_port_height_mm(stack)
            h_f, w_f = self._computed_port_factors()
            w_used = siw_width
            if w_used is None:
                w_text = self._vars["siw_width"].get().strip()
                if w_text:
                    w_used = float(w_text)
                else:
                    params = self._draft_params(with_overrides=False)
                    params.stackup = stack
                    w_used = params.default_siw_width_mm()
            try:
                ph = float(self._vars["port_height_factor"].get().strip() or h_f)
                pw = float(self._vars["port_width_factor"].get().strip() or w_f)
            except ValueError:
                ph, pw = h_f, w_f
            self._port_hint.set(
                f"預設 Port：H = h+2×t_cu = {h_port_default:.4f} mm（×h={h_f:.4f}），"
                f"W = w = {w_used:.4f} mm（×w={w_f:.1f}）；"
                f"目前 H={ph * h:.4f} mm，W={pw * w_used:.4f} mm"
            )
        except ValueError:
            pass

    def _update_material_info(self) -> None:
        mat = get_material(self._vars["substrate_material"].get())
        tand = f"{mat.tan_delta:g}" if mat.tan_delta > 0 else "0 (loss free)"
        self._material_info.set(
            f"εr={mat.er:g}  |  tanδ={tand}  |  CST：{mat.cst_material_name}"
        )

    def _on_material_change(self, *_args: object) -> None:
        if self._updating_fields:
            return
        self._update_material_info()
        self._apply_defaults(update_fields=False)
        self._schedule_preview_refresh()

    def _schedule_preview_refresh(self) -> None:
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(120, self._run_scheduled_preview)
        self._schedule_cst_vba_refresh()
        self._schedule_hfss_refresh()

    def _schedule_cst_vba_refresh(self) -> None:
        if self._cst_panel is None:
            return
        if self._cst_refresh_job is not None:
            self.after_cancel(self._cst_refresh_job)
        self._cst_refresh_job = self.after(200, self._run_cst_vba_refresh)

    def _schedule_hfss_refresh(self) -> None:
        if self._hfss_panel is None:
            return
        if self._hfss_refresh_job is not None:
            self.after_cancel(self._hfss_refresh_job)
        self._hfss_refresh_job = self.after(200, self._run_hfss_refresh)

    def _run_hfss_refresh(self) -> None:
        self._hfss_refresh_job = None
        if self._hfss_panel is not None:
            self._hfss_panel.refresh()

    def _run_cst_vba_refresh(self) -> None:
        self._cst_refresh_job = None
        if self._cst_panel is not None:
            self._cst_panel.refresh()

    def _run_scheduled_preview(self) -> None:
        self._preview_job = None
        self._refresh_preview()

    def _reset_xy_view(self) -> None:
        self._xy_view_state["custom"] = False
        self._refresh_preview()

    def _reset_yz_view(self) -> None:
        self._yz_view_state["custom"] = False
        self._refresh_preview()

    def _parse_float(self, key: str, label: str, *, positive: bool = True) -> float:
        text = self._vars[key].get().strip()
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"{label} 請輸入有效數字") from exc
        if positive and value <= 0:
            raise ValueError(f"{label} 必須大於 0")
        return value

    def _parse_int(self, key: str, label: str) -> int:
        text = self._vars[key].get().strip()
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError(f"{label} 請輸入整數") from exc
        if value < 4:
            raise ValueError(f"{label} 至少為 4")
        if value % 2 != 0:
            raise ValueError(f"{label} 須為偶數")
        return value

    def _parse_optional_float(self, key: str) -> float | None:
        text = self._vars[key].get().strip()
        if not text:
            return None
        return float(text)

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

    def _computed_port_factors(self) -> tuple[float, float]:
        stack = self._stackup()
        return default_port_height_factor(stack), default_port_width_factor()

    def attach_slot_panel(self, panel: SlotViaPanel) -> None:
        self._slot_panel = panel

    def overlay_enabled(self) -> bool:
        return bool(self._overlay_var.get())

    def refresh_overlay_if_enabled(self) -> None:
        if self.overlay_enabled():
            self._refresh_preview()

    def _on_slot_overlay_toggle(self) -> None:
        self._refresh_preview()

    def _parse_port_factor(self, key: str, *, default: float, lenient: bool) -> float:
        label = "埠高度倍數" if "height" in key else "埠寬度倍數"
        text = self._vars[key].get().strip()
        if not text:
            if lenient:
                return default
            raise ValueError(f"{label} 請輸入有效數字")
        try:
            value = float(text)
        except ValueError as exc:
            if lenient:
                return default
            raise ValueError(f"{label} 請輸入有效數字") from exc
        if value <= 0:
            raise ValueError(f"{label} 必須大於 0")
        return value

    def _draft_params(self, *, with_overrides: bool, lenient_ports: bool = False) -> SIWParams:
        freq = self._parse_float("freq_ghz", "中心頻率")
        via_d = self._parse_float("via_diameter", "Via 直徑")
        length = self._parse_float("siw_length", "SIW 長度")
        sub_w = self._parse_float("substrate_width", "基板寬度")
        stackup = self._stackup() if with_overrides else StackupParams()

        siw_w = self._parse_float("siw_width", "SIW 寬度") if with_overrides else None
        pitch = self._parse_float("via_pitch", "Via 孔距") if with_overrides else None
        via_count = self._parse_int("via_count", "Via 個數") if with_overrides else None

        port1_x = self._parse_optional_float("port1_x") if with_overrides else None
        port2_x = self._parse_optional_float("port2_x") if with_overrides else None
        if with_overrides:
            h_def, w_def = self._computed_port_factors()
            port_h = self._parse_port_factor(
                "port_height_factor", default=h_def, lenient=lenient_ports
            )
            port_w = self._parse_port_factor(
                "port_width_factor", default=w_def, lenient=lenient_ports
            )
        else:
            stack = StackupParams()
            port_h = default_port_height_factor(stack)
            port_w = default_port_width_factor()

        return SIWParams(
            substrate_length_mm=length,
            substrate_width_mm=sub_w,
            center_freq_ghz=freq,
            via_diameter_mm=via_d,
            material=resolve_material_key(self._vars["substrate_material"].get()),
            stackup=stackup,
            siw_width_mm=siw_w,
            via_count_target=via_count,
            via_pitch_mm=pitch,
            port1_x_mm=port1_x,
            port2_x_mm=port2_x,
            port1_enabled=self._vars["port1_enabled"].get(),
            port2_enabled=self._vars["port2_enabled"].get(),
            port_height_factor=port_h,
            port_width_factor=port_w,
        )

    def _apply_defaults(
        self,
        update_fields: bool = False,
        *,
        include_siw_width: bool = True,
        include_port_factors: bool = False,
        include_via_layout: bool = False,
    ) -> None:
        try:
            params = self._draft_params(with_overrides=False)
            params.stackup = self._stackup()
            try:
                params_live = self._draft_params(with_overrides=True)
                pitch = params_live.via_pitch_mm or params.default_via_pitch_mm()
                params_live.via_pitch_mm = pitch
                d = params_live.via_diameter_mm
            except ValueError:
                pitch = params.default_via_pitch_mm()
                d = params.via_diameter_mm
                params_live = params
            count = params.default_via_count()
            a_eff = params.equivalent_waveguide_width_mm()
            correction = (d * d) / (0.95 * pitch)
            suggested_w = a_eff + correction
            fc = params.default_fc_ghz()
            suggested_h_factor, suggested_w_factor = self._computed_port_factors()
            if update_fields:
                self._updating_fields = True
                default_pitch = params.default_via_pitch_mm()
                if include_siw_width:
                    self._vars["siw_width"].set(f"{params.default_siw_width_mm(default_pitch):.4f}")
                if include_port_factors:
                    self._vars["port_height_factor"].set(f"{suggested_h_factor:.4f}")
                    self._vars["port_width_factor"].set(f"{suggested_w_factor:.4f}")
                if include_via_layout:
                    self._vars["via_pitch"].set(f"{default_pitch:.4f}")
                    self._vars["via_count"].set(str(count))
                self._updating_fields = False
            current_w = self._vars["siw_width"].get().strip()
            hint = (
                f"建議寬度 a = a_eff + d²/(0.95p) = {a_eff:.3f} + {correction:.3f} "
                f"= {suggested_w:.4f} mm（fc={fc:.1f} GHz）"
            )
            if current_w:
                self._siw_width_hint.set(f"{hint}；目前使用 {current_w} mm")
            else:
                self._siw_width_hint.set(hint)
            self._update_port_hint()
            self._status.set(
                f"建議值：a_eff={a_eff:.3f} mm，a={suggested_w:.4f} mm，"
                f"孔距 {pitch:.4f} mm，Via {count} 個（fc={fc:.1f} GHz）"
            )
        except ValueError as exc:
            self._status.set(str(exc))

    def _restore_defaults(self) -> None:
        self._apply_defaults(
            update_fields=True,
            include_siw_width=True,
            include_port_factors=False,
            include_via_layout=True,
        )
        self._refresh_preview()

    def _restore_port_defaults(self) -> None:
        h_f, w_f = self._computed_port_factors()
        self._updating_fields = True
        self._vars["port_height_factor"].set(f"{h_f:.4f}")
        self._vars["port_width_factor"].set(f"{w_f:.4f}")
        self._vars["port1_x"].set("")
        self._vars["port2_x"].set("")
        self._updating_fields = False
        self._apply_defaults(update_fields=False)
        self._refresh_preview()

    def _align_substrate_x_leakage(self) -> None:
        try:
            pitch = self._parse_float("via_pitch", "Via 孔距")
            diameter = self._parse_float("via_diameter", "Via 直徑")
            count = self._parse_int("via_count", "Via 個數")
            factor = self._parse_leakage_margin_factor()
            new_len = compute_leakage_safe_substrate_length_circular(
                pitch_mm=pitch,
                via_diameter_mm=diameter,
                via_count=count,
                margin_factor=factor,
            )
            margin = factor * (pitch - diameter)
            self._updating_fields = True
            self._vars["siw_length"].set(f"{new_len:.4f}")
            self._updating_fields = False
            self._apply_defaults(update_fields=False)
            self._refresh_preview()
            self._status.set(
                f"基板 X 已對齊：端面至 Via 邊緣 = {factor:g}×(pitch−d) = {margin:.4f} mm，"
                f"長度 {new_len:.4f} mm"
            )
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")

    def _auto_ports(self) -> None:
        self._vars["port1_x"].set("")
        self._vars["port2_x"].set("")
        self._refresh_preview()

    def _build_geometry(self, *, lenient_ports: bool = False) -> None:
        params = self._draft_params(with_overrides=True, lenient_ports=lenient_ports)
        params.siw_width_mm = self._parse_float("siw_width", "SIW 寬度")
        params.via_pitch_mm = self._parse_float("via_pitch", "Via 孔距")
        params.via_count_target = self._parse_int("via_count", "Via 個數")
        params.stackup = self._stackup()
        self._geometry = build_siw_geometry(params)

    def _refresh_preview(self) -> None:
        try:
            self._do_refresh_preview(lenient_ports=False)
        except ValueError:
            try:
                self._do_refresh_preview(lenient_ports=True)
            except ValueError as exc:
                self._status.set(f"錯誤：{exc}")
            except Exception as exc:  # noqa: BLE001
                self._status.set(f"錯誤：{exc}")

    def _do_refresh_preview(self, *, lenient_ports: bool) -> None:
        try:
            xy_limits = saved_limits(self._figure_xy, self._xy_view_state["custom"])
            yz_limits = saved_limits(self._figure_yz, self._yz_view_state["custom"])

            self._build_geometry(lenient_ports=lenient_ports)
            assert self._geometry is not None
            overlay_geom = None
            if self._overlay_var.get() and self._slot_panel is not None:
                overlay_geom = self._slot_panel.overlay_slot_geometry()
            render_preview(self._geometry, self._figure_xy, overlay_slot_geometry=overlay_geom)
            render_preview_yz(self._geometry, self._figure_yz)
            restore_limits(self._figure_xy, xy_limits)
            restore_limits(self._figure_yz, yz_limits)

            self._apply_defaults(update_fields=False)
            self._canvas_xy.draw_idle()
            self._canvas_yz.draw_idle()
            g = self._geometry
            clip = f"（截掉 {g.via_count_requested - g.via_count}）" if g.via_count_clipped else ""
            overlay_note = ""
            if overlay_geom is not None:
                sp = overlay_geom.params
                overlay_note = (
                    f" | Slot 疊圖 {len(overlay_geom.slot_vias)} 個"
                    f" | 基板 {sp.substrate_length_mm:.2f}×{sp.substrate_width_mm:.2f} mm"
                )
            self._status.set(
                f"預覽 OK | w={g.siw_width_mm:.4f} mm | Via {g.via_count}{clip} | "
                f"h={g.params.stackup.substrate_height_mm} mm{overlay_note}"
            )
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")
            raise
        except Exception as exc:  # noqa: BLE001
            self._status.set(f"錯誤：{exc}")
            raise

    def _export_cst(self, *, clear_existing: bool = True) -> None:
        try:
            self._build_geometry()
            assert self._geometry is not None
            p = self._geometry.params
            name = self._design_name()

            result = generate_siw_cst(
                project_root=PROJECT_ROOT,
                design_name=name,
                substrate_length_mm=p.substrate_length_mm,
                substrate_width_mm=p.substrate_width_mm,
                substrate_height_mm=p.stackup.substrate_height_mm,
                center_freq_ghz=p.center_freq_ghz,
                via_diameter_mm=p.via_diameter_mm,
                material=p.material,
                siw_width_mm=p.siw_width_mm,
                via_pitch_mm=p.via_pitch_mm,
                via_count_target=p.via_count_target,
                port1_x_mm=p.port1_x_mm,
                port2_x_mm=p.port2_x_mm,
                port1_enabled=p.port1_enabled,
                port2_enabled=p.port2_enabled,
                port_height_factor=p.port_height_factor,
                port_width_factor=p.port_width_factor,
                clear_existing=clear_existing,
            )
            folder = result["output"]
            messagebox.showinfo(
                "輸出完成",
                f"已輸出至：\n{folder}\n\n"
                f"設計名稱：{name}\n"
                f"Via 數量：{result['via_count']}\n"
                f"含 DXF / STL / VBA / siw_params.txt",
            )
            self._status.set(f"已輸出至 {folder}")
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc))
            self._status.set(f"錯誤：{exc}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("輸出失敗", str(exc))
            self._status.set(f"錯誤：{exc}")

    def _export_custom_module(self) -> None:
        from siw_generator.custom_io import KIND_RSIW, save_geometry_module_with_confirm
        from siw_generator.operation_log import log_operation

        try:
            self._build_geometry(lenient_ports=True)
            assert self._geometry is not None
            title = self._design_name()
            path = save_geometry_module_with_confirm(
                self,
                self._geometry,
                kind=KIND_RSIW,
                title=title,
            )
            if path is None:
                return
            log_operation("module", "匯出模組", path.name)
            messagebox.showinfo(
                "匯出完成",
                f"已匯出至：\n{path}\n\nVia {self._geometry.via_count} 個（不含 Port）",
            )
            self._status.set(f"已匯出 {path.name}")
            if self._module_panel is not None:
                self._module_panel.refresh_list()
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc))
        except OSError as exc:
            messagebox.showerror("匯出失敗", str(exc))

    def _apply_imported_module(self, module, path: Path) -> None:
        from siw_generator.custom_io import KIND_RSIW, material_display_for_key, module_stem_without_prefix
        from siw_generator.operation_log import log_operation

        self._updating_fields = True
        try:
            self._vars["design_name"].set(module_stem_without_prefix(path.name, KIND_RSIW))
            self._vars["freq_ghz"].set(f"{module.center_freq_ghz:.4f}")
            if module.via_diameter_mm is not None:
                self._vars["via_diameter"].set(f"{module.via_diameter_mm:.4f}")
            self._vars["siw_length"].set(f"{module.substrate_length_mm:.4f}")
            self._vars["substrate_width"].set(f"{module.substrate_width_mm:.4f}")
            self._vars["substrate_height"].set(f"{module.stackup.substrate_height_mm:.4f}")
            self._vars["copper_thickness_um"].set(f"{module.stackup.copper_thickness_um:.0f}")
            self._vars["substrate_material"].set(material_display_for_key(module.material))
            if module.siw_width_mm is not None:
                self._vars["siw_width"].set(f"{module.siw_width_mm:.4f}")
            if module.via_pitch_mm is not None:
                self._vars["via_pitch"].set(f"{module.via_pitch_mm:.4f}")
            if module.vias:
                self._vars["via_count"].set(str(len(module.vias)))
        finally:
            self._updating_fields = False

        self._update_material_info()
        self._apply_defaults(
            update_fields=True,
            include_siw_width=False,
            include_port_factors=True,
            include_via_layout=False,
        )
        self._refresh_preview()
        log_operation("module", "匯入模組", path.name)
        self._status.set(f"已匯入 {path.name}")

    def on_tab_show(self) -> None:
        if self._module_panel is not None:
            self._module_panel.refresh_list()

    def current_geometry(self):
        """Return geometry for CST VBA preview/export."""
        self._build_geometry(lenient_ports=True)
        if self._geometry is None:
            raise ValueError("無法建立幾何")
        return self._geometry


def main() -> None:
    from siw_generator.console_encoding import configure_console_encoding

    configure_console_encoding()
    app = SIWGeneratorApp()
    app.mainloop()


class SIWGeneratorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"SIW Via Generator {__version__}")
        self.minsize(1200, 720)

        self._recipe_name = tk.StringVar(value="")
        self._build_recipe_bar()
        self._configure_notebook_style()

        notebook = ttk.Notebook(self, style="Semi.TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._notebook = notebook

        circular = CircularViaPanel(notebook)
        slot = SlotViaPanel(notebook)
        circular.attach_slot_panel(slot)
        slot.attach_overlay_target(circular)
        from siw_generator.gui_custom import CustomViaPanel

        custom = CustomViaPanel(notebook)
        from siw_generator.gui_compose import ComposePanel

        compose = ComposePanel(notebook)
        cst_vba = CSTVbaPanel(notebook, circular_panel=circular, slot_panel=slot, compose_panel=compose)
        circular.attach_cst_panel(cst_vba)
        slot.attach_cst_panel(cst_vba)
        from siw_generator.gui_hfss import HfssScriptPanel

        hfss = HfssScriptPanel(notebook, circular_panel=circular, slot_panel=slot)
        circular.attach_hfss_panel(hfss)
        slot.attach_hfss_panel(hfss)

        from siw_generator.gui_help_panel import HelpPanel

        help_panel = HelpPanel(notebook)
        notebook.add(circular, text="圓形 Via")
        notebook.add(slot, text="圓角矩形 Slot Via")
        notebook.add(custom, text="Custom")
        notebook.add(compose, text="組合")
        notebook.add(cst_vba, text="CST VBA")
        notebook.add(hfss, text="HFSS")
        notebook.add(help_panel, text="說明")

        self._circular = circular
        self._slot = slot
        self._custom = custom
        self._compose = compose
        self._cst_vba = cst_vba
        self._hfss = hfss
        self._help_panel = help_panel

        self._pending_ui_state: dict | None = None
        self._startup_done = False
        self._load_last_session_or_defaults()

        def _on_tab_changed(_event: object) -> None:
            idx = notebook.index(notebook.select())
            if idx == notebook.index(circular):
                circular.on_tab_show()
            elif idx == notebook.index(slot):
                slot.on_tab_show()
            elif idx == notebook.index(cst_vba):
                cst_vba.convert()
            elif idx == notebook.index(hfss):
                hfss.convert()
            elif idx == notebook.index(compose):
                compose.on_tab_show()
            elif idx == notebook.index(help_panel):
                help_panel.on_tab_show()

        notebook.bind("<<NotebookTabChanged>>", _on_tab_changed)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after_idle(self._finalize_startup)

    def _maximize_window(self) -> None:
        try:
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            self.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
        w = max(self.winfo_screenwidth(), 1200)
        h = max(self.winfo_screenheight(), 720)
        self.geometry(f"{w}x{h}+0+0")

    def _finalize_startup(self) -> None:
        self._maximize_window()
        self.update_idletasks()
        if self._pending_ui_state:
            self._apply_ui_state(self._pending_ui_state)
            self._pending_ui_state = None
        else:
            self._compose.apply_ui_state(None)
        self._startup_done = True

    def _collect_ui_state(self) -> dict:
        return dict(self._compose.export_ui_state())

    def _apply_ui_state(self, ui: dict | None) -> None:
        if not ui:
            self._compose.apply_ui_state(None)
            return
        self._compose.apply_ui_state(ui)

    def _configure_notebook_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Semi.TNotebook", background="#1b2838", borderwidth=0, tabmargins=(2, 4, 2, 0))
        style.configure(
            "Semi.TNotebook.Tab",
            font=("Microsoft JhengHei", 12),
            padding=(16, 10),
            background="#3d4f61",
            foreground="#cfd8dc",
        )
        style.map(
            "Semi.TNotebook.Tab",
            background=[("selected", "#0277bd"), ("active", "#455a64")],
            foreground=[("selected", "#ffffff"), ("active", "#eceff1")],
            expand=[("selected", [1, 1, 1, 0])],
        )

    def _build_recipe_bar(self) -> None:
        bar = ttk.Frame(self, padding=(8, 6, 8, 0))
        bar.pack(fill=tk.X)
        ttk.Label(bar, text="Recipe 檔名").pack(side=tk.LEFT)
        ttk.Entry(bar, textvariable=self._recipe_name, width=28).pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(bar, text="儲存", command=self._save_recipe).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(bar, text="讀取", command=self._load_recipe_dialog).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(
            bar,
            text="儲存於 recipe/ ；空白檔名 → 時間戳記_SIW.json ；關閉時自動記住欄位",
            foreground="#666",
        ).pack(side=tk.LEFT)

    def _active_tab_key(self) -> str:
        idx = self._notebook.index(self._notebook.select())
        if idx == self._notebook.index(self._compose):
            return "compose"
        if idx == self._notebook.index(self._slot):
            return "slot"
        return "circular"

    def _collect_recipe_data(self) -> tuple[str, str, dict, dict, dict]:
        return (
            self._recipe_name.get(),
            self._active_tab_key(),
            self._circular.export_state(),
            self._slot.export_state(),
            self._compose.export_state(),
        )

    def _apply_recipe_data(self, data: dict) -> None:
        if data.get("circular"):
            self._circular.apply_state(data["circular"])
        if data.get("slot"):
            self._slot.apply_state(data["slot"])
        if data.get("compose"):
            self._compose.apply_state(data["compose"])
        self._circular.finish_init(apply_defaults=False)
        self._slot.finish_init(apply_defaults=False)
        active = data.get("active_tab", "circular")
        if active == "compose":
            target = self._compose
        elif active == "slot":
            target = self._slot
        else:
            target = self._circular
        self._notebook.select(target)
        name = str(data.get("recipe_name", "")).strip()
        if name:
            self._recipe_name.set(name)
        ui = data.get("ui_state")
        if isinstance(ui, dict) and ui:
            if self._startup_done:
                self.after_idle(lambda u=dict(ui): self._apply_ui_state(u))
            else:
                self._pending_ui_state = ui
        elif self._startup_done:
            self.after_idle(lambda: self._compose.apply_ui_state(None))

    def _save_recipe(self) -> None:
        from siw_generator.export_paths import resolve_recipe_stem
        from siw_generator.recipe_io import recipe_path, save_recipe_file

        try:
            recipe_name, active_tab, circular, slot, compose = self._collect_recipe_data()
            stem = resolve_recipe_stem(recipe_name)
            path = save_recipe_file(
                recipe_path(stem),
                recipe_name=stem,
                active_tab=active_tab,
                circular=circular,
                slot=slot,
                compose=compose,
                ui_state=self._collect_ui_state(),
            )
            self._recipe_name.set(stem)
            from siw_generator.operation_log import log_operation

            log_operation("recipe", "儲存 Recipe", path.name)
            messagebox.showinfo("已儲存", f"Recipe 已儲存至：\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("儲存失敗", str(exc))

    def _load_recipe_dialog(self) -> None:
        from tkinter import filedialog

        from siw_generator.recipe_io import load_recipe_file

        path = filedialog.askopenfilename(
            title="讀取 Recipe",
            initialdir=str(recipe_dir()),
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            data = load_recipe_file(Path(path))
            self._apply_recipe_data(data)
            from siw_generator.operation_log import log_operation

            log_operation("recipe", "讀取 Recipe", Path(path).name)
            messagebox.showinfo("已讀取", f"已載入：\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("讀取失敗", str(exc))

    def _load_last_session_or_defaults(self) -> None:
        from siw_generator.recipe_io import load_session

        data = load_session()
        if data:
            self._apply_recipe_data(data)
        else:
            self._circular.finish_init(apply_defaults=True)
            self._slot.finish_init(apply_defaults=True)

    def _on_close(self) -> None:
        from siw_generator.recipe_io import save_session

        try:
            recipe_name, active_tab, circular, slot, compose = self._collect_recipe_data()
            save_session(
                recipe_name=recipe_name,
                active_tab=active_tab,
                circular=circular,
                slot=slot,
                compose=compose,
                ui_state=self._collect_ui_state(),
            )
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


if __name__ == "__main__":
    main()
