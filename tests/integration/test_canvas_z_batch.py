"""Adding many items is one deferred z derivation, not one per item (#450)."""

from __future__ import annotations

from open_garden_planner.core.commands import MoveToLayerCommand
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem


def test_two_thousand_single_adds_derive_z_a_handful_of_times(qtbot) -> None:
    scene = CanvasScene(5000, 3000)
    calls = []
    original = scene._refresh_layer_z

    def spy(layer_id):
        calls.append(layer_id)
        return original(layer_id)

    scene._refresh_layer_z = spy  # type: ignore[method-assign]
    items = [RectangleItem(index * 2, 0, 1, 1) for index in range(2000)]
    for item in items:
        scene.addItem(item)

    # One synchronous derivation for the first item and one on the flush. A
    # per-add derivation would be 2 000 calls (the reported 45 s regression).
    assert len(calls) <= 10
    assert items[-1].zValue() > items[0].zValue()
    assert all(0.0 <= item.zValue() < 100.0 for item in items)

    scene.flush_z_refresh()
    assert len(calls) <= 10
    assert scene._next_rank_cache == {}
    values = [item.zValue() for item in items]
    assert all(0.0 <= value < 100.0 for value in values)
    assert values == sorted(values)
    # _refresh_layer_z is a derivation, never a rank writer: the ranks are
    # still exactly the distinct ones addItem assigned.
    assert len({item.stack_order for item in items}) == len(items)


def test_a_bed_with_existing_plants_still_refreshes_synchronously(qtbot) -> None:
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem

    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    plant = CircleItem(
        200, 200, 20, object_type=ObjectType.TREE, layer_id=layer_id
    )
    scene.addItem(plant)
    bed = RectangleItem(
        0, 0, 400, 400, object_type=ObjectType.RAISED_BED, layer_id=layer_id
    )
    bed.add_child_id(plant.item_id)
    plant.parent_bed_id = bed.item_id
    scene.addItem(bed)

    assert plant.zValue() > bed.zValue()


def test_clear_cancels_a_pending_deferred_refresh(qtbot) -> None:
    scene = CanvasScene(5000, 3000)
    scene.addItem(RectangleItem(0, 0, 10, 10))
    scene.addItem(RectangleItem(20, 0, 10, 10))
    assert scene._z_refresh_timer.isActive()
    scene.clear()
    assert not scene._z_refresh_timer.isActive()
    assert scene._provisional_z == {}


def test_a_rank_writer_invalidates_the_next_rank_cache(qtbot) -> None:
    """MoveToLayerCommand assigns N ranks after asking for one (#450 review)."""
    scene = CanvasScene(5000, 3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    target = Layer(name="Target", z_order=0)
    scene.add_layer(target)
    originals = [RectangleItem(index * 20, 0, 10, 10) for index in range(3)]
    for item in originals:
        scene.addItem(item)

    view.command_manager.execute(
        MoveToLayerCommand(originals, target.id, scene, target.name)
    )
    newest = RectangleItem(200, 0, 10, 10)
    newest.layer_id = target.id
    scene.addItem(newest)
    scene.flush_z_refresh()

    ranks = [item.stack_order for item in (*originals, newest)]
    assert len(set(ranks)) == len(ranks), ranks
    assert newest.zValue() > max(item.zValue() for item in originals)


def test_a_layer_reorder_invalidates_a_stale_provisional_z(qtbot) -> None:
    scene = CanvasScene(5000, 3000)
    layer = scene.active_layer
    first = RectangleItem(0, 0, 10, 10, layer_id=layer.id)
    scene.addItem(first)
    assert 0.0 <= first.zValue() < 100.0

    layer.z_order = 1
    scene._update_items_z_order()
    second = RectangleItem(20, 0, 10, 10, layer_id=layer.id)
    scene.addItem(second)

    assert second.zValue() >= 100.0
    assert second.zValue() > first.zValue()


def test_a_ground_surface_takes_its_band_before_the_deferred_refresh(qtbot) -> None:
    """A bulk add keeps a lawn under the sun overlays and the next item in band.

    The provisional cache holds a value in the LAYER's band, never the highest
    ``zValue``: a ground surface's z lives in ``GROUND_Z_RANGE`` (negative), so
    seeding from it would drop the next added item below the background — the
    merge of the ground band (PR #584) with the batched derivation (#450).
    """
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.canvas_scene import GROUND_Z_RANGE

    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    # A load seeds the cache for every layer before any add.
    scene._update_items_z_order()

    lawn = RectangleItem(0, 0, 400, 400, object_type=ObjectType.LAWN, layer_id=layer_id)
    scene.addItem(lawn)
    low, high = GROUND_Z_RANGE
    assert low < lawn.zValue() < high, lawn.zValue()

    # A save/load boundary derives the layer, which now holds only ground
    # surfaces: the next item must not be seeded from the lawn's negative z.
    scene.flush_z_refresh()
    solid = RectangleItem(500, 0, 10, 10, layer_id=layer_id)
    scene.addItem(solid)
    assert 0.0 <= solid.zValue() < 100.0, solid.zValue()
    assert solid.zValue() > lawn.zValue()


def test_a_large_existing_layer_still_batches_its_adds(qtbot) -> None:
    scene = CanvasScene(5000, 3000)
    items = [RectangleItem(index, 0, 1, 1) for index in range(1000)]
    for item in items:
        scene.addItem(item)
    scene.flush_z_refresh()

    calls = []
    original = scene._refresh_layer_z

    def spy(layer_id):
        calls.append(layer_id)
        return original(layer_id)

    scene._refresh_layer_z = spy  # type: ignore[method-assign]
    for index in range(500):
        scene.addItem(RectangleItem(2000 + index, 0, 1, 1))
    scene.flush_z_refresh()

    assert len(calls) <= 10, len(calls)
    assert all(0.0 <= item.zValue() < 100.0 for item in scene.items())
