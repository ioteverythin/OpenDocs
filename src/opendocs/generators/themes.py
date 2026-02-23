"""Pluggable theming system for all generators.

Themes define colors, fonts, and layout values. Every generator receives
a ``Theme`` instance and uses it instead of hardcoded constants.

Usage::

    from opendocs.generators.themes import get_theme, list_themes

    theme = get_theme("ocean")
    gen = WordGenerator(theme=theme)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Theme dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ThemeColors:
    """All color slots used across generators. Values are RGB tuples."""

    # Brand / primary
    primary: tuple[int, int, int] = (0, 102, 204)
    primary_dark: tuple[int, int, int] = (0, 71, 153)
    primary_light: tuple[int, int, int] = (102, 178, 255)
    secondary: tuple[int, int, int] = (51, 51, 51)
    accent: tuple[int, int, int] = (255, 153, 0)
    accent_soft: tuple[int, int, int] = (255, 200, 120)

    # Text
    heading: tuple[int, int, int] = (0, 51, 102)
    text: tuple[int, int, int] = (33, 33, 33)
    muted: tuple[int, int, int] = (128, 128, 128)
    caption: tuple[int, int, int] = (100, 100, 100)

    # Backgrounds
    white: tuple[int, int, int] = (255, 255, 255)
    bg_light: tuple[int, int, int] = (245, 247, 250)
    bg_warm: tuple[int, int, int] = (253, 249, 243)
    bg_section: tuple[int, int, int] = (235, 241, 250)

    # Tables
    table_header_bg: tuple[int, int, int] = (0, 82, 164)
    table_alt_row: tuple[int, int, int] = (240, 245, 255)
    table_border: tuple[int, int, int] = (180, 200, 220)

    # Code
    code_bg: tuple[int, int, int] = (40, 44, 52)
    code_text: tuple[int, int, int] = (171, 178, 191)
    code_bg_light: tuple[int, int, int] = (245, 245, 245)

    # Status
    success: tuple[int, int, int] = (40, 167, 69)
    warning: tuple[int, int, int] = (255, 193, 7)
    danger: tuple[int, int, int] = (220, 53, 69)
    info: tuple[int, int, int] = (23, 162, 184)

    # Slides
    slide_title_bg: tuple[int, int, int] = (0, 82, 164)
    slide_accent_bar: tuple[int, int, int] = (255, 153, 0)


@dataclass(frozen=True)
class ThemeFonts:
    """Font family and size configuration."""

    heading: str = "Calibri"
    body: str = "Calibri"
    code: str = "Courier"

    title_size_pt: int = 36
    h1_size_pt: int = 24
    h2_size_pt: int = 20
    h3_size_pt: int = 16
    h4_size_pt: int = 13
    body_size_pt: int = 11
    code_size_pt: int = 9
    caption_size_pt: int = 9
    small_size_pt: int = 8


@dataclass(frozen=True)
class ThemeLayout:
    """Layout constants."""

    page_margin_inches: float = 1.0
    slide_width_inches: float = 13.333
    slide_height_inches: float = 7.5
    space_after_heading: int = 6
    space_after_paragraph: int = 4
    space_before_section: int = 12
    code_block_padding: int = 8


@dataclass(frozen=True)
class Theme:
    """Complete theme definition."""

    name: str = "corporate"
    display_name: str = "Corporate Blue"
    description: str = "Professional blue theme suitable for business reports."
    colors: ThemeColors = field(default_factory=ThemeColors)
    fonts: ThemeFonts = field(default_factory=ThemeFonts)
    layout: ThemeLayout = field(default_factory=ThemeLayout)


# ---------------------------------------------------------------------------
# Built-in themes
# ---------------------------------------------------------------------------

CORPORATE_THEME = Theme(
    name="corporate",
    display_name="Corporate Blue",
    description="Professional blue theme for business and technical reports.",
    colors=ThemeColors(
        primary=(0, 102, 204),
        primary_dark=(0, 71, 153),
        primary_light=(102, 178, 255),
        secondary=(51, 51, 51),
        accent=(255, 153, 0),
        accent_soft=(255, 200, 120),
        heading=(0, 51, 102),
        text=(33, 33, 33),
        muted=(128, 128, 128),
        table_header_bg=(0, 82, 164),
        table_alt_row=(240, 245, 255),
        slide_title_bg=(0, 82, 164),
        slide_accent_bar=(255, 153, 0),
    ),
)

OCEAN_THEME = Theme(
    name="ocean",
    display_name="Ocean Teal",
    description="Calm teal and seafoam theme for a modern, approachable look.",
    colors=ThemeColors(
        primary=(0, 150, 136),
        primary_dark=(0, 105, 92),
        primary_light=(128, 203, 196),
        secondary=(55, 71, 79),
        accent=(255, 112, 67),
        accent_soft=(255, 171, 145),
        heading=(0, 77, 64),
        text=(38, 50, 56),
        muted=(120, 144, 156),
        caption=(96, 125, 139),
        bg_light=(232, 245, 233),
        bg_section=(224, 242, 241),
        table_header_bg=(0, 121, 107),
        table_alt_row=(232, 245, 233),
        table_border=(178, 223, 219),
        code_bg=(38, 50, 56),
        code_text=(176, 190, 197),
        code_bg_light=(236, 239, 241),
        slide_title_bg=(0, 121, 107),
        slide_accent_bar=(255, 112, 67),
    ),
    fonts=ThemeFonts(heading="Segoe UI", body="Segoe UI"),
)

SUNSET_THEME = Theme(
    name="sunset",
    display_name="Sunset Warm",
    description="Warm amber, coral and earth tones for a bold, creative look.",
    colors=ThemeColors(
        primary=(230, 74, 25),
        primary_dark=(191, 54, 12),
        primary_light=(255, 138, 101),
        secondary=(62, 39, 35),
        accent=(255, 179, 0),
        accent_soft=(255, 213, 79),
        heading=(121, 44, 0),
        text=(40, 26, 22),
        muted=(141, 110, 99),
        caption=(109, 76, 65),
        bg_light=(255, 248, 241),
        bg_warm=(255, 243, 224),
        bg_section=(255, 236, 210),
        table_header_bg=(191, 54, 12),
        table_alt_row=(255, 243, 224),
        table_border=(215, 189, 167),
        code_bg=(50, 30, 20),
        code_text=(210, 180, 160),
        code_bg_light=(255, 248, 241),
        slide_title_bg=(191, 54, 12),
        slide_accent_bar=(255, 179, 0),
    ),
    fonts=ThemeFonts(heading="Georgia", body="Calibri"),
)

DARK_THEME = Theme(
    name="dark",
    display_name="Dark Elegance",
    description="Dark background with vibrant accents for a sleek, modern look.",
    colors=ThemeColors(
        primary=(100, 181, 246),
        primary_dark=(66, 165, 245),
        primary_light=(144, 202, 249),
        secondary=(224, 224, 224),
        accent=(255, 167, 38),
        accent_soft=(255, 202, 40),
        heading=(130, 177, 255),
        text=(220, 220, 220),
        muted=(158, 158, 158),
        caption=(176, 176, 176),
        white=(48, 48, 48),
        bg_light=(55, 55, 60),
        bg_warm=(50, 50, 55),
        bg_section=(60, 63, 70),
        table_header_bg=(55, 71, 100),
        table_alt_row=(50, 53, 60),
        table_border=(80, 85, 95),
        code_bg=(30, 30, 35),
        code_text=(180, 200, 220),
        code_bg_light=(45, 45, 50),
        slide_title_bg=(33, 33, 48),
        slide_accent_bar=(255, 167, 38),
    ),
    fonts=ThemeFonts(heading="Segoe UI", body="Segoe UI", code="Courier"),
)

MINIMAL_THEME = Theme(
    name="minimal",
    display_name="Minimal Mono",
    description="Clean black-and-white with subtle gray accents. Maximum readability.",
    colors=ThemeColors(
        primary=(50, 50, 50),
        primary_dark=(30, 30, 30),
        primary_light=(120, 120, 120),
        secondary=(80, 80, 80),
        accent=(0, 0, 0),
        accent_soft=(160, 160, 160),
        heading=(20, 20, 20),
        text=(30, 30, 30),
        muted=(140, 140, 140),
        caption=(110, 110, 110),
        bg_light=(250, 250, 250),
        bg_warm=(248, 248, 248),
        bg_section=(242, 242, 242),
        table_header_bg=(50, 50, 50),
        table_alt_row=(248, 248, 248),
        table_border=(210, 210, 210),
        code_bg=(245, 245, 245),
        code_text=(50, 50, 50),
        code_bg_light=(245, 245, 245),
        slide_title_bg=(30, 30, 30),
        slide_accent_bar=(100, 100, 100),
    ),
    fonts=ThemeFonts(heading="Arial", body="Arial", code="Courier"),
)

EMERALD_THEME = Theme(
    name="emerald",
    display_name="Emerald Forest",
    description="Rich green and gold tones inspired by nature.",
    colors=ThemeColors(
        primary=(46, 125, 50),
        primary_dark=(27, 94, 32),
        primary_light=(129, 199, 132),
        secondary=(33, 33, 33),
        accent=(255, 193, 7),
        accent_soft=(255, 224, 130),
        heading=(27, 94, 32),
        text=(33, 37, 41),
        muted=(108, 117, 125),
        caption=(85, 95, 85),
        bg_light=(232, 245, 233),
        bg_warm=(241, 248, 233),
        bg_section=(220, 237, 200),
        table_header_bg=(27, 94, 32),
        table_alt_row=(232, 245, 233),
        table_border=(165, 214, 167),
        code_bg=(25, 35, 25),
        code_text=(160, 200, 160),
        code_bg_light=(241, 248, 233),
        slide_title_bg=(27, 94, 32),
        slide_accent_bar=(255, 193, 7),
    ),
    fonts=ThemeFonts(heading="Cambria", body="Calibri"),
)

ROYAL_THEME = Theme(
    name="royal",
    display_name="Royal Purple",
    description="Regal purple and gold for a premium, distinguished feel.",
    colors=ThemeColors(
        primary=(103, 58, 183),
        primary_dark=(69, 39, 160),
        primary_light=(179, 157, 219),
        secondary=(49, 27, 146),
        accent=(255, 215, 0),
        accent_soft=(255, 235, 59),
        heading=(49, 27, 146),
        text=(33, 33, 33),
        muted=(130, 119, 158),
        caption=(106, 90, 140),
        bg_light=(243, 237, 255),
        bg_warm=(248, 242, 255),
        bg_section=(237, 231, 246),
        table_header_bg=(69, 39, 160),
        table_alt_row=(243, 237, 255),
        table_border=(206, 192, 230),
        code_bg=(35, 25, 55),
        code_text=(200, 180, 230),
        code_bg_light=(243, 237, 255),
        slide_title_bg=(69, 39, 160),
        slide_accent_bar=(255, 215, 0),
    ),
    fonts=ThemeFonts(heading="Palatino Linotype", body="Calibri"),
)


SLATE_THEME = Theme(
    name="slate",
    display_name="Slate Professional",
    description="Cool blue-gray tones for a polished, enterprise-grade look.",
    colors=ThemeColors(
        primary=(69, 90, 100),
        primary_dark=(38, 50, 56),
        primary_light=(144, 164, 174),
        secondary=(55, 71, 79),
        accent=(38, 166, 154),
        accent_soft=(128, 203, 196),
        heading=(38, 50, 56),
        text=(33, 33, 33),
        muted=(120, 144, 156),
        caption=(96, 125, 139),
        bg_light=(236, 239, 241),
        bg_warm=(240, 242, 245),
        bg_section=(227, 232, 238),
        table_header_bg=(55, 71, 79),
        table_alt_row=(236, 239, 241),
        table_border=(176, 190, 197),
        code_bg=(38, 50, 56),
        code_text=(176, 190, 197),
        code_bg_light=(236, 239, 241),
        slide_title_bg=(38, 50, 56),
        slide_accent_bar=(38, 166, 154),
    ),
    fonts=ThemeFonts(heading="Segoe UI", body="Segoe UI"),
)

ROSE_THEME = Theme(
    name="rose",
    display_name="Rosé Blush",
    description="Soft pink and rose-gold tones for an elegant, refined aesthetic.",
    colors=ThemeColors(
        primary=(183, 28, 28),
        primary_dark=(136, 14, 79),
        primary_light=(239, 154, 154),
        secondary=(62, 39, 35),
        accent=(255, 171, 145),
        accent_soft=(248, 187, 208),
        heading=(136, 14, 79),
        text=(38, 30, 35),
        muted=(158, 130, 140),
        caption=(130, 110, 120),
        bg_light=(253, 242, 245),
        bg_warm=(252, 228, 236),
        bg_section=(248, 220, 230),
        table_header_bg=(136, 14, 79),
        table_alt_row=(253, 242, 245),
        table_border=(225, 190, 200),
        code_bg=(45, 30, 38),
        code_text=(220, 180, 195),
        code_bg_light=(253, 242, 245),
        slide_title_bg=(136, 14, 79),
        slide_accent_bar=(255, 171, 145),
    ),
    fonts=ThemeFonts(heading="Georgia", body="Calibri"),
)

NORDIC_THEME = Theme(
    name="nordic",
    display_name="Nordic Frost",
    description="Inspired by Scandinavian design — icy blues, white space, and clean lines.",
    colors=ThemeColors(
        primary=(94, 129, 172),
        primary_dark=(59, 66, 82),
        primary_light=(136, 192, 208),
        secondary=(76, 86, 106),
        accent=(191, 97, 106),
        accent_soft=(208, 135, 112),
        heading=(46, 52, 64),
        text=(59, 66, 82),
        muted=(122, 130, 150),
        caption=(108, 118, 138),
        bg_light=(236, 239, 244),
        bg_warm=(242, 244, 248),
        bg_section=(229, 233, 240),
        table_header_bg=(59, 66, 82),
        table_alt_row=(236, 239, 244),
        table_border=(180, 190, 205),
        code_bg=(46, 52, 64),
        code_text=(216, 222, 233),
        code_bg_light=(236, 239, 244),
        slide_title_bg=(59, 66, 82),
        slide_accent_bar=(191, 97, 106),
    ),
    fonts=ThemeFonts(heading="Segoe UI", body="Segoe UI"),
)

CYBER_THEME = Theme(
    name="cyber",
    display_name="Cyberpunk Neon",
    description="Electric neon on dark backgrounds — bold, futuristic, high-contrast.",
    colors=ThemeColors(
        primary=(0, 255, 159),
        primary_dark=(0, 200, 120),
        primary_light=(102, 255, 191),
        secondary=(180, 180, 220),
        accent=(255, 0, 128),
        accent_soft=(255, 102, 178),
        heading=(0, 230, 140),
        text=(210, 210, 230),
        muted=(140, 140, 170),
        caption=(160, 160, 190),
        white=(18, 18, 30),
        bg_light=(25, 25, 42),
        bg_warm=(22, 22, 38),
        bg_section=(30, 30, 50),
        table_header_bg=(20, 20, 40),
        table_alt_row=(28, 28, 48),
        table_border=(60, 60, 100),
        code_bg=(12, 12, 20),
        code_text=(0, 255, 159),
        code_bg_light=(25, 25, 42),
        slide_title_bg=(15, 15, 28),
        slide_accent_bar=(255, 0, 128),
    ),
    fonts=ThemeFonts(heading="Consolas", body="Segoe UI", code="Consolas"),
)

TERRACOTTA_THEME = Theme(
    name="terracotta",
    display_name="Terracotta Earth",
    description="Warm clay, sand, and ochre tones — organic and grounded.",
    colors=ThemeColors(
        primary=(175, 89, 62),
        primary_dark=(140, 65, 42),
        primary_light=(210, 140, 115),
        secondary=(82, 66, 55),
        accent=(192, 157, 70),
        accent_soft=(218, 195, 130),
        heading=(120, 55, 35),
        text=(55, 42, 35),
        muted=(145, 125, 110),
        caption=(125, 105, 90),
        bg_light=(250, 244, 237),
        bg_warm=(248, 240, 228),
        bg_section=(242, 230, 215),
        table_header_bg=(140, 65, 42),
        table_alt_row=(250, 244, 237),
        table_border=(210, 190, 170),
        code_bg=(50, 38, 30),
        code_text=(210, 185, 165),
        code_bg_light=(248, 240, 228),
        slide_title_bg=(140, 65, 42),
        slide_accent_bar=(192, 157, 70),
    ),
    fonts=ThemeFonts(heading="Cambria", body="Calibri"),
)

SAPPHIRE_THEME = Theme(
    name="sapphire",
    display_name="Sapphire Night",
    description="Deep navy and bright sapphire blue for a premium, high-end feel.",
    colors=ThemeColors(
        primary=(30, 60, 160),
        primary_dark=(20, 40, 120),
        primary_light=(90, 130, 220),
        secondary=(30, 30, 80),
        accent=(0, 200, 255),
        accent_soft=(102, 220, 255),
        heading=(15, 30, 100),
        text=(25, 25, 60),
        muted=(100, 105, 140),
        caption=(80, 85, 130),
        bg_light=(235, 238, 252),
        bg_warm=(230, 234, 250),
        bg_section=(220, 226, 248),
        table_header_bg=(20, 40, 120),
        table_alt_row=(235, 238, 252),
        table_border=(170, 180, 220),
        code_bg=(15, 20, 50),
        code_text=(140, 170, 230),
        code_bg_light=(235, 238, 252),
        slide_title_bg=(20, 40, 120),
        slide_accent_bar=(0, 200, 255),
    ),
    fonts=ThemeFonts(heading="Calibri", body="Calibri"),
)

MINT_THEME = Theme(
    name="mint",
    display_name="Fresh Mint",
    description="Light mint green and charcoal — crisp, clean, and easy on the eyes.",
    colors=ThemeColors(
        primary=(0, 175, 137),
        primary_dark=(0, 137, 107),
        primary_light=(105, 215, 185),
        secondary=(50, 60, 60),
        accent=(255, 183, 77),
        accent_soft=(255, 213, 140),
        heading=(0, 110, 85),
        text=(35, 45, 45),
        muted=(110, 135, 130),
        caption=(90, 115, 110),
        bg_light=(235, 250, 245),
        bg_warm=(240, 252, 247),
        bg_section=(218, 245, 235),
        table_header_bg=(0, 137, 107),
        table_alt_row=(235, 250, 245),
        table_border=(170, 220, 205),
        code_bg=(30, 45, 40),
        code_text=(160, 210, 195),
        code_bg_light=(235, 250, 245),
        slide_title_bg=(0, 137, 107),
        slide_accent_bar=(255, 183, 77),
    ),
    fonts=ThemeFonts(heading="Segoe UI", body="Segoe UI"),
)

MONOCHROME_THEME = Theme(
    name="monochrome",
    display_name="High Contrast",
    description="Pure black and white with zero color — maximum accessibility and print-friendliness.",
    colors=ThemeColors(
        primary=(0, 0, 0),
        primary_dark=(0, 0, 0),
        primary_light=(80, 80, 80),
        secondary=(40, 40, 40),
        accent=(0, 0, 0),
        accent_soft=(120, 120, 120),
        heading=(0, 0, 0),
        text=(0, 0, 0),
        muted=(100, 100, 100),
        caption=(80, 80, 80),
        bg_light=(255, 255, 255),
        bg_warm=(255, 255, 255),
        bg_section=(240, 240, 240),
        table_header_bg=(0, 0, 0),
        table_alt_row=(245, 245, 245),
        table_border=(180, 180, 180),
        code_bg=(240, 240, 240),
        code_text=(0, 0, 0),
        code_bg_light=(245, 245, 245),
        slide_title_bg=(0, 0, 0),
        slide_accent_bar=(80, 80, 80),
    ),
    fonts=ThemeFonts(heading="Arial", body="Arial", code="Courier"),
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_THEME_REGISTRY: dict[str, Theme] = {
    t.name: t
    for t in [
        CORPORATE_THEME,
        OCEAN_THEME,
        SUNSET_THEME,
        DARK_THEME,
        MINIMAL_THEME,
        EMERALD_THEME,
        ROYAL_THEME,
        SLATE_THEME,
        ROSE_THEME,
        NORDIC_THEME,
        CYBER_THEME,
        TERRACOTTA_THEME,
        SAPPHIRE_THEME,
        MINT_THEME,
        MONOCHROME_THEME,
    ]
}


def get_theme(name: str) -> Theme:
    """Get a theme by name. Raises ``KeyError`` if not found."""
    key = name.lower().strip()
    if key not in _THEME_REGISTRY:
        available = ", ".join(sorted(_THEME_REGISTRY.keys()))
        raise KeyError(f"Unknown theme '{name}'. Available: {available}")
    return _THEME_REGISTRY[key]


def list_themes() -> list[Theme]:
    """Return all registered themes."""
    return list(_THEME_REGISTRY.values())


def register_theme(theme: Theme) -> None:
    """Register a custom theme at runtime."""
    _THEME_REGISTRY[theme.name.lower().strip()] = theme


# Convenience: default theme
DEFAULT_THEME = CORPORATE_THEME
