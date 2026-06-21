"""Ensure UTF-8 console output (especially on Windows cp950 terminals)."""

from __future__ import annotations

import sys


def configure_console_encoding() -> None:
    """Reconfigure stdout/stderr to UTF-8 and set Windows console code page when possible."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError, ValueError):
                pass

    if sys.platform != "win32":
        return

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:  # noqa: BLE001
        pass
