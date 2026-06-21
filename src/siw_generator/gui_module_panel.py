"""Module list / import / export panel for Via design tabs."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox, ttk

from siw_generator.app_paths import module_dir
from siw_generator.custom_geometry import CustomModuleDefinition
from siw_generator.custom_io import (
    KIND_CUSTOM,
    KIND_RSIW,
    KIND_SSIW,
    PREFIX_BY_KIND,
    list_module_files,
    load_module_file,
)
from siw_generator.operation_log import log_operation

_DELETE_BTN_BORDER = "#c62828"
_DELETE_BTN_FG = "#c62828"
_DELETE_BTN_BG = "#ffebee"
_DELETE_BTN_ACTIVE_BG = "#ffcdd2"
_DELETE_BTN_ACTIVE_FG = "#b71c1c"


def _widget_bg(widget: tk.Misc) -> str:
    try:
        bg = ttk.Style().lookup("TFrame", "background")
        if bg:
            return str(bg)
    except tk.TclError:
        pass
    try:
        return str(widget.cget("background"))
    except tk.TclError:
        return "#f0f0f0"


def make_transparent_red_button(parent: tk.Misc, *, text: str, command: Callable[[], None]) -> tk.Frame:
    """Flat red delete-style button with red outline."""
    normal_bg = _widget_bg(parent)
    border = tk.Frame(parent, bg=_DELETE_BTN_BORDER, padx=1, pady=1)
    btn = tk.Button(
        border,
        text=text,
        command=command,
        fg=_DELETE_BTN_FG,
        bg=normal_bg,
        activebackground=_DELETE_BTN_ACTIVE_BG,
        activeforeground=_DELETE_BTN_ACTIVE_FG,
        disabledforeground="#ef9a9a",
        relief=tk.FLAT,
        borderwidth=0,
        highlightthickness=0,
        padx=16,
        pady=3,
        width=6,
        cursor="hand2",
    )
    btn.pack(fill=tk.BOTH, expand=True)

    def _on_enter(_event: object) -> None:
        btn.configure(bg=_DELETE_BTN_BG)

    def _on_leave(_event: object) -> None:
        btn.configure(bg=normal_bg)

    btn.bind("<Enter>", _on_enter)
    btn.bind("<Leave>", _on_leave)
    return border

class ModuleFilePanel(ttk.LabelFrame):
    """List module/ JSON files filtered by kind prefix; import selected entry."""

    def __init__(
        self,
        parent: tk.Misc,
        *,
        kind: str,
        on_import: Callable[[CustomModuleDefinition, Path], None],
        on_export: Callable[[], None],
    ) -> None:
        super().__init__(parent, text="模組 (module/)", padding=6)
        self._kind = kind
        self._on_import = on_import
        self._on_export = on_export
        self._paths: list[Path] = []

        ttk.Label(
            self,
            text=f"前綴 {PREFIX_BY_KIND[kind]} — 目錄 {module_dir()}",
            foreground="#666",
            wraplength=220,
        ).pack(anchor="w", pady=(0, 4))

        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True)
        self._listbox = tk.Listbox(
            list_frame,
            height=6,
            exportselection=False,
            selectbackground="#0277bd",
            selectforeground="#ffffff",
            activestyle="none",
        )
        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=scroll.set)
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_row, text="匯入模組", command=self._import_selected).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="匯出模組", command=self._on_export).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_row, text="重新整理", command=self.refresh_list).pack(side=tk.LEFT, padx=(0, 4))
        make_transparent_red_button(btn_row, text="刪除", command=self._delete_selected).pack(side=tk.LEFT)
        self.refresh_list()

    def refresh_list(self) -> None:
        self._paths = list_module_files(kinds=(self._kind,))
        self._listbox.delete(0, tk.END)
        for path in self._paths:
            self._listbox.insert(tk.END, path.name)
        if not self._paths:
            self._listbox.insert(tk.END, "（尚無模組）")

    def _import_selected(self) -> None:
        if not self._paths:
            return
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showwarning("匯入模組", "請先在清單中選取模組", parent=self.winfo_toplevel())
            return
        idx = int(sel[0])
        if idx >= len(self._paths):
            return
        path = self._paths[idx]
        try:
            module = load_module_file(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("匯入失敗", str(exc), parent=self.winfo_toplevel())
            return
        expected = {KIND_CUSTOM: KIND_CUSTOM, KIND_RSIW: KIND_RSIW, KIND_SSIW: KIND_SSIW}[self._kind]
        if module.kind != expected:
            messagebox.showwarning(
                "匯入模組",
                f"檔案種類為 {module.kind}，此分頁僅支援 {PREFIX_BY_KIND[self._kind]} 模組。",
                parent=self.winfo_toplevel(),
            )
            return
        self._on_import(module, path)

    def _delete_selected(self) -> None:
        if not self._paths:
            messagebox.showwarning("刪除模組", "尚無可刪除的模組", parent=self.winfo_toplevel())
            return
        sel = self._listbox.curselection()
        if not sel:
            messagebox.showwarning("刪除模組", "請先在清單中選取模組", parent=self.winfo_toplevel())
            return
        idx = int(sel[0])
        if idx >= len(self._paths):
            return
        path = self._paths[idx]
        if not messagebox.askyesno(
            "刪除模組",
            f"確定刪除 module/ 中的\n\n{path.name}？",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            path.unlink()
        except OSError as exc:
            messagebox.showerror("刪除失敗", str(exc), parent=self.winfo_toplevel())
            return
        log_operation("module", "刪除模組", path.name)
        self.refresh_list()