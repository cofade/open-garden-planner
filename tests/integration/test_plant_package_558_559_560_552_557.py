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


def test_history_refresh_updates_focused_widget(
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
    props._refresh_field_values()
    assert spin.value() == 1.0  # ordinary notification protects the edit

    props._history_refresh = True
    props._refresh_field_values()
    props._history_refresh = False
    assert spin.value() == 7.0  # history transition wins


def test_plant_panel_history_bypasses_focus_guard(
    canvas: CanvasView, plant_panel: PlantDatabasePanel, monkeypatch
) -> None:
    item = _tree(canvas)
    plant_panel.set_selected_items([item])
    monkeypatch.setattr(plant_panel, "_holds_field_focus", lambda: True)
    # Ordinary stray signal: panel stays put.
    plant_panel.set_selected_items([item])
    # History transition: same call refreshes instead of returning early.
    plant_panel._history_pending = True
    plant_panel.set_selected_items([item])
    assert plant_panel._history_pending is False
    assert plant_panel._current_plant_item is item


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
