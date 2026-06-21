"""Core SIW generation logic."""

from __future__ import annotations

from pathlib import Path

from siw_generator.cst_export import export_cst_package
from siw_generator.dxf_export import export_siw_dxf
from siw_generator.materials import DEFAULT_SUBSTRATE_KEY
from siw_generator.siw_geometry import (
    SIWGeometry,
    SIWParams,
    build_siw_geometry,
    compute_leakage_safe_substrate_length_circular,
    default_port_height_factor,
    default_port_width_factor,
)
from siw_generator.slot_geometry import SlotSIWParams, build_slot_siw_geometry
from siw_generator.stackup import StackupParams


def _build_params(
    *,
    substrate_length_mm: float,
    substrate_width_mm: float,
    center_freq_ghz: float,
    via_diameter_mm: float,
    material: str,
    er: float | None,
    substrate_height_mm: float,
    copper_thickness_um: float,
    edge_margin_mm: float,
    siw_width_mm: float | None,
    via_pitch_mm: float | None,
    via_count_target: int | None = None,
    port1_x_mm: float | None = None,
    port2_x_mm: float | None = None,
    port1_enabled: bool = True,
    port2_enabled: bool = True,
    port_height_factor: float | None = None,
    port_width_factor: float | None = None,
) -> SIWParams:
    stackup = StackupParams(
        substrate_height_mm=substrate_height_mm,
        copper_thickness_mm=copper_thickness_um / 1000.0,
    )
    port_h = (
        port_height_factor
        if port_height_factor is not None
        else default_port_height_factor(stackup)
    )
    port_w = (
        port_width_factor
        if port_width_factor is not None
        else default_port_width_factor()
    )
    return SIWParams(
        substrate_length_mm=substrate_length_mm,
        substrate_width_mm=substrate_width_mm,
        center_freq_ghz=center_freq_ghz,
        via_diameter_mm=via_diameter_mm,
        material=material,
        er=er,
        stackup=stackup,
        edge_margin_mm=edge_margin_mm,
        siw_width_mm=siw_width_mm,
        via_pitch_mm=via_pitch_mm,
        via_count_target=via_count_target,
        port1_x_mm=port1_x_mm,
        port2_x_mm=port2_x_mm,
        port1_enabled=port1_enabled,
        port2_enabled=port2_enabled,
        port_height_factor=port_h,
        port_width_factor=port_w,
    )


def generate_siw_dxf(
    output_path: str | Path,
    *,
    substrate_length_mm: float = 10.0,
    substrate_width_mm: float = 10.0,
    center_freq_ghz: float = 120.0,
    via_diameter_mm: float = 0.15,
    material: str = DEFAULT_SUBSTRATE_KEY,
    er: float | None = None,
    substrate_height_mm: float = 0.127,
    copper_thickness_um: float = 15.0,
    edge_margin_mm: float = 0.0,
    siw_width_mm: float | None = None,
    via_pitch_mm: float | None = None,
    cst_mode: bool = False,
) -> dict:
    """Generate an SIW sidewall via pattern and export it as DXF."""
    params = _build_params(
        substrate_length_mm=substrate_length_mm,
        substrate_width_mm=substrate_width_mm,
        center_freq_ghz=center_freq_ghz,
        via_diameter_mm=via_diameter_mm,
        material=material,
        er=er,
        substrate_height_mm=substrate_height_mm,
        copper_thickness_um=copper_thickness_um,
        edge_margin_mm=edge_margin_mm,
        siw_width_mm=siw_width_mm,
        via_pitch_mm=via_pitch_mm,
    )
    geometry = build_siw_geometry(params)
    saved_path = export_siw_dxf(geometry, output_path, cst_mode=cst_mode)
    return summarize_geometry(geometry, saved_path)


def generate_siw_cst(
    output_dir: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
    design_name: str = "SIW",
    **kwargs: object,
) -> dict:
    """Generate a CST import package (STEP, DXF, VBA macro, notes, params txt)."""
    from siw_generator.export_paths import make_cst_output_dir

    params = _build_params(
        substrate_length_mm=float(kwargs.get("substrate_length_mm", 10.0)),
        substrate_width_mm=float(kwargs.get("substrate_width_mm", 10.0)),
        center_freq_ghz=float(kwargs.get("center_freq_ghz", 120.0)),
        via_diameter_mm=float(kwargs.get("via_diameter_mm", 0.15)),
        material=str(kwargs.get("material", DEFAULT_SUBSTRATE_KEY)),
        er=kwargs.get("er"),  # type: ignore[arg-type]
        substrate_height_mm=float(kwargs.get("substrate_height_mm", 0.127)),
        copper_thickness_um=float(kwargs.get("copper_thickness_um", 15.0)),
        edge_margin_mm=float(kwargs.get("edge_margin_mm", 0.0)),
        siw_width_mm=kwargs.get("siw_width_mm"),  # type: ignore[arg-type]
        via_pitch_mm=kwargs.get("via_pitch_mm"),  # type: ignore[arg-type]
        via_count_target=kwargs.get("via_count_target"),  # type: ignore[arg-type]
        port1_x_mm=kwargs.get("port1_x_mm"),  # type: ignore[arg-type]
        port2_x_mm=kwargs.get("port2_x_mm"),  # type: ignore[arg-type]
        port1_enabled=bool(kwargs.get("port1_enabled", True)),
        port2_enabled=bool(kwargs.get("port2_enabled", True)),
        port_height_factor=kwargs.get("port_height_factor"),  # type: ignore[arg-type]
        port_width_factor=kwargs.get("port_width_factor"),  # type: ignore[arg-type]
    )
    geometry = build_siw_geometry(params)
    clear_existing = bool(kwargs.get("clear_existing", True))

    if output_dir is None:
        root = Path(project_root) if project_root else Path.cwd()
        out_path = make_cst_output_dir(root, design_name)
    else:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

    files = export_cst_package(
        geometry,
        out_path,
        design_name=design_name,
        clear_existing=clear_existing,
    )
    summary = summarize_geometry(geometry, out_path)
    summary["design_name"] = design_name
    summary["cst_files"] = files
    if not files.get("step"):
        summary["step_note"] = (
            "STEP optional. Use siw_cst.stl or siw_cst_macro.bas for CST import."
        )
    return summary


def generate_slot_siw_cst(
    output_dir: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
    design_name: str = "SIW_Slot",
    **kwargs: object,
) -> dict:
    """Generate a CST package for rounded-rectangle slot via SIW."""
    from siw_generator.export_paths import make_cst_output_dir

    stackup = StackupParams(
        substrate_height_mm=float(kwargs.get("substrate_height_mm", 0.127)),
        copper_thickness_mm=float(kwargs.get("copper_thickness_um", 15.0)) / 1000.0,
    )
    params = SlotSIWParams(
        substrate_length_mm=float(kwargs.get("substrate_length_mm", 10.0)),
        substrate_width_mm=float(kwargs.get("substrate_width_mm", 10.0)),
        center_freq_ghz=float(kwargs.get("center_freq_ghz", 120.0)),
        slot_width_mm=float(kwargs.get("slot_width_mm", 0.15)),
        slot_length_mm=float(kwargs.get("slot_length_mm", 1.0)),
        slot_corner_r_mm=float(kwargs.get("slot_corner_r_mm", 0.015)),
        slot_pitch_mm=float(kwargs.get("slot_pitch_mm", 1.05)),
        material=str(kwargs.get("material", DEFAULT_SUBSTRATE_KEY)),
        er=kwargs.get("er"),  # type: ignore[arg-type]
        stackup=stackup,
        siw_width_mm=kwargs.get("siw_width_mm"),  # type: ignore[arg-type]
        via_count_target=kwargs.get("via_count_target"),  # type: ignore[arg-type]
        port1_x_mm=kwargs.get("port1_x_mm"),  # type: ignore[arg-type]
        port2_x_mm=kwargs.get("port2_x_mm"),  # type: ignore[arg-type]
        port1_enabled=bool(kwargs.get("port1_enabled", True)),
        port2_enabled=bool(kwargs.get("port2_enabled", True)),
        port_height_factor=kwargs.get("port_height_factor"),  # type: ignore[arg-type]
        port_width_factor=kwargs.get("port_width_factor"),  # type: ignore[arg-type]
    )
    geometry = build_slot_siw_geometry(params)
    clear_existing = bool(kwargs.get("clear_existing", True))

    if output_dir is None:
        root = Path(project_root) if project_root else Path.cwd()
        out_path = make_cst_output_dir(root, design_name)
    else:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

    files = export_cst_package(
        geometry,
        out_path,
        design_name=design_name,
        clear_existing=clear_existing,
    )
    summary = summarize_geometry(geometry, out_path)
    summary["design_name"] = design_name
    summary["cst_files"] = files
    summary["via_type"] = "slot"
    return summary


def generate_compose_cst(
    layout,
    output_dir: str | Path | None = None,
    *,
    project_root: str | Path | None = None,
    design_name: str = "Compose",
    clear_existing: bool = True,
) -> dict:
    """Generate a CST import package for a composed module layout."""
    from siw_generator.compose_cst_export import export_compose_cst_package
    from siw_generator.export_paths import make_cst_output_dir

    if output_dir is None:
        root = Path(project_root) if project_root else Path.cwd()
        out_path = make_cst_output_dir(root, design_name)
    else:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

    files = export_compose_cst_package(
        layout,
        out_path,
        design_name=design_name,
        clear_existing=clear_existing,
    )
    return {
        "status": "ok",
        "output": str(out_path),
        "design_name": design_name,
        "module_count": len(layout.placements),
        "port_count": len(layout.ports),
        "cst_files": files,
    }


def summarize_geometry(geometry: SIWGeometry, output_path: Path) -> dict:
    params = geometry.params
    mat = params.substrate_material
    stack = params.stackup
    z = stack.z_bounds_centered()
    assert params.er is not None
    return {
        "status": "ok",
        "output": str(output_path),
        "material": {
            "key": mat.key,
            "name": mat.name,
            "er": mat.er,
            "tan_delta": mat.tan_delta,
        },
        "stackup": {
            "substrate_height_mm": stack.substrate_height_mm,
            "copper_thickness_um": stack.copper_thickness_um,
            "total_thickness_mm": round(stack.total_thickness_mm, 4),
            "z_substrate_mm": [round(z["substrate"][0], 4), round(z["substrate"][1], 4)],
        },
        "substrate_mm": {
            "length": params.substrate_length_mm,
            "width": params.substrate_width_mm,
        },
        "center_freq_ghz": params.center_freq_ghz,
        "via_diameter_mm": params.via_diameter_mm,
        "er_used": params.er,
        "siw_width_mm": round(geometry.siw_width_mm, 4),
        "via_pitch_mm": round(geometry.via_pitch_mm, 4),
        "guided_wavelength_mm": round(params.guided_wavelength_mm(), 4),
        "via_count": geometry.via_count,
        "via_count_requested": geometry.via_count_requested,
        "via_count_clipped": geometry.via_count_clipped,
        "ports": [
            {
                "name": pt.name,
                "plane": pt.plane,
                "x_mm": round(pt.x_mm, 4),
                "y_min_mm": round(pt.y_min_mm, 4),
                "y_max_mm": round(pt.y_max_mm, 4),
                "z_min_mm": round(pt.z_min_mm, 4),
                "z_max_mm": round(pt.z_max_mm, 4),
                "width_mm": round(pt.width_mm, 4),
                "height_mm": round(pt.height_mm, 4),
                "enabled": pt.enabled,
            }
            for pt in geometry.ports
        ],
    }
