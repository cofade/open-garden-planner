"""Unit tests for the themed icon provider (ui/icons.py — #279, ADR-039)."""

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import QApplication

from open_garden_planner.ui import icons
from open_garden_planner.ui.theme import ThemeMode, apply_theme


def _image(pixmap: QPixmap) -> QImage:
    return pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _has_visible_pixels(pixmap: QPixmap) -> bool:
    image = _image(pixmap)
    return any(
        image.pixelColor(x, y).alpha() > 0
        for x in range(image.width())
        for y in range(image.height())
    )


def _contains_color(pixmap: QPixmap, target: QColor, tolerance: int = 40) -> bool:
    image = _image(pixmap)
    for x in range(image.width()):
        for y in range(image.height()):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() < 200:
                continue
            distance = (
                abs(pixel.red() - target.red())
                + abs(pixel.green() - target.green())
                + abs(pixel.blue() - target.blue())
            )
            if distance <= tolerance:
                return True
    return False


class TestIconProvider:
    def test_available_icons_covers_the_set(self, qtbot) -> None:  # noqa: ARG002
        names = icons.available_icons()
        assert len(names) >= 70
        assert "select" in names
        assert "constraint_distance" in names
        assert "garden_bed" in names

    def test_get_icon_renders_visible_pixels(self, qtbot) -> None:  # noqa: ARG002
        icon = icons.get_icon("select")
        assert icon is not None
        assert _has_visible_pixels(icon.pixmap(QSize(24, 24)))

    def test_unknown_name_returns_none(self, qtbot) -> None:  # noqa: ARG002
        assert icons.get_icon("definitely_not_an_icon") is None
        assert icons.get_pixmap("definitely_not_an_icon") is None
        assert icons.get_icon("") is None

    def test_color_override_changes_pixels(self, qtbot) -> None:  # noqa: ARG002
        default = icons.get_pixmap("measure", size=32)
        red = icons.get_pixmap("measure", size=32, color="#ff0000")
        assert default is not None and red is not None
        assert _image(default) != _image(red)
        assert _contains_color(red, QColor("#ff0000"))

    def test_accent_sentinel_maps_to_theme_accent(self, qtbot) -> None:  # noqa: ARG002
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            pixmap = icons.get_pixmap("garden_bed", size=64)
            assert pixmap is not None
            # The three seedling dots carry the sentinel -> light accent.
            assert _contains_color(pixmap, QColor("#3d8b37"))

            apply_theme(app, ThemeMode.DARK)
            dark_pixmap = icons.get_pixmap("garden_bed", size=64)
            assert dark_pixmap is not None
            assert _contains_color(dark_pixmap, QColor("#66bb6a"))
        finally:
            apply_theme(app, ThemeMode.LIGHT)

    def test_disabled_mode_is_grayed(self, qtbot) -> None:  # noqa: ARG002
        icon = icons.get_icon("constraint_distance")
        assert icon is not None
        normal = icon.pixmap(QSize(24, 24), QIcon.Mode.Normal)
        disabled = icon.pixmap(QSize(24, 24), QIcon.Mode.Disabled)
        assert _has_visible_pixels(disabled)
        assert _image(normal) != _image(disabled)

    def test_cache_returns_same_icon_object(self, qtbot) -> None:  # noqa: ARG002
        first = icons.get_icon("undo")
        second = icons.get_icon("undo")
        assert first is second

    def test_theme_switch_invalidates_cache(self, qtbot) -> None:  # noqa: ARG002
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            light = icons.get_pixmap("tree", size=24)
            apply_theme(app, ThemeMode.DARK)
            dark = icons.get_pixmap("tree", size=24)
            assert light is not None and dark is not None
            # Dark text_primary differs from light -> different pixels.
            assert _image(light) != _image(dark)
        finally:
            apply_theme(app, ThemeMode.LIGHT)
