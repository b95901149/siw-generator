"""Waveguide parameter report export."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from siw_generator.siw_geometry import SIWGeometry


def write_parameter_report(
    geometry: SIWGeometry,
    output_path: str | Path,
    *,
    design_name: str = "SIW",
) -> Path:
    """Write a text file recording SIW / waveguide design parameters."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    p = geometry.params
    mat = p.substrate_material
    stack = p.stackup
    z = stack.z_bounds_centered()
    assert p.er is not None

    lines = [
        "SIW 波導設計參數紀錄",
        "=" * 50,
        f"產生時間   : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"設計名稱   : {design_name}",
        "",
        "[板材]",
        f"  材料       : {mat.name}",
        f"  εr         : {p.er}",
        f"  tan δ      : {mat.tan_delta}",
        f"  基板厚度 h : {stack.substrate_height_mm} mm",
        f"  銅厚       : {stack.copper_thickness_um:.0f} µm（每面）",
        f"  總厚度     : {stack.total_thickness_mm:.4f} mm",
        "",
        "[基板尺寸]",
        f"  長度 (X)   : {p.substrate_length_mm} mm",
        f"  寬度 (Y)   : {p.substrate_width_mm} mm",
        "",
        "[SIW 電磁]",
        f"  中心頻率   : {p.center_freq_ghz} GHz",
        f"  導波波長 λg: {p.guided_wavelength_mm():.4f} mm",
    ]
    if not geometry.is_slot:
        pitch = geometry.via_pitch_mm
        a_eff = p.equivalent_waveguide_width_mm()
        corr = p.via_width_correction_mm(pitch)
        lines.extend(
            [
                f"  截止頻率 fc: {p.default_fc_ghz():.2f} GHz",
                f"  等效寬度 a_eff: {a_eff:.4f} mm",
                f"  Via 修正   : d²/(0.95p) = {corr:.4f} mm",
                f"  SIW 寬度 a : {geometry.siw_width_mm:.4f} mm",
                f"  孔距安全   : p < 2d ({2*p.via_diameter_mm:.3f}), "
                f"p < λg/4 ({p.guided_wavelength_mm()/4:.3f})",
            ]
        )
    else:
        lines.append(f"  SIW 寬度 w : {geometry.siw_width_mm:.4f} mm")
    lines.extend(["", "[Via 圍牆]"])
    if geometry.is_slot and geometry.slot_params is not None:
        sp = geometry.slot_params
        lines.extend(
            [
                f"  形式       : 圓角矩形 Slot",
                f"  Slot W     : {sp.slot_width_mm} mm",
                f"  Slot L     : {sp.slot_length_mm} mm",
                f"  Slot R     : {sp.slot_corner_r_mm} mm",
                f"  Slot pitch : {sp.slot_pitch_mm:.4f} mm",
                f"  Slot 總數  : {geometry.via_count}",
                f"  要求個數   : {geometry.via_count_requested}",
                f"  超出截掉   : {'是' if geometry.via_count_clipped else '否'}",
                f"  X 排列     : 以 X=0 為中心向兩側延伸",
                "",
                "[Slot 中心座標 (X, Y) mm]",
            ]
        )
        seen: set[tuple[float, float]] = set()
        for slot in geometry.slot_vias:
            key = (round(slot.x_mm, 4), round(slot.y_mm, 4))
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  ({slot.x_mm:.4f}, {slot.y_mm:.4f})")
        if not seen:
            lines.append("  (無)")
    else:
        lines.extend(
            [
                f"  Via 直徑   : {p.via_diameter_mm} mm",
                f"  Via 孔距   : {geometry.via_pitch_mm:.4f} mm",
                f"  Via 總數   : {geometry.via_count}",
                f"  要求個數   : {geometry.via_count_requested}",
                f"  超出截掉   : {'是' if geometry.via_count_clipped else '否'}",
                f"  X 排列     : 以 X=0 為中心向兩側延伸",
                "",
                "[Via 中心座標 (X, Y) mm]",
            ]
        )
        seen = set()
        for via in geometry.vias:
            key = (round(via.x_mm, 4), round(via.y_mm, 4))
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"  ({via.x_mm:.4f}, {via.y_mm:.4f})")
        if not seen:
            lines.append("  (無)")

    lines.extend(
        [
            "",
            "[Port 設定 — YZ 平面]",
            f"  高度倍數   : {p.port_height_factor} × h  →  H_port = {p.port_height_factor * stack.substrate_height_mm:.4f} mm"
            f"（預設 h+2×t_cu={stack.substrate_height_mm + 2.0 * stack.copper_thickness_mm:.4f} mm）",
            f"  寬度倍數   : {p.port_width_factor} × w  →  W_port = {p.port_width_factor * geometry.siw_width_mm:.4f} mm"
            f"（預設 = SIW 寬度 w）",
            f"  Port1 啟用 : {'是' if p.port1_enabled else '否'}",
            f"  Port2 啟用 : {'是' if p.port2_enabled else '否'}",
        ]
    )
    for port in geometry.ports:
        lines.extend(
            [
                f"  {port.name}:",
                f"    X 平面位置 : {port.x_mm:.4f} mm",
                f"    Y 範圍     : {port.y_min_mm:.4f} .. {port.y_max_mm:.4f} mm  (W={port.width_mm:.4f})",
                f"    Z 範圍     : {port.z_min_mm:.4f} .. {port.z_max_mm:.4f} mm  (H={port.height_mm:.4f})",
                f"    說明       : 自底層接地銅箔向上延伸，Y 方向以中心對稱",
            ]
        )

    lines.extend(
        [
            "",
            "[Z 軸堆疊 (原點在堆疊中心)]",
            f"  底銅       : {z['bottom_copper'][0]:.4f} .. {z['bottom_copper'][1]:.4f} mm",
            f"  介電層     : {z['substrate'][0]:.4f} .. {z['substrate'][1]:.4f} mm",
            f"  頂銅       : {z['top_copper'][0]:.4f} .. {z['top_copper'][1]:.4f} mm",
            "",
        ]
    )

    output.write_text("\n".join(lines), encoding="utf-8")
    return output
