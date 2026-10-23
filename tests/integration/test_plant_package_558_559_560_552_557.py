"""Package 558/559/560/552/557 — plant details, lock, and estimated heights.

- #552: FIXED bypass closed; Lock/Unlock menu; padlock badge; save/reload.
- #559: Plant Details species + instance edits are one undo step each.
- #560: history refresh updates even a focused editor; ordinary typing kept.
- #558: Max Spread edit resizes the 2D footprint + 3D spread, center kept.
- #557: unknown height renders the plant form at a category fallback.
"""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QDoubleSpinBox

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plant_height_estimate import (
    ESTIMATED_HEIGHT_PARAM,
    estimated_height_cm,
)
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.bundled_species_db import merge_calendar_data
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel
from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel


@pytest.fixture()
def canvas(qtbot) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    return view


@pytest.fixture()
def props(qtbot, canvas: CanvasView) -> PropertiesPanel:
    p = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(p)
    return p


@pytest.fixture()
def plant_panel(qtbot, canvas: CanvasView) -> PlantDatabasePanel:
    p = PlantDatabasePanel()
    p.set_command_manager(canvas.command_manager)
    qtbot.addWidget(p)
    return p


def _tree(canvas: CanvasView, radius: float = 80.0) -> CircleItem:
    item = CircleItem(100.0, 100.0, radius, object_type=ObjectType.TREE)
    item.plant_species = "Oak"
    item.metadata["plant_species"] = merge_calendar_data(
        PlantSpeciesData(
            common_name="Oak",
            scientific_name="Quercus robur",
            max_spread_cm=2.0 * radius,
            max_height_cm=400.0,
            data_source="custom",
        ).to_dict()
    )
    canvas.scene().addItem(item)
    return item


# ── #552 ────────────────────────────────────────────────────────────────


def test_fixed_lock_refuses_panel_move_and_unlock_allows_it(
    canvas: CanvasView, props: PropertiesPanel
) -> None:
    rect = RectangleItem(100.0, 100.0, 400.0, 300.0, object_type=ObjectType.RAISED_BED)
    canvas.scene().addItem(rect)
    manager = canvas.command_manager

    # Lock via the shared menu dispatch (undoable).
    menu_steps = manager.undo_depth
    from PyQt6.QtWidgets import QMenu

    menu = QMenu()
    lock_action = rect.build_lock_context_menu(menu)
    assert lock_action is not None
    assert rect.dispatch_lock_action(lock_action, lock_action) is True
    assert rect.is_position_locked() is True
    assert manager.undo_depth == menu_steps + 1
    rect.refresh_lock_badge()
    assert getattr(rect, "_lock_badge_item", None) is not None

    # Panel X/Y attempt is refused: no move, no new move command.
    props.set_selected_items([rect])
    before = rect.pos()
    steps = manager.undo_depth
    x_spin = QDoubleSpinBox()
    y_spin = QDoubleSpinBox()
    for spin in (x_spin, y_spin):
        spin.setRange(0.0, 10000.0)
    x_spin.setValue(before.x() + 50.0)
    y_spin.setValue(before.y())
    props._on_position_changed(rect, x_spin, y_spin)
    assert rect.pos() == before
    assert manager.undo_depth == steps
    # The refused values are restored on the widgets, not left visible.
    pinned = rect.mapToScene(rect.boundingRect().topLeft())
    assert x_spin.value() == pinned.x()
    assert y_spin.value() == pinned.y()

    # Unlock (its own undo step), then the panel moves again.
    menu2 = QMenu()
    unlock_action = rect.build_lock_context_menu(menu2)
    assert rect.dispatch_lock_action(unlock_action, unlock_action) is True
    assert rect.is_position_locked() is False
    rect.refresh_lock_badge()
    assert getattr(rect, "_lock_badge_item", None) is None
    steps2 = manager.undo_depth
    x_spin.setValue(before.x() + 50.0)
    y_spin.setValue(before.y())
    props._on_position_changed(rect, x_spin, y_spin)
    assert manager.undo_depth == steps2 + 1
    assert rect.pos() != before

    # Save/reload preserves the unlocked state; re-lock then reload preserves
    # the lock and the badge re-derives on selection (#552).
    from open_garden_planner.core.project import ProjectManager

    menu3 = QMenu()
    lock_action3 = rect.build_lock_context_menu(menu3)
    assert rect.dispatch_lock_action(lock_action3, lock_action3) is True
    assert rect.is_position_locked() is True
    pm = ProjectManager()
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "lock.ogp"
        pm.save(canvas.scene(), path)
        pm.load(canvas.scene(), path)
    loaded = next(
        it
        for it in canvas.scene().items()
        if getattr(it, "item_id", None) == rect.item_id
    )
    assert loaded.is_position_locked() is True
    props.set_selected_items([loaded])
    assert getattr(loaded, "_lock_badge_item", None) is not None


# ── #559 ────────────────────────────────────────────────────────────────


def test_species_field_edit_is_one_undo_step(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    item = _tree(canvas)
    manager = canvas.command_manager
    plant_panel.set_selected_items([item])
    steps = manager.undo_depth

    plant_panel.family_edit.setText("Testaceae")
    plant_panel._on_field_changed()
    assert manager.undo_depth == steps + 1
    assert item.metadata["plant_species"]["family"] == "Testaceae"

    manager.undo()
    assert item.metadata["plant_species"].get("family", "") != "Testaceae"
    manager.redo()
    assert item.metadata["plant_species"]["family"] == "Testaceae"


def test_instance_field_edit_is_one_undo_step(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    item = _tree(canvas)
    manager = canvas.command_manager
    plant_panel.set_selected_items([item])
    steps = manager.undo_depth

    plant_panel._update_instance_metadata("variety_cultivar", "Crimson")
    assert manager.undo_depth == steps + 1
    assert item.metadata["plant_instance"]["variety_cultivar"] == "Crimson"

    manager.undo()
    assert "variety_cultivar" not in item.metadata["plant_instance"]
    manager.redo()
    assert item.metadata["plant_instance"]["variety_cultivar"] == "Crimson"


def test_noop_edit_adds_no_history(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    item = _tree(canvas)
    manager = canvas.command_manager
    plant_panel.set_selected_items([item])
    steps = manager.undo_depth
    plant_panel._on_field_changed()  # widgets already match the model
    assert manager.undo_depth == steps


# ── #560 ────────────────────────────────────────────────────────────────


def _lock(rect: RectangleItem) -> None:
    from PyQt6.QtWidgets import QMenu

    menu = QMenu()
    action = rect.build_lock_context_menu(menu)
    assert rect.dispatch_lock_action(action, action) is True


def test_properties_panel_is_wired_to_history_by_its_constructor(
    canvas: CanvasView, props: PropertiesPanel
) -> None:
    """The app builds the panel with command_manager= and never calls
    set_command_manager(): the history signal must still reach it (#560)."""
    rect = RectangleItem(100.0, 100.0, 400.0, 300.0, object_type=ObjectType.RAISED_BED)
    canvas.scene().addItem(rect)
    _lock(rect)
    assert props._history_pending is False  # an own commit is not history
    canvas.command_manager.undo()
    assert props._history_pending is True
    props.set_selected_items([rect])
    assert props._history_pending is False


def test_undo_refreshes_focused_widget_but_ordinary_notification_does_not(
    canvas: CanvasView, props: PropertiesPanel, monkeypatch
) -> None:
    rect = RectangleItem(100.0, 100.0, 400.0, 300.0, object_type=ObjectType.RAISED_BED)
    canvas.scene().addItem(rect)
    props.set_selected_items([rect])
    assert props._field_refreshers

    spin = QDoubleSpinBox()
    spin.setValue(1.0)
    props._register_refresh(spin, lambda: spin.setValue(7.0))
    monkeypatch.setattr(props, "_is_focused", lambda _w: True)

    props.set_selected_items([rect])  # ordinary notification
    assert spin.value() == 1.0  # uncommitted typing is protected

    _lock(rect)
    canvas.command_manager.undo()  # real undo -> real history_navigated
    props.set_selected_items([rect])
    assert spin.value() == 7.0  # history transition wins over the focus guard


def test_plant_panel_gets_history_signal_from_real_undo(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    item = _tree(canvas)
    plant_panel.set_selected_items([item])
    plant_panel.family_edit.setText("Testaceae")
    plant_panel._on_field_changed()
    assert plant_panel._history_pending is False
    canvas.command_manager.undo()
    assert plant_panel._history_pending is True
    plant_panel.set_selected_items([item])
    assert plant_panel._history_pending is False


def test_undo_commits_pending_notes_before_navigating(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    """The active edit commits before undo; a refresh never erases redo."""
    item = _tree(canvas)
    manager = canvas.command_manager
    plant_panel.set_selected_items([item])
    plant_panel.family_edit.setText("Testaceae")
    plant_panel._on_field_changed()
    plant_panel.notes_edit.setPlainText("typed, not yet committed")
    assert plant_panel._notes_has_pending is True

    manager.undo()
    plant_panel.set_selected_items([item])

    assert manager.can_redo is True  # redo stack survived
    assert manager.redo_depth == 1
    assert plant_panel._notes_has_pending is False
    assert "notes" not in (item.metadata.get("plant_instance") or {}) or not (
        item.metadata["plant_instance"].get("notes")
    )


def test_different_spinboxes_never_coalesce_into_one_undo_step(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    item = _tree(canvas, radius=80.0)
    manager = canvas.command_manager
    plant_panel.set_selected_items([item])
    steps = manager.undo_depth

    plant_panel.max_spread_spin.setValue(200.0)
    plant_panel.ph_min_spin.setValue(5.5)

    assert manager.undo_depth == steps + 2


def test_locked_item_badge_is_derived_on_load_and_hidden_in_export(
    canvas: CanvasView,
) -> None:
    import tempfile
    from pathlib import Path

    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.services.export_service import ExportService
    from open_garden_planner.ui.canvas.items.garden_item import LockBadgeItem

    rect = RectangleItem(100.0, 100.0, 400.0, 300.0, object_type=ObjectType.RAISED_BED)
    canvas.scene().addItem(rect)
    _lock(rect)
    pm = ProjectManager()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "lock.ogp"
        pm.save(canvas.scene(), path)
        pm.load(canvas.scene(), path)
    loaded = next(
        it
        for it in canvas.scene().items()
        if getattr(it, "item_id", None) == rect.item_id
    )
    # No selection happened: the badge must already be there.
    assert getattr(loaded, "_lock_badge_item", None) is not None

    hidden, _selected = ExportService._hide_overlay_items(canvas.scene())
    try:
        assert any(isinstance(h, LockBadgeItem) for h in hidden)
        assert not loaded._lock_badge_item.isVisible()
    finally:
        ExportService._restore_overlay_items(hidden, [])
    assert loaded._lock_badge_item.isVisible()


# ── #558 ────────────────────────────────────────────────────────────────


def test_max_spread_edit_resizes_footprint_centered(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    item = _tree(canvas, radius=80.0)
    manager = canvas.command_manager
    plant_panel.set_selected_items([item])
    center_before = item.mapToScene(item.rect().center())

    plant_panel.max_spread_spin.setValue(200.0)
    plant_panel._on_field_changed()

    assert item.metadata["plant_species"]["max_spread_cm"] == 200.0
    assert item.radius == pytest.approx(100.0)
    center_after = item.mapToScene(item.rect().center())
    assert center_after.x() == pytest.approx(center_before.x())
    assert center_after.y() == pytest.approx(center_before.y())
    assert item.transformOriginPoint() == item.rect().center()

    manager.undo()
    assert item.radius == pytest.approx(80.0)
    assert item.metadata["plant_species"]["max_spread_cm"] == pytest.approx(160.0)
    manager.redo()
    assert item.radius == pytest.approx(100.0)


def test_max_spread_preserves_explicit_override(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    item = _tree(canvas, radius=80.0)
    item.spacing_radius_cm = 30.0  # explicit user override wins
    plant_panel.set_selected_items([item])
    plant_panel.max_spread_spin.setValue(200.0)
    plant_panel._on_field_changed()
    assert item.radius == pytest.approx(80.0)
    assert item.metadata["plant_species"]["max_spread_cm"] == 200.0


# ── #557 ────────────────────────────────────────────────────────────────


def test_spin_drag_coalesces_into_one_undo_step(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    """A numeric drag is one undoable gesture, not one entry per tick (#559)."""
    item = _tree(canvas, radius=80.0)
    manager = canvas.command_manager
    plant_panel.set_selected_items([item])
    steps = manager.undo_depth

    plant_panel.max_spread_spin.setValue(200.0)
    plant_panel.max_spread_spin.setValue(210.0)
    plant_panel.max_spread_spin.setValue(220.0)

    assert manager.undo_depth == steps + 1
    assert item.metadata["plant_species"]["max_spread_cm"] == 220.0
    manager.undo()
    assert item.metadata["plant_species"]["max_spread_cm"] == pytest.approx(160.0)
    assert item.radius == pytest.approx(80.0)


def test_category_fallback_table_is_documented() -> None:
    assert estimated_height_cm("tree", "ROUND_DECIDUOUS") == 400.0
    assert estimated_height_cm("shrub", "COMPACT_SHRUB") == 150.0
    assert estimated_height_cm("perennial", "FLOWERING_PERENNIAL") == 60.0
    assert estimated_height_cm("perennial", "VEGETABLE") == 50.0
    assert estimated_height_cm("perennial", None) == 60.0
    assert estimated_height_cm("path", None) is None


def test_unknown_height_builds_plant_form_not_placeholder() -> None:
    from open_garden_planner.core.scene3d.builders.plants import (
        PLACEHOLDER,
        build_plant,
        plant_archetype,
    )
    from open_garden_planner.core.scene3d.record import Params, Record

    base = {
        "item_id": "x",
        "kind": "TREE",
        "shape": "circle",
        "footprints": (),
        "transform": None,
        "material": None,
        "height_cm": None,
        "path": (),
        "path_width_cm": None,
        "params": Params(
            {
                "radius_cm": 80.0,
                "seed": "s",
                "sprite_species": "Oak",
                "plant_category": "ROUND_DECIDUOUS",
                ESTIMATED_HEIGHT_PARAM: 400.0,
            }
        ),
        "parent_id": None,
        "name": "t",
    }
    rec = Record(**base)  # type: ignore[arg-type]
    assert plant_archetype(rec) != PLACEHOLDER
    parts = build_plant(rec)
    assert len(parts) >= 1
    assert all("placeholder" not in (p.name or "").lower() for p in parts)

    rec_none = Record(**{**base, "params": Params({"radius_cm": 80.0, "seed": "s", "sprite_species": "Oak", "plant_category": "ROUND_DECIDUOUS"})})  # type: ignore[arg-type]
    assert plant_archetype(rec_none) == PLACEHOLDER


@pytest.mark.parametrize("field", ["max_spread_spin", "current_height_spin"])
def test_separate_numeric_gestures_have_separate_undo_steps(canvas, plant_panel, field):
    item = _tree(canvas)
    plant_panel.set_selected_items([item])
    spin = getattr(plant_panel, field)
    spin.setValue(200)
    spin.editingFinished.emit()
    spin.setValue(300)
    spin.editingFinished.emit()
    assert canvas.command_manager.undo_depth == 2
    canvas.command_manager.undo()
    plant_panel.set_selected_items([item])
    assert spin.value() == 200


def test_pending_properties_name_is_the_next_undoable_edit(canvas, props):
    from PyQt6.QtWidgets import QLineEdit

    rect = RectangleItem(100, 100, 400, 300)
    rect.name = "before"
    canvas.scene().addItem(rect)
    _lock(rect)
    props.set_selected_items([rect])
    edit = next(e for e in props.findChildren(QLineEdit) if hasattr(e, "_ogp_name_start"))
    edit.setText("pending")
    canvas.command_manager.undo()
    props.set_selected_items([rect])
    assert rect.name == "before"
    assert rect.is_position_locked()
    assert canvas.command_manager.redo_depth == 1
    canvas.command_manager.redo()
    props.set_selected_items([rect])
    assert rect.name == edit.text() == "pending"


def test_unselected_padlock_follows_constraint_history(canvas, props):
    rect = RectangleItem(100, 100, 400, 300)
    canvas.scene().addItem(rect)
    _lock(rect)
    props.set_selected_items([])
    canvas.command_manager.undo()
    assert not rect.is_position_locked()
    assert getattr(rect, "_lock_badge_item", None) is None
    canvas.command_manager.redo()
    assert rect.is_position_locked()
    assert rect._lock_badge_item.isVisible()


@pytest.mark.parametrize("action", ["save", "discard_check"])
def test_immediate_save_and_close_guard_include_pending_notes(qtbot, monkeypatch, tmp_path, action):
    from PyQt6.QtWidgets import QMessageBox

    from tests.integration.test_view3d_workspace import build_app3d

    window, _ = build_app3d(qtbot, monkeypatch, tmp_path)
    item = _tree(window.canvas_view)
    window.plant_database_panel.set_selected_items([item])
    window._project_manager.mark_clean()
    window.plant_database_panel.notes_edit.setPlainText("save me immediately")
    if action == "save":
        path = tmp_path / "pending.ogp"
        window._project_manager.save(window.canvas_scene, path)
        import json

        assert "save me immediately" in json.dumps(json.loads(path.read_text(encoding="utf-8")))
    else:
        prompts = []
        monkeypatch.setattr(QMessageBox, "question", lambda *a: prompts.append(a) or QMessageBox.StandardButton.Cancel)
        assert window._confirm_discard_changes() is False
        assert len(prompts) == 1


def test_properties_refreshes_other_fields_while_name_has_focus(qtbot, canvas, props):
    from PyQt6.QtWidgets import QLineEdit

    rect = RectangleItem(100, 100, 400, 300)
    canvas.scene().addItem(rect)
    props.set_selected_items([rect])
    props.show()
    props.activateWindow()
    edit = next(e for e in props.findChildren(QLineEdit) if hasattr(e, "_ogp_name_start"))
    edit.setFocus()
    qtbot.waitUntil(edit.hasFocus)
    edit.setText("still typing")
    probes = []
    other = QDoubleSpinBox(props)
    props._register_refresh(other, lambda: probes.append(True))
    props.set_selected_items([rect])
    assert probes
    assert edit.text() == "still typing"


def test_plant_refreshes_other_fields_while_family_has_focus(qtbot, canvas, plant_panel):
    item = _tree(canvas)
    plant_panel.set_selected_items([item])
    plant_panel.show()
    plant_panel.activateWindow()
    edit = plant_panel.family_edit
    edit.setFocus()
    qtbot.waitUntil(edit.hasFocus)
    edit.setText("still typing")
    item.metadata["plant_species"]["max_height_cm"] = 900
    plant_panel.set_selected_items([item])
    assert plant_panel.max_height_spin.value() == 900
    assert edit.text() == "still typing"


@pytest.mark.parametrize("kind", ["line", "arc", "bezier", "text"])
def test_every_object_menu_exposes_undoable_position_lock(canvas, monkeypatch, kind):
    from types import SimpleNamespace

    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtWidgets import QMenu

    from open_garden_planner.ui.canvas.items.arc_item import ArcItem
    from open_garden_planner.ui.canvas.items.bezier_item import BezierItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.text_item import TextItem

    points = [QPointF(100, 100), QPointF(200, 200)]
    item = {
        "line": lambda: PolylineItem(points),
        "arc": lambda: ArcItem(QPointF(200, 200), 100, 0, 90),
        "bezier": lambda: BezierItem(points, points, points),
        "text": lambda: TextItem(100, 100, "hello"),
    }[kind]()
    canvas.scene().addItem(item)
    def choose_lock(menu, _pos):
        return next(action for action in menu.actions() if action.text() == "Lock position")

    monkeypatch.setattr(QMenu, "exec", choose_lock)
    item.contextMenuEvent(SimpleNamespace(screenPos=lambda: QPoint()))
    assert item.is_position_locked()
    assert item._lock_badge_item.isVisible()
    canvas.command_manager.undo()
    assert not item.is_position_locked()
    assert item._lock_badge_item is None
    canvas.command_manager.redo()
    assert item.is_position_locked()


def test_constraint_tool_path_derives_badge_without_selection(canvas):
    from open_garden_planner.core.commands import AddConstraintCommand
    from open_garden_planner.core.constraints import AnchorRef, ConstraintType
    from open_garden_planner.core.measure_snapper import AnchorType

    rect = RectangleItem(100, 100, 400, 300)
    canvas.scene().addItem(rect)
    anchor = AnchorRef(rect.item_id, AnchorType.CENTER, 0)
    cmd = AddConstraintCommand(canvas.scene().constraint_graph, anchor, anchor, 0,
                               ConstraintType.FIXED, target_x=100, target_y=100)
    canvas._execute_constraint_with_solve(cmd)
    assert not rect.isSelected()
    assert rect._lock_badge_item.isVisible()


def test_direct_spin_focus_preserves_partial_input_on_ordinary_refresh(qtbot, canvas, plant_panel):
    item = _tree(canvas)
    plant_panel.set_selected_items([item])
    plant_panel.show()
    plant_panel.activateWindow()
    spin = plant_panel.max_height_spin
    spin.setFocus()
    qtbot.waitUntil(spin.hasFocus)
    spin.lineEdit().setText("-")
    partial = spin.lineEdit().text()
    item.metadata["plant_species"]["max_spread_cm"] = 190
    plant_panel.set_selected_items([item])
    assert spin.lineEdit().text() == partial
    assert plant_panel.max_spread_spin.value() == 190


@pytest.mark.parametrize("panel_name,spin_name", [("plant_database_panel", "max_height_spin"), ("properties_panel", None)])
def test_save_interprets_directly_focused_numeric_editor(qtbot, monkeypatch, tmp_path, panel_name, spin_name):
    from PyQt6.QtWidgets import QApplication

    from tests.integration.test_view3d_workspace import build_app3d

    window, _ = build_app3d(qtbot, monkeypatch, tmp_path)
    item = _tree(window.canvas_view)
    item.setSelected(True)
    window._update_plant_database_panel()
    panel = getattr(window, panel_name)
    panel.set_selected_items([item])
    panel.show()
    window.show()
    window.activateWindow()
    spin = getattr(panel, spin_name) if spin_name else next(s for s in panel.findChildren(QDoubleSpinBox) if s.maximum() >= 777)
    spin.setKeyboardTracking(False)
    spin.setFocus()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is spin)
    spin.lineEdit().setText("777")
    assert spin.value() != 777
    window._flush_pending_panel_edits()
    assert spin.value() == 777


def test_notes_cursor_survives_unrelated_refresh(qtbot, canvas, plant_panel):
    item = _tree(canvas)
    plant_panel.set_selected_items([item])
    plant_panel.show()
    plant_panel.activateWindow()
    edit = plant_panel.notes_edit
    edit.setFocus()
    qtbot.waitUntil(edit.hasFocus)
    edit.setPlainText("some uncommitted notes")
    cursor = edit.textCursor()
    cursor.setPosition(8)
    edit.setTextCursor(cursor)
    item.metadata["plant_species"]["max_height_cm"] = 800
    plant_panel.set_selected_items([item])
    assert edit.toPlainText() == "some uncommitted notes"
    assert edit.textCursor().position() == 8


def test_unchanged_online_species_focus_never_converts_or_blocks_history(qtbot, canvas, plant_panel, monkeypatch, tmp_path):
    from copy import deepcopy
    from unittest.mock import Mock

    from open_garden_planner.core.project import ProjectManager

    item = _tree(canvas)
    item.metadata["plant_species"].update(data_source="trefle", source_id="online-1")
    before = deepcopy(item.metadata["plant_species"])
    library = Mock()
    monkeypatch.setattr("open_garden_planner.ui.panels.plant_database_panel.get_plant_library", lambda: library)
    plant_panel.set_selected_items([item])
    plant_panel.show()
    plant_panel.activateWindow()
    plant_panel.family_edit.setFocus()
    qtbot.waitUntil(plant_panel.family_edit.hasFocus)
    _lock(item)
    canvas.command_manager.undo()
    plant_panel.set_selected_items([item])
    assert not item.is_position_locked()
    assert canvas.command_manager.redo_depth == 1
    canvas.command_manager.redo()
    plant_panel.set_selected_items([item])
    assert item.is_position_locked()
    pm = ProjectManager()
    pm.before_save.connect(plant_panel.flush_pending_edits)
    pm.save(canvas.scene(), tmp_path / "online.ogp")
    assert item.metadata["plant_species"] == before
    library.add_plant.assert_not_called()
    library.update_plant.assert_not_called()


def test_species_command_has_independent_nested_snapshots(canvas):
    from open_garden_planner.core.commands import PlantSpeciesEditCommand

    item = _tree(canvas)
    old = {"raw_data": {"source": "old"}}
    new = {"raw_data": {"source": "new"}}
    cmd = PlantSpeciesEditCommand(item, old, new)
    old["raw_data"]["source"] = "mutated"
    new["raw_data"]["source"] = "mutated"
    cmd.execute()
    assert item.metadata["plant_species"]["raw_data"]["source"] == "new"
    item.metadata["plant_species"]["raw_data"]["source"] = "also mutated"
    cmd.undo()
    assert item.metadata["plant_species"]["raw_data"]["source"] == "old"
    cmd.execute()
    assert item.metadata["plant_species"]["raw_data"]["source"] == "new"
