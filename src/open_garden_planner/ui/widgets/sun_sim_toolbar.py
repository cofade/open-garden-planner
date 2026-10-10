"""Date/time control toolbar for the sun & shade simulation (US-E3, #258).

A plain ``QToolBar``: date picker + time-of-day slider + animate button +
hint label. It edits a WALL-CLOCK reading — a calendar date plus a time of
day — in the clock's zone (the system zone in the app: the garden and the
computer share a timezone in practice).

Since Phase 17 L1.0 (ADR-052) the toolbar is a VIEW of the app's one
``core/sim_clock.SimClock``. ``datetime_changed`` carries the naive wall
reading, which the app stores unchanged, so the plan date IS the picker's
date by construction — handing over an instant instead would let a time-only
drag move the date inside a spring-forward gap that starts before midnight
(America/Nuuk). The app mirrors the clock back with ``set_datetime_local``
(signals blocked). Its own "now" seed only matters standalone. The sim time
is deliberately NOT persisted — not in ``UiStateStore``, not in the ``.ogp`` —
so a fresh run always reflects today. The date picker is limited to the
clock's supported range (the system zone's conversion fails near the 1970
epoch and during 3001 on Windows).
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QDate, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QDateEdit,
    QLabel,
    QSlider,
    QToolBar,
    QToolButton,
    QWidget,
)

from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE
from open_garden_planner.ui.icons import get_icon, get_pixmap

_ANIMATE_INTERVAL_MS = 200
_ANIMATE_STEP_MINUTES = 10


class SunSimToolbar(QToolBar):
    """Sun & shade simulation time control.

    Signals:
        datetime_changed: emitted with the NAIVE wall-clock ``datetime``
            (picker date + slider time) whenever the user changes date or time
            (or the animation ticks).
    """

    datetime_changed = pyqtSignal(object)
    #: Heatmap button checked — the app should compute & show the heatmap.
    heatmap_requested = pyqtSignal()
    #: Heatmap button unchecked — the app should hide the heatmap.
    heatmap_cleared = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self.setObjectName("SunSimToolbar")  # required for QMainWindow.saveState
        self.setWindowTitle(self.tr("Sun & Shade Simulation"))
        self.setMovable(False)

        self.addWidget(QLabel(self.tr("Date:")))
        self._date_edit = QDateEdit(self)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDateRange(
            QDate(MIN_PLAN_DATE.year, MIN_PLAN_DATE.month, MIN_PLAN_DATE.day),
            QDate(MAX_PLAN_DATE.year, MAX_PLAN_DATE.month, MAX_PLAN_DATE.day),
        )
        self._date_edit.setToolTip(self.tr("Simulation date"))
        self.addWidget(self._date_edit)

        self._time_icon = QLabel(self)
        self._time_icon.setFixedSize(16, 16)
        self._time_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addWidget(self._time_icon)
        self._time_label = QLabel("12:00", self)
        self._time_label.setMinimumWidth(48)
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.addWidget(self._time_label)

        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(0, 24 * 60 - 1)
        self._slider.setPageStep(60)
        self._slider.setValue(12 * 60)
        self._slider.setFixedWidth(220)
        self._slider.setToolTip(self.tr("Time of day"))
        self.addWidget(self._slider)

        self._animate_button = QToolButton(self)
        self._animate_button.setText(self.tr("Animate"))
        self._animate_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._animate_button.setCheckable(True)
        self._animate_button.toggled.connect(lambda _c: self._update_animate_icon())
        self._animate_button.setToolTip(
            self.tr("Animate the sun across the day")
        )
        self.addWidget(self._animate_button)

        self.addSeparator()

        # ── Hours-of-sun heatmap (US-E4) — recompute on demand only ───────
        self._heatmap_button = QToolButton(self)
        self._heatmap_button.setText(self.tr("Hours of Sun"))
        self._heatmap_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._heatmap_button.setCheckable(True)
        self._heatmap_button.setToolTip(
            self.tr(
                "Compute a full-day hours-of-sun heatmap for the shown date"
            )
        )
        self.addWidget(self._heatmap_button)

        # NOTE: the night / no-location HINT is deliberately NOT a widget here.
        # A variable-width label in this toolbar's flow reflowed Qt's overflow
        # popup and bumped the Animate button to another row when the night
        # text toggled on/off; the hint now lives on the status bar instead
        # (GardenPlannerApp._set_sun_hint). 2026-07 fix.
        self._animate_timer = QTimer(self)
        self._animate_timer.setInterval(_ANIMATE_INTERVAL_MS)
        self._animate_timer.timeout.connect(self._on_animate_tick)

        self._date_edit.dateChanged.connect(self._on_inputs_changed)
        self._slider.valueChanged.connect(self._on_inputs_changed)
        self._animate_button.toggled.connect(self._on_animate_toggled)
        self._heatmap_button.toggled.connect(self._on_heatmap_toggled)

        # Standalone seed only — in the app the sim clock's wall time replaces it.
        self.set_datetime_local(datetime.now().replace(second=0, microsecond=0))
        self.refresh_theme_icons()

    # ── public API ─────────────────────────────────────────────

    def _update_animate_icon(self) -> None:
        play = get_icon("player_pause" if self._animate_button.isChecked() else "player_play")
        if play is not None:
            self._animate_button.setIcon(play)

    def refresh_theme_icons(self) -> None:
        """Theme-switch hook (#310): play/pause on Animate, sun-hours glyph
        on the heatmap button, a clock next to the time label."""
        self._update_animate_icon()
        heat = get_icon("sun_sim")
        if heat is not None:
            self._heatmap_button.setIcon(heat)
        clock = get_pixmap("clock", 14)
        if clock is not None:
            self._time_icon.setPixmap(clock)

    def current_wall_datetime(self) -> datetime:
        """The selected date + time of day as a naive wall-clock reading."""
        date = self._date_edit.date()
        minutes = self._slider.value()
        return datetime(
            date.year(), date.month(), date.day(), minutes // 60, minutes % 60
        )

    def set_datetime_local(self, dt: datetime) -> None:
        """Show the naive wall reading ``dt`` without emitting ``datetime_changed``.

        The toolbar shows wall readings in the clock's zone, so an aware
        datetime (an instant, whose zone would be a guess) is refused. Only a
        field that differs is written: re-setting an unchanged date makes
        ``QDateEdit`` redraw its text and erases a date the user is part-way
        through typing — with Animate running the mirror fires every 200 ms
        (L1.0 senior review).
        """
        if dt.tzinfo is not None:
            raise ValueError("set_datetime_local takes a naive wall reading")
        target_date = QDate(dt.year, dt.month, dt.day)
        target_minutes = dt.hour * 60 + dt.minute
        self._date_edit.blockSignals(True)
        self._slider.blockSignals(True)
        try:
            if self._date_edit.date() != target_date:
                self._date_edit.setDate(target_date)
            if self._slider.value() != target_minutes:
                self._slider.setValue(target_minutes)
        finally:
            self._date_edit.blockSignals(False)
            self._slider.blockSignals(False)
        self._update_time_label()

    def stop_animation(self) -> None:
        self._animate_button.setChecked(False)

    def set_heatmap_busy(self, busy: bool) -> None:
        """Busy indication while the worker computes."""
        self._heatmap_button.setEnabled(not busy)
        self._heatmap_button.setText(
            self.tr("Computing…") if busy else self.tr("Hours of Sun")
        )

    def set_heatmap_active(self, active: bool) -> None:
        """Reflect heatmap visibility (button check state), no signals."""
        self._heatmap_button.blockSignals(True)
        try:
            self._heatmap_button.setChecked(active)
        finally:
            self._heatmap_button.blockSignals(False)

    # ── internals ──────────────────────────────────────────────

    def _update_time_label(self) -> None:
        minutes = self._slider.value()
        self._time_label.setText(f"{minutes // 60:02d}:{minutes % 60:02d}")

    def _on_inputs_changed(self) -> None:
        self._update_time_label()
        self.datetime_changed.emit(self.current_wall_datetime())

    def _on_animate_toggled(self, checked: bool) -> None:
        if checked:
            self._animate_timer.start()
        else:
            self._animate_timer.stop()

    def _on_heatmap_toggled(self, checked: bool) -> None:
        if checked:
            self.heatmap_requested.emit()
        else:
            self.heatmap_cleared.emit()

    def _on_animate_tick(self) -> None:
        # Advancing the slider fires valueChanged → one recompute per tick.
        next_value = self._slider.value() + _ANIMATE_STEP_MINUTES
        self._slider.setValue(next_value % (24 * 60))
