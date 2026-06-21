"""CST output directory naming."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def sanitize_design_name(name: str) -> str:
    text = name.strip()
    if not text:
        return "SIW"
    safe = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE)
    return safe.strip("_") or "SIW"


def default_recipe_stem() -> str:
    """Default recipe filename stem when name field is blank."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_SIW"


def resolve_recipe_stem(name: str) -> str:
    text = name.strip()
    if not text:
        return default_recipe_stem()
    safe = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE)
    return safe.strip("_") or default_recipe_stem()


def sanitize_module_stem(name: str, prefix: str) -> str:
    """Sanitize module title and ensure required prefix (e.g. ctm-, RSIW-)."""
    text = name.strip()
    if not text:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        text = f"{stamp}"
    safe = re.sub(r"[^\w\-]+", "_", text, flags=re.UNICODE)
    safe = safe.strip("_") or datetime.now().strftime("%Y%m%d_%H%M%S")
    if not safe.lower().startswith(prefix.lower()):
        safe = f"{prefix}{safe}"
    return safe


def make_cst_output_dir(project_root: str | Path, design_name: str = "SIW") -> Path:
    """Create CST/{YYYYMMDD_HHMMSS_name}/ under project root."""
    root = Path(project_root)
    safe_name = sanitize_design_name(design_name)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = root / "CST" / f"{stamp}_{safe_name}"
    out.mkdir(parents=True, exist_ok=True)
    return out
