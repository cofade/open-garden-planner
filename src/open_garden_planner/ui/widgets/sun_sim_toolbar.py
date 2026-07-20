"""Date/time control toolbar for the sun & shade simulation (US-E3, #258).

A plain ``QToolBar``: date picker + time-of-day slider + animate button +
hint label. The widget works in the SYSTEM LOCAL timezone (the pragmatic
choice — the garden and the computer share a timezone in practice) and
emits timezone-aware local datetimes; the controller converts to UTC.
The sim time defaults to the current date/time each session (seeded in the
constructor) and is deliberately NOT persisted — not in ``UiStateStore``, not
in the ``.ogp`` — so a fresh run always reflects today.
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

_ANIMATE_INTERVAL_MS = 200
_ANIMATE_STEP_MINUTES = 10


class SunSimToolbar(QToolBar):
    """Sun & shade simulation time control.

    Signals:
        datetime_changed: emitted with a timezone-aware local ``datetime``
            whenever the user changes date or time (or the animation ticks).
    """

    datetime_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("", parent)
        self.setObjectName("SunSimToolbar")  # required for QMainWindow.saveState
        self.setWindowTitle(self.tr("Sun & Shade Simulation"))
        self.setMovable(False)

        self.addWidget(QLabel(self.tr("Date:")))
        self._date_edit = QDateEdit(self)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setToolTip(self.tr("Simulation date"))
        self.addWidget(self._date_edit)

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
        self._animate_button.setCheckable(True)
        self._animate_button.setToolTip(
            self.tr("Animate the sun across the day")
        )
        self.addWidget(self._animate_button)

        self._hint_label = QLabel("", self)
        self._hint_label.setStyleSheet("color: #806a00; font-style: italic;")
        self._hint_label.setContentsMargins(12, 0, 0, 0)
        self.addWidget(self._hint_label)

        self._animate_timer = QTimer(self)
        self._animate_timer.setInterval(_ANIMATE_INTERVAL_MS)
        self._animate_timer.timeout.connect(self._on_animate_tick)

        self._date_edit.dateChanged.connect(self._on_inputs_changed)
        self._slider.valueChanged.connect(self._on_inputs_changed)
        self._animate_button.toggled.connect(self._on_animate_toggled)

        now = datetime.now().astimezone()
        self.set_datetime_local(now)

    # ── public API ─────────────────────────────────────────────

    def current_datetime_local(self) -> datetime:
        """The selected instant as a timezone-aware local datetime."""
        date = self._date_edit.date()
        minutes = self._slider.value()
        naive = datetime(
            date.year(), date.month(), date.day(), minutes // 60, minutes % 60
        )
        return naive.astimezone()  # attach the system local timezone

    def set_datetime_local(self, dt: datetime) -> None:
        """Set the controls without emitting ``datetime_changed``."""
        local = dt.astimezone() if dt.tzinfo is not None else dt
        self._date_edit.blockSignals(True)
        self._slider.blockSignals(True)
        try:
            self._date_edit.setDate(QDate(local.year, local.month, local.day))
            self._slider.setValue(local.hour * 60 + local.minute)
        finally:
            self._date_edit.blockSignals(False)
            self._slider.blockSignals(False)
        self._update_time_label()

    def set_hint(self, text: str) -> None:
        """Show an empty-state hint (no location / night), or clear with ''."""
        self._hint_label.setText(text)

    def stop_animation(self) -> None:
        self._animate_button.setChecked(False)

    # ── internals ──────────────────────────────────────────────

    def _update_time_label(self) -> None:
        minutes = self._slider.value()
        self._time_label.setText(f"{minutes // 60:02d}:{minutes % 60:02d}")

    def _on_inputs_changed(self) -> None:
        self._update_time_label()
        self.datetime_changed.emit(self.current_datetime_local())

    def _on_animate_toggled(self, checked: bool) -> None:
        if checked:
            self._animate_timer.start()
        else:
            self._animate_timer.stop()

    def _on_animate_tick(self) -> None:
        # Advancing the slider fires valueChanged → one recompute per tick.
        next_value = self._slider.value() + _ANIMATE_STEP_MINUTES
        self._slider.setValue(next_value % (24 * 60))
