"""Tests for the plant-bed parent-child relationship (US-11.1)."""

import uuid

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.commands import (
    CommandManager,
    CreateItemCommand,
    CreateItemsCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
    SetParentBedCommand,
)
from open_garden_planner.core.object_types import ObjectType, is_bed_type
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    GardenItemMixin,
    PolygonItem,
    RectangleItem,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scene(qtbot) -> CanvasScene:
    """Create a CanvasScene for testing."""
    return CanvasScene(5000, 3000)


@pytest.fixture
def manager(qtbot) -> CommandManager:
    """Create a CommandManager for testing."""
    return CommandManager()


def _make_bed(x: float = 100, y: float = 100, size: float = 400) -> PolygonItem:
    """Create a GARDEN_BED polygon at (x, y) with given size."""
    vertices = [
        QPointF(x, y),
        QPointF(x + size, y),
        QPointF(x + size, y + size),
        QPointF(x, y + size),
    ]
    bed = PolygonItem(vertices, object_type=ObjectType.GARDEN_BED)
    return bed


def _make_plant(cx: float = 300, cy: float = 300, radius: float = 20) -> CircleItem:
    """Create a TREE plant at (cx, cy)."""
    plant = CircleItem(cx, cy, radius, object_type=ObjectType.TREE)
    return plant


# ---------------------------------------------------------------------------
# is_bed_type helper
# ---------------------------------------------------------------------------

class TestIsBedType:
    def test_garden_bed(self) -> None:
        assert is_bed_type(ObjectType.GARDEN_BED) is True

    def test_raised_bed(self) -> None:
        assert is_bed_type(ObjectType.RAISED_BED) is True

    def test_house_is_not_bed(self) -> None:
        assert is_bed_type(ObjectType.HOUSE) is False

    def test_none(self) -> None:
        assert is_bed_type(None) is False


# ---------------------------------------------------------------------------
# GardenItemMixin parent-child fields
# ---------------------------------------------------------------------------

class TestGardenItemMixinFields:
    def test_default_values(self, qtbot) -> None:
        plant = _make_plant()
        assert plant.parent_bed_id is None
        assert plant.child_item_ids == []
        assert plant.has_children is False

    def test_add_child(self, qtbot) -> None:
        bed = _make_bed()
        child_id = uuid.uuid4()
        bed.add_child_id(child_id)
        assert child_id in bed.child_item_ids
        assert bed.has_children is True

    def test_add_child_duplicate(self, qtbot) -> None:
        bed = _make_bed()
        child_id = uuid.uuid4()
        bed.add_child_id(child_id)
        bed.add_child_id(child_id)
        assert bed.child_item_ids.count(child_id) == 1

    def test_remove_child(self, qtbot) -> None:
        bed = _make_bed()
        child_id = uuid.uuid4()
        bed.add_child_id(child_id)
        bed.remove_child_id(child_id)
        assert child_id not in bed.child_item_ids

    def test_remove_child_absent(self, qtbot) -> None:
        bed = _make_bed()
        bed.remove_child_id(uuid.uuid4())  # should not raise

    def test_child_item_ids_returns_copy(self, qtbot) -> None:
        bed = _make_bed()
        child_id = uuid.uuid4()
        bed.add_child_id(child_id)
        ids = bed.child_item_ids
        ids.clear()
        assert bed.has_children is True  # original unaffected


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

class TestSceneHelpers:
    def test_find_item_by_id(self, scene) -> None:
        bed = _make_bed()
        scene.addItem(bed)
        found = scene.find_item_by_id(bed.item_id)
        assert found is bed

    def test_find_item_by_id_not_found(self, scene) -> None:
        assert scene.find_item_by_id(uuid.uuid4()) is None

    def test_find_smallest_bed_containing(self, scene) -> None:
        # Big bed
        big = _make_bed(x=0, y=0, size=1000)
        scene.addItem(big)
        # Small bed nested inside
        small = _make_bed(x=100, y=100, size=200)
        scene.addItem(small)

        # Point inside both — should return the smaller one
        pt = QPointF(200, 200)
        result = scene.find_smallest_bed_containing(pt)
        assert result is small

    def test_find_smallest_bed_outside(self, scene) -> None:
        bed = _make_bed(x=100, y=100, size=200)
        scene.addItem(bed)

        pt = QPointF(50, 50)
        assert scene.find_smallest_bed_containing(pt) is None


# ---------------------------------------------------------------------------
# Auto-parenting on create
# ---------------------------------------------------------------------------

class TestAutoParenting:
    def test_create_plant_inside_bed(self, scene, manager) -> None:
        bed = _make_bed(x=100, y=100, size=400)
        scene.addItem(bed)

        plant = _make_plant(cx=300, cy=300)
        cmd = CreateItemCommand(scene, plant, "tree")
        manager.execute(cmd)

        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids

    def test_create_plant_outside_bed(self, scene, manager) -> None:
        bed = _make_bed(x=100, y=100, size=100)
        scene.addItem(bed)

        plant = _make_plant(cx=900, cy=900)
        cmd = CreateItemCommand(scene, plant, "tree")
        manager.execute(cmd)

        assert plant.parent_bed_id is None

    def test_undo_create_detaches(self, scene, manager) -> None:
        bed = _make_bed(x=100, y=100, size=400)
        scene.addItem(bed)

        plant = _make_plant(cx=300, cy=300)
        cmd = CreateItemCommand(scene, plant, "tree")
        manager.execute(cmd)

        # Undo should detach
        manager.undo()
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids


# ---------------------------------------------------------------------------
# SetParentBedCommand
# ---------------------------------------------------------------------------

class TestSetParentBedCommand:
    def test_attach(self, scene, manager) -> None:
        bed = _make_bed()
        plant = _make_plant()
        scene.addItem(bed)
        scene.addItem(plant)

        cmd = SetParentBedCommand(scene, plant, None, bed.item_id)
        manager.execute(cmd)

        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids

    def test_detach(self, scene, manager) -> None:
        bed = _make_bed()
        plant = _make_plant()
        scene.addItem(bed)
        scene.addItem(plant)

        # Attach first
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)

        cmd = SetParentBedCommand(scene, plant, bed.item_id, None)
        manager.execute(cmd)

        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids

    def test_undo_detach_restores(self, scene, manager) -> None:
        bed = _make_bed()
        plant = _make_plant()
        scene.addItem(bed)
        scene.addItem(plant)

        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)

        cmd = SetParentBedCommand(scene, plant, bed.item_id, None)
        manager.execute(cmd)
        manager.undo()

        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids

    def test_attach_elevates_plant_z_above_bed(self, scene, manager) -> None:
        """Issue #173: plant drawn before bed must render on top after move-into."""
        bed = _make_bed()
        plant = _make_plant()
        scene.addItem(bed)
        scene.addItem(plant)
        # Plant created first, then bed → both share the layer's default z=0.
        bed.setZValue(0)
        plant.setZValue(0)

        cmd = SetParentBedCommand(scene, plant, None, bed.item_id)
        manager.execute(cmd)

        assert plant.zValue() > bed.zValue()

    def test_attach_does_not_lower_plant_already_above_bed(
        self, scene, manager
    ) -> None:
        bed = _make_bed()
        plant = _make_plant()
        scene.addItem(bed)
        scene.addItem(plant)
        bed.setZValue(0)
        plant.setZValue(50)  # already well above

        cmd = SetParentBedCommand(scene, plant, None, bed.item_id)
        manager.execute(cmd)

        assert plant.zValue() == 50

    def test_detach_does_not_change_z(self, scene, manager) -> None:
        bed = _make_bed()
        plant = _make_plant()
        scene.addItem(bed)
        scene.addItem(plant)
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)
        bed.setZValue(0)
        plant.setZValue(1)

        cmd = SetParentBedCommand(scene, plant, bed.item_id, None)
        manager.execute(cmd)

        # Detach should not touch z — plant stays where it is.
        assert plant.zValue() == 1

    def test_undo_attach_restores_pre_attach_z(self, scene, manager) -> None:
        """Undo of attach must put z back where the user had it (symmetric)."""
        bed = _make_bed()
        plant = _make_plant()
        scene.addItem(bed)
        scene.addItem(plant)
        bed.setZValue(0)
        plant.setZValue(0)  # original z before attach

        cmd = SetParentBedCommand(scene, plant, None, bed.item_id)
        manager.execute(cmd)
        assert plant.zValue() == 1  # elevated by attach
        manager.undo()

        assert plant.zValue() == 0  # restored on undo

    def test_undo_attach_restores_non_zero_pre_attach_z(self, scene, manager) -> None:
        """Snapshot must be the actual pre-execute z, not a hardcoded 0.

        If the user explicitly elevated the plant before attaching it (e.g.
        z=5 to put it above another bed), undo must restore z=5, not 0.
        """
        bed = _make_bed()
        plant = _make_plant()
        scene.addItem(bed)
        scene.addItem(plant)
        bed.setZValue(0)
        plant.setZValue(5)  # user explicitly elevated the plant

        cmd = SetParentBedCommand(scene, plant, None, bed.item_id)
        manager.execute(cmd)
        assert plant.zValue() == 5  # already above bed, so unchanged
        manager.undo()

        assert plant.zValue() == 5  # restored to user's pre-attach value


# ---------------------------------------------------------------------------
# DeleteItemsCommand relationship handling
# ---------------------------------------------------------------------------

class TestDeleteWithRelationships:
    def test_delete_bed_snapshots_children(self, scene, manager) -> None:
        bed = _make_bed(x=100, y=100, size=400)
        scene.addItem(bed)
        plant = _make_plant(cx=300, cy=300)
        scene.addItem(plant)

        # Manually link
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)

        cmd = DeleteItemsCommand(scene, [bed, plant])
        manager.execute(cmd)

        # Items removed
        assert bed.scene() is None
        assert plant.scene() is None

        # Undo restores items and relationships
        manager.undo()
        assert bed.scene() is scene
        assert plant.scene() is scene
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_project_serialize_deserialize(self, scene, qtbot) -> None:
        from open_garden_planner.core.project import ProjectManager

        pm = ProjectManager()

        bed = _make_bed(x=100, y=100, size=400)
        scene.addItem(bed)
        plant = _make_plant(cx=300, cy=300)
        scene.addItem(plant)

        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)

        # Serialize
        data = pm._serialize_item(bed)
        assert data is not None
        assert "child_item_ids" in data
        assert str(plant.item_id) in data["child_item_ids"]

        plant_data = pm._serialize_item(plant)
        assert plant_data is not None
        assert "parent_bed_id" in plant_data
        assert plant_data["parent_bed_id"] == str(bed.item_id)

        # Deserialize
        loaded_bed = pm._deserialize_item(data)
        assert loaded_bed is not None
        assert isinstance(loaded_bed, GardenItemMixin)
        assert loaded_bed.child_item_ids == [plant.item_id]

        loaded_plant = pm._deserialize_item(plant_data)
        assert loaded_plant is not None
        assert isinstance(loaded_plant, GardenItemMixin)
        assert loaded_plant.parent_bed_id == bed.item_id


# ---------------------------------------------------------------------------
# Movement propagation (MoveItemsCommand)
# ---------------------------------------------------------------------------

class TestMovement:
    def test_move_bed_includes_children_via_command(self, scene, manager) -> None:
        bed = _make_bed(x=100, y=100, size=400)
        scene.addItem(bed)
        plant = _make_plant(cx=300, cy=300)
        scene.addItem(plant)

        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)

        plant_start = plant.pos()

        # Move bed and its children together (simulating what canvas_view does)
        delta = QPointF(50, 50)
        cmd = MoveItemsCommand([bed, plant], delta)
        manager.execute(cmd)

        # Plant should have moved
        assert plant.pos().x() == pytest.approx(plant_start.x() + 50)
        assert plant.pos().y() == pytest.approx(plant_start.y() + 50)

        # Undo
        manager.undo()
        assert plant.pos().x() == pytest.approx(plant_start.x())
        assert plant.pos().y() == pytest.approx(plant_start.y())
