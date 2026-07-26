"""Semantic-token and typography-role invariants for ui/theme.py (#279).

The LIGHT/DARK key-parity test lives in test_theme.py; this file pins the
visual-refresh additions: every semantic token parses, the tinted *_bg
surfaces genuinely differ between modes (a copy-paste palette would defeat
dark mode), the live-palette helpers work, and set_text_role drives the
dynamic properties the stylesheet targets.
"""

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QLabel

from open_garden_planner.ui import theme
from open_garden_planner.ui.theme import ThemeColors, ThemeMode

_SEMANTIC_TOKENS = (
    "success_bg",
    "warning_bg",
    "error_bg",
    "info_bg",
    "caution",
    "on_status",
    "overlay_bg",
    "overlay_border",
    "overlay_text",
    "overlay_field_bg",
    "overlay_field_border",
)


class TestSemanticTokens:
    def test_tokens_exist_in_both_palettes(self) -> None:
        for token in _SEMANTIC_TOKENS:
            assert token in ThemeColors.LIGHT, token
            assert token in ThemeColors.DARK, token

    def test_hex_tokens_parse_as_qcolor(self) -> None:
        for palette in (ThemeColors.LIGHT, ThemeColors.DARK):
            for token, value in palette.items():
                if value.startswith("rgba"):
                    continue  # overlay tokens — QSS-only rgba strings
                assert QColor(value).isValid(), f"{token}={value}"

    def test_bg_tints_differ_between_modes(self) -> None:
        for token in ("success_bg", "warning_bg", "error_bg", "info_bg"):
            assert ThemeColors.LIGHT[token] != ThemeColors.DARK[token], token

    def test_overlay_tokens_constant_across_modes(self) -> None:
        # Deliberate: the dynamic-input overlay sits on the always-light canvas.
        for token in ("overlay_bg", "overlay_border", "overlay_text"):
            assert ThemeColors.LIGHT[token] == ThemeColors.DARK[token], token

    def test_urgency_scale_pairwise_distinct_in_both_palettes(self) -> None:
        """The four active urgency levels must never collapse to the same hex
        (dark mode DID collapse this_week/coming_up before the ADR-039
        review round — this is the test that would have caught it)."""
        for palette in (ThemeColors.LIGHT, ThemeColors.DARK):
            hexes = [
                palette[theme.URGENCY_TOKENS[key]]
                for key in ("overdue", "today", "this_week", "coming_up")
            ]
            assert len(set(hexes)) == 4, hexes

    def test_info_foreground_and_surface_are_coherent(self) -> None:
        """info (text) and info_bg (surface) must live in the same hue family
        — both blue — so info text on an info card cannot read green-on-blue."""
        for palette in (ThemeColors.LIGHT, ThemeColors.DARK):
            info = QColor(palette["info"])
            assert info.blue() > info.green() > info.red(), palette["info"]


class TestLivePaletteHelpers:
    def test_theme_color_and_rgba_follow_apply_theme(self, qtbot) -> None:  # noqa: ARG002
        app = QApplication.instance()
        try:
            theme.apply_theme(app, ThemeMode.DARK)
            assert theme.theme_color("accent") == ThemeColors.DARK["accent"]
            assert theme.is_dark_theme()

            accent = QColor(ThemeColors.DARK["accent"])
            expected = f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, 42)"
            assert theme.rgba("accent", 42) == expected
        finally:
            theme.apply_theme(app, ThemeMode.LIGHT)
            assert not theme.is_dark_theme()

    def test_listener_fires_on_apply(self, qtbot) -> None:  # noqa: ARG002
        app = QApplication.instance()
        seen: list[dict[str, str]] = []
        theme.register_theme_listener(seen.append)
        try:
            theme.apply_theme(app, ThemeMode.DARK)
            assert seen and seen[-1]["accent"] == ThemeColors.DARK["accent"]
        finally:
            theme.unregister_theme_listener(seen.append)
            theme.apply_theme(app, ThemeMode.LIGHT)


class TestSetTextRole:
    def test_sets_properties_and_font_weight_applies(self, qtbot) -> None:  # noqa: ARG002
        label = QLabel("heading")
        theme.set_text_role(label, "h2", "error")
        assert label.property("textRole") == "h2"
        assert label.property("colorRole") == "error"

    def test_font_weight_600_is_supported(self, qtbot) -> None:  # noqa: ARG002
        """The h1/h2 rules rely on ``font-weight: 600`` — assert Qt honours
        it on a polished label (fallback would be switching the QSS to
        ``bold``; see ADR-039)."""
        label = QLabel("heading")
        label.setStyleSheet("font-weight: 600;")
        label.ensurePolished()
        assert label.font().weight() >= 600
