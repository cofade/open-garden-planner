"""Compact, always available month scrubber for the existing simulation clock."""

from datetime import date, timedelta
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QMenu, QSlider, QToolBar, QToolButton, QWidget

from open_garden_planner.core.object_types import get_translated_display_name, is_plant_type
from open_garden_planner.core.plan_timeline import (
    instance_date,
    month_number,
    month_start,
    timeline_month_range,
)


class PlanTimelineToolbar(QToolBar):
    """A clock view: emits requested dates, stores no second plan date."""

    date_requested = pyqtSignal(object)

    def __init__(self, scene: Any, parent: QWidget | None = None) -> None:
        super().__init__(self.tr("Plan Timeline"), parent)
        self.setObjectName("PlanTimelineToolbar")
        self.setMovable(False)
        self._scene = scene
        self.addWidget(QLabel(self.tr("Plan date:"), self))
        self._month_label = QLabel(self)
        self._month_label.setMinimumWidth(230)
        self.addWidget(self._month_label)
        self._month_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._month_slider.setFixedWidth(220)
        self._month_slider.setPageStep(12)
        self._month_slider.setToolTip(self.tr("Scrub the plan by month"))
        self.addWidget(self._month_slider)
        self._today_button = QToolButton(self)
        self._today_button.setText(self.tr("Today"))
        self._today_button.clicked.connect(lambda: self.date_requested.emit(date.today()))
        self.addWidget(self._today_button)
        self._hidden_button = QToolButton(self)
        self._hidden_menu = QMenu(self._hidden_button)
        self._hidden_button.setMenu(self._hidden_menu)
        self._hidden_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._hidden_menu.aboutToShow.connect(self._populate_hidden)
        self.addWidget(self._hidden_button)
        self._month_slider.valueChanged.connect(self._request_month)
        scene.timeline_changed.connect(self.refresh)
        self.refresh()

    def _request_month(self, number: int) -> None:
        self.date_requested.emit(month_start(number))

    def refresh(self) -> None:
        day = self._scene.plan_date
        if day is None:
            return
        plants = [item for item in self._scene.items()
                  if is_plant_type(getattr(item, "object_type", None))]
        low, high = timeline_month_range((p.metadata for p in plants), date.today(), day)
        self._month_slider.blockSignals(True)
        self._month_slider.setRange(low, high)
        self._month_slider.setValue(month_number(day))
        self._month_slider.blockSignals(False)
        indicator = (self.tr("Viewing plan as of {date}").format(date=day.isoformat())
                     if day != date.today() else self.tr("Viewing today's plan"))
        self._month_label.setText(indicator)
        self._month_label.setToolTip(indicator)
        self._today_button.setToolTip(indicator)
        self._today_button.setEnabled(day != date.today())
        count = sum(not self._scene.is_present(p) for p in plants)
        self._hidden_button.setText(self.tr("{count} plants hidden by date").format(count=count))
        self._hidden_button.setEnabled(count > 0)

    def _populate_hidden(self) -> None:
        self._hidden_menu.clear()
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
            if target is None or not MIN_PLAN_DATE <= target <= MAX_PLAN_DATE:
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
