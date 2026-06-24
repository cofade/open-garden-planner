"""Integration tests for the click-to-toggle / hover-peek sidebar accordion (US-226).

End-to-end against the real ``GardenPlannerApp``: every panel starts collapsed;
a header click toggles open/closed without reordering the list; selecting a
plant/bed auto-opens the matching contextual panels; and an auto-opened panel can
be closed with a single click (and stays closed for that selection).
"""

# ruff: noqa: ARG001, ARG002, ARG005

from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.widgets.panel_stack import PanelState, PinSource


def _make_app(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    # A dirty project would pop a close prompt and block headless teardown.
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


def _add_plant(win, name="Tomato") -> CircleItem:
    plant = CircleItem(
        center_x=50, center_y=50, radius=20, object_type=ObjectType.TREE, name=name
    )
    plant.metadata["plant_species"] = {"common_name": name}
    win.canvas_scene.addItem(plant)
    return plant


def _add_bed(win) -> RectangleItem:
    bed = RectangleItem(
        x=0, y=0, width=200, height=100, object_type=ObjectType.GARDEN_BED, name="Bed 1"
    )
    win.canvas_scene.addItem(bed)
    return bed


def test_startup_all_collapsed(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    assert ctrl.pinned_keys() == []
    for key in ctrl.panel_keys():
        assert ctrl.state_of(key) is PanelState.COLLAPSED


def test_click_toggles_open_and_closed(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    header = ctrl.panel("layers").header

    header.pin_toggled.emit(True)  # simulate a title-bar click
    assert ctrl.state_of("layers") is PanelState.PINNED
    assert ctrl._entries["layers"].pin_source is PinSource.USER

    header.pin_toggled.emit(True)
    assert ctrl.state_of("layers") is PanelState.COLLAPSED


def test_opening_a_panel_does_not_reorder(qtbot, monkeypatch):
    """The reported bug: toggling a panel moved it to the end of the list."""
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    layout = ctrl._layout
    panels = ctrl.panels()
    before = [layout.indexOf(p) for p in panels]

    ctrl.panel("properties").header.pin_toggled.emit(True)  # open the first panel
    after = [layout.indexOf(p) for p in panels]
    assert before == after


def test_plant_selection_autopins_details_and_companion(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    plant = _add_plant(win)

    plant.setSelected(True)
    assert ctrl.state_of("plant_details") is PanelState.PINNED
    assert ctrl.state_of("companion") is PanelState.PINNED

    win.canvas_scene.clearSelection()
    assert ctrl.state_of("plant_details") is PanelState.COLLAPSED
    assert ctrl.state_of("companion") is PanelState.COLLAPSED


def test_bed_selection_autopins_crop_rotation(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    bed = _add_bed(win)

    bed.setSelected(True)
    assert ctrl.state_of("crop_rotation") is PanelState.PINNED
    assert ctrl.state_of("plant_details") is PanelState.COLLAPSED

    win.canvas_scene.clearSelection()
    assert ctrl.state_of("crop_rotation") is PanelState.COLLAPSED


def test_companion_closable_while_plant_selected(qtbot, monkeypatch):
    """The reported bug: with a plant selected, 'Companion' could not be closed."""
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    plant = _add_plant(win)

    plant.setSelected(True)
    assert ctrl.state_of("companion") is PanelState.PINNED

    ctrl.panel("companion").header.pin_toggled.emit(True)  # user clicks to close
    assert ctrl.state_of("companion") is PanelState.COLLAPSED

    # A re-notify for the same selection (e.g. scene change) must not reopen it.
    win._update_companion_panel()
    assert ctrl.state_of("companion") is PanelState.COLLAPSED


def test_reselecting_reopens_dismissed_panel(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    p1 = _add_plant(win, "Tomato")
    p2 = _add_plant(win, "Basil")

    p1.setSelected(True)
    ctrl.panel("companion").header.pin_toggled.emit(True)  # dismiss for p1
    assert ctrl.state_of("companion") is PanelState.COLLAPSED

    win.canvas_scene.clearSelection()
    p2.setSelected(True)  # genuine selection change → dismissal reset
    assert ctrl.state_of("companion") is PanelState.PINNED


def test_user_pin_survives_selection_clear(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    ctrl.panel("layers").header.pin_toggled.emit(True)  # USER pin, not selection
    win.canvas_scene.clearSelection()
    assert ctrl.state_of("layers") is PanelState.PINNED


def test_contextual_panels_hidden_until_relevant(qtbot, monkeypatch):
    """The selection-driven panels are hidden entirely until a matching item is
    selected — no empty placeholder bars (restored pre-US-226 behaviour)."""
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    contextual = ("plant_details", "companion", "crop_rotation")

    # Startup: nothing selected → all three hidden.
    for key in contextual:
        assert ctrl.panel(key).isHidden(), f"{key} should start hidden"

    # Plant selected → Plant Details + Companion shown; Crop Rotation stays hidden.
    plant = _add_plant(win)
    plant.setSelected(True)
    assert not ctrl.panel("plant_details").isHidden()
    assert not ctrl.panel("companion").isHidden()
    assert ctrl.panel("crop_rotation").isHidden()

    # Bed selected → Crop Rotation shown; plant panels hidden again.
    win.canvas_scene.clearSelection()
    bed = _add_bed(win)
    bed.setSelected(True)
    assert not ctrl.panel("crop_rotation").isHidden()
    assert ctrl.panel("plant_details").isHidden()
    assert ctrl.panel("companion").isHidden()


def test_non_plant_non_bed_selection_hides_all_contextual(qtbot, monkeypatch):
    """The reported issue: selecting a non-plant/non-bed object must not leave an
    openable empty Plant Details panel."""
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    house = RectangleItem(
        x=0, y=0, width=100, height=50, object_type=ObjectType.HOUSE, name="House"
    )
    win.canvas_scene.addItem(house)
    house.setSelected(True)
    for key in ("plant_details", "companion", "crop_rotation"):
        assert ctrl.panel(key).isHidden(), f"{key} should be hidden for a non-plant"
