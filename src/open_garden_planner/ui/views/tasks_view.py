"""Unified Tasks dashboard tab (US-C2, #188).

Aggregates auto-generated tasks (planting-calendar windows, succession sow/clear,
soil amendments, frost protection) plus user-created manual tasks into one
grouped list (Overdue / Today / This Week / Upcoming / No date, plus Snoozed and
Done sections). Each task can be navigated-to, completed, snoozed, dismissed and
— for manual tasks — edited/deleted.

The task *generation* is delegated to the pure, Qt-free
:mod:`open_garden_planner.services.task_generator`; this module only builds the
:class:`~open_garden_planner.services.task_generator.PlanState` snapshot from the
live scene/project (``build_plan_state``) and renders the result. Per-task status
(done/snooze/dismiss) lives in the project's ``task_states`` and is resolved at
render time via :func:`open_garden_planner.services.task_status.effective_status`,
so simply reopening the project the next day re-buckets and un-snoozes correctly.
"""
from __future__ import annotations

import datetime
from typing import Any

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.task_generator import (
    BedInput,
    PlanState,
    PlantRowInput,
    Task,
    classify_urgency,
    generate_all,
)
from open_garden_planner.services.task_status import effective_status

# Refresh debounce — coalesce edit bursts to at most one regeneration/second.
_REFRESH_DEBOUNCE_MS = 1000

# Active urgency buckets in display order, with translatable headers resolved
# lazily (so QCoreApplication picks up the installed translator).
_BUCKET_ORDER = ("overdue", "today", "this_week", "upcoming", "no_date")

_URGENCY_COLOR = {
    "overdue": "#c0392b",
    "today": "#e67e22",
    "this_week": "#f1c40f",
    "upcoming": "#27ae60",
    "no_date": "#7f8c8d",
}


def _parse_frost(mmdd: str, year: int) -> datetime.date | None:
    """Parse an 'MM-DD' frost date for ``year`` (None on failure)."""
    try:
        m, d = (int(x) for x in mmdd.split("-"))
        return datetime.date(year, m, d)
    except (ValueError, AttributeError):
        return None


def build_plan_state(
    scene: Any,
    project_manager: Any,
    frost_alerts: list | None = None,
    soil_service: Any | None = None,
) -> PlanState:
    """Snapshot the live scene + project into a Qt-free :class:`PlanState`.

    Reuses the same data sources as the planting-calendar dashboard
    (species week-offsets, the location's last-frost date, succession plans) and
    the soil amendment engine. Propagation steps are intentionally NOT fed here —
    they remain surfaced on the calendar dashboard (US-C2 scope is calendar /
    succession / soil / frost / manual).
    """
    from open_garden_planner.core.object_types import (  # noqa: PLC0415
        get_translated_display_name,
        is_bed_type,
    )
    from open_garden_planner.models.plant_data import PlantSpeciesData  # noqa: PLC0415
    from open_garden_planner.models.task import ManualTask  # noqa: PLC0415

    today = datetime.date.today()
    year = today.year

    last_frost: datetime.date | None = None
    location = project_manager.location or {}
    frost_dates = location.get("frost_dates") or {}
    lsf = frost_dates.get("last_spring_frost")
    if lsf:
        last_frost = _parse_frost(lsf, year)

    plant_rows: list[PlantRowInput] = []
    beds: list[BedInput] = []
    if scene is not None:
        for item in scene.items():
            object_type = getattr(item, "object_type", None)
            metadata = getattr(item, "metadata", None) or {}
            ps_dict = metadata.get("plant_species") if isinstance(metadata, dict) else None
            if ps_dict:
                try:
                    sp = PlantSpeciesData.from_dict(ps_dict)
                except Exception:
                    sp = None
                if sp is not None:
                    species_key = sp.scientific_name or sp.common_name or getattr(item, "name", "")
                    if species_key:
                        plant_rows.append(PlantRowInput(
                            display_name=(getattr(item, "name", "") or sp.common_name or species_key),
                            species_key=species_key,
                            indoor_sow_start=sp.indoor_sow_start,
                            indoor_sow_end=sp.indoor_sow_end,
                            direct_sow_start=sp.direct_sow_start,
                            direct_sow_end=sp.direct_sow_end,
                            transplant_start=sp.transplant_start,
                            transplant_end=sp.transplant_end,
                            harvest_start=sp.harvest_start,
                            harvest_end=sp.harvest_end,
                        ))
            if is_bed_type(object_type):
                bed_id = str(getattr(item, "item_id", ""))
                if not bed_id:
                    continue
                name = getattr(item, "name", "") or get_translated_display_name(object_type)
                beds.append(BedInput(
                    bed_id=bed_id,
                    name=name,
                    amendment_recs=_bed_amendment_recs(bed_id, item, soil_service),
                ))

    manual_tasks = tuple(
        ManualTask.from_dict(d) for d in project_manager.manual_tasks.values()
    )

    return PlanState(
        today=today,
        year=year,
        last_frost=last_frost,
        plant_rows=tuple(plant_rows),
        beds=tuple(beds),
        succession_plans=dict(project_manager.succession_plans),
        manual_tasks=manual_tasks,
        frost_alerts=tuple(frost_alerts or ()),
    )


def _bed_amendment_recs(
    bed_id: str, item: Any, soil_service: Any | None
) -> tuple[tuple[str, str], ...]:
    """Flatten a bed's amendment recommendations into (name, rationale) pairs."""
    if soil_service is None:
        return ()
    record = soil_service.get_effective_record(bed_id)
    if record is None:
        return ()
    from open_garden_planner.core.measurements import (  # noqa: PLC0415
        calculate_area_and_perimeter,
    )
    from open_garden_planner.services.soil_service import SoilService  # noqa: PLC0415

    result = calculate_area_and_perimeter(item)
    if result is None:
        return ()
    area_m2 = result[0] / 10_000.0
    if area_m2 <= 0.0:
        return ()
    recs = SoilService.calculate_amendments(record, bed_area_m2=area_m2)
    pairs: list[tuple[str, str]] = []
    for rec in recs:
        name = rec.amendment.display_name()
        pairs.append((name, f"~{rec.quantity_g:.0f} g"))
    return tuple(pairs)


class TasksView(QWidget):
    """The Tasks dashboard tab."""

    #: Switch to the canvas and select the bed with this UUID string.
    navigate_to_bed = pyqtSignal(str)
    #: Switch to the canvas and select all items of this species key.
    navigate_to_species = pyqtSignal(str)
    #: Switch to the canvas and select the items with these UUID strings.
    navigate_to_items = pyqtSignal(object)

    def __init__(
        self,
        canvas_scene: Any,
        project_manager: Any,
        command_manager: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene = canvas_scene
        self._pm = project_manager
        self._cmd = command_manager
        self._soil_service: Any | None = None
        self._frost_alerts: list = []

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(_REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)

        self._build_ui()
        self.refresh()

    # ── setup ────────────────────────────────────────────────────────────────
    def set_soil_service(self, service: Any) -> None:
        """Inject the soil service used to compute amendment tasks."""
        self._soil_service = service

    def set_frost_alerts(self, alerts: list) -> None:
        """Receive frost alerts from the calendar view's single weather fetch."""
        self._frost_alerts = list(alerts or [])
        self.schedule_refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(self.tr("Tasks"))
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        add_btn = QPushButton(self.tr("Add Task"))
        add_btn.clicked.connect(self._on_add_task)
        header.addWidget(add_btn)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(4)
        self._content_layout.addStretch()
        scroll.setWidget(self._content)
        layout.addWidget(scroll)

    # ── refresh ──────────────────────────────────────────────────────────────
    def schedule_refresh(self) -> None:
        """Coalesce refresh requests to at most one per second (#188)."""
        self._refresh_timer.start()

    def _on_refresh_timer(self) -> None:
        """Debounced refresh — skip the heavy rebuild while the tab is hidden
        (the tab-switch handler refreshes it when it next becomes visible)."""
        if not self.isVisible():
            return
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the task list from current project state."""
        self._clear_content()
        try:
            state = build_plan_state(
                self._scene, self._pm, self._frost_alerts, self._soil_service
            )
        except RuntimeError:
            return  # scene torn down (shutdown)
        tasks = generate_all(state)
        today = state.today
        task_states = self._pm.task_states

        buckets: dict[str, list[Task]] = {b: [] for b in _BUCKET_ORDER}
        snoozed: list[Task] = []
        done: list[Task] = []
        for task in tasks:
            eff = effective_status(task_states.get(task.task_id), today)
            if eff in ("archived", "dismissed"):
                continue
            if eff == "snoozed":
                snoozed.append(task)
            elif eff == "done":
                done.append(task)
            else:
                buckets[self._bucket(task, today)].append(task)

        headers = {
            "overdue": self.tr("Overdue"),
            "today": self.tr("Today"),
            "this_week": self.tr("This Week"),
            "upcoming": self.tr("Upcoming"),
            "no_date": self.tr("No date"),
        }
        any_rows = False
        for bucket in _BUCKET_ORDER:
            rows = buckets[bucket]
            if rows:
                any_rows = True
                self._add_section(headers[bucket], _URGENCY_COLOR[bucket], rows)
        if snoozed:
            self._add_section(self.tr("Snoozed"), "#95a5a6", snoozed, snoozed=True)
        if done:
            self._add_section(self.tr("Done"), "#95a5a6", done, is_done=True)

        if not any_rows and not snoozed and not done:
            empty = QLabel(self.tr("No tasks — you're all caught up."))
            empty.setStyleSheet("color: gray; padding: 24px;")
            self._content_layout.insertWidget(self._content_layout.count() - 1, empty)

    @staticmethod
    def _bucket(task: Task, today: datetime.date) -> str:
        """Render-time urgency bucket for a task (manual tasks may fall outside
        the generators' actionable window, so re-derive defensively)."""
        if task.start_date is not None and task.end_date is not None:
            urgency = classify_urgency(task.start_date, task.end_date, today)
            if urgency is not None:
                return urgency
            return "overdue" if task.end_date < today else "upcoming"
        return "no_date"

    def _clear_content(self) -> None:
        while self._content_layout.count() > 1:  # keep the trailing stretch
            item = self._content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)  # detach now so findChildren reflects the rebuild
                w.deleteLater()

    # ── rendering ─────────────────────────────────────────────────────────────
    def _add_section(
        self,
        title: str,
        color: str,
        tasks: list[Task],
        *,
        snoozed: bool = False,
        is_done: bool = False,
    ) -> None:
        header = QLabel(f"{title} ({len(tasks)})")
        header.setStyleSheet(f"font-weight: bold; color: {color}; margin-top: 6px;")
        self._content_layout.insertWidget(self._content_layout.count() - 1, header)
        for task in sorted(tasks, key=lambda t: (t.start_date or datetime.date.max)):
            self._content_layout.insertWidget(
                self._content_layout.count() - 1,
                self._build_row(task, color, snoozed=snoozed, is_done=is_done),
            )

    def _build_row(
        self,
        task: Task,
        color: str,
        *,
        snoozed: bool,
        is_done: bool,
    ) -> QFrame:
        row = QFrame()
        row.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)

        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color};")
        layout.addWidget(dot)

        label = QLabel(self._row_text(task))
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if is_done:
            label.setStyleSheet("color: gray; text-decoration: line-through;")
        layout.addWidget(label, 1)

        if task.start_date is not None:
            date_lbl = QLabel(task.start_date.isoformat())
            date_lbl.setStyleSheet("color: gray;")
            layout.addWidget(date_lbl)

        # Navigate
        if task.bed_id or task.species_key or task.item_ids:
            go = QPushButton("→")
            go.setFixedWidth(28)
            go.setToolTip(self.tr("Show on canvas"))
            go.clicked.connect(lambda _=False, t=task: self._navigate(t))
            layout.addWidget(go)

        if snoozed:
            unsnooze = QPushButton(self.tr("Un-snooze"))
            unsnooze.clicked.connect(lambda _=False, t=task: self._pm.clear_task_status(t.task_id))
            layout.addWidget(unsnooze)
            return row

        if not is_done:
            done_btn = QPushButton(self.tr("Done"))
            done_btn.setFixedWidth(56)
            done_btn.clicked.connect(lambda _=False, t=task: self._mark_done(t))
            layout.addWidget(done_btn)

            snooze_btn = QPushButton(self.tr("Snooze"))
            snooze_btn.clicked.connect(lambda _=False, t=task, b=snooze_btn: self._snooze_menu(t, b))
            layout.addWidget(snooze_btn)

            if task.source == "manual":
                edit_btn = QPushButton(self.tr("Edit"))
                edit_btn.setFixedWidth(48)
                edit_btn.clicked.connect(lambda _=False, t=task: self._edit_manual(t))
                layout.addWidget(edit_btn)
                del_btn = QPushButton(self.tr("Delete"))
                del_btn.clicked.connect(lambda _=False, t=task: self._delete_manual(t))
                layout.addWidget(del_btn)
            elif task.dismissible:
                dismiss_btn = QPushButton(self.tr("Dismiss"))
                dismiss_btn.clicked.connect(
                    lambda _=False, t=task: self._pm.set_task_status(t.task_id, "dismissed")
                )
                layout.addWidget(dismiss_btn)
        else:
            reopen = QPushButton(self.tr("Reopen"))
            reopen.clicked.connect(lambda _=False, t=task: self._pm.clear_task_status(t.task_id))
            layout.addWidget(reopen)
        return row

    def _row_text(self, task: Task) -> str:
        if task.notes:
            return f"{task.title} — {task.notes}"
        return task.title

    # ── actions ───────────────────────────────────────────────────────────────
    def _navigate(self, task: Task) -> None:
        if task.bed_id:
            self.navigate_to_bed.emit(task.bed_id)
        elif task.item_ids:
            self.navigate_to_items.emit(list(task.item_ids))
        elif task.species_key:
            self.navigate_to_species.emit(task.species_key)

    def _mark_done(self, task: Task) -> None:
        self._pm.set_task_status(
            task.task_id, "done", done_date=datetime.date.today().isoformat()
        )

    def _snooze_menu(self, task: Task, anchor: QWidget) -> None:
        from PyQt6.QtCore import Qt  # noqa: PLC0415

        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        today = datetime.date.today()
        options = [
            (self.tr("1 day"), 1),
            (self.tr("1 week"), 7),
            (self.tr("2 weeks"), 14),
        ]
        for label, days in options:
            act = menu.addAction(label)
            until = (today + datetime.timedelta(days=days)).isoformat()
            act.triggered.connect(
                lambda _=False, t=task, u=until: self._pm.set_task_status(
                    t.task_id, "open", snooze_until=u
                )
            )
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _on_add_task(self) -> None:
        from open_garden_planner.ui.dialogs.task_dialog import TaskDialog  # noqa: PLC0415

        dialog = TaskDialog(self, scene=self._scene)
        if dialog.exec():
            self._commit_manual(dialog.result_task(), edit=False)

    def _edit_manual(self, task: Task) -> None:
        from open_garden_planner.ui.dialogs.task_dialog import TaskDialog  # noqa: PLC0415

        existing = self._pm.get_manual_task(task.task_id)
        if existing is None:
            return
        dialog = TaskDialog(self, task=existing, scene=self._scene, edit_mode=True)
        if dialog.exec():
            self._commit_manual(dialog.result_task(), edit=True)

    def _delete_manual(self, task: Task) -> None:
        from open_garden_planner.core.commands import (  # noqa: PLC0415
            DeleteManualTaskCommand,
        )

        cmd = DeleteManualTaskCommand(self._pm, task.task_id)
        if self._cmd is not None:
            self._cmd.execute(cmd)
        else:
            cmd.execute()

    def _commit_manual(self, task: Any, *, edit: bool) -> None:
        from open_garden_planner.core.commands import (  # noqa: PLC0415
            AddManualTaskCommand,
            EditManualTaskCommand,
        )

        cmd = (
            EditManualTaskCommand(self._pm, task)
            if edit
            else AddManualTaskCommand(self._pm, task)
        )
        if self._cmd is not None:
            self._cmd.execute(cmd)
        else:
            cmd.execute()
