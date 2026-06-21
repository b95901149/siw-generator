"""Save/load custom SIW modules (JSON)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from siw_generator.app_paths import module_dir
from siw_generator.custom_geometry import CustomModuleDefinition, CustomVia, CustomViaRole, CustomViaType
from siw_generator.export_paths import sanitize_module_stem
from siw_generator.siw_geometry import SIWGeometry
from siw_generator.stackup import StackupParams

MODULE_FORMAT = "siw-generator-module"
MODULE_VERSION = 1

KIND_CUSTOM = "custom"
KIND_RSIW = "rsiw"
KIND_SSIW = "ssiw"

PREFIX_BY_KIND = {
    KIND_CUSTOM: "ctm-",
    KIND_RSIW: "RSIW-",
    KIND_SSIW: "SSIW-",
}

DIR_BY_KIND = {
    KIND_CUSTOM: module_dir,
    KIND_RSIW: module_dir,
    KIND_SSIW: module_dir,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def _via_to_dict(via: CustomVia) -> dict[str, Any]:
    data: dict[str, Any] = {
        "x_mm": via.x_mm,
        "y_mm": via.y_mm,
        "type": via.via_type.value,
        "w_mm": via.w_mm,
        "h_mm": via.h_mm,
    }
    if via.via_type is CustomViaType.SLOT:
        if via.length_mm is not None:
            data["length_mm"] = via.length_mm
        if via.corner_r_mm is not None:
            data["corner_r_mm"] = via.corner_r_mm
    if via.via_role is not CustomViaRole.THROUGH:
        data["via_role"] = via.via_role.value
    return data


def _via_from_dict(data: dict[str, Any]) -> CustomVia:
    via_type = CustomViaType(data.get("type", "circle"))
    via_role = CustomViaRole(data.get("via_role", "through"))
    w = float(data.get("w_mm", 0.15))
    h = float(data.get("h_mm", w))
    return CustomVia(
        x_mm=float(data["x_mm"]),
        y_mm=float(data["y_mm"]),
        via_type=via_type,
        via_role=via_role,
        w_mm=w,
        h_mm=h,
        length_mm=float(data["length_mm"]) if "length_mm" in data else None,
        corner_r_mm=float(data["corner_r_mm"]) if "corner_r_mm" in data else None,
    )


def module_to_dict(module: CustomModuleDefinition, *, title: str = "") -> dict[str, Any]:
    stack = module.stackup
    payload: dict[str, Any] = {
        "format": MODULE_FORMAT,
        "version": MODULE_VERSION,
        "kind": module.kind,
        "saved_at": _now_iso(),
        "title": title.strip(),
        "substrate_length_mm": module.substrate_length_mm,
        "substrate_width_mm": module.substrate_width_mm,
        "substrate_height_mm": stack.substrate_height_mm,
        "copper_thickness_um": stack.copper_thickness_um,
        "material": module.material,
        "center_freq_ghz": module.center_freq_ghz,
        "vias": [_via_to_dict(v) for v in module.vias],
    }
    if module.siw_width_mm is not None:
        payload["siw_width_mm"] = module.siw_width_mm
    if module.via_diameter_mm is not None:
        payload["via_diameter_mm"] = module.via_diameter_mm
    if module.via_pitch_mm is not None:
        payload["via_pitch_mm"] = module.via_pitch_mm
    if module.slot_width_mm is not None:
        payload["slot_width_mm"] = module.slot_width_mm
    if module.slot_length_mm is not None:
        payload["slot_length_mm"] = module.slot_length_mm
    if module.slot_corner_r_mm is not None:
        payload["slot_corner_r_mm"] = module.slot_corner_r_mm
    if module.slot_pitch_mm is not None:
        payload["slot_pitch_mm"] = module.slot_pitch_mm
    return payload


def module_from_dict(data: dict[str, Any]) -> CustomModuleDefinition:
    if data.get("format") != MODULE_FORMAT:
        raise ValueError(f"不支援的模組格式：{data.get('format')}")
    stack = StackupParams(
        substrate_height_mm=float(data.get("substrate_height_mm", 0.127)),
        copper_thickness_mm=float(data.get("copper_thickness_um", 15.0)) / 1000.0,
    )
    return CustomModuleDefinition(
        substrate_length_mm=float(data.get("substrate_length_mm", 10.0)),
        substrate_width_mm=float(data.get("substrate_width_mm", 10.0)),
        stackup=stack,
        material=str(data.get("material", "rt5880_lossy")),
        center_freq_ghz=float(data.get("center_freq_ghz", 120.0)),
        siw_width_mm=float(data["siw_width_mm"]) if "siw_width_mm" in data else None,
        via_diameter_mm=float(data["via_diameter_mm"]) if "via_diameter_mm" in data else None,
        via_pitch_mm=float(data["via_pitch_mm"]) if "via_pitch_mm" in data else None,
        slot_width_mm=float(data["slot_width_mm"]) if "slot_width_mm" in data else None,
        slot_length_mm=float(data["slot_length_mm"]) if "slot_length_mm" in data else None,
        slot_corner_r_mm=float(data["slot_corner_r_mm"]) if "slot_corner_r_mm" in data else None,
        slot_pitch_mm=float(data["slot_pitch_mm"]) if "slot_pitch_mm" in data else None,
        vias=[_via_from_dict(v) for v in data.get("vias", [])],
        kind=str(data.get("kind", KIND_CUSTOM)),
    )


def module_stem_without_prefix(name: str, kind: str) -> str:
    """Return module title without kind prefix (e.g. RSIW-test → test)."""
    stem = Path(name).stem
    prefix = PREFIX_BY_KIND[kind]
    if stem.lower().startswith(prefix.lower()):
        return stem[len(prefix) :]
    return stem


def material_display_for_key(material_key: str) -> str:
    from siw_generator.materials import SUBSTRATE_MATERIALS, default_substrate_display_name

    mat = SUBSTRATE_MATERIALS.get(material_key.strip())
    if mat is not None:
        return mat.cst_material_name
    return default_substrate_display_name()


def module_path(kind: str, title: str) -> Path:
    prefix = PREFIX_BY_KIND[kind]
    folder = DIR_BY_KIND[kind]()
    stem = sanitize_module_stem(title, prefix)
    return folder / f"{stem}.json"


def list_module_files(*, kinds: tuple[str, ...] | None = None) -> list[Path]:
    kinds = kinds or (KIND_CUSTOM, KIND_RSIW, KIND_SSIW)
    folder = module_dir()
    if not folder.is_dir():
        return []
    paths: list[Path] = []
    if KIND_CUSTOM in kinds:
        paths.extend(folder.glob("ctm-*.json"))
    if KIND_RSIW in kinds:
        paths.extend(folder.glob(f"{PREFIX_BY_KIND[KIND_RSIW]}*.json"))
    if KIND_SSIW in kinds:
        paths.extend(folder.glob(f"{PREFIX_BY_KIND[KIND_SSIW]}*.json"))
    return sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)


def save_module_file(
    module: CustomModuleDefinition,
    path: str | Path,
    *,
    title: str = "",
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = module_to_dict(module, title=title or output.stem)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def load_module_file(path: str | Path) -> CustomModuleDefinition:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return module_from_dict(data)


def build_module_from_geometry(geometry: SIWGeometry, *, kind: str) -> CustomModuleDefinition:
    p = geometry.params
    stack = p.stackup
    vias: list[CustomVia] = []
    if geometry.is_slot:
        for slot in geometry.slot_vias:
            vias.append(
                CustomVia(
                    x_mm=slot.x_mm,
                    y_mm=slot.y_mm,
                    via_type=CustomViaType.SLOT,
                    w_mm=slot.width_mm,
                    h_mm=slot.width_mm,
                    length_mm=slot.length_mm,
                    corner_r_mm=slot.corner_r_mm,
                )
            )
        sp = geometry.slot_params
        return CustomModuleDefinition(
            substrate_length_mm=p.substrate_length_mm,
            substrate_width_mm=p.substrate_width_mm,
            stackup=stack,
            material=p.material,
            center_freq_ghz=p.center_freq_ghz,
            siw_width_mm=geometry.siw_width_mm,
            slot_width_mm=sp.slot_width_mm if sp else None,
            slot_length_mm=sp.slot_length_mm if sp else None,
            slot_corner_r_mm=sp.slot_corner_r_mm if sp else None,
            slot_pitch_mm=sp.slot_pitch_mm if sp else None,
            vias=vias,
            kind=kind,
        )

    for via in geometry.vias:
        vias.append(
            CustomVia(
                x_mm=via.x_mm,
                y_mm=via.y_mm,
                via_type=CustomViaType.CIRCLE,
                w_mm=via.diameter_mm,
                h_mm=via.diameter_mm,
            )
        )
    return CustomModuleDefinition(
        substrate_length_mm=p.substrate_length_mm,
        substrate_width_mm=p.substrate_width_mm,
        stackup=stack,
        material=p.material,
        center_freq_ghz=p.center_freq_ghz,
        siw_width_mm=geometry.siw_width_mm,
        via_diameter_mm=p.via_diameter_mm,
        via_pitch_mm=geometry.via_pitch_mm,
        vias=vias,
        kind=kind,
    )


def export_geometry_module(geometry: SIWGeometry, *, kind: str, title: str) -> Path:
    module = build_module_from_geometry(geometry, kind=kind)
    path = module_path(kind, title)
    return save_module_file(module, path, title=path.stem)


def save_geometry_module_with_confirm(
    parent,
    geometry: SIWGeometry,
    *,
    kind: str,
    title: str,
) -> Path | None:
    """Save SIW geometry as module JSON; ask before overwrite."""
    from tkinter import messagebox

    if not title.strip():
        messagebox.showwarning("匯出模組", "請輸入模組標題", parent=parent)
        return None
    path = module_path(kind, title)
    if path.exists() and not messagebox.askyesno(
        "覆蓋確認",
        f"{path.name} 已存在，是否覆蓋？",
        parent=parent,
    ):
        return None
    return export_geometry_module(geometry, kind=kind, title=title)
