"""Integration test: File -> New Plan must not crash with a compare overlay
active (issue #337, US-10.7).

§8.10 policy: drive the real UI workflow, not just the scene-level methods
it calls — a unit test that hand-calls scene.clear() cannot see whether the
menu action itself is wired in a safe order.
"""

# ruff: noqa: ARG005

from PyQt6.QtWidgets import QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.ui.dialogs import NewProjectDialog

PLANT_OBJECTS = [
    {
        "type": "circle",
        "object_type": "TREE",
        "center_x": 200.0,
        "center_y": 150.0,
        "radius": 30.0,
        "fill_color": "#88cc88",
        "name": "Apfelbaum",
    },
]


def _make_app(qtbot, monkeypatch):
    # A dirty project would pop a close prompt and block headless teardown.
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard
    )
    # The startup sequence opens a MODAL Welcome dialog on a 500ms timer —
    # headless, its exec() blocks pytest-qt forever. See §11.4.
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda self: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


class TestNewPlanClearsCompareOverlay:
    """#337: File -> New Plan must not raise RuntimeError when a compare
    overlay (US-10.7) is active."""

    def test_new_plan_with_active_overlay_does_not_raise(
        self, qtbot, monkeypatch
    ) -> None:
        win = _make_app(qtbot, monkeypatch)

        # Populate the compare overlay the way _load_compare_overlay_from_
        # previous_season() does after opening a plan with linked seasons.
        win.canvas_scene.set_compare_overlay(PLANT_OBJECTS)
        win._compare_overlay_action.setEnabled(True)
        win._compare_overlay_action.setChecked(True)
        assert len(win.canvas_scene._compare_items) > 0

        # File -> New Plan, accepting the dialog with its defaults.
        monkeypatch.setattr(
            NewProjectDialog, "exec", lambda self: NewProjectDialog.DialogCode.Accepted
        )

        # Must not raise RuntimeError (the #337 crash).
        win._on_new_project()

        # The overlay must be fully reset: no tracked items, action disabled.
        assert win.canvas_scene._compare_items == []
        assert not win._compare_overlay_action.isEnabled()
        assert not win._compare_overlay_action.isChecked()

        # The second reader of _compare_items (set_compare_overlay_visible,
        # reached via the "Show Previous Season Overlay" menu action) must
        # also survive — round 1 of #337's fix left this one unguarded.
        win._on_toggle_compare_overlay(True)
        win._on_toggle_compare_overlay(False)
