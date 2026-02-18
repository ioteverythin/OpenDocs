"""Shared styles and theming constants for all generators.

These module-level classes are the *active* color/font/layout values.
Call ``apply_theme(theme)`` to reconfigure them from a ``Theme`` object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .themes import Theme


# ---------------------------------------------------------------------------
# Color palette (RGB tuples) — mutable via apply_theme()
# ---------------------------------------------------------------------------

class Colors:
    # Brand
    PRIMARY = (0, 102, 204)          # Core blue
    PRIMARY_DARK = (0, 71, 153)      # Darker blue for depth
    PRIMARY_LIGHT = (102, 178, 255)  # Light blue for accents
    SECONDARY = (51, 51, 51)         # Dark gray
    ACCENT = (255, 153, 0)           # Orange
    ACCENT_SOFT = (255, 200, 120)    # Soft orange

    # Text
    HEADING = (0, 51, 102)           # Dark blue
    TEXT = (33, 33, 33)              # Near-black
    MUTED = (128, 128, 128)          # Gray
    CAPTION = (100, 100, 100)        # Slightly darker gray

    # Backgrounds
    WHITE = (255, 255, 255)
    BG_LIGHT = (245, 247, 250)       # Light blue-gray
    BG_WARM = (253, 249, 243)        # Warm off-white
    BG_SECTION = (235, 241, 250)     # Section header background

    # Tables
    TABLE_HEADER_BG = (0, 82, 164)   # Deep blue
    TABLE_ALT_ROW = (240, 245, 255)  # Light blue tint
    TABLE_BORDER = (180, 200, 220)   # Soft border

    # Code
    CODE_BG = (40, 44, 52)           # Dark code background (One Dark)
    CODE_TEXT = (171, 178, 191)      # Light gray text on dark bg
    CODE_BG_LIGHT = (245, 245, 245)  # Light fallback for PDF

    # Status / Semantic
    SUCCESS = (40, 167, 69)          # Green
    WARNING = (255, 193, 7)          # Yellow
    DANGER = (220, 53, 69)           # Red
    INFO = (23, 162, 184)            # Cyan

    # Slide-specific
    SLIDE_GRADIENT_TOP = (0, 82, 164)
    SLIDE_GRADIENT_BOTTOM = (0, 51, 102)
    SLIDE_ACCENT_BAR = (255, 153, 0)  # Orange accent stripe


# ---------------------------------------------------------------------------
# Font configuration
# ---------------------------------------------------------------------------

class Fonts:
    HEADING = "Calibri"
    BODY = "Calibri"
    CODE = "Consolas"

    TITLE_SIZE_PT = 36
    H1_SIZE_PT = 24
    H2_SIZE_PT = 20
    H3_SIZE_PT = 16
    H4_SIZE_PT = 13
    BODY_SIZE_PT = 11
    CODE_SIZE_PT = 9
    CAPTION_SIZE_PT = 9
    SMALL_SIZE_PT = 8


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

class Layout:
    """Page / slide layout constants."""
    PAGE_MARGIN_INCHES = 1.0
    SLIDE_WIDTH_INCHES = 13.333
    SLIDE_HEIGHT_INCHES = 7.5

    # Spacing (in points)
    SPACE_AFTER_HEADING = 6
    SPACE_AFTER_PARAGRAPH = 4
    SPACE_BEFORE_SECTION = 12
    CODE_BLOCK_PADDING = 8


# ---------------------------------------------------------------------------
# Theme application
# ---------------------------------------------------------------------------

def apply_theme(theme: Theme) -> None:
    """Reconfigure the module-level Colors/Fonts/Layout from a Theme object.

    After calling this, all generators that reference ``Colors.PRIMARY``
    etc. will pick up the themed values automatically.
    """
    c = theme.colors
    Colors.PRIMARY = c.primary
    Colors.PRIMARY_DARK = c.primary_dark
    Colors.PRIMARY_LIGHT = c.primary_light
    Colors.SECONDARY = c.secondary
    Colors.ACCENT = c.accent
    Colors.ACCENT_SOFT = c.accent_soft
    Colors.HEADING = c.heading
    Colors.TEXT = c.text
    Colors.MUTED = c.muted
    Colors.CAPTION = c.caption
    Colors.WHITE = c.white
    Colors.BG_LIGHT = c.bg_light
    Colors.BG_WARM = c.bg_warm
    Colors.BG_SECTION = c.bg_section
    Colors.TABLE_HEADER_BG = c.table_header_bg
    Colors.TABLE_ALT_ROW = c.table_alt_row
    Colors.TABLE_BORDER = c.table_border
    Colors.CODE_BG = c.code_bg
    Colors.CODE_TEXT = c.code_text
    Colors.CODE_BG_LIGHT = c.code_bg_light
    Colors.SLIDE_GRADIENT_TOP = c.slide_title_bg
    Colors.SLIDE_GRADIENT_BOTTOM = c.primary_dark
    Colors.SLIDE_ACCENT_BAR = c.slide_accent_bar

    f = theme.fonts
    Fonts.HEADING = f.heading
    Fonts.BODY = f.body
    Fonts.CODE = f.code
    Fonts.TITLE_SIZE_PT = f.title_size_pt
    Fonts.H1_SIZE_PT = f.h1_size_pt
    Fonts.H2_SIZE_PT = f.h2_size_pt
    Fonts.H3_SIZE_PT = f.h3_size_pt
    Fonts.H4_SIZE_PT = f.h4_size_pt
    Fonts.BODY_SIZE_PT = f.body_size_pt
    Fonts.CODE_SIZE_PT = f.code_size_pt
    Fonts.CAPTION_SIZE_PT = f.caption_size_pt
    Fonts.SMALL_SIZE_PT = f.small_size_pt

    lay = theme.layout
    Layout.PAGE_MARGIN_INCHES = lay.page_margin_inches
    Layout.SLIDE_WIDTH_INCHES = lay.slide_width_inches
    Layout.SLIDE_HEIGHT_INCHES = lay.slide_height_inches
    Layout.SPACE_AFTER_HEADING = lay.space_after_heading
    Layout.SPACE_AFTER_PARAGRAPH = lay.space_after_paragraph
    Layout.SPACE_BEFORE_SECTION = lay.space_before_section
    Layout.CODE_BLOCK_PADDING = lay.code_block_padding


def reset_theme() -> None:
    """Reset styles back to corporate defaults."""
    from .themes import CORPORATE_THEME
    apply_theme(CORPORATE_THEME)
