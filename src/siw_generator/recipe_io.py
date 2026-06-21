"""Recipe and session persistence under recipe/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from siw_generator.app_paths import recipe_dir
from siw_generator.export_paths import resolve_recipe_stem

RECIPE_FORMAT = "siw-generator-recipe"
RECIPE_VERSION = 1
SESSION_FILENAME = "_last_session.json"


def session_path() -> Path:
    return recipe_dir() / SESSION_FILENAME


def recipe_path(stem: str) -> Path:
    safe = resolve_recipe_stem(stem)
    return recipe_dir() / f"{safe}.json"


def list_recipe_files() -> list[Path]:
    folder = recipe_dir()
    if not folder.is_dir():
        return []
    return sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def build_recipe_payload(
    *,
    recipe_name: str,
    active_tab: str,
    circular: dict[str, Any],
    slot: dict[str, Any],
    compose: dict[str, Any] | None = None,
    ui_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "format": RECIPE_FORMAT,
        "version": RECIPE_VERSION,
        "saved_at": _now_iso(),
        "recipe_name": str(recipe_name).strip(),
        "active_tab": active_tab,
        "circular": circular,
        "slot": slot,
    }
    if compose is not None:
        payload["compose"] = compose
    if ui_state:
        payload["ui_state"] = ui_state
    return payload


def save_recipe_file(
    path: Path,
    *,
    recipe_name: str,
    active_tab: str,
    circular: dict[str, Any],
    slot: dict[str, Any],
    compose: dict[str, Any] | None = None,
    ui_state: dict[str, Any] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_recipe_payload(
        recipe_name=recipe_name,
        active_tab=active_tab,
        circular=circular,
        slot=slot,
        compose=compose,
        ui_state=ui_state,
    )
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def save_session(
    *,
    recipe_name: str,
    active_tab: str,
    circular: dict[str, Any],
    slot: dict[str, Any],
    compose: dict[str, Any] | None = None,
    ui_state: dict[str, Any] | None = None,
) -> Path:
    return save_recipe_file(
        session_path(),
        recipe_name=recipe_name,
        active_tab=active_tab,
        circular=circular,
        slot=slot,
        compose=compose,
        ui_state=ui_state,
    )


def load_recipe_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != RECIPE_FORMAT:
        raise ValueError(f"不支援的 recipe 格式：{path.name}")
    return data


def load_session() -> dict[str, Any] | None:
    path = session_path()
    if not path.is_file():
        return None
    try:
        return load_recipe_file(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
