"""Integration gate (§8.10) for the Package-3c iconography migration (#310).

`tests/integration/test_icon_system.py` covers the main window (menus, View
submenus, status bar, tabs, theme refresh). This file covers the panel- and
widget-level sites that used to render emoji / unicode pseudo-icons or a
private `QSvgRenderer` path, proving each now shows a PROVIDER icon (a real
pixmap, no glyph text) and — where the widget opts in — re-tints on a theme
switch through `refresh_theme_icons`.
"""

# ruff: noqa: ARG001, ARG002

import uuid

import pytest
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication

from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.panels.constraints_panel import ConstraintListItem
from open_garden_planner.ui.panels.layers_panel import LayerListItem
from open_garden_planner.ui.panels.plant_search_panel import PlantSearchPanel
from open_garden_planner.ui.theme import ThemeMode, apply_theme
from open_garden_planner.ui.widgets.collapsible_panel import CollapsiblePanel
from open_garden_planner.ui.widgets.sun_sim_toolbar import SunSimToolbar


def _img(pixmap: QPixmap) -> QImage:
    return pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)


def _has_glyph(text: str) -> bool:
    """True if the text carries any symbol/emoji-range character (the class of
    pseudo-icons #310 removed)."""
    return any(ord(ch) >= 0x2190 for ch in text)


class TestLayersPanelProviderIcons:
    def test_eye_and_lock_are_provider_icons_and_retint(self, qtbot) -> None:
        item = LayerListItem(Layer(name="Test"))
        qtbot.addWidget(item)
        assert not item.visibility_btn.icon().isNull()
        assert not item.lock_btn.icon().isNull()
        app = QApplication.instance()
        apply_theme(app, ThemeMode.LIGHT)
        try:
            light = _img(item.visibility_btn.icon().pixmap(QSize(20, 20)))
            apply_theme(app, ThemeMode.DARK)  # propagates refresh_theme_icons to the item
            dark = _img(item.visibility_btn.icon().pixmap(QSize(20, 20)))
            assert light != dark, "layer eye icon did not re-tint on theme switch"
        finally:
            apply_theme(app, ThemeMode.LIGHT)

    def test_state_changes_swap_icons(self, qtbot) -> None:
        """The buttons only emit; the panel pushes the new state back through
        `update_layer` (pre-existing flow) — that path must swap eye/eye_off
        and lock/lock_open."""
        layer = Layer(name="Test", visible=True, locked=False)
        item = LayerListItem(layer)
        qtbot.addWidget(item)
        open_eye = _img(item.visibility_btn.icon().pixmap(QSize(20, 20)))
        open_lock = _img(item.lock_btn.icon().pixmap(QSize(20, 20)))
        item.update_layer(Layer(name="Test", visible=False, locked=True, id=layer.id))
        assert _img(item.visibility_btn.icon().pixmap(QSize(20, 20))) != open_eye
        assert _img(item.lock_btn.icon().pixmap(QSize(20, 20))) != open_lock


class TestPanelsAndWidgets:
    def test_plant_search_type_filters_carry_icons_not_emoji(self, qtbot) -> None:
        panel = PlantSearchPanel()
        qtbot.addWidget(panel)
        for checkbox in (panel.tree_checkbox, panel.shrub_checkbox, panel.perennial_checkbox):
            assert not checkbox.icon().isNull()
            assert not _has_glyph(checkbox.text()), checkbox.text()

    @pytest.mark.parametrize("type_name", ["FIXED", "TANGENT", "COINCIDENT", "HORIZONTAL_DISTANCE", "ANGLE"])
    def test_constraint_row_shows_type_icon_and_no_glyph_prefix(self, qtbot, type_name: str) -> None:
        row = ConstraintListItem(uuid.uuid4(), "Bed A", "Bed B", 120.0, True, type_name)
        qtbot.addWidget(row)
        from PyQt6.QtWidgets import QLabel

        labels = row.findChildren(QLabel)
        pixmap_labels = [lbl for lbl in labels if lbl.pixmap() is not None and not lbl.pixmap().isNull()]
        assert len(pixmap_labels) >= 2, "status dot + type icon expected"
        text_labels = [lbl.text() for lbl in labels if lbl.text()]
        assert text_labels and not any(_has_glyph(t) for t in text_labels), text_labels

    def test_collapsible_panel_chevron_is_a_pixmap(self, qtbot) -> None:
        panel = CollapsiblePanel("Title", expanded=True)
        qtbot.addWidget(panel)
        assert panel._indicator.pixmap() is not None and not panel._indicator.pixmap().isNull()
        assert panel._indicator.text() == ""
        expanded_img = _img(panel._indicator.pixmap())
        panel.set_expanded(False, emit=False)
        assert _img(panel._indicator.pixmap()) != expanded_img
        panel.set_info_tooltip("hint")
        assert panel._info_label.pixmap() is not None and not panel._info_label.pixmap().isNull()

    def test_sun_sim_toolbar_buttons_carry_icons(self, qtbot) -> None:
        bar = SunSimToolbar()
        qtbot.addWidget(bar)
        assert not bar._animate_button.icon().isNull()
        assert not bar._heatmap_button.icon().isNull()
        assert bar._time_icon.pixmap() is not None and not bar._time_icon.pixmap().isNull()
        play = _img(bar._animate_button.icon().pixmap(QSize(20, 20)))
        bar._animate_button.setChecked(True)  # play → pause
        assert _img(bar._animate_button.icon().pixmap(QSize(20, 20))) != play
        bar._animate_button.setChecked(False)


class TestNoEmojiInChromeSources:
    """Static guard: the emoji / pictograph ranges must not reappear as chrome
    text in the migrated modules (textual arrows in messages are allowed —
    only the pictograph and dingbat ranges the migration removed are banned)."""

    BANNED = [
        (0x1F300, 0x1FAFF),  # emoji pictographs (🌳 🌿 🌸 🌱 📷 🔄 🔒 🌫 🌧 …)
        (0x2600, 0x26FF),    # misc symbols (☀ ⛅ ⛈ ★ ● ⚠ ❄ …)
        (0x2700, 0x27BF),    # dingbats (✓ ✗ …)
    ]
    MODULES = [
        "app/application.py",
        "ui/panels/layers_panel.py",
        "ui/panels/plant_search_panel.py",
        "ui/panels/companion_panel.py",
        "ui/panels/journal_panel.py",
        "ui/panels/constraints_panel.py",
        "ui/views/planting_calendar_view.py",
        "ui/views/tasks_view.py",
        "ui/views/seed_inventory_view.py",
        "ui/dialogs/seed_inventory_dialog.py",
        "ui/dialogs/season_manager_dialog.py",
        "ui/widgets/collapsible_panel.py",
        "ui/widgets/weather_widget.py",
        "services/weather_service.py",
        "ui/theme.py",
    ]

    @pytest.mark.parametrize("module", MODULES)
    def test_no_banned_glyph_in_code(self, module: str) -> None:
        from pathlib import Path

        src = Path(__file__).parents[2] / "src" / "open_garden_planner" / module
        offenders = []
        for lineno, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]  # comments may mention the old glyphs
            for ch in code:
                if any(lo <= ord(ch) <= hi for lo, hi in self.BANNED):
                    offenders.append((lineno, line.strip()[:80]))
                    break
        assert offenders == [], offenders
