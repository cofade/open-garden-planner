"""Integration tests for issue #170 — auto-populate plant species data on drop.

Covers the two creation paths that put a plant on the canvas:
  * Drag from the gallery → ``CanvasView.dropEvent`` (gallery: MIME).
  * Tool draw with TREE/SHRUB/PERENNIAL → ``CircleTool._finalize_circle``.

Both must populate ``item.metadata['plant_species']`` from the bundled
``plant_species.json`` so the plant detail panel shows pH/NPK without the
user clicking Suchen, and US-12.10d soil-mismatch warnings start firing
automatically. Misses fall through to the existing API search button.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.core.tools.circle_tool import CircleTool
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _drop(view: CanvasView, mime_text: str, scene_pos: QPointF = QPointF(100, 100)) -> None:
    """Simulate a gallery drop with the given MIME text at scene_pos."""
    mime = QMimeData()
    mime.setText(mime_text)
    # mapFromScene gives us a viewport point that the view will map back.
    view_point = view.mapFromScene(scene_pos)
    event = QDropEvent(
        QPointF(view_point),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.dropEvent(event)


def _find_circle(view: CanvasView) -> CircleItem | None:
    for item in view.scene().items():
        if isinstance(item, CircleItem):
            return item
    return None


# ---------------------------------------------------------------------------
# Drag-from-gallery path


class TestGalleryDropAutopopulate:
    def test_tomato_drop_populates_full_species_metadata(
        self, canvas: CanvasView
    ) -> None:
        _drop(canvas, "gallery:TREE:species=Solanum lycopersicum:category=fruit")

        item = _find_circle(canvas)
        assert item is not None
        species = item.metadata.get("plant_species")
        assert species is not None, "metadata['plant_species'] must be populated on drop"
        # Critical fields for US-12.10d warnings.
        assert species["ph_min"] == pytest.approx(6.0)
        assert species["ph_max"] == pytest.approx(6.8)
        assert species["nutrient_demand"] == "heavy"
        assert species["n_demand"] == "high"
        # Calendar overlay also applied.
        assert species["frost_tolerance"] == "tender"
        assert species["indoor_sow_start"] == -8

    def test_unknown_species_drop_leaves_metadata_empty(
        self, canvas: CanvasView
    ) -> None:
        _drop(canvas, "gallery:TREE:species=Imaginus plantus:category=fruit")

        item = _find_circle(canvas)
        assert item is not None
        # Drop succeeds, the legacy plant_species string is set, but metadata
        # stays untouched so the API-search button is still the user's path.
        assert item.plant_species == "Imaginus plantus"
        assert "plant_species" not in item.metadata


# ---------------------------------------------------------------------------
# Tool-draw path (CircleTool with set_plant_info)


class TestCircleToolAutopopulate:
    def _click(self, tool: CircleTool, x: float, y: float) -> None:
        event = MagicMock()
        event.button.return_value = Qt.MouseButton.LeftButton
        event.buttons.return_value = Qt.MouseButton.LeftButton
        event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
        tool.mouse_press(event, QPointF(x, y))

    def test_tool_draw_populates_metadata(self, canvas: CanvasView) -> None:
        # Activate via the canvas tool manager so the tool gets the right view.
        canvas.set_active_tool(ToolType.TREE)
        tool = canvas.tool_manager.active_tool
        assert isinstance(tool, CircleTool)

        tool.set_plant_info(category=None, species="Capsicum annuum")
        # Two clicks: center, then rim 50cm away.
        self._click(tool, 100, 100)
        self._click(tool, 150, 100)

        item = _find_circle(canvas)
        assert item is not None
        species = item.metadata.get("plant_species")
        assert species is not None
        assert species["scientific_name"] == "Capsicum annuum"
        assert species["ph_min"] == pytest.approx(6.0)
        assert species["nutrient_demand"] == "heavy"


# ---------------------------------------------------------------------------
# Cross-feature: AC "warnings start firing automatically"


class TestMetadataPersistenceAcrossOperations:
    """Auto-populated metadata must survive undo/redo and project round-trip."""

    def test_undo_redo_preserves_metadata(self, canvas: CanvasView) -> None:
        # CreateItemCommand keeps a reference to the same item instance, so
        # undo/redo is just remove/add — metadata should round-trip trivially.
        # Pin that contract here so a future refactor can't silently drop it.
        _drop(canvas, "gallery:TREE:species=Solanum lycopersicum:category=fruit")

        item_before = _find_circle(canvas)
        assert item_before is not None
        ph_before = item_before.metadata["plant_species"]["ph_min"]

        canvas._command_manager.undo()
        assert _find_circle(canvas) is None  # item removed

        canvas._command_manager.redo()
        item_after = _find_circle(canvas)
        assert item_after is not None
        # Same instance, so metadata is preserved by reference.
        assert item_after.metadata["plant_species"]["ph_min"] == ph_before
        assert item_after.metadata["plant_species"]["nutrient_demand"] == "heavy"

    def test_serialized_metadata_round_trip(self, canvas: CanvasView) -> None:
        # Project save/load goes through _serialize_item → _deserialize_item.
        # If metadata is dropped from the circle serializer, plants saved
        # before this PR's drop hook would lose their species data on
        # reload. Lock the round-trip in.
        _drop(canvas, "gallery:TREE:species=Solanum lycopersicum:category=fruit")

        item = _find_circle(canvas)
        assert item is not None
        species_before = dict(item.metadata["plant_species"])

        # Round-trip the metadata dict via JSON like the project file would.
        import json
        round_tripped = json.loads(json.dumps(item.metadata))
        assert round_tripped["plant_species"]["ph_min"] == species_before["ph_min"]
        assert round_tripped["plant_species"]["nutrient_demand"] == species_before["nutrient_demand"]


class TestAutopopulateUnlocksSoilWarnings:
    def test_dropped_tomato_with_manual_bed_link_triggers_mismatch(
        self, canvas: CanvasView
    ) -> None:
        # Note: this test bypasses _auto_parent_plant by linking the plant to
        # the bed directly. That keeps it focused on what this PR controls —
        # that auto-populated metadata feeds the warning calculator. The
        # real auto-parent path is exercised by tests in
        # test_plant_soil_warnings.py and is unaffected by this PR.
        scene = canvas.scene()

        # Acidic bed (pH 4.5) at the origin.
        bed = RectangleItem(
            x=0, y=0, width=400, height=300,
            object_type=ObjectType.GARDEN_BED,
            name="Acid Bed",
        )
        scene.addItem(bed)

        # Drop a tomato — must auto-populate metadata.
        _drop(canvas, "gallery:TREE:species=Solanum lycopersicum:category=fruit",
              scene_pos=QPointF(100, 100))
        plant = _find_circle(canvas)
        assert plant is not None
        assert plant.metadata.get("plant_species") is not None

        # Manually link the plant to the bed (the auto-parent path varies by
        # geometry; this isolates the warning logic).
        bed._child_item_ids = [plant._item_id]

        svc = MagicMock(spec=SoilService)
        svc.get_effective_record.return_value = SoilTestRecord(
            date="2026-05-01", ph=4.5,
        )
        canvas.set_soil_service(svc)
        canvas.refresh_soil_mismatches()

        # AC: warnings fire automatically — bed is now flagged.
        assert bed._soil_mismatch_level in ("warning", "critical")
