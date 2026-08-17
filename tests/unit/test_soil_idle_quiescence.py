"""Unit tests for soil-handler idle quiescence (issue #305).

``CanvasView._update_soil_mismatches`` / ``_update_soil_badges`` are driven
by a 500 ms debounce timer that restarts on every ``scene.changed``. Before
the fix, both methods touched every bed item unconditionally on each tick
(``setToolTip()`` / ``item.update()`` / ``SoilBadgeItem.setPos()`` via
``update_position()``) — each of which itself makes the scene emit
``changed``, restarting the same debounce timer that just fired. That is a
self-sustaining loop: measured in the real ``GardenPlannerApp`` with a
single never-selected ``GARDEN_BED`` on the plan, 16 ``scene.changed``
emissions + 8 minimap renders per 4 s, forever (0 for a non-bed rectangle,
which the mismatch/badge code ignores entirely).

The fix makes both handlers idempotent: only call ``setToolTip`` when the
tooltip text actually changed, only call ``item.update()`` when the
mismatch level actually changed, and only call ``setPos`` (inside
``SoilBadgeItem.update_position``) when the computed position actually
changed.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import open_garden_planner.ui.canvas.canvas_view as canvas_view_module
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.soil_test import SoilTestRecord
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.soil_badge_item import SoilBadgeItem


class _FixedDate(date):
    """A ``datetime.date`` stand-in whose ``today()`` is pinned to a soil
    sampling window (April) so ``SoilService.is_test_overdue`` can flag a
    bed as overdue deterministically, regardless of the real calendar date
    the test suite happens to run on."""

    @classmethod
    def today(cls) -> date:  # type: ignore[override]
        return date(2026, 4, 1)


class TestSoilMismatchHandlerIdleQuiescence:
    """Pins the ``_update_soil_mismatches`` half of issue #305."""

    def test_bed_never_selected_settles_to_zero_scene_changed(
        self, qtbot: Any
    ) -> None:
        scene = CanvasScene(width_cm=2000, height_cm=2000)
        view = CanvasView(scene)
        qtbot.addWidget(view)  # type: ignore[attr-defined]

        pm = ProjectManager()
        svc = SoilService(pm)
        view.set_soil_service(svc)

        bed = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)

        # Let whatever the addItem() triggered (debounce tick(s)) settle.
        qtbot.wait(800)  # type: ignore[attr-defined]

        changes = {"n": 0}
        scene.changed.connect(
            lambda _rects: changes.__setitem__("n", changes["n"] + 1)
        )

        qtbot.wait(1500)  # type: ignore[attr-defined]

        assert changes["n"] == 0, (
            f"scene.changed fired {changes['n']} times with a never-selected "
            "bed present and nothing else happening — self-sustaining loop "
            "(issue #305)"
        )


class TestSoilBadgeHandlerIdleQuiescence:
    """Pins the ``_update_soil_badges`` half of issue #305.

    Requires an actual overdue badge to exist so ``update_position()`` runs
    on every debounce tick — the branch the bug report calls out
    specifically (``SoilBadgeItem.update_position`` calling ``setPos``
    unconditionally).
    """

    def test_bed_with_overdue_badge_settles_to_zero_scene_changed(
        self, qtbot: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(canvas_view_module, "date", _FixedDate)

        scene = CanvasScene(width_cm=2000, height_cm=2000)
        view = CanvasView(scene)
        qtbot.addWidget(view)  # type: ignore[attr-defined]

        pm = ProjectManager()
        svc = SoilService(pm)
        view.set_soil_service(svc)

        bed = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        bed_id = str(bed.item_id)

        # Far enough in the past (well over the 180-day threshold) that,
        # combined with the pinned April "today", the bed is overdue.
        svc.add_record(bed_id, SoilTestRecord(date="2020-01-01"))
        view.refresh_soil_badges()

        assert bed_id in view._soil_badges, (
            "test setup did not produce an overdue badge — proves nothing"
        )

        # Let the scene.changed from addItem()/refresh's addItem() (badge)
        # and any debounce tick(s) it schedules settle.
        qtbot.wait(800)  # type: ignore[attr-defined]

        changes = {"n": 0}
        scene.changed.connect(
            lambda _rects: changes.__setitem__("n", changes["n"] + 1)
        )

        qtbot.wait(1500)  # type: ignore[attr-defined]

        assert changes["n"] == 0, (
            f"scene.changed fired {changes['n']} times with an overdue soil "
            "badge present and nothing else happening — self-sustaining "
            "loop (issue #305)"
        )


class TestSoilBadgeItemUpdatePositionIsIdempotent:
    """Direct, timer-free pin for the ``SoilBadgeItem.update_position`` fix."""

    def test_second_call_does_not_move_the_badge(self, qtbot: Any) -> None:
        scene = CanvasScene(width_cm=2000, height_cm=2000)
        view = CanvasView(scene)
        qtbot.addWidget(view)  # type: ignore[attr-defined]

        bed = RectangleItem(0, 0, 200, 100, object_type=ObjectType.GARDEN_BED)
        scene.addItem(bed)
        badge = SoilBadgeItem(bed, str(bed.item_id))
        scene.addItem(badge)

        badge.update_position()
        first_pos = badge.pos()

        move_count = {"n": 0}
        original_set_pos = badge.setPos

        def counting_set_pos(*args: Any, **kwargs: Any) -> None:
            move_count["n"] += 1
            original_set_pos(*args, **kwargs)

        badge.setPos = counting_set_pos  # type: ignore[method-assign]

        badge.update_position()

        assert move_count["n"] == 0, "setPos was called though the bed did not move"
        assert badge.pos() == first_pos
