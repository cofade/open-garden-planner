"""Regression test for the derive-only stacking clamp (issue #338).

A plant's z-value must always render above its parent bed's, driven by the
scene's normalized per-layer stacking order
(`core.stacking.normalize_order` via `CanvasScene._normalized_layer_order`)
rather than an ad-hoc z bump. See ADR-043 and
`docs/08-crosscutting-concepts/` section 8.25.

Superseded assumption from the old (pre-#338) version of this file: z used
to be bumped directly on `parent_bed_id`-linked items regardless of layer.
Now z is only ever derived for items that belong to an actual layer, so
every fixture here explicitly assigns `layer_id`.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import GROUND_Z_RANGE, CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem


def _make_scene_with_bed_and_plant(qtbot) -> tuple[CanvasScene, PolygonItem, CircleItem]:
    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    bed = PolygonItem(
        [QPointF(0, 0), QPointF(400, 0), QPointF(400, 400), QPointF(0, 400)],
        object_type=ObjectType.GARDEN_BED,
        layer_id=layer_id,
    )
    # edged (a height): an in-ground bed without one lies in the ground band under every
    # plant, and the clamp this file pins would never be what keeps the plant on top
    # (senior review of the PR #584 manual pass) — the in-ground case has its own test
    bed.metadata["object_height_cm"] = 20.0
    plant = CircleItem(
        center_x=200,
        center_y=200,
        radius=20,
        object_type=ObjectType.TREE,
        layer_id=layer_id,
    )
    scene.addItem(bed)
    scene.addItem(plant)
    plant.parent_bed_id = bed.item_id
    bed.add_child_id(plant.item_id)
    return scene, bed, plant


class TestPlantAboveBedAfterLink:
    def test_plant_zvalue_above_bed_after_linking(self, qtbot) -> None:
        scene, bed, plant = _make_scene_with_bed_and_plant(qtbot)

        scene._update_items_z_order()

        assert plant.zValue() > bed.zValue(), (
            "Plant must render above its parent bed once linked -- the "
            "normalized stacking order clamps a plant to sit immediately "
            "above its bed."
        )

    def test_stays_above_after_a_second_refresh(self, qtbot) -> None:
        scene, bed, plant = _make_scene_with_bed_and_plant(qtbot)
        scene._update_items_z_order()
        first_plant_z = plant.zValue()
        first_bed_z = bed.zValue()

        scene._update_items_z_order()

        assert plant.zValue() > bed.zValue()
        # Idempotent: refreshing again with nothing changed reproduces the
        # exact same derived z-values.
        assert plant.zValue() == first_plant_z
        assert bed.zValue() == first_bed_z

    def test_plant_stays_above_bed_even_when_added_first(self, qtbot) -> None:
        # Plant added to the scene BEFORE its bed, so raw insertion order
        # alone would rank the bed above the plant -- normalization must
        # still clamp the plant above the bed.
        scene = CanvasScene(5000, 3000)
        layer_id = scene.active_layer.id
        plant = CircleItem(
            center_x=200,
            center_y=200,
            radius=20,
            object_type=ObjectType.TREE,
            layer_id=layer_id,
        )
        bed = PolygonItem(
            [QPointF(0, 0), QPointF(400, 0), QPointF(400, 400), QPointF(0, 400)],
            object_type=ObjectType.GARDEN_BED,
            layer_id=layer_id,
        )
        bed.metadata["object_height_cm"] = 20.0  # edged: in the plant's band (see fixture)
        scene.addItem(plant)
        scene.addItem(bed)
        plant.parent_bed_id = bed.item_id
        bed.add_child_id(plant.item_id)

        scene._update_items_z_order()

        assert plant.zValue() > bed.zValue()

    def test_plant_without_parent_bed_unaffected(self, qtbot) -> None:
        scene = CanvasScene(5000, 3000)
        layer_id = scene.active_layer.id
        plant = CircleItem(
            center_x=200,
            center_y=200,
            radius=20,
            object_type=ObjectType.TREE,
            layer_id=layer_id,
        )
        scene.addItem(plant)
        # Should run without error and not crash on a missing parent bed.
        scene._update_items_z_order()

    def test_unrelated_item_in_same_layer_is_unaffected(self, qtbot) -> None:
        scene, bed, plant = _make_scene_with_bed_and_plant(qtbot)
        layer_id = scene.active_layer.id
        # a solid: a lawn now lies under every plant whatever its rank (manual pass of
        # PR #584, GROUND_Z_RANGE) — the clamp question needs an item in the same band
        table = RectangleItem(
            0, 500, 200, 100, object_type=ObjectType.TABLE_RECTANGULAR, layer_id=layer_id
        )
        scene.addItem(table)

        scene._update_items_z_order()

        # the table has no parent/child relationship with bed or plant, so the
        # clamp never touches it -- it keeps its own place in the stack
        # (the last item added, so it lands on top of both).
        assert plant.zValue() > bed.zValue()
        assert table.zValue() > plant.zValue()
        # And every z-value stays strictly inside the layer's band.
        layer = scene.get_layer_by_id(layer_id)
        assert layer is not None
        for z in (bed.zValue(), plant.zValue(), table.zValue()):
            assert layer.z_order * 100 <= z < layer.z_order * 100 + 100

    def test_a_plant_on_an_in_ground_bed_is_above_it_by_the_ground_band(self, qtbot) -> None:
        """An in-ground bed without a height is a ground surface (PR #584 manual
        pass): it lies in the ground band, under its plants whatever the ranks."""
        scene, bed, plant = _make_scene_with_bed_and_plant(qtbot)
        del bed.metadata["object_height_cm"]
        scene._update_items_z_order()
        assert GROUND_Z_RANGE[0] < bed.zValue() < GROUND_Z_RANGE[1]
        assert plant.zValue() > bed.zValue()
