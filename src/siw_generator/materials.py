"""Substrate material catalog for SIW design."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubstrateMaterial:
    """Laminate electrical parameters used in SIW sizing."""

    key: str
    name: str
    er: float
    tan_delta: float
    description: str
    cst_material_name: str = ""
    cst_library: bool = True

    def __post_init__(self) -> None:
        if not self.cst_material_name:
            object.__setattr__(self, "cst_material_name", self.name)


ALUMINA_96_LOSSY = SubstrateMaterial(
    key="alumina96_lossy",
    name="Alumina (96%) (lossy)",
    er=9.6,
    tan_delta=0.002,
    description="Alumina 96%, er≈9.6, lossy",
)

RT5880_LOSS_FREE = SubstrateMaterial(
    key="rt5880_loss_free",
    name="Rogers RT-duroid 5880 (loss free)",
    er=2.20,
    tan_delta=0.0,
    description="RT/duroid 5880, er=2.20, loss-free",
)

RT5880_LOSSY = SubstrateMaterial(
    key="rt5880_lossy",
    name="Rogers RT-duroid 5880 (lossy)",
    er=2.20,
    tan_delta=0.0009,
    description="RT/duroid 5880, er=2.20, tanδ=0.0009 @10GHz",
)

RO3003_LOSS_FREE = SubstrateMaterial(
    key="ro3003_loss_free",
    name="Rogers RO3003 (loss free)",
    er=3.00,
    tan_delta=0.0,
    description="RO3003, er=3.00, loss-free",
)

RO3003_LOSSY = SubstrateMaterial(
    key="ro3003_lossy",
    name="Rogers RO3003 (lossy)",
    er=3.00,
    tan_delta=0.0013,
    description="RO3003, er=3.00, tanδ=0.0013 @10GHz",
)

RT5880 = RT5880_LOSSY

DEFAULT_SUBSTRATE_KEY = RT5880_LOSSY.key

SUBSTRATE_MATERIAL_ORDER: tuple[str, ...] = (
    ALUMINA_96_LOSSY.key,
    RT5880_LOSS_FREE.key,
    RT5880_LOSSY.key,
    RO3003_LOSS_FREE.key,
    RO3003_LOSSY.key,
)

SUBSTRATE_MATERIALS: dict[str, SubstrateMaterial] = {
    mat.key: mat
    for mat in (
        ALUMINA_96_LOSSY,
        RT5880_LOSS_FREE,
        RT5880_LOSSY,
        RO3003_LOSS_FREE,
        RO3003_LOSSY,
    )
}


def substrate_display_names() -> list[str]:
    """CST-exact material names for GUI combobox."""
    return [SUBSTRATE_MATERIALS[key].cst_material_name for key in SUBSTRATE_MATERIAL_ORDER]


def default_substrate_display_name() -> str:
    return SUBSTRATE_MATERIALS[DEFAULT_SUBSTRATE_KEY].cst_material_name


def resolve_material_key(display_or_key: str) -> str:
    """Map combobox label or internal key to catalog key."""
    text = display_or_key.strip()
    if not text:
        return DEFAULT_SUBSTRATE_KEY
    lowered = text.lower().replace(" ", "").replace("/", "").replace("-", "")
    if lowered in SUBSTRATE_MATERIALS:
        return lowered
    for key in SUBSTRATE_MATERIAL_ORDER:
        mat = SUBSTRATE_MATERIALS[key]
        if text == mat.cst_material_name or text == mat.name or text == mat.key:
            return key
    aliases = {
        "5880": RT5880_LOSSY.key,
        "duroid5880": RT5880_LOSSY.key,
        "rtduroid5880": RT5880_LOSSY.key,
        "rogers5880": RT5880_LOSSY.key,
        "rt5880": RT5880_LOSSY.key,
    }
    if lowered in aliases:
        return aliases[lowered]
    return lowered if lowered in SUBSTRATE_MATERIALS else DEFAULT_SUBSTRATE_KEY


def get_material(key: str) -> SubstrateMaterial:
    resolved = resolve_material_key(key)
    try:
        return SUBSTRATE_MATERIALS[resolved]
    except KeyError as exc:
        available = ", ".join(substrate_display_names())
        raise ValueError(f"Unknown material '{key}'. Available: {available}") from exc
