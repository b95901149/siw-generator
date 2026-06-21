"""Example: generate CST import package for RT5880 SIW."""

from siw_generator.generator import generate_siw_cst

if __name__ == "__main__":
    result = generate_siw_cst(
        "output/cst",
        substrate_length_mm=10.0,
        substrate_width_mm=10.0,
        substrate_height_mm=0.127,
        copper_thickness_um=15.0,
        center_freq_ghz=120.0,
        via_diameter_mm=0.15,
        material="rt5880",
    )
    print(result)
