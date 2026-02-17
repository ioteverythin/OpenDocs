"""Pluggable theming system for all generators.

Themes define colors, fonts, and layout values. Every generator receives
a ``Theme`` instance and uses it instead of hardcoded constants.

Usage::

    from ioteverything.generators.themes import get_theme, list_themes

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
    code: str = "Consolas"

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
    fonts=ThemeFonts(heading="Segoe UI", body="Segoe UI", code="Cascadia Code"),
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
    fonts=ThemeFonts(heading="Arial", body="Arial", code="Courier New"),
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
