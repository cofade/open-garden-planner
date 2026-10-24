"""The 2D sun study lies ON the ground surfaces (manual pass of PR #584).

The owner drew a lawn and switched the shadows and Hours of Sun on: both were hidden
under the lawn, because the two overlays sat below every layer item. A surface with
no height of its own — a lawn, a terrace, a driveway, a pond, a path, an in-ground
bed (``core.object_height.lies_on_ground``), and a group made only of those — is now
drawn in a band below the overlays (``canvas_scene.GROUND_Z_RANGE``), and everything
else stays above them: solids, plants, objects without a height (a cold frame),
generic shapes, annotations. Arrange works inside each band (``arrange.py``).

The pixels are the export pipeline's (``render_scene_region``): a shadow and the
heatmap must change the lawn's pixels and leave the shed that casts them alone. The
band follows the item: a height set on a lawn lifts it out, its undo puts it back, a
type change moves it, and ground surfaces keep their order among themselves.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QImage, QPainter

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import ChangePropertyCommand, CreateItemCommand
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.layer import Layer
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import GROUND_Z_RANGE, CanvasScene, ground_z
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.text_item import TextItem
from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController
from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowController

BERLIN = {"latitude": 52.52, "longitude": 13.405}
#: The shadow points north (+0.40, +0.92) at Berlin's June noon (test_shadow_overlay.py).
JUNE_NOON_UTC = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
REGION = QRectF(0, 0, 500, 500)
PX_PER_CM = 1.0
#: The shed: 60 x 60 cm at (200, 100), 200 cm tall — its noon shadow reaches ~120 cm north.
SHED = (200.0, 100.0, 60.0, 60.0)
IN_ITS_SHADOW = (235.0, 200.0)   # on the lawn, north of the shed
ON_THE_SHED = (230.0, 130.0)     # the shed's own roof
IN_THE_SUN = (100.0, 400.0)      # lawn far from the shed


@pytest.fixture
def view(qtbot) -> CanvasView:
    scene = CanvasScene(500.0, 500.0)
    canvas = CanvasView(scene)
    qtbot.addWidget(canvas)
    return canvas


def _add(view: CanvasView, item) -> None:
    view.command_manager.execute(CreateItemCommand(view.scene(), item, "add"))


def _lawn(view: CanvasView, layer=None) -> RectangleItem:
    scene = view.scene()
    lawn = RectangleItem(0, 0, 500, 500, object_type=ObjectType.LAWN,
                         layer_id=(layer or scene.active_layer).id)
    _add(view, lawn)
    return lawn


def _shed(view: CanvasView) -> RectangleItem:
    scene = view.scene()
    shed = RectangleItem(*SHED, object_type=ObjectType.TOOL_SHED, layer_id=scene.active_layer.id)
    shed.metadata[METADATA_KEY] = 200.0
    _add(view, shed)
    return shed


def _render(scene: CanvasScene) -> np.ndarray:
    width, height = round(REGION.width() * PX_PER_CM), round(REGION.height() * PX_PER_CM)
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        render_scene_region(scene, painter, QRectF(0, 0, width, height), REGION, y_flip=True)
    finally:
        painter.end()
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    data = np.frombuffer(image.constBits().asstring(image.sizeInBytes()), dtype=np.uint8)
    return data.reshape(height, image.bytesPerLine())[:, : width * 3].reshape(height, width, 3)


def _patch(rgb: np.ndarray, at: tuple[float, float], half: int = 6) -> np.ndarray:
    """The mean colour of a small square around a scene point (the §8.19 pixel formula)."""
    x = round((at[0] - REGION.x()) * PX_PER_CM)
    y = round(rgb.shape[0] - (at[1] - REGION.y()) * PX_PER_CM)
    return rgb[y - half: y + half, x - half: x + half].reshape(-1, 3).astype(float).mean(axis=0)


def _in_ground_band(item) -> bool:
    low, high = GROUND_Z_RANGE
    return low < item.zValue() < high


class TestTheShadowLiesOnTheLawn:
    def test_a_shadow_darkens_the_lawn_and_leaves_the_shed_alone(self, view) -> None:
        scene = view.scene()
        _shed(view)
        _lawn(view)   # drawn AFTER the shed: by insertion it would cover it
        controller = SunShadowController(scene, lambda: BERLIN)
        before = _render(scene)
        controller.set_enabled(True)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        after = _render(scene)
        shaded = _patch(before, IN_ITS_SHADOW) - _patch(after, IN_ITS_SHADOW)
        assert shaded.sum() > 60.0, f"the shadow is not on the lawn ({shaded})"
        assert np.abs(_patch(before, IN_THE_SUN) - _patch(after, IN_THE_SUN)).max() < 1.0
        roof = np.abs(_patch(before, ON_THE_SHED) - _patch(after, ON_THE_SHED))
        assert roof.max() < 1.0, "the shed stands above its own shadow"

    def test_the_hours_of_sun_lie_on_the_lawn_too(self, view, qtbot) -> None:
        scene = view.scene()
        _shed(view)
        _lawn(view)
        heatmap = SunHeatmapController(scene, lambda: BERLIN)
        try:
            assert heatmap.run_for_day(date(2026, 6, 21))
            qtbot.waitUntil(lambda: heatmap.result() is not None and not heatmap.result_pending,
                            timeout=60000)
            shown = _render(scene)
            heatmap._overlay.setVisible(False)
            for line in heatmap._contour_items:
                line.setVisible(False)
            hidden = _render(scene)
            # measured: 41.8 summed over RGB at that spot (in shade around noon only: a
            # pale cell); 0.0 while the lawn covered the map
            assert np.abs(_patch(shown, IN_ITS_SHADOW) - _patch(hidden, IN_ITS_SHADOW)).sum() > 10.0
            roof = np.abs(_patch(shown, ON_THE_SHED, 3) - _patch(hidden, ON_THE_SHED, 3))
            assert roof.max() < 1.0, "the shed stands above the map"
        finally:
            heatmap.shutdown()


class TestGroundZ:
    @pytest.mark.parametrize("layer_z", [-150.0, 0.0, 0.5, 50.0, 99.9, 100.0, 1e4, 1e9])
    def test_every_layer_z_lands_inside_the_band(self, layer_z: float) -> None:
        low, high = GROUND_Z_RANGE
        assert low < ground_z(layer_z) < high

    def test_the_order_is_kept_within_and_across_layers(self) -> None:
        values = [base + 100.0 * (i + 1) / 41 for base in (0.0, 100.0, 1100.0, 1e5)
                  for i in range(40)]
        moved = [ground_z(value) for value in values]
        assert all(a < b for a, b in zip(moved, moved[1:], strict=False))


class TestTheGroundBand:
    def test_ground_surfaces_lie_below_the_overlays_and_everything_else_above(self, view) -> None:
        scene = view.scene()
        shed = _shed(view)
        lawn = _lawn(view)
        path = PolygonItem([QPointF(x, y) for x, y in ((10, 10), (60, 10), (60, 400), (10, 400))],
                           object_type=ObjectType.PATH, layer_id=scene.active_layer.id)
        _add(view, path)
        bed = RectangleItem(300, 300, 100, 100, object_type=ObjectType.GARDEN_BED,
                            layer_id=scene.active_layer.id)
        _add(view, bed)
        zone = RectangleItem(400, 50, 60, 60, object_type=ObjectType.GENERIC_RECTANGLE,
                             layer_id=scene.active_layer.id)
        _add(view, zone)
        parasol = RectangleItem(420, 300, 40, 40, object_type=ObjectType.PARASOL,
                                layer_id=scene.active_layer.id)
        _add(view, parasol)   # no height in the plan, yet it stands up
        cold_frame = RectangleItem(320, 320, 40, 40, object_type=ObjectType.COLD_FRAME,
                                   layer_id=scene.active_layer.id)
        _add(view, cold_frame)   # stands on the bed without a height: never under it
        note = TextItem(50, 50, "note", layer_id=scene.active_layer.id)
        _add(view, note)
        pin = JournalPinItem(80, 80, "note-1", layer_id=scene.active_layer.id)
        _add(view, pin)
        for item in (lawn, path, bed):
            assert _in_ground_band(item), item.object_type
        assert lawn.zValue() < path.zValue() < bed.zValue(), "their order among themselves stays"
        for item in (shed, note, pin, zone, parasol, cold_frame):
            assert item.zValue() >= 0.0, item.object_type
        assert GROUND_Z_RANGE[0] > -1000.0, "above the background image"
        assert GROUND_Z_RANGE[1] < -500.0, "below the shadow overlay (-500) and the map (-450)"

    def test_a_group_of_ground_surfaces_lies_on_the_ground_and_a_mixed_one_does_not(
            self, view) -> None:
        """Both reviews of the manual pass: a group is drawn in ONE slot — a grouped
        lawn left in its layer's band hid the overlays and lay over a path ranked above
        the group. A group of surfaces only takes the band; a mixed one stays."""
        from open_garden_planner.core.commands import GroupCommand

        scene = view.scene()
        lawn = _lawn(view)
        terrace = RectangleItem(50, 50, 100, 100, object_type=ObjectType.TERRACE_PATIO,
                                layer_id=scene.active_layer.id)
        _add(view, terrace)
        view.command_manager.execute(GroupCommand(scene, [lawn, terrace]))
        group = lawn.parentItem()
        assert group is not None and _in_ground_band(group)
        path = PolygonItem([QPointF(x, y) for x, y in ((0, 0), (40, 0), (40, 400), (0, 400))],
                           object_type=ObjectType.PATH, layer_id=scene.active_layer.id)
        _add(view, path)
        assert group.zValue() < path.zValue() < -500.0, "the path ranked above lies above it"
        view.command_manager.undo()   # the path
        view.command_manager.undo()   # the group
        assert lawn.parentItem() is None and _in_ground_band(lawn) and _in_ground_band(terrace)
        shed = _shed(view)
        view.command_manager.execute(GroupCommand(scene, [lawn, shed]))
        mixed = lawn.parentItem()
        assert mixed is not None and mixed.zValue() >= 0.0
        # the documented limit (ADR-043 addendum): a surface ranked above a mixed group
        # is still drawn under it, in 2D and in the 3D ground bake
        later = PolygonItem([QPointF(x, y) for x, y in ((0, 0), (40, 0), (40, 400), (0, 400))],
                            object_type=ObjectType.PATH, layer_id=scene.active_layer.id)
        _add(view, later)
        assert later.zValue() < -500.0 < mixed.zValue()

    def test_the_layer_order_holds_among_ground_surfaces_across_layers(self, view) -> None:
        scene = view.scene()
        upper = Layer(name="Upper", z_order=1)
        scene.add_layer(upper)
        terrace = RectangleItem(0, 0, 200, 200, object_type=ObjectType.TERRACE_PATIO,
                                layer_id=upper.id)
        _add(view, terrace)
        lawn = _lawn(view, layer=scene.layers[0])
        assert scene.layers[0].z_order < upper.z_order
        assert _in_ground_band(lawn) and _in_ground_band(terrace)
        assert lawn.zValue() < terrace.zValue()

    def test_a_height_lifts_a_lawn_out_of_the_band_and_undo_puts_it_back(self, view) -> None:
        lawn = _lawn(view)

        def set_height(item, value) -> None:
            if value is None:
                item.metadata.pop(METADATA_KEY, None)
            else:
                item.metadata[METADATA_KEY] = value

        view.command_manager.execute(
            ChangePropertyCommand(lawn, "object height", None, 30.0, apply_func=set_height))
        assert lawn.zValue() >= 0.0, "a lawn with a height is a solid"
        view.command_manager.undo()
        assert _in_ground_band(lawn)
        view.command_manager.redo()
        assert lawn.zValue() >= 0.0

    def test_a_type_change_moves_an_item_in_and_out_of_the_band(self, view) -> None:
        scene = view.scene()
        shape = RectangleItem(0, 0, 200, 200, object_type=ObjectType.TOOL_SHED,
                              layer_id=scene.active_layer.id)
        _add(view, shape)
        assert shape.zValue() >= 0.0

        def set_type(item, value) -> None:
            item.object_type = value

        view.command_manager.execute(ChangePropertyCommand(
            shape, "object type", ObjectType.TOOL_SHED, ObjectType.LAWN,
            apply_func=set_type))
        assert _in_ground_band(shape)
        view.command_manager.undo()
        assert shape.zValue() >= 0.0

    def test_the_properties_panels_type_change_moves_it_and_undo_moves_it_back(
            self, view, qtbot) -> None:
        """The user's path: the Properties panel's type combo (shapes and lines both
        commit with ``register_applied``) — a lawn made a shed rises above the overlays,
        a path made a fence too; undo puts each back under them."""
        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
        from open_garden_planner.ui.panels.properties_panel import PropertiesPanel

        scene = view.scene()
        panel = PropertiesPanel(command_manager=view.command_manager)
        qtbot.addWidget(panel)
        lawn = PolygonItem([QPointF(x, y) for x, y in ((0, 0), (300, 0), (300, 300), (0, 300))],
                           object_type=ObjectType.LAWN, layer_id=scene.active_layer.id)
        path = PolylineItem([QPointF(10, 400), QPointF(400, 400)], object_type=ObjectType.PATH,
                            layer_id=scene.active_layer.id)
        for item in (lawn, path):
            _add(view, item)
            assert _in_ground_band(item), item.object_type
        panel._on_property_changed(lawn, "object_type", ObjectType.GARAGE_SHED)
        panel._on_property_changed(path, "object_type", ObjectType.FENCE)
        assert lawn.zValue() >= 0.0 and path.zValue() >= 0.0
        view.command_manager.undo()
        view.command_manager.undo()
        assert lawn.object_type is ObjectType.LAWN and path.object_type is ObjectType.PATH
        assert _in_ground_band(lawn) and _in_ground_band(path)


class TestArrangeStaysInItsBand:
    """Senior review of the manual pass: Arrange ranked over the whole layer, so a
    lawn stepped "forward" past a table and nothing visible moved. Each band of the
    selection is now arranged alone, and the layer renumbered ground first."""

    @staticmethod
    def _three(view):
        scene = view.scene()
        lower = _lawn(view)
        table = RectangleItem(100, 100, 200, 200, object_type=ObjectType.TABLE_RECTANGULAR,
                              layer_id=scene.active_layer.id)
        _add(view, table)
        upper = PolygonItem([QPointF(x, y) for x, y in ((50, 50), (350, 50), (350, 350), (50, 350))],
                            object_type=ObjectType.TERRACE_PATIO, layer_id=scene.active_layer.id)
        _add(view, upper)
        return scene, lower, table, upper

    def test_bring_forward_steps_past_the_next_ground_surface_not_a_solid(self, view) -> None:
        from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome
        from open_garden_planner.ui.canvas.arrange import build_arrange_command

        scene, lower, table, upper = self._three(view)
        assert lower.zValue() < upper.zValue() < table.zValue()
        command, outcome = build_arrange_command(scene, [lower], ArrangeMode.BRING_FORWARD)
        assert outcome is ArrangeOutcome.CHANGED and command is not None
        view.command_manager.execute(command)
        assert upper.zValue() < lower.zValue() < table.zValue(), "a visible step, among surfaces"
        assert lower.stack_order < table.stack_order and upper.stack_order < table.stack_order, \
            "ranks agree with the drawing: ground first"
        view.command_manager.undo()
        assert lower.zValue() < upper.zValue()

    def test_at_the_edge_of_its_band_it_refuses_and_records_nothing(self, view) -> None:
        from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome
        from open_garden_planner.ui.canvas.arrange import build_arrange_command

        scene, lower, table, upper = self._three(view)
        command, outcome = build_arrange_command(scene, [upper], ArrangeMode.BRING_TO_FRONT)
        assert command is None and outcome is ArrangeOutcome.ALREADY_AT_FRONT
        command, outcome = build_arrange_command(scene, [table], ArrangeMode.SEND_TO_BACK)
        assert command is None and outcome is ArrangeOutcome.ALREADY_AT_BACK

    def test_a_mixed_selection_arranges_each_band_in_one_step(self, view) -> None:
        from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome
        from open_garden_planner.ui.canvas.arrange import build_arrange_command

        scene, lower, table, upper = self._three(view)
        shed = _shed(view)
        assert table.zValue() < shed.zValue()
        command, outcome = build_arrange_command(scene, [lower, table], ArrangeMode.BRING_TO_FRONT)
        assert outcome is ArrangeOutcome.CHANGED
        depth = len(view.command_manager._undo_stack)
        view.command_manager.execute(command)
        assert len(view.command_manager._undo_stack) == depth + 1
        assert upper.zValue() < lower.zValue() < shed.zValue() < table.zValue()


    def test_an_unrelated_arrange_leaves_a_plant_on_an_in_ground_bed_where_it_is(self, view) -> None:
        """Senior review round 2: arrange split the layer by band while the drawing
        normalized the whole layer, so sending a LAWN to the back moved a perennial on
        an in-ground bed under a tree. One band split (``_band_entries``) feeds both."""
        from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome
        from open_garden_planner.ui.canvas.arrange import build_arrange_command
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        scene = view.scene()
        layer = scene.active_layer.id
        tree = CircleItem(200, 200, 150, object_type=ObjectType.TREE, layer_id=layer)
        bed = RectangleItem(0, 0, 400, 400, object_type=ObjectType.GARDEN_BED, layer_id=layer)
        plant = CircleItem(150, 150, 30, object_type=ObjectType.PERENNIAL, layer_id=layer)
        lawn = RectangleItem(300, 300, 400, 400, object_type=ObjectType.LAWN, layer_id=layer)
        lawn2 = RectangleItem(350, 350, 400, 400, object_type=ObjectType.LAWN, layer_id=layer)
        for item in (tree, bed, plant, lawn, lawn2):
            _add(view, item)
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)
        scene._update_items_z_order()
        above_tree = plant.zValue() > tree.zValue()
        command, outcome = build_arrange_command(scene, [lawn2], ArrangeMode.SEND_TO_BACK)
        assert outcome is ArrangeOutcome.CHANGED
        view.command_manager.execute(command)
        assert lawn2.zValue() < lawn.zValue() < -500.0
        assert (plant.zValue() > tree.zValue()) is above_tree, "the arrange of a lawn moved a plant"
        command, outcome = build_arrange_command(scene, [plant], ArrangeMode.BRING_TO_FRONT)
        if above_tree:
            assert outcome is ArrangeOutcome.ALREADY_AT_FRONT and command is None
        else:
            view.command_manager.execute(command)
            assert plant.zValue() > tree.zValue()

    def test_bring_to_front_on_a_plant_of_an_in_ground_bed_is_a_visible_step(self, view) -> None:
        """Senior review round 2: "Bring to Front" on such a plant under a table was
        recorded as a change while the plant stayed under the table."""
        from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome
        from open_garden_planner.ui.canvas.arrange import build_arrange_command
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        scene = view.scene()
        layer = scene.active_layer.id
        bed = RectangleItem(0, 0, 400, 400, object_type=ObjectType.GARDEN_BED, layer_id=layer)
        plant = CircleItem(150, 150, 30, object_type=ObjectType.PERENNIAL, layer_id=layer)
        table = RectangleItem(100, 100, 200, 200, object_type=ObjectType.TABLE_RECTANGULAR,
                              layer_id=layer)
        for item in (bed, plant, table):
            _add(view, item)
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)
        scene._update_items_z_order()
        assert bed.zValue() < plant.zValue() < table.zValue()
        command, outcome = build_arrange_command(scene, [plant], ArrangeMode.BRING_TO_FRONT)
        assert outcome is ArrangeOutcome.CHANGED
        view.command_manager.execute(command)
        assert plant.zValue() > table.zValue() > bed.zValue()


class TestTheBandOnReload:
    def test_a_saved_lawn_reopens_in_the_band(self, view, tmp_path: Path) -> None:
        scene = view.scene()
        _shed(view)
        _lawn(view)
        manager = ProjectManager()
        path = tmp_path / "ground.ogp"
        manager.save(scene, path)
        manager.load(scene, path)
        lawns = [item for item in scene.items()
                 if getattr(item, "object_type", None) is ObjectType.LAWN]
        sheds = [item for item in scene.items()
                 if getattr(item, "object_type", None) is ObjectType.TOOL_SHED]
        assert len(lawns) == 1 and _in_ground_band(lawns[0])
        assert len(sheds) == 1 and sheds[0].zValue() >= 0.0
