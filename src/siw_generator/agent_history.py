"""Parse and render agent history documentation."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from siw_generator.app_paths import app_project_root
from siw_generator.resource_info import (
    format_duration,
    format_resource_line,
    parse_timestamp,
    snapshot_resources,
)


@dataclass
class HistoryEntry:
    index: int
    title: str
    timestamp: str
    command: str
    summary_lines: list[str] = field(default_factory=list)


def agent_history_path() -> Path:
    if getattr(sys, "frozen", False):
        beside = Path(sys.executable).resolve().parent / "docs" / "AGENT_HISTORY.md"
        if beside.is_file():
            return beside
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        bundled = meipass / "docs" / "AGENT_HISTORY.md"
        if bundled.is_file():
            return bundled
    return app_project_root() / "docs" / "AGENT_HISTORY.md"


def usage_guide_path() -> Path:
    if getattr(sys, "frozen", False):
        beside = Path(sys.executable).resolve().parent / "docs" / "USER_GUIDE.md"
        if beside.is_file():
            return beside
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        bundled = meipass / "docs" / "USER_GUIDE.md"
        if bundled.is_file():
            return bundled
    return app_project_root() / "docs" / "USER_GUIDE.md"


def load_agent_history_text() -> str:
    path = agent_history_path()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "找不到 docs/AGENT_HISTORY.md"


def load_usage_guide_text() -> str:
    path = usage_guide_path()
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "找不到 docs/USER_GUIDE.md"


def parse_agent_history(text: str) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []
    blocks = re.split(r"\n---+\n", text)
    for block in blocks:
        block = block.strip()
        if not block.startswith("## "):
            continue
        lines = block.splitlines()
        header = lines[0]
        m = re.match(r"##\s+(\d+)\.\s*(.+)", header)
        if not m:
            continue
        idx = int(m.group(1))
        title = m.group(2).strip()
        timestamp = ""
        command_lines: list[str] = []
        summary_lines: list[str] = []
        section: str | None = None
        for line in lines[1:]:
            ts = re.match(r"^`(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})`$", line.strip())
            if ts:
                timestamp = ts.group(1)
                continue
            if line.strip() == "### 指令":
                section = "command"
                continue
            if line.strip() == "### 實作摘要":
                section = "summary"
                continue
            if line.startswith("## "):
                break
            if section == "command":
                if line.startswith(">"):
                    command_lines.append(line.lstrip("> ").strip())
            elif section == "summary":
                if line.strip():
                    summary_lines.append(line.rstrip())
        command = " ".join(command_lines).strip()
        if command or title:
            entries.append(
                HistoryEntry(
                    index=idx,
                    title=title,
                    timestamp=timestamp,
                    command=command,
                    summary_lines=summary_lines,
                )
            )
    return entries


def _text_tag_opts(base_font_size: int = 10) -> dict[str, dict]:
    s = base_font_size
    return {
        "title": {"foreground": "#1565c0", "font": ("Microsoft JhengHei", s + 1, "bold")},
        "timestamp": {"foreground": "#757575", "font": ("Consolas", max(8, s - 1))},
        "section": {"foreground": "#00695c", "font": ("Microsoft JhengHei", s, "bold")},
        "command": {
            "foreground": "#c62828",
            "background": "#fff3e0",
            "font": ("Microsoft JhengHei", s),
            "lmargin1": 12,
            "lmargin2": 12,
            "rmargin": 12,
            "spacing1": 4,
            "spacing3": 6,
        },
        "command_prefix": {"foreground": "#e65100", "font": ("Consolas", s, "bold")},
        "body": {"foreground": "#212121", "font": ("Microsoft JhengHei", s)},
        "intro": {"foreground": "#616161", "font": ("Microsoft JhengHei", s)},
        "divider": {"foreground": "#bdbdbd"},
        "stats": {
            "foreground": "#1b5e20",
            "background": "#e8f5e9",
            "font": ("Microsoft JhengHei", s),
            "lmargin1": 8,
            "lmargin2": 8,
            "rmargin": 8,
            "spacing1": 6,
            "spacing3": 8,
        },
    }


def compute_development_stats(entries: list[HistoryEntry]) -> str:
    timestamps = [parse_timestamp(e.timestamp) for e in entries if e.timestamp]
    timestamps = [t for t in timestamps if t is not None]
    snap = snapshot_resources()
    resource_line = format_resource_line(snap)

    lines = [
        "【開發統計】",
        f"指令項目：{len(entries)} 筆",
    ]
    if timestamps:
        first = min(timestamps)
        last = max(timestamps)
        span_sec = max(0.0, (last - first).total_seconds())
        lines.append(
            f"開發跨度：{first.strftime('%Y-%m-%d %H:%M')} ~ {last.strftime('%Y-%m-%d %H:%M')} "
            f"（約 {format_duration(span_sec)}）"
        )
    lines.append(f"本程式資源：{resource_line}")
    return "\n".join(lines)


def _insert_stats_header(text_widget, entries: list[HistoryEntry]) -> None:
    text_widget.insert("end", compute_development_stats(entries) + "\n\n", "stats")


def apply_text_tags(text_widget, *, base_font_size: int = 10) -> None:
    for name, opts in _text_tag_opts(base_font_size).items():
        text_widget.tag_configure(name, **opts)


def render_history_widget(text_widget, *, commands_only: bool = False, base_font_size: int = 10) -> None:
    raw = load_agent_history_text()
    intro = ""
    if not commands_only:
        intro_match = re.split(r"\n---+\n", raw, maxsplit=1)
        if intro_match and not intro_match[0].strip().startswith("## "):
            intro = intro_match[0].strip()

    entries = parse_agent_history(raw)
    apply_text_tags(text_widget, base_font_size=base_font_size)
    text_widget.configure(state="normal")
    text_widget.delete("1.0", "end")

    if commands_only:
        _insert_stats_header(text_widget, entries)
        for e in entries:
            if e.timestamp:
                text_widget.insert("end", f"[{e.timestamp}] ", "timestamp")
            text_widget.insert("end", f"{e.index}. {e.title}\n", "title")
            text_widget.insert("end", "> ", "command_prefix")
            text_widget.insert("end", f"{e.command}\n\n", "command")
        return

    if intro:
        text_widget.insert("end", intro + "\n\n", "intro")
        text_widget.insert("end", "---\n\n", "divider")

    _insert_stats_header(text_widget, entries)

    for i, e in enumerate(entries):
        text_widget.insert("end", f"## {e.index}. {e.title}\n\n", "title")
        if e.timestamp:
            text_widget.insert("end", f"`{e.timestamp}`\n\n", "timestamp")
        text_widget.insert("end", "### 指令\n\n", "section")
        text_widget.insert("end", "> ", "command_prefix")
        text_widget.insert("end", f"{e.command}\n\n", "command")
        if e.summary_lines:
            text_widget.insert("end", "### 實作摘要\n\n", "section")
            text_widget.insert("end", "\n".join(e.summary_lines) + "\n", "body")
        if i < len(entries) - 1:
            text_widget.insert("end", "\n---\n\n", "divider")

    text_widget.configure(state="disabled")
