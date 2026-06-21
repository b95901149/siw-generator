"""Process and development resource usage helpers."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ResourceSnapshot:
    memory_mb: float | None
    cpu_count: int
    process_cpu_percent: float | None


def process_memory_mb() -> float | None:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS_EX()
            counters.cb = ctypes.sizeof(counters)
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                ctypes.windll.kernel32.GetCurrentProcess(),
                ctypes.byref(counters),
                counters.cb,
            )
            if ok:
                return counters.WorkingSetSize / (1024 * 1024)
        except Exception:  # noqa: BLE001
            return None
        return None
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024.0
    except Exception:  # noqa: BLE001
        return None


def snapshot_resources() -> ResourceSnapshot:
    cpu_count = os.cpu_count() or 1
    mem = process_memory_mb()
    cpu_pct: float | None = None
    try:
        import psutil

        cpu_pct = psutil.Process().cpu_percent(interval=None)
    except Exception:  # noqa: BLE001
        cpu_pct = None
    return ResourceSnapshot(memory_mb=mem, cpu_count=cpu_count, process_cpu_percent=cpu_pct)


def format_resource_line(snap: ResourceSnapshot) -> str:
    parts: list[str] = []
    if snap.memory_mb is not None:
        parts.append(f"記憶體 {snap.memory_mb:.1f} MB")
    parts.append(f"CPU 核心 {snap.cpu_count}")
    if snap.process_cpu_percent is not None:
        parts.append(f"程序 CPU {snap.process_cpu_percent:.1f}%")
    return " | ".join(parts)


def parse_timestamp(text: str) -> datetime | None:
    text = text.strip().strip("`")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f} 秒"
    minutes = seconds / 60.0
    if minutes < 60:
        return f"{minutes:.1f} 分鐘"
    hours = minutes / 60.0
    return f"{hours:.1f} 小時"
