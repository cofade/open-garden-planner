"""`.ogp` save/load round-trip tests for per-object stacking order (#338).

Covers the ADR-043 persistence contract:
  (a) the historical inversion bug (`scene.items()` is top-first, so a naive
      save/load round-trip reversed same-layer stacking) is fixed,
  (b) explicit ranks round-trip byte-for-byte through the JSON,
  (c) an old-format file (no "stack_order" keys) loads in file order,
  (d) FILE_VERSION is unchanged and the raw JSON carries "stack_order",
  (e) paste/duplicate preserve the relative stacking of the copies,
  (f) delete -> undo restores the exact slot.
"""
from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import DeleteItemsCommand, SetParentBedCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CircleItem,
    PolygonItem,
    RectangleItem,
)


@pytest.fixture
def manager(qtbot) -> ProjectManager:  # noqa: ARG001 — qtbot for Qt init
    return ProjectManager()


def _bottom_to_top_names(scene: CanvasScene) -> list[str]:
    """Every named RectangleItem in the scene, bottom-to-top by z-value."""
    items = [i for i in scene.items() if isinstance(i, RectangleItem) and i.name]
    return [i.name for i in sorted(items, key=lambda i: i.zValue())]


def _rect(
    name: str,
    x: float,
    layer_id,
    object_type: ObjectType = ObjectType.GENERIC_RECTANGLE,
) -> RectangleItem:
    return RectangleItem(
        x, 0, 100, 100, object_type=object_type, name=name, layer_id=layer_id
    )


def _bottom_to_top_named_curves(scene: CanvasScene) -> list[str]:
    """Every named Rectangle/Arc/Bezier item in the scene, bottom-to-top by z.

    Unlike :func:`_bottom_to_top_names`, this also picks up ``ArcItem``/
    ``BezierItem`` — neither is a ``GardenItemMixin`` (they are
    ``CurveEditMixin, QGraphicsPathItem``) but both carry ``stack_order``/
    ``layer_id`` and a ``name`` (issue #338 review round 2, P0).
    """
    items = [
        i
        for i in scene.items()
        if isinstance(i, (RectangleItem, ArcItem, BezierItem)) and i.name
    ]
    return [i.name for i in sorted(items, key=lambda i: i.zValue())]


# ---------------------------------------------------------------------------
# (a) The inversion regression
# ---------------------------------------------------------------------------


def test_stacking_order_survives_save_load_roundtrip(manager, tmp_path) -> None:
    """lawn -> path -> bed (bottom to top) must reload in the same order.

    Before the #338 fix, `_serialize_scene` walked `scene.items()` (top-first)
    directly, and load re-inserted in file order -- so every same-layer
    stacking order got reversed on every save/load cycle (docs/11.4).
    """
    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    lawn = _rect("lawn", 0, layer_id, ObjectType.LAWN)
    path = _rect("path", 150, layer_id, ObjectType.PATH)
    bed = _rect("bed", 300, layer_id, ObjectType.GARDEN_BED)
    scene.addItem(lawn)
    scene.addItem(path)
    scene.addItem(bed)
    assert _bottom_to_top_names(scene) == ["lawn", "path", "bed"]

    file_path = tmp_path / "stack.ogp"
    manager.save(scene, file_path)

    loaded_scene = CanvasScene(5000, 3000)
    manager.load(loaded_scene, file_path)

    assert _bottom_to_top_names(loaded_scene) == ["lawn", "path", "bed"], (
        "Same-layer stacking order must survive a save/load round-trip."
    )


# ---------------------------------------------------------------------------
# (b) Explicit ranks round-trip
# ---------------------------------------------------------------------------


def test_explicit_ranks_round_trip(manager, tmp_path) -> None:
    """An explicit, non-default rank round-trips through the raw JSON, and
    the order it implies survives the load.

    Load always does a post-load renumber to clean STACK_STEP multiples
    (ADR-043 -- "so that files saved by the new app carry honest ranks"),
    so the exact value 500 isn't expected to survive verbatim; the ORDER it
    encoded (b above a) is the persisted invariant.
    """
    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    a = _rect("a", 0, layer_id)
    b = _rect("b", 150, layer_id)
    scene.addItem(a)
    scene.addItem(b)
    a.stack_order = 9000  # explicitly reverse the default add-order rank
    b.stack_order = 500

    file_path = tmp_path / "ranks.ogp"
    manager.save(scene, file_path)

    raw = json.loads(file_path.read_text(encoding="utf-8"))
    saved_ranks = {obj["name"]: obj["stack_order"] for obj in raw["objects"]}
    assert saved_ranks == {"a": 9000, "b": 500}

    loaded_scene = CanvasScene(5000, 3000)
    manager.load(loaded_scene, file_path)

    # b (rank 500) sorts below a (rank 9000) -- the explicit reversal of the
    # add-order survives the round-trip.
    assert _bottom_to_top_names(loaded_scene) == ["b", "a"]


# ---------------------------------------------------------------------------
# (c) Old-format file (no "stack_order" keys) loads in file order
# ---------------------------------------------------------------------------


def test_old_format_file_without_stack_order_loads_in_file_order(
    manager, tmp_path
) -> None:
    """A genuinely old-shaped file (no "stack_order" keys, objects listed
    TOP-first the way v1.27.2's buggy `_serialize_scene` wrote them) must
    load without raising, and must reproduce exactly what re-opening that
    file in the OLD app itself would have shown.

    v1.27.2 serialized via `scene.items()` directly -- Qt's native
    top-first order -- with no `stack_order` key (the key didn't exist yet).
    Both the old app's loader and the current one build the scene by
    `addItem`-ing objects in file-array order, and an unranked item always
    ranks on top of whatever's already there -- so array order becomes
    bottom-to-top INSERTION order on load, regardless of which app reads
    it. A file listing the topmost item first therefore loads back
    *inverted* from how it originally looked when saved -- that is the
    historical bug (docs/11.4) baked permanently into any file an old app
    already wrote, and it is self-consistent: reloading it in the OLD app
    would show the exact same inverted order, not a fresh corruption. This
    test pins that the current loader reproduces that same result (doesn't
    crash, doesn't invert AGAIN, doesn't silently "fix" it into some other
    order) rather than actually testing today's save format.

    NOTE: this fixture must NOT be built by round-tripping through
    `manager.save()` and merely stripping "stack_order" -- today's save
    already writes bottom-first (the #338 fix), so that would produce a
    file already in the shape the new loader expects and the test would
    pass even if the legacy (top-first, no-key) case were broken.
    """
    # The scene as it looked when originally drawn and saved by the OLD
    # app: lawn on the bottom, path on top of it.
    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    lawn = _rect("lawn", 0, layer_id, ObjectType.LAWN)
    path = _rect("path", 150, layer_id, ObjectType.PATH)
    scene.addItem(lawn)
    scene.addItem(path)
    assert _bottom_to_top_names(scene) == ["lawn", "path"]

    file_path = tmp_path / "legacy.ogp"
    manager.save(scene, file_path)  # current save: bottom-first, with ranks

    # Reshape into the OLD app's file: TOP-first object order, no
    # "stack_order" key at all.
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    raw["objects"].reverse()  # bottom-first -> top-first (path, then lawn)
    for obj in raw["objects"]:
        obj.pop("stack_order", None)
    file_path.write_text(json.dumps(raw), encoding="utf-8")

    loaded_scene = CanvasScene(5000, 3000)
    manager.load(loaded_scene, file_path)  # must not raise

    # File order (path first, then lawn) becomes bottom-to-top insertion
    # order -- the visual stacking is inverted from the original ["lawn",
    # "path"], matching what the OLD app itself would show on reload.
    assert _bottom_to_top_names(loaded_scene) == ["path", "lawn"]


# ---------------------------------------------------------------------------
# (d) FILE_VERSION unchanged and the raw JSON carries stack_order
# ---------------------------------------------------------------------------


def test_file_version_unchanged_and_stack_order_key_present(manager, tmp_path) -> None:
    assert FILE_VERSION == "1.4"

    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    scene.addItem(_rect("lawn", 0, layer_id, ObjectType.LAWN))

    file_path = tmp_path / "version.ogp"
    manager.save(scene, file_path)

    raw = json.loads(file_path.read_text(encoding="utf-8"))
    assert raw["version"] == "1.4"
    assert len(raw["objects"]) == 1
    assert "stack_order" in raw["objects"][0]


# ---------------------------------------------------------------------------
# (e) Paste / duplicate preserve relative stacking
# ---------------------------------------------------------------------------


class TestPasteDuplicatePreservesStacking:
    @pytest.fixture
    def canvas(self, qtbot) -> CanvasView:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.set_snap_enabled(False)
        return view

    def test_duplicate_preserves_relative_order_of_two_overlapping_copies(
        self, canvas: CanvasView
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        # Two overlapping rects, back added after front so back ends up on
        # top -- name encodes intended relative order for the assertion.
        back = RectangleItem(
            0, 0, 100, 100, object_type=ObjectType.LAWN, name="back", layer_id=layer_id
        )
        front = RectangleItem(
            20, 20, 100, 100,
            object_type=ObjectType.GARDEN_BED,
            name="front",
            layer_id=layer_id,
        )
        scene.addItem(back)
        scene.addItem(front)
        assert back.zValue() < front.zValue()

        back.setSelected(True)
        front.setSelected(True)
        canvas.duplicate_selected()

        dup_back = next(
            i
            for i in scene.items()
            if isinstance(i, RectangleItem) and i.name == "back" and i is not back
        )
        dup_front = next(
            i
            for i in scene.items()
            if isinstance(i, RectangleItem) and i.name == "front" and i is not front
        )
        assert dup_back.zValue() < dup_front.zValue(), (
            "Duplicated copies must keep the same relative stacking order "
            "as their originals."
        )

    def test_copy_paste_preserves_relative_order_of_two_overlapping_copies(
        self, canvas: CanvasView
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        back = RectangleItem(
            0, 0, 100, 100, object_type=ObjectType.LAWN, name="back", layer_id=layer_id
        )
        front = RectangleItem(
            20, 20, 100, 100,
            object_type=ObjectType.GARDEN_BED,
            name="front",
            layer_id=layer_id,
        )
        scene.addItem(back)
        scene.addItem(front)

        back.setSelected(True)
        front.setSelected(True)
        canvas.copy_selected()
        for item in scene.selectedItems():
            item.setSelected(False)
        canvas.paste()

        dup_back = next(
            i
            for i in scene.items()
            if isinstance(i, RectangleItem) and i.name == "back" and i is not back
        )
        dup_front = next(
            i
            for i in scene.items()
            if isinstance(i, RectangleItem) and i.name == "front" and i is not front
        )
        assert dup_back.zValue() < dup_front.zValue()


# ---------------------------------------------------------------------------
# (f) Delete -> undo restores the exact slot
# ---------------------------------------------------------------------------


class TestDeleteUndoRestoresSlot:
    @pytest.fixture
    def canvas(self, qtbot) -> CanvasView:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.set_snap_enabled(False)
        return view

    def test_delete_middle_item_then_undo_restores_order(
        self, canvas: CanvasView
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, layer_id)
        b = _rect("b", 150, layer_id)
        c = _rect("c", 300, layer_id)
        scene.addItem(a)
        scene.addItem(b)
        scene.addItem(c)
        assert _bottom_to_top_names(scene) == ["a", "b", "c"]
        b_rank_before = b.stack_order

        command = DeleteItemsCommand(scene, [b])
        canvas.command_manager.execute(command)
        assert _bottom_to_top_names(scene) == ["a", "c"]

        canvas.command_manager.undo()

        assert _bottom_to_top_names(scene) == ["a", "b", "c"], (
            "Undoing a delete must restore the exact original slot, not "
            "just re-add the item on top."
        )
        assert b.stack_order == b_rank_before


# ---------------------------------------------------------------------------
# (f2) Delete -> undo restores a plant's derived z above its bed, whichever
#      of the two was deleted (issue #338 review round 3, P0)
# ---------------------------------------------------------------------------


class TestDeleteUndoRestoresPlantAboveBed:
    """`DeleteItemsCommand.undo` used to refresh the derived z only when a
    bed's child list was relinked (an internal ``relinked`` flag). Undoing
    the deletion of a linked PLANT restores ``parent_bed_id`` through the
    command's other snapshot branch (``_plant_parents``) without touching
    any bed's child list, so that flag never fired and the plant came back
    rendering below its bed. The fix drops the flag and always refreshes
    once anything was restored -- see ``DeleteItemsCommand.undo``.
    """

    @pytest.fixture
    def canvas(self, qtbot) -> CanvasView:
        scene = CanvasScene(width_cm=5000, height_cm=3000)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        view.set_snap_enabled(False)
        return view

    def _linked_plant_and_bed(
        self, canvas: CanvasView
    ) -> tuple[CanvasScene, CircleItem, PolygonItem]:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        # Plant added BEFORE its bed, so its raw insertion-order rank is
        # lower than the bed's -- only the parent-bed clamp puts the plant
        # back above once linked.
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
        scene.addItem(plant)
        scene.addItem(bed)
        assert plant.stack_order is not None and bed.stack_order is not None
        assert plant.stack_order < bed.stack_order

        link = SetParentBedCommand(scene, plant, None, bed.item_id)
        canvas.command_manager.execute(link)
        assert plant.zValue() > bed.zValue()
        return scene, plant, bed

    @pytest.mark.parametrize("delete_target", ["plant", "bed"])
    def test_undo_delete_restores_plant_above_bed(
        self, canvas: CanvasView, delete_target: str
    ) -> None:
        scene, plant, bed = self._linked_plant_and_bed(canvas)
        target = plant if delete_target == "plant" else bed

        delete = DeleteItemsCommand(scene, [target])
        canvas.command_manager.execute(delete)
        canvas.command_manager.undo()

        assert plant.zValue() > bed.zValue(), (
            f"Undoing the deletion of the {delete_target} must leave the "
            "plant rendering above its bed again -- DeleteItemsCommand.undo "
            "must refresh z whenever anything was restored, not only when "
            "a bed's child list was relinked."
        )


# ---------------------------------------------------------------------------
# (g) Arc/Bezier items are ranked on add and survive save/load (issue #338
#     review round 2, P0 -- neither is a GardenItemMixin, so the ranking
#     block in CanvasScene.addItem must not be gated on that isinstance
#     check).
# ---------------------------------------------------------------------------


def _arc(name: str, cx: float, layer_id) -> ArcItem:
    return ArcItem(
        center=QPointF(cx, 0),
        radius=20.0,
        start_deg=0.0,
        span_deg=90.0,
        name=name,
        layer_id=layer_id,
    )


def _bezier(name: str, cx: float, layer_id) -> BezierItem:
    return BezierItem(
        anchors=[QPointF(cx, 0), QPointF(cx + 50, 50)],
        handles_in=[QPointF(cx, 0), QPointF(cx + 30, 50)],
        handles_out=[QPointF(cx + 20, 0), QPointF(cx + 50, 50)],
        name=name,
        layer_id=layer_id,
    )


def test_arc_is_ranked_on_add_and_renders_above_earlier_rect() -> None:
    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    rect = _rect("rect", 0, layer_id)
    scene.addItem(rect)
    arc = _arc("arc", 200, layer_id)
    scene.addItem(arc)

    assert arc.stack_order is not None, (
        "ArcItem must get a stacking rank on add, same as any other ranked "
        "item -- the rank-assignment block must not be gated on "
        "isinstance(item, GardenItemMixin)."
    )
    assert arc.zValue() > rect.zValue(), (
        "An arc added after a rect must render above it, not stay at the "
        "default z=0 until some unrelated refresh sweeps it into place."
    )


def test_bezier_is_ranked_on_add_and_renders_above_earlier_rect() -> None:
    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    rect = _rect("rect", 0, layer_id)
    scene.addItem(rect)
    bezier = _bezier("bezier", 200, layer_id)
    scene.addItem(bezier)

    assert bezier.stack_order is not None
    assert bezier.zValue() > rect.zValue()


def test_arc_and_bezier_survive_save_load_roundtrip_in_order(
    manager, tmp_path
) -> None:
    """rect -> arc -> bezier (bottom to top) must reload in the same order."""
    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    rect = _rect("rect", 0, layer_id)
    arc = _arc("arc", 200, layer_id)
    bezier = _bezier("bezier", 400, layer_id)
    scene.addItem(rect)
    scene.addItem(arc)
    scene.addItem(bezier)
    assert _bottom_to_top_named_curves(scene) == ["rect", "arc", "bezier"]

    file_path = tmp_path / "arc_bezier_stack.ogp"
    manager.save(scene, file_path)

    raw = json.loads(file_path.read_text(encoding="utf-8"))
    by_name = {obj.get("name"): obj for obj in raw["objects"]}
    assert "stack_order" in by_name["arc"], (
        "ArcItem.to_dict() must write stack_order once addItem ranks it."
    )
    assert "stack_order" in by_name["bezier"]

    loaded_scene = CanvasScene(5000, 3000)
    manager.load(loaded_scene, file_path)

    assert _bottom_to_top_named_curves(loaded_scene) == ["rect", "arc", "bezier"], (
        "Arc/bezier stacking order must survive a save/load round-trip, "
        "same as any other ranked item type."
    )
