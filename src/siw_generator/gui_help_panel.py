"""Help / usage guide, system log, and agent history panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import scrolledtext, ttk

from siw_generator.agent_history import render_history_widget
from siw_generator.app_paths import log_dir
from siw_generator.operation_log import read_current_log
from siw_generator.usage_guide_render import render_usage_widget

_FONT_MIN = 7
_FONT_MAX = 24
_FONT_DEFAULT = 10
_CTRL_MASK = 0x0004

_NAV_ITEMS = (
    ("system", "系統"),
    ("usage", "使用說明"),
    ("history", "開發紀錄"),
)

_NAV_FONT = ("Microsoft JhengHei", 12)
_NAV_FONT_ACTIVE = ("Microsoft JhengHei", 13, "bold")
_NAV_BG = "#1b2838"
_NAV_BG_ACTIVE = "#0277bd"
_NAV_FG = "#cfd8dc"
_NAV_FG_ACTIVE = "#ffffff"


class HelpPanel(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=0)
        self._commands_only = False
        self._usage_font_size = _FONT_DEFAULT
        self._history_font_size = _FONT_DEFAULT
        self._usage_photos: list[tk.PhotoImage] = []
        self._active_page = "system"
        self._nav_buttons: dict[str, tk.Button] = {}

        shell = ttk.Frame(self, padding=4)
        shell.pack(fill=tk.BOTH, expand=True)

        body = ttk.Panedwindow(shell, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        nav_wrap = tk.Frame(body, bg=_NAV_BG, width=132)
        content_wrap = ttk.Frame(body, padding=(8, 4))
        body.add(nav_wrap, weight=0)
        body.add(content_wrap, weight=1)

        tk.Label(
            nav_wrap,
            text="SIW\nGenerator",
            bg=_NAV_BG,
            fg="#64b5f6",
            font=("Microsoft JhengHei", 11, "bold"),
            justify=tk.LEFT,
            padx=10,
            pady=12,
        ).pack(anchor="w", pady=(0, 16))

        for key, label in _NAV_ITEMS:
            btn = tk.Button(
                nav_wrap,
                text=label,
                anchor="w",
                padx=14,
                pady=10,
                relief=tk.FLAT,
                borderwidth=0,
                bg=_NAV_BG,
                fg=_NAV_FG,
                activebackground=_NAV_BG_ACTIVE,
                activeforeground=_NAV_FG_ACTIVE,
                font=_NAV_FONT,
                command=lambda k=key: self._show_page(k),
            )
            btn.pack(fill=tk.X, padx=6, pady=2)
            self._nav_buttons[key] = btn

        self._pages: dict[str, ttk.Frame] = {}
        for key, _label in _NAV_ITEMS:
            page = ttk.Frame(content_wrap, padding=4)
            self._pages[key] = page

        self._build_system_page(self._pages["system"])
        self._build_usage_page(self._pages["usage"])
        self._build_history_page(self._pages["history"])
        self._show_page("system")

    def _style_nav(self) -> None:
        for key, btn in self._nav_buttons.items():
            active = key == self._active_page
            btn.configure(
                bg=_NAV_BG_ACTIVE if active else _NAV_BG,
                fg=_NAV_FG_ACTIVE if active else _NAV_FG,
                font=_NAV_FONT_ACTIVE if active else _NAV_FONT,
            )

    def _show_page(self, key: str) -> None:
        self._active_page = key
        for page in self._pages.values():
            page.pack_forget()
        self._pages[key].pack(fill=tk.BOTH, expand=True)
        self._style_nav()
        if key == "system":
            self._reload_log()

    def _build_system_page(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(top, text="系統 Log", font=("", 13, "bold")).pack(side=tk.LEFT)
        ttk.Label(top, text=f"目錄：{log_dir()}", foreground="#666").pack(side=tk.RIGHT)
        ttk.Label(
            parent,
            text="記錄模組新增／修改／組合操作；依 ISO 週自動分割 log 檔。",
            foreground="#555",
            wraplength=640,
        ).pack(anchor="w", pady=(0, 8))

        self._log_text = scrolledtext.ScrolledText(
            parent,
            wrap=tk.WORD,
            font=("Consolas", 10),
            state=tk.DISABLED,
            height=28,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(btn_row, text="重新整理", command=self._reload_log).pack(side=tk.LEFT, padx=(0, 6))

    def _reload_log(self) -> None:
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.insert(tk.END, read_current_log())
        self._log_text.configure(state=tk.DISABLED)

    def _build_usage_page(self, parent: ttk.Frame) -> None:
        usage_top = ttk.Frame(parent)
        usage_top.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(usage_top, text="SIW Via Generator 使用說明", font=("", 12, "bold")).pack(side=tk.LEFT)
        ttk.Label(usage_top, text="Ctrl+滾輪：縮放文字", foreground="#666").pack(side=tk.RIGHT)

        self._usage = scrolledtext.ScrolledText(
            parent,
            wrap=tk.WORD,
            font=("Microsoft JhengHei", _FONT_DEFAULT),
            state=tk.DISABLED,
            height=28,
        )
        self._usage.pack(fill=tk.BOTH, expand=True)
        self._usage.bind("<Control-MouseWheel>", self._on_usage_wheel_zoom)

        usage_btn = ttk.Frame(parent)
        usage_btn.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(usage_btn, text="重新載入", command=self._reload_usage).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(usage_btn, text="重設字級", command=self._reset_usage_font).pack(side=tk.LEFT)
        self._usage_font_label = ttk.Label(usage_btn, text=f"字級 {_FONT_DEFAULT}")
        self._usage_font_label.pack(side=tk.RIGHT)
        self._reload_usage()

    def _build_history_page(self, parent: ttk.Frame) -> None:
        hist_top = ttk.Frame(parent)
        hist_top.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(hist_top, text="開發指令紀錄", font=("", 12, "bold")).pack(side=tk.LEFT)
        ttk.Label(hist_top, text="Ctrl+滾輪：縮放文字", foreground="#666").pack(side=tk.RIGHT)
        ttk.Label(
            parent,
            text="指令以橘底紅字標示；僅收錄導致功能／程式變更的使用者指令。",
            foreground="#666",
            wraplength=720,
        ).pack(anchor="w", pady=(0, 8))

        self._history = scrolledtext.ScrolledText(
            parent,
            wrap=tk.WORD,
            font=("Microsoft JhengHei", _FONT_DEFAULT),
            state=tk.DISABLED,
            height=26,
        )
        self._history.pack(fill=tk.BOTH, expand=True)
        self._history.bind("<Control-MouseWheel>", self._on_history_wheel_zoom)

        btn_row = ttk.Frame(parent)
        btn_row.pack(fill=tk.X, pady=(8, 0))
        self._toggle_btn = ttk.Button(btn_row, text="只顯示指令", command=self._toggle_view)
        self._toggle_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="重新載入", command=self._reload_history).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_row, text="重設字級", command=self._reset_history_font).pack(side=tk.LEFT)
        self._history_font_label = ttk.Label(btn_row, text=f"字級 {_FONT_DEFAULT}")
        self._history_font_label.pack(side=tk.RIGHT)
        self._reload_history()

    def _wheel_delta(self, event: tk.Event) -> int:
        if event.num == 4:
            return 1
        if event.num == 5:
            return -1
        return 1 if event.delta > 0 else -1

    def _on_usage_wheel_zoom(self, event: tk.Event) -> str:
        if not (event.state & _CTRL_MASK):
            return ""
        delta = self._wheel_delta(event)
        self._usage_font_size = min(_FONT_MAX, max(_FONT_MIN, self._usage_font_size + delta))
        self._reload_usage()
        return "break"

    def _on_history_wheel_zoom(self, event: tk.Event) -> str:
        if not (event.state & _CTRL_MASK):
            return ""
        delta = self._wheel_delta(event)
        self._history_font_size = min(_FONT_MAX, max(_FONT_MIN, self._history_font_size + delta))
        self._reload_history()
        return "break"

    def _reset_usage_font(self) -> None:
        self._usage_font_size = _FONT_DEFAULT
        self._reload_usage()

    def _reset_history_font(self) -> None:
        self._history_font_size = _FONT_DEFAULT
        self._reload_history()

    def _reload_usage(self) -> None:
        self._usage_photos = render_usage_widget(self._usage, font_size=self._usage_font_size)
        self._usage_font_label.configure(text=f"字級 {self._usage_font_size}")

    def _reload_history(self) -> None:
        render_history_widget(
            self._history,
            commands_only=self._commands_only,
            base_font_size=self._history_font_size,
        )
        self._history.configure(state=tk.DISABLED)
        self._history_font_label.configure(text=f"字級 {self._history_font_size}")

    def _toggle_view(self) -> None:
        self._commands_only = not self._commands_only
        self._toggle_btn.configure(text="顯示完整說明" if self._commands_only else "只顯示指令")
        self._reload_history()

    def refresh_system_log(self) -> None:
        if self._active_page == "system":
            self._reload_log()

    def on_tab_show(self) -> None:
        if self._active_page == "system":
            self._reload_log()
