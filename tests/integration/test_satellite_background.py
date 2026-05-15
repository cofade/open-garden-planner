"""Integration: the satellite-background menu item is wired correctly.

With the API key set we get a clickable menu action; without it the menu
item is grayed out. The full handler path is covered indirectly by the
unit tests on its building blocks (see note below).
"""

# ruff: noqa: ARG002

from __future__ import annotations

# QtWebEngineWidgets must be imported before QApplication is created. The
# dialog itself imports it, so loading the module early — at the top of
# this test file — keeps the test running with qtbot's app.
from PyQt6 import QtWebEngineWidgets  # noqa: F401, I001
from PyQt6.QtGui import QAction

import open_garden_planner.ui.dialogs.map_picker_dialog as map_picker_mod  # noqa: F401


def _menu_action(win, label_fragment: str) -> QAction | None:
    """Find a top-level menu action whose text contains ``label_fragment``."""
    for menu_action in win.menuBar().actions():
        menu = menu_action.menu()
        if menu is None:
            continue
        for act in menu.actions():
            if label_fragment in act.text():
                return act
    return None


class TestMenuActionGating:
    def test_action_disabled_when_no_key(self, qtbot, monkeypatch) -> None:
        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)
        action = _menu_action(win, "Satellite")
        assert action is not None
        assert action.isEnabled() is False

    def test_action_enabled_when_key_set(self, qtbot, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)
        action = _menu_action(win, "Satellite")
        assert action is not None
        assert action.isEnabled() is True


# Note on coverage:
# The actual ``_on_load_satellite_background`` handler is short (<30 lines of
# glue: open dialog → read fetch_result → replace existing BackgroundImageItem
# → addItem). Its individual pieces are exercised elsewhere:
#   - Menu-action wiring/gating: ``TestMenuActionGating`` above.
#   - Dialog ↔ JS bridge contract:    ``tests/integration/test_map_picker_dialog.py``.
#   - HTTP/tile-math/mosaic:          ``tests/unit/test_google_maps_service.py``.
#   - Geo metadata + auto-scale:      ``tests/unit/test_background_image_item_geo.py``.
#   - Canvas centering math regression: ``test_background_image_item_geo.py::TestCenteringWithScale``.
# A full end-to-end test that constructs ``GardenPlannerApp`` and drives the
# handler hangs pytest-qt teardown (Qt thread/timer cleanup issue, not a
# logic bug — the test itself passes when run in isolation). The end-to-end
# path is therefore covered by manual smoke testing per the project workflow.
