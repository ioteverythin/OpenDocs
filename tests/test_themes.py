"""Tests for the theme system."""

from __future__ import annotations

import pytest

from ioteverything.generators.themes import (
    CORPORATE_THEME,
    DEFAULT_THEME,
    OCEAN_THEME,
    Theme,
    get_theme,
    list_themes,
    register_theme,
)
from ioteverything.generators.styles import Colors, apply_theme, reset_theme


class TestThemeRegistry:
    def test_list_themes_returns_builtin(self):
        themes = list_themes()
        names = [t.name for t in themes]
        assert "corporate" in names
        assert "ocean" in names
        assert "sunset" in names
        assert "dark" in names
        assert "minimal" in names
        assert "emerald" in names
        assert "royal" in names

    def test_get_theme_returns_correct_theme(self):
        t = get_theme("ocean")
        assert t is OCEAN_THEME

    def test_get_theme_case_insensitive(self):
        t = get_theme("OCEAN")
        assert t is OCEAN_THEME

    def test_get_theme_unknown_raises(self):
        with pytest.raises(KeyError):
            get_theme("nonexistent")

    def test_default_is_corporate(self):
        assert DEFAULT_THEME is CORPORATE_THEME

    def test_register_custom_theme(self):
        from ioteverything.generators.themes import ThemeColors, ThemeFonts, ThemeLayout

        custom = Theme(
            name="test_custom",
            colors=ThemeColors(
                primary=(255, 0, 0),
                primary_dark=(200, 0, 0),
                primary_light=(255, 100, 100),
                secondary=(0, 255, 0),
                accent=(0, 0, 255),
                heading=(50, 50, 50),
                text=(30, 30, 30),
                muted=(150, 150, 150),
                bg_light=(245, 245, 245),
                code_bg=(40, 40, 40),
                code_text=(220, 220, 220),
                code_bg_light=(240, 240, 240),
                table_header_bg=(100, 0, 0),
                table_border=(200, 200, 200),
                table_alt_row=(250, 250, 250),
                success=(0, 200, 0),
                warning=(255, 200, 0),
                danger=(200, 0, 0),
                info=(0, 150, 200),
                white=(255, 255, 255),
            ),
            fonts=ThemeFonts(heading="Arial", body="Arial", code="Courier"),
            layout=ThemeLayout(),
        )
        register_theme(custom)
        names = [t.name for t in list_themes()]
        assert "test_custom" in names
        assert get_theme("test_custom") is custom


class TestApplyTheme:
    def test_apply_changes_colors(self):
        original_primary = Colors.PRIMARY
        ocean = get_theme("ocean")
        apply_theme(ocean)
        assert Colors.PRIMARY == ocean.colors.primary
        reset_theme()
        assert Colors.PRIMARY == original_primary

    def test_reset_restores_corporate(self):
        apply_theme(get_theme("sunset"))
        assert Colors.PRIMARY != CORPORATE_THEME.colors.primary
        reset_theme()
        assert Colors.PRIMARY == CORPORATE_THEME.colors.primary


class TestThemeDataclass:
    def test_theme_has_required_fields(self):
        t = get_theme("corporate")
        assert hasattr(t, "colors")
        assert hasattr(t, "fonts")
        assert hasattr(t, "layout")
        assert hasattr(t.colors, "primary")
        assert hasattr(t.fonts, "heading")
        assert hasattr(t.layout, "page_margin_inches")

    def test_all_themes_have_valid_colors(self):
        for theme in list_themes():
            # Each color should be an RGB tuple
            for field in ["primary", "accent", "heading", "text"]:
                c = getattr(theme.colors, field)
                assert isinstance(c, tuple), f"{theme.name}.{field} is not tuple"
                assert len(c) == 3, f"{theme.name}.{field} length != 3"
                assert all(0 <= v <= 255 for v in c), f"{theme.name}.{field} out of range"
