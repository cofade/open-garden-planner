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

import datetime
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QDate, QLocale, QPoint, QRect, Qt, QTimer, pyqtSignal
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
from open_garden_planner.core.frost_dates import parse_frost
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.models.plant_data import species_key as _species_key
from open_garden_planner.models.propagation import PropagationPlan
from open_garden_planner.services.task_generator import (
    PlanState,
    Task,
    build_plan_state,
    classify_urgency,
    frost_anchor_years,
    generate_actionable_for_surface,
    generate_for_date_window,
    propagate_plans_by_anchor,
)
from open_garden_planner.services.task_status import effective_status
from open_garden_planner.services.weather_service import get_frost_alerts
from open_garden_planner.ui.icons import get_icon, get_pixmap
from open_garden_planner.ui.theme import URGENCY_TOKENS, set_text_role, theme_qcolor, urgency_dot
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


def _urgency_qcolor(urgency: str) -> QColor:
    """Semantic color for a dashboard urgency — the ONE shared map in
    theme.py (same map as the Tasks tab, #228 convergence), pairwise
    distinct in both palettes (pinned by test_theme_tokens)."""
    return theme_qcolor(URGENCY_TOKENS.get(urgency, "text_disabled"))

# All task types including propagation steps
_PROP_TASK_TYPES = ("prick_out", "harden_off")

# Refresh debounce — coalesce edit/undo bursts and skip work while the tab is
# hidden (refresh() is heavyweight, #210/#225). Mirrors the Tasks tab pattern.
_REFRESH_DEBOUNCE_MS = 250

# Propagation step date editors commit their override after the user pauses for
# this long, or immediately on focus-out — whichever comes first. Mirrors
# properties_panel._TEXT_COMMIT_DEBOUNCE_MS (#210): the editor used to write on
# every ``dateChanged``, so stepping through dates with the arrow keys wrote an
# override per step and ran the calendar's full refresh() each time (one user
# gesture is not one undo step — invariant 4). The debounce (rather than
# focus-out only) is what lets Ctrl+Z work while the editor still has focus,
# and it also means a date picked from the calendar popup is never lost.
_STEP_COMMIT_DEBOUNCE_MS = 600


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


@dataclass(frozen=True)
class _GanttWindow:
    """One calendar window to draw, already clipped to the displayed year.

    Produced by the shared task generators rather than recomputed in the widget
    (#414), so the chart shows exactly what the dashboard and the agent list.
    """

    start: datetime.date
    end: datetime.date
    task_type: str


@dataclass(frozen=True)
class _PropStepWindow:
    """One propagation step to draw, already clipped to the displayed year."""

    start: datetime.date
    end: datetime.date
    step_id: str
    anchor_year: int


#: Which Gantt bar colour each generated calendar task type is drawn in.
#: Also the set of task types the chart draws at all — a generated type missing
#: here is a task the dashboard lists and the chart silently omits.
_GANTT_COLORS: dict[str, QColor] = {
    "indoor_sow": _COL_INDOOR,
    "direct_sow": _COL_DIRECT,
    "transplant": _COL_TRANSPL,
    "harvest": _COL_HARVEST,
}


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
    """Deprecated shim — use the shared frost-date rule (#414).

    This was a SECOND independent parser; a third copy lived in the location
    dialog's regex. All three now go through
    :mod:`open_garden_planner.core.frost_dates`, which also owns the
    29-February-in-a-non-leap-year substitution. Kept as a module-level alias so
    existing importers keep working.
    """
    return parse_frost(mmdd, year)


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
        set_text_role(self._title_lbl, "h2")
        header_layout.addWidget(self._title_lbl)
        header_layout.addStretch()
        self._toggle_btn = QPushButton()
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setFixedSize(24, 22)
        self._toggle_btn.setToolTip(self.tr("Collapse/expand"))
        self._set_toggle_icon()
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
        set_text_role(self._empty_lbl, "hint")
        self._empty_lbl.setStyleSheet("padding: 6px 12px;")
        self._empty_lbl.hide()
        outer.addWidget(self._empty_lbl)

    def _set_toggle_icon(self) -> None:
        icon = get_icon("chevron_right" if self._collapsed else "chevron_down")
        if icon is not None:
            self._toggle_btn.setIcon(icon)

    def refresh_theme_icons(self) -> None:
        """Theme-switch hook: re-tint the collapse chevron (#310)."""
        self._set_toggle_icon()

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._content_scroll.setVisible(not self._collapsed)
        self._empty_lbl.setVisible(
            not self._collapsed and not self._content_scroll.isVisibleTo(self)
            and self._empty_lbl.text() != ""
        )
        self._set_toggle_icon()

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
        # Templates substitute the task's display_name into %1. Types not listed
        # (succession_sow/clear, soil_mismatch, soil_amendment, manual) fall
        # through to "%1" — their display_name is already a complete label.
        task_templates = {
            "indoor_sow":         self.tr("Start indoor sowing of %1"),
            "direct_sow":         self.tr("Direct sow %1"),
            "transplant":         self.tr("Transplant %1 outdoors"),
            "harvest":            self.tr("Harvest %1"),
            "prick_out":          self.tr("Prick out %1 seedlings"),
            "harden_off":         self.tr("Start hardening off %1"),
            "frost_alert_orange": "%1",  # marker = row icon (#310)
            "frost_alert_red":    "%1",
        }

        for urgency in _URGENCY_ORDER:
            group = grouped[urgency]
            if not group:
                continue
            color = _urgency_qcolor(urgency)

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

        dot = QLabel()
        dot.setFixedSize(14, 14)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if task.task_type == "frost_alert_red":
            marker = get_pixmap("frost", 12, color=color.name())
        elif task.task_type == "frost_alert_orange":
            marker = get_pixmap("warning", 12, color=color.name())
        else:
            marker = urgency_dot(color)  # painted themed marker (was "●")
        if marker is not None:
            dot.setPixmap(marker)
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

        goto_btn = QPushButton()
        goto_icon = get_icon("go_to")
        if goto_icon is not None:
            goto_btn.setIcon(goto_icon)
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
        windows: dict[str, list[_GanttWindow]] | None = None,
        prop_steps: dict[str, list[_PropStepWindow]] | None = None,
    ) -> None:
        """Set the rows and the already-computed windows to draw for ``year``.

        ``windows`` / ``prop_steps`` are produced by the shared generators (see
        ``PlantingCalendarView._compute_gantt_windows``). The widget used to
        recompute every window itself from ``self._last_frost`` plus the species
        week-offsets, which made it the SECOND independent implementation of "offset to date"
        -- the agent's `generate_for_date_window` and the dashboard's `generate_all` both *call* `generate_calendar_tasks` rather than reimplementing it, so the generator itself is the first implementation and the Gantt's re-derivation the second; the old count included the callers -- and the reason a window anchored on another year's frost
        could not be drawn: only the current year's anchor existed here (#414).
        Drawing what the generators produced is what makes the chart and the
        dashboard agree by construction.
        """
        self._rows = rows
        self._year = year
        self._last_frost = last_frost
        self._first_fall = first_fall
        self._windows = windows or {}
        self._prop_steps = prop_steps or {}
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
            self._paint_bars(painter, row, y)

            # Propagation sub-row
            if self._show_propagation:
                self._paint_prop_row(painter, row, i, y + _ROW_H)

    def _paint_bars(self, painter: QPainter, row: _PlantRow, row_y: int) -> None:
        """Draw the calendar windows the generators produced for this species.

        The windows arrive already clipped to the displayed year, from whichever
        frost anchor years reach into it (#414) — so a window anchored on the
        PREVIOUS year's frost still draws its January part, and one anchored on
        next year's draws its December part.
        """
        bar_y = row_y + _BAR_MARGIN
        bar_h = _ROW_H - 2 * _BAR_MARGIN
        year = self._year

        for window in self._windows.get(row.species_key, ()):
            color = _GANTT_COLORS.get(window.task_type, _COL_DIRECT)
            x1 = _date_to_x(window.start.month, window.start.day, year)
            x2 = _date_to_x(window.end.month, window.end.day, year)
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
        # sub-row marker: a small provider chevron (was a "↳" text glyph, #310)
        chevron = get_pixmap("chevron_right", 10)
        if chevron is not None:
            painter.drawPixmap(14, sub_y + (_PROP_ROW_H - 10) // 2, chevron)
        painter.drawText(
            QRect(26, sub_y, _NAME_W - 32, _PROP_ROW_H),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.tr("Propagation"),
        )

        if not self._prop_steps.get(row.species_key):
            return

        year = self._year
        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)
        bar_top = sub_y + _PROP_BAR_Y
        bar_h = _PROP_BAR_H

        # Paint each propagation step, from EVERY anchor year whose plan reaches
        # into the displayed year (#414). Before this the sub-row could only draw
        # the plan anchored on the current year's frost, so a tomato-only plan
        # showed neither the indoor sowing (20 Nov - 4 Dec) nor the prick-out of
        # the plan anchored on next year's frost.
        step_styles = [
            ("germination",  _COL_GERM,            False),  # period bar
            ("harden_off",   _COL_HARDEN,           False),  # period bar
            ("prick_out",    _COL_PRICK,            True),   # point marker
            ("transplant",   _COL_TRANSPLANT_PROP,  True),   # point marker
        ]

        windows = self._prop_steps.get(row.species_key, ())
        by_step: dict[str, list[_PropStepWindow]] = {}
        for window in windows:
            by_step.setdefault(window.step_id, []).append(window)

        painter.setPen(Qt.PenStyle.NoPen)
        for step_id, color, is_point in step_styles:
            for step_window in by_step.get(step_id, ()):
                d_start = max(step_window.start, year_start)
                d_end = min(step_window.end, year_end)
                x1 = _date_to_x(d_start.month, d_start.day, year)
                x2 = _date_to_x(d_end.month, d_end.day, year)

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

    #: Emitted once per gesture with every committed step date.
    #: ``(species_key, [(step_id, start_iso, end_iso), ...])`` — BATCHED, because
    #: the receiving slot runs a full calendar refresh (and a weather fetch), so
    #: emitting per step made one user gesture cost N heavyweight refreshes.
    steps_date_changed = pyqtSignal(object)
    #: Emitted when the user resets a step override.
    #: (species_key, step_id)
    step_date_reset = pyqtSignal(str, str)
    #: (species_key, step_id) — the edit was refused and nothing was stored.
    step_date_rejected = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        self._name_lbl = QLabel()
        set_text_role(self._name_lbl, "h2")
        self._info_lbl = QLabel()
        self._info_lbl.setWordWrap(True)
        self._info_lbl.setStyleSheet("font-size: 9pt;")
        layout.addWidget(self._name_lbl)
        layout.addWidget(self._info_lbl)

        # Propagation step editor (shown when propagation mode is enabled)
        self._prop_widget = QWidget()
        prop_layout = QVBoxLayout(self._prop_widget)
        prop_layout.setContentsMargins(0, 4, 0, 0)
        prop_layout.setSpacing(2)

        hdr = QLabel(self.tr("Propagation Steps"))
        set_text_role(hdr, "small", "secondary")
        hdr.setStyleSheet("font-weight: 600;")
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

            reset_btn = QPushButton()  # provider refresh icon (was "↺", #310)
            reset_icon = get_icon("refresh")
            if reset_icon is not None:
                reset_btn.setIcon(reset_icon)
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

    def refresh_theme_icons(self) -> None:
        """Theme-switch hook: re-tint the per-step reset buttons (#310)."""
        icon = get_icon("refresh")
        if icon is None:
            return
        for _start, _end, reset_btn in self._step_rows.values():
            reset_btn.setIcon(icon)

    def _connect_step_signals(self) -> None:
        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(_STEP_COMMIT_DEBOUNCE_MS)
        self._commit_timer.timeout.connect(self._flush_pending_steps)
        #: ``step_id -> (species_key, start_iso, end_iso)``, captured when the edit
        #: was ARMED. Both the species AND the values are captured, never read at
        #: flush time: the flush can run after the panel has been pointed at a
        #: different plant (so the species key would be wrong), and the commit slot
        #: calls ``refresh()`` which rewrites the editors (so the values would be
        #: wrong). See :meth:`_flush_pending_steps` for the defects this shape
        #: prevents.
        self._pending_steps: dict[str, tuple[str, str, str]] = {}

        for step_id, (start_edit, end_edit, reset_btn) in self._step_rows.items():
            # Use default-arg capture to avoid closure issues
            def make_changed_handler(sid: str) -> Any:
                def handler() -> None:
                    # The ONLY place an edit is armed. `dateChanged` fires on a
                    # real user change, so arming here is what keeps a tab-through
                    # that touches nothing from committing anything.
                    if not self._current_species_key:
                        return
                    row = self._step_rows.get(sid)
                    if row is None:
                        return
                    row_start, row_end, _reset = row
                    start_d = row_start.date().toPyDate()
                    end_d = row_end.date().toPyDate() if row_end is not None else start_d
                    self._pending_steps[sid] = (
                        self._current_species_key, start_d.isoformat(), end_d.isoformat(),
                    )
                    self._commit_timer.start()
                return handler

            def make_commit_handler(sid: str) -> Any:
                # Focus-out commits immediately so the override is stored (and the
                # plan rebuilt) as soon as the user leaves the field -- but ONLY
                # what `dateChanged` already armed.
                #
                # `editingFinished` fires on EVERY focus-out, including a
                # tab-through that changed nothing. Arming here wrote an override
                # for every step the user's focus merely passed, which silently
                # froze the propagation dates so they stopped following the frost
                # date (#415 round-4 review). It looks like a harmless no-op and
                # is a data change.
                def handler() -> None:
                    if sid in self._pending_steps:
                        self._flush_pending_steps()
                return handler

            def make_reset_handler(sid: str) -> Any:
                def handler() -> None:
                    if not self._current_species_key:
                        return
                    self._pending_steps.pop(sid, None)
                    # Only stop the debounce if nothing else is armed: resetting
                    # one step must not strand a sibling edit that is waiting on
                    # the timer (#415 round-4 review).
                    if not self._pending_steps:
                        self._commit_timer.stop()
                    self.step_date_reset.emit(self._current_species_key, sid)
                return handler

            start_edit.dateChanged.connect(make_changed_handler(step_id))
            start_edit.editingFinished.connect(make_commit_handler(step_id))
            if end_edit is not None:
                end_edit.dateChanged.connect(make_changed_handler(step_id))
                end_edit.editingFinished.connect(make_commit_handler(step_id))
            reset_btn.clicked.connect(make_reset_handler(step_id))

    def _flush_pending_steps(self) -> None:
        """Commit every armed step's override, in ONE batch, then clear.

        Everything this needs is in ``_pending_steps``; the editors are NEVER
        read here. Five defects that shape came from, each of which was shipped:

        * **A dict, not a single slot.** Correcting a step's start and then its end
          arms two steps; one slot kept only the last and the first was dropped.
        * **The species key is captured at ARM time.** The flush runs from
          ``show_species``, which had already reassigned
          ``_current_species_key`` — so an armed edit was persisted against the
          species the user had just clicked *onto*. Silent cross-species
          corruption in the ``.ogp``.
        * **The values are captured at ARM time too.** The commit slot calls
          ``refresh()``, which reaches back into ``_populate_prop_editor` and
          rewrites the editors, so reading them here persisted values the user
          never entered — or dropped the edit outright, for every step after the
          first.
        * **Nothing is armed without a `dateChanged`.** Arming on ``editingFinished``
          wrote an override for every step a tab-through merely passed, silently
          freezing the propagation dates.
        * **One emit per species, not per step.** The slot runs a full calendar
          refresh and a weather fetch, so N emits cost N heavyweight refreshes.

        An inverted pair (the user moved a start past its end) is REFUSED and
        reported, never silently rewritten: clamping to a zero-length period
        persisted an end date the user never entered.

        Only armed entries are considered, so a flush triggered by an unrelated
        refresh is a no-op by construction — there is nothing to accidentally
        write.
        """
        armed = dict(self._pending_steps)
        self._commit_timer.stop()
        if not armed:
            return
        # Every armed entry is accounted for below (written or rejected), so the
        # clear is safe here and only here.
        self._pending_steps.clear()

        writes_by_species: dict[str, list[tuple[str, str, str]]] = {}
        rejected: list[tuple[str, str]] = []
        for step_id, (species_key, start_iso, end_iso) in sorted(armed.items()):
            if not species_key:
                continue
            if end_iso < start_iso:   # ISO dates sort chronologically
                rejected.append((species_key, step_id))
                continue
            writes_by_species.setdefault(species_key, []).append(
                (step_id, start_iso, end_iso)
            )

        for species_key, step_id in rejected:
            self.step_date_rejected.emit(species_key, step_id)
        # One emit per species, so a gesture touching two plants refreshes once
        # each rather than once per step.
        for species_key, writes in writes_by_species.items():
            self.steps_date_changed.emit((species_key, writes))

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
        # Commit any armed edit BEFORE pointing the panel at another plant. The
        # Gantt has Qt::NoFocus, so clicking another chart row fires no
        # `editingFinished` to commit implicitly — without this the edit would be
        # stranded by the populate below and lost.
        #
        # This DOES re-enter `show_species` (`steps_date_changed` → the view slot
        # → `_repopulate_detail` → `show_species`), and the outer call's correctness
        # rests on TWO load-bearing orderings:
        #   1. the flush clears `_pending_steps` BEFORE it emits, so the inner
        #      `show_species` finds nothing to flush and does not recurse; and
        #   2. the two lines below run AFTER the flush returns, so they overwrite
        #      whatever the inner call set — which is the species the user wants.
        # Reversing either reintroduces a cross-species misattribution, so
        # `test_show_species_reassigns_after_the_flush` pins it.
        self._flush_pending_steps()
        self._current_species_key = species_key
        self._current_plan = prop_plan

        name = sp.common_name or sp.scientific_name
        sci = f" ({sp.scientific_name})" if sp.scientific_name and sp.scientific_name != name else ""
        self._name_lbl.setText(f"{name}{sci}")
        parts: list[str] = []
        if sp.days_to_germination_min is not None:
            parts.append(self.tr("Germination: {min}–{max} days").format(
                min=sp.days_to_germination_min, max=sp.days_to_germination_max))
        if sp.min_germination_temp_c is not None:
            parts.append(self.tr("Min. germ. temp: {temp} °C").format(temp=sp.min_germination_temp_c))
        if sp.seed_depth_cm is not None:
            parts.append(self.tr("Seed depth: {depth} cm").format(depth=sp.seed_depth_cm))
        if sp.frost_tolerance:
            parts.append(self.tr("Frost tolerance: {level}").format(
                level=self._frost_tolerance_text(sp.frost_tolerance)))
        if sp.days_to_maturity_min is not None:
            parts.append(self.tr("Maturity: {min}–{max} days").format(
                min=sp.days_to_maturity_min, max=sp.days_to_maturity_max))
        self._info_lbl.setText("  ·  ".join(parts) if parts else no_data_text)

        # Update propagation editor
        if self._show_propagation and prop_plan is not None:
            self._populate_prop_editor(prop_plan)
            self._prop_widget.show()
            self.setMaximumHeight(240)
        else:
            self._prop_widget.hide()
            self.setMaximumHeight(90)

    def _frost_tolerance_text(self, token: str) -> str:
        """Translated label for a species' raw frost-tolerance data token.

        The data files store an English token (``hardy`` / ``half-hardy`` /
        ``tender``); #415 found the detail line printing that token verbatim, so
        the German UI showed English words inline. Unknown tokens fall back to
        the raw value rather than being hidden.
        """
        labels = {
            "hardy": self.tr("hardy"),
            "half-hardy": self.tr("half-hardy"),
            "tender": self.tr("tender"),
        }
        return labels.get(token, token)

    def _populate_prop_editor(self, plan: PropagationPlan) -> None:
        """Fill date editors from a PropagationPlan, blocking signals.

        Each step is shown with its REAL dates (#415). This used to force the
        displayed year to the current year "for readability", with the start and
        the end moved independently, so a step that crossed New Year was stored
        inverted into the .ogp (start 2026-12-24 / end 2026-01-22) and a step in
        another calendar year silently moved. The editors' display format is
        "dd MMM" (no year), so the real dates read the same as before while an
        edit can no longer change a year the user did not touch.
        """
        # show_species already flushed any armed edit before swapping the plan, so
        # there is nothing pending here. Clearing defensively would risk the very
        # silent-discard this path used to cause, so it is deliberately absent.
        for step_id, (start_edit, end_edit, reset_btn) in self._step_rows.items():
            step = plan.get_step(step_id)
            if step is None:
                continue
            start_edit.blockSignals(True)
            start_edit.setDate(QDate(step.start_date.year, step.start_date.month, step.start_date.day))
            start_edit.blockSignals(False)

            if end_edit is not None:
                end_edit.blockSignals(True)
                end_edit.setDate(QDate(step.end_date.year, step.end_date.month, step.end_date.day))
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
    #: Emitted with the full ``list[FrostAlert]`` after each weather fetch, so
    #: the US-C2 Tasks tab can reuse this single forecast (no second fetch).
    frost_alerts_ready = pyqtSignal(object)

    def __init__(self, canvas_scene: Any, project_manager: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canvas_scene = canvas_scene
        self._project_manager = project_manager
        #: Latest frost alerts from the most recent weather fetch (US-C2).
        self._current_frost_alerts: list = []
        self._rows: list[_PlantRow] = []
        self._prop_plans: dict[str, PropagationPlan] = {}
        self._current_dashboard_tasks: list[_DashboardTask] = []
        #: The snapshot the dashboard and the Gantt are both derived from, so the
        #: two cannot disagree about which frost anchor years exist (#414).
        self._plan_state: PlanState | None = None
        self._soil_service: Any | None = None
        # Debounced refresh so the view can be wired to stack_changed (undo/redo)
        # without heavyweight churn; skips work while the tab is hidden (#225).
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)
        self._build_ui()

    def set_soil_service(self, service: Any | None) -> None:
        """Inject the SoilService so the dashboard can show soil mismatch cards (US-12.10d)."""
        self._soil_service = service

    def schedule_refresh(self) -> None:
        """Coalesce refresh requests (debounced) — safe to wire to stack_changed."""
        self._refresh_timer.start()

    def _on_refresh_timer(self) -> None:
        """Debounced refresh — skip the heavy rebuild while the tab is hidden
        (``_on_tab_changed`` refreshes the view when it next becomes visible)."""
        if not self.isVisible():
            return
        self.refresh()

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
        set_text_role(self._empty_lbl, color_role="secondary")
        self._empty_lbl.setStyleSheet("font-size: 13px;")
        self._empty_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._empty_lbl)

        # Detail panel
        self._detail = _DetailPanel()
        self._detail.steps_date_changed.connect(self._on_steps_date_changed)
        self._detail.step_date_rejected.connect(self._on_step_date_rejected)
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
            key = _species_key({"source_id": species.source_id, "scientific_name": species.scientific_name, "common_name": species.common_name})
            if key != "_unknown" and key not in seen:
                name = species.common_name or species.scientific_name
                seen[key] = _PlantRow(display_name=name, species=species, species_key=key)
            # Collect seed packet link (first one found wins per species)
            if key != "_unknown" and key not in seed_links and item.metadata:
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
        from open_garden_planner.services.task_generator import build_propagation_plans

        store = get_seed_inventory()
        packets = {key: store.get(packet_id) for key, packet_id in (seed_links or {}).items()}
        return build_propagation_plans(
            {row.species_key: row.species for row in rows}, last_frost,
            self._project_manager.propagation_overrides, packets,
        )

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

        # Build propagation plans (US-9.5 + US-9.6). The EDITABLE plan stays the
        # one anchored on the current year's frost (#414); the other anchors are
        # drawn on the chart and listed by the dashboard/agent, but not edited,
        # because the detail panel edits exactly one plan per species.
        if last_frost is not None and rows:
            self._prop_plans = self._build_propagation_plans(rows, last_frost, seed_links)
        else:
            self._prop_plans = {}

        # Update dashboard via the single unified engine (#228). This also
        # refreshes self._plan_state, which the Gantt windows are derived from.
        self._rebuild_dashboard()

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
        year = datetime.date.today().year
        windows, prop_steps = self._compute_gantt_windows(year)
        self._gantt.set_data(rows, year, last_frost, first_fall, windows, prop_steps)
        self._scroll.show()

    def _compute_gantt_windows(
        self, year: int,
    ) -> tuple[dict[str, list[_GanttWindow]], dict[str, list[_PropStepWindow]]]:
        """Windows for the chart, produced by the shared generators (#414).

        The Gantt used to recompute every window from the current year's frost
        plus the species week-offsets, so it drew exactly one anchor year. Here
        the chart asks the shared engine for everything overlapping ``year`` —
        including windows anchored on the previous or next year's frost, which
        is what makes a tomato harvest running into February finally visible in
        January.
        """
        windows: dict[str, list[_GanttWindow]] = {}
        prop_steps: dict[str, list[_PropStepWindow]] = {}
        state = self._plan_state
        if state is None or state.last_frost is None:
            return windows, prop_steps

        year_start = datetime.date(year, 1, 1)
        year_end = datetime.date(year, 12, 31)

        # actionable_only=False: the chart draws the whole displayed year, which is
        # not an urgency window. Leaving the dashboard's True in place would drop
        # every window that is not urgent *today* — i.e. most of the chart.
        from dataclasses import replace  # noqa: PLC0415

        for task in generate_for_date_window(
            replace(state, actionable_only=False), year_start, year_end
        ):
            if task.source != "calendar" or not task.species_key:
                continue
            if task.start_date is None or task.end_date is None:
                continue
            if task.task_type not in _GANTT_COLORS:
                continue
            windows.setdefault(task.species_key, []).append(_GanttWindow(
                start=max(task.start_date, year_start),
                end=min(task.end_date, year_end),
                task_type=task.task_type,
            ))

        if not self._prop_toggle.isChecked():
            return windows, prop_steps

        # Propagation steps, per anchor year, from the same shared calculator.
        for (species_key, anchor_year), plan in propagate_plans_by_anchor(
            state, frost_anchor_years(state, year_start, year_end)
        ).items():
            for step in plan.steps:
                if step.end_date < year_start or step.start_date > year_end:
                    continue
                prop_steps.setdefault(species_key, []).append(_PropStepWindow(
                    start=max(step.start_date, year_start),
                    end=min(step.end_date, year_end),
                    step_id=step.step_id,
                    anchor_year=anchor_year,
                ))

        for values in windows.values():
            values.sort(key=lambda w: (w.start, w.task_type))
        for values in prop_steps.values():
            values.sort(key=lambda w: (w.start, w.anchor_year, w.step_id))
        return windows, prop_steps

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
        """Persist task completion, then rebuild only the dashboard.

        Rebuild the dashboard (not a full ``refresh()``) so toggling Done doesn't
        kick off a redundant weather fetch; the resulting ``task_states_changed``
        already schedules a (debounced) full refresh in the app.
        """
        if hasattr(self._project_manager, "set_task_completion"):
            self._project_manager.set_task_completion(task_id, done)
        self._rebuild_dashboard()

    def _on_propagation_toggled(self, checked: bool) -> None:
        """Enable/disable propagation sub-rows in the Gantt and detail panel."""
        self._gantt.set_show_propagation(checked)
        self._detail.set_show_propagation(checked)
        # Refresh dashboard to include/exclude propagation tasks
        self.refresh()

    def _on_steps_date_changed(self, payload: object) -> None:
        """Persist a whole gesture's step dates, then refresh ONCE.

        ``payload`` is ``(species_key, [(step_id, start_iso, end_iso), ...])``.
        Batched because this slot runs a full calendar refresh — which walks the
        scene, rebuilds the dashboard and re-fetches the weather — and emitting
        per step made a single user gesture cost N of those (invariant 4).

        The species key comes from the panel and is the one captured when the
        edit was ARMED, not whatever the panel is showing now (#415).

        The batch is ALL-OR-NOTHING: every step is validated before any is written,
        so a refusal cannot leave half a gesture applied while the message says a
        step "was not changed". A ``False`` return from the writer is honoured
        rather than discarded. Both checks are unreachable today — the panel filters
        inverted pairs first — and both are written anyway, because the alternative
        is two layers that agree by coincidence.
        """
        species_key, writes = payload            # type: ignore[misc]

        # ALL-OR-NOTHING. The loop below writes as it goes, so a batch whose second
        # step was refused would leave the first stored and then `return` without a
        # refresh — telling the user one step "was not changed" while another was,
        # which is a worse lie than either outcome alone. So every step is checked
        # FIRST and nothing is written until the whole batch is known good.
        #
        # This is unreachable today: the panel filters inverted pairs before
        # emitting and its ISO strings always parse. It is written anyway for the
        # same reason the writer returns a bool — the alternative is two layers
        # agreeing by coincidence, which is the shape of the original status-route
        # P0 (a guard that looked like a check and was not one).
        def _parses(value: str) -> bool:
            try:
                datetime.date.fromisoformat(value)
            except (TypeError, ValueError):
                return False
            return True

        invalid = [
            step_id
            for step_id, start_iso, end_iso in writes
            if not (_parses(start_iso) and _parses(end_iso)) or end_iso < start_iso
        ]
        if invalid:
            self.step_date_rejected.emit(species_key, invalid[0])
            return

        refused: list[str] = []
        for step_id, start_iso, end_iso in writes:
            if not self._project_manager.set_propagation_override(
                species_key, step_id, start_iso, end_iso
            ):
                refused.append(step_id)
        if refused:
            # The panel filters inverted pairs before emitting, so this should be
            # unreachable. Checking it anyway is the point: `set_propagation_override`
            # returns bool *so that a refusal is observable*, and its only production
            # caller used to discard the value — leaving two layers that agreed by
            # coincidence rather than by construction. If they ever disagree, the
            # user is told instead of a step silently keeping its calculated dates.
            # (Round 7 raised this; the same "silent no-op that looks like a
            # successful edit" shape as the status-message route, one layer up.)
            self.step_date_rejected.emit(species_key, refused[0])
            return
        self.refresh()
        self._repopulate_detail(species_key)

    def _on_step_date_rejected(self, species_key: str, step_id: str) -> None:   # noqa: ARG002
        """Tell the user their dates were refused, and show the real state.

        The end date preceding the start is the one input the model cannot hold
        (#415). Silently clamping it persisted a value the user never entered, and
        silently refusing looked like a lost edit; a status message plus a
        re-populate makes both the refusal and the actual stored dates visible.
        """
        message = self.tr(
            "The end date of a propagation step cannot be before its start "
            "date — the step was not changed."
        )
        # The calendar tab emits its own signal rather than reaching for the canvas.
        # `CanvasView.set_status_message` now works (it emits a signal — see its
        # docstring) and the tab shares the same `CanvasScene` as the canvas, so the
        # canvas route was *reachable*; it is the wrong owner either way — a tab
        # message should come from the tab, and routing it through the canvas
        # couples this refusal to whichever canvas view happens to be attached.
        # (An earlier version justified this by claiming the canvas is not in this
        # tab's scene. Round 6 measured that claim false: the scene IS shared.)
        self.status_message.emit(message)
        self._repopulate_detail(species_key)

    def _repopulate_detail(self, species_key: str) -> None:
        """Re-point the detail panel at a species' freshly rebuilt plan.

        Unconditional on visibility: the panel's content must show what is
        actually stored even when the tab is hidden, or a refused edit keeps
        displaying the date the user typed as though it had been saved.
        """
        plan = self._prop_plans.get(species_key)
        if plan is None:
            return
        row = next((r for r in self._rows if r.species_key == species_key), None)
        if row is not None:
            self._detail.show_species(
                row.species, species_key, plan,
                no_data_text=self.tr("No detailed data available"),
            )

    def _on_step_date_reset(self, species_key: str, step_id: str) -> None:
        """Clear a propagation step override and revert to calculated dates."""
        self._project_manager.clear_propagation_override(species_key, step_id)
        self.refresh()
        self._repopulate_detail(species_key)

    # ─── Weather widget slots (US-12.1 / US-12.2) ────────────────────

    def _on_weather_ready(self) -> None:
        """Apply frost tinting; frost alerts flow into the dashboard via the
        unified engine (build_plan_state → generate_frost_tasks) on refresh."""
        forecast = self._weather.forecast()
        if forecast is None:
            return
        settings = get_settings()
        orange_c = settings.frost_warning_orange_c
        red_c = settings.frost_warning_red_c
        self._weather.apply_frost_thresholds(orange_c, red_c)
        plants = self._collect_plant_info()
        alerts = get_frost_alerts(forecast, plants, orange_c, red_c)
        self._current_frost_alerts = alerts
        # Update the frost corner badge (was emitted from the old _inject path).
        actionable = [a for a in alerts if self._frost_alert_actionable(a)]
        max_severity = ""
        if any(a.severity == "red" for a in actionable):
            max_severity = "red"
        elif actionable:
            max_severity = "orange"
        self.frost_alert_ready.emit(len(actionable), max_severity)
        # Share the computed alerts with the US-C2 Tasks tab (single fetch).
        self.frost_alerts_ready.emit(alerts)
        # Regenerate the dashboard with the new alerts. Rebuild only the
        # dashboard (NOT a full refresh — that would re-trigger the weather
        # fetch and loop).
        self._rebuild_dashboard()

    @staticmethod
    def _frost_alert_actionable(alert: Any) -> bool:
        """Whether a frost alert falls inside the actionable urgency window."""
        try:
            d = datetime.date.fromisoformat(alert.date)
        except (ValueError, AttributeError):
            return False
        return classify_urgency(d, d, datetime.date.today()) is not None

    @property
    def current_frost_alerts(self) -> list:
        """Latest frost alerts from the most recent weather fetch (US-C2)."""
        return list(self._current_frost_alerts)

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

    #: A one-line message for the main window's status bar.
    #:
    #: The calendar tab carries its own rather than reaching through the canvas.
    #: The tab and the canvas share one ``CanvasScene``, so the canvas route was
    #: *reachable*; the tab owning its own signal is still the right design — a tab
    #: message should come from the tab, and routing it through the canvas couples
    #: this refusal to whichever canvas view happens to be attached.
    #:
    #: An earlier version justified this by claiming the canvas is not in this tab's
    #: scene. Round 6 measured that claim FALSE. It is deleted rather than rebutted,
    #: because a rebuttal beside a false reason still leaves the false reason
    #: standing — which is what happened when round 6 added a note instead.
    status_message = pyqtSignal(str)

    # ── dashboard generation (unified engine, #228) ─────────────────────────────

    def apply_theme_colors(self, _colors: dict[str, str]) -> None:
        """Re-render on theme switch — dashboard urgency colors are palette-driven."""
        self.schedule_refresh()

    def _rebuild_dashboard(self) -> None:
        """Regenerate the Today's-Tasks dashboard from the unified engine.

        Separate from :meth:`refresh` so the async weather callback can update
        the frost rows without re-triggering the weather fetch (which would loop).
        """
        today = datetime.date.today()
        state = build_plan_state(
            self._canvas_scene,
            self._project_manager,
            frost_alerts=self._current_frost_alerts,
            soil_service=self._soil_service,
            # include_propagation (rather than a pre-built single-year
            # ``prop_plans`` dict) so the anchor-year machinery runs inside the
            # shared generator — this surface used to pass one plan per species,
            # which is exactly the single-anchor limitation #414 removes.
            include_propagation=self._prop_toggle.isChecked(),
        )
        self._plan_state = state
        task_states = self._project_manager.task_states
        bed_names = self._bed_name_map()
        dash: list[_DashboardTask] = []
        # generate_actionable_for_surface, not generate_all: the dashboard must
        # list windows anchored on ANY year's frost (#414) while still applying
        # its own "actionable now" rule.
        for task in generate_actionable_for_surface(state):
            # Calendar shows only actionable, still-open tasks (done / snoozed /
            # dismissed / archived are hidden via the shared status resolver).
            if effective_status(task_states.get(task.task_id), today) != "open":
                continue
            adapted = self._adapt_task(task, today, bed_names)
            if adapted is not None:
                dash.append(adapted)
        self._current_dashboard_tasks = dash
        self._dashboard.set_data(dash)

    def _bed_name_map(self) -> dict[str, str]:
        """item_id → display name for every garden item (for succession rows)."""
        from open_garden_planner.ui.canvas.items import GardenItemMixin  # noqa: PLC0415
        return {
            str(item.item_id): (item.name or str(item.item_id)[:8])
            for item in self._canvas_scene.items()
            if isinstance(item, GardenItemMixin)
        }

    def _adapt_task(
        self, task: Task, today: datetime.date, bed_names: dict[str, str]
    ) -> _DashboardTask | None:
        """Map a unified :class:`Task` to a compact dashboard row, or None when
        it falls outside the calendar's actionable window (undated/too far)."""
        if task.start_date is None or task.end_date is None:
            return None
        urgency = classify_urgency(task.start_date, task.end_date, today)
        if urgency is None:
            return None
        # Frost rows carry no species_key; their "→" highlight selects the
        # affected plants via the canvas "frost_items:" navigation branch
        # (application._on_highlight_species), so encode the item ids there.
        if task.task_type.startswith("frost_alert"):
            highlight_key = "frost_items:" + ",".join(task.item_ids)
        else:
            highlight_key = task.species_key
        return _DashboardTask(
            task_id=task.task_id,
            task_type=task.task_type,
            display_name=self._dashboard_display(task, bed_names),
            task_date=task.start_date,
            end_date=task.end_date,
            # The engine's "upcoming" is the dashboard's "coming_up" bucket.
            urgency="coming_up" if urgency == "upcoming" else urgency,
            species_key=highlight_key,
        )

    def _dashboard_display(self, task: Task, bed_names: dict[str, str]) -> str:
        """Row text for a task, matching the dashboard panel's templates."""
        tt = task.task_type
        if tt in ("succession_sow", "succession_clear"):
            bed = bed_names.get(task.bed_id or "", (task.bed_id or "")[:8])
            template = (
                self.tr("Sow {name} in {bed} (succession)")
                if tt == "succession_sow"
                else self.tr("Clear {name} from {bed} (succession)")
            )
            return template.format(name=task.title, bed=bed)
        if tt.startswith("frost_alert"):
            names = ", ".join(self._names_for_ids(list(task.item_ids)))
            if names:
                return self.tr("{title} — {names}").format(
                    title=task.title, names=names
                )
            return task.title
        # calendar / propagation: bare plant name (the panel template adds the
        # verb). soil_mismatch / soil_amendment / manual: title is a full label.
        return task.title

    def _on_weather_failed(self, message: str) -> None:
        """Weather forecast fetch failed — no frost alerts shown."""
