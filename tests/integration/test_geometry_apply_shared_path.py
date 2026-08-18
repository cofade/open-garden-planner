"""The canonical geometry-apply path (US-D2.2), and the bug that extracting it exposed.

Before US-D2.2 every caller of ``ResizeItemCommand`` built its own ``apply_func``
closure. The copies had drifted: each item's drag-release closure re-pinned
``transformOriginPoint`` onto the new rect centre (the #218 fix), while the
three numeric-entry branches in ``properties_panel`` never did. Resizing a
**rotated** item from the panel therefore left the pivot behind, so the item
lurched away on the next repaint and saved a displaced position.

Measured before the fix: a TREE at scene (200, 200), rotated 30 degrees, resized
from radius 50 to 100 cm through the panel's own code, ended up centred at
(263.4, 163.4) — **73.2 cm** from where it was. At rotation 0 the drift is
exactly 0.0, which is why it survived every test and every manual pass.

These tests pin (a) that the drift is gone, (b) the mechanism that caused it, and
(c) that the panel and the Agent API now produce identical geometry — which is
only guaranteed because they run the same function.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF, QRectF

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rect_like_geometry,
    apply_rotation,
    build_circle_resize,
    build_ellipse_resize,
    build_rect_resize,
    is_resizable_rect_like,
)
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel

_ROTATIONS = [0.0, 30.0, 90.0, 215.0]
_CORNER_NAMES = ["TOP_LEFT", "TOP_RIGHT", "BOTTOM_LEFT", "BOTTOM_RIGHT"]


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=8000, height_cm=6000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _scene_centre(item: object) -> QPointF:
    return item.mapToScene(item.rect().center())  # type: ignore[attr-defined]


class TestRotatedPanelResizeRegression:
    """The bug the extraction exposed, pinned so it cannot come back."""

    @pytest.mark.parametrize("rotation", _ROTATIONS)
    def test_panel_resize_holds_a_rotated_circle_in_place(
        self, canvas: CanvasView, qtbot: object, rotation: float  # noqa: ARG002
    ) -> None:
        scene = canvas.scene()
        item = CircleItem(200.0, 200.0, 50.0, object_type=ObjectType.TREE)
        scene.addItem(item)
        apply_rotation(item, rotation)
        before = _scene_centre(item)

        panel = PropertiesPanel()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_command_manager(canvas.command_manager)
        panel._on_dimension_changed(item, "circle_diameter", 200.0)

        after = _scene_centre(item)
        drift = math.hypot(after.x() - before.x(), after.y() - before.y())
        assert drift < 1e-6, (
            f"a rotated circle resized from the properties panel drifted "
            f"{drift:.3f} cm (rotation {rotation} degrees). Before US-D2.2 this "
            f"was 73.2 cm at 30 degrees and 0.0 at 0 degrees."
        )
        assert item.rect().width() == pytest.approx(200.0)

    @pytest.mark.parametrize("rotation", _ROTATIONS)
    def test_panel_resize_re_pins_the_rotation_origin(
        self, canvas: CanvasView, qtbot: object, rotation: float  # noqa: ARG002
    ) -> None:
        """The mechanism, asserted directly: the serializer invariant
        ``transformOriginPoint == rect().center()`` (#219) must survive a
        numeric-entry resize. It is the single line the panel's closures were
        missing, and the reason the item drifted."""
        scene = canvas.scene()
        item = RectangleItem(300.0, 300.0, 100.0, 80.0)
        scene.addItem(item)
        apply_rotation(item, rotation)

        panel = PropertiesPanel()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_command_manager(canvas.command_manager)

        class _Spin:
            def __init__(self, value: float) -> None:
                self._value = value

            def value(self) -> float:
                return self._value

        panel._on_dimension_changed(
            item, "rect_size", None, _Spin(240.0), _Spin(160.0)
        )

        origin = item.transformOriginPoint()
        centre = item.rect().center()
        assert origin.x() == pytest.approx(centre.x())
        assert origin.y() == pytest.approx(centre.y())

    def test_undo_restores_a_rotated_panel_resize_exactly(
        self, canvas: CanvasView, qtbot: object  # noqa: ARG002
    ) -> None:
        scene = canvas.scene()
        item = CircleItem(500.0, 500.0, 40.0, object_type=ObjectType.SHRUB)
        scene.addItem(item)
        apply_rotation(item, 45.0)
        before_centre = _scene_centre(item)
        before_radius = item.radius

        panel = PropertiesPanel()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_command_manager(canvas.command_manager)
        panel._on_dimension_changed(item, "circle_diameter", 300.0)
        canvas.command_manager.undo()

        after_centre = _scene_centre(item)
        assert item.radius == pytest.approx(before_radius)
        assert after_centre.x() == pytest.approx(before_centre.x())
        assert after_centre.y() == pytest.approx(before_centre.y())


class TestPanelAndAgentAgree:
    """The point of the extraction: two callers, one geometry."""

    @pytest.mark.parametrize("rotation", _ROTATIONS)
    def test_circle_panel_and_agent_produce_the_same_geometry(
        self, canvas: CanvasView, qtbot: object, rotation: float  # noqa: ARG002
    ) -> None:
        scene = canvas.scene()
        panel_item = CircleItem(200.0, 200.0, 50.0, object_type=ObjectType.TREE)
        agent_item = CircleItem(200.0, 200.0, 50.0, object_type=ObjectType.TREE)
        scene.addItem(panel_item)
        scene.addItem(agent_item)
        apply_rotation(panel_item, rotation)
        apply_rotation(agent_item, rotation)

        panel = PropertiesPanel()
        qtbot.addWidget(panel)  # type: ignore[attr-defined]
        panel.set_command_manager(canvas.command_manager)
        panel._on_dimension_changed(panel_item, "circle_diameter", 180.0)

        # What the Agent API's resize_object does for the same target.
        _old, new = build_circle_resize(agent_item, 180.0, keep_center=True)
        apply_rect_like_geometry(agent_item, new)

        assert panel_item.rect() == agent_item.rect()
        assert panel_item.pos().x() == pytest.approx(agent_item.pos().x())
        assert panel_item.pos().y() == pytest.approx(agent_item.pos().y())
        assert panel_item.radius == pytest.approx(agent_item.radius)


class TestAnchorPolicies:
    @pytest.mark.parametrize("rotation", _ROTATIONS)
    def test_keep_center_holds_the_scene_centre_for_every_shape(
        self, canvas: CanvasView, rotation: float
    ) -> None:
        scene = canvas.scene()
        cases = [
            (CircleItem(400.0, 400.0, 60.0, object_type=ObjectType.SHRUB), 200.0, None),
            (RectangleItem(600.0, 600.0, 100.0, 80.0), 250.0, 170.0),
            (EllipseItem(900.0, 900.0, 120.0, 60.0), 300.0, 140.0),
        ]
        for item, width, height in cases:
            scene.addItem(item)
            apply_rotation(item, rotation)
            before = _scene_centre(item)
            if height is None:
                _old, new = build_circle_resize(item, width, keep_center=True)
            elif isinstance(item, EllipseItem):
                _old, new = build_ellipse_resize(
                    item, width, height, keep_center=True
                )
            else:
                _old, new = build_rect_resize(item, width, height, keep_center=True)
            apply_rect_like_geometry(item, new)
            after = _scene_centre(item)
            drift = math.hypot(after.x() - before.x(), after.y() - before.y())
            assert drift < 1e-6, f"{type(item).__name__} drifted {drift:.6f} cm"

    def test_keep_anchor_is_the_panel_default_for_rectangles(
        self, canvas: CanvasView
    ) -> None:
        """The panel's long-standing behaviour: an UNROTATED rectangle grows
        right/down from its existing local origin, so pos is untouched."""
        scene = canvas.scene()
        item = RectangleItem(600.0, 600.0, 100.0, 80.0)
        scene.addItem(item)
        pos_before = item.pos()
        _old, new = build_rect_resize(item, 250.0, 170.0)  # keep_center=False
        apply_rect_like_geometry(item, new)
        assert item.pos().x() == pytest.approx(pos_before.x())
        assert item.pos().y() == pytest.approx(pos_before.y())


class TestResizableShapePredicate:
    def test_rect_backed_items_are_resizable(self) -> None:
        assert is_resizable_rect_like(
            CircleItem(0.0, 0.0, 10.0, object_type=ObjectType.TREE)
        )
        assert is_resizable_rect_like(RectangleItem(0.0, 0.0, 10.0, 10.0))
        assert is_resizable_rect_like(EllipseItem(0.0, 0.0, 10.0, 10.0))

    def test_vertex_backed_items_are_not(self) -> None:
        """Polygons are vertex-backed; resize_object must refuse them by name
        rather than silently no-op. Vertex editing is US-D2.6."""
        polygon = PolygonItem(
            [QPointF(0, 0), QPointF(100, 0), QPointF(50, 80)],
            object_type=ObjectType.GARDEN_BED,
        )
        assert not is_resizable_rect_like(polygon)


class TestVertexEditCornerDrag:
    """The vertex-edit corner drag must satisfy THREE invariants at once.

    History, because it is the whole point of this class. On master the drag
    pinned the anchor corner correctly but never re-pinned
    ``transformOriginPoint``, so a rotated rectangle stored a centre up to 331 cm
    from the visible one — the #219 failure mode, i.e. it saved displaced. The
    first fix in this PR added the re-pin and **broke the anchor instead**:
    ``new_pos`` was hand-derived assuming the origin stayed at the *old* rect
    centre, so moving the origin slid the shape out from under the cursor by up
    to 671 cm. A swap, not a fix, and it shipped with two tests that both
    asserted only the half that now worked — one of them algebraically implied by
    the other, so 373 tests stayed green.

    The real fix routes ``pos`` through ``anchored_position`` (which bakes in
    ``O = new_rect.center()``), making the re-pin and the placement one coupled
    solution rather than two half-solutions in the same function. These tests
    assert all three invariants over **every corner × rotation**, so fixing one
    at the expense of another fails here.
    """

    @staticmethod
    def _corner_point(corner: object, rect: QRectF) -> QPointF:
        from open_garden_planner.ui.canvas.items.resize_handle import RectCorner

        return {
            RectCorner.TOP_LEFT: rect.topLeft,
            RectCorner.TOP_RIGHT: rect.topRight,
            RectCorner.BOTTOM_LEFT: rect.bottomLeft,
            RectCorner.BOTTOM_RIGHT: rect.bottomRight,
        }[corner]()

    @pytest.mark.parametrize("rotation", _ROTATIONS)
    @pytest.mark.parametrize("corner_name", _CORNER_NAMES)
    def test_corner_drag_holds_all_three_invariants(
        self, canvas: CanvasView, corner_name: str, rotation: float
    ) -> None:
        from open_garden_planner.ui.canvas.items.resize_handle import (
            RectCorner,
            _opposite_corner,
        )

        corner = RectCorner[corner_name]
        scene = canvas.scene()
        item = RectangleItem(500, 500, 400, 300, object_type=ObjectType.RAISED_BED)
        scene.addItem(item)
        apply_rotation(item, rotation)

        initial_rect, initial_pos = item.rect(), item.pos()
        anchor_before = item.mapToScene(_opposite_corner(corner, initial_rect))
        dragged_before = item.mapToScene(self._corner_point(corner, initial_rect))
        delta = QPointF(120.0, 90.0)

        item._move_corner_to(corner, delta, initial_rect, initial_pos)
        new_rect = item.rect()

        # 1. The diagonally opposite corner is held fixed in scene space —
        #    what the method's own docstring promises.
        anchor_after = item.mapToScene(_opposite_corner(corner, new_rect))
        assert anchor_after.x() == pytest.approx(anchor_before.x(), abs=1e-6)
        assert anchor_after.y() == pytest.approx(anchor_before.y(), abs=1e-6)

        # 2. The dragged corner tracks the cursor, or the shape slides away
        #    from the pointer mid-drag.
        dragged_after = item.mapToScene(self._corner_point(corner, new_rect))
        assert dragged_after.x() == pytest.approx(
            dragged_before.x() + delta.x(), abs=1e-6
        )
        assert dragged_after.y() == pytest.approx(
            dragged_before.y() + delta.y(), abs=1e-6
        )

        # 3. The serializer invariant: the stored centre (pos + rect.center())
        #    is where the object actually appears, so it does not move on
        #    reload. NOT implied by (1) and (2) — this is the #219 half.
        stored = item.pos() + new_rect.center()
        visual = item.mapToScene(new_rect.center())
        assert stored.x() == pytest.approx(visual.x(), abs=1e-6)
        assert stored.y() == pytest.approx(visual.y(), abs=1e-6)
        assert item.transformOriginPoint().x() == pytest.approx(
            new_rect.center().x()
        )


class TestRotatedRectanglePanelResize:
    """The one place the panel's behaviour genuinely CHANGED, pinned.

    For an unrotated rectangle the new anchor-preserving builder is
    byte-identical to what the panel did before (``pos`` untouched) — that is
    covered by ``test_keep_anchor_is_the_panel_default_for_rectangles``. For a
    **rotated** rectangle the old code kept ``pos`` literally while leaving the
    pivot stale, which was incoherent rather than correct; the builder now pins
    the rectangle's top-left corner in scene space instead. That is a deliberate
    behaviour change and the senior review was right that it shipped untested.
    """

    @pytest.mark.parametrize("rotation", _ROTATIONS)
    def test_anchor_corner_stays_put_under_rotation(
        self, canvas: CanvasView, qtbot: object, rotation: float  # noqa: ARG002
    ) -> None:
        scene = canvas.scene()
        item = RectangleItem(600.0, 600.0, 100.0, 80.0)
        scene.addItem(item)
        apply_rotation(item, rotation)
        anchor_before = item.mapToScene(item.rect().topLeft())

        _old, new = build_rect_resize(item, 250.0, 170.0)  # panel default
        apply_rect_like_geometry(item, new)

        anchor_after = item.mapToScene(item.rect().topLeft())
        assert anchor_after.x() == pytest.approx(anchor_before.x())
        assert anchor_after.y() == pytest.approx(anchor_before.y())
        # And the invariant that made the old behaviour incoherent now holds.
        assert item.transformOriginPoint().x() == pytest.approx(
            item.rect().center().x()
        )


class TestOneRotationImplementation:
    """Drift guard: `apply_rotation` must have exactly one definition.

    The senior review caught that the first cut left all five per-item
    `apply_rotation` closures in place, so `geometry_apply.apply_rotation` was a
    SIXTH copy used only by the agent — the opposite of a consolidation. This
    fails if anyone reintroduces a private one.
    """

    def test_only_geometry_apply_defines_apply_rotation(self) -> None:
        import re
        from pathlib import Path

        src = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"
        # Paths only, never line numbers: a guard that breaks on an unrelated
        # edit above the definition gets deleted rather than fixed.
        definitions = sorted(
            path.relative_to(src).as_posix()
            for path in src.rglob("*.py")
            for line in path.read_text(encoding="utf-8").splitlines()
            if re.match(r"\s*def apply_rotation\b", line)
        )
        assert definitions == ["ui/canvas/geometry_apply.py"], (
            "apply_rotation must be defined exactly once, in geometry_apply. "
            f"Found: {definitions}"
        )
