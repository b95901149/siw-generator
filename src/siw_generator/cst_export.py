"""CST Studio Suite export: VBA macro, STL, STEP, and import notes."""
from __future__ import annotations
from pathlib import Path
from siw_generator.param_report import write_parameter_report
from siw_generator.siw_geometry import SIWGeometry

_COPPER_MATERIAL = "Copper (annealed)"
_PORT_YRANGE = '"-siw_width*port_width_factor/2", "siw_width*port_width_factor/2"'
def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")
def _store_param(name: str, value: float | int | str, description: str = "") -> str:
    val = _fmt(float(value)) if isinstance(value, (int, float)) else str(value)
    if description:
        return f'    Call StoreParameterWithDescription("{name}", "{val}", "{description}")'
    return f'    Call StoreParameter("{name}", "{val}")'


def _store_param_expr(name: str, expr: str, description: str = "") -> str:
    if description:
        return f'    Call StoreParameterWithDescription("{name}", "{expr}", "{description}")'
    return f'    Call StoreParameter("{name}", "{expr}")'


def _vba_emit_add_to_history(header: str, body: list[str], *, indent: str = "    ") -> list[str]:
    """VBA lines that store parametric shape commands in CST History for Rebuild."""
    lines = [f"{indent}hist = \"\""]
    for line in body:
        escaped = line.replace('"', '""')
        lines.append(f'{indent}hist = hist & "{escaped}" & vbCrLf')
    lines.append(f'{indent}AddToHistory "{header}", hist')
    return lines


def _vba_hist_lit(text: str) -> str:
    """Append a literal line into hist (no embedded quotes)."""
    return f'    hist = hist & "{text}" & vbCrLf'


def _vba_hist_quoted_pair(prop: str, var: str, lo: str, hi: str) -> str:
    """Append .Xrange/.Yrange with two quoted parametric expressions."""
    return (
        f'    hist = hist & "{prop}" & q & {var} & "{lo}" & q & ", " & q & {var} & "{hi}" & q & vbCrLf'
    )


def _vba_hist_quoted_center(prop: str, var: str, tail: str) -> str:
    """Append .Xcenter/.Ycenter with one quoted parametric expression."""
    return f'    hist = hist & "{prop}" & q & {var} & "{tail}" & q & vbCrLf'


def _vba_hist_slot_name(index_var: str, suffix: str) -> str:
    """Append .Name slot_{n}{suffix} into hist."""
    if suffix:
        return (
            f'    hist = hist & "    .Name " & q & "slot_" & CStr({index_var}) & "{suffix}" & q & vbCrLf'
        )
    return f'    hist = hist & "    .Name " & q & "slot_" & CStr({index_var}) & q & vbCrLf'


def _vba_brick_hist_block(
    name: str,
    material: str,
    x_lo: str,
    x_hi: str,
    y_lo: str,
    y_hi: str,
    z_lo: str,
    z_hi: str,
    *,
    component: str = "siw",
) -> list[str]:
    """History text lines for one parametric brick."""
    return [
        _vba_hist_lit("With Brick"),
        _vba_hist_lit("    .Reset"),
        f'    hist = hist & "    .Name " & q & "{name}" & q & vbCrLf',
        f'    hist = hist & "    .Component " & q & "{component}" & q & vbCrLf',
        f'    hist = hist & "    .Material " & q & "{material}" & q & vbCrLf',
        f'    hist = hist & "    .Xrange " & q & "{x_lo}" & q & ", " & q & "{x_hi}" & q & vbCrLf',
        f'    hist = hist & "    .Yrange " & q & "{y_lo}" & q & ", " & q & "{y_hi}" & q & vbCrLf',
        f'    hist = hist & "    .Zrange " & q & "{z_lo}" & q & ", " & q & "{z_hi}" & q & vbCrLf',
        _vba_hist_lit("    .Create"),
        _vba_hist_lit("End With"),
    ]


def _vba_inline_brick_history(
    header: str,
    name: str,
    material: str,
    x_lo: str,
    x_hi: str,
    y_lo: str,
    y_hi: str,
    z_lo: str,
    z_hi: str,
) -> list[str]:
    lines = ['    hist = ""']
    lines.extend(
        _vba_brick_hist_block(
            name,
            material,
            x_lo,
            x_hi,
            y_lo,
            y_hi,
            z_lo,
            z_hi,
        )
    )
    lines.append(f'    AddToHistory "{header}", hist')
    lines.append("")
    return lines


def _vba_param_helpers() -> list[str]:
    """CST design parameters need Evaluate() for VBA numeric logic."""
    return [
        "Function ParamD(ByVal expr As String) As Double",
        "    ParamD = Evaluate(expr)",
        "End Function",
        "",
        "Function ParamL(ByVal expr As String) As Long",
        "    ParamL = CLng(Evaluate(expr))",
        "End Function",
        "",
    ]


def _vba_add_one_via_sub() -> list[str]:
    c = _COPPER_MATERIAL
    z_lo = "-substrate_height/2-copper_thickness"
    z_hi = "substrate_height/2+copper_thickness"
    return [
        "Sub AddOneVia(ByRef viaIndex As Long, xExpr As String, yExpr As String)",
        "    Dim hist As String",
        "    Dim q As String",
        "    q = Chr(34)",
        "    viaIndex = viaIndex + 1",
        '    hist = ""',
        _vba_hist_lit("With Cylinder"),
        _vba_hist_lit("    .Reset"),
        '    hist = hist & "    .Name " & q & "via_" & CStr(viaIndex) & q & vbCrLf',
        f'    hist = hist & "    .Component " & q & "vias" & q & vbCrLf',
        f'    hist = hist & "    .Material " & q & "{c}" & q & vbCrLf',
        f'    hist = hist & "    .Axis " & q & "z" & q & vbCrLf',
        _vba_hist_quoted_center("    .Xcenter ", "xExpr", ""),
        _vba_hist_quoted_center("    .Ycenter ", "yExpr", ""),
        f'    hist = hist & "    .Zcenter " & q & "0" & q & vbCrLf',
        f'    hist = hist & "    .OuterRadius " & q & "via_radius" & q & vbCrLf',
        f'    hist = hist & "    .InnerRadius " & q & "0" & q & vbCrLf',
        f'    hist = hist & "    .Zrange " & q & "{z_lo}" & q & ", " & q & "{z_hi}" & q & vbCrLf',
        _vba_hist_lit("    .Create"),
        _vba_hist_lit("End With"),
        '    AddToHistory "SIW via " & CStr(viaIndex), hist',
        "End Sub",
        "",
    ]


def _vba_create_circular_vias_sub() -> list[str]:
    """Loop-based via placement with substrate-edge clipping (matches DXF/Python)."""
    return [
        "Sub CreateCircularVias()",
        "    Dim viaIndex As Long",
        "    Dim k As Long",
        "    Dim col As Long",
        "    Dim xExpr As String",
        "    Dim limit As Double",
        "    Dim xMag As Double",
        "",
        "    viaIndex = 0",
        "    limit = ParamD(\"substrate_length\") / 2# - ParamD(\"via_radius\")",
        "    Dim nCols As Long",
        "    nCols = ParamL(\"via_col_requested\")",
        "",
        "    If (nCols Mod 2) = 1 Then",
        '        Call AddOneVia(viaIndex, "0", "-siw_width/2")',
        '        Call AddOneVia(viaIndex, "0", "siw_width/2")',
        "        For k = 1 To (nCols - 1) \\ 2",
        "            xMag = k * ParamD(\"via_pitch\")",
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*via_pitch"',
        '            Call AddOneVia(viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(viaIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*via_pitch"',
        '            Call AddOneVia(viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(viaIndex, xExpr, "siw_width/2")',
        "        Next k",
        "    Else",
        "        For col = 0 To nCols / 2 - 1",
        "            k = 2 * col + 1",
        "            xMag = k * ParamD(\"via_pitch\") / 2#",
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*via_pitch/2"',
        '            Call AddOneVia(viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(viaIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*via_pitch/2"',
        '            Call AddOneVia(viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(viaIndex, xExpr, "siw_width/2")',
        "        Next col",
        "    End If",
        "End Sub",
        "",
    ]


def _vba_circular_vias_call() -> list[str]:
    return ["", "    Call CreateCircularVias", ""]


def _vba_add_one_via_sub_direct() -> list[str]:
    """Direct .Create circular via (legacy parametric, re-run macro to rebuild)."""
    c = _COPPER_MATERIAL
    return [
        "Sub AddOneVia(ByRef viaIndex As Long, xExpr As String, yExpr As String)",
        "    viaIndex = viaIndex + 1",
        "    With Cylinder",
        "        .Reset",
        '        .Name "via_" & CStr(viaIndex)',
        '        .Component "vias"',
        f'        .Material "{c}"',
        '        .Axis "z"',
        "        .Xcenter (Chr(34) & xExpr & Chr(34))",
        "        .Ycenter (Chr(34) & yExpr & Chr(34))",
        '        .Zcenter "0"',
        '        .OuterRadius "via_radius"',
        '        .InnerRadius "0"',
        '        .Zrange "-substrate_height/2-copper_thickness", "substrate_height/2+copper_thickness"',
        "        .Create",
        "    End With",
        "End Sub",
        "",
    ]


def _vba_create_circular_vias_sub_direct() -> list[str]:
    return [
        "Sub CreateCircularVias()",
        "    Dim viaIndex As Long",
        "    Dim k As Long",
        "    Dim col As Long",
        "    Dim xExpr As String",
        "    Dim limit As Double",
        "    Dim xMag As Double",
        "",
        "    viaIndex = 0",
        "    limit = substrate_length / 2# - via_radius",
        "",
        "    If (via_col_requested Mod 2) = 1 Then",
        '        Call AddOneVia(viaIndex, "0", "-siw_width/2")',
        '        Call AddOneVia(viaIndex, "0", "siw_width/2")',
        "        For k = 1 To (via_col_requested - 1) \\ 2",
        "            xMag = k * via_pitch",
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*via_pitch"',
        '            Call AddOneVia(viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(viaIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*via_pitch"',
        '            Call AddOneVia(viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(viaIndex, xExpr, "siw_width/2")',
        "        Next k",
        "    Else",
        "        For col = 0 To via_col_requested / 2 - 1",
        "            k = 2 * col + 1",
        "            xMag = k * via_pitch / 2#",
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*via_pitch/2"',
        '            Call AddOneVia(viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(viaIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*via_pitch/2"',
        '            Call AddOneVia(viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(viaIndex, xExpr, "siw_width/2")',
        "        Next col",
        "    End If",
        "End Sub",
        "",
    ]


def _vba_add_one_slot_sub_direct() -> list[str]:
    """Direct .Create rounded-rectangle slot (legacy parametric, re-run macro to rebuild)."""
    c = _COPPER_MATERIAL
    z = '"-substrate_height/2-copper_thickness", "substrate_height/2+copper_thickness"'
    lines = [
        "Sub AddOneSlot(ByRef slotIndex As Long, xExpr As String, yExpr As String)",
        "    slotIndex = slotIndex + 1",
        "    If slot_length > 2 * slot_corner_r + 0.000001 Or slot_width > 2 * slot_corner_r + 0.000001 Then",
    ]

    def brick(name_suffix: str, x_lo: str, x_hi: str, y_lo: str, y_hi: str) -> list[str]:
        return [
            "        With Brick",
            "            .Reset",
            f'            .Name "slot_" & CStr(slotIndex) & "{name_suffix}"',
            '            .Component "vias"',
            f'            .Material "{c}"',
            f"            .Xrange xExpr & \"{x_lo}\", xExpr & \"{x_hi}\"",
            f"            .Yrange yExpr & \"{y_lo}\", yExpr & \"{y_hi}\"",
            f"            .Zrange {z}",
            "            .Create",
            "        End With",
        ]

    def cyl(name_suffix: str, x_tail: str, y_tail: str) -> list[str]:
        return [
            "        With Cylinder",
            "            .Reset",
            f'            .Name "slot_" & CStr(slotIndex) & "{name_suffix}"',
            '            .Component "vias"',
            f'            .Material "{c}"',
            '            .Axis "z"',
            f'            .Xcenter xExpr & "{x_tail}"',
            f'            .Ycenter yExpr & "{y_tail}"',
            '            .Zcenter "0"',
            '            .OuterRadius "slot_corner_r"',
            '            .InnerRadius "0"',
            f"            .Zrange {z}",
            "            .Create",
            "        End With",
        ]

    lines.extend(
        brick("_main", "-(slot_length/2-slot_corner_r)", "+(slot_length/2-slot_corner_r)", "-slot_width/2", "+slot_width/2")
    )
    lines.extend(
        brick("_left", "-slot_length/2", "-(slot_length/2-slot_corner_r)", "-(slot_width/2-slot_corner_r)", "+(slot_width/2-slot_corner_r)")
    )
    lines.extend(
        brick("_right", "+(slot_length/2-slot_corner_r)", "+slot_length/2", "-(slot_width/2-slot_corner_r)", "+(slot_width/2-slot_corner_r)")
    )
    lines.extend(cyl("_c1", "-(slot_length/2-slot_corner_r)", "-(slot_width/2-slot_corner_r)"))
    lines.extend(cyl("_c2", "+(slot_length/2-slot_corner_r)", "-(slot_width/2-slot_corner_r)"))
    lines.extend(cyl("_c3", "+(slot_length/2-slot_corner_r)", "+(slot_width/2-slot_corner_r)"))
    lines.extend(cyl("_c4", "-(slot_length/2-slot_corner_r)", "+(slot_width/2-slot_corner_r)"))
    lines.extend(
        [
            "    Else",
            "        With Cylinder",
            "            .Reset",
            '            .Name "slot_" & CStr(slotIndex)',
            '            .Component "vias"',
            f'            .Material "{c}"',
            '            .Axis "z"',
            "            .Xcenter xExpr",
            "            .Ycenter yExpr",
            '            .Zcenter "0"',
            '            .OuterRadius "slot_corner_r"',
            '            .InnerRadius "0"',
            f"            .Zrange {z}",
            "            .Create",
            "        End With",
            "    End If",
            "End Sub",
            "",
        ]
    )
    return lines


def _vba_create_slot_vias_sub_direct() -> list[str]:
    return [
        "Sub CreateSlotVias()",
        "    Dim slotIndex As Long",
        "    Dim k As Long",
        "    Dim col As Long",
        "    Dim xExpr As String",
        "    Dim limit As Double",
        "    Dim xMag As Double",
        "",
        "    slotIndex = 0",
        "    limit = substrate_length / 2# - slot_length / 2#",
        "",
        "    If (slot_col_requested Mod 2) = 1 Then",
        '        Call AddOneSlot(slotIndex, "0", "-siw_width/2")',
        '        Call AddOneSlot(slotIndex, "0", "siw_width/2")',
        "        For k = 1 To (slot_col_requested - 1) \\ 2",
        "            xMag = k * slot_pitch",
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*slot_pitch"',
        '            Call AddOneSlot(slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(slotIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*slot_pitch"',
        '            Call AddOneSlot(slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(slotIndex, xExpr, "siw_width/2")',
        "        Next k",
        "    Else",
        "        For col = 0 To slot_col_requested / 2 - 1",
        "            k = 2 * col + 1",
        "            xMag = k * slot_pitch / 2#",
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*slot_pitch/2"',
        '            Call AddOneSlot(slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(slotIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*slot_pitch/2"',
        '            Call AddOneSlot(slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(slotIndex, xExpr, "siw_width/2")',
        "        Next col",
        "    End If",
        "End Sub",
        "",
    ]


def _vba_define_ports_sub_direct(geometry: SIWGeometry) -> list[str]:
    lines = ["Sub DefinePorts()"]
    for port in geometry.ports:
        if not port.enabled:
            continue
        orientation = "xmin" if port.side == "left" else "xmax"
        port_num = "1" if port.name == "Port1" else "2"
        x_key = "port1_x" if port.name == "Port1" else "port2_x"
        lines.extend(
            [
                "",
                f"    ' {port.name}: waveguide port on YZ plane",
                "    With Port",
                "        .Reset",
                f'        .PortNumber "{port_num}"',
                '        .NumberOfModes "1"',
                f'        .Label "{port.name}"',
                '        .Coordinates "Free"',
                f'        .Orientation "{orientation}"',
                '        .PortOnBound "False"',
                '        .ClipPickedPortToBound "False"',
                f'        .Xrange "{x_key}", "{x_key}"',
                f"        .Yrange {_PORT_YRANGE}",
                '        .Zrange "-substrate_height/2-copper_thickness", "-substrate_height/2-copper_thickness+port_height"',
                "        .Create",
                "    End With",
            ]
        )
    lines.extend(["End Sub", ""])
    return lines


def _vba_add_one_slot_sub() -> list[str]:
    """Rounded-rectangle slot; writes parametric shape into CST History."""
    c = _COPPER_MATERIAL
    z_lo = "-substrate_height/2-copper_thickness"
    z_hi = "substrate_height/2+copper_thickness"

    def brick_block(name_suffix: str, x_lo: str, x_hi: str, y_lo: str, y_hi: str) -> list[str]:
        return [
            _vba_hist_lit("With Brick"),
            _vba_hist_lit("    .Reset"),
            _vba_hist_slot_name("slotIndex", name_suffix),
            f'    hist = hist & "    .Component " & q & "vias" & q & vbCrLf',
            f'    hist = hist & "    .Material " & q & "{c}" & q & vbCrLf',
            _vba_hist_quoted_pair("    .Xrange ", "xExpr", x_lo, x_hi),
            _vba_hist_quoted_pair("    .Yrange ", "yExpr", y_lo, y_hi),
            f'    hist = hist & "    .Zrange " & q & "{z_lo}" & q & ", " & q & "{z_hi}" & q & vbCrLf',
            _vba_hist_lit("    .Create"),
            _vba_hist_lit("End With"),
        ]

    def cyl_block(name_suffix: str, x_tail: str, y_tail: str) -> list[str]:
        return [
            _vba_hist_lit("With Cylinder"),
            _vba_hist_lit("    .Reset"),
            _vba_hist_slot_name("slotIndex", name_suffix),
            f'    hist = hist & "    .Component " & q & "vias" & q & vbCrLf',
            f'    hist = hist & "    .Material " & q & "{c}" & q & vbCrLf',
            f'    hist = hist & "    .Axis " & q & "z" & q & vbCrLf',
            _vba_hist_quoted_center("    .Xcenter ", "xExpr", x_tail),
            _vba_hist_quoted_center("    .Ycenter ", "yExpr", y_tail),
            f'    hist = hist & "    .Zcenter " & q & "0" & q & vbCrLf',
            f'    hist = hist & "    .OuterRadius " & q & "slot_corner_r" & q & vbCrLf',
            f'    hist = hist & "    .InnerRadius " & q & "0" & q & vbCrLf',
            f'    hist = hist & "    .Zrange " & q & "{z_lo}" & q & ", " & q & "{z_hi}" & q & vbCrLf',
            _vba_hist_lit("    .Create"),
            _vba_hist_lit("End With"),
        ]

    lines = [
        "Sub AddOneSlot(ByRef slotIndex As Long, xExpr As String, yExpr As String)",
        "    Dim hist As String",
        "    Dim q As String",
        "    q = Chr(34)",
        "    slotIndex = slotIndex + 1",
        '    hist = ""',
    ]
    lines.extend(
        brick_block(
            "_main",
            "-(slot_length/2-slot_corner_r)",
            "+(slot_length/2-slot_corner_r)",
            "-slot_width/2",
            "+slot_width/2",
        )
    )
    lines.extend(
        brick_block(
            "_left",
            "-slot_length/2",
            "-(slot_length/2-slot_corner_r)",
            "-(slot_width/2-slot_corner_r)",
            "+(slot_width/2-slot_corner_r)",
        )
    )
    lines.extend(
        brick_block(
            "_right",
            "+(slot_length/2-slot_corner_r)",
            "+slot_length/2",
            "-(slot_width/2-slot_corner_r)",
            "+(slot_width/2-slot_corner_r)",
        )
    )
    lines.extend(cyl_block("_c1", "-(slot_length/2-slot_corner_r)", "-(slot_width/2-slot_corner_r)"))
    lines.extend(cyl_block("_c2", "+(slot_length/2-slot_corner_r)", "-(slot_width/2-slot_corner_r)"))
    lines.extend(cyl_block("_c3", "+(slot_length/2-slot_corner_r)", "+(slot_width/2-slot_corner_r)"))
    lines.extend(cyl_block("_c4", "-(slot_length/2-slot_corner_r)", "+(slot_width/2-slot_corner_r)"))
    lines.extend(
        [
            '    AddToHistory "SIW slot " & CStr(slotIndex), hist',
            "End Sub",
            "",
        ]
    )
    return lines


def _vba_create_slot_vias_sub() -> list[str]:
    """Loop-based slot placement; each slot is stored in History for Rebuild."""
    return [
        "Sub CreateSlotVias()",
        "    Dim slotIndex As Long",
        "    Dim k As Long",
        "    Dim col As Long",
        "    Dim xExpr As String",
        "    Dim limit As Double",
        "    Dim xMag As Double",
        "",
        "    slotIndex = 0",
        "    limit = ParamD(\"substrate_length\") / 2# - ParamD(\"slot_length\") / 2#",
        "    Dim nCols As Long",
        "    nCols = ParamL(\"slot_col_requested\")",
        "",
        "    If (nCols Mod 2) = 1 Then",
        '        Call AddOneSlot(slotIndex, "0", "-siw_width/2")',
        '        Call AddOneSlot(slotIndex, "0", "siw_width/2")',
        "        For k = 1 To (nCols - 1) \\ 2",
        "            xMag = k * ParamD(\"slot_pitch\")",
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*slot_pitch"',
        '            Call AddOneSlot(slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(slotIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*slot_pitch"',
        '            Call AddOneSlot(slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(slotIndex, xExpr, "siw_width/2")',
        "        Next k",
        "    Else",
        "        For col = 0 To nCols / 2 - 1",
        "            k = 2 * col + 1",
        "            xMag = k * ParamD(\"slot_pitch\") / 2#",
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*slot_pitch/2"',
        '            Call AddOneSlot(slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(slotIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*slot_pitch/2"',
        '            Call AddOneSlot(slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(slotIndex, xExpr, "siw_width/2")',
        "        Next col",
        "    End If",
        "End Sub",
        "",
    ]


def _vba_slot_vias_call() -> list[str]:
    return ["", "    Call CreateSlotVias", ""]


def _vba_define_parameters(geometry: SIWGeometry, *, rerun_macro: bool = False) -> list[str]:
    p = geometry.params
    mat = p.substrate_material
    stack = p.stackup
    pitch = geometry.via_pitch_mm
    n_cols_requested = max(geometry.via_count_requested // 2, 1)
    n_cols_placed = len(geometry.x_positions_mm) if geometry.x_positions_mm else max(
        geometry.via_count // 2, 1
    )
    rebuild_hint = "re-run this macro to rebuild" if rerun_macro else "then Rebuild"
    lines = [
        "Sub DefineParameters()",
        f"    ' SIW design parameters — edit in CST Parameter List, {rebuild_hint}",
    ]
    param_defs: list[tuple[str, float | int | str, str]] = [
        ("substrate_length", p.substrate_length_mm, "substrate length (mm)"),
        ("substrate_width", p.substrate_width_mm, "substrate width (mm)"),
        ("substrate_height", stack.substrate_height_mm, "dielectric height h (mm)"),
        ("copper_thickness", stack.copper_thickness_mm, "copper thickness per side t_cu (mm)"),
        (
            "copper_thickness_um",
            stack.copper_thickness_um,
            "copper thickness per side t_cu (µm)",
        ),
        ("center_freq_ghz", p.center_freq_ghz, "center frequency (GHz)"),
        ("er_sub", mat.er, "substrate relative permittivity"),
        ("tand_sub", mat.tan_delta, "substrate loss tangent"),
        ("siw_width", geometry.siw_width_mm, "SIW via-wall spacing a (mm)"),
        ("via_pitch", pitch, "via column pitch p (mm)"),
        (
            "via_col_requested",
            n_cols_requested,
            "requested via columns along X (clip to substrate)",
        ),
        (
            "via_col_placed",
            n_cols_placed,
            "via columns fitting at export (reference only)",
        ),
        (
            "via_count_requested",
            geometry.via_count_requested,
            "requested via count (two rows)",
        ),
    ]
    if geometry.is_slot and geometry.slot_params is not None:
        sp = geometry.slot_params
        param_defs.extend(
            [
                ("slot_width", sp.slot_width_mm, "slot via width W (mm)"),
                ("slot_length", sp.slot_length_mm, "slot via length L (mm)"),
                (
                    "slot_corner_r",
                    min(
                        sp.slot_corner_r_mm,
                        sp.slot_length_mm / 2.0,
                        sp.slot_width_mm / 2.0,
                    ),
                    "slot corner fillet radius R (mm, clamped to min(L,W)/2)",
                ),
                ("slot_pitch", sp.slot_pitch_mm, "slot column pitch (mm)"),
                (
                    "slot_col_requested",
                    n_cols_requested,
                    "requested slot columns along X (clip to substrate)",
                ),
                (
                    "slot_count_requested",
                    geometry.via_count_requested,
                    "requested slot count (two rows)",
                ),
            ]
        )
    else:
        param_defs.append(("via_diameter", p.via_diameter_mm, "circular via diameter d (mm)"))
    for port in geometry.ports:
        if not port.enabled:
            continue
        key = "port1_x" if port.name == "Port1" else "port2_x"
        param_defs.append((key, port.x_mm, f"{port.name} X on YZ plane (mm)"))
    if geometry.ports:
        ref = next(pt for pt in geometry.ports if pt.enabled)
        param_defs.extend(
            [
                (
                    "port_width_factor",
                    p.port_width_factor,
                    "port width factor × siw_width (W_port = factor × a)",
                ),
                ("port_height", ref.height_mm, "port aperture height H_port (mm)"),
            ]
        )
    for name, value, desc in param_defs:
        lines.append(_store_param(name, value, desc))
    if geometry.ports and any(pt.enabled for pt in geometry.ports):
        lines.append(
            _store_param_expr(
                "port_width",
                "siw_width*port_width_factor",
                "port aperture width W_port = port_width_factor × siw_width (mm)",
            )
        )
    if not geometry.is_slot:
        lines.append(
            _store_param_expr(
                "via_radius",
                "via_diameter/2",
                "circular via radius r=d/2 (mm)",
            )
        )
    lines.extend(["End Sub", ""])
    return lines


def _vba_brick(
    name: str,
    material: str,
    x_rng: str,
    y_rng: str,
    z_rng: str,
    *,
    component: str = "siw",
) -> list[str]:
    return [
        "    With Brick",
        "        .Reset",
        f'        .Name "{name}"',
        f'        .Component "{component}"',
        f'        .Material "{material}"',
        f"        .Xrange {x_rng}",
        f"        .Yrange {y_rng}",
        f"        .Zrange {z_rng}",
        "        .Create",
        "    End With",
    ]


def _vba_ensure_component() -> list[str]:
    return [
        "Sub EnsureSIWComponent()",
        "    On Error Resume Next",
        '    Component.New "siw"',
        "    On Error GoTo 0",
        "End Sub",
        "",
        "Sub EnsureViasComponent()",
        "    On Error Resume Next",
        '    Component.New "vias"',
        "    On Error GoTo 0",
        "End Sub",
        "",
    ]


def _vba_clear_project_sub(sub_name: str) -> list[str]:
    """VBA sub that removes ports and components via CST-supported Delete APIs."""
    return [
        f"Sub {sub_name}()",
        "    On Error Resume Next",
        "    Dim i As Long",
        "    Dim j As Long",
        "    Dim nPorts As Long",
        "    Dim portNum As Long",
        "    Dim portNums(64) As Long",
        "    nPorts = Port.StartPortNumberIteration()",
        "    For i = 1 To nPorts",
        "        If i > 64 Then Exit For",
        "        portNums(i) = Port.GetNextPortNumber()",
        "    Next i",
        "    For j = nPorts To 1 Step -1",
        "        Port.Delete portNums(j)",
        "    Next j",
        "    For i = 1 To 64",
        "        nPorts = Port.StartPortNumberIteration()",
        "        If nPorts <= 0 Then Exit For",
        "        portNum = Port.GetNextPortNumber()",
        "        Port.Delete portNum",
        "    Next i",
        "    For i = 64 To 1 Step -1",
        "        Port.Delete i",
        "    Next i",
        "    Component.Delete \"vias\"",
        "    Component.Delete \"siw\"",
        "    For i = 1 To 64",
        "        Component.Delete \"component\" & CStr(i)",
        "    Next i",
        "    On Error GoTo 0",
        "End Sub",
        "",
    ]


def _vba_cleanup(_geometry: SIWGeometry) -> list[str]:
    """Remove prior geometry so the macro can be re-run safely."""
    return _vba_clear_project_sub("ClearPreviousSIW")


def _vba_define_ports_sub(geometry: SIWGeometry) -> list[str]:
    """Waveguide ports stored in History so Rebuild updates aperture geometry."""
    lines = [
        "Sub DefinePorts()",
        "    Dim hist As String",
        "    Dim q As String",
        "    q = Chr(34)",
    ]
    for port in geometry.ports:
        if not port.enabled:
            continue
        orientation = "xmin" if port.side == "left" else "xmax"
        port_num = "1" if port.name == "Port1" else "2"
        x_key = "port1_x" if port.name == "Port1" else "port2_x"
        header = f"SIW {port.name}"
        body = [
            "With Port",
            "    .Reset",
            f'    .PortNumber "{port_num}"',
            '    .NumberOfModes "1"',
            f'    .Label "{port.name}"',
            '    .Coordinates "Free"',
            f'    .Orientation "{orientation}"',
            '    .PortOnBound "False"',
            '    .ClipPickedPortToBound "False"',
            f'    .Xrange "{x_key}", "{x_key}"',
            f"    .Yrange {_PORT_YRANGE}",
            '    .Zrange "-substrate_height/2-copper_thickness", "-substrate_height/2-copper_thickness+port_height"',
            "    .Create",
            "End With",
        ]
        lines.append(f"    ' {port.name}: waveguide port on YZ plane")
        lines.extend(_vba_emit_add_to_history(header, body))
    lines.extend(["End Sub", ""])
    return lines


def _vba_substrate_material_history(mat) -> list[str]:
    """Store substrate material in History so Rebuild creates it before geometry."""
    name = mat.cst_material_name
    body = [
        "On Error Resume Next",
        f'Material.Delete "{name}"',
        "On Error GoTo 0",
        "With Material",
        "    .Reset",
        f'    .Name "{name}"',
        '    .FrqType "all"',
        '    .Type "Normal"',
        '    .MaterialUnit "Frequency", "GHz"',
        '    .MaterialUnit "Geometry", "mm"',
        '    .Epsilon "er_sub"',
        '    .Mu "1.0"',
        '    .Kappa "0.0"',
        '    .TanD "tand_sub"',
        '    .TanDFreq "10.0"',
        '    .TanDGiven "True"',
        '    .Colour "0.0", "1.0", "1.0"',
        "    .Create",
        "End With",
    ]
    return _vba_emit_add_to_history("SIW substrate material", body)


def _vba_main_material_calls(mat) -> list[str]:
    """Ensure substrate and copper exist before geometry (direct .Create or AddToHistory)."""
    lines = [
        "    Call DefineMaterial",
        "",
        "    Call DefineCopperMaterial",
        "",
    ]
    if mat.cst_library:
        return [
            "    Call EnsureSubstrateMaterial",
            "",
            *lines,
        ]
    return lines


def _vba_build_geometry_history_sub(geometry: SIWGeometry, mat) -> list[str]:
    """Write parametric substrate, vias/slots, and ports into CST History."""
    via_call = "CreateSlotVias" if geometry.is_slot else "CreateCircularVias"
    mat_name = mat.cst_material_name
    lines = [
        "Sub BuildSIWGeometryHistory()",
        "    Dim hist As String",
        "    Dim q As String",
        "    q = Chr(34)",
        "    Call EnsureSIWComponent",
        "",
    ]
    lines.extend(_vba_substrate_material_history(mat))
    lines.append("")
    lines.extend(
        _vba_inline_brick_history(
            "SIW substrate",
            "substrate",
            mat_name,
            "-substrate_length/2",
            "substrate_length/2",
            "-substrate_width/2",
            "substrate_width/2",
            "-substrate_height/2",
            "substrate_height/2",
        )
    )
    lines.extend(
        _vba_inline_brick_history(
            "SIW copper bottom",
            "copper_bottom",
            _COPPER_MATERIAL,
            "-substrate_length/2",
            "substrate_length/2",
            "-substrate_width/2",
            "substrate_width/2",
            "-substrate_height/2-copper_thickness",
            "-substrate_height/2",
        )
    )
    lines.extend(
        _vba_inline_brick_history(
            "SIW copper top",
            "copper_top",
            _COPPER_MATERIAL,
            "-substrate_length/2",
            "substrate_length/2",
            "-substrate_width/2",
            "substrate_width/2",
            "substrate_height/2",
            "substrate_height/2+copper_thickness",
        )
    )
    lines.extend(
        [
            "    Call EnsureViasComponent",
            f"    Call {via_call}",
            "    Call DefinePorts",
            "End Sub",
            "",
        ]
    )
    return lines


def build_cst_vba_text(
    geometry: SIWGeometry,
    *,
    parametric: bool = True,
    clear_existing: bool = True,
) -> str:
    """Build CST VBA macro source text from SIW geometry."""
    if parametric:
        return _build_cst_vba_text_parametric(geometry, clear_existing=clear_existing)
    return _build_cst_vba_text_direct(geometry, clear_existing=clear_existing)


def _build_cst_vba_text_direct(geometry: SIWGeometry, *, clear_existing: bool = True) -> str:
    """Parametric VBA with StoreParameter and direct .Create (re-run macro to rebuild)."""
    mat = geometry.params.substrate_material
    mat_name = mat.cst_material_name
    via_call = "CreateSlotVias" if geometry.is_slot else "CreateCircularVias"

    lines: list[str] = [
        "' CST VBA macro - SIW via structure (parametric, direct .Create)",
        "' Import: Macro > Run Macro (or paste into Macro Editor)",
        "' Units: mm, GHz | Origin: XY center, Z at stack center",
        "' After editing Parameter List: re-run this macro to rebuild geometry",
        "' No History / Rebuild — compatible with legacy CST workflow",
        "",
        "Sub Main",
        "",
    ]
    if clear_existing:
        lines.extend(["    Call ClearPreviousSIW", ""])
    lines.extend(["    Call DefineParameters", ""])
    lines.extend(_vba_main_material_calls(mat))
    lines.extend(["    Call EnsureSIWComponent", ""])
    lines.extend(
        _vba_brick(
            "substrate",
            mat_name,
            '"-substrate_length/2", "substrate_length/2"',
            '"-substrate_width/2", "substrate_width/2"',
            '"-substrate_height/2", "substrate_height/2"',
        )
    )
    lines.append("")
    lines.extend(
        _vba_brick(
            "copper_bottom",
            _COPPER_MATERIAL,
            '"-substrate_length/2", "substrate_length/2"',
            '"-substrate_width/2", "substrate_width/2"',
            '"-substrate_height/2-copper_thickness", "-substrate_height/2"',
        )
    )
    lines.append("")
    lines.extend(
        _vba_brick(
            "copper_top",
            _COPPER_MATERIAL,
            '"-substrate_length/2", "substrate_length/2"',
            '"-substrate_width/2", "substrate_width/2"',
            '"substrate_height/2", "substrate_height/2+copper_thickness"',
        )
    )
    lines.extend(["", "    Call EnsureViasComponent", "", f"    Call {via_call}", "", "    Call DefinePorts", "", "End Sub", ""])
    lines.extend(_vba_define_parameters(geometry, rerun_macro=True))
    if geometry.is_slot:
        lines.extend(_vba_add_one_slot_sub_direct())
        lines.extend(_vba_create_slot_vias_sub_direct())
    else:
        lines.extend(_vba_add_one_via_sub_direct())
        lines.extend(_vba_create_circular_vias_sub_direct())
    lines.extend(_vba_define_ports_sub_direct(geometry))
    lines.extend(_vba_ensure_component())
    lines.extend(_vba_cleanup(geometry))
    lines.extend(_vba_define_material(mat))
    lines.extend(_vba_define_copper_material())
    if mat.cst_library:
        lines.extend(_vba_ensure_library_materials(mat))
    return "\n".join(lines)


def _build_cst_vba_text_parametric(geometry: SIWGeometry, *, clear_existing: bool = True) -> str:
    """Parametric VBA with StoreParameter, History, and Rebuild."""
    p = geometry.params
    mat = p.substrate_material
    lines: list[str] = [
        "' CST VBA macro - SIW via structure (parametric)",
        "' Import: Macro > Run Macro (or paste into Macro Editor)",
        "' Units: mm, GHz | Origin: XY center, Z at stack center",
        "' After first Run Macro: edit Parameter List, then Rebuild to update geometry",
        "' Re-run macro only when via/slot count changes or on a fresh project",
        "",
        "Sub Main",
        "",
    ]
    if clear_existing:
        lines.extend(["    Call ClearPreviousSIW", ""])
    lines.extend(["    Call DefineParameters", ""])
    lines.extend(_vba_main_material_calls(mat))
    lines.extend(
        [
            "    Call BuildSIWGeometryHistory",
            "",
            "    Rebuild",
            "",
            "End Sub",
            "",
        ]
    )
    lines.extend(_vba_define_parameters(geometry))
    lines.extend(_vba_param_helpers())
    lines.extend(_vba_build_geometry_history_sub(geometry, mat))
    if geometry.is_slot:
        lines.extend(_vba_add_one_slot_sub())
        lines.extend(_vba_create_slot_vias_sub())
    else:
        lines.extend(_vba_add_one_via_sub())
        lines.extend(_vba_create_circular_vias_sub())
    lines.extend(_vba_define_ports_sub(geometry))
    lines.extend(_vba_ensure_component())
    lines.extend(_vba_cleanup(geometry))
    lines.extend(_vba_define_material(mat))
    lines.extend(_vba_define_copper_material())
    if mat.cst_library:
        lines.extend(_vba_ensure_library_materials(mat))
    return "\n".join(lines)


def export_cst_vba_macro(
    geometry: SIWGeometry,
    output_path: str | Path,
    *,
    parametric: bool = True,
    clear_existing: bool = True,
) -> Path:
    """Generate a CST VBA macro from SIW geometry."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        build_cst_vba_text(geometry, parametric=parametric, clear_existing=clear_existing),
        encoding="utf-8",
    )
    return output


def _vba_ensure_material_from_library_sub(
    sub_name: str,
    material_name: str,
    *,
    fallback_call: str | None = None,
) -> list[str]:
    """Load a CST library material into the project; optional fallback VBA call."""
    lines = [
        f"Sub {sub_name}()",
        "    Dim ok As Boolean",
        "    ok = False",
        "    On Error Resume Next",
        "    With Material",
        "        .Reset",
        f'        .Name "{material_name}"',
        f'        .LoadFromMaterialLibrary "{material_name}"',
        "        .Create",
        "    End With",
        "    If Err.Number = 0 Then ok = True",
        "    Err.Clear",
        "    On Error GoTo 0",
    ]
    if fallback_call:
        lines.extend(
            [
                "    If Not ok Then",
                f"        {fallback_call}",
                "    End If",
            ]
        )
    lines.extend(["End Sub", ""])
    return lines


def _vba_ensure_library_materials(mat) -> list[str]:
    """Substrate: LoadFromMaterialLibrary with DefineMaterial fallback (optional helper)."""
    return _vba_ensure_material_from_library_sub(
        "EnsureSubstrateMaterial",
        mat.cst_material_name,
        fallback_call="Call DefineMaterial",
    )


def _vba_define_copper_material() -> list[str]:
    """Create copper as a high-conductivity Normal material (works without Material Library)."""
    name = _COPPER_MATERIAL
    return [
        "Sub DefineCopperMaterial()",
        "    ' Normal + Kappa: reliable in VBA and History (Lossy metal / SetProperty often fails)",
        "    On Error Resume Next",
        f'    Material.Delete "{name}"',
        "    On Error GoTo 0",
        "    With Material",
        "        .Reset",
        f'        .Name "{name}"',
        '        .FrqType "all"',
        '        .Type "Normal"',
        '        .MaterialUnit "Frequency", "GHz"',
        '        .MaterialUnit "Geometry", "mm"',
        '        .Epsilon "1"',
        '        .Mu "1"',
        '        .Kappa "58000000"',
        '        .TanD "0"',
        '        .TanDFreq "10.0"',
        '        .TanDGiven "True"',
        '        .Colour "1.0", "0.7", "0.0"',
        "        .Create",
        "    End With",
        "End Sub",
        "",
    ]


def _vba_define_material(mat) -> list[str]:
    """Create/update custom substrate material from er_sub / tand_sub parameters."""
    name = mat.cst_material_name
    er_default = _fmt(mat.er)
    tand_default = _fmt(mat.tan_delta)
    return [
        "Sub DefineMaterial()",
        "    ' Use CST parameter variables (defined by DefineParameters)",
        f"    Dim erVal As String",
        f"    Dim tandVal As String",
        "    On Error Resume Next",
        f'    Material.Delete "{name}"',
        "    On Error GoTo 0",
        "    erVal = CStr(er_sub)",
        "    tandVal = CStr(tand_sub)",
        f'    If erVal = "" Then erVal = "{er_default}"',
        f'    If tandVal = "" Then tandVal = "{tand_default}"',
        "    With Material",
        "        .Reset",
        f'        .Name "{name}"',
        '        .FrqType "all"',
        '        .Type "Normal"',
        '        .MaterialUnit "Frequency", "GHz"',
        '        .MaterialUnit "Geometry", "mm"',
        "        .Epsilon erVal",
        '        .Mu "1.0"',
        '        .Kappa "0.0"',
        "        .TanD tandVal",
        '        .TanDFreq "10.0"',
        '        .TanDGiven "True"',
        '        .Colour "0.0", "1.0", "1.0"',
        "        .Create",
        "    End With",
        "End Sub",
        "",
    ]
def export_cst_step(geometry: SIWGeometry, output_path: str | Path) -> Path | None:
    """Export 3D STEP model for CST File > Import (optional cadquery dependency)."""
    try:
        import cadquery as cq
    except ImportError:
        return None
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    p = geometry.params
    stack = p.stackup
    z = stack.z_bounds_centered()
    def brick(z0: float, z1: float) -> "cq.Workplane":
        height = z1 - z0
        center_z = (z0 + z1) / 2.0
        return (
            cq.Workplane("XY")
            .box(p.substrate_length_mm, p.substrate_width_mm, height)
            .translate((0, 0, center_z))
        )
    assy = cq.Assembly()
    assy.add(brick(*z["substrate"]), name="substrate")
    assy.add(brick(*z["bottom_copper"]), name="copper_bottom")
    assy.add(brick(*z["top_copper"]), name="copper_top")
    z0, z1 = z["full_stack"]
    via_height = z1 - z0
    via_center_z = (z0 + z1) / 2.0
    if geometry.is_slot:
        for idx, slot in enumerate(geometry.slot_vias, start=1):
            slot_len = max(slot.length_mm - slot.width_mm, 0.0)
            if slot_len > 1e-6:
                body = (
                    cq.Workplane("XY")
                    .slot2D(slot_len, slot.width_mm)
                    .extrude(via_height)
                    .translate((slot.x_mm, slot.y_mm, via_center_z))
                )
            else:
                body = (
                    cq.Workplane("XY")
                    .circle(slot.width_mm / 2.0)
                    .extrude(via_height)
                    .translate((slot.x_mm, slot.y_mm, via_center_z))
                )
            assy.add(body, name=f"slot_{idx}")
    else:
        radius = p.via_diameter_mm / 2.0
        for idx, via in enumerate(geometry.vias, start=1):
            cyl = (
                cq.Workplane("XY")
                .circle(radius)
                .extrude(via_height)
                .translate((via.x_mm, via.y_mm, via_center_z))
            )
            assy.add(cyl, name=f"via_{idx}")
    assy.save(str(output))
    return output
def write_cst_import_notes(geometry: SIWGeometry, output_path: str | Path) -> Path:
    """Write CST import instructions alongside generated files."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    p = geometry.params
    mat = p.substrate_material
    stack = p.stackup
    z = stack.z_bounds_centered()
    text = f"""CST Studio Suite 匯入說明 - SIW Generator
========================================
建議優先順序：
1) VBA 巨集（siw_cst_macro.bas）— Macro > Run Macro（含材料、參數化幾何）
2) STL 3D 模型（siw_cst.stl）— File > Import > STL（單位 mm）
3) STEP 3D 模型（siw_cst.step，可選）— File > Import > STEP
4) DXF 2D 圖層（siw_cst.dxf）— File > Import > DXF 2D
VBA 參數化：
  巨集會建立 CST 參數（substrate_length、via_pitch、siw_width、port_width 等）。
  首次 Run Macro 會寫入 History 並 Rebuild；之後在 Parameter List 修改尺寸後按 Rebuild 即可更新幾何。
  變更 via_col_requested / slot 個數需重新 Run Macro（History 項目數固定）。
  重複 Run Macro 會先刪除 siw / vias 元件與 Port 再重建；參數化 History 模式可能累加 History，建議空白專案首次執行。
  直接建立模式（siw_cst_macro_direct.bas）同樣參數化（StoreParameter），但幾何以 .Create 建立；修改 Parameter List 後需重新 Run Macro（無 Rebuild）。
  圓孔 via 的 X 位置以 via_pitch 倍數表示（0、±p、±2p…）。
  圓孔 via 由 VBA 迴圈建立（CreateCircularVias / AddOneVia），放在 vias 元件；基板與銅箔在 siw 元件。
  Via 欄位數依 via_col_requested 排列，超出基板 (|X| > L/2 - via_radius) 的欄位會自動略過（與 DXF 一致）。
  金屬層厚度參數：copper_thickness (mm)、copper_thickness_um (µm)，用於上下銅箔與 via 高度。
  材料：基板先嘗試 LoadFromMaterialLibrary（{mat.cst_material_name}），再以 DefineMaterial（er_sub / tand_sub）確保存在；銅箔由 DefineCopperMaterial 建立（{_COPPER_MATERIAL}，σ=5.8e7 S/m），無需 Material Library。
  Slot 模式：圓角矩形 Slot 由 VBA 建立（CreateSlotVias / AddOneSlot，R = slot_corner_r 來自 Slot 分頁）；亦可匯入 siw_cst.stl 對照。
板材堆疊（原點在堆疊中心，Z 軸向上）：
  介電層高度 : {stack.substrate_height_mm} mm  ({mat.name})
  雙面銅厚   : {stack.copper_thickness_um:.0f} µm（每面）
  總厚度     : {stack.total_thickness_mm:.4f} mm
  介電 Z 範圍: {z['substrate'][0]:.4f} .. {z['substrate'][1]:.4f} mm
  底銅 Z 範圍: {z['bottom_copper'][0]:.4f} .. {z['bottom_copper'][1]:.4f} mm
  頂銅 Z 範圍: {z['top_copper'][0]:.4f} .. {z['top_copper'][1]:.4f} mm
電磁參數：
  中心頻率   : {p.center_freq_ghz} GHz
  εr         : {p.er}
  tan δ      : {mat.tan_delta}
  SIW 寬度   : {geometry.siw_width_mm:.4f} mm
  Via 直徑   : {p.via_diameter_mm} mm
  Via 間距   : {geometry.via_pitch_mm:.4f} mm
  Via 數量   : {geometry.via_count}
Port 設定：
  Port1（左側 SIW 開口）: {"啟用" if any(pt.name=="Port1" for pt in geometry.ports) else "停用"}
  Port2（右側 SIW 開口）: {"啟用" if any(pt.name=="Port2" for pt in geometry.ports) else "停用"}
"""
    for port in geometry.ports:
        text += (
            f"  {port.name}: X={port.x_mm:.4f} mm, "
            f"W={port.width_mm:.4f} mm, H={port.height_mm:.4f} mm "
            f"(YZ plane, Y-centered)\n"
        )
    text += f"""
DXF 圖層（CST 2D 匯入）：
  DIELECTRIC_BOUNDARY → 擠出 {stack.substrate_height_mm} mm → 指派 {mat.cst_material_name}
  COPPER_TOP / COPPER_BOTTOM → 各擠出 {stack.copper_thickness_mm} mm → PEC / Copper
  VIA_HOLE → 貫通孔，半徑 {p.via_diameter_mm / 2.0:.4f} mm
  PORT1 / PORT2 → 波導端口開口線
VBA 巨集：
  自動建立介電基板、雙面銅箔（siw 元件）與所有 via 圓柱（vias 元件，Copper (annealed)）。
  可重複 Run Macro；基板使用 CST 材料庫名稱（與 GUI 下拉選單一致）。
STL 匯入：
  File > Import > STL，Scale = 1，單位選 mm。
  匯入後分別指派：介電層 → {mat.cst_material_name}，銅箔/via → PEC 或 Copper。
邊界條件建議（120 GHz）：
  - X/Y 方向：Open (add space) 或 PML
  - Z 方向：Open 或 PML
  - 求解器：Time Domain / Transient 或 Frequency Domain
"""
    output.write_text(text, encoding="utf-8")
    return output
def export_cst_package(
    geometry: SIWGeometry,
    output_dir: str | Path,
    *,
    design_name: str = "SIW",
    clear_existing: bool = True,
) -> dict[str, str]:
    """Export all CST-ready artifacts into one folder."""
    from siw_generator.dxf_export import export_siw_dxf
    from siw_generator.hfss_export import export_hfss_script
    from siw_generator.stl_export import export_siw_stl
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    files["dxf"] = str(export_siw_dxf(geometry, out / "siw_cst.dxf", cst_mode=True))
    files["vba_macro"] = str(
        export_cst_vba_macro(geometry, out / "siw_cst_macro.bas", clear_existing=clear_existing)
    )
    files["vba_macro_direct"] = str(
        export_cst_vba_macro(
            geometry,
            out / "siw_cst_macro_direct.bas",
            parametric=False,
            clear_existing=clear_existing,
        )
    )
    files["stl"] = str(export_siw_stl(geometry, out / "siw_cst.stl"))
    files["import_notes"] = str(write_cst_import_notes(geometry, out / "CST_IMPORT.txt"))
    files["params_txt"] = str(
        write_parameter_report(geometry, out / "siw_params.txt", design_name=design_name)
    )
    files["hfss_script"] = str(export_hfss_script(geometry, out / "siw_hfss.vbs"))
    step = export_cst_step(geometry, out / "siw_cst.step")
    files["step"] = str(step) if step is not None else ""
    return files

