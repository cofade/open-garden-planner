"""Integration tests for the hover-peek / click-to-pin sidebar accordion (US-226).

End-to-end against the real ``GardenPlannerApp``: every panel starts collapsed;
a header click pins/unpins; multiple pins share the splitter; and selecting a
plant/bed auto-pins the matching contextual panels (unpinning on clear).
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
    for panel in ctrl.panels():
        key = next(k for k, p in win._tracked_panels.items() if p is panel)
        assert ctrl.state_of(key) is PanelState.COLLAPSED


def test_click_pins_and_unpins(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    header = win._tracked_panels["layers"].header

    header.pin_toggled.emit(True)  # simulate a title-bar click
    assert ctrl.state_of("layers") is PanelState.PINNED
    assert ctrl._entries["layers"].pin_source is PinSource.USER

    header.pin_toggled.emit(True)
    assert ctrl.state_of("layers") is PanelState.COLLAPSED


def test_multiple_pins_share_space(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    win.resize(1200, 900)
    win.show()

    win._tracked_panels["layers"].header.pin_toggled.emit(True)
    win._tracked_panels["constraints"].header.pin_toggled.emit(True)
    qtbot.wait(50)  # let the deferred equalize run

    assert ctrl.pinned_keys() == ["layers", "constraints"]
    sizes = ctrl._splitter.sizes()
    assert len(sizes) == 2
    assert abs(sizes[0] - sizes[1]) <= 2


def test_plant_selection_autopins_details_and_companion(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    plant = _add_plant(win)

    plant.setSelected(True)
    assert ctrl.state_of("plant_details") is PanelState.PINNED
    assert ctrl.state_of("companion") is PanelState.PINNED
    assert ctrl._entries["plant_details"].pin_source is PinSource.SELECTION

    win.canvas_scene.clearSelection()
    assert ctrl.state_of("plant_details") is PanelState.COLLAPSED
    assert ctrl.state_of("companion") is PanelState.COLLAPSED


def test_bed_selection_autopins_crop_rotation(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    bed = _add_bed(win)

    bed.setSelected(True)
    assert ctrl.state_of("crop_rotation") is PanelState.PINNED
    # A bed is not a plant, so the plant panels stay collapsed.
    assert ctrl.state_of("plant_details") is PanelState.COLLAPSED

    win.canvas_scene.clearSelection()
    assert ctrl.state_of("crop_rotation") is PanelState.COLLAPSED


def test_user_pin_survives_selection_clear(qtbot, monkeypatch):
    win = _make_app(qtbot, monkeypatch)
    ctrl = win._sidebar_controller
    plant = _add_plant(win)

    plant.setSelected(True)
    assert ctrl.state_of("plant_details") is PanelState.PINNED
    # User clicks the auto-pinned panel -> upgrade to a USER pin.
    win._tracked_panels["plant_details"].header.pin_toggled.emit(True)
    assert ctrl._entries["plant_details"].pin_source is PinSource.USER

    win.canvas_scene.clearSelection()
    assert ctrl.state_of("plant_details") is PanelState.PINNED  # survives clear
