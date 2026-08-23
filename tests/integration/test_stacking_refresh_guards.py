"""Regression pins for the per-object stacking-order refresh machinery
(issue #338 review round 2, P1-1 and P1-2).

Round 1 shipped three guarantees with no dedicated regression test:
  (a) ``ProjectManager.load`` never leaves the scene's z-refresh suspended
      forever, even if the deserialize loop raises partway through (P1-1).
  (b) a z-refresh only ever touches items that actually carry a stacking
      rank -- a foreign ``QGraphicsLineItem`` sitting at a fixed overlay z
      (e.g. the 900-band dimension line, or the 10002-band soil badge) must
      survive both a full ``_update_items_z_order()`` sweep and an arrange
      command untouched (P1-2a).
  (c) a bulk re-add (``CreateItemsCommand``, ``DeleteItemsCommand.undo``)
      does ONE z-refresh pass for the whole batch, not one per item -- the
      O(n) vs O(n^2) distinction that makes bulk operations usable on a
      large scene (P1-2b).
"""
from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtWidgets import QGraphicsLineItem

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import CreateItemsCommand, DeleteItemsCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.stacking import ArrangeMode
from open_garden_planner.ui.canvas.arrange import build_arrange_command
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem


@pytest.fixture
def manager(qtbot) -> ProjectManager:  # noqa: ARG001 — qtbot for Qt init
    return ProjectManager()


def _rect(name: str, x: float, layer_id) -> RectangleItem:
    return RectangleItem(
        x, 0, 100, 100, object_type=ObjectType.GENERIC_RECTANGLE, name=name, layer_id=layer_id
    )


# ---------------------------------------------------------------------------
# (a) P1-1: bulk load stays exception-safe
# ---------------------------------------------------------------------------


class TestBulkLoadExceptionSafety:
    def test_exception_mid_deserialize_loop_does_not_strand_the_suspend_flag(
        self, manager: ProjectManager, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ``.ogp`` load that raises on its 2nd object must still leave
        ``scene._suspend_z_refresh`` False afterwards -- a stuck-True flag
        would silently disable every future z-refresh for the rest of the
        session (new items would never get a correct z-value again).
        """
        scene = CanvasScene(5000, 3000)
        layer_id = scene.active_layer.id
        scene.addItem(_rect("a", 0, layer_id))
        scene.addItem(_rect("b", 150, layer_id))
        scene.addItem(_rect("c", 300, layer_id))
        file_path = tmp_path / "explode.ogp"
        manager.save(scene, file_path)

        original_deserialize = manager._deserialize_item
        calls = {"n": 0}

        def _raise_on_second_object(obj: dict[str, Any]):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom mid-load")
            return original_deserialize(obj)

        monkeypatch.setattr(manager, "_deserialize_item", _raise_on_second_object)

        loaded_scene = CanvasScene(5000, 3000)
        with pytest.raises(RuntimeError, match="boom mid-load"):
            manager.load(loaded_scene, file_path)

        assert loaded_scene._suspend_z_refresh is False, (
            "An exception partway through the deserialize loop must not "
            "leave _suspend_z_refresh stuck True -- ProjectManager.load "
            "must use the suspend_z_refresh() context manager (whose "
            "finally always resumes it), not a bare begin/end call pair."
        )

        # And the scene must still refresh normally afterwards.
        extra = _rect("d", 450, loaded_scene.active_layer.id)
        loaded_scene.addItem(extra)
        assert extra.zValue() != 0.0


# ---------------------------------------------------------------------------
# (b) P1-2a: a refresh never touches an item outside the ranking system
# ---------------------------------------------------------------------------


class TestForeignZValuesSurviveRefresh:
    def test_fixed_z_overlay_items_are_untouched_by_full_refresh_and_arrange(
        self, canvas: CanvasView
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        a = _rect("a", 0, layer_id)
        b = _rect("b", 150, layer_id)
        scene.addItem(a)
        scene.addItem(b)

        # Plain QGraphicsLineItem, never given a stack_order/layer_id --
        # this is the shape of the DIMENSION_LINE_Z (900) and soil-badge
        # (10002) overlays, which must never be swept into a layer's
        # [z_order*100, z_order*100+100) band.
        low_overlay = QGraphicsLineItem(0, 0, 10, 10)
        low_overlay.setZValue(900)
        scene.addItem(low_overlay)

        high_overlay = QGraphicsLineItem(0, 0, 10, 10)
        high_overlay.setZValue(10002)
        scene.addItem(high_overlay)

        assert low_overlay.zValue() == 900
        assert high_overlay.zValue() == 10002

        scene._update_items_z_order()
        assert low_overlay.zValue() == 900, "A full refresh must not touch a foreign z."
        assert high_overlay.zValue() == 10002

        a.setSelected(True)
        cmd, outcome = build_arrange_command(scene, [a], ArrangeMode.BRING_TO_FRONT)
        assert cmd is not None, outcome
        canvas.command_manager.execute(cmd)

        assert low_overlay.zValue() == 900, "An arrange command must not touch a foreign z."
        assert high_overlay.zValue() == 10002


# ---------------------------------------------------------------------------
# (c) P1-2b: bulk re-add does O(1) refreshes, not O(n)
# ---------------------------------------------------------------------------


class TestBulkReAddRefreshCount:
    def test_create_items_command_does_a_constant_number_of_refreshes(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        items = [_rect(f"item{i}", i * 10, layer_id) for i in range(50)]

        calls = {"n": 0}
        original = CanvasScene._refresh_layer_z

        def _spy(self: CanvasScene, layer_id_arg):
            calls["n"] += 1
            return original(self, layer_id_arg)

        monkeypatch.setattr(CanvasScene, "_refresh_layer_z", _spy)

        cmd = CreateItemsCommand(scene, items, "items")
        canvas.command_manager.execute(cmd)

        max_expected = len(scene.layers) + 1
        assert calls["n"] <= max_expected, (
            f"CreateItemsCommand with {len(items)} items triggered "
            f"{calls['n']} per-layer z-refreshes; expected at most "
            f"{max_expected} (one full _update_items_z_order() pass), not "
            "one per item added."
        )
        assert calls["n"] < len(items)

    def test_delete_items_undo_does_a_constant_number_of_refreshes(
        self, canvas: CanvasView, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        items = [_rect(f"item{i}", i * 10, layer_id) for i in range(50)]
        for item in items:
            scene.addItem(item)

        cmd = DeleteItemsCommand(scene, items)
        canvas.command_manager.execute(cmd)

        calls = {"n": 0}
        original = CanvasScene._refresh_layer_z

        def _spy(self: CanvasScene, layer_id_arg):
            calls["n"] += 1
            return original(self, layer_id_arg)

        monkeypatch.setattr(CanvasScene, "_refresh_layer_z", _spy)

        canvas.command_manager.undo()

        max_expected = len(scene.layers) + 1
        assert calls["n"] <= max_expected, (
            f"DeleteItemsCommand.undo re-adding {len(items)} items "
            f"triggered {calls['n']} per-layer z-refreshes; expected at "
            f"most {max_expected}, not one per item re-added."
        )
        assert calls["n"] < len(items)
