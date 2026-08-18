"""The plant-search debounce timer must die with its dialog (#310 battery
finding, 2026-08-18; §11.4 "unparented QTimer outlives its dialog").

An unparented ``QTimer()`` armed by typing into the search box kept ticking
after the dialog was closed and deleted; 500 ms later it called
``_perform_search`` on a dead dialog, which opened a modal
``QMessageBox.warning(self)`` → Windows heap corruption (0xc0000374) inside
whatever test happened to be processing events at that moment. The timer is
now parented to the dialog and stopped in ``done()``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from open_garden_planner.services.plant_api import PlantAPIManager
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog


def test_debounce_timer_is_parented_and_stopped_on_done(qtbot, monkeypatch) -> None:  # noqa: ARG001
    dlg = PlantSearchDialog(PlantAPIManager(trefle_api_token="fake-token"))
    qtbot.addWidget(dlg)
    assert dlg._search_timer.parent() is dlg, "timer must be owned by the dialog"

    performed = MagicMock()
    monkeypatch.setattr(dlg, "_perform_search", performed)
    dlg._search_timer.timeout.disconnect()
    dlg._search_timer.timeout.connect(performed)

    dlg.search_input.setText("carrot")  # arms the 500 ms debounce
    assert dlg._search_timer.isActive()
    dlg.done(0)  # close/reject/accept all route through done()
    assert not dlg._search_timer.isActive()
    qtbot.wait(700)
    performed.assert_not_called()


def test_direct_search_settles_the_pending_debounce(qtbot, monkeypatch) -> None:  # noqa: ARG001
    """The pattern every dialog test uses — type, then call `_perform_search()`
    directly — must not leave the 500 ms timer armed behind it (the probe on
    2026-08-18 showed all 17 such calls in the battery leaving it armed)."""
    from unittest.mock import MagicMock

    dlg = PlantSearchDialog(PlantAPIManager(trefle_api_token="fake-token"))
    qtbot.addWidget(dlg)
    monkeypatch.setattr(dlg._api_manager, "search", MagicMock(return_value=[]))
    dlg.search_input.setText("carrot")
    assert dlg._search_timer.isActive()
    dlg._perform_search()
    assert not dlg._search_timer.isActive(), "a synchronous search must disarm the debounce"
