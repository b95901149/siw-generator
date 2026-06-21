"""Weekly rotating operation log under log/."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from siw_generator.app_paths import log_dir

_LOG_PREFIX = "siw_generator_"


def _now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def week_key(when: datetime | None = None) -> str:
    dt = when or _now_local()
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def log_path_for_week(when: datetime | None = None) -> Path:
    folder = log_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{_LOG_PREFIX}{week_key(when)}.log"


def log_operation(category: str, action: str, detail: str = "") -> None:
    """Append one timestamped line to the current week's log file."""
    ts = _now_local().replace(microsecond=0).isoformat(sep=" ")
    line = f"[{ts}] [{category}] {action}"
    if detail:
        line = f"{line} — {detail}"
    path = log_path_for_week()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_current_log(*, tail_lines: int = 500) -> str:
    path = log_path_for_week()
    if not path.is_file():
        return "（本週尚無 log 紀錄）\n"
    lines = path.read_text(encoding="utf-8").splitlines()
    if tail_lines > 0 and len(lines) > tail_lines:
        lines = lines[-tail_lines:]
    return "\n".join(lines) + "\n"


def list_log_files() -> list[Path]:
    folder = log_dir()
    if not folder.is_dir():
        return []
    return sorted(folder.glob(f"{_LOG_PREFIX}*.log"), key=lambda p: p.name, reverse=True)
