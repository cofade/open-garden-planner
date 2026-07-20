"""Integration tests for the object-height property (US-E2, #257).

Covers the two contracts the unit tests cannot:

1. ``.ogp`` round-trip — ``object_height_cm`` is additive metadata that
   survives save/clear/load with NO FILE_VERSION bump (template:
   ``test_container_roundtrip.py``), including on a polyline caster
   (FENCE/WALL get their metadata post-hoc in the deserializer, not via
   the constructor — the one divergent code path).
2. The properties-panel spin — one undoable command per edit (#209),
   0 = clear-the-override semantics, and the #206 in-place refresher
   showing fresh values after undo.
"""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QDoubleSpinBox, QGraphicsScene, QLabel

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import CommandManager
from open_garden_planner.core.object_height import (
    METADATA_KEY,
    effective_height_cm,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel


@pytest.fixture
def manager(qtbot) -> ProjectManager:  # noqa: ARG001 — qtbot for Qt init
    return ProjectManager()


@pytest.fixture
def scene(qtbot) -> QGraphicsScene:  # noqa: ARG001
    return QGraphicsScene()


def _field_by_label(panel: PropertiesPanel, label_text: str):
    form = panel._form_layout
    for i in range(form.rowCount()):
        label_item = form.itemAt(i, form.ItemRole.LabelRole)
        field_item = form.itemAt(i, form.ItemRole.FieldRole)
        if label_item is None or field_item is None:
            continue
        label_widget = label_item.widget()
        if isinstance(label_widget, QLabel) and label_text in label_widget.text():
            return field_item.widget()
    return None


class TestRoundTrip:
    def test_file_version_not_bumped(self) -> None:
        """object_height_cm is additive metadata — no FILE_VERSION bump."""
        assert FILE_VERSION == "1.4"

    def test_wall_polyline_height_round_trips(self, manager, scene, tmp_path) -> None:
        """Polyline items receive metadata post-hoc in the deserializer —
        the divergent path, so a WALL (the primary shadow caster) is the
        round-trip subject."""
        wall = PolylineItem(
            [QPointF(0, 0), QPointF(400, 0)], object_type=ObjectType.WALL
        )
        wall.metadata[METADATA_KEY] = 250.0
        scene.addItem(wall)

        file_path = tmp_path / "wall.ogp"
        manager.save(scene, file_path)
        scene.clear()
        manager.load(scene, file_path)

        walls = [i for i in scene.items() if isinstance(i, PolylineItem)]
        assert len(walls) == 1
        assert walls[0].metadata[METADATA_KEY] == 250.0
        assert effective_height_cm(walls[0].object_type, walls[0].metadata) == 250.0

    def test_unset_fence_resolves_to_default_after_load(
        self, manager, scene, tmp_path
    ) -> None:
        fence = PolylineItem(
            [QPointF(0, 0), QPointF(300, 0)], object_type=ObjectType.FENCE
        )
        scene.addItem(fence)
        file_path = tmp_path / "fence.ogp"
        manager.save(scene, file_path)
        assert METADATA_KEY not in file_path.read_text(encoding="utf-8")
        scene.clear()
        manager.load(scene, file_path)

        fences = [i for i in scene.items() if isinstance(i, PolylineItem)]
        assert effective_height_cm(fences[0].object_type, fences[0].metadata) == 120.0

    def test_rectangle_height_round_trips(self, manager, scene, tmp_path) -> None:
        shed = RectangleItem(0, 0, 300, 200, object_type=ObjectType.TOOL_SHED)
        shed.metadata[METADATA_KEY] = 275.0
        scene.addItem(shed)
        file_path = tmp_path / "shed.ogp"
        manager.save(scene, file_path)
        scene.clear()
        manager.load(scene, file_path)

        sheds = [i for i in scene.items() if isinstance(i, RectangleItem)]
        assert sheds[0].metadata[METADATA_KEY] == 275.0

    def test_old_file_without_key_loads_clean(self, manager, scene, tmp_path) -> None:
        """Graceful degrade both ways: a file without the key loads and the
        saved JSON of an untouched plan carries no object_height_cm."""
        bed = RectangleItem(10, 10, 200, 100, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        file_path = tmp_path / "legacy.ogp"
        manager.save(scene, file_path)
        raw = json.loads(file_path.read_text(encoding="utf-8"))
        assert raw["version"] == "1.4"
        assert METADATA_KEY not in json.dumps(raw)
        scene.clear()
        manager.load(scene, file_path)  # must not raise


class TestPanelUndo:
    def test_edit_is_one_undo_step_and_reverts(self, qtbot) -> None:  # noqa: ARG002
        cmd_mgr = CommandManager()
        panel = PropertiesPanel(command_manager=cmd_mgr)
        fence = RectangleItem(0, 0, 300, 10, object_type=ObjectType.FENCE)
        panel.set_selected_items([fence])

        spin = _field_by_label(panel, "Object height")
        assert isinstance(spin, QDoubleSpinBox)
        # Displays the resolved default (FENCE → 120) though nothing stored.
        assert spin.value() == 120.0
        assert METADATA_KEY not in fence.metadata

        stack_changes = []
        cmd_mgr.stack_changed.connect(lambda: stack_changes.append(True))

        spin.setValue(180.0)
        assert fence.metadata[METADATA_KEY] == 180.0
        assert cmd_mgr.can_undo
        # Exactly one undoable step, and it dirtied the stack (#209: the app
        # wires stack_changed → mark_dirty).
        assert len(stack_changes) == 1

        cmd_mgr.undo()
        assert METADATA_KEY not in fence.metadata

        cmd_mgr.redo()
        assert fence.metadata[METADATA_KEY] == 180.0

    def test_refresher_updates_spin_after_undo(self, qtbot) -> None:  # noqa: ARG002
        cmd_mgr = CommandManager()
        panel = PropertiesPanel(command_manager=cmd_mgr)
        fence = RectangleItem(0, 0, 300, 10, object_type=ObjectType.FENCE)
        panel.set_selected_items([fence])
        spin = _field_by_label(panel, "Object height")

        spin.setValue(180.0)
        cmd_mgr.undo()
        # The #223 wiring calls set_selected_items on stack_changed, which
        # takes the same-selection in-place refresh path.
        panel.set_selected_items([fence])
        assert spin.value() == 120.0  # back to the resolved default

    def test_zero_clears_the_override(self, qtbot) -> None:  # noqa: ARG002
        cmd_mgr = CommandManager()
        panel = PropertiesPanel(command_manager=cmd_mgr)
        wall = RectangleItem(0, 0, 400, 20, object_type=ObjectType.WALL)
        wall.metadata[METADATA_KEY] = 250.0
        panel.set_selected_items([wall])
        spin = _field_by_label(panel, "Object height")
        assert spin.value() == 250.0

        spin.setValue(0.0)
        assert METADATA_KEY not in wall.metadata
        # One undo step restores the explicit 250.
        cmd_mgr.undo()
        assert wall.metadata[METADATA_KEY] == 250.0

    def test_no_height_row_for_type_without_semantics(self, qtbot) -> None:  # noqa: ARG002
        panel = PropertiesPanel(command_manager=CommandManager())
        generic = RectangleItem(0, 0, 100, 100)  # GENERIC_RECTANGLE
        panel.set_selected_items([generic])
        assert _field_by_label(panel, "Object height") is None
