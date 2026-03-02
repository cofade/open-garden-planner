"""Planting calendar view — month-by-month Gantt chart + today dashboard.

Implements US-8.5: a dedicated tab showing indoor sow, direct sow,
transplant, and harvest windows for each plant species placed on the canvas.

Implements US-8.6: a "Today's Tasks" dashboard at the top of the tab showing
actionable tasks grouped by urgency (overdue / today / this week / coming up).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QLocale, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.plant_data import PlantSpeciesData

# ─── Layout constants ──────────────────────────────────────────────────────────
_NAME_W = 210          # left column: plant name
_MONTH_W = 72          # width of each month column
_ROW_H = 36            # row height
_HEADER_H = 42         # header height
_BAR_MARGIN = 8        # vertical margin inside a row for bars
_BAR_RADIUS = 3        # rounded corner radius for bars
_TOTAL_W = _NAME_W + 12 * _MONTH_W

# ─── Colour palette ────────────────────────────────────────────────────────────
_COL_INDOOR = QColor(91, 155, 213)    # steel blue  — indoor sow
_COL_DIRECT = QColor(112, 173, 71)   # green        — direct sow
_COL_TRANSPL = QColor(237, 125, 49)  # orange       — transplant
_COL_HARVEST = QColor(192, 0, 0)     # dark red      — harvest
_COL_TODAY = QColor(220, 50, 50)     # bright red    — today marker
_COL_FROST_SPR = QColor(60, 120, 210)   # blue — last spring frost line
_COL_FROST_FALL = QColor(80, 160, 230)  # light blue — first fall frost line
_COL_GRID = QColor(220, 220, 220)
_COL_ALT_ROW = QColor(248, 248, 248)
_COL_HDR_BG = QColor(242, 242, 242)
_COL_SEL_ROW = QColor(215, 232, 252)
_COL_HOV_ROW = QColor(235, 243, 255)

# ─── Dashboard urgency colours ─────────────────────────────────────────────────
_URGENCY_ORDER = ("overdue", "today", "this_week", "coming_up")
_URGENCY_COLORS: dict[str, QColor] = {
    "overdue":   QColor(200,  50,  50),
    "today":     QColor(200, 120,   0),
    "this_week": QColor( 40, 140,  60),
    "coming_up": QColor( 60, 140, 100),
}


def _month_abbr(month_1: int) -> str:
    """Return the locale-aware short month name (1-indexed)."""
    return QLocale().monthName(month_1, QLocale.FormatType.ShortFormat)

_CALENDAR_FIELDS = (
    "indoor_sow_start", "indoor_sow_end",
    "direct_sow_start", "direct_sow_end",
    "transplant_start", "transplant_end",
    "harvest_start", "harvest_end",
)


@dataclass
class _PlantRow:
    """One row in the Gantt chart."""

    display_name: str
    species: PlantSpeciesData


@dataclass
class _DashboardTask:
    """A single actionable task in the Today dashboard."""

    task_id: str        # "{species_key}:{task_type}:{year}"
    task_type: str      # "indoor_sow" | "direct_sow" | "transplant" | "harvest"
    display_name: str   # human-readable plant name
    task_date: datetime.date   # window start date (for display)
    end_date: datetime.date    # window end date
    urgency: str        # "overdue" | "today" | "this_week" | "coming_up"
    species_key: str    # used to match canvas items


# ─── Helper utilities ──────────────────────────────────────────────────────────

def _days_in_year(year: int) -> int:
    return 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365


def _date_to_x(month: int, day: int, year: int) -> float:
    """Return x coordinate (including NAME_W offset) for a calendar date."""
    d = datetime.date(year, month, day)
    yday = d.timetuple().tm_yday
    return _NAME_W + (yday - 1) / _days_in_year(year) * (12 * _MONTH_W)


def _parse_frost(mmdd: str, year: int) -> datetime.date | None:
    """Parse 'MM-DD' into a date for the given year, or None on failure."""
    try:
        m, d = map(int, mmdd.split("-"))
        return datetime.date(year, m, d)
    except (ValueError, AttributeError):
        return None


def _classify_urgency(
    start: datetime.date, end: datetime.date, today: datetime.date
) -> str | None:
    """Return the urgency bucket for a task window, or None if not actionable."""
    # Window is currently active (started, not yet ended)
    if start <= today <= end:
        return "today"
    # Window ended recently (within 14 days) — still overdue/actionable
    delta_end = (today - end).days
    if 1 <= delta_end <= 14:
        return "overdue"
    # Window starts in the next 7 days
    delta_start = (start - today).days
    if 1 <= delta_start <= 7:
        return "this_week"
    # Window starts 8–30 days from now
    if 8 <= delta_start <= 30:
        return "coming_up"
    return None


def _generate_dashboard_tasks(
    rows: list[_PlantRow],
    last_frost: datetime.date,
    today: datetime.date,
    completed_ids: set[str],
) -> list[_DashboardTask]:
    """Generate actionable dashboard tasks from plant rows and frost dates."""
    year = today.year
    year_start = datetime.date(year, 1, 1)
    year_end = datetime.date(year, 12, 31)
    task_defs = [
        ("indoor_sow",  "indoor_sow_start",  "indoor_sow_end"),
        ("direct_sow",  "direct_sow_start",  "direct_sow_end"),
        ("transplant",  "transplant_start",  "transplant_end"),
        ("harvest",     "harvest_start",     "harvest_end"),
    ]

    tasks: list[_DashboardTask] = []
    for row in rows:
        sp = row.species
        species_key = sp.scientific_name or sp.common_name or row.display_name
        for task_type, start_attr, end_attr in task_defs:
            start_w = getattr(sp, start_attr)
            end_w = getattr(sp, end_attr)
            if start_w is None or end_w is None:
                continue
            start_date = last_frost + datetime.timedelta(weeks=start_w)
            end_date = last_frost + datetime.timedelta(weeks=end_w)
            if end_date < year_start or start_date > year_end:
                continue
            urgency = _classify_urgency(start_date, end_date, today)
            if urgency is None:
                continue
            task_id = f"{species_key}:{task_type}:{year}"
            if task_id in completed_ids:
                continue
            tasks.append(_DashboardTask(
                task_id=task_id,
                task_type=task_type,
                display_name=row.display_name,
                task_date=start_date,
                end_date=end_date,
                urgency=urgency,
                species_key=species_key,
            ))
    return tasks


# ─── Dashboard panel ───────────────────────────────────────────────────────────

class _DashboardPanel(QFrame):
    """Top panel showing actionable planting tasks grouped by urgency."""

    task_toggled = pyqtSignal(str, bool)   # task_id, done
    highlight_requested = pyqtSignal(str)  # species_key

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._collapsed = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ────────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("dashboardPanelHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 4, 6, 4)
        self._title_lbl = QLabel(self.tr("Today's Tasks"))
        self._title_lbl.setStyleSheet("font-weight: bold; font-size: 9pt;")
        header_layout.addWidget(self._title_lbl)
        header_layout.addStretch()
        self._toggle_btn = QPushButton("▾")
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setFixedSize(24, 22)
        self._toggle_btn.setToolTip(self.tr("Collapse/expand"))
        self._toggle_btn.clicked.connect(self._toggle)
        header_layout.addWidget(self._toggle_btn)
        outer.addWidget(header)

        # ── Scrollable task content ───────────────────────────────────────────
        self._content_scroll = QScrollArea()
        self._content_scroll.setWidgetResizable(True)
        self._content_scroll.setMaximumHeight(170)
        self._content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._content_inner = QWidget()
        self._content_layout = QVBoxLayout(self._content_inner)
        self._content_layout.setContentsMargins(6, 4, 6, 4)
        self._content_layout.setSpacing(2)
        self._content_scroll.setWidget(self._content_inner)
        outer.addWidget(self._content_scroll)

        # ── No-tasks label ────────────────────────────────────────────────────
        self._empty_lbl = QLabel(self.tr("No upcoming tasks in the next 30 days."))
        self._empty_lbl.setStyleSheet("color: #666; font-size: 9pt; padding: 6px 12px;")
        self._empty_lbl.hide()
        outer.addWidget(self._empty_lbl)

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._content_scroll.setVisible(not self._collapsed)
        self._empty_lbl.setVisible(
            not self._collapsed and not self._content_scroll.isVisibleTo(self)
            and self._empty_lbl.text() != ""
        )
        self._toggle_btn.setText("▸" if self._collapsed else "▾")

    def set_data(self, tasks: list[_DashboardTask]) -> None:
        """Rebuild the dashboard content with new tasks."""
        # Clear old content
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        grouped: dict[str, list[_DashboardTask]] = {u: [] for u in _URGENCY_ORDER}
        for task in tasks:
            grouped[task.urgency].append(task)

        total = sum(len(v) for v in grouped.values())
        self._title_lbl.setText(self.tr("Today's Tasks") + f" ({total})")

        if total == 0:
            self._content_scroll.hide()
            self._empty_lbl.setText(self.tr("No upcoming tasks in the next 30 days."))
            self._empty_lbl.show()
            self._toggle_btn.setEnabled(False)
            return

        self._empty_lbl.hide()
        self._toggle_btn.setEnabled(True)
        if not self._collapsed:
            self._content_scroll.show()

        urgency_labels = {
            "overdue":   self.tr("Overdue"),
            "today":     self.tr("Today"),
            "this_week": self.tr("This Week"),
            "coming_up": self.tr("Coming Up"),
        }
        task_templates = {
            "indoor_sow": self.tr("Start indoor sowing of %1"),
            "direct_sow": self.tr("Direct sow %1"),
            "transplant": self.tr("Transplant %1 outdoors"),
            "harvest":    self.tr("Harvest %1"),
        }

        for urgency in _URGENCY_ORDER:
            group = grouped[urgency]
            if not group:
                continue
            color = _URGENCY_COLORS[urgency]

            # Group header
            grp_lbl = QLabel(urgency_labels[urgency])
            grp_lbl.setStyleSheet(
                f"font-weight: bold; font-size: 8pt; color: {color.name()};"
                " padding: 3px 2px 1px 2px;"
            )
            self._content_layout.addWidget(grp_lbl)

            for task in group:
                self._content_layout.addWidget(
                    self._make_task_row(task, task_templates, color)
                )

        self._content_layout.addStretch()

    def _make_task_row(
        self,
        task: _DashboardTask,
        templates: dict[str, str],
        color: QColor,
    ) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(6)

        # Colored urgency dot
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color.name()}; font-size: 8pt;")
        dot.setFixedWidth(12)
        layout.addWidget(dot)

        # Task description
        template = templates.get(task.task_type, "%1")
        lbl = QLabel(template.replace("%1", task.display_name))
        lbl.setStyleSheet("font-size: 9pt;")
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(lbl)

        # Date hint — use hint property so theme.py provides the secondary color
        date_lbl = QLabel(task.task_date.strftime("%b %d"))
        date_lbl.setStyleSheet("font-size: 8pt;")
        date_lbl.setProperty("hint", True)
        date_lbl.setFixedWidth(44)
        layout.addWidget(date_lbl)

        # Highlight-on-canvas button
        goto_btn = QPushButton("→")
        goto_btn.setToolTip(self.tr("Highlight on canvas"))
        goto_btn.setFlat(True)
        goto_btn.setFixedSize(26, 20)
        species_key = task.species_key
        goto_btn.clicked.connect(lambda: self.highlight_requested.emit(species_key))
        layout.addWidget(goto_btn)

        # Mark-done toggle button (checkable QPushButton, clearly labeled)
        done_btn = QPushButton(self.tr("Done"))
        done_btn.setObjectName("taskDoneBtn")
        done_btn.setCheckable(True)
        done_btn.setFixedSize(46, 20)
        done_btn.setToolTip(self.tr("Mark as done"))
        task_id = task.task_id
        done_btn.toggled.connect(lambda checked: self.task_toggled.emit(task_id, checked))
        layout.addWidget(done_btn)

        return row


# ─── Gantt painting widget ─────────────────────────────────────────────────────

class _GanttWidget(QWidget):
    """Custom-painted Gantt chart widget (placed inside a QScrollArea)."""

    row_clicked = pyqtSignal(int)  # emits row index (–1 = deselected)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[_PlantRow] = []
        self._year: int = datetime.date.today().year
        self._last_frost: datetime.date | None = None
        self._first_fall: datetime.date | None = None
        self._selected: int = -1
        self._hovered: int = -1
        # translated marker labels — set by PlantingCalendarView before painting
        self.label_today = "Today"
        self.label_last_frost = "Last frost"
        self.label_first_frost = "First frost"
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ── public API ─────────────────────────────────────────────────────────────

    def set_data(
        self,
        rows: list[_PlantRow],
        year: int,
        last_frost: datetime.date | None,
        first_fall: datetime.date | None,
    ) -> None:
        self._rows = rows
        self._year = year
        self._last_frost = last_frost
        self._first_fall = first_fall
        self._selected = -1
        total_h = max(_HEADER_H + len(rows) * _ROW_H, _HEADER_H + 1)
        self.setFixedSize(_TOTAL_W, total_h)
        self.update()

    # ── mouse ──────────────────────────────────────────────────────────────────

    def _row_at(self, y: int) -> int:
        if y < _HEADER_H:
            return -1
        row = (y - _HEADER_H) // _ROW_H
        return row if row < len(self._rows) else -1

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        row = self._row_at(event.pos().y())
        if row != self._hovered:
            self._hovered = row
            self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[override]  # noqa: ARG002
        if self._hovered != -1:
            self._hovered = -1
            self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            row = self._row_at(event.pos().y())
            new_sel = row if row != self._selected else -1
            if new_sel != self._selected:
                self._selected = new_sel
                self.update()
                self.row_clicked.emit(self._selected)

    # ── painting ───────────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_header(painter)
        self._paint_rows(painter)
        self._paint_frost_lines(painter)
        self._paint_today(painter)

    def _paint_header(self, painter: QPainter) -> None:
        painter.fillRect(0, 0, _TOTAL_W, _HEADER_H, _COL_HDR_BG)
        # "Plant" heading
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(9)
        painter.setFont(bold)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(QRect(8, 0, _NAME_W - 16, _HEADER_H), Qt.AlignmentFlag.AlignVCenter, "Plant")
        # Month labels + vertical dividers
        normal = QFont()
        normal.setPointSize(9)
        painter.setFont(normal)
        for m in range(12):
            x = _NAME_W + m * _MONTH_W
            painter.setPen(QPen(_COL_GRID, 1))
            painter.drawLine(x, 0, x, _HEADER_H)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(QRect(x + 2, 0, _MONTH_W - 4, _HEADER_H), Qt.AlignmentFlag.AlignCenter, _month_abbr(m + 1))
        # Bottom border
        painter.setPen(QPen(QColor(190, 190, 190), 1))
        painter.drawLine(0, _HEADER_H - 1, _TOTAL_W, _HEADER_H - 1)

    def _paint_rows(self, painter: QPainter) -> None:
        normal = QFont()
        normal.setPointSize(9)
        painter.setFont(normal)

        for i, row in enumerate(self._rows):
            y = _HEADER_H + i * _ROW_H
            # Row background
            if i == self._selected:
                bg: Any = _COL_SEL_ROW
            elif i == self._hovered:
                bg = _COL_HOV_ROW
            elif i % 2:
                bg = _COL_ALT_ROW
            else:
                bg = Qt.GlobalColor.white
            painter.fillRect(0, y, _TOTAL_W, _ROW_H, bg)
            # Grid lines
            painter.setPen(QPen(_COL_GRID, 0.5))
            painter.drawLine(0, y + _ROW_H - 1, _TOTAL_W, y + _ROW_H - 1)
            for m in range(12):
                mx = _NAME_W + m * _MONTH_W
                painter.drawLine(mx, y, mx, y + _ROW_H)
            # Plant name (clipped to name column)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(QRect(8, y, _NAME_W - 16, _ROW_H), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, row.display_name)
            # Calendar bars
            if self._last_frost is not None:
                self._paint_bars(painter, row.species, y)

    def _paint_bars(self, painter: QPainter, sp: PlantSpeciesData, row_y: int) -> None:
        assert self._last_frost is not None
        bar_y = row_y + _BAR_MARGIN
        bar_h = _ROW_H - 2 * _BAR_MARGIN
        year = self._year
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)

        segments = [
            (sp.indoor_sow_start, sp.indoor_sow_end, _COL_INDOOR),
            (sp.direct_sow_start, sp.direct_sow_end, _COL_DIRECT),
            (sp.transplant_start, sp.transplant_end, _COL_TRANSPL),
            (sp.harvest_start, sp.harvest_end, _COL_HARVEST),
        ]
        for start_w, end_w, color in segments:
            if start_w is None or end_w is None:
                continue
            d_start = self._last_frost + datetime.timedelta(weeks=start_w)
            d_end = self._last_frost + datetime.timedelta(weeks=end_w)
            if d_end < year_start or d_start > year_end:
                continue
            d_start = max(d_start, year_start)
            d_end = min(d_end, year_end)
            x1 = _date_to_x(d_start.month, d_start.day, year)
            x2 = _date_to_x(d_end.month, d_end.day, year)
            if x2 - x1 < 4:
                x2 = x1 + 4
            rect = QRect(int(x1), bar_y, int(x2 - x1), bar_h)
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, _BAR_RADIUS, _BAR_RADIUS)

    def _paint_today(self, painter: QPainter) -> None:
        today = datetime.date.today()
        if today.year != self._year:
            return
        x = int(_date_to_x(today.month, today.day, self._year))
        total_h = _HEADER_H + len(self._rows) * _ROW_H
        pen = QPen(_COL_TODAY, 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(x, 0, x, total_h)
        # "Today" label in header
        small = QFont()
        small.setPointSize(7)
        small.setBold(True)
        painter.setFont(small)
        painter.setPen(_COL_TODAY)
        painter.drawText(x + 3, 14, self.label_today)

    def _paint_frost_lines(self, painter: QPainter) -> None:
        total_h = _HEADER_H + len(self._rows) * _ROW_H
        pairs = [
            (self._last_frost, _COL_FROST_SPR, self.label_last_frost),
            (self._first_fall, _COL_FROST_FALL, self.label_first_frost),
        ]
        small = QFont()
        small.setPointSize(7)
        painter.setFont(small)
        for frost_date, color, label in pairs:
            if frost_date is None:
                continue
            try:
                d = datetime.date(self._year, frost_date.month, frost_date.day)
            except ValueError:
                continue
            x = int(_date_to_x(d.month, d.day, self._year))
            pen = QPen(color, 1)
            pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.drawLine(x, _HEADER_H, x, total_h)
            painter.setPen(color)
            painter.drawText(x + 2, _HEADER_H + 20, label)


# ─── Detail panel ──────────────────────────────────────────────────────────────

class _DetailPanel(QFrame):
    """Shows botanical details for the selected plant row."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMaximumHeight(90)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)
        self._name_lbl = QLabel()
        self._name_lbl.setStyleSheet("font-weight: bold; font-size: 10pt;")
        self._info_lbl = QLabel()
        self._info_lbl.setWordWrap(True)
        self._info_lbl.setStyleSheet("font-size: 9pt; color: #444;")
        layout.addWidget(self._name_lbl)
        layout.addWidget(self._info_lbl)

    def show_species(self, sp: PlantSpeciesData, no_data_text: str = "No detailed data available") -> None:
        name = sp.common_name or sp.scientific_name
        sci = f" ({sp.scientific_name})" if sp.scientific_name and sp.scientific_name != name else ""
        self._name_lbl.setText(f"{name}{sci}")
        parts: list[str] = []
        if sp.days_to_germination_min is not None:
            parts.append(f"Germination: {sp.days_to_germination_min}–{sp.days_to_germination_max} days")
        if sp.min_germination_temp_c is not None:
            parts.append(f"Min. germ. temp: {sp.min_germination_temp_c} °C")
        if sp.seed_depth_cm is not None:
            parts.append(f"Seed depth: {sp.seed_depth_cm} cm")
        if sp.frost_tolerance:
            parts.append(f"Frost tolerance: {sp.frost_tolerance}")
        if sp.days_to_maturity_min is not None:
            parts.append(f"Maturity: {sp.days_to_maturity_min}–{sp.days_to_maturity_max} days")
        self._info_lbl.setText("  ·  ".join(parts) if parts else no_data_text)


# ─── Main view ─────────────────────────────────────────────────────────────────

class PlantingCalendarView(QWidget):
    """Full-screen tab view: planting calendar Gantt chart + today dashboard.

    Reads placed plants from canvas_scene and frost dates from
    project_manager.location to draw a 12-month Gantt chart and a
    "Today's Tasks" dashboard at the top.
    """

    #: Emitted when the user clicks "highlight on canvas" for a task.
    #: Carries the species key (scientific_name or common_name).
    highlight_species = pyqtSignal(str)

    def __init__(self, canvas_scene: Any, project_manager: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canvas_scene = canvas_scene
        self._project_manager = project_manager
        self._rows: list[_PlantRow] = []
        self._build_ui()

    # ── construction ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Dashboard panel (US-8.6)
        self._dashboard = _DashboardPanel()
        self._dashboard.highlight_requested.connect(self.highlight_species.emit)
        self._dashboard.task_toggled.connect(self._on_task_toggled)
        root.addWidget(self._dashboard)

        root.addWidget(self._make_legend())

        # Scroll area holding the Gantt chart
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._gantt = _GanttWidget()
        self._gantt.row_clicked.connect(self._on_row_clicked)
        self._scroll.setWidget(self._gantt)
        root.addWidget(self._scroll, 1)

        # Empty-state label (shown instead of scroll area when no data)
        self._empty_lbl = QLabel()
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #888; font-size: 13px;")
        self._empty_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._empty_lbl)

        # Detail panel
        self._detail = _DetailPanel()
        root.addWidget(self._detail)
        self._detail.hide()

        self.refresh()

    def _make_legend(self) -> QWidget:
        bar = QFrame()
        bar.setFrameShape(QFrame.Shape.StyledPanel)
        bar.setMaximumHeight(34)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(10)
        items = [
            (_COL_INDOOR, self.tr("Indoor sow")),
            (_COL_DIRECT, self.tr("Direct sow")),
            (_COL_TRANSPL, self.tr("Transplant")),
            (_COL_HARVEST, self.tr("Harvest")),
        ]
        for color, label in items:
            swatch = QLabel()
            swatch.setFixedSize(14, 14)
            swatch.setStyleSheet(f"background-color: {color.name()}; border-radius: 2px;")
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 9pt;")
            layout.addWidget(swatch)
            layout.addWidget(lbl)
        layout.addStretch()
        return bar

    # ── data collection ────────────────────────────────────────────────────────

    def _collect_data(
        self,
    ) -> tuple[list[_PlantRow], datetime.date | None, datetime.date | None]:
        """Collect unique plant species and frost dates from current project state."""
        location = self._project_manager.location
        year = datetime.date.today().year
        last_frost: datetime.date | None = None
        first_fall: datetime.date | None = None

        if location:
            frost = location.get("frost_dates") or {}
            lsf = frost.get("last_spring_frost")
            fff = frost.get("first_fall_frost")
            if lsf:
                last_frost = _parse_frost(lsf, year)
            if fff:
                first_fall = _parse_frost(fff, year)

        seen: dict[str, _PlantRow] = {}
        for item in self._canvas_scene.items():
            if not hasattr(item, "metadata"):
                continue
            ps_dict = item.metadata.get("plant_species")
            if not ps_dict:
                continue
            try:
                species = PlantSpeciesData.from_dict(ps_dict)
            except Exception:
                continue
            # Only include if at least one calendar window is defined
            if not any(getattr(species, f) is not None for f in _CALENDAR_FIELDS):
                continue
            key = species.scientific_name or species.common_name
            if key and key not in seen:
                name = species.common_name or species.scientific_name
                seen[key] = _PlantRow(display_name=name, species=species)

        rows = sorted(seen.values(), key=lambda r: r.display_name.lower())
        return rows, last_frost, first_fall

    # ── refresh ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Rebuild the chart and dashboard from current canvas + project state."""
        rows, last_frost, first_fall = self._collect_data()
        self._rows = rows

        # ── Update dashboard (US-8.6) ──────────────────────────────────────────
        today = datetime.date.today()
        completed_ids: set[str] = set()
        if hasattr(self._project_manager, "task_completions"):
            completed_ids = self._project_manager.task_completions
        if last_frost is not None and rows:
            tasks = _generate_dashboard_tasks(rows, last_frost, today, completed_ids)
        else:
            tasks = []
        self._dashboard.set_data(tasks)

        # ── Update Gantt ───────────────────────────────────────────────────────
        # Update translated marker labels on the gantt widget
        self._gantt.label_today = self.tr("Today")
        self._gantt.label_last_frost = self.tr("Last frost")
        self._gantt.label_first_frost = self.tr("First frost")

        no_location = last_frost is None
        if not rows or no_location:
            self._scroll.hide()
            self._detail.hide()
            if no_location:
                self._empty_lbl.setText(
                    self.tr(
                        "No location set.\n"
                        "Use File \u203a Set Garden Location to configure frost dates\n"
                        "before the planting calendar can be shown."
                    )
                )
            else:
                self._empty_lbl.setText(
                    self.tr(
                        "No plants with calendar data found.\n"
                        "Place plants on the canvas and use Search Plant Database\n"
                        "to assign species data."
                    )
                )
            self._empty_lbl.show()
            return

        self._empty_lbl.hide()
        year = today.year
        self._gantt.set_data(rows, year, last_frost, first_fall)
        self._scroll.show()

    # ── event handlers ─────────────────────────────────────────────────────────

    def _on_row_clicked(self, row_idx: int) -> None:
        if 0 <= row_idx < len(self._rows):
            self._detail.show_species(
                self._rows[row_idx].species,
                no_data_text=self.tr("No detailed data available"),
            )
            self._detail.show()
        else:
            self._detail.hide()

    def _on_task_toggled(self, task_id: str, done: bool) -> None:
        """Persist task completion state, then refresh the dashboard."""
        if hasattr(self._project_manager, "set_task_completion"):
            self._project_manager.set_task_completion(task_id, done)
        self.refresh()
