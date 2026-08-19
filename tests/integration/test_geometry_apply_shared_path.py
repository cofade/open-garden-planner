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

import ast
import math
import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsScene

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


def _rotate_command_bindings(tree: ast.Module) -> dict[str, str]:
    """Map local name → imported name for the file's ``from … import`` lines.

    A bare ``RIC(...)`` callee is invisible to a name check unless the alias is
    resolved back to what it imported. ``from …commands import
    RotateItemCommand as RIC`` was the hole a reviewer walked through the
    name-only version with.
    """
    bindings: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bindings[alias.asname or alias.name] = alias.name
    return bindings


def _is_rotate_command(
    node: ast.Call, bindings: dict[str, str] | None = None
) -> bool:
    """Whether ``node`` constructs a ``RotateItemCommand``.

    Accepts a dotted callee (``commands.RotateItemCommand(...)``), a bare name,
    and — through ``bindings`` — a bare name an ``import … as`` alias binds to
    the class (``from …commands import RotateItemCommand as RIC``). The class
    definition itself is an ``ast.ClassDef``, never an ``ast.Call``, so it
    needs no special case.
    """
    func = node.func
    if isinstance(func, ast.Name):
        return (bindings or {}).get(func.id, func.id) == "RotateItemCommand"
    return isinstance(func, ast.Attribute) and func.attr == "RotateItemCommand"


def _rotate_applier(node: ast.Call) -> ast.expr | None:
    """The ``apply_func`` argument, positional **or** keyword.

    ``apply_func`` is a plain positional-or-keyword parameter
    (``core/commands.py``), so ``apply_func=...`` is one word from the
    positional form and was the likeliest way a future caller would write it —
    the previous version of this guard read ``node.args[3]`` only and missed it.
    """
    for keyword in node.keywords:
        if keyword.arg == "apply_func":
            return keyword.value
    return node.args[3] if len(node.args) >= 4 else None


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
    @pytest.mark.parametrize(
        "delta",
        [
            QPointF(120.0, 90.0),   # grow
            QPointF(-120.0, -90.0),  # shrink
            QPointF(-9999.0, -9999.0),  # past the MINIMUM_SIZE_CM floor
        ],
        ids=["grow", "shrink", "clamped"],
    )
    def test_corner_drag_holds_all_three_invariants(
        self,
        canvas: CanvasView,
        corner_name: str,
        rotation: float,
        delta: QPointF,
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

        item._move_corner_to(corner, delta, initial_rect, initial_pos)
        new_rect = item.rect()
        # A drag past MINIMUM_SIZE_CM reverts that axis to its initial extent,
        # so cursor tracking necessarily breaks — that is what a clamp is. The
        # anchor and the #219 invariant must still hold exactly, and nothing
        # pinned that branch before.
        # Clamped == an axis kept its initial extent because the drag would have
        # gone below MINIMUM_SIZE_CM. Derived from the result, not from the
        # delta, so the test does not encode the clamp policy it is observing.
        clamped = (
            new_rect.width() == initial_rect.width()
            or new_rect.height() == initial_rect.height()
        )

        # 1. The diagonally opposite corner is held fixed in scene space —
        #    what the method's own docstring promises.
        anchor_after = item.mapToScene(_opposite_corner(corner, new_rect))
        assert anchor_after.x() == pytest.approx(anchor_before.x(), abs=1e-6)
        assert anchor_after.y() == pytest.approx(anchor_before.y(), abs=1e-6)

        # 2. The dragged corner tracks the cursor, or the shape slides away
        #    from the pointer mid-drag. Not asserted for a clamped drag.
        if not clamped:
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


class TestEqualConstraintPartnerResize:
    """``ResizeItemCommand`` has a SECOND callable injection point.

    Besides ``apply_func`` it takes ``partner_resizes``, whose apply functions
    it also runs on execute and undo (``commands.py``). The first pass of the
    geometry-apply extraction enumerated only the first, so the EQUAL-constraint
    partner appliers in ``core/tools/constraint_tool.py`` kept hand-rolled
    geometry — and with it a rotation bug: they solved for a new ``pos`` as if
    the item were unrotated, so a rotated partner's stored centre ended up
    **25.9 cm** adrift at 30 degrees and **70.7 cm** at 90.

    Found by the senior review applying section 11.4's own stated lesson: grep
    the constructor and enumerate, do not reason from the files you happened to
    open.
    """

    @pytest.mark.parametrize("rotation", _ROTATIONS)
    def test_rectangle_partner_resize_is_rotation_correct(
        self, canvas: CanvasView, rotation: float
    ) -> None:
        from open_garden_planner.core.measure_snapper import AnchorType
        from open_garden_planner.core.tools.constraint_tool import (
            _build_equal_resize_fn,
        )

        scene = canvas.scene()
        item = RectangleItem(400, 400, 200, 100, object_type=ObjectType.RAISED_BED)
        scene.addItem(item)
        apply_rotation(item, rotation)
        centre_before = item.mapToScene(item.rect().center())

        _old_size, apply_fn = _build_equal_resize_fn(item, AnchorType.EDGE_TOP)
        apply_fn(item, 300.0)

        assert item.rect().width() == pytest.approx(300.0)
        # Centre-preserving is what these appliers were always trying to do —
        # they just did it in a way that only worked unrotated.
        centre_after = item.mapToScene(item.rect().center())
        assert centre_after.x() == pytest.approx(centre_before.x(), abs=1e-6)
        assert centre_after.y() == pytest.approx(centre_before.y(), abs=1e-6)
        # And the #219 invariant, which the hand-rolled version never restored.
        stored = item.pos() + item.rect().center()
        visual = item.mapToScene(item.rect().center())
        assert stored.x() == pytest.approx(visual.x(), abs=1e-6)
        assert stored.y() == pytest.approx(visual.y(), abs=1e-6)

    @pytest.mark.parametrize("rotation", _ROTATIONS)
    def test_circle_partner_resize_was_already_correct(
        self, canvas: CanvasView, rotation: float
    ) -> None:
        """The counterpart, pinned so nobody "fixes" it into a regression.

        ``circle_apply`` rebuilds the rect around the *same* local centre, so
        ``_center``, ``rect().center()`` and ``transformOriginPoint`` stay
        coincident and it is already rotation-correct. A review round claimed it
        left ``_center`` stale; measurement said otherwise, and this records the
        measurement rather than the claim.
        """
        from open_garden_planner.core.measure_snapper import AnchorType
        from open_garden_planner.core.tools.constraint_tool import (
            _build_equal_resize_fn,
        )

        scene = canvas.scene()
        item = CircleItem(400, 400, 50, object_type=ObjectType.TREE)
        scene.addItem(item)
        apply_rotation(item, rotation)
        centre_before = item.mapToScene(item.rect().center())

        _old_size, apply_fn = _build_equal_resize_fn(item, AnchorType.EDGE_TOP)
        apply_fn(item, 120.0)

        assert item._radius == pytest.approx(120.0)
        assert item._center.x() == pytest.approx(item.rect().center().x())
        assert item._center.y() == pytest.approx(item.rect().center().y())
        assert item.transformOriginPoint().x() == pytest.approx(
            item.rect().center().x()
        )
        centre_after = item.mapToScene(item.rect().center())
        assert centre_after.x() == pytest.approx(centre_before.x(), abs=1e-6)
        assert centre_after.y() == pytest.approx(centre_before.y(), abs=1e-6)


class TestApplyRefreshHooks:
    """The apply function must refresh the derived UI a resize leaves stale."""

    def test_apply_refreshes_the_area_label(self, qtbot) -> None:
        """A resize that leaves ``pos`` unchanged fires no itemChange, so the
        area label showed a stale value after resizing through the canonical
        path (measured: still "2.00 m²" after a 400×300 resize). The apply
        function must refresh it explicitly."""
        scene = QGraphicsScene()
        rect = RectangleItem(0, 0, 200, 100)
        scene.addItem(rect)
        rect._area_label_visible = True
        rect._update_area_label()
        assert rect._area_label_item.text() == "2.00 m²"

        _old, new = build_rect_resize(rect, 400, 300)
        apply_rect_like_geometry(rect, new)

        assert rect._area_label_item.text() == "12.00 m²"


class TestNoPrivateRotationAppliers:
    """Drift guard: rotation must have exactly one implementation.

    Widened after review: matching only ``def apply_rotation`` would miss a
    private copy under another name, and miss a ``lambda`` handed straight to
    ``RotateItemCommand`` — which is the shorter, likelier way to reintroduce
    one.
    """

    @staticmethod
    def _source_files() -> list[Path]:
        src = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"
        return sorted(src.rglob("*.py"))

    def test_apply_rotation_is_defined_once(self) -> None:
        src = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"
        definitions = sorted(
            path.relative_to(src).as_posix()
            for path in self._source_files()
            for line in path.read_text(encoding="utf-8").splitlines()
            if re.match(r"\s*def apply_rotation\b", line)
        )
        assert definitions == ["ui/canvas/geometry_apply.py"], (
            f"apply_rotation must be defined exactly once. Found: {definitions}"
        )

    def test_no_private_rotation_applier_reaches_rotateitemcommand(self) -> None:
        """Every ``RotateItemCommand`` must be handed the SHARED applier.

        Walks the AST rather than matching text. The regex version had two holes
        a reviewer demonstrated — ``_legacy_apply_rotation`` and
        ``item._apply_rotation`` both *contain* the substring ``apply_rotation``,
        so both slipped through — plus a false positive: ``.*?`` under DOTALL
        stops at the first ``)``, so a call wrapping an argument in ``float(...)``
        was reported as an offender. Comparing the fourth argument to the NAME
        ``apply_rotation`` has neither problem.
        """
        src = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"
        offenders: list[str] = []
        for path in self._source_files():
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            bindings = _rotate_command_bindings(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not _is_rotate_command(
                    node, bindings
                ):
                    continue
                applier = _rotate_applier(node)
                if not (
                    isinstance(applier, ast.Name)
                    and bindings.get(applier.id, applier.id) == "apply_rotation"
                ):
                    offenders.append(
                        f"{path.relative_to(src).as_posix()}:{node.lineno} -> "
                        f"{ast.dump(applier)[:60]}"
                    )
        assert not offenders, (
            "every RotateItemCommand must be given geometry_apply.apply_rotation "
            f"by name; found: {offenders}"
        )

    @staticmethod
    def _offenders_in(source: str) -> list[str]:
        found = []
        tree = ast.parse(source)
        bindings = _rotate_command_bindings(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not _is_rotate_command(
                node, bindings
            ):
                continue
            arg = _rotate_applier(node)
            if arg is None:
                found.append("<no applier argument>")
            elif not (
                isinstance(arg, ast.Name)
                and bindings.get(arg.id, arg.id) == "apply_rotation"
            ):
                found.append(ast.dump(arg)[:40])
        return found

    def test_the_ast_guard_rejects_the_regex_blind_spots(self) -> None:
        """Teeth, using the exact shapes that defeated the regex version."""
        assert self._offenders_in(
            "RotateItemCommand(i, o, n, _legacy_apply_rotation)"
        ), "a renamed private copy must be caught"
        assert self._offenders_in(
            "RotateItemCommand(i, o, n, item._apply_rotation)"
        ), "a bound method must be caught"
        assert self._offenders_in(
            "RotateItemCommand(i, o, n, lambda it, a: it._apply_rotation(a))"
        ), "a lambda must be caught"
        # ...and the shape the regex falsely flagged must pass: its `.*?` under
        # DOTALL stopped at the first `)`, so `float(old)` truncated the match.
        assert not self._offenders_in(
            "RotateItemCommand(\n"
            "    item,\n"
            "    float(old),\n"
            "    new,\n"
            "    apply_rotation,\n"
            ")"
        ), "a wrapped argument must NOT be a false positive"

    def test_the_ast_guard_has_no_holes_of_its_own(self) -> None:
        """The shapes a reviewer demonstrated the FIRST ast version missed,
        plus the import-alias hole in the second.

        `apply_func` is a plain positional-or-keyword parameter, so the keyword
        form is one word away from the positional one and is the likeliest way a
        future caller writes it — yet `node.args[3]` never saw it.
        """
        assert self._offenders_in(
            "RotateItemCommand(i, o, n, apply_func=item._apply_rotation)"
        ), "the KEYWORD form must be caught"
        assert self._offenders_in(
            "commands.RotateItemCommand(i, o, n, item._apply_rotation)"
        ), "a dotted callee must be caught"
        assert self._offenders_in(
            "RotateItemCommand(i, o, n)"
        ), "an applier supplied some other way must not pass as 'too few args'"
        assert not self._offenders_in(
            "RotateItemCommand(i, o, n, apply_func=apply_rotation)"
        ), "the keyword form with the SHARED applier must pass"
        assert self._offenders_in(
            "from core.commands import RotateItemCommand as RIC\n"
            "RIC(i, o, n, item._apply_rotation)"
        ), "an aliased import must be caught"
        assert not self._offenders_in(
            "from core.commands import RotateItemCommand as RIC\n"
            "RIC(i, o, n, apply_rotation)"
        ), "an aliased import with the SHARED applier must pass"
        assert not self._offenders_in(
            "from geometry_apply import apply_rotation as AR\n"
            "RotateItemCommand(i, o, n, AR)"
        ), "an aliased SHARED applier must pass"
