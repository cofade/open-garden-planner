"""The 2D sun study lies ON the ground surfaces (manual pass of PR #584).

The owner drew a lawn and switched the shadows and Hours of Sun on: both were hidden
under the lawn, because the two overlays sat below every layer item. A surface with
no height of its own — a lawn, a terrace, a driveway, a pond, a path, an in-ground
bed (``core.object_height.lies_on_ground``), and a group made only of those — is now
drawn in a band below the overlays (``canvas_scene.GROUND_Z_RANGE``), and everything
else stays above them: solids, plants, objects without a height (a cold frame),
generic shapes, annotations. Arrange works inside each band (``arrange.py``). A
mixed group cannot be split across the band, so its surfaces paint the shadow and
the map on themselves (#1031), clipped to their own cover.

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
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import ChangePropertyCommand, CreateItemCommand
from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.layer import Layer
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import GROUND_Z_RANGE, CanvasScene, ground_z
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
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


def _view_patch(view: CanvasView, at: tuple[float, float], half: int = 5) -> np.ndarray:
    """The mean colour of a small square of the LIVE viewport (not an export)."""
    point = view.mapFromScene(QPointF(*at))
    image = view.viewport().grab(
        QRect(point.x() - half, point.y() - half, 2 * half, 2 * half)
    ).toImage()
    image = image.convertToFormat(QImage.Format.Format_RGB888)
    data = np.frombuffer(image.constBits().asstring(image.sizeInBytes()), dtype=np.uint8)
    pixels = data.reshape(image.height(), image.bytesPerLine())[:, : image.width() * 3]
    return pixels.reshape(-1, 3).astype(float).mean(axis=0)


def test_the_family_garden_bed_keeps_its_live_shadow_when_grouped(qtbot, monkeypatch) -> None:
    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowOverlayItem

    monkeypatch.setattr(GardenPlannerApp, "_startup_sequence", lambda _: None)
    monkeypatch.setattr(GardenPlannerApp, "_start_update_check", lambda _: None)
    window = GardenPlannerApp()
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(window)
    window.resize(1100, 720)
    window.show()
    plan = (Path(__file__).parents[2]
            / "src/open_garden_planner/resources/examples/de/family-garden.ogp")
    window._load_project_file(str(plan))
    view = window.canvas_view
    scene = view.scene()
    overlay = next(item for item in scene.items() if isinstance(item, SunShadowOverlayItem))
    qtbot.waitUntil(lambda: overlay._picture_key is not None, timeout=3000)
    view.set_zoom(0.8)
    view.centerOn(QPointF(855, 681))
    qtbot.waitUntil(lambda: overlay._picture_key is not None
                    and overlay._picture_key[1][:1] == (0.8,), timeout=3000)

    viewport = view.viewport()

    def click(x: float, y: float, modifiers=Qt.KeyboardModifier.NoModifier) -> None:
        qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, modifiers,
                         view.mapFromScene(QPointF(x, y)))

    # Exposed soil on both sides of the example's shadow boundary, away from
    # the group frame, spacing rings and dimensions.
    points = ((826, 705), (838, 659), (913, 701), (913, 663))
    before = np.array([_view_patch(view, point, half=2) for point in points])
    click(916, 681)
    click(876, 681, Qt.KeyboardModifier.ControlModifier)  # Borage
    click(958, 681, Qt.KeyboardModifier.ControlModifier)  # Pansy
    assert len(scene.selectedItems()) == 3
    view.group_selected()
    (group,) = scene.selectedItems()
    assert len([item for item in group.childItems() if hasattr(item, "item_id")]) == 3

    first = np.array([_view_patch(view, point, half=2) for point in points])
    scene.clearSelection()
    click(876, 681)
    assert scene.selectedItems() == [group]
    again = np.array([_view_patch(view, point, half=2) for point in points])
    assert np.abs(first - before).max() < 3, (before, first)
    assert np.abs(again - before).max() < 3, (before, again)


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

    def test_a_plant_crown_stands_above_the_shadow(self, view) -> None:
        """#876: a shadow must not tint a crown that stands in it."""
        scene = view.scene()
        _shed(view)
        _lawn(view)
        tree = CircleItem(235.0, 190.0, 30.0, object_type=ObjectType.TREE)
        _add(view, tree)
        controller = SunShadowController(scene, lambda: BERLIN)
        before = _render(scene)
        controller.set_enabled(True)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        after = _render(scene)
        # Verify the shed's shadow actually darkened the lawn right beside the crown
        # (tree is centred at (235, 190) r=30 -> north edge at y=220; shed shadow
        # reaches ~y=280 at x=255), so a no-op shadow controller cannot pass.
        shaded = _patch(before, (255.0, 240.0)) - _patch(after, (255.0, 240.0))
        assert shaded.sum() > 60.0, f"the shadow is not on the lawn ({shaded})"
        crown = np.abs(_patch(before, (235.0, 190.0), 4) - _patch(after, (235.0, 190.0), 4))
        assert crown.max() < 1.0, f"the shadow tinted the crown: {crown}"

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

    def test_the_hours_of_sun_lie_on_a_bed_grouped_with_a_solid(self, view, qtbot) -> None:
        """The map is painted by the bed itself when a group lifts it above the
        overlays (#1031) — a grouped bed must not lose the hours of sun."""
        from open_garden_planner.core.commands import GroupCommand

        scene = view.scene()
        _shed(view)
        _lawn(view)
        bed = RectangleItem(200, 180, 80, 40, object_type=ObjectType.GARDEN_BED,
                            layer_id=scene.active_layer.id)
        table = RectangleItem(300, 300, 40, 40, object_type=ObjectType.TABLE_RECTANGULAR,
                              layer_id=scene.active_layer.id)
        for item in (bed, table):
            _add(view, item)
        view.command_manager.execute(GroupCommand(scene, [bed, table]))
        heatmap = SunHeatmapController(scene, lambda: BERLIN)
        try:
            assert heatmap.run_for_day(date(2026, 6, 21))
            qtbot.waitUntil(lambda: heatmap.result() is not None and not heatmap.result_pending,
                            timeout=60000)
            from open_garden_planner.ui.canvas.sun_heatmap import (
                SunContourLayerItem,
                SunHeatmapOverlayItem,
            )

            assert any(isinstance(item, SunHeatmapOverlayItem)
                       for item in scene._ground_overlays)
            assert any(isinstance(item, SunContourLayerItem)
                       for item in scene._ground_overlays)
            shown = _render(scene)
            heatmap._overlay.setVisible(False)
            for line in heatmap._contour_items:
                line.setVisible(False)
            scene.refresh_ground_overlays()
            hidden = _render(scene)
            bed_tint = np.abs(_patch(shown, (250.0, 200.0)) - _patch(hidden, (250.0, 200.0)))
            assert bed_tint.sum() > 10.0, f"the grouped bed lost the map ({bed_tint})"
            table_tint = np.abs(_patch(shown, (320.0, 320.0), 3)
                                - _patch(hidden, (320.0, 320.0), 3))
            assert table_tint.max() < 1.0, "the table stands above the map"
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
        _add(view, parasol)   # stands up: its default height, never the ground band
        cold_frame = RectangleItem(320, 320, 40, 40, object_type=ObjectType.COLD_FRAME,
                                   layer_id=scene.active_layer.id)
        _add(view, cold_frame)   # stands on the bed: never under it
        note = TextItem(50, 50, "note", layer_id=scene.active_layer.id)
        _add(view, note)
        pin = JournalPinItem(80, 80, "note-1", layer_id=scene.active_layer.id)
        _add(view, pin)
        for item in (lawn, path, bed, zone):
            assert _in_ground_band(item), item.object_type
        assert lawn.zValue() < path.zValue() < bed.zValue() < zone.zValue(), "their order among themselves stays"
        for item in (shed, note, pin, parasol, cold_frame):
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

    def test_a_bed_grouped_with_its_planted_plant_paints_the_overlays_itself(
            self, view) -> None:
        """A bed grouped with the plants rooted in it is ONE z slot (#1031).

        A mixed group stays in its layer's band, above the sun-study overlays;
        the bed therefore paints the overlays on itself (clipped to its cover),
        so its soil keeps the shade and the grouped plants, drawn after it,
        stay bright. The pixel test below pins both halves.
        """
        from open_garden_planner.core.commands import GroupCommand

        scene = view.scene()
        bed = RectangleItem(200, 180, 80, 40, object_type=ObjectType.GARDEN_BED,
                            layer_id=scene.active_layer.id)
        plant = CircleItem(220, 200, 15, object_type=ObjectType.PERENNIAL,
                           layer_id=scene.active_layer.id)
        plant.parent_bed_id = bed.item_id
        for item in (bed, plant):
            _add(view, item)
        view.command_manager.execute(GroupCommand(scene, [bed, plant]))
        group = bed.parentItem()
        assert group is not None and group.zValue() >= 0.0
        assert group.zValue() > -500.0, "the group is above the shadow overlay"
        assert bed.object_type is ObjectType.GARDEN_BED  # and still a ground surface

    def test_a_bed_grouped_with_its_plant_still_receives_the_shadow(self, view) -> None:
        """The pixels, not only the band: grouping must not lift the soil out."""
        from open_garden_planner.core.commands import GroupCommand

        scene = view.scene()
        _shed(view)   # (200, 100) 200 cm tall; its noon shadow reaches (235, 200)
        _lawn(view)
        bed = RectangleItem(200, 180, 80, 40, object_type=ObjectType.GARDEN_BED,
                            layer_id=scene.active_layer.id)
        plant = CircleItem(215, 185, 10, object_type=ObjectType.PERENNIAL,
                           layer_id=scene.active_layer.id)
        plant.parent_bed_id = bed.item_id
        for item in (bed, plant):
            _add(view, item)
        view.command_manager.execute(GroupCommand(scene, [bed, plant]))
        controller = SunShadowController(scene, lambda: BERLIN)
        before = _render(scene)
        controller.set_enabled(True)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        after = _render(scene)
        shaded = _patch(before, (250.0, 200.0)) - _patch(after, (250.0, 200.0))
        assert shaded.sum() > 30.0, f"the grouped bed did not receive the shadow ({shaded})"
        crown = np.abs(_patch(before, (215.0, 185.0), 3) - _patch(after, (215.0, 185.0), 3))
        assert crown.max() < 1.0, f"the grouped plant was tinted by the ground shadow ({crown})"

    def test_a_bed_grouped_with_a_plant_of_another_parent_keeps_the_shadow(
            self, view) -> None:
        """The owner's second grouping (#1031): the bed and a plant of a planter
        outside it. The bed must keep its shade, and the planter's plant — drawn
        after the bed in the same group — must stay bright."""
        from open_garden_planner.core.commands import GroupCommand

        scene = view.scene()
        _shed(view)
        _lawn(view)
        bed = RectangleItem(200, 180, 80, 40, object_type=ObjectType.GARDEN_BED,
                            layer_id=scene.active_layer.id)
        planter = CircleItem(240, 240, 15, object_type=ObjectType.CONTAINER_ROUND,
                             layer_id=scene.active_layer.id)
        plant = CircleItem(240, 240, 10, object_type=ObjectType.PERENNIAL,
                           layer_id=scene.active_layer.id)
        for item in (bed, planter, plant):
            _add(view, item)
        plant.parent_bed_id = planter.item_id
        view.command_manager.execute(GroupCommand(scene, [bed, plant]))
        controller = SunShadowController(scene, lambda: BERLIN)
        before = _render(scene)
        controller.set_enabled(True)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        after = _render(scene)
        shaded = _patch(before, (250.0, 200.0)) - _patch(after, (250.0, 200.0))
        assert shaded.sum() > 30.0, f"the grouped bed lost its shadow ({shaded})"
        crown = np.abs(_patch(before, (240.0, 240.0), 3) - _patch(after, (240.0, 240.0), 3))
        assert crown.max() < 1.0, f"the planter's plant was tinted by the shade ({crown})"

    def test_grouping_and_ungrouping_return_the_same_pixels(self, view) -> None:
        """No clipped-shade halo survives the group (#1031).

        The first cut cut the grouped plants out of the shade; the hole was still
        there after ungrouping — a bright ring around every plant. The surface
        now paints the shade on itself, so an ungrouped plan is byte-identical
        to what it was before the group was made.
        """
        from open_garden_planner.core.commands import GroupCommand, UngroupCommand

        scene = view.scene()
        _shed(view)
        _lawn(view)
        bed = RectangleItem(200, 180, 80, 40, object_type=ObjectType.GARDEN_BED,
                            layer_id=scene.active_layer.id)
        plant = CircleItem(220, 200, 12, object_type=ObjectType.PERENNIAL,
                           layer_id=scene.active_layer.id)
        plant.parent_bed_id = bed.item_id
        for item in (bed, plant):
            _add(view, item)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_enabled(True)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        before = _render(scene)

        view.command_manager.execute(GroupCommand(scene, [bed, plant]))
        grouped = _render(scene)
        soil = np.abs(_patch(grouped, (250.0, 200.0)) - _patch(before, (250.0, 200.0)))
        assert soil.max() < 1.0, f"the grouped soil changed shade ({soil})"

        view.command_manager.execute(UngroupCommand(scene, bed.parentItem()))
        after = _render(scene)
        changed = np.abs(after.astype(int) - before.astype(int)).sum(axis=2)
        assert int((changed > 8).sum()) <= 8, (
            f"ungrouping left {int((changed > 8).sum())} changed pixels, "
            "a shade hole around the plants"
        )

    def test_the_live_canvas_repaints_a_grouped_bed_when_the_shadow_switches(
            self, view, qtbot) -> None:
        """A grouped bed's own paint reads the shadow (#1031): switching the
        overlay must invalidate that bed's cache, not only the overlay's."""
        from open_garden_planner.core.commands import GroupCommand

        scene = view.scene()
        view.resize(600, 500)
        view.show()
        view.scale(3, 3)
        _shed(view)
        _lawn(view)
        # Straddles the shed's noon shadow boundary (~y=275): the south strip is
        # shaded, the north one sunny — a flipped shade picture would swap them.
        bed = RectangleItem(200, 245, 80, 40, object_type=ObjectType.GARDEN_BED,
                            layer_id=scene.active_layer.id)
        plant = CircleItem(220, 255, 12, object_type=ObjectType.PERENNIAL,
                           layer_id=scene.active_layer.id)
        plant.parent_bed_id = bed.item_id
        for item in (bed, plant):
            _add(view, item)
        view.centerOn(QPointF(250.0, 270.0))
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_enabled(True)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        qtbot.wait(300)
        from open_garden_planner.ui.canvas.sun_shadow_controller import (
            SunShadowOverlayItem,
        )

        overlay = next(
            item for item in scene.items() if isinstance(item, SunShadowOverlayItem)
        )
        assert overlay._picture is not None, (
            "the overlay kept no picture: this test would only exercise the exact path"
        )
        shaded_points = ((250.0, 250.0), (250.0, 280.0))
        ungrouped = [_view_patch(view, point) for point in shaded_points]

        view.command_manager.execute(GroupCommand(scene, [bed, plant]))
        qtbot.wait(300)
        grouped = [_view_patch(view, point) for point in shaded_points]
        for point, before, after in zip(shaded_points, ungrouped, grouped, strict=True):
            assert np.abs(after - before).max() < 3.0, (
                f"the grouped bed changed shade at {point} ({before} -> {after})"
            )

        controller.set_enabled(False)
        qtbot.wait(300)
        sunny = _view_patch(view, shaded_points[0])
        assert sunny.sum() - ungrouped[0].sum() > 30.0, (
            f"the grouped bed kept the shade after it was switched off "
            f"({ungrouped[0]} -> {sunny})"
        )

        controller.set_enabled(True)
        qtbot.wait(300)
        again = _view_patch(view, shaded_points[0])
        assert np.abs(again - ungrouped[0]).max() < 3.0, (
            f"the grouped bed did not repaint when the shade came back ({again})"
        )

    def test_a_bed_grouped_with_an_unrelated_solid_stays_above_the_overlays(self, view) -> None:
        from open_garden_planner.core.commands import GroupCommand

        scene = view.scene()
        bed = RectangleItem(200, 180, 80, 40, object_type=ObjectType.GARDEN_BED,
                            layer_id=scene.active_layer.id)
        plant = CircleItem(220, 200, 15, object_type=ObjectType.PERENNIAL,
                           layer_id=scene.active_layer.id)
        plant.parent_bed_id = bed.item_id
        table = RectangleItem(300, 300, 40, 40, object_type=ObjectType.TABLE_RECTANGULAR,
                              layer_id=scene.active_layer.id)
        for item in (bed, plant, table):
            _add(view, item)
        view.command_manager.execute(GroupCommand(scene, [bed, plant, table]))
        group = bed.parentItem()
        assert group is not None and group.zValue() >= 0.0

    @pytest.mark.parametrize("alpha", (0, 128))
    def test_a_translucent_bed_grouped_with_its_plant_keeps_one_shadow(self, view, alpha) -> None:
        from open_garden_planner.core.commands import GroupCommand

        scene = view.scene()
        _shed(view)
        _lawn(view)
        layer = scene.active_layer.id
        bed = RectangleItem(200, 245, 80, 40, object_type=ObjectType.GARDEN_BED,
                            layer_id=layer)
        tint = QColor(170, 100, 50, alpha)
        bed.fill_pattern = FillPattern.SOLID
        bed.fill_color = tint
        bed.setBrush(QBrush(tint))
        plant = CircleItem(220, 255, 12, object_type=ObjectType.PERENNIAL, layer_id=layer)
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)
        for item in (bed, plant):
            _add(view, item)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(JUNE_NOON_UTC)
        controller.set_enabled(True)
        point = (250.0, 250.0)
        before = _patch(_render(scene), point)

        view.command_manager.execute(GroupCommand(scene, [bed, plant]))
        controller.recompute_now()
        assert _in_ground_band(bed.parentItem())
        after = _patch(_render(scene), point)
        assert np.abs(after - before).max() < 3, (before, after)

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
        assert plant.zValue() > tree.zValue(), "added after the tree: drawn over it"
        command, outcome = build_arrange_command(scene, [lawn2], ArrangeMode.SEND_TO_BACK)
        assert outcome is ArrangeOutcome.CHANGED
        view.command_manager.execute(command)
        assert lawn2.zValue() < lawn.zValue() < -500.0
        assert plant.zValue() > tree.zValue(), "the arrange of a lawn moved a plant"
        command, outcome = build_arrange_command(scene, [plant], ArrangeMode.BRING_TO_FRONT)
        assert outcome is ArrangeOutcome.ALREADY_AT_FRONT and command is None

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
