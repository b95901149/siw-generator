"""Command-line interface for SIW generator."""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from siw_generator.generator import generate_siw_cst, generate_siw_dxf
from siw_generator.materials import DEFAULT_SUBSTRATE_KEY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate SIW sidewall via pattern (DXF / CST package)",
    )
    parser.add_argument(
        "--format",
        choices=("dxf", "cst"),
        default="cst",
        help="Output format: cst package (default) or single dxf",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output path (dxf file or cst folder); default auto under CST/",
    )
    parser.add_argument("--name", default="SIW", help="Design name for CST folder")
    parser.add_argument("--substrate-length", type=float, default=10.0)
    parser.add_argument("--substrate-width", type=float, default=10.0)
    parser.add_argument("--substrate-height", type=float, default=0.127,
                        help="Dielectric thickness in mm (default: 0.127)")
    parser.add_argument("--copper-um", type=float, default=15.0,
                        help="Copper thickness per side in um (default: 15)")
    parser.add_argument("--freq", type=float, default=120.0)
    parser.add_argument("--via-diameter", type=float, default=0.15)
    parser.add_argument("--material", default=DEFAULT_SUBSTRATE_KEY)
    parser.add_argument("--er", type=float, default=None)
    parser.add_argument("--siw-width", type=float, default=None)
    parser.add_argument("--via-pitch", type=float, default=None)
    parser.add_argument("--edge-margin", type=float, default=0.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    from siw_generator.console_encoding import configure_console_encoding

    configure_console_encoding()
    args = build_parser().parse_args(argv)
    common = dict(
        substrate_length_mm=args.substrate_length,
        substrate_width_mm=args.substrate_width,
        center_freq_ghz=args.freq,
        via_diameter_mm=args.via_diameter,
        material=args.material,
        er=args.er,
        substrate_height_mm=args.substrate_height,
        copper_thickness_um=args.copper_um,
        edge_margin_mm=args.edge_margin,
        siw_width_mm=args.siw_width,
        via_pitch_mm=args.via_pitch,
    )

    if args.format == "cst":
        result = generate_siw_cst(
            output_dir=args.output,
            project_root=Path.cwd(),
            design_name=args.name,
            **common,
        )
    else:
        output_path = args.output or "output/siw_vias.dxf"
        result = generate_siw_dxf(
            output_path,
            cst_mode=True,
            **common,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
