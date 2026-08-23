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

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import DeleteItemsCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem


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
    scene = CanvasScene(5000, 3000)
    layer_id = scene.active_layer.id
    lawn = _rect("lawn", 0, layer_id, ObjectType.LAWN)
    path = _rect("path", 150, layer_id, ObjectType.PATH)
    scene.addItem(lawn)
    scene.addItem(path)

    file_path = tmp_path / "legacy.ogp"
    manager.save(scene, file_path)

    # Simulate an older app version's file: strip every "stack_order" key.
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    for obj in raw["objects"]:
        obj.pop("stack_order", None)
    file_path.write_text(json.dumps(raw), encoding="utf-8")

    loaded_scene = CanvasScene(5000, 3000)
    manager.load(loaded_scene, file_path)  # must not raise

    # File order (lawn, then path) is what an old app would have shown.
    assert _bottom_to_top_names(loaded_scene) == ["lawn", "path"]


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
