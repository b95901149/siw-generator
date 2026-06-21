"""HFSS VBScript preview tab."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from siw_generator.hfss_export import build_hfss_script_text
from siw_generator.siw_geometry import SIWGeometry


class HfssScriptPanel(ttk.Frame):
    """Show generated HFSS VBScript macro for the active design panel."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        circular_panel,
        slot_panel,
    ) -> None:
        super().__init__(parent)
        self._circular_panel = circular_panel
        self._slot_panel = slot_panel
        self._source = tk.StringVar(value="圓形 Via")
        self._status = tk.StringVar(value="切換至此分頁或按重新產生以顯示 HFSS 巨集")

        self._build_ui()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="來源設計").pack(side=tk.LEFT)
        source_box = ttk.Combobox(
            toolbar,
            textvariable=self._source,
            values=("圓形 Via", "Slot Via"),
            state="readonly",
            width=16,
        )
        source_box.pack(side=tk.LEFT, padx=(8, 16))
        source_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        ttk.Button(toolbar, text="重新產生", command=self.refresh).pack(side=tk.LEFT, padx=(0, 8))
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

    def _geometry_from_source(self) -> SIWGeometry:
        label = self._source.get().strip()
        if label == "Slot Via":
            return self._slot_panel.current_geometry()
        return self._circular_panel.current_geometry()

    def refresh(self) -> None:
        try:
            geometry = self._geometry_from_source()
            script = build_hfss_script_text(geometry)
        except ValueError as exc:
            self._set_text("")
            self._status.set(f"錯誤：{exc}")
            return
        except Exception as exc:  # noqa: BLE001
            self._set_text("")
            self._status.set(f"錯誤：{exc}")
            return

        self._set_text(script)
        mode = "Slot" if geometry.is_slot else "圓形"
        self._status.set(
            f"{mode} Via | HFSS VBScript | Via {geometry.via_count} 個 | "
            f"{len(script.splitlines())} 行 | Tools > Run Script 或儲存為 .vbs"
        )

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
            messagebox.showwarning("複製", "目前沒有可複製的 HFSS 巨集內容")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self._status.set("已複製 HFSS 巨集至剪貼簿")
