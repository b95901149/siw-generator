"""Shared GUI panel state export/import."""

from __future__ import annotations

import tkinter as tk
from typing import Any


def export_panel_vars(vars_map: dict[str, tk.Variable]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, var in vars_map.items():
        if isinstance(var, tk.BooleanVar):
            out[key] = bool(var.get())
        else:
            out[key] = var.get()
    return out


def apply_panel_vars(vars_map: dict[str, tk.Variable], state: dict[str, Any] | None) -> bool:
    if not state:
        return False
    for key, var in vars_map.items():
        if key not in state:
            continue
        value = state[key]
        if isinstance(var, tk.BooleanVar):
            var.set(bool(value))
        else:
            var.set(str(value))
    return True
