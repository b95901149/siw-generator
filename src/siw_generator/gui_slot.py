"""GUI panel for rounded-rectangle slot via SIW."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from typing import TYPE_CHECKING

from siw_generator.app_paths import app_project_root
from siw_generator.export_paths import sanitize_design_name
from siw_generator.generator import generate_slot_siw_cst
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
    DEFAULT_LEAKAGE_MARGIN_FACTOR,
    SIWGeometry,
    clamp_leakage_margin_factor,
    default_port_height_factor,
    default_port_height_mm,
    default_port_width_factor,
)
from siw_generator.slot_geometry import (
    SlotSIWParams,
    build_slot_siw_geometry,
    compute_leakage_safe_substrate_length_slot,
)
from siw_generator.stackup import StackupParams

if TYPE_CHECKING:
    from siw_generator.gui import CircularViaPanel

PROJECT_ROOT = app_project_root()


class SlotViaPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self._updating_fields = False
        self._vars = {
            "design_name": tk.StringVar(value="SIW_Slot"),
            "freq_ghz": tk.StringVar(value="120.0"),
            "siw_length": tk.StringVar(value="10.0"),
            "substrate_width": tk.StringVar(value="10.0"),
            "substrate_height": tk.StringVar(value="0.127"),
            "copper_thickness_um": tk.StringVar(value="15"),
            "substrate_material": tk.StringVar(value=default_substrate_display_name()),
            "siw_width": tk.StringVar(value="1.027"),
            "slot_width": tk.StringVar(value="0.15"),
            "slot_length": tk.StringVar(value="1.0"),
            "slot_corner_r": tk.StringVar(value="0.015"),
            "slot_pitch": tk.StringVar(value="1.05"),
            "slot_count": tk.StringVar(value="18"),
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
        self._overlay_circular: CircularViaPanel | None = None
        self._cst_panel = None
        self._cst_refresh_job: str | None = None
        self._hfss_panel = None
        self._hfss_refresh_job: str | None = None
        self._module_panel = None

        self._build_ui()
        self._setup_traces()

    def _setup_traces(self) -> None:
        self._vars["substrate_material"].trace_add("write", self._on_material_change)
        for name in ("freq_ghz", "siw_length", "substrate_height"):
            self._vars[name].trace_add("write", self._on_primary_change)
        self._vars["copper_thickness_um"].trace_add("write", self._on_param_change)
        for name in ("substrate_width", "design_name", "siw_width"):
            self._vars[name].trace_add("write", self._on_secondary_change)
        for key in (
            "slot_width", "slot_length", "slot_corner_r", "slot_pitch", "slot_count",
            "port1_x", "port2_x", "port_height_factor", "port_width_factor",
        ):
            self._vars[key].trace_add("write", self._on_param_change)
        self._vars["port1_enabled"].trace_add("write", self._on_param_change)
        self._vars["port2_enabled"].trace_add("write", self._on_param_change)

    def attach_overlay_target(self, circular_panel: CircularViaPanel) -> None:
        """Notify circular panel when Slot params change (for XY overlay)."""
        self._overlay_circular = circular_panel

    def attach_cst_panel(self, panel) -> None:
        self._cst_panel = panel

    def attach_hfss_panel(self, panel) -> None:
        self._hfss_panel = panel

    def overlay_slot_geometry(self) -> SIWGeometry | None:
        """Slot geometry for overlay on circular SIW preview."""
        try:
            self._build_geometry()
            return self._geometry
        except ValueError:
            return None

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
                update_fields=True, include_siw_width=True, include_port_factors=True
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

        ttk.Label(left, text="Slot SIW 參數", font=("", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        fields = [
            ("中心頻率 (GHz)", "freq_ghz"),
            ("SIW 長度 (mm)", "siw_length"),
            ("防洩漏倍數 (0~2)", "leakage_margin_factor"),
            ("基板寬度 (mm)", "substrate_width"),
            ("基板厚度 h (mm)", "substrate_height"),
            ("銅厚 t_cu (µm)", "copper_thickness_um"),
            ("SIW 寬度 w (mm，可調)", "siw_width"),
            ("Slot 寬度 W (mm)", "slot_width"),
            ("Slot 長度 L (mm)", "slot_length"),
            ("Slot R 角半徑 (mm)", "slot_corner_r"),
            ("Slot pitch (mm)", "slot_pitch"),
            ("Slot 個數 (總數)", "slot_count"),
        ]
        field_start = 2
        for row, (label, key) in enumerate(fields, start=field_start):
            ttk.Label(left, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(left, textvariable=self._vars[key], width=14).grid(
                row=row, column=1, sticky="ew", pady=3, padx=(8, 0)
            )

        ttk.Label(left, text="基板材料").grid(row=1, column=0, sticky="w", pady=3)
        material_combo = ttk.Combobox(
            left,
            textvariable=self._vars["substrate_material"],
            values=substrate_display_names(),
            state="readonly",
            width=28,
        )
        material_combo.grid(row=1, column=1, sticky="ew", pady=3, padx=(8, 0))
        material_combo.bind("<<ComboboxSelected>>", self._on_material_change)

        hint_row = field_start + len(fields)
        self._siw_hint = tk.StringVar(value="")
        ttk.Label(left, textvariable=self._siw_hint, foreground="#555", wraplength=240).grid(
            row=hint_row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )

        port_section = hint_row + 1
        ttk.Label(left, text="Port 設定", font=("", 10, "bold")).grid(
            row=port_section, column=0, columnspan=2, sticky="w", pady=(8, 4)
        )
        for idx, (label, key) in enumerate(
            [("埠高度 ×h", "port_height_factor"), ("埠寬度 ×w", "port_width_factor")]
        ):
            ttk.Label(left, text=label).grid(row=port_section + 1 + idx, column=0, sticky="w", pady=2)
            ttk.Entry(left, textvariable=self._vars[key], width=14).grid(
                row=port_section + 1 + idx, column=1, sticky="ew", pady=2, padx=(8, 0)
            )

        self._port_hint = tk.StringVar(value="")
        ttk.Label(left, textvariable=self._port_hint, foreground="#555", wraplength=240).grid(
            row=port_section + 3, column=0, columnspan=2, sticky="w", pady=(2, 4)
        )

        port1_row = ttk.Frame(left)
        port1_row.grid(row=port_section + 4, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ttk.Checkbutton(port1_row, text="Port1 左側", variable=self._vars["port1_enabled"]).pack(side=tk.LEFT)
        ttk.Label(port1_row, text="YZ X").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Entry(port1_row, textvariable=self._vars["port1_x"], width=8).pack(side=tk.LEFT)

        port2_row = ttk.Frame(left)
        port2_row.grid(row=port_section + 5, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Checkbutton(port2_row, text="Port2 右側", variable=self._vars["port2_enabled"]).pack(side=tk.LEFT)
        ttk.Label(port2_row, text="YZ X").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Entry(port2_row, textvariable=self._vars["port2_x"], width=8).pack(side=tk.LEFT)

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
        ).grid(row=port_section + 7, column=0, columnspan=2, sticky="w", pady=(10, 4))
        ttk.Label(
            left,
            text="Slot 外形：obround（兩端半圓 R=W/2，長邊沿 X）",
            wraplength=240,
            foreground="#555",
        ).grid(row=port_section + 8, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self._update_material_info()

        btn_row = ttk.Frame(left)
        btn_row.grid(row=port_section + 9, column=0, columnspan=2, sticky="ew", pady=(6, 4))
        ttk.Button(btn_row, text="還原建議值", command=self._restore_defaults).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="更新預覽", command=self._refresh_preview).pack(side=tk.LEFT)

        ttk.Label(center, text="輸出 / 模組", font=("", 11, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(center, text="名稱").pack(anchor="w")
        ttk.Entry(center, textvariable=self._vars["design_name"], width=18).pack(
            fill=tk.X, pady=(2, 8)
        )

        from siw_generator.custom_io import KIND_SSIW
        from siw_generator.gui_module_panel import ModuleFilePanel

        self._module_panel = ModuleFilePanel(
            center,
            kind=KIND_SSIW,
            on_import=self._apply_imported_module,
            on_export=self._export_custom_module,
        )
        self._module_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        ttk.Label(
            center,
            text="留空名稱預設 SIW_Slot\n輸出至 CST/{時間}_{名稱}/",
            foreground="#555",
            justify=tk.LEFT,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Button(center, text="輸出 CST 套件", command=self._export_cst).pack(fill=tk.X, pady=4)

        ttk.Label(center, textvariable=self._status, wraplength=200, foreground="#444").pack(
            anchor="w", pady=(12, 0)
        )

        preview_paned = ttk.Panedwindow(right, orient=tk.VERTICAL)
        preview_paned.pack(fill=tk.BOTH, expand=True)

        xy_frame, self._figure_xy, self._canvas_xy, self._xy_view_state = attach_zoomable_canvas(
            preview_paned,
            title="XY 平面 — Slot 俯視（滾輪縮放、工具列平移）",
            figsize=DEFAULT_FIGSIZE_SQUARE,
            on_reset=self._reset_xy_view,
        )
        yz_frame, self._figure_yz, self._canvas_yz, self._yz_view_state = attach_zoomable_canvas(
            preview_paned,
            title="YZ 平面 — Port / Slot（滾輪縮放、工具列平移）",
            figsize=DEFAULT_FIGSIZE_WIDE,
            on_reset=self._reset_yz_view,
        )
        preview_paned.add(xy_frame, weight=3)
        preview_paned.add(yz_frame, weight=2)

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
        if value < 2 or value % 2 != 0:
            raise ValueError(f"{label} 須為 ≥2 的偶數（2 = 連續壁，上下各 1 個 Slot）")
        return value

    def _parse_optional_float(self, key: str) -> float | None:
        text = self._vars[key].get().strip()
        return float(text) if text else None

    def _stackup(self) -> StackupParams:
        h = self._parse_float("substrate_height", "基板厚度")
        cu_um = self._parse_float("copper_thickness_um", "銅厚")
        return StackupParams(
            substrate_height_mm=h,
            copper_thickness_mm=cu_um / 1000.0,
        )

    def _parse_leakage_margin_factor(self) -> float:
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

    def _update_port_hint(self, *, siw_width: float | None = None) -> None:
        try:
            stack = self._stackup()
            h = stack.substrate_height_mm
            h_port_default = default_port_height_mm(stack)
            h_f, w_f = self._computed_port_factors()
            w_used = siw_width
            if w_used is None:
                w_text = self._vars["siw_width"].get().strip()
                w_used = float(w_text) if w_text else SlotSIWParams(stackup=stack).default_siw_width_mm()
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

    def _parse_port_factor(self, key: str, label: str) -> float:
        h_def, w_def = self._computed_port_factors()
        default = h_def if "height" in key else w_def
        text = self._vars[key].get().strip()
        if not text:
            return default
        value = float(text)
        if value <= 0:
            raise ValueError(f"{label} 必須大於 0")
        return value

    def _draft_params(self) -> SlotSIWParams:
        return SlotSIWParams(
            substrate_length_mm=self._parse_float("siw_length", "SIW 長度"),
            substrate_width_mm=self._parse_float("substrate_width", "基板寬度"),
            center_freq_ghz=self._parse_float("freq_ghz", "中心頻率"),
            slot_width_mm=self._parse_float("slot_width", "Slot 寬度 W"),
            slot_length_mm=self._parse_float("slot_length", "Slot 長度 L"),
            slot_corner_r_mm=self._parse_float("slot_corner_r", "Slot R 角", positive=False),
            slot_pitch_mm=self._parse_float("slot_pitch", "Slot pitch"),
            material=resolve_material_key(self._vars["substrate_material"].get()),
            stackup=self._stackup(),
            siw_width_mm=self._parse_float("siw_width", "SIW 寬度"),
            via_count_target=self._parse_int("slot_count", "Slot 個數"),
            port1_x_mm=self._parse_optional_float("port1_x"),
            port2_x_mm=self._parse_optional_float("port2_x"),
            port1_enabled=self._vars["port1_enabled"].get(),
            port2_enabled=self._vars["port2_enabled"].get(),
            port_height_factor=self._parse_port_factor("port_height_factor", "埠高度倍數"),
            port_width_factor=self._parse_port_factor("port_width_factor", "埠寬度倍數"),
        )

    def _apply_defaults(
        self,
        update_fields: bool = False,
        *,
        include_siw_width: bool = True,
        include_port_factors: bool = False,
    ) -> None:
        try:
            params = SlotSIWParams(stackup=self._stackup())
            params.center_freq_ghz = self._parse_float("freq_ghz", "中心頻率")
            suggested_w = params.default_siw_width_mm()
            count = params.default_slot_count()
            if update_fields:
                self._updating_fields = True
                if include_siw_width:
                    self._vars["siw_width"].set(f"{suggested_w:.4f}")
                if include_port_factors:
                    h_f, w_f = self._computed_port_factors()
                    self._vars["port_height_factor"].set(f"{h_f:.4f}")
                    self._vars["port_width_factor"].set(f"{w_f:.4f}")
                self._vars["slot_count"].set(str(count))
                self._updating_fields = False
            current = self._vars["siw_width"].get().strip() or f"{suggested_w:.4f}"
            self._siw_hint.set(
                f"建議 SIW 寬度（矩形波導近似）{suggested_w:.4f} mm；目前 {current} mm"
            )
            self._update_port_hint(siw_width=float(current))
            self._status.set(f"建議：w={suggested_w:.4f} mm，Slot {count} 個，pitch=1.05 mm")
        except ValueError as exc:
            self._status.set(str(exc))

    def _restore_defaults(self) -> None:
        self._updating_fields = True
        self._vars["slot_width"].set("0.15")
        self._vars["slot_length"].set("1.0")
        self._vars["slot_corner_r"].set("0.015")
        self._vars["slot_pitch"].set("1.05")
        self._updating_fields = False
        self._apply_defaults(update_fields=True, include_siw_width=True, include_port_factors=False)
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
            length = self._parse_float("slot_length", "Slot 長度 L")
            count = self._parse_int("slot_count", "Slot 個數")
            factor = self._parse_leakage_margin_factor()
            if count == 2:
                width = self._parse_float("slot_width", "Slot 寬度 W")
                new_len = compute_leakage_safe_substrate_length_slot(
                    pitch_mm=0.0,
                    slot_length_mm=length,
                    slot_count=count,
                    slot_width_mm=width,
                    margin_factor=factor,
                )
                margin = factor * width
                status = (
                    f"基板 X 已對齊：連續壁（Slot 2 個置中）| "
                    f"端面至 Slot 邊緣 = {factor:g}×W = {margin:.4f} mm，"
                    f"長度 {new_len:.4f} mm"
                )
            else:
                pitch = self._parse_float("slot_pitch", "Slot pitch")
                new_len = compute_leakage_safe_substrate_length_slot(
                    pitch_mm=pitch,
                    slot_length_mm=length,
                    slot_count=count,
                    margin_factor=factor,
                )
                margin = factor * (pitch - length)
                status = (
                    f"基板 X 已對齊：Slot {count} 個不變 | "
                    f"端面至 Slot 邊緣 = {factor:g}×(pitch−L) = {margin:.4f} mm，"
                    f"長度 {new_len:.4f} mm"
                )
            self._updating_fields = True
            self._vars["siw_length"].set(f"{new_len:.4f}")
            self._updating_fields = False
            self._apply_defaults(update_fields=False)
            self._refresh_preview()
            self._status.set(status)
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")

    def _on_primary_change(self, *_args: object) -> None:
        self._apply_defaults(update_fields=True, include_siw_width=False)
        self._refresh_preview()

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
        self._schedule_preview()

    def _on_secondary_change(self, *_args: object) -> None:
        if self._updating_fields:
            return
        self._update_port_hint()
        self._schedule_preview()

    def _on_param_change(self, *_args: object) -> None:
        if self._updating_fields:
            return
        self._update_port_hint()
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(120, self._run_scheduled)
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

    def _run_scheduled(self) -> None:
        self._preview_job = None
        self._refresh_preview()

    def _build_geometry(self) -> None:
        self._geometry = build_slot_siw_geometry(self._draft_params())

    def _refresh_preview(self) -> None:
        try:
            xy_limits = saved_limits(self._figure_xy, self._xy_view_state["custom"])
            yz_limits = saved_limits(self._figure_yz, self._yz_view_state["custom"])
            self._build_geometry()
            assert self._geometry is not None
            render_preview(self._geometry, self._figure_xy)
            render_preview_yz(self._geometry, self._figure_yz)
            restore_limits(self._figure_xy, xy_limits)
            restore_limits(self._figure_yz, yz_limits)
            self._apply_defaults(update_fields=False)
            g = self._geometry
            clip = f"（截掉 {g.via_count_requested - g.via_count}）" if g.via_count_clipped else ""
            self._status.set(
                f"預覽 OK | w={g.siw_width_mm:.4f} mm | Slot {g.via_count}{clip}"
            )
            if self._overlay_circular is not None:
                self._overlay_circular.refresh_overlay_if_enabled()
            self._canvas_xy.draw_idle()
            self._canvas_yz.draw_idle()
        except ValueError as exc:
            self._status.set(f"錯誤：{exc}")
        except Exception as exc:  # noqa: BLE001
            self._status.set(f"錯誤：{exc}")

    def _reset_xy_view(self) -> None:
        self._xy_view_state["custom"] = False
        self._refresh_preview()

    def _reset_yz_view(self) -> None:
        self._yz_view_state["custom"] = False
        self._refresh_preview()

    def _export_cst(self, *, clear_existing: bool = True) -> None:
        try:
            self._build_geometry()
            assert self._geometry is not None
            p = self._geometry.slot_params
            assert p is not None
            name = sanitize_design_name(self._vars["design_name"].get())
            result = generate_slot_siw_cst(
                project_root=PROJECT_ROOT,
                design_name=name,
                substrate_length_mm=p.substrate_length_mm,
                substrate_width_mm=p.substrate_width_mm,
                substrate_height_mm=p.stackup.substrate_height_mm,
                center_freq_ghz=p.center_freq_ghz,
                slot_width_mm=p.slot_width_mm,
                slot_length_mm=p.slot_length_mm,
                slot_corner_r_mm=p.slot_corner_r_mm,
                slot_pitch_mm=p.slot_pitch_mm,
                siw_width_mm=p.siw_width_mm,
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
                f"已輸出至：\n{folder}\n\nSlot 數量：{result['via_count']}\n含 DXF / STL / VBA / siw_params.txt",
            )
            self._status.set(f"已輸出至 {folder}")
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("輸出失敗", str(exc))

    def _export_custom_module(self) -> None:
        from siw_generator.custom_io import KIND_SSIW, save_geometry_module_with_confirm
        from siw_generator.operation_log import log_operation

        try:
            self._build_geometry()
            assert self._geometry is not None
            title = self.design_name()
            path = save_geometry_module_with_confirm(
                self,
                self._geometry,
                kind=KIND_SSIW,
                title=title,
            )
            if path is None:
                return
            log_operation("module", "匯出模組", path.name)
            messagebox.showinfo(
                "匯出完成",
                f"已匯出至：\n{path}\n\nSlot {self._geometry.via_count} 個（不含 Port）",
            )
            self._status.set(f"已匯出 {path.name}")
            if self._module_panel is not None:
                self._module_panel.refresh_list()
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc))
        except OSError as exc:
            messagebox.showerror("匯出失敗", str(exc))

    def _apply_imported_module(self, module, path: Path) -> None:
        from siw_generator.custom_io import KIND_SSIW, material_display_for_key, module_stem_without_prefix
        from siw_generator.operation_log import log_operation

        self._updating_fields = True
        try:
            self._vars["design_name"].set(module_stem_without_prefix(path.name, KIND_SSIW))
            self._vars["freq_ghz"].set(f"{module.center_freq_ghz:.4f}")
            self._vars["siw_length"].set(f"{module.substrate_length_mm:.4f}")
            self._vars["substrate_width"].set(f"{module.substrate_width_mm:.4f}")
            self._vars["substrate_height"].set(f"{module.stackup.substrate_height_mm:.4f}")
            self._vars["copper_thickness_um"].set(f"{module.stackup.copper_thickness_um:.0f}")
            self._vars["substrate_material"].set(material_display_for_key(module.material))
            if module.siw_width_mm is not None:
                self._vars["siw_width"].set(f"{module.siw_width_mm:.4f}")
            if module.slot_width_mm is not None:
                self._vars["slot_width"].set(f"{module.slot_width_mm:.4f}")
            if module.slot_length_mm is not None:
                self._vars["slot_length"].set(f"{module.slot_length_mm:.4f}")
            if module.slot_corner_r_mm is not None:
                self._vars["slot_corner_r"].set(f"{module.slot_corner_r_mm:.4f}")
            if module.slot_pitch_mm is not None:
                self._vars["slot_pitch"].set(f"{module.slot_pitch_mm:.4f}")
            if module.vias:
                self._vars["slot_count"].set(str(len(module.vias)))
        finally:
            self._updating_fields = False

        self._update_material_info()
        self._apply_defaults(
            update_fields=True,
            include_siw_width=False,
            include_port_factors=True,
        )
        self._refresh_preview()
        log_operation("module", "匯入模組", path.name)
        self._status.set(f"已匯入 {path.name}")

    def on_tab_show(self) -> None:
        if self._module_panel is not None:
            self._module_panel.refresh_list()

    def current_geometry(self):
        """Return geometry for CST VBA preview/export."""
        self._build_geometry()
        if self._geometry is None:
            raise ValueError("無法建立幾何")
        return self._geometry

    def design_name(self) -> str:
        return sanitize_design_name(self._vars["design_name"].get())
