"""CST VBA preview tab."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from siw_generator.app_paths import app_project_root
from siw_generator.compose_cst_export import build_compose_cst_vba_text, export_compose_cst_package
from siw_generator.cst_export import build_cst_vba_text
from siw_generator.export_paths import make_cst_output_dir
from siw_generator.siw_geometry import SIWGeometry


class CSTVbaPanel(ttk.Frame):
    """Show generated CST VBA macro for the active design panel."""

    _SOURCE_COMPOSE = "當前組合"
    _SOURCE_CIRCULAR = "圓形 Via"
    _SOURCE_SLOT = "Slot Via"

    def __init__(
        self,
        parent: tk.Misc,
        *,
        circular_panel,
        slot_panel,
        compose_panel=None,
    ) -> None:
        super().__init__(parent)
        self._circular_panel = circular_panel
        self._slot_panel = slot_panel
        self._compose_panel = compose_panel
        self._source = tk.StringVar(value=self._SOURCE_COMPOSE)
        self._parametric = True
        self._clear_existing = tk.BooleanVar(value=True)
        self._status = tk.StringVar(value="切換至此分頁或按輸出按鈕以顯示 VBA")

        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="來源設計").pack(side=tk.LEFT)
        source_box = ttk.Combobox(
            toolbar,
            textvariable=self._source,
            values=(self._SOURCE_COMPOSE, self._SOURCE_CIRCULAR, self._SOURCE_SLOT),
            state="readonly",
            width=16,
        )
        source_box.pack(side=tk.LEFT, padx=(8, 16))
        source_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Checkbutton(
            toolbar,
            text="清除現有 component 與 port",
            variable=self._clear_existing,
            command=self.refresh,
        ).pack(side=tk.LEFT, padx=(0, 16))

        ttk.Button(
            toolbar,
            text="參數化 VBA (History+Rebuild)",
            command=lambda: self.refresh(parametric=True),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            toolbar,
            text="參數化 VBA (重跑巨集)",
            command=lambda: self.refresh(parametric=False),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="輸出 CST 套件", command=self._export_cst_package).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="複製全部", command=self._copy_all).pack(side=tk.LEFT)

        text_frame = ttk.Frame(self, padding=(8, 0, 8, 8))
        text_frame.pack(fill=tk.BOTH, expand=True)

        self._text = tk.Text(
            text_frame,
            wrap=tk.NONE,
            font=("Consolas", 10),
            undo=False,
        )
        y_scroll = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self._text.yview)
        x_scroll = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=self._text.xview)
        self._text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self._text.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        ttk.Label(self, textvariable=self._status, foreground="#444", padding=(8, 0, 8, 8)).pack(
            anchor="w"
        )

    def _is_compose_source(self) -> bool:
        return self._source.get().strip() == self._SOURCE_COMPOSE

    @property
    def clear_existing(self) -> bool:
        return bool(self._clear_existing.get())

    def _geometry_from_source(self) -> SIWGeometry:
        label = self._source.get().strip()
        if label == self._SOURCE_SLOT:
            return self._slot_panel.current_geometry()
        if label == self._SOURCE_COMPOSE:
            raise ValueError("當前組合請使用 compose CST 匯出")
        return self._circular_panel.current_geometry()

    def refresh(self, *, parametric: bool | None = None) -> None:
        if parametric is not None:
            self._parametric = parametric
        try:
            if self._is_compose_source():
                if self._compose_panel is None:
                    raise ValueError("組合面板未就緒")
                layout = self._compose_panel.current_layout()
                title = self._compose_panel.combination_design_name()
                vba = build_compose_cst_vba_text(
                    layout,
                    title=title,
                    clear_existing=self.clear_existing,
                )
                summary = (
                    f"組合 layout (重跑巨集) | module {len(layout.placements)} | "
                    f"fill {len(layout.filled_cells)} | Port {len(layout.ports)}"
                )
            else:
                geometry = self._geometry_from_source()
                vba = build_cst_vba_text(
                    geometry,
                    parametric=self._parametric,
                    clear_existing=self.clear_existing,
                )
                mode = "Slot" if geometry.is_slot else "圓形"
                vba_kind = "參數化 (History+Rebuild)" if self._parametric else "參數化 (重跑巨集)"
                summary = f"{mode} Via | {vba_kind} | Via {geometry.via_count} 個"
        except ValueError as exc:
            self._set_text("")
            self._status.set(f"錯誤：{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self._set_text("")
            self._status.set(f"錯誤：{exc}")
            return

        self._set_text(vba)
        self._status.set(f"{summary} | {len(vba.splitlines())} 行 | 可直接貼至 CST Macro Editor")

    def _export_cst_package(self) -> None:
        try:
            if self._is_compose_source():
                if self._compose_panel is None:
                    raise ValueError("組合面板未就緒")
                layout = self._compose_panel.current_layout()
                name = self._compose_panel.combination_design_name()
                if not layout.placements and not layout.filled_cells and not layout.ports:
                    raise ValueError("組合為空，請先放置 module 或填補基板")
                out = make_cst_output_dir(app_project_root(), name)
                export_compose_cst_package(
                    layout,
                    out,
                    design_name=name,
                    clear_existing=self.clear_existing,
                )
                messagebox.showinfo(
                    "輸出完成",
                    f"已輸出至：\n{out}\n\n"
                    f"組合名稱：{name}\n"
                    f"module {len(layout.placements)} | Port {len(layout.ports)}\n"
                    f"含 DXF / STL / VBA / compose_params.txt",
                )
                self._status.set(f"已輸出組合 CST 至 {out}")
                self.refresh()
                return
            label = self._source.get().strip()
            if label == self._SOURCE_SLOT:
                self._slot_panel._export_cst(clear_existing=self.clear_existing)
            else:
                self._circular_panel._export_cst(clear_existing=self.clear_existing)
        except ValueError as exc:
            messagebox.showerror("參數錯誤", str(exc))
            self._status.set(f"錯誤：{exc}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("輸出失敗", str(exc))
            self._status.set(f"錯誤：{exc}")

    def convert(self) -> None:
        """Alias used when switching notebook tabs."""
        self.refresh()

    def _set_text(self, content: str) -> None:
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        if content:
            self._text.insert("1.0", content)
        self._text.configure(state=tk.DISABLED)

    def _copy_all(self) -> None:
        content = self._text.get("1.0", tk.END).strip()
        if not content:
            self.refresh()
            content = self._text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("複製", "目前沒有可複製的 VBA 內容")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self._status.set("已複製 VBA 至剪貼簿")
