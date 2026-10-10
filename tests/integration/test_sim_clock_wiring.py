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
import weakref
from datetime import UTC, date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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

    def test_an_unparented_controller_dies_without_a_gc_cycle(self, scene) -> None:
        """The controller owns its clock and listens to it; a strong listener
        would close a cycle and leave the QObject to the cyclic GC, which may run
        on a worker thread (the #230 neighbourhood). Senior review P2."""
        clock = SimClock(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller = SunShadowController(scene, lambda: BERLIN, clock=clock)
        alive = weakref.ref(controller)
        del controller
        assert alive() is None
        assert clock.instant_changed.receiver_count() == 0


# ── the app owns one clock ───────────────────────────────────────────────────


def _app(qtbot):
    from open_garden_planner.app.application import GardenPlannerApp

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win._view3d_window = MagicMock()  # the Qt 3D window needs an RHI context
    return win


def _local(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    """A naive wall reading — what the toolbar hands the clock (ADR-052)."""
    return datetime(y, mo, d, h, mi)


def _date_spy(win) -> list[date]:
    seen: list[date] = []
    win._sim_clock.date_changed.connect(seen.append)
    return seen


class TestAppOwnsOneClock:
    def test_every_consumer_shares_the_app_clock(self, qtbot) -> None:
        win = _app(qtbot)
        assert isinstance(win._sim_clock, SimClock)
        assert win._sun_controller.clock is win._sim_clock
        assert win._sun_toolbar.current_wall_datetime() == win._sim_clock.wall

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


class TestTypingUnderAnimate:
    def test_a_partly_typed_date_survives_an_animation_tick(self, qtbot) -> None:
        """The clock mirror runs on every Animate tick (every 200 ms). It used to
        re-set the unchanged date, which made QDateEdit redraw its text and wipe
        a date the user was typing; keyboard date entry was impossible while
        animating (L1.0 senior review round 2, P1)."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        from PyQt6.QtWidgets import QLineEdit

        win = _app(qtbot)
        win._sim_clock.set_datetime(_local(2026, 6, 21, 12))
        win._sun_sim_action.trigger()  # show the toolbar
        win.show()
        qtbot.waitExposed(win)
        edit = win._sun_toolbar._date_edit
        line = edit.findChild(QLineEdit)
        edit.setFocus()
        QTest.keyClick(edit, Qt.Key.Key_End)
        QTest.keyClick(edit, Qt.Key.Key_Backspace)
        QTest.keyClick(edit, Qt.Key.Key_Backspace)
        typed = line.text()
        assert typed != "2026-06-21"  # the user is mid-edit

        win._sun_toolbar._on_animate_tick()
        assert line.text() == typed, "the mirror wiped the partly typed date"

        QTest.keyClick(edit, Qt.Key.Key_2)
        QTest.keyClick(edit, Qt.Key.Key_8)
        assert win._sim_clock.plan_date == date(2026, 6, 28)
        assert win._sim_clock.time_of_day == time(12, 10)  # the tick still landed


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


class TestToolbarPathPreMidnightGap:
    """The L1.0 gate on the PRODUCT path, in a zone whose spring-forward gap
    starts before midnight (America/Nuuk: Saturday 23:00 → Sunday 00:00). The
    first draft handed the clock the toolbar's ``naive.astimezone()`` instant,
    and an Animate tick from 22:50 moved the plan date to Sunday (senior review
    P1). Skips without IANA tz data (a bare Windows venv); CI Linux runs it."""

    def test_every_slider_value_and_animation_tick_keeps_the_date(
        self, qtbot, monkeypatch
    ) -> None:
        try:
            nuuk = ZoneInfo("America/Nuuk")
        except ZoneInfoNotFoundError:
            pytest.skip("no IANA tz data for America/Nuuk on this platform")
        monkeypatch.setattr(
            sim_clock_module, "SimClock", functools.partial(SimClock, tz=nuuk)
        )
        win = _app(qtbot)
        toolbar = win._sun_toolbar
        saturday = date(2026, 3, 28)
        toolbar._date_edit.setDate(QDate(2026, 3, 28))
        assert win._sim_clock.plan_date == saturday
        dates = _date_spy(win)

        for minutes in range(24 * 60):  # the user drags through the whole day
            toolbar._slider.setValue(minutes)
            assert win._sim_clock.plan_date == saturday, minutes
            assert toolbar._slider.value() == minutes  # the mirror never jumps
        toolbar._slider.setValue(22 * 60 + 50)
        for _ in range(20):  # Animate: 22:50 → through the gap → past midnight
            toolbar._on_animate_tick()
            assert win._sim_clock.plan_date == saturday

        assert dates == []
        assert toolbar._date_edit.date() == QDate(2026, 3, 28)


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

    def test_result_queued_after_the_worker_returned_never_paints(
        self, qtbot
    ) -> None:
        """``QThread.isRunning()`` is already False once ``run()`` returned,
        while its success/finished still wait in the GUI queue. A stale rule
        keyed on ``is_running`` let that queued map paint under the new date
        (senior review P1). Driven through the button, so its busy, checked and
        enabled states are asserted too."""
        win = _app(qtbot)
        win._project_manager._location = dict(BERLIN)
        win.canvas_scene.addItem(
            RectangleItem(100, 100, 40, 40, object_type=ObjectType.TOOL_SHED)
        )
        win._sim_clock.set_datetime(datetime(2026, 6, 21, 12, 0))
        toolbar = win._sun_toolbar
        heatmap = win._sun_heatmap
        button = toolbar._heatmap_button
        idle_text = button.text()

        button.setChecked(True)  # the user asks for the hours-of-sun map
        assert heatmap.result_pending
        assert not button.isEnabled()  # busy while computing
        worker = heatmap._worker
        assert worker is not None
        assert worker.wait(60000)  # run() returned; its signals are queued
        assert not heatmap.is_running and heatmap.result_pending

        with qtbot.waitSignal(heatmap.finished, timeout=60000) as blocker:
            win._sim_clock.set_date(date(2026, 6, 22))  # before the queue drains
        assert blocker.args == [False]
        qtbot.wait(100)
        assert not heatmap.heatmap_visible()
        assert not heatmap.result_pending
        assert not button.isChecked()
        assert button.isEnabled()
        assert button.text() == idle_text


class TestHeatmapLaunchGuard:
    def test_a_second_launch_waits_for_the_pending_result(self, qtbot) -> None:
        """``is_running`` is False once ``run()`` returned, while the result is
        still queued; a launch accepted there let the first worker's
        ``finished`` deleteLater the running second one (a Qt fatal abort,
        measured in the L1.0 review). ``run_for_day`` now waits."""
        win = _app(qtbot)
        win._project_manager._location = dict(BERLIN)
        win.canvas_scene.addItem(
            RectangleItem(100, 100, 40, 40, object_type=ObjectType.TOOL_SHED)
        )
        heatmap = win._sun_heatmap
        assert heatmap.run_for_day(date(2026, 6, 21))
        worker = heatmap._worker
        assert worker is not None and worker.wait(60000)
        assert not heatmap.is_running and heatmap.result_pending
        assert heatmap.run_for_day(date(2026, 6, 22)) is False
        with qtbot.waitSignal(heatmap.finished, timeout=60000):
            pass
        assert not heatmap.result_pending
        with qtbot.waitSignal(heatmap.finished, timeout=60000) as blocker:
            assert heatmap.run_for_day(date(2026, 6, 22))
        assert blocker.args == [True]
        heatmap.shutdown()


def test_toolbar_refuses_an_instant(qtbot) -> None:
    """The toolbar shows wall readings in the clock's zone; an aware datetime
    would be shown in a guessed zone, so it is refused (round-3 review)."""
    toolbar = SunSimToolbar()
    qtbot.addWidget(toolbar)
    before = toolbar.current_wall_datetime()
    emitted: list[datetime] = []
    toolbar.datetime_changed.connect(emitted.append)
    with pytest.raises(ValueError, match="naive"):
        toolbar.set_datetime_local(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
    assert toolbar.current_wall_datetime() == before  # refused before any write
    assert emitted == []


def test_toolbar_alone_is_limited_to_the_clock_range(qtbot) -> None:
    toolbar = SunSimToolbar()
    qtbot.addWidget(toolbar)
    assert toolbar._date_edit.minimumDate() == QDate(MIN_PLAN_DATE)
    assert toolbar._date_edit.maximumDate() == QDate(MAX_PLAN_DATE)
