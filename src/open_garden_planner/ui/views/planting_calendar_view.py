"""Planting calendar view — month-by-month Gantt chart + today dashboard.

Implements US-8.5: a dedicated tab showing indoor sow, direct sow,
transplant, and harvest windows for each plant species placed on the canvas.

Implements US-8.6: a "Today's Tasks" dashboard at the top of the tab showing
actionable tasks grouped by urgency (overdue / today / this week / coming up).

Implements US-9.5: propagation sub-rows in the Gantt chart showing the full
indoor pre-cultivation cycle (germination → pricking out → hardening off →
transplanting), with user-adjustable per-step dates.
"""
from __future__ import annotations

import contextlib
import datetime
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QDate, QLocale, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.app.settings import get_settings
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.models.propagation import PropagationPlan, compute_propagation_plan
from open_garden_planner.services.weather_service import get_frost_alerts
from open_garden_planner.ui.widgets.weather_widget import WeatherWidget

# ─── Layout constants ──────────────────────────────────────────────────────────
_NAME_W = 210          # left column: plant name
_MONTH_W = 72          # width of each month column
_ROW_H = 36            # main row height
_PROP_ROW_H = 22       # propagation sub-row height
_HEADER_H = 42         # header height
_BAR_MARGIN = 8        # vertical margin inside a row for bars
_BAR_RADIUS = 3        # rounded corner radius for bars
_PROP_BAR_H = 8        # bar height for propagation sub-row
_PROP_BAR_Y = 7        # offset from sub-row top to bar center
_TOTAL_W = _NAME_W + 12 * _MONTH_W

# ─── Colour palette — main calendar ────────────────────────────────────────────
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

# ─── Colour palette — propagation sub-row ──────────────────────────────────────
_COL_PROP_BG = QColor(245, 248, 250)        # sub-row background
_COL_PROP_BG_ALT = QColor(240, 244, 248)
_COL_PROP_BG_SEL = QColor(210, 228, 250)
_COL_GERM = QColor(140, 195, 235)           # light steel blue — germination
_COL_PRICK = QColor(155, 89, 182)           # purple — prick out (point marker)
_COL_HARDEN = QColor(26, 188, 156)          # teal — harden off
_COL_TRANSPLANT_PROP = QColor(230, 126, 34) # orange — transplant marker

# ─── Dashboard urgency colours ─────────────────────────────────────────────────
_URGENCY_ORDER = ("overdue", "today", "this_week", "coming_up")
_URGENCY_COLORS: dict[str, QColor] = {
    "overdue":       QColor(200,  50,  50),
    "today":         QColor(200, 120,   0),
    "this_week":     QColor( 40, 140,  60),
    "coming_up":     QColor( 60, 140, 100),
    "soil_mismatch": QColor(200, 120,   0),  # amber — same as "today" (US-12.10d)
}

# All task types including propagation steps
_PROP_TASK_TYPES = ("prick_out", "harden_off")


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
    species_key: str = ""   # defaults to scientific_name or common_name if not set


@dataclass
class _DashboardTask:
    """A single actionable task in the Today dashboard."""

    task_id: str        # "{species_key}:{task_type}:{year}"
    task_type: str      # "indoor_sow" | "direct_sow" | "transplant" | "harvest" | "prick_out" | "harden_off"
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
    if start <= today <= end:
        return "today"
    delta_end = (today - end).days
    if 1 <= delta_end <= 14:
        return "overdue"
    delta_start = (start - today).days
    if 1 <= delta_start <= 7:
        return "this_week"
    if 8 <= delta_start <= 30:
        return "coming_up"
    return None


def _generate_dashboard_tasks(
    rows: list[_PlantRow],
    last_frost: datetime.date,
    today: datetime.date,
    completed_ids: set[str],
    prop_plans: dict[str, PropagationPlan] | None = None,
) -> list[_DashboardTask]:
    """Generate actionable dashboard tasks from plant rows and frost dates.

    Includes standard planting tasks (indoor sow, direct sow, transplant,
    harvest) plus propagation tasks (pricking out, hardening off) from US-9.5.
    """
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
        # Use explicit key if set, otherwise derive from species data
        species_key = row.species_key or (sp.scientific_name or sp.common_name or row.display_name)

        # Standard calendar tasks
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

        # Propagation tasks (US-9.5): prick_out and harden_off
        if prop_plans is None:
            continue
        plan = prop_plans.get(species_key)
        if plan is None:
            continue
        prop_task_defs = [
            ("prick_out",  "prick_out"),
            ("harden_off", "harden_off"),
        ]
        for task_type, step_id in prop_task_defs:
            step = plan.get_step(step_id)
            if step is None:
                continue
            start_date = step.start_date
            end_date = step.end_date
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
            "indoor_sow":         self.tr("Start indoor sowing of %1"),
            "direct_sow":         self.tr("Direct sow %1"),
            "transplant":         self.tr("Transplant %1 outdoors"),
            "harvest":            self.tr("Harvest %1"),
            "prick_out":          self.tr("Prick out %1 seedlings"),
            "harden_off":         self.tr("Start hardening off %1"),
            "frost_alert_orange": self.tr("⚠ Frost: %1"),
            "frost_alert_red":    self.tr("❄ Hard frost: %1"),
        }

        for urgency in _URGENCY_ORDER:
            group = grouped[urgency]
            if not group:
                continue
            color = _URGENCY_COLORS[urgency]

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

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color.name()}; font-size: 8pt;")
        dot.setFixedWidth(12)
        layout.addWidget(dot)

        template = templates.get(task.task_type, "%1")
        lbl = QLabel(template.replace("%1", task.display_name))
        lbl.setStyleSheet("font-size: 9pt;")
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(lbl)

        date_lbl = QLabel(task.task_date.strftime("%b %d"))
        date_lbl.setStyleSheet("font-size: 8pt;")
        date_lbl.setProperty("hint", True)
        date_lbl.setFixedWidth(44)
        layout.addWidget(date_lbl)

        goto_btn = QPushButton("→")
        goto_btn.setToolTip(self.tr("Highlight on canvas"))
        goto_btn.setFlat(True)
        goto_btn.setFixedSize(26, 20)
        species_key = task.species_key
        goto_btn.clicked.connect(lambda: self.highlight_requested.emit(species_key))
        layout.addWidget(goto_btn)

        if not task.task_type.startswith("frost_alert"):
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
    """Custom-painted Gantt chart widget (placed inside a QScrollArea).

    Supports two display modes:
    - Normal: one _ROW_H row per plant (main calendar bars only).
    - Propagation: _ROW_H + _PROP_ROW_H per plant — adds a sub-row
      showing germination → prick out → harden off → transplant.
    """

    row_clicked = pyqtSignal(int)  # emits row index (–1 = deselected)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[_PlantRow] = []
        self._year: int = datetime.date.today().year
        self._last_frost: datetime.date | None = None
        self._first_fall: datetime.date | None = None
        self._selected: int = -1
        self._hovered: int = -1
        self._show_propagation: bool = False
        self._prop_plans: dict[str, PropagationPlan] = {}
        # translated marker labels
        self.label_today = "Today"
        self.label_last_frost = "Last frost"
        self.label_first_frost = "First frost"
        self.label_germination = "Germination"
        self.label_prick_out = "Prick out"
        self.label_harden_off = "Harden off"
        self.label_transplant = "Transplant"
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ── public API ─────────────────────────────────────────────────────────────

    @property
    def effective_row_h(self) -> int:
        """Total row height per plant (including propagation sub-row if enabled)."""
        return _ROW_H + (_PROP_ROW_H if self._show_propagation else 0)

    def set_data(
        self,
        rows: list[_PlantRow],
        year: int,
        last_frost: datetime.date | None,
        first_fall: datetime.date | None,
        prop_plans: dict[str, PropagationPlan] | None = None,
    ) -> None:
        self._rows = rows
        self._year = year
        self._last_frost = last_frost
        self._first_fall = first_fall
        self._prop_plans = prop_plans or {}
        self._selected = -1
        self._update_size()
        self.update()

    def set_show_propagation(self, show: bool) -> None:
        self._show_propagation = show
        self._update_size()
        self.update()

    def _update_size(self) -> None:
        total_h = max(_HEADER_H + len(self._rows) * self.effective_row_h, _HEADER_H + 1)
        self.setFixedSize(_TOTAL_W, total_h)

    # ── mouse ──────────────────────────────────────────────────────────────────

    def _row_at(self, y: int) -> int:
        if y < _HEADER_H:
            return -1
        row = (y - _HEADER_H) // self.effective_row_h
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
        bold = QFont()
        bold.setBold(True)
        bold.setPointSize(9)
        painter.setFont(bold)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(QRect(8, 0, _NAME_W - 16, _HEADER_H), Qt.AlignmentFlag.AlignVCenter, "Plant")
        normal = QFont()
        normal.setPointSize(9)
        painter.setFont(normal)
        for m in range(12):
            x = _NAME_W + m * _MONTH_W
            painter.setPen(QPen(_COL_GRID, 1))
            painter.drawLine(x, 0, x, _HEADER_H)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(QRect(x + 2, 0, _MONTH_W - 4, _HEADER_H), Qt.AlignmentFlag.AlignCenter, _month_abbr(m + 1))
        painter.setPen(QPen(QColor(190, 190, 190), 1))
        painter.drawLine(0, _HEADER_H - 1, _TOTAL_W, _HEADER_H - 1)

    def _paint_rows(self, painter: QPainter) -> None:
        normal = QFont()
        normal.setPointSize(9)
        painter.setFont(normal)
        rh = self.effective_row_h

        for i, row in enumerate(self._rows):
            y = _HEADER_H + i * rh

            # Main row background
            if i == self._selected:
                bg: Any = _COL_SEL_ROW
            elif i == self._hovered:
                bg = _COL_HOV_ROW
            elif i % 2:
                bg = _COL_ALT_ROW
            else:
                bg = Qt.GlobalColor.white
            painter.fillRect(0, y, _TOTAL_W, _ROW_H, bg)

            # Grid lines for main row
            painter.setPen(QPen(_COL_GRID, 0.5))
            painter.drawLine(0, y + _ROW_H - 1, _TOTAL_W, y + _ROW_H - 1)
            for m in range(12):
                mx = _NAME_W + m * _MONTH_W
                painter.drawLine(mx, y, mx, y + _ROW_H)

            # Plant name
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(QRect(8, y, _NAME_W - 16, _ROW_H), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, row.display_name)

            # Calendar bars
            if self._last_frost is not None:
                self._paint_bars(painter, row.species, y)

            # Propagation sub-row
            if self._show_propagation:
                self._paint_prop_row(painter, row, i, y + _ROW_H)

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

    def _paint_prop_row(
        self, painter: QPainter, row: _PlantRow, row_idx: int, sub_y: int
    ) -> None:
        """Paint the propagation sub-row at vertical position sub_y."""
        # Sub-row background
        if row_idx == self._selected:
            bg: Any = _COL_PROP_BG_SEL
        elif row_idx % 2:
            bg = _COL_PROP_BG_ALT
        else:
            bg = _COL_PROP_BG
        painter.fillRect(0, sub_y, _TOTAL_W, _PROP_ROW_H, bg)

        # Bottom border of sub-row
        painter.setPen(QPen(_COL_GRID, 0.5))
        painter.drawLine(0, sub_y + _PROP_ROW_H - 1, _TOTAL_W, sub_y + _PROP_ROW_H - 1)
        for m in range(12):
            mx = _NAME_W + m * _MONTH_W
            painter.drawLine(mx, sub_y, mx, sub_y + _PROP_ROW_H)

        # Label in name column
        small = QFont()
        small.setPointSize(7)
        painter.setFont(small)
        painter.setPen(QColor(130, 130, 130))
        painter.drawText(
            QRect(14, sub_y, _NAME_W - 20, _PROP_ROW_H),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "↳ " + self.tr("Propagation"),
        )

        plan = self._prop_plans.get(row.species_key)
        if plan is None or self._last_frost is None:
            return

        year = self._year
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)
        bar_top = sub_y + _PROP_BAR_Y
        bar_h = _PROP_BAR_H

        # Paint each propagation step
        step_styles = [
            ("germination",  _COL_GERM,            False),  # period bar
            ("harden_off",   _COL_HARDEN,           False),  # period bar
            ("prick_out",    _COL_PRICK,            True),   # point marker
            ("transplant",   _COL_TRANSPLANT_PROP,  True),   # point marker
        ]

        painter.setPen(Qt.PenStyle.NoPen)
        for step_id, color, is_point in step_styles:
            step = plan.get_step(step_id)
            if step is None:
                continue
            d_start = step.start_date
            d_end = step.end_date
            if d_end < year_start or d_start > year_end:
                continue
            d_start_cl = max(d_start, year_start)
            d_end_cl = min(d_end, year_end)
            x1 = _date_to_x(d_start_cl.month, d_start_cl.day, year)
            x2 = _date_to_x(d_end_cl.month, d_end_cl.day, year)

            if is_point:
                # Draw a small diamond marker
                cx = int(x1)
                cy = bar_top + bar_h // 2
                half = 5
                painter.setBrush(QBrush(color))
                diamond = QPolygon([
                    QPoint(cx, cy - half),
                    QPoint(cx + half, cy),
                    QPoint(cx, cy + half),
                    QPoint(cx - half, cy),
                ])
                painter.drawPolygon(diamond)
            else:
                # Period bar
                if x2 - x1 < 4:
                    x2 = x1 + 4
                rect = QRect(int(x1), bar_top, int(x2 - x1), bar_h)
                painter.setBrush(QBrush(color))
                painter.drawRoundedRect(rect, 2, 2)

        # Restore font for next row
        normal = QFont()
        normal.setPointSize(9)
        painter.setFont(normal)

    def _paint_today(self, painter: QPainter) -> None:
        today = datetime.date.today()
        if today.year != self._year:
            return
        x = int(_date_to_x(today.month, today.day, self._year))
        total_h = _HEADER_H + len(self._rows) * self.effective_row_h
        pen = QPen(_COL_TODAY, 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawLine(x, 0, x, total_h)
        small = QFont()
        small.setPointSize(7)
        small.setBold(True)
        painter.setFont(small)
        painter.setPen(_COL_TODAY)
        painter.drawText(x + 3, 14, self.label_today)

    def _paint_frost_lines(self, painter: QPainter) -> None:
        total_h = _HEADER_H + len(self._rows) * self.effective_row_h
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
    """Shows botanical details and propagation step editor for the selected plant."""

    #: Emitted when the user confirms a step date change.
    #: (species_key, step_id, start_iso, end_iso)
    step_date_changed = pyqtSignal(str, str, str, str)
    #: Emitted when the user resets a step override.
    #: (species_key, step_id)
    step_date_reset = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        self._name_lbl = QLabel()
        self._name_lbl.setStyleSheet("font-weight: bold; font-size: 10pt;")
        self._info_lbl = QLabel()
        self._info_lbl.setWordWrap(True)
        self._info_lbl.setStyleSheet("font-size: 9pt; color: #444;")
        layout.addWidget(self._name_lbl)
        layout.addWidget(self._info_lbl)

        # Propagation step editor (shown when propagation mode is enabled)
        self._prop_widget = QWidget()
        prop_layout = QVBoxLayout(self._prop_widget)
        prop_layout.setContentsMargins(0, 4, 0, 0)
        prop_layout.setSpacing(2)

        hdr = QLabel(self.tr("Propagation Steps"))
        hdr.setStyleSheet("font-weight: bold; font-size: 8pt; color: #555;")
        prop_layout.addWidget(hdr)

        # Step rows: (step_id, label, is_period)
        self._step_rows: dict[str, tuple[QDateEdit, QDateEdit | None, QPushButton]] = {}
        step_defs = [
            ("indoor_sow",  self.tr("Indoor sow"),    True),
            ("germination", self.tr("Germination"),   True),
            ("prick_out",   self.tr("Prick out"),     False),
            ("harden_off",  self.tr("Harden off"),    True),
            ("transplant",  self.tr("Transplant"),    False),
        ]
        for step_id, label, is_period in step_defs:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            lbl = QLabel(label + ":")
            lbl.setStyleSheet("font-size: 8pt;")
            lbl.setFixedWidth(80)
            row_layout.addWidget(lbl)

            start_edit = QDateEdit()
            start_edit.setCalendarPopup(True)
            start_edit.setDisplayFormat("dd MMM")
            start_edit.setFixedWidth(80)
            row_layout.addWidget(start_edit)

            end_edit: QDateEdit | None = None
            if is_period:
                dash = QLabel("–")
                dash.setStyleSheet("font-size: 8pt;")
                row_layout.addWidget(dash)
                end_edit = QDateEdit()
                end_edit.setCalendarPopup(True)
                end_edit.setDisplayFormat("dd MMM")
                end_edit.setFixedWidth(80)
                row_layout.addWidget(end_edit)

            reset_btn = QPushButton(self.tr("↺"))
            reset_btn.setToolTip(self.tr("Reset to calculated date"))
            reset_btn.setFixedSize(22, 20)
            reset_btn.setFlat(True)
            row_layout.addWidget(reset_btn)
            row_layout.addStretch()

            prop_layout.addWidget(row_widget)
            self._step_rows[step_id] = (start_edit, end_edit, reset_btn)

        layout.addWidget(self._prop_widget)
        self._prop_widget.hide()

        self._current_species_key: str = ""
        self._current_plan: PropagationPlan | None = None
        self._show_propagation: bool = False

        # Connect signals (deferred — need species_key captured per call)
        self._connect_step_signals()

    def _connect_step_signals(self) -> None:
        for step_id, (start_edit, end_edit, reset_btn) in self._step_rows.items():
            # Use default-arg capture to avoid closure issues
            def make_changed_handler(sid: str, se: QDateEdit, ee: QDateEdit | None) -> Any:
                def handler() -> None:
                    if not self._current_species_key or self._current_plan is None:
                        return
                    start_d = se.date().toPyDate()
                    end_d = ee.date().toPyDate() if ee else start_d
                    self.step_date_changed.emit(
                        self._current_species_key, sid,
                        start_d.isoformat(), end_d.isoformat(),
                    )
                return handler

            def make_reset_handler(sid: str) -> Any:
                def handler() -> None:
                    if not self._current_species_key:
                        return
                    self.step_date_reset.emit(self._current_species_key, sid)
                return handler

            start_edit.dateChanged.connect(make_changed_handler(step_id, start_edit, end_edit))
            if end_edit is not None:
                end_edit.dateChanged.connect(make_changed_handler(step_id, start_edit, end_edit))
            reset_btn.clicked.connect(make_reset_handler(step_id))

    # ── public API ─────────────────────────────────────────────────────────────

    def set_show_propagation(self, show: bool) -> None:
        self._show_propagation = show
        self._prop_widget.setVisible(show and self._current_plan is not None)
        # Adjust max height
        if show and self._current_plan is not None:
            self.setMaximumHeight(240)
        else:
            self.setMaximumHeight(90)

    def show_species(
        self,
        sp: PlantSpeciesData,
        species_key: str,
        prop_plan: PropagationPlan | None,
        no_data_text: str = "No detailed data available",
    ) -> None:
        self._current_species_key = species_key
        self._current_plan = prop_plan

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

        # Update propagation editor
        if self._show_propagation and prop_plan is not None:
            self._populate_prop_editor(prop_plan)
            self._prop_widget.show()
            self.setMaximumHeight(240)
        else:
            self._prop_widget.hide()
            self.setMaximumHeight(90)

    def _populate_prop_editor(self, plan: PropagationPlan) -> None:
        """Fill date editors from a PropagationPlan, blocking signals."""
        year = datetime.date.today().year
        for step_id, (start_edit, end_edit, reset_btn) in self._step_rows.items():
            step = plan.get_step(step_id)
            if step is None:
                continue
            start_edit.blockSignals(True)
            # Force year of display date to current year for readability
            s = step.start_date
            try:
                display_s = datetime.date(year, s.month, s.day)
            except ValueError:
                display_s = s
            start_edit.setDate(QDate(display_s.year, display_s.month, display_s.day))
            start_edit.blockSignals(False)

            if end_edit is not None:
                end_edit.blockSignals(True)
                e = step.end_date
                try:
                    display_e = datetime.date(year, e.month, e.day)
                except ValueError:
                    display_e = e
                end_edit.setDate(QDate(display_e.year, display_e.month, display_e.day))
                end_edit.blockSignals(False)

            # Highlight overridden steps
            reset_btn.setEnabled(step.overridden)


# ─── Main view ─────────────────────────────────────────────────────────────────

class PlantingCalendarView(QWidget):
    """Full-screen tab view: planting calendar Gantt chart + today dashboard.

    Reads placed plants from canvas_scene and frost dates from
    project_manager.location to draw a 12-month Gantt chart and a
    "Today's Tasks" dashboard at the top.

    US-9.5 adds propagation sub-rows that show the indoor pre-cultivation
    timeline (germination → prick out → harden off → transplant) for each
    species that is sown indoors.
    """

    #: Emitted when the user clicks "highlight on canvas" for a task.
    highlight_species = pyqtSignal(str)
    #: Emitted after frost alerts are computed: (alert_count, max_severity).
    #: max_severity is "red", "orange", or "" when there are no alerts.
    frost_alert_ready = pyqtSignal(int, str)

    def __init__(self, canvas_scene: Any, project_manager: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canvas_scene = canvas_scene
        self._project_manager = project_manager
        self._rows: list[_PlantRow] = []
        self._prop_plans: dict[str, PropagationPlan] = {}
        self._current_dashboard_tasks: list[_DashboardTask] = []
        self._soil_service: Any | None = None
        self._pest_disease_service: Any | None = None
        self._build_ui()

    def set_soil_service(self, service: Any | None) -> None:
        """Inject the SoilService so the dashboard can show soil mismatch cards (US-12.10d)."""
        self._soil_service = service

    def set_pest_disease_service(self, service: Any | None) -> None:
        """Inject the PestDiseaseService so the dashboard shows active issues (US-12.7)."""
        self._pest_disease_service = service

    # ── construction ───────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Weather forecast widget (US-12.1)
        self._weather = WeatherWidget()
        self._weather.forecast_ready.connect(self._on_weather_ready)
        self._weather.forecast_failed.connect(self._on_weather_failed)
        root.addWidget(self._weather)

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

        # Empty-state label
        self._empty_lbl = QLabel()
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #888; font-size: 13px;")
        self._empty_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._empty_lbl)

        # Detail panel
        self._detail = _DetailPanel()
        self._detail.step_date_changed.connect(self._on_step_date_changed)
        self._detail.step_date_reset.connect(self._on_step_date_reset)
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

        # US-9.5: propagation toggle checkbox
        self._prop_toggle = QCheckBox(self.tr("Show propagation steps"))
        self._prop_toggle.setStyleSheet("font-size: 9pt;")
        self._prop_toggle.setChecked(False)
        self._prop_toggle.toggled.connect(self._on_propagation_toggled)
        layout.addWidget(self._prop_toggle)

        return bar

    # ── data collection ────────────────────────────────────────────────────────

    def _collect_data(
        self,
    ) -> tuple[list[_PlantRow], datetime.date | None, datetime.date | None, dict[str, str]]:
        """Collect unique plant species, frost dates, and seed packet links from current project state."""
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
        seed_links: dict[str, str] = {}  # species_key -> seed_packet_id (first linked wins)
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
            if not any(getattr(species, f) is not None for f in _CALENDAR_FIELDS):
                continue
            key = species.scientific_name or species.common_name
            if key and key not in seen:
                name = species.common_name or species.scientific_name
                seen[key] = _PlantRow(display_name=name, species=species, species_key=key)
            # Collect seed packet link (first one found wins per species)
            if key and key not in seed_links and item.metadata:
                pi = item.metadata.get("plant_instance", {})
                packet_id = pi.get("seed_packet_id")
                if packet_id:
                    seed_links[key] = packet_id

        rows = sorted(seen.values(), key=lambda r: r.display_name.lower())
        return rows, last_frost, first_fall, seed_links

    def _build_propagation_plans(
        self,
        rows: list[_PlantRow],
        last_frost: datetime.date,
        seed_links: dict[str, str] | None = None,
    ) -> dict[str, PropagationPlan]:
        """Build PropagationPlan for each plant that supports pre-cultivation."""
        from open_garden_planner.models.seed_inventory import get_seed_inventory

        overrides = self._project_manager.propagation_overrides
        store = get_seed_inventory()
        plans: dict[str, PropagationPlan] = {}

        for row in rows:
            sp = row.species
            # Only compute for plants that have indoor sowing data
            if sp.indoor_sow_start is None or sp.transplant_start is None:
                continue

            sow_start = last_frost + datetime.timedelta(weeks=sp.indoor_sow_start)
            sow_end = (
                last_frost + datetime.timedelta(weeks=sp.indoor_sow_end)
                if sp.indoor_sow_end is not None
                else sow_start + datetime.timedelta(days=14)
            )
            transplant_date = last_frost + datetime.timedelta(weeks=sp.transplant_start)

            # US-9.6: Use linked seed packet germination data when available
            germ_min = sp.days_to_germination_min
            germ_max = sp.days_to_germination_max
            if seed_links:
                packet_id = seed_links.get(row.species_key)
                if packet_id:
                    packet = store.get(packet_id)
                    if packet:
                        if packet.germination_days_min is not None:
                            germ_min = packet.germination_days_min
                        if packet.germination_days_max is not None:
                            germ_max = packet.germination_days_max

            sp_overrides = overrides.get(row.species_key, {})
            plan = compute_propagation_plan(
                species_key=row.species_key,
                sow_start=sow_start,
                sow_end=sow_end,
                transplant_date=transplant_date,
                germination_days_min=germ_min,
                germination_days_max=germ_max,
                prick_out_after_days=sp.prick_out_after_days,
                harden_off_days=sp.harden_off_days,
                overrides=sp_overrides,
            )
            plans[row.species_key] = plan

        return plans

    # ── refresh ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Rebuild the chart and dashboard from current canvas + project state."""
        # Trigger weather fetch if location is available (US-12.1)
        location = self._project_manager.location if hasattr(self._project_manager, "location") else None
        if location:
            lat = location.get("latitude")
            lon = location.get("longitude")
            if lat is not None and lon is not None:
                self._weather.set_location(float(lat), float(lon))
                self._weather.refresh()
            else:
                self._weather.set_location(None, None)
        else:
            self._weather.set_location(None, None)

        rows, last_frost, first_fall, seed_links = self._collect_data()
        self._rows = rows

        # Build propagation plans (US-9.5 + US-9.6)
        if last_frost is not None and rows:
            self._prop_plans = self._build_propagation_plans(rows, last_frost, seed_links)
        else:
            self._prop_plans = {}

        # Update dashboard (US-8.6 + US-9.5)
        today = datetime.date.today()
        completed_ids: set[str] = set()
        if hasattr(self._project_manager, "task_completions"):
            completed_ids = self._project_manager.task_completions
        if last_frost is not None and rows:
            tasks = _generate_dashboard_tasks(
                rows, last_frost, today, completed_ids,
                prop_plans=self._prop_plans if self._prop_toggle.isChecked() else None,
            )
        else:
            tasks = []
        self._current_dashboard_tasks: list[_DashboardTask] = tasks
        self._dashboard.set_data(tasks)

        # Merge soil mismatch alerts into dashboard (US-12.10d)
        self._inject_soil_mismatch_tasks()
        # Merge active pest/disease issues into dashboard (US-12.7)
        self._inject_pest_disease_tasks()

        # Update Gantt translated marker labels
        self._gantt.label_today = self.tr("Today")
        self._gantt.label_last_frost = self.tr("Last frost")
        self._gantt.label_first_frost = self.tr("First frost")
        self._gantt.label_germination = self.tr("Germination")
        self._gantt.label_prick_out = self.tr("Prick out")
        self._gantt.label_harden_off = self.tr("Harden off")
        self._gantt.label_transplant = self.tr("Transplant")

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
        self._gantt.set_data(rows, year, last_frost, first_fall, self._prop_plans)
        self._scroll.show()

    # ── event handlers ─────────────────────────────────────────────────────────

    def _on_row_clicked(self, row_idx: int) -> None:
        if 0 <= row_idx < len(self._rows):
            row = self._rows[row_idx]
            prop_plan = self._prop_plans.get(row.species_key)
            self._detail.show_species(
                row.species,
                row.species_key,
                prop_plan,
                no_data_text=self.tr("No detailed data available"),
            )
            self._detail.show()
        else:
            self._detail.hide()

    def _on_task_toggled(self, task_id: str, done: bool) -> None:
        """Persist task completion state, then refresh the dashboard.

        ``pest_disease:<target_id>:<record_id>`` tasks are routed to
        ``PestDiseaseService.update_record`` so "Done" resolves the issue
        (sets ``resolved_date``) instead of just toggling a planting-task flag.
        """
        if task_id.startswith("pest_disease:") and self._pest_disease_service is not None:
            _, target_id, record_id = task_id.split(":", 2)
            log = self._pest_disease_service.get_log(target_id)
            for r in log.records:
                if r.id == record_id:
                    if done and r.resolved_date is None:
                        r.resolved_date = datetime.date.today().isoformat()
                    elif not done:
                        r.resolved_date = None
                    self._pest_disease_service.update_record(target_id, r)
                    break
            self.refresh()
            return
        if hasattr(self._project_manager, "set_task_completion"):
            self._project_manager.set_task_completion(task_id, done)
        self.refresh()

    def _on_propagation_toggled(self, checked: bool) -> None:
        """Enable/disable propagation sub-rows in the Gantt and detail panel."""
        self._gantt.set_show_propagation(checked)
        self._detail.set_show_propagation(checked)
        # Refresh dashboard to include/exclude propagation tasks
        self.refresh()

    def _on_step_date_changed(
        self, species_key: str, step_id: str, start_iso: str, end_iso: str
    ) -> None:
        """Persist a user-adjusted propagation step date to the project."""
        if hasattr(self._project_manager, "set_propagation_override"):
            self._project_manager.set_propagation_override(
                species_key, step_id, start_iso, end_iso
            )
        self.refresh()
        # Re-populate detail panel with updated plan
        plan = self._prop_plans.get(species_key)
        if plan is not None and self._detail.isVisible():
            row = next((r for r in self._rows if r.species_key == species_key), None)
            if row:
                self._detail.show_species(
                    row.species, species_key, plan,
                    no_data_text=self.tr("No detailed data available"),
                )

    def _on_step_date_reset(self, species_key: str, step_id: str) -> None:
        """Clear a propagation step override and revert to calculated dates."""
        if hasattr(self._project_manager, "clear_propagation_override"):
            self._project_manager.clear_propagation_override(species_key, step_id)
        self.refresh()
        # Re-populate detail panel
        plan = self._prop_plans.get(species_key)
        if plan is not None and self._detail.isVisible():
            row = next((r for r in self._rows if r.species_key == species_key), None)
            if row:
                self._detail.show_species(
                    row.species, species_key, plan,
                    no_data_text=self.tr("No detailed data available"),
                )

    # ─── Weather widget slots (US-12.1 / US-12.2) ────────────────────

    def _on_weather_ready(self) -> None:
        """Apply frost tinting and inject frost alerts into the dashboard."""
        forecast = self._weather.forecast()
        if forecast is None:
            return
        settings = get_settings()
        orange_c = settings.frost_warning_orange_c
        red_c = settings.frost_warning_red_c
        self._weather.apply_frost_thresholds(orange_c, red_c)
        plants = self._collect_plant_info()
        alerts = get_frost_alerts(forecast, plants, orange_c, red_c)
        self._inject_frost_tasks(alerts)

    def _collect_plant_info(self) -> list[dict]:
        """Return a list of plant info dicts for all plant items on the canvas."""
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items import CircleItem, GardenItemMixin
        result: list[dict] = []
        for item in self._canvas_scene.items():
            if not isinstance(item, CircleItem):
                continue
            if not isinstance(item, GardenItemMixin):
                continue
            if not is_plant_type(item.object_type):
                continue
            name: str = ""
            frost_tolerance: str | None = None
            ps_dict = item.metadata.get("plant_species")
            if ps_dict and isinstance(ps_dict, dict):
                try:
                    species = PlantSpeciesData.from_dict(ps_dict)
                    name = species.common_name or species.scientific_name or ""
                    frost_tolerance = species.frost_tolerance
                except Exception:
                    pass
            if not name:
                name = item.name
            if not name and hasattr(item, "plant_species") and item.plant_species:
                name = item.plant_species.replace("_", " ").title()
            result.append({
                "id": str(item.item_id),
                "name": name or "?",
                "frost_protection_needed": item.frost_protection_needed,
                "frost_tolerance": frost_tolerance,
            })
        return result

    def _inject_frost_tasks(self, alerts: list) -> None:
        """Merge frost alerts into the dashboard task list."""
        today = datetime.date.today()
        frost_tasks: list[_DashboardTask] = []
        for alert in alerts:
            alert_date = datetime.date.fromisoformat(alert.date)
            urgency = _classify_urgency(alert_date, alert_date, today)
            if urgency is None:
                continue
            plant_names = self._names_for_ids(alert.affected_plant_ids)
            temp_str = QLocale().toString(float(alert.min_temp), "f", 1)
            display = f"{temp_str}°C — {', '.join(plant_names)}"
            task_type = "frost_alert_red" if alert.severity == "red" else "frost_alert_orange"
            species_key = "frost_items:" + ",".join(alert.affected_plant_ids)
            frost_tasks.append(
                _DashboardTask(
                    task_id=f"frost:{alert.date}:{alert.severity}",
                    task_type=task_type,
                    display_name=display,
                    task_date=alert_date,
                    end_date=alert_date,
                    urgency=urgency,
                    species_key=species_key,
                )
            )
        self._dashboard.set_data(self._current_dashboard_tasks + frost_tasks)
        max_severity = ""
        if any(t.task_type == "frost_alert_red" for t in frost_tasks):
            max_severity = "red"
        elif frost_tasks:
            max_severity = "orange"
        self.frost_alert_ready.emit(len(frost_tasks), max_severity)

    def _names_for_ids(self, item_ids: list[str]) -> list[str]:
        """Return plant names for the given item IDs."""
        from open_garden_planner.ui.canvas.items import GardenItemMixin
        id_set = set(item_ids)
        names: list[str] = []
        for item in self._canvas_scene.items():
            if not isinstance(item, GardenItemMixin) or str(item.item_id) not in id_set:
                continue
            name: str = ""
            ps_dict = item.metadata.get("plant_species")
            if ps_dict and isinstance(ps_dict, dict):
                try:
                    species = PlantSpeciesData.from_dict(ps_dict)
                    name = species.common_name or species.scientific_name or ""
                except Exception:
                    pass
            if not name:
                name = item.name
            if not name and hasattr(item, "plant_species") and item.plant_species:
                name = item.plant_species.replace("_", " ").title()
            names.append(name or "?")
        return names

    def _inject_soil_mismatch_tasks(self) -> None:
        """Merge soil mismatch alerts into the dashboard task list (US-12.10d)."""
        if self._soil_service is None:
            return
        from open_garden_planner.core.object_types import is_bed_type
        from open_garden_planner.models.plant_data import PlantSpeciesData
        from open_garden_planner.services.soil_service import SoilService
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        today = datetime.date.today()
        soil_tasks: list[_DashboardTask] = []
        all_items = list(self._canvas_scene.items())
        for item in all_items:
            if not isinstance(item, GardenItemMixin):
                continue
            if not is_bed_type(getattr(item, "object_type", None)):
                continue
            bed_id = str(getattr(item, "item_id", ""))
            record = self._soil_service.get_effective_record(bed_id)
            child_ids = {str(c) for c in getattr(item, "_child_item_ids", [])}
            specs: list[PlantSpeciesData] = []
            for child in all_items:
                if str(getattr(child, "item_id", "")) not in child_ids:
                    continue
                ps_dict = getattr(child, "metadata", {}).get("plant_species")
                if ps_dict and isinstance(ps_dict, dict):
                    with contextlib.suppress(Exception):
                        specs.append(PlantSpeciesData.from_dict(ps_dict))
            mismatches = SoilService.get_mismatched_plants(record, specs)
            if not mismatches:
                continue
            bed_name = str(getattr(item, "name", "") or self.tr("Bed"))
            plant_names = ", ".join(
                s.common_name or s.scientific_name or "?" for s, _ in mismatches
            )
            display = self.tr("Soil mismatch in {bed}: {plants}").format(
                bed=bed_name, plants=plant_names
            )
            soil_tasks.append(
                _DashboardTask(
                    task_id=f"soil_mismatch:{bed_id}",
                    task_type="soil_mismatch",
                    display_name=display,
                    task_date=today,
                    end_date=today,
                    urgency="today",
                    species_key="",
                )
            )
        if soil_tasks:
            self._current_dashboard_tasks = self._current_dashboard_tasks + soil_tasks
            self._dashboard.set_data(self._current_dashboard_tasks)

    def _inject_pest_disease_tasks(self) -> None:
        """Merge active pest/disease issues into the dashboard task list (US-12.7)."""
        if self._pest_disease_service is None:
            return
        from open_garden_planner.core.object_types import is_bed_type, is_plant_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        today = datetime.date.today()
        # Map target_id → display name by scanning the scene once.
        names: dict[str, str] = {}
        for item in self._canvas_scene.items():
            if not isinstance(item, GardenItemMixin):
                continue
            object_type = getattr(item, "object_type", None)
            if not (is_bed_type(object_type) or is_plant_type(object_type)):
                continue
            tid = str(getattr(item, "item_id", ""))
            if tid:
                names[tid] = str(getattr(item, "name", "") or self.tr("Item"))

        pest_tasks: list[_DashboardTask] = []
        for target_id, record in self._pest_disease_service.get_active_issues():
            display_name = names.get(target_id, self.tr("Unknown"))
            kind_label = (
                self.tr("Pest") if record.kind == "pest" else self.tr("Disease")
            )
            display = self.tr("{kind} on {target}: {name}").format(
                kind=kind_label, target=display_name, name=record.name
            )
            urgency = {
                "high": "today",
                "medium": "this_week",
                "low": "coming_up",
            }.get(record.severity, "this_week")
            pest_tasks.append(
                _DashboardTask(
                    task_id=f"pest_disease:{target_id}:{record.id}",
                    task_type="pest_disease",
                    display_name=display,
                    task_date=today,
                    end_date=today,
                    urgency=urgency,
                    species_key="",
                )
            )
        if pest_tasks:
            self._current_dashboard_tasks = self._current_dashboard_tasks + pest_tasks
            self._dashboard.set_data(self._current_dashboard_tasks)

    def _on_weather_failed(self, message: str) -> None:
        """Weather forecast fetch failed — no frost alerts shown."""
