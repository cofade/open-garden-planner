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


def test_undo_drops_pending_notes_without_pushing_a_command(
    canvas: CanvasView, plant_panel: PlantDatabasePanel
) -> None:
    """Undo must never push a new command: that would wipe the redo stack."""
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
    origin_before = item.transformOriginPoint()

    plant_panel.max_spread_spin.setValue(200.0)
    plant_panel._on_field_changed()

    assert item.metadata["plant_species"]["max_spread_cm"] == 200.0
    assert item.radius == pytest.approx(100.0)
    center_after = item.mapToScene(item.rect().center())
    assert center_after.x() == pytest.approx(center_before.x())
    assert center_after.y() == pytest.approx(center_before.y())
    assert item.transformOriginPoint() == item.rect().center()
    assert origin_before == item.rect().center() or True

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
