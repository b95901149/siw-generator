"""Render USER_GUIDE.md with images into a Tk text widget."""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path

from siw_generator.agent_history import load_usage_guide_text, usage_guide_path

_FONT = "Microsoft JhengHei"
_BASE_SIZE = 10
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def _guide_dir() -> Path:
    return usage_guide_path().parent


def _resolve_image(path_text: str) -> Path | None:
    import sys

    rel = Path(path_text.strip())
    base = _guide_dir()
    candidates = [base / rel]
    if getattr(sys, "frozen", False):
        candidates.extend(
            [
                Path(sys.executable).resolve().parent / "docs" / rel,
                Path(getattr(sys, "_MEIPASS", "")) / "docs" / rel,
            ]
        )
    for p in candidates:
        if p.is_file():
            return p
    return None


def _tag_opts(size: int) -> dict[str, dict]:
    return {
        "h1": {"font": (_FONT, size + 4, "bold"), "foreground": "#0d47a1", "spacing3": 10},
        "h2": {"font": (_FONT, size + 2, "bold"), "foreground": "#1565c0", "spacing1": 8, "spacing3": 6},
        "h3": {"font": (_FONT, size + 1, "bold"), "foreground": "#00695c", "spacing1": 6, "spacing3": 4},
        "body": {"font": (_FONT, size), "foreground": "#212121", "spacing3": 3, "lmargin1": 8, "lmargin2": 8},
        "bullet": {"font": (_FONT, size), "foreground": "#212121", "lmargin1": 20, "lmargin2": 32},
        "caption": {"font": (_FONT, max(8, size - 1), "italic"), "foreground": "#616161", "spacing3": 8},
        "code": {"font": ("Consolas", max(8, size - 1)), "foreground": "#37474f", "lmargin1": 12, "lmargin2": 12},
        "divider": {"foreground": "#bdbdbd", "spacing3": 6},
    }


def render_usage_widget(text_widget: tk.Text, *, font_size: int = _BASE_SIZE) -> list[tk.PhotoImage]:
    """Render guide markdown; return PhotoImage refs to prevent GC."""
    raw = load_usage_guide_text()
    for name, opts in _tag_opts(font_size).items():
        text_widget.tag_configure(name, **opts)
    text_widget.configure(state=tk.NORMAL)
    text_widget.delete("1.0", tk.END)
    photos: list[tk.PhotoImage] = []

    for line in raw.splitlines():
        stripped = line.strip()
        img_match = _IMAGE_RE.search(line)
        if img_match:
            alt, path_text = img_match.group(1), img_match.group(2)
            img_path = _resolve_image(path_text)
            if img_path:
                try:
                    photo = tk.PhotoImage(file=str(img_path))
                    photos.append(photo)
                    w = photo.width()
                    max_w = 680
                    if w > max_w:
                        factor = max(1, int(w / max_w) + 1)
                        photo = photo.subsample(factor, factor)
                        photos.append(photo)
                    text_widget.image_create(tk.END, image=photo)
                    text_widget.insert(tk.END, "\n", "body")
                except tk.TclError:
                    text_widget.insert(tk.END, f"[圖片無法載入: {path_text}]\n", "caption")
            else:
                text_widget.insert(tk.END, f"[找不到圖片: {path_text}]\n", "caption")
            if alt:
                text_widget.insert(tk.END, f"{alt}\n", "caption")
            continue

        if stripped.startswith("# "):
            text_widget.insert(tk.END, stripped[2:] + "\n", "h1")
        elif stripped.startswith("## "):
            text_widget.insert(tk.END, stripped[3:] + "\n", "h2")
        elif stripped.startswith("### "):
            text_widget.insert(tk.END, stripped[4:] + "\n", "h3")
        elif stripped == "---":
            text_widget.insert(tk.END, "─" * 40 + "\n", "divider")
        elif stripped.startswith("- "):
            text_widget.insert(tk.END, "• " + stripped[2:] + "\n", "bullet")
        elif stripped.startswith("|") and stripped.endswith("|"):
            text_widget.insert(tk.END, stripped + "\n", "code")
        elif stripped.startswith("```"):
            continue
        elif stripped:
            text_widget.insert(tk.END, stripped + "\n", "body")
        else:
            text_widget.insert(tk.END, "\n", "body")

    text_widget.configure(state=tk.DISABLED)
    return photos
