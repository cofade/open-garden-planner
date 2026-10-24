"""Permanent adaptive plan-date and solar-time view of the one SimClock (ADR-062)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any

from PyQt6.QtCore import QDate, QRect, QSize, Qt, QTime, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QDateEdit,
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QTimeEdit,
    QToolBar,
    QToolButton,
    QWidget,
)

from open_garden_planner.core.object_types import get_translated_display_name, is_plant_type
from open_garden_planner.core.plan_timeline import instance_date, month_number, timeline_month_range
from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE
from open_garden_planner.ui.icons import get_icon

_ANIMATE_INTERVAL_MS = 200
_ANIMATE_STEP_MINUTES = 10
#: The shortest the two sliders get while the strip makes room to stay within two
#: rows: German at 10 pt in an 800-px strip needs 80 px (measured with real fonts),
#: and 10 px more leaves room for a platform font that runs wider.
_MIN_SLIDER_WIDTH = 70


def _editor_owner(edit: QDateTimeEdit) -> SunSimToolbar | None:
    # Group layouts reparent the editors into two intermediate widgets.
    owner = edit.parentWidget()
    while owner is not None and not isinstance(owner, SunSimToolbar):
        owner = owner.parentWidget()
    return owner


def _step_editor(edit: QDateTimeEdit, steps: int) -> None:
    """Native keys, wheel and spin buttons share the toolbar's wall-time step."""
    if edit.isReadOnly():
        return
    owner = _editor_owner(edit)
    assert owner is not None
    section = edit.currentSection()
    edit.interpretText()
    owner._step_datetime(section, steps)
    edit.setSelectedSection(section)


def _editor_steps(edit: QDateTimeEdit) -> QAbstractSpinBox.StepEnabledFlag:
    flags = QAbstractSpinBox.StepEnabledFlag.StepNone
    owner = _editor_owner(edit)
    # Qt queries the virtual while constructing an editor, before both fields exist.
    if edit.isReadOnly() or owner is None or not owner._controls_ready:
        return flags
    wall = owner.current_wall_datetime()
    if owner._stepped_datetime(edit.currentSection(), 1) > wall:
        flags |= QAbstractSpinBox.StepEnabledFlag.StepUpEnabled
    if owner._stepped_datetime(edit.currentSection(), -1) < wall:
        flags |= QAbstractSpinBox.StepEnabledFlag.StepDownEnabled
    return flags


class _PlanDateEdit(QDateEdit):
    def stepBy(self, steps: int) -> None:
        _step_editor(self, steps)

    def stepEnabled(self) -> QAbstractSpinBox.StepEnabledFlag:
        return _editor_steps(self)


class _PlanTimeEdit(QTimeEdit):
    def stepBy(self, steps: int) -> None:
        _step_editor(self, steps)

    def stepEnabled(self) -> QAbstractSpinBox.StepEnabledFlag:
        return _editor_steps(self)


class _TodayButton(QToolButton):
    """Today, or Past / Future in its place while the plan date is elsewhere.

    One width for all of its texts, so the controls after it never move while the
    date does (owner manual pass of #386: a separate Past/Future label pushed the
    month slider away from the pointer while it was dragged).
    """

    def __init__(self, texts: tuple[str, ...], parent: QWidget) -> None:
        super().__init__(parent)
        self._texts = texts

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        metrics = self.fontMetrics()

        def width(text: str) -> int:
            # measured as QToolButton::sizeHint measures it: a bounding rect, rounded
            # up. horizontalAdvance rounds to nearest, and the difference moved the
            # width by 1 px with fractional font metrics (125 % scaling, unhinted
            # fonts) - invisible offscreen, where every advance is a whole box
            return metrics.size(Qt.TextFlag.TextShowMnemonic, text).width()

        # the style's padding around the current text, put around the widest one,
        # plus one letter of room: the buffer the owner asked for
        hint.setWidth(hint.width() - width(self.text())
                      + max(width(text) for text in self._texts) + metrics.horizontalAdvance("M"))
        return hint


class _GroupFlow(QLayout):
    """Wrap complete control groups, without QToolBar's overflow popup."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(2, 2, 2, 2)
        self.setSpacing(12)

    def addItem(self, item: QLayoutItem | None) -> None:
        if item is not None:
            self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), False)[0]

    def rows_for_width(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), False)[1]

    def minimumSize(self) -> QSize:
        sizes = [item.minimumSize() for item in self._items]
        return QSize(max((s.width() for s in sizes), default=0) + 4,
                     max((s.height() for s in sizes), default=0) + 4)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, True)

    def _arrange(self, rect: QRect, apply: bool) -> tuple[int, int]:
        left, top, right, bottom = self.getContentsMargins()
        x, y = rect.x() + left, rect.y() + top
        rows: list[list[tuple[QLayoutItem, QSize]]] = [[]]
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            if x > rect.x() + left and x + size.width() > rect.right() - right + 1:
                rows.append([])
                x = rect.x() + left
            rows[-1].append((item, size))
            x += size.width() + self.spacing()
        for row in rows:
            row_height = max((size.height() for _, size in row), default=0)
            x = rect.x() + left
            for item, size in row:
                if apply:
                    # Give each group's box the full row height. Its QHBoxLayout
                    # centres sliders, fields and buttons on one shared axis.
                    item.setGeometry(QRect(x, y, size.width(), row_height))
                x += size.width() + self.spacing()
            y += row_height + 4
        return y - 4 + bottom - rect.y(), len(rows)


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
    date_requested = pyqtSignal(object)
    location_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, *, scene: Any = None) -> None:
        super().__init__("", parent)
        self.setObjectName("SunSimToolbar")
        self.setWindowTitle(self.tr("Plan & Sun"))
        self.setMovable(False)
        self._scene = scene
        self._controls_ready = False
        self._requesting_month = False
        self._preferred_day = 1
        self._exposure_hint = ""
        self._map_status: tuple[date | None, bool, str] = (None, False, "")
        self._location_available = True
        self._content = QWidget(self)
        self._content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._flow = _GroupFlow(self._content)
        self.addWidget(self._content)

        group = self._group()
        self._date_edit = _PlanDateEdit(self)
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        self._date_edit.setDateRange(QDate(MIN_PLAN_DATE.year, 1, 1), QDate(MAX_PLAN_DATE.year, 12, 31))
        self._date_edit.setMinimumWidth(self._date_edit.fontMetrics().horizontalAdvance("2000-00-00") + 48)
        self._date_edit.setToolTip(self.tr("Plan date: plant presence, growth and sunlight"))
        group.addWidget(self._date_edit)
        self._today_button = _TodayButton((self.tr("Today"), self.tr("Past"), self.tr("Future")), self)
        self._configure_button(self._today_button, self.tr("Today"), group)
        # the text says where the plan date is; what the button does stays the same
        self._today_button.setAccessibleName(self.tr("Go to today"))
        self._today_button.clicked.connect(lambda: self.date_requested.emit(date.today()))

        group = self._group()
        group.addWidget(QLabel(self.tr("Months"), self))
        self._month_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._month_slider.setFixedWidth(180)
        self._month_slider.setPageStep(12)
        self._month_slider.setToolTip(self.tr("Scrub by month; Page Up/Down jumps one year"))
        group.addWidget(self._month_slider)

        group = self._group()
        self._time_edit = _PlanTimeEdit(self)
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setToolTip(self.tr("Time of day"))
        self._time_edit.setMinimumWidth(self._time_edit.fontMetrics().horizontalAdvance("00:00") + 40)
        group.addWidget(self._time_edit)
        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(0, 24 * 60 - 1)
        self._slider.setPageStep(60)
        self._slider.setFixedWidth(180)
        self._slider.setToolTip(self.tr("Time of day"))
        group.addWidget(self._slider)
        self._animate_button = self._button(self.tr("Animate"), group, checkable=True)
        self._animate_button.setToolTip(self.tr("Animate the sun across the selected day"))

        group = self._group()
        self._heatmap_button = self._button(self.tr("Hours of Sun"), group, checkable=True)
        self._location_button = self._button(self.tr("Set location for sunlight…"), group)
        self._location_button.setAutoRaise(True)
        font = self._location_button.font()
        font.setUnderline(True)
        self._location_button.setFont(font)
        self._location_button.setToolTip(self.tr(
            "Sun shadows and Hours of Sun need a garden location. Opens File → Set Garden Location…"))
        self._location_button.clicked.connect(self.location_requested)
        self._location_button.hide()
        self._map_label = QLabel(self)
        self._map_label.setWordWrap(True)
        self._map_label.hide()
        group.addWidget(self._map_label)
        group = self._group()
        self._hidden_button = self._button("", group)
        self._hidden_button.setObjectName("PlanDateHiddenPlants")
        self._hidden_menu = QMenu(self._hidden_button)
        self._hidden_button.setMenu(self._hidden_menu)
        self._hidden_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._hidden_button.setToolTip(self.tr("Plants hidden by the plan date"))
        self._hidden_menu.aboutToShow.connect(self._populate_hidden)

        self._animate_timer = QTimer(self)
        self._animate_timer.setInterval(_ANIMATE_INTERVAL_MS)
        self._animate_timer.timeout.connect(self._on_animate_tick)
        self._date_edit.dateChanged.connect(self._on_calendar_changed)
        self._time_edit.timeChanged.connect(self._on_time_edited)
        self._slider.valueChanged.connect(self._on_time_slid)
        self._month_slider.valueChanged.connect(self._request_month)
        self._month_slider.sliderReleased.connect(self._finish_month_drag)
        self._animate_button.toggled.connect(self._on_animate_toggled)
        self._heatmap_button.toggled.connect(self._on_heatmap_toggled)
        if scene is not None:
            scene.timeline_changed.connect(self.refresh)
        self.set_datetime_local(datetime.now().replace(second=0, microsecond=0))
        self.refresh_theme_icons()
        self._controls_ready = True

    def _group(self) -> QHBoxLayout:
        widget = QWidget(self._content)
        group = QHBoxLayout(widget)
        group.setContentsMargins(0, 0, 0, 0)
        group.setSpacing(5)
        group.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self._flow.addWidget(widget)
        return group

    def _button(self, text: str, group: QHBoxLayout, *, checkable: bool = False) -> QToolButton:
        button = QToolButton(self)
        self._configure_button(button, text, group, checkable=checkable)
        return button

    @staticmethod
    def _configure_button(button: QToolButton, text: str, group: QHBoxLayout, *,
                          checkable: bool = False) -> None:
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setCheckable(checkable)
        group.addWidget(button)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._reflow()

    def flow_width(self) -> int:
        """The width the reflow fits the control groups into."""
        return max(1, self.width() - 12)

    def _reflow(self) -> None:
        slider_width = 140 if self.width() < 1100 else 180
        available = self.flow_width()
        while True:
            for slider in (self._month_slider, self._slider):
                slider.setFixedWidth(slider_width)
            # Font metrics vary across platforms and themes. Recalculate group
            # hints before deciding whether the preferred slider length fits.
            for index in range(self._flow.count()):
                item = self._flow.itemAt(index)
                widget = item.widget() if item is not None else None
                layout = widget.layout() if widget is not None else None
                if widget is not None and layout is not None:
                    layout.invalidate()
                    layout.activate()
                    widget.updateGeometry()
            if self._flow.rows_for_width(available) <= 2 or slider_width <= _MIN_SLIDER_WIDTH:
                break
            slider_width -= 10
        height = self._flow.heightForWidth(available)
        if self._content.height() != height:
            self._content.setFixedHeight(height)
            self.setFixedHeight(height + 8)

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
        if self._date_edit.date() != target_date and not self._requesting_month:
            self._preferred_day = dt.day
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
        self.refresh()

    @property
    def animation_active(self) -> bool:
        return self._animate_button.isChecked()

    def set_animation_active(self, active: bool) -> None:
        self._animate_button.setChecked(active)

    def stop_animation(self) -> None:
        self._animate_button.setChecked(False)

    def set_heatmap_busy(self, busy: bool) -> None:
        """Busy indication while the worker computes."""
        self._heatmap_button.setProperty("busy", busy)

    def set_heatmap_active(self, active: bool) -> None:
        """Reflect heatmap visibility (button check state), no signals."""
        self._heatmap_button.blockSignals(True)
        try:
            self._heatmap_button.setChecked(active)
        finally:
            self._heatmap_button.blockSignals(False)

    def set_exposure_hint(self, text: str) -> None:
        """Hints live in the button tooltip: variable-width labels reflow this toolbar."""
        if text == self._exposure_hint:
            return
        self._exposure_hint = text
        self._heatmap_button.setToolTip(self.tr("Full-day hours of sun; updates automatically while enabled")
                                       + ("\n" + text if text else ""))

    # ── internals ──────────────────────────────────────────────

    def _stepped_datetime(self, section: QDateTimeEdit.Section, steps: int) -> datetime:
        """Step a naive civil reading; only the clock's absolute range saturates."""
        wall = self.current_wall_datetime()
        if not steps:
            return wall
        if section in (QDateTimeEdit.Section.HourSection, QDateTimeEdit.Section.MinuteSection):
            origin = datetime(MIN_PLAN_DATE.year, MIN_PLAN_DATE.month, MIN_PLAN_DATE.day)
            minute = ((wall.date() - MIN_PLAN_DATE).days * 1440 + wall.hour * 60 + wall.minute)
            minute += steps * (60 if section == QDateTimeEdit.Section.HourSection else 1)
            last = ((MAX_PLAN_DATE - MIN_PLAN_DATE).days + 1) * 1440 - 1
            return origin + timedelta(minutes=max(0, min(last, minute)))
        day = self._date_edit.date()
        if section == QDateTimeEdit.Section.DaySection:
            day = day.addDays(steps)
        elif section in (QDateTimeEdit.Section.MonthSection, QDateTimeEdit.Section.YearSection):
            day = QDate(day.year(), day.month(), 1)
            day = (day.addMonths(steps) if section == QDateTimeEdit.Section.MonthSection
                   else day.addYears(steps))
            if day.isValid():
                day = day.addDays(min(self._preferred_day, day.daysInMonth()) - 1)
        else:
            return wall
        if not day.isValid():
            day = self._date_edit.maximumDate() if steps > 0 else self._date_edit.minimumDate()
        day = max(self._date_edit.minimumDate(), min(self._date_edit.maximumDate(), day))
        return datetime.combine(day.toPyDate(), wall.time())

    def _step_datetime(self, section: QDateTimeEdit.Section, steps: int) -> None:
        target = self._stepped_datetime(section, steps)
        if target == self.current_wall_datetime():
            return
        previous = self._requesting_month
        self._requesting_month = section in (
            QDateTimeEdit.Section.MonthSection, QDateTimeEdit.Section.YearSection)
        try:
            self.set_datetime_local(target)
            self.datetime_changed.emit(target)
        finally:
            self._requesting_month = previous

    def _update_time_label(self) -> None:
        minutes = self._slider.value()
        self._time_edit.blockSignals(True)
        self._time_edit.setTime(QTime(minutes // 60, minutes % 60))
        self._time_edit.blockSignals(False)

    def _on_time_slid(self, _minutes: int) -> None:
        self._update_time_label()
        self.datetime_changed.emit(self.current_wall_datetime())

    def _on_calendar_changed(self, day: QDate) -> None:
        self._preferred_day = day.day()
        self.datetime_changed.emit(self.current_wall_datetime())
        self.refresh()

    def _on_time_edited(self, tod: QTime) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(tod.hour() * 60 + tod.minute())
        self._slider.blockSignals(False)
        self.datetime_changed.emit(self.current_wall_datetime())

    def _finish_month_drag(self) -> None:
        self._preferred_day = self._date_edit.date().day()

    def set_map_status(self, day: date | None, updating: bool, unavailable: str = "") -> None:
        self._map_status = (day, updating, unavailable)
        # A current map already shares the calendar's date. Only an older preview
        # needs its own date; pending/failure states always remain visible.
        text = (self.tr("Map: {date}").format(date=day.isoformat())
                if day and day != self._date_edit.date().toPyDate() else "")
        if updating:
            text = (self.tr("Map: {date} — Updating…").format(date=day.isoformat())
                    if text and day is not None else self.tr("Updating…"))
        elif unavailable and text and day is not None:
            text = self.tr("Map: {date} — Unavailable").format(date=day.isoformat())
        self._map_label.setText(text or unavailable)
        self._map_label.setToolTip(text or unavailable)
        self._map_label.setFixedWidth(min(220, self._map_label.fontMetrics().horizontalAdvance(text or unavailable) + 2))
        self._map_label.setVisible(self._location_available and bool(text or unavailable))
        self._flow.invalidate()
        self.updateGeometry()
        self._reflow()

    def set_location_available(self, available: bool) -> None:
        """Keep the location prerequisite beside the sun controls until configured."""
        self._location_available = available
        self._location_button.setVisible(not available)
        self.set_map_status(*self._map_status)

    def _on_animate_toggled(self, checked: bool) -> None:
        self._update_animate_icon()
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

    def _request_month(self, number: int) -> None:
        year, month0 = divmod(number, 12)
        day = date(year, month0 + 1, min(self._preferred_day, monthrange(year, month0 + 1)[1]))
        self._requesting_month = True
        try:
            self.date_requested.emit(day)
        finally:
            self._requesting_month = False

    def refresh(self) -> None:
        day = self._scene.plan_date if self._scene is not None else self._date_edit.date().toPyDate()
        if day is None:
            return
        plants = [] if self._scene is None else [item for item in self._scene.items()
                  if is_plant_type(getattr(item, "object_type", None))]
        low, high = timeline_month_range((p.metadata for p in plants), date.today(), day)
        self._month_slider.blockSignals(True)
        self._month_slider.setRange(low, high)
        self._month_slider.setValue(month_number(day))
        self._month_slider.blockSignals(False)
        today = date.today()
        if day < today:
            text, tip = self.tr("Past"), self.tr("The plan date is in the past. Click to go back to today.")
        elif day > today:
            text, tip = self.tr("Future"), self.tr("The plan date is in the future. Click to go back to today.")
        else:
            text, tip = self.tr("Today"), self.tr("The plan date is today.")
        self._today_button.setText(text)
        self._today_button.setToolTip(tip)
        self._today_button.setEnabled(day != today)
        count = sum(not self._scene.is_present(p) for p in plants)
        self._hidden_button.setText(self.tr("{count} hidden").format(count=count))
        self._hidden_button.setEnabled(count > 0)
        self.set_map_status(*self._map_status)

    def _populate_hidden(self) -> None:
        self._hidden_menu.clear()
        if self._scene is None:
            return
        for item in self._scene.items():
            if not is_plant_type(getattr(item, "object_type", None)) or self._scene.is_present(item):
                continue
            name = item.name or get_translated_display_name(item.object_type)
            planted = instance_date(item.metadata, "planting_date")
            removed = instance_date(item.metadata, "removal_date")
            text = self.tr("{name} — planted: {planted}; removed: {removed}").format(
                name=name, planted=planted.isoformat() if planted else "—",
                removed=removed.isoformat() if removed else "—")
            action = self._hidden_menu.addAction(text)
            assert action is not None
            # Retain only an id in a menu that can outlive the current document.
            action.triggered.connect(lambda _checked=False, iid=str(item.item_id): self._reveal(iid))

    def _reveal(self, item_id: str) -> None:
        from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE

        for item in self._scene.items():
            if str(getattr(item, "item_id", "")) != item_id:
                continue
            planted = instance_date(item.metadata, "planting_date")
            removed = instance_date(item.metadata, "removal_date")
            target = planted if planted and self._scene.plan_date < planted else (
                removed - timedelta(days=1) if removed and removed > date.min else None)
            if (target is None or not MIN_PLAN_DATE <= target <= MAX_PLAN_DATE
                    or (planted is not None and removed is not None and removed <= planted)):
                QMessageBox.information(self, self.tr("Plant date unavailable"),
                    self.tr("This plant is not present within the supported plan dates ({min} to {max}). Its stored dates have been preserved.").format(
                        min=MIN_PLAN_DATE.isoformat(), max=MAX_PLAN_DATE.isoformat()))
                return
            self.date_requested.emit(target)
            if not self._scene.is_present(item):
                return
            ancestor = item
            while ancestor.parentItem() is not None:
                ancestor = ancestor.parentItem()
            if ancestor.layer_id:
                layer = self._scene.get_layer_by_id(ancestor.layer_id)
                if layer is not None and not layer.visible:
                    from open_garden_planner.core.commands import SetLayerPropertyCommand

                    manager = self._scene._command_manager
                    if manager is None:
                        return
                    manager.execute(SetLayerPropertyCommand(self._scene, layer, "visible", False, True))
            self._scene.clearSelection()
            ancestor.setSelected(True)
            for view in self._scene.views():
                view.ensureVisible(ancestor)
            return
