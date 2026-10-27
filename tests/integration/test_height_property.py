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
    DEFAULT_HEIGHTS_CM,
    METADATA_KEY,
    effective_height_cm,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels import PropertiesPanel

#: The kinds that had no height until L4's second owner pass (ADR-065).
FORMERLY_HEIGHT_LESS = ["COLD_FRAME", "FIRE_PIT", "HAMMOCK", "PARASOL", "PERGOLA",
                        "PLANTER_POT", "RAIN_BARREL", "SWING", "WATER_TAP"]


@pytest.fixture
def manager(qtbot) -> ProjectManager:
    return ProjectManager()


@pytest.fixture
def scene(qtbot) -> QGraphicsScene:
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
    def test_edit_is_one_undo_step_and_reverts(self, qtbot) -> None:
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

    def test_refresher_updates_spin_after_undo(self, qtbot) -> None:
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

    def test_zero_clears_the_override(self, qtbot) -> None:
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

    def test_a_generic_shape_can_be_given_a_height(self, qtbot) -> None:
        """#628: the field is the only way to set one, so it appears for a footprint.

        Before, the row was gated on the TYPE having a height semantic, which for a
        type with no default was only true once an explicit height existed — the field
        that would create one could never appear. A polygon could not cast a shadow,
        and an in-ground bed could not be mounded, without changing the object's type
        (and with it its look and 3D builder).
        """
        cmd_mgr = CommandManager()
        panel = PropertiesPanel(command_manager=cmd_mgr)
        generic = RectangleItem(0, 0, 100, 100)  # GENERIC_RECTANGLE
        panel.set_selected_items([generic])

        spin = _field_by_label(panel, "Object height")
        assert isinstance(spin, QDoubleSpinBox)
        assert spin.value() == 0.0 and spin.text() == "Auto"   # today's behaviour
        assert METADATA_KEY not in generic.metadata

        spin.setValue(150.0)
        assert generic.metadata[METADATA_KEY] == 150.0
        assert effective_height_cm(generic.object_type, generic.metadata) == 150.0
        cmd_mgr.undo()
        assert METADATA_KEY not in generic.metadata
        assert effective_height_cm(generic.object_type, generic.metadata) is None

    def test_the_field_sets_a_ground_surface_up_as_a_solid(self, qtbot) -> None:
        """A terrace given a height is a platform: ``lies_on_ground`` yields (#628)."""
        from open_garden_planner.core.object_height import lies_on_ground

        panel = PropertiesPanel(command_manager=CommandManager())
        terrace = RectangleItem(0, 0, 400, 300, object_type=ObjectType.TERRACE_PATIO)
        panel.set_selected_items([terrace])
        assert lies_on_ground(terrace.object_type, terrace.metadata) is True
        spin = _field_by_label(panel, "Object height")
        assert isinstance(spin, QDoubleSpinBox)
        spin.setValue(30.0)
        assert lies_on_ground(terrace.object_type, terrace.metadata) is False
        assert effective_height_cm(terrace.object_type, terrace.metadata) == 30.0

    def test_an_item_without_a_footprint_has_no_height_row(self, qtbot) -> None:
        """Text has no outline, so it cannot be a solid: no field (and no regression)."""
        from open_garden_planner.ui.canvas.items.text_item import TextItem

        panel = PropertiesPanel(command_manager=CommandManager())
        text = TextItem(10.0, 10.0, "note")
        panel.set_selected_items([text])
        assert _field_by_label(panel, "Object height") is None

    @pytest.mark.parametrize("type_name", [
        "GENERIC_POLYGON", "GENERIC_RECTANGLE", "GENERIC_CIRCLE", "GENERIC_ELLIPSE",
        "GARDEN_BED", "TERRACE_PATIO", "POND_POOL", "LAWN", "PATH", "DRIVEWAY",
    ])
    def test_every_footprint_type_offers_the_height_field(
            self, qtbot, type_name: str) -> None:
        """The whole #628 set, through the real panel: the field appears and is Auto."""
        panel = PropertiesPanel(command_manager=CommandManager())
        item = RectangleItem(0, 0, 200, 150, object_type=ObjectType[type_name])
        panel.set_selected_items([item])
        spin = _field_by_label(panel, "Object height")
        assert spin is not None, f"{type_name}: Height row missing"
        assert spin.value() == 0.0 and spin.text() == "Auto"
        assert spin.toolTip() == "No height — no shadow on the 2D plan"
        spin.setValue(120.0)
        assert effective_height_cm(item.object_type, item.metadata) == 120.0

    def test_a_generic_shape_with_a_height_casts_a_shadow(self, qtbot) -> None:
        """The point of the field: a plain polygon becomes a caster and a 3D solid.

        The owner's workaround was to change the object's type to Garage - which also
        changed its look and its 3D builder. With the height alone, the walk finds it
        (the same rule the 3D snapshot uses) and its shadow is not empty.
        """
        from open_garden_planner.core.shadow_geometry import compute_scene_shadows
        from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
        from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
        from open_garden_planner.ui.canvas.sun_shadow_controller import (
            collect_identified_casters,
        )

        scene = CanvasScene(1000.0, 1000.0)
        star = PolygonItem([QPointF(x, y) for x, y in (
            (500.0, 700.0), (590.0, 400.0), (320.0, 580.0), (680.0, 580.0),
            (410.0, 400.0))], object_type=ObjectType.GENERIC_POLYGON,
            layer_id=scene.active_layer.id)
        scene.addItem(star)
        panel = PropertiesPanel(command_manager=CommandManager())
        panel.set_selected_items([star])
        assert collect_identified_casters(scene) == []      # no height: no caster
        spin = _field_by_label(panel, "Object height")
        assert isinstance(spin, QDoubleSpinBox)
        spin.setValue(150.0)
        assert star.metadata[METADATA_KEY] == 150.0
        casters = collect_identified_casters(scene)
        assert len(casters) == 1 and casters[0].height_cm == 150.0
        shadow = compute_scene_shadows(
            [(footprint, 150.0) for footprint in casters[0].footprints], 35.0, 180.0)
        assert shadow, "a height must give the shape a shadow"

        spin.setValue(0.0)                                  # back to Auto
        assert METADATA_KEY not in star.metadata
        assert collect_identified_casters(scene) == []

    @pytest.mark.parametrize("type_name", FORMERLY_HEIGHT_LESS)
    def test_every_standing_object_shows_its_default_and_takes_a_height(
            self, qtbot, type_name: str) -> None:
        """L4's second owner pass (ADR-065): the kinds that had no height — a parasol,
        a fire pit, the open frames — show their default in the panel, like a
        trampoline, and a typed height is one undo step. Through the real panel: the
        predicate alone was proven insufficient evidence (#308, review round 2)."""
        cmd_mgr = CommandManager()
        panel = PropertiesPanel(command_manager=cmd_mgr)
        item = RectangleItem(0, 0, 200, 150, object_type=ObjectType[type_name])
        panel.set_selected_items([item])
        spin = _field_by_label(panel, "Object height")
        assert spin is not None, f"{type_name}: Height row missing"
        default = DEFAULT_HEIGHTS_CM[type_name]
        assert spin.value() == default and spin.text() != "Auto"
        assert spin.toolTip() == "Default for this object type"
        assert METADATA_KEY not in item.metadata  # a default is never written
        spin.setValue(default + 40.0)
        assert effective_height_cm(item.object_type, item.metadata) == default + 40.0
        cmd_mgr.undo()
        assert METADATA_KEY not in item.metadata
        assert effective_height_cm(item.object_type, item.metadata) == default
