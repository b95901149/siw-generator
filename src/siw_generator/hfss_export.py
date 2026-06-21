"""Ansys HFSS VBScript export from SIWGeometry."""

from __future__ import annotations

from pathlib import Path

from siw_generator.siw_geometry import SIWGeometry

_COPPER = "copper"
_SUBSTRATE_MAT = "siw_substrate"
_DESIGN_NAME = "SIW_Design"


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _mm(value: float | int) -> str:
    return f"{_fmt(float(value))}mm"


def _q(name: str) -> str:
    """HFSS MaterialValue embedded quotes."""
    return f'""{name}""'


def _hfss_define_variables(geometry: SIWGeometry) -> list[str]:
    p = geometry.params
    mat = p.substrate_material
    stack = p.stackup
    pitch = geometry.via_pitch_mm
    n_cols_requested = max(geometry.via_count_requested // 2, 1)

    vars_list: list[tuple[str, str]] = [
        ("substrate_length", _mm(p.substrate_length_mm)),
        ("substrate_width", _mm(p.substrate_width_mm)),
        ("substrate_height", _mm(stack.substrate_height_mm)),
        ("copper_thickness", _mm(stack.copper_thickness_mm)),
        ("center_freq_ghz", _fmt(p.center_freq_ghz)),
        ("er_sub", _fmt(mat.er)),
        ("tand_sub", _fmt(mat.tan_delta)),
        ("siw_width", _mm(geometry.siw_width_mm)),
        ("via_pitch", _mm(pitch)),
        ("via_col_requested", str(n_cols_requested)),
        ("via_count_requested", str(geometry.via_count_requested)),
        ("port_width_factor", _fmt(p.port_width_factor)),
        ("port_height_factor", _fmt(p.port_height_factor)),
        ("port_width", "siw_width*port_width_factor"),
        ("port_height", "substrate_height*port_height_factor"),
    ]

    if geometry.is_slot and geometry.slot_params is not None:
        sp = geometry.slot_params
        corner = min(sp.slot_corner_r_mm, sp.slot_length_mm / 2.0, sp.slot_width_mm / 2.0)
        vars_list.extend(
            [
                ("slot_width", _mm(sp.slot_width_mm)),
                ("slot_length", _mm(sp.slot_length_mm)),
                ("slot_corner_r", _mm(corner)),
                ("slot_pitch", _mm(sp.slot_pitch_mm)),
                ("slot_col_requested", str(n_cols_requested)),
                ("slot_count_requested", str(geometry.via_count_requested)),
            ]
        )
    else:
        vars_list.extend(
            [
                ("via_diameter", _mm(p.via_diameter_mm)),
                ("via_radius", "via_diameter/2"),
            ]
        )

    for port in geometry.ports:
        if not port.enabled:
            continue
        key = "port1_x" if port.name == "Port1" else "port2_x"
        vars_list.append((key, _mm(port.x_mm)))

    lines = [
        "Sub DefineVariables(oDesign)",
        "    Dim props",
    ]
    for name, value in vars_list:
        lines.append(
            f'    props = Array("NAME:{name}", "PropType:=", "VariableProp", "UserDef:=", true, "Value:=", "{value}")'
        )
        lines.append(
            '    oDesign.ChangeProperty Array("NAME:AllTabs", Array("NAME:LocalVariableTab", '
            'Array("NAME:PropServers", "LocalVariables"), Array("NAME:NewProps", props)))'
        )
    lines.extend(["End Sub", ""])
    return lines


def _hfss_material_sub() -> list[str]:
    return [
        "Sub EnsureSubstrateMaterial(oProject)",
        "    Dim oDefinitionMgr",
        "    Set oDefinitionMgr = oProject.GetDefinitionManager()",
        "    On Error Resume Next",
        f'    oDefinitionMgr.RemoveMaterial "{_SUBSTRATE_MAT}"',
        "    On Error GoTo 0",
        "    oDefinitionMgr.AddMaterial Array(\"NAME:" + _SUBSTRATE_MAT + "\", _",
        '        "CoordinateSystemType:=", "Cartesian", _',
        '        Array("NAME:AttachedData", _',
        '            Array("NAME:MatAppearanceParams", "color:=", "(132 132 193)"), _',
        '            Array("NAME:PhysicsParams", _',
        '                "permittivity:=", "er_sub", _',
        '                "dielectric_loss_tangent:=", "tand_sub", _',
        '                "conductivity:=", "0", _',
        '                "permeability:=", "1")), _',
        '        "localCoordSystem:=", Array(0, 0, 0, 1, 0, 0, 0, 1, 0))',
        "End Sub",
        "",
    ]


def _hfss_attrs(name: str, material: str, *, solve_inside: bool = False) -> str:
    mat = _q(material)
    inside = "true" if solve_inside else "false"
    return (
        f'Array("NAME:Attributes", "Name:=", "{name}", "Flags:=", "", '
        f'"Color:=", "(143 175 143)", "Transparency:=", 0, '
        f'"PartCoordinateSystem:=", "Global", "MaterialValue:=", "{mat}", '
        f'"SolveInside:=", {inside})'
    )


def _hfss_stack_geometry() -> list[str]:
    z_sub_lo = "-substrate_height/2"
    z_cu_bot_lo = "-substrate_height/2-copper_thickness"
    z_cu_top_lo = "substrate_height/2"
    return [
        "Sub BuildStack(oEditor)",
        "    oEditor.CreateBox _",
        '        Array("NAME:BoxParameters", _',
        '            "XPosition:=", "-substrate_length/2", "YPosition:=", "-substrate_width/2", _',
        f'            "ZPosition:=", "{z_sub_lo}", _',
        '            "XSize:=", "substrate_length", "YSize:=", "substrate_width", "ZSize:=", "substrate_height"), _',
        f"        {_hfss_attrs('substrate', _SUBSTRATE_MAT, solve_inside=True)}",
        "    oEditor.CreateBox _",
        '        Array("NAME:BoxParameters", _',
        '            "XPosition:=", "-substrate_length/2", "YPosition:=", "-substrate_width/2", _',
        f'            "ZPosition:=", "{z_cu_bot_lo}", _',
        '            "XSize:=", "substrate_length", "YSize:=", "substrate_width", "ZSize:=", "copper_thickness"), _',
        f"        {_hfss_attrs('copper_bottom', _COPPER)}",
        "    oEditor.CreateBox _",
        '        Array("NAME:BoxParameters", _',
        '            "XPosition:=", "-substrate_length/2", "YPosition:=", "-substrate_width/2", _',
        f'            "ZPosition:=", "{z_cu_top_lo}", _',
        '            "XSize:=", "substrate_length", "YSize:=", "substrate_width", "ZSize:=", "copper_thickness"), _',
        f"        {_hfss_attrs('copper_top', _COPPER)}",
        "End Sub",
        "",
    ]


def _hfss_circular_via_subs() -> list[str]:
    z_h = "substrate_height+2*copper_thickness"
    return [
        "Sub AddOneVia(oEditor, ByRef viaIndex, xExpr, yExpr)",
        "    viaIndex = viaIndex + 1",
        "    oEditor.CreateCylinder _",
        '        Array("NAME:CylinderParameters", _',
        '            "XCenter:=", xExpr, "YCenter:=", yExpr, "ZCenter:=", "0mm", _',
        '            "Radius:=", "via_radius", "Height:=", "' + z_h + '", _',
        '            "WhichAxis:=", "Z", "NumSides:=", "0"), _',
        f'        {_hfss_attrs("via_tmp", _COPPER)}',
        '    oEditor.ChangeProperty Array("NAME:AllTabs", Array("NAME:Geometry3DAttributeTab", _',
        '        Array("NAME:PropServers", "via_tmp"), Array("NAME:ChangedProps", _',
        '        Array("NAME:Name", "Value:=", "via_" & CStr(viaIndex)))))',
        "End Sub",
        "",
        "Sub CreateCircularVias(oDesign, oEditor)",
        "    Dim viaIndex, k, col, xExpr, limit, xMag, nCols",
        "    viaIndex = 0",
        '    limit = oDesign.Evaluate("substrate_length/2-via_radius")',
        "    nCols = via_col_requested",
        "    If (nCols Mod 2) = 1 Then",
        '        Call AddOneVia(oEditor, viaIndex, "0mm", "-siw_width/2")',
        '        Call AddOneVia(oEditor, viaIndex, "0mm", "siw_width/2")',
        "        For k = 1 To (nCols - 1) \\ 2",
        '            xMag = k * oDesign.Evaluate("via_pitch")',
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*via_pitch"',
        '            Call AddOneVia(oEditor, viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(oEditor, viaIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*via_pitch"',
        '            Call AddOneVia(oEditor, viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(oEditor, viaIndex, xExpr, "siw_width/2")',
        "        Next k",
        "    Else",
        "        For col = 0 To nCols / 2 - 1",
        "            k = 2 * col + 1",
        '            xMag = k * oDesign.Evaluate("via_pitch") / 2#',
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*via_pitch/2"',
        '            Call AddOneVia(oEditor, viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(oEditor, viaIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*via_pitch/2"',
        '            Call AddOneVia(oEditor, viaIndex, xExpr, "-siw_width/2")',
        '            Call AddOneVia(oEditor, viaIndex, xExpr, "siw_width/2")',
        "        Next col",
        "    End If",
        "End Sub",
        "",
    ]


def _hfss_slot_via_subs() -> list[str]:
    z_h = "substrate_height+2*copper_thickness"
    attrs = _hfss_attrs("slot_part", _COPPER)
    return [
        "Sub AddOneSlot(oEditor, ByRef slotIndex, xExpr, yExpr)",
        "    slotIndex = slotIndex + 1",
        "    If oEditor.GetModelUnits() <> \"mm\" Then oEditor.SetModelUnits Array(\"NAME:Units Parameter\", \"Units:=\", \"mm\")",
        "    If slot_length > 2 * slot_corner_r + 0.000001 Or slot_width > 2 * slot_corner_r + 0.000001 Then",
        "        oEditor.CreateBox Array(\"NAME:BoxParameters\", \"XPosition:=\", xExpr & \"-(slot_length/2-slot_corner_r)\", \"YPosition:=\", yExpr & \"-slot_width/2\", \"ZPosition:=\", \"-(" + z_h + ")/2\", \"XSize:=\", \"slot_length-2*slot_corner_r\", \"YSize:=\", \"slot_width\", \"ZSize:=\", \"" + z_h + "\"), " + attrs,
        "        oEditor.CreateBox Array(\"NAME:BoxParameters\", \"XPosition:=\", xExpr & \"-slot_length/2\", \"YPosition:=\", yExpr & \"-(slot_width/2-slot_corner_r)\", \"ZPosition:=\", \"-(" + z_h + ")/2\", \"XSize:=\", \"slot_corner_r\", \"YSize:=\", \"slot_width-2*slot_corner_r\", \"ZSize:=\", \"" + z_h + "\"), " + attrs,
        "        oEditor.CreateBox Array(\"NAME:BoxParameters\", \"XPosition:=\", xExpr & \"+(slot_length/2-slot_corner_r)\", \"YPosition:=\", yExpr & \"-(slot_width/2-slot_corner_r)\", \"ZPosition:=\", \"-(" + z_h + ")/2\", \"XSize:=\", \"slot_corner_r\", \"YSize:=\", \"slot_width-2*slot_corner_r\", \"ZSize:=\", \"" + z_h + "\"), " + attrs,
        "        oEditor.CreateCylinder Array(\"NAME:CylinderParameters\", \"XCenter:=\", xExpr & \"-(slot_length/2-slot_corner_r)\", \"YCenter:=\", yExpr & \"-(slot_width/2-slot_corner_r)\", \"ZCenter:=\", \"0mm\", \"Radius:=\", \"slot_corner_r\", \"Height:=\", \"" + z_h + "\", \"WhichAxis:=\", \"Z\", \"NumSides:=\", \"0\"), " + attrs,
        "        oEditor.CreateCylinder Array(\"NAME:CylinderParameters\", \"XCenter:=\", xExpr & \"+(slot_length/2-slot_corner_r)\", \"YCenter:=\", yExpr & \"-(slot_width/2-slot_corner_r)\", \"ZCenter:=\", \"0mm\", \"Radius:=\", \"slot_corner_r\", \"Height:=\", \"" + z_h + "\", \"WhichAxis:=\", \"Z\", \"NumSides:=\", \"0\"), " + attrs,
        "        oEditor.CreateCylinder Array(\"NAME:CylinderParameters\", \"XCenter:=\", xExpr & \"+(slot_length/2-slot_corner_r)\", \"YCenter:=\", yExpr & \"+(slot_width/2-slot_corner_r)\", \"ZCenter:=\", \"0mm\", \"Radius:=\", \"slot_corner_r\", \"Height:=\", \"" + z_h + "\", \"WhichAxis:=\", \"Z\", \"NumSides:=\", \"0\"), " + attrs,
        "        oEditor.CreateCylinder Array(\"NAME:CylinderParameters\", \"XCenter:=\", xExpr & \"-(slot_length/2-slot_corner_r)\", \"YCenter:=\", yExpr & \"+(slot_width/2-slot_corner_r)\", \"ZCenter:=\", \"0mm\", \"Radius:=\", \"slot_corner_r\", \"Height:=\", \"" + z_h + "\", \"WhichAxis:=\", \"Z\", \"NumSides:=\", \"0\"), " + attrs,
        "    Else",
        "        oEditor.CreateCylinder Array(\"NAME:CylinderParameters\", \"XCenter:=\", xExpr, \"YCenter:=\", yExpr, \"ZCenter:=\", \"0mm\", \"Radius:=\", \"slot_corner_r\", \"Height:=\", \"" + z_h + "\", \"WhichAxis:=\", \"Z\", \"NumSides:=\", \"0\"), " + attrs,
        "    End If",
        "End Sub",
        "",
        "Sub CreateSlotVias(oDesign, oEditor)",
        "    Dim slotIndex, k, col, xExpr, limit, xMag, nCols",
        "    slotIndex = 0",
        '    limit = oDesign.Evaluate("substrate_length/2-slot_length/2")',
        "    nCols = slot_col_requested",
        "    If (nCols Mod 2) = 1 Then",
        '        Call AddOneSlot(oEditor, slotIndex, "0mm", "-siw_width/2")',
        '        Call AddOneSlot(oEditor, slotIndex, "0mm", "siw_width/2")',
        "        For k = 1 To (nCols - 1) \\ 2",
        '            xMag = k * oDesign.Evaluate("slot_pitch")',
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*slot_pitch"',
        '            Call AddOneSlot(oEditor, slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(oEditor, slotIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*slot_pitch"',
        '            Call AddOneSlot(oEditor, slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(oEditor, slotIndex, xExpr, "siw_width/2")',
        "        Next k",
        "    Else",
        "        For col = 0 To nCols / 2 - 1",
        "            k = 2 * col + 1",
        '            xMag = k * oDesign.Evaluate("slot_pitch") / 2#',
        "            If xMag > limit + 0.000001 Then Exit For",
        '            xExpr = CStr(k) & "*slot_pitch/2"',
        '            Call AddOneSlot(oEditor, slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(oEditor, slotIndex, xExpr, "siw_width/2")',
        '            xExpr = "-" & CStr(k) & "*slot_pitch/2"',
        '            Call AddOneSlot(oEditor, slotIndex, xExpr, "-siw_width/2")',
        '            Call AddOneSlot(oEditor, slotIndex, xExpr, "siw_width/2")',
        "        Next col",
        "    End If",
        "End Sub",
        "",
    ]


def _hfss_ports_sub(geometry: SIWGeometry) -> list[str]:
    lines = [
        "Sub DefinePorts(oDesign)",
        "    Dim oEditor, oModule",
        "    Set oEditor = oDesign.SetActiveEditor(\"3D Modeler\")",
        "    Set oModule = oDesign.GetModule(\"BoundarySetup\")",
        "    oEditor.SetModelUnits Array(\"NAME:Units Parameter\", \"Units:=\", \"mm\")",
    ]
    z_start = "-substrate_height/2-copper_thickness"
    for port in geometry.ports:
        if not port.enabled:
            continue
        sheet = "Port1Sheet" if port.name == "Port1" else "Port2Sheet"
        x_key = "port1_x" if port.name == "Port1" else "port2_x"
        lines.extend(
            [
                f"    oEditor.CreateRectangle Array(\"NAME:RectangleParameters\", \"XStart:=\", \"{x_key}\", "
                f"\"YStart:=\", \"-port_width/2\", \"ZStart:=\", \"{z_start}\", "
                f"\"Width:=\", \"port_width\", \"Height:=\", \"port_height\", \"WhichAxis:=\", \"X\"), "
                f'{_hfss_attrs(sheet, "vacuum")}',
                f"    oModule.AssignWavePort Array(\"NAME:{port.name}\", \"Objects:=\", Array(\"{sheet}\"), "
                f"\"NumModes:=\", 1), Array(\"NAME:Modes\", Array(\"NAME:Mode1\", \"ModeNum:=\", 1, "
                f"\"UseIntLine:=\", false))",
            ]
        )
    lines.extend(["End Sub", ""])
    return lines


def _hfss_analysis_setup() -> list[str]:
    return [
        "Sub InsertAnalysisSetup(oDesign)",
        "    Dim oModule",
        "    Set oModule = oDesign.GetModule(\"AnalysisSetup\")",
        "    On Error Resume Next",
        '    oModule.DeleteSetup "Setup1"',
        "    On Error GoTo 0",
        "    oModule.InsertSetup \"HfssDriven\", Array(\"NAME:Setup1\", _",
        '        "Frequency:=", "center_freq_ghz&\"GHz\", _',
        '        "MaxDeltaS:=", 0.02, _',
        '        "MaximumPasses:=", 15, _',
        '        "MinimumPasses:=", 1, _',
        '        "MinimumConvergedPasses:=", 1, _',
        '        "IsEnabled:=", true)',
        "End Sub",
        "",
    ]


def build_hfss_script_text(geometry: SIWGeometry) -> str:
    """Build HFSS VBScript macro from SIW geometry."""
    via_call = "CreateSlotVias" if geometry.is_slot else "CreateCircularVias"
    lines: list[str] = [
        "' HFSS VBScript macro - SIW via structure (parametric)",
        "' Run: Tools > Run Script, or paste into Scripting editor",
        "' Requires: Ansys Electronics Desktop with HFSS; open/create a project first",
        "' Units: mm, GHz | Origin: XY center, Z at stack center",
        "' Re-run script after editing design variables in HFSS",
        "",
        "Dim oAnsoftApp, oDesktop, oProject, oDesign, oEditor",
        "",
        "Sub Main()",
        "    Set oAnsoftApp = CreateObject(\"AnsoftHfss.HfssScriptInterface\")",
        "    Set oDesktop = oAnsoftApp.GetAppDesktop()",
        "    oDesktop.RestoreWindow",
        "    Set oProject = oDesktop.GetActiveProject()",
        "    If oProject Is Nothing Then",
        '        MsgBox "Please open or create an HFSS project first.", vbExclamation',
        "        Exit Sub",
        "    End If",
        "    On Error Resume Next",
        f'    oProject.DeleteDesign "{_DESIGN_NAME}"',
        "    On Error GoTo 0",
        f'    Set oDesign = oProject.InsertDesign("HFSS", "{_DESIGN_NAME}", "DrivenModal", "")',
        "    oDesign.SetSolutionType \"DrivenModal\"",
        "    oDesign.SetModelUnits Array(\"NAME:Units Parameter\", \"Units:=\", \"mm\")",
        "",
        "    Call DefineVariables(oDesign)",
        "    Call EnsureSubstrateMaterial(oProject)",
        "",
        "    Set oEditor = oDesign.SetActiveEditor(\"3D Modeler\")",
        "    Call BuildStack(oEditor)",
        f"    Call {via_call}(oDesign, oEditor)",
        "    Call DefinePorts(oDesign)",
        "    Call InsertAnalysisSetup(oDesign)",
        "",
        "    oProject.Save",
        f'    MsgBox "HFSS design {_DESIGN_NAME} created.", vbInformation',
        "End Sub",
        "",
        "Call Main()",
        "",
    ]
    lines.extend(_hfss_define_variables(geometry))
    lines.extend(_hfss_material_sub())
    lines.extend(_hfss_stack_geometry())
    if geometry.is_slot:
        lines.extend(_hfss_slot_via_subs())
    else:
        lines.extend(_hfss_circular_via_subs())
    lines.extend(_hfss_ports_sub(geometry))
    lines.extend(_hfss_analysis_setup())
    return "\n".join(lines) + "\n"


def export_hfss_script(geometry: SIWGeometry, output_path: str | Path) -> Path:
    """Write HFSS VBScript macro to disk."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_hfss_script_text(geometry), encoding="utf-8")
    return output
