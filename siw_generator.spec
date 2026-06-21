# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — build with .venv-build (scripts/build_exe.ps1)."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

_root = Path(SPECPATH)
_docs = _root / "docs" / "AGENT_HISTORY.md"
_guide = _root / "docs" / "USER_GUIDE.md"

datas = collect_data_files("matplotlib", include_py_files=False)
datas += collect_data_files("ezdxf", include_py_files=False)
if _docs.is_file():
    datas.append((str(_docs), "docs"))
if _guide.is_file():
    datas.append((str(_guide), "docs"))
_img_dir = _root / "docs" / "images"
if _img_dir.is_dir():
    for _img in _img_dir.glob("*.png"):
        datas.append((str(_img), "docs/images"))


def _conda_runtime_binaries() -> list[tuple[str, str]]:
    """Bundle Conda DLLs required by _ctypes, ssl, tkinter, etc."""
    root = Path(sys.base_prefix)
    lib_bin = root / "Library" / "bin"
    names = [
        "ffi.dll",
        "ffi-8.dll",
        "ffi-7.dll",
        "libbz2.dll",
        "liblzma.dll",
        "zlib.dll",
        "libcrypto-3-x64.dll",
        "libssl-3-x64.dll",
        "expat.dll",
        "tcl86t.dll",
        "tk86t.dll",
    ]
    binaries: list[tuple[str, str]] = []
    for name in names:
        path = lib_bin / name
        if path.is_file():
            binaries.append((str(path), "."))
    return binaries


binaries = _conda_runtime_binaries()

hiddenimports = [
    "siw_generator.gui_slot",
    "siw_generator.gui_cst_vba",
    "siw_generator.gui_hfss",
    "siw_generator.gui_custom",
    "siw_generator.gui_compose",
    "siw_generator.gui_module_panel",
    "siw_generator.gui_preview",
    "siw_generator.gui_help_panel",
    "siw_generator.gui_state",
    "siw_generator.recipe_io",
    "siw_generator.agent_history",
    "siw_generator.resource_info",
    "siw_generator.usage_guide_render",
    "siw_generator.slot_geometry",
    "siw_generator.via_shapes",
    "siw_generator.stl_export",
    "siw_generator.cst_export",
    "siw_generator.hfss_export",
    "siw_generator.custom_geometry",
    "siw_generator.custom_io",
    "siw_generator.custom_preview",
    "siw_generator.compose_geometry",
    "siw_generator.compose_preview",
    "siw_generator.compose_io",
    "siw_generator.operation_log",
    "siw_generator.param_report",
    "siw_generator.app_paths",
    "siw_generator.export_paths",
    "matplotlib.backends.backend_tkagg",
    "PIL._tkinter_finder",
]

excludes = [
    "cadquery",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "PySide6",
    "vtk",
    "pandas",
    "scipy",
    "IPython",
    "jupyter",
    "notebook",
    "bokeh",
    "dask",
    "plotly",
    "panel",
    "statsmodels",
    "skimage",
    "xarray",
    "torch",
    "tensorflow",
]

a = Analysis(
    ["scripts/gui_entry.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SIW-Generator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
