"""Application paths (source checkout vs PyInstaller executable)."""

from __future__ import annotations

import sys
from pathlib import Path


def app_project_root() -> Path:
    """Directory for CST output: folder containing the .exe, or repo root in dev."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def recipe_dir() -> Path:
    """Directory for saved recipes and last-session state."""
    path = app_project_root() / "recipe"
    path.mkdir(parents=True, exist_ok=True)
    return path


def module_dir() -> Path:
    """Directory for module JSON (ctm- / RSIW- / SSIW-)."""
    path = app_project_root() / "module"
    path.mkdir(parents=True, exist_ok=True)
    return path


def combination_dir() -> Path:
    """Directory for saved combination JSON files."""
    path = app_project_root() / "combination"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    """Directory for weekly operation logs."""
    path = app_project_root() / "log"
    path.mkdir(parents=True, exist_ok=True)
    return path
