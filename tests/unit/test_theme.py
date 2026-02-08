"""Tests for the branded green theme system."""

from PyQt6.QtGui import QColor

from open_garden_planner.ui.theme import ThemeColors, ThemeMode, generate_stylesheet


class TestThemeColors:
    """Test the ThemeColors class color palettes."""

    def test_light_theme_has_green_accent(self, qtbot) -> None:  # noqa: ARG002
        colors = ThemeColors.LIGHT
        accent = QColor(colors["accent"])
        # Green channel should dominate over red and blue
        assert accent.green() > accent.red()
        assert accent.green() > accent.blue()

    def test_dark_theme_has_green_accent(self, qtbot) -> None:  # noqa: ARG002
        colors = ThemeColors.DARK
        accent = QColor(colors["accent"])
        assert accent.green() > accent.red()
        assert accent.green() > accent.blue()

    def test_light_theme_has_canvas_outside_color(self, qtbot) -> None:  # noqa: ARG002
        assert "canvas_outside" in ThemeColors.LIGHT

    def test_dark_theme_has_canvas_outside_color(self, qtbot) -> None:  # noqa: ARG002
        assert "canvas_outside" in ThemeColors.DARK

    def test_light_theme_has_grid_colors(self, qtbot) -> None:  # noqa: ARG002
        assert "grid_line" in ThemeColors.LIGHT
        assert "grid_line_major" in ThemeColors.LIGHT

    def test_dark_theme_has_grid_colors(self, qtbot) -> None:  # noqa: ARG002
        assert "grid_line" in ThemeColors.DARK
        assert "grid_line_major" in ThemeColors.DARK

    def test_light_theme_has_scale_bar_colors(self, qtbot) -> None:  # noqa: ARG002
        assert "scale_bar_fg" in ThemeColors.LIGHT
        assert "scale_bar_outline" in ThemeColors.LIGHT

    def test_dark_theme_has_scale_bar_colors(self, qtbot) -> None:  # noqa: ARG002
        assert "scale_bar_fg" in ThemeColors.DARK
        assert "scale_bar_outline" in ThemeColors.DARK

    def test_light_theme_has_canvas_border(self, qtbot) -> None:  # noqa: ARG002
        assert "canvas_border" in ThemeColors.LIGHT

    def test_dark_theme_has_canvas_border(self, qtbot) -> None:  # noqa: ARG002
        assert "canvas_border" in ThemeColors.DARK

    def test_light_theme_has_accent_text(self, qtbot) -> None:  # noqa: ARG002
        assert "accent_text" in ThemeColors.LIGHT

    def test_dark_theme_has_accent_text(self, qtbot) -> None:  # noqa: ARG002
        assert "accent_text" in ThemeColors.DARK

    def test_get_colors_light(self, qtbot) -> None:  # noqa: ARG002
        colors = ThemeColors.get_colors(ThemeMode.LIGHT)
        assert colors is ThemeColors.LIGHT

    def test_get_colors_dark(self, qtbot) -> None:  # noqa: ARG002
        colors = ThemeColors.get_colors(ThemeMode.DARK)
        assert colors is ThemeColors.DARK

    def test_light_dark_differ(self, qtbot) -> None:  # noqa: ARG002
        assert ThemeColors.LIGHT["background"] != ThemeColors.DARK["background"]
        assert ThemeColors.LIGHT["accent"] != ThemeColors.DARK["accent"]

    def test_all_color_keys_consistent(self, qtbot) -> None:  # noqa: ARG002
        """Both themes must define the same set of keys."""
        assert set(ThemeColors.LIGHT.keys()) == set(ThemeColors.DARK.keys())


class TestGenerateStylesheet:
    """Test stylesheet generation."""

    def test_generates_string(self, qtbot) -> None:  # noqa: ARG002
        result = generate_stylesheet(ThemeMode.LIGHT)
        assert isinstance(result, str)
        assert len(result) > 100

    def test_contains_accent_color(self, qtbot) -> None:  # noqa: ARG002
        result = generate_stylesheet(ThemeMode.LIGHT)
        assert ThemeColors.LIGHT["accent"] in result

    def test_dark_stylesheet_differs(self, qtbot) -> None:  # noqa: ARG002
        light = generate_stylesheet(ThemeMode.LIGHT)
        dark = generate_stylesheet(ThemeMode.DARK)
        assert light != dark


class TestCanvasSceneTheme:
    """Test canvas scene theme color propagation."""

    def test_apply_theme_colors_updates_canvas(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene()
        colors = ThemeColors.DARK
        scene.apply_theme_colors(colors)
        assert QColor(colors["canvas_background"]) == scene.CANVAS_COLOR
        assert QColor(colors["canvas_outside"]) == scene.OUTSIDE_COLOR

    def test_default_canvas_color(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

        scene = CanvasScene()
        assert QColor("#f5f5dc") == scene.CANVAS_COLOR


class TestCanvasViewTheme:
    """Test canvas view theme color propagation."""

    def test_apply_theme_colors_updates_grid(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
        from open_garden_planner.ui.canvas.canvas_view import CanvasView

        scene = CanvasScene()
        view = CanvasView(scene)
        colors = ThemeColors.DARK
        view.apply_theme_colors(colors)
        assert view._canvas_border_color == QColor(colors["canvas_border"])

    def test_apply_theme_colors_updates_scale_bar(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
        from open_garden_planner.ui.canvas.canvas_view import CanvasView

        scene = CanvasScene()
        view = CanvasView(scene)
        colors = ThemeColors.DARK
        view.apply_theme_colors(colors)
        assert view._scale_bar_fg == QColor(colors["scale_bar_fg"])
