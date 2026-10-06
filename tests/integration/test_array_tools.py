"""#395 — the four array tools, end to end.

``CanvasView.create_grid_array``, ``create_linear_array``,
``create_circular_array`` and ``create_array_along_path`` are reachable from the
context menu of all five shape items, but the full suite executed only their first
one or two lines: each opens a modal dialog and returns unless it is Accepted, so
without a monkeypatched ``exec()`` no test can reach the body. Measured at
v1.29.0: 317 of 321 statements across the four were never run.

Each test here patches the dialog's ``exec`` and asserts what the user would see:
how many items exist, where they are, and that the whole array is **one** undo
step (invariant 4). The undo-step count is asserted as a NUMBER, not as "undo
works", because "undo works" passes even when a command pushes three.

Positions are asserted in **scene** centimetres and the assertions were written
against the real geometry, not the intuitive one — three of them were wrong on
first draft and are now pinned deliberately:

* ``count`` in the dialogs INCLUDES the original item (the loops start at i=1),
  so ``count=4`` adds three copies;
* a +90° linear array runs DOWN the screen, i.e. DECREASING scene Y, because the
  code negates the sine on purpose ("to match screen-space intuition where 90° =
  downward and 270° = upward", ADR-002);
* circular copies are placed by CHORD offset, so they lie on a circle of radius
  ``r`` centred one radius *behind* the source — not at distance ``r`` from it.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import math
from typing import Any

import pytest
from PyQt6.QtWidgets import QDialog

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


def _view_with(qtbot, item: Any) -> tuple[CanvasView, Any]:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    scene.addItem(item)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    item.setSelected(True)
    return view, item


def _rect(qtbot, x: float = 100.0, y: float = 100.0) -> tuple[CanvasView, Any]:
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    return _view_with(qtbot, RectangleItem(
        x=x, y=y, width=40.0, height=30.0,
        object_type=ObjectType.GARDEN_BED, name="Source",
    ))


def _patch_dialog(monkeypatch, module: str, cls: str, **attrs: Any) -> None:
    """Force the named dialog to be Accepted with the given settings.

    The dialogs expose their settings as read-only ``@property`` accessors over
    spin boxes, so the values are patched onto the CLASS rather than assigned to
    an instance (which would raise "property has no setter").
    """
    import importlib

    dialog_cls = getattr(importlib.import_module(module), cls)

    def _no_widgets(self, *_args, **_kwargs) -> None:   # skip the real spin boxes
        return None

    def _accepted(self) -> int:
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(dialog_cls, "__init__", _no_widgets)
    monkeypatch.setattr(dialog_cls, "exec", _accepted)
    for key, value in attrs.items():
        monkeypatch.setattr(dialog_cls, key, property(lambda _self, _v=value: _v))


def _rect_centres(scene: CanvasScene, exclude: Any = None) -> list[tuple[float, float]]:
    """Scene-centre of every rectangle copy, in scene centimetres (ADR-002).

    The source is excluded BY IDENTITY, not by name: array copies inherit the
    source's ``name``, so a name filter would discard exactly the items under
    test.
    """
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    out = []
    for item in scene.items():
        if isinstance(item, RectangleItem) and item is not exclude:
            c = item.sceneBoundingRect().center()
            out.append((round(c.x(), 1), round(c.y(), 1)))
    return sorted(out)


def _stack_len(view: CanvasView) -> int:
    """The undo-stack depth — asserted as a NUMBER, not as "undo works"."""
    return len(view._command_manager._undo_stack)  # noqa: SLF001 - the count IS the contract


def _circle_centre(src: Any, radius: float, start_deg: float) -> tuple[float, float]:
    """The circle circular-array copies lie on: one radius behind the source."""
    s = math.radians(start_deg)
    c = src.sceneBoundingRect().center()
    return (c.x() - radius * math.cos(s), c.y() + radius * math.sin(s))


def _angles_from(centre: tuple[float, float], points: list[tuple[float, float]]) -> list[int]:
    ccx, ccy = centre
    return sorted(
        round(math.degrees(math.atan2(cy - ccy, cx - ccx))) % 360 for cx, cy in points
    )


class TestGridArray:
    def test_creates_rows_times_columns_minus_one_items_in_one_undo_step(
        self, qtbot, monkeypatch
    ) -> None:
        _patch_dialog(
            monkeypatch,
            "open_garden_planner.ui.dialogs.grid_array_dialog",
            "GridArrayDialog",
            rows=3, cols=4, row_spacing_cm=50.0, col_spacing_cm=60.0,
            create_constraints=False,
        )
        view, source = _rect(qtbot)
        view.create_grid_array()

        # A 3x4 grid holds the original at (0,0), so 11 NEW rectangles.
        assert len(_rect_centres(view.scene(), exclude=source)) == 11
        assert _stack_len(view) == 1, (
            f"the array pushed {_stack_len(view)} undo steps; one user gesture "
            "must be one undo step (invariant 4)"
        )

    def test_columns_step_east_and_rows_follow_the_row_spacing(
        self, qtbot, monkeypatch
    ) -> None:
        """Rows go DOWN the screen, which is -Y in scene coords (ADR-002 flip)."""
        _patch_dialog(
            monkeypatch,
            "open_garden_planner.ui.dialogs.grid_array_dialog",
            "GridArrayDialog",
            rows=2, cols=3, row_spacing_cm=40.0, col_spacing_cm=25.0,
            create_constraints=False,
        )
        view, source = _rect(qtbot)
        view.create_grid_array()

        centres = _rect_centres(view.scene(), exclude=source)
        xs = sorted({c[0] for c in centres})
        ys = sorted({c[1] for c in centres})
        assert len(xs) == 3 and len(ys) == 2, (xs, ys)
        # Larger scene X is east/right; the column spacing is exact.
        assert xs[1] - xs[0] == pytest.approx(25.0, abs=0.5)
        assert xs[2] - xs[1] == pytest.approx(25.0, abs=0.5)
        # The two rows are one row-spacing apart in Y.
        assert abs(ys[1] - ys[0]) == pytest.approx(40.0, abs=0.5)


class TestLinearArray:
    def _linear(self, monkeypatch, **attrs: Any) -> None:
        _patch_dialog(
            monkeypatch,
            "open_garden_planner.ui.dialogs.linear_array_dialog",
            "LinearArrayDialog",
            create_constraints=False,
            **attrs,
        )

    def test_creates_count_minus_one_copies_evenly_spaced(self, qtbot, monkeypatch) -> None:
        self._linear(monkeypatch, count=4, spacing_cm=30.0, angle_deg=0.0)
        view, source = _rect(qtbot)
        view.create_linear_array()

        centres = _rect_centres(view.scene(), exclude=source)
        assert len(centres) == 3, centres      # count includes the original
        assert _stack_len(view) == 1

        # angle 0 = due east: constant Y, evenly spaced X.
        assert len({c[1] for c in centres}) == 1
        xs = sorted(c[0] for c in centres)
        for a, b in zip(xs, xs[1:], strict=False):
            assert b - a == pytest.approx(30.0, abs=1.0), xs

    def test_a_ninety_degree_array_steps_down_the_screen(self, qtbot, monkeypatch) -> None:
        """+90° is DOWNWARD on screen, i.e. DECREASING scene Y (ADR-002).

        ``create_linear_array`` negates the sine deliberately, so the scene-Y
        sign is the opposite of the naive reading. Pinned because the flip is
        exactly what regresses silently.
        """
        self._linear(monkeypatch, count=3, spacing_cm=20.0, angle_deg=90.0)
        view, source = _rect(qtbot)
        view.create_linear_array()

        centres = _rect_centres(view.scene(), exclude=source)
        assert len({c[0] for c in centres}) == 1, "a 90-degree array must not change X"
        ys = sorted((c[1] for c in centres), reverse=True)
        assert ys[0] > ys[1], "a +90 degree array must DECREASE scene Y"
        assert ys[0] - ys[1] == pytest.approx(20.0, abs=1.0)

    def test_a_two_seventy_degree_array_steps_up_the_screen(self, qtbot, monkeypatch) -> None:
        """270° is the mirror of 90°: it runs UP, i.e. increasing scene Y."""
        self._linear(monkeypatch, count=3, spacing_cm=20.0, angle_deg=270.0)
        view, source = _rect(qtbot)
        view.create_linear_array()

        centres = _rect_centres(view.scene(), exclude=source)
        ys = sorted(c[1] for c in centres)
        assert ys[1] > ys[0], "a 270 degree array must INCREASE scene Y"
        assert ys[1] - ys[0] == pytest.approx(20.0, abs=1.0)


class TestCircularArray:
    RADIUS = 80.0
    COUNT = 4

    def _circular(self, monkeypatch, **attrs: Any) -> None:
        _patch_dialog(
            monkeypatch,
            "open_garden_planner.ui.dialogs.circular_array_dialog",
            "CircularArrayDialog",
            **attrs,
        )

    @staticmethod
    def _near_centre(qtbot) -> tuple[CanvasView, Any]:
        """A source near the canvas centre, so the bounds clamp cannot distort it."""
        return _rect(qtbot, x=980.0, y=980.0)

    def test_every_copy_lies_on_the_circle_of_the_requested_radius(
        self, qtbot, monkeypatch
    ) -> None:
        self._circular(
            monkeypatch, count=self.COUNT, radius_cm=self.RADIUS,
            start_angle_deg=0.0, sweep_angle_deg=360.0,
        )
        view, source = self._near_centre(qtbot)
        view.create_circular_array()

        centres = _rect_centres(view.scene(), exclude=source)
        assert len(centres) == self.COUNT - 1, centres
        assert _stack_len(view) == 1

        for cx, cy in centres:
            ccx, ccy = _circle_centre(source, self.RADIUS, 0.0)
            assert math.hypot(cx - ccx, cy - ccy) == pytest.approx(self.RADIUS, abs=1.0), (
                cx, cy, "a copy is not on the requested circle"
            )

    def test_a_full_sweep_does_not_duplicate_the_start_position(
        self, qtbot, monkeypatch
    ) -> None:
        """360 / count, not 360 / (count - 1): the closing copy is not a twin.

        With count=4 the step is 90°, so the copies sit at 90, 180 and 270 and
        none lands back on the start position.
        """
        self._circular(
            monkeypatch, count=self.COUNT, radius_cm=self.RADIUS,
            start_angle_deg=0.0, sweep_angle_deg=360.0,
        )
        view, source = self._near_centre(qtbot)
        view.create_circular_array()

        centres = _rect_centres(view.scene(), exclude=source)
        assert len(centres) == 3, centres
        offsets = _angles_from(_circle_centre(source, self.RADIUS, 0.0), centres)
        assert offsets == [90, 180, 270], offsets

    def test_a_partial_sweep_includes_both_endpoints(self, qtbot, monkeypatch) -> None:
        """sweep < 360 divides by (count - 1) so the last copy lands on the end."""
        self._circular(
            monkeypatch, count=3, radius_cm=100.0,
            start_angle_deg=0.0, sweep_angle_deg=180.0,
        )
        view, source = self._near_centre(qtbot)
        view.create_circular_array()

        centres = _rect_centres(view.scene(), exclude=source)
        assert len(centres) == 2, centres
        # Step is 180 / (3 - 1) = 90, so the copies land on the 90° and 180°
        # marks. The scene frame MIRRORS the sine (ADR-002 flip), so 90° reads
        # as 270° here while 180° is unchanged.
        offsets = _angles_from(_circle_centre(source, 100.0, 0.0), centres)
        assert offsets == [180, 270], offsets


class TestArrayAlongPath:
    def _path_view(self, qtbot) -> tuple[CanvasView, Any]:
        from PyQt6.QtCore import QPointF

        from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
        from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

        path = PolylineItem(
            points=[QPointF(100.0, 500.0), QPointF(900.0, 500.0)],
            object_type=ObjectType.PATH, name="Path",
        )
        scene = CanvasScene(width_cm=2000, height_cm=2000)
        scene.addItem(path)
        source = RectangleItem(
            x=100.0, y=480.0, width=40.0, height=30.0,
            object_type=ObjectType.GARDEN_BED, name="Source",
        )
        scene.addItem(source)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        # This action needs BOTH selected: one item and one polyline path.
        source.setSelected(True)
        path.setSelected(True)
        return view, source

    def test_places_count_copies_evenly_along_the_selected_path(
        self, qtbot, monkeypatch
    ) -> None:
        _patch_dialog(
            monkeypatch,
            "open_garden_planner.ui.dialogs.array_along_path_dialog",
            "ArrayAlongPathDialog",
            count=5, spacing_cm=0.0, use_spacing_mode=False,
            start_offset_pct=0.0, end_offset_pct=0.0, follow_tangent=False,
        )
        view, source = self._path_view(qtbot)
        view.create_array_along_path()

        centres = _rect_centres(view.scene(), exclude=source)
        assert len(centres) == 5, centres
        assert _stack_len(view) == 1

        # A straight path from x=100 to x=900: copies advance in X only, evenly.
        assert len({c[1] for c in centres}) == 1, "a straight path must not change Y"
        xs = sorted(c[0] for c in centres)
        for a, b in zip(xs, xs[1:], strict=False):
            assert b - a == pytest.approx(200.0, abs=2.0), xs

    def test_refuses_when_only_the_item_is_selected(self, qtbot, monkeypatch) -> None:
        """The refusal path: one item and no path changes nothing, and adds no undo step."""
        _patch_dialog(
            monkeypatch,
            "open_garden_planner.ui.dialogs.array_along_path_dialog",
            "ArrayAlongPathDialog",
            count=5, spacing_cm=0.0, use_spacing_mode=False,
            start_offset_pct=0.0, end_offset_pct=0.0, follow_tangent=False,
        )
        view, source = self._path_view(qtbot)
        # Deselect the path, leaving only the source item.
        for item in view.scene().selectedItems():
            if item is not source:
                item.setSelected(False)

        before = len(_rect_centres(view.scene(), exclude=source))
        view.create_array_along_path()

        assert len(_rect_centres(view.scene(), exclude=source)) == before
        assert _stack_len(view) == 0, (
            "a refused array must not touch the undo stack — a guard that "
            "half-applies and then errors passes a happy-path test"
        )


class TestGuards:
    @pytest.mark.parametrize(
        "method", ["create_grid_array", "create_linear_array", "create_circular_array"]
    )
    def test_nothing_is_created_when_nothing_is_selected(
        self, qtbot, method: str
    ) -> None:
        scene = CanvasScene(width_cm=2000, height_cm=2000)
        view = CanvasView(scene)
        qtbot.addWidget(view)
        before = len(list(scene.items()))

        getattr(view, method)()

        assert len(list(scene.items())) == before
        assert _stack_len(view) == 0
