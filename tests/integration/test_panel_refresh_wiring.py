"""Command-stack → panel refresh wiring (follow-up to #206/#222).

The properties panel's in-place value refresh landed in #222. This file covers
the *wiring* side that #222 left on the table:

  * the constraints + properties + plant-database panels are all driven by a
    single ``stack_changed`` connection (one refresh per command), not the old
    three-signal ``command_executed`` + ``can_undo_changed`` + ``can_redo_changed``
    fan-out; and
  * the **plant-database panel now refreshes on undo/redo** — previously it was
    wired only to ``selectionChanged`` / ``object_type_changed``, so undoing a
    species assignment while the plant stayed selected left its details stale.

``can_undo/redo_changed`` stay wired to the toolbar Undo/Redo action enablement
only (their real job).
"""

# ruff: noqa: ARG001, ARG002, ARG005

from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.core.commands import MoveItemsCommand
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.panels import ConstraintsPanel
from open_garden_planner.ui.panels.companion_panel import CompanionPanel
from open_garden_planner.ui.panels.crop_rotation_panel import CropRotationPanel


def _silence_close_prompt(monkeypatch) -> None:
    """Executing a command marks the project dirty; the close prompt would then
    block headless teardown. Auto-discard so qtbot can tear the window down."""
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: QMessageBox.StandardButton.Discard,
    )


def _make_app(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    _silence_close_prompt(monkeypatch)
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


class TestStackChangedDrivesPanels:
    """One refresh per stack mutation, across execute/undo/redo."""

    def test_each_panel_refreshes_once_on_execute_undo_redo(self, qtbot, monkeypatch) -> None:
        # The constraints panel is wired with ``stack_changed.connect(
        # self.constraints_panel.refresh)`` — a bound method captured at wiring
        # time, so patch the *class* method before the app is built (an instance
        # patch would be invisible to the already-bound connection).
        constraint_calls: list[int] = []
        orig_constraint = ConstraintsPanel.refresh

        def _spy_refresh(self):
            constraint_calls.append(1)
            return orig_constraint(self)

        monkeypatch.setattr(ConstraintsPanel, "refresh", _spy_refresh)

        win = _make_app(qtbot, monkeypatch)

        item = RectangleItem(0, 0, 100, 50)
        win.canvas_scene.addItem(item)
        item.setSelected(True)

        prop_calls: list[int] = []
        plant_calls: list[int] = []

        orig_prop = win.properties_panel.set_selected_items
        orig_plant = win.plant_database_panel.set_selected_items

        monkeypatch.setattr(
            win.properties_panel,
            "set_selected_items",
            lambda items: (prop_calls.append(len(items)), orig_prop(items))[1],
        )
        monkeypatch.setattr(
            win.plant_database_panel,
            "set_selected_items",
            lambda items: (plant_calls.append(len(items)), orig_plant(items))[1],
        )

        mgr = win.canvas_view.command_manager

        for action in ("execute", "undo", "redo"):
            prop_calls.clear()
            plant_calls.clear()
            constraint_calls.clear()
            if action == "execute":
                mgr.execute(MoveItemsCommand([item], QPointF(10, 0)))
            else:
                getattr(mgr, action)()
            qtbot.waitUntil(lambda: len(prop_calls) >= 1 and len(plant_calls) >= 1)

            assert prop_calls == [1], f"properties panel: one refresh on {action}"
            # The key regression guard: the plant-database panel must refresh on
            # undo/redo too, not just on selection change.
            assert plant_calls == [1], f"plant DB panel: one refresh on {action}"
            # Constraints panel: exactly one refresh per command (was up to 3×).
            assert constraint_calls == [1], f"constraints panel: one refresh on {action}"

    def test_undo_redo_actions_still_track_manager(self, qtbot, monkeypatch) -> None:
        win = _make_app(qtbot, monkeypatch)

        item = RectangleItem(0, 0, 100, 50)
        win.canvas_scene.addItem(item)
        mgr = win.canvas_view.command_manager

        mgr.execute(MoveItemsCommand([item], QPointF(10, 0)))
        assert win._undo_action.isEnabled(), "can_undo_changed still drives the toolbar"
        assert not win._redo_action.isEnabled()

        mgr.undo()
        assert not win._undo_action.isEnabled()
        assert win._redo_action.isEnabled()


class TestCompanionCropRotationRefreshOnUndoRedo:
    """#225: companion + crop-rotation panels were wired only to selectionChanged,
    so undo/redo of a species/reparent change left them stale. They are now wired
    to ``stack_changed`` as well — assert they refresh on undo and redo."""

    def test_panels_refresh_on_undo_redo(self, qtbot, monkeypatch) -> None:
        companion_calls: list[int] = []
        crop_calls: list[int] = []
        orig_comp = CompanionPanel.update_for_plant
        orig_crop = CropRotationPanel.update_for_bed

        def _spy_comp(self, item):
            companion_calls.append(1)
            return orig_comp(self, item)

        def _spy_crop(self, item, area_id):
            crop_calls.append(1)
            return orig_crop(self, item, area_id)

        # Patch the class methods before the app is built (the bound-method
        # connections are captured at wiring time).
        monkeypatch.setattr(CompanionPanel, "update_for_plant", _spy_comp)
        monkeypatch.setattr(CropRotationPanel, "update_for_bed", _spy_crop)

        win = _make_app(qtbot, monkeypatch)
        item = RectangleItem(0, 0, 100, 50)
        win.canvas_scene.addItem(item)
        item.setSelected(True)
        mgr = win.canvas_view.command_manager

        mgr.execute(MoveItemsCommand([item], QPointF(10, 0)))
        for action in ("undo", "redo"):
            companion_calls.clear()
            crop_calls.clear()
            getattr(mgr, action)()
            qtbot.waitUntil(lambda: bool(companion_calls) and bool(crop_calls))
            assert companion_calls, f"companion panel must refresh on {action} (#225)"
            assert crop_calls, f"crop-rotation panel must refresh on {action} (#225)"
