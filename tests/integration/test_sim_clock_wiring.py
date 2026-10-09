"""Phase 17 L1.0 (#385) — one sim clock behind the toolbar, overlay, heatmap and 3D.

The §8.10 workflow for L1.0: the user scrubs the sun toolbar, and every
consumer reads the same plan date and instant from ``GardenPlannerApp``'s one
``SimClock``. The L1.0 gate "a time change never fires ``date_changed``" is
checked here at the app boundary: a time-of-day drag, including the
animation's wrap past midnight, keeps the heatmap and does not regrow the 3D
geometry. The fix the clock brings is also checked: the overlay and 3D used to
grow plants for the instant's UTC date, while the heatmap used the toolbar's
local date. After local midnight east of UTC those were different days; now
there is one plan date.

The 3D window is a ``MagicMock`` stand-in, as in ``test_plant_growth_wiring``:
the Qt 3D view needs an RHI context, which only the Windows-only tests in
``test_3d_view`` provide.
"""

from __future__ import annotations

import functools
from datetime import UTC, date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QDate, QPointF

from open_garden_planner.core import sim_clock as sim_clock_module
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE, SimClock
from open_garden_planner.ui.canvas import sun_shadow_controller as overlay_module
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowController
from open_garden_planner.ui.widgets.sun_sim_toolbar import SunSimToolbar

BERLIN = {"latitude": 52.52, "longitude": 13.405}
TOKYO_FIXED = timezone(timedelta(hours=9))


class _AtDateSpy:
    """Wraps ``collect_shadow_casters`` and records the growth date it is given."""

    def __init__(self, real) -> None:
        self._real = real
        self.dates: list[date | None] = []

    def __call__(self, scene, at_date=None):
        self.dates.append(at_date)
        return self._real(scene, at_date=at_date)


@pytest.fixture
def scene(qtbot) -> CanvasScene:  # noqa: ARG001 — qtbot for Qt init
    canvas = CanvasScene(500.0, 500.0)
    canvas.addItem(RectangleItem(100, 100, 40, 40, object_type=ObjectType.TOOL_SHED))
    return canvas


# ── the overlay reads the clock ──────────────────────────────────────────────


class TestShadowOverlayReadsTheClock:
    def test_growth_date_is_the_local_plan_date_not_the_utc_date(
        self, scene, monkeypatch
    ) -> None:
        spy = _AtDateSpy(overlay_module.collect_shadow_casters)
        monkeypatch.setattr(overlay_module, "collect_shadow_casters", spy)
        # 01:00 on 22 June at +09:00 is 16:00 UTC on 21 June. Berlin's sun is up
        # (≈ 18:00 CEST), so the overlay builds casters.
        clock = SimClock(datetime(2026, 6, 22, 1, 0), tz=TOKYO_FIXED)
        controller = SunShadowController(scene, lambda: BERLIN, clock=clock)
        controller.set_enabled(True)
        assert controller.sim_datetime_utc.date() == date(2026, 6, 21)
        assert spy.dates == [date(2026, 6, 22)]

    def test_a_clock_write_recomputes_an_enabled_overlay(self, scene) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller = SunShadowController(scene, lambda: BERLIN, clock=clock)
        controller.set_enabled(True)
        before = controller.recompute_count
        clock.set_time_of_day(time(16, 0))
        assert controller.recompute_count == before + 1
        assert controller.sim_datetime_utc == clock.utc

    def test_a_disabled_overlay_ignores_the_clock(self, scene) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller = SunShadowController(scene, lambda: BERLIN, clock=clock)
        clock.set_time_of_day(time(16, 0))
        clock.set_date(date(2031, 6, 21))
        assert controller.recompute_count == 0

    def test_standalone_controller_owns_a_private_clock(self, scene) -> None:
        first = SunShadowController(scene, lambda: BERLIN)
        second = SunShadowController(scene, lambda: BERLIN)
        assert first.clock is not second.clock
        first.set_sim_datetime(datetime(2026, 12, 21, 12, 0, tzinfo=UTC))
        assert first.clock.utc == datetime(2026, 12, 21, 12, 0, tzinfo=UTC)
        assert second.clock.utc != first.clock.utc

    def test_set_sim_datetime_writes_the_shared_clock(self, scene) -> None:
        clock = SimClock(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller = SunShadowController(scene, lambda: BERLIN, clock=clock)
        controller.set_sim_datetime(datetime(2026, 12, 21, 10, 0, tzinfo=UTC))
        assert clock.utc == datetime(2026, 12, 21, 10, 0, tzinfo=UTC)

    def test_set_sim_datetime_still_refuses_naive(self, scene) -> None:
        controller = SunShadowController(scene, lambda: BERLIN)
        with pytest.raises(ValueError, match="timezone-aware"):
            controller.set_sim_datetime(datetime(2026, 6, 21, 12, 0))


# ── the app owns one clock ───────────────────────────────────────────────────


def _app(qtbot):
    from open_garden_planner.app.application import GardenPlannerApp

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._view3d_window = MagicMock()  # the Qt 3D window needs an RHI context
    return win


def _local(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    """A wall time in the system zone — the zone the toolbar and app clock use."""
    return datetime(y, mo, d, h, mi).astimezone()


def _date_spy(win) -> list[date]:
    seen: list[date] = []
    win._sim_clock.date_changed.connect(seen.append)
    return seen


class TestAppOwnsOneClock:
    def test_every_consumer_shares_the_app_clock(self, qtbot) -> None:
        win = _app(qtbot)
        assert isinstance(win._sim_clock, SimClock)
        assert win._sun_controller.clock is win._sim_clock
        toolbar_wall = win._sun_toolbar.current_datetime_local().replace(tzinfo=None)
        assert toolbar_wall == win._sim_clock.wall

    def test_time_drag_moves_the_light_only(self, qtbot) -> None:
        win = _app(qtbot)
        win._sim_clock.set_datetime(_local(2026, 6, 21, 10))
        win._view3d_window.reset_mock()
        heatmap = win._sun_heatmap
        heatmap._ensure_overlay().setVisible(True)
        heatmap._computed_day = date(2026, 6, 21)
        win._sun_toolbar.set_heatmap_active(True)
        dates = _date_spy(win)

        win._sun_toolbar._slider.setValue(16 * 60 + 30)  # the user drags the slider

        assert win._sim_clock.time_of_day == time(16, 30)
        assert win._sim_clock.plan_date == date(2026, 6, 21)
        assert dates == []
        win._view3d_window.rebuild.assert_not_called()
        win._view3d_window.set_sun.assert_called()
        assert heatmap.heatmap_visible(), "a time drag keeps the whole-day map"
        assert win._sun_toolbar._heatmap_button.isChecked()

    def test_date_edit_regrows_and_clears_the_stale_heatmap(self, qtbot) -> None:
        win = _app(qtbot)
        win._sim_clock.set_datetime(_local(2026, 6, 21, 12))
        win._view3d_window.reset_mock()
        heatmap = win._sun_heatmap
        heatmap._ensure_overlay().setVisible(True)
        heatmap._computed_day = date(2026, 6, 21)
        win._sun_toolbar.set_heatmap_active(True)
        dates = _date_spy(win)

        win._sun_toolbar._date_edit.setDate(QDate(2031, 6, 21))  # the user picks a date

        assert dates == [date(2031, 6, 21)]
        assert win._sim_clock.time_of_day == time(12, 0)
        win._view3d_window.rebuild.assert_called_once()
        win._view3d_window.set_sun.assert_called()
        assert not heatmap.heatmap_visible()
        assert not win._sun_toolbar._heatmap_button.isChecked()

    def test_animation_wrap_past_midnight_keeps_the_date(self, qtbot) -> None:
        win = _app(qtbot)
        win._sim_clock.set_datetime(_local(2026, 6, 21, 23, 50))
        win._view3d_window.reset_mock()
        dates = _date_spy(win)

        win._sun_toolbar._on_animate_tick()  # one 10-minute animation step

        assert win._sim_clock.time_of_day == time(0, 0)
        assert win._sim_clock.plan_date == date(2026, 6, 21)
        assert dates == []
        win._view3d_window.rebuild.assert_not_called()

    def test_an_external_clock_write_moves_the_toolbar(self, qtbot) -> None:
        """A later writer (the 3D view's own time control, L1.3+) only writes
        the clock; the toolbar follows without echoing a second write."""
        win = _app(qtbot)
        writes: list[object] = []
        win._sim_clock.instant_changed.connect(writes.append)
        win._sim_clock.set_datetime(datetime(2027, 3, 1, 9, 15))
        assert len(writes) == 1
        assert win._sun_toolbar._date_edit.date() == QDate(2027, 3, 1)
        assert win._sun_toolbar._slider.value() == 9 * 60 + 15

    def test_heatmap_request_uses_the_plan_date(self, qtbot, monkeypatch) -> None:
        win = _app(qtbot)
        win._sim_clock.set_datetime(_local(2026, 12, 21, 15))
        requested: list[date] = []
        monkeypatch.setattr(
            win._sun_heatmap, "run_for_day", lambda day: requested.append(day) or True
        )
        win._on_heatmap_requested()
        assert requested == [date(2026, 12, 21)]

    def test_enabling_the_sim_keeps_the_clock(self, qtbot) -> None:
        """The toggle used to re-seed the overlay from the toolbar widgets; the
        clock is the truth now and enabling must not move it."""
        win = _app(qtbot)
        win._sim_clock.set_datetime(_local(2026, 9, 1, 7, 45))
        before = win._sim_clock.instant
        win._sun_sim_action.trigger()
        assert win._sun_controller.enabled
        assert win._sim_clock.instant == before
        assert win._sun_controller.sim_datetime_utc == before.utc

    def test_toolbar_date_picker_is_limited_to_the_clock_range(self, qtbot) -> None:
        win = _app(qtbot)
        edit = win._sun_toolbar._date_edit
        assert edit.minimumDate() == QDate(MIN_PLAN_DATE)
        assert edit.maximumDate() == QDate(MAX_PLAN_DATE)


class TestOnePlanDateEastOfUtc:
    """After local midnight east of UTC, the overlay, the heatmap and the 3D
    view used to name two different days. Now they all name the plan date."""

    def test_overlay_heatmap_and_3d_agree(self, qtbot, monkeypatch) -> None:
        monkeypatch.setattr(
            sim_clock_module, "SimClock", functools.partial(SimClock, tz=TOKYO_FIXED)
        )
        spy = _AtDateSpy(overlay_module.collect_shadow_casters)
        monkeypatch.setattr(overlay_module, "collect_shadow_casters", spy)
        win = _app(qtbot)
        win._project_manager._location = dict(BERLIN)  # silent: no weather fetch
        win._sim_clock.set_datetime(datetime(2026, 6, 22, 1, 0))  # 16:00 UTC, 21 June
        assert win._sim_clock.utc.date() == date(2026, 6, 21)

        win._sun_controller.set_enabled(True)  # overlay
        requested: list[date] = []
        monkeypatch.setattr(
            win._sun_heatmap, "run_for_day", lambda day: requested.append(day) or True
        )
        win._on_heatmap_requested()  # heatmap
        records_dates: list[date | None] = []
        monkeypatch.setattr(
            "open_garden_planner.ui.view3d.snapshot.collect_scene3d_records",
            lambda _scene, at_date=None: records_dates.append(at_date) or [],
        )
        win._refresh_3d_view()  # 3D geometry

        assert spy.dates[-1] == date(2026, 6, 22)
        assert requested == [date(2026, 6, 22)]
        assert records_dates == [date(2026, 6, 22)]
        assert win._sun_toolbar._date_edit.date() == QDate(2026, 6, 22)


class TestHeatmapMidComputeDateChange:
    def test_late_result_never_paints_under_a_new_date(self, qtbot) -> None:
        """Before L1.0 the app cleared the heatmap only when it was VISIBLE, so a
        date change while the worker was still computing let the old day's map
        paint under the new date."""
        win = _app(qtbot)
        win._project_manager._location = dict(BERLIN)
        wall = PolylineItem(
            [QPointF(50.0, 200.0), QPointF(450.0, 200.0)], object_type=ObjectType.WALL
        )
        win.canvas_scene.addItem(wall)
        win._sim_clock.set_datetime(_local(2026, 6, 21, 12))
        heatmap = win._sun_heatmap
        with qtbot.waitSignal(heatmap.finished, timeout=60000) as blocker:
            assert heatmap.run_for_day(date(2026, 6, 21), cell_cm=2.0)
            assert heatmap.is_running
            win._sun_toolbar._date_edit.setDate(QDate(2026, 6, 22))
        assert blocker.args == [False]
        qtbot.wait(100)  # a stray queued success slot would land here
        assert not heatmap.heatmap_visible()
        heatmap.shutdown()


def test_toolbar_alone_is_limited_to_the_clock_range(qtbot) -> None:
    toolbar = SunSimToolbar()
    qtbot.addWidget(toolbar)
    assert toolbar._date_edit.minimumDate() == QDate(MIN_PLAN_DATE)
    assert toolbar._date_edit.maximumDate() == QDate(MAX_PLAN_DATE)
