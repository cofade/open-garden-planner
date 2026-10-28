"""Selection and info card coordinator for the 3D workspace (Phase 17 L2, issue #583)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from .info_card import CardSubject, View3DCardSlot, View3DInfoCard, card_facts
from .problems_dialog import BUILD_FAILED, reason_text
from .selection_bridge import apply_click, hit_ids, selected_record_ids, sole_selected
from .sync_controller import TickReport
from .workspace_protocols import EngineHost

_LOG = logging.getLogger(__name__)


def _log_failure(what: str, error: BaseException) -> None:
    _LOG.warning("%s: %s: %s", what, type(error).__name__, error)


class WorkspaceSelectionCoordinator:
    """Coordinates canvas and 3D selection, ring synchronization, and the info card."""

    def __init__(
        self,
        get_scene: Callable[[], QGraphicsScene | None],
        get_controller: Callable[[], Any],
        get_clock: Callable[[], Any],
        get_location: Callable[[], Any],
        get_sun_heatmap: Callable[[], Any],
        find_item: Callable[[str | None], QGraphicsItem | None],
        is_chrome_visible: Callable[[], bool],
        is_pane_showing: Callable[[], bool],
        schedule_xray: Callable[[], None],
        get_probe_text: Callable[[], str],
        on_walk_applied: Callable[[TickReport], None],
        on_walk_resume_pause: Callable[[bool], None],
    ) -> None:
        self._get_scene = get_scene
        self._get_controller = get_controller
        self._get_clock = get_clock
        self._get_location = get_location
        self._get_sun_heatmap = get_sun_heatmap
        self._find_item = find_item
        self._is_chrome_visible = is_chrome_visible
        self._is_pane_showing = is_pane_showing
        self._schedule_xray = schedule_xray
        self._get_probe_text = get_probe_text
        self._on_walk_applied = on_walk_applied
        self._on_walk_resume_pause = on_walk_resume_pause

        self._card_slot: View3DCardSlot | None = None
        self._card: View3DInfoCard | None = None
        self._selection_wired = False

    @property
    def card_slot(self) -> View3DCardSlot | None:
        return self._card_slot

    @property
    def card(self) -> View3DInfoCard | None:
        return self._card

    def setup_card_slot(self, slot: View3DCardSlot) -> None:
        self._card_slot = slot
        self._card = slot.card

    def wire(self, host: EngineHost, orbit: Any, controller: Any) -> None:
        orbit.watch(host)
        orbit.picked.connect(self.on_picked)
        controller.applied.connect(self.on_applied)
        controller.problems_changed.connect(self.refresh_card)
        scene = self._get_scene()
        if scene is not None and not self._selection_wired:
            scene.selectionChanged.connect(self.on_canvas_selection)
            self._selection_wired = True
        self.on_canvas_selection()

    def unwire(self) -> None:
        scene = self._get_scene()
        if scene is not None and self._selection_wired:
            try:
                scene.selectionChanged.disconnect(self.on_canvas_selection)
            except (RuntimeError, TypeError):
                _LOG.debug("3D workspace: the canvas selection was already disconnected")
        self._selection_wired = False
        if self._card_slot is not None:
            self._card_slot.show_hint("")
            self._card_slot.hide()

    def on_canvas_selection(self) -> None:
        controller, scene = self._get_controller(), self._get_scene()
        if controller is None or scene is None:
            return
        try:
            ids = selected_record_ids(scene)
        except RuntimeError:
            return
        controller.set_selection(ids)
        self.refresh_card()
        self._schedule_xray()

    def on_picked(self, hit: object, modifiers: object) -> None:
        scene = self._get_scene()
        if scene is not None:
            held = (
                modifiers
                if isinstance(modifiers, Qt.KeyboardModifier)
                else Qt.KeyboardModifier.NoModifier
            )
            apply_click(scene, hit_ids(hit), held)

    def on_showing_changed(self, showing: bool) -> None:
        self._on_walk_resume_pause(showing)
        if showing:
            self.refresh_card()

    def on_applied(self, report: TickReport) -> None:
        self.refresh_card()
        self._on_walk_applied(report)

    def refresh_card(self) -> None:
        slot = self._card_slot
        if slot is None:
            return
        slot.setVisible(self._is_chrome_visible() and self._get_controller() is not None)
        if not self._is_pane_showing():
            return
        subject = self.card_subject()
        if subject is None:
            slot.show_hint(self.selection_hint())
        else:
            slot.show_subject(subject)

    def selection_hint(self) -> str:
        scene = self._get_scene()
        try:
            count = len(scene.selectedItems()) if scene is not None else 0
        except RuntimeError:
            count = 0
        if count > 1:
            return QCoreApplication.translate(
                "Workspace", "{count} objects selected."
            ).format(count=count)
        probe = self._get_probe_text()
        if probe:
            return probe
        return QCoreApplication.translate(
            "Workspace", "Click an object to see what the 3D view shows of it."
        )

    def card_subject(self) -> CardSubject | None:
        controller, scene, clock = (
            self._get_controller(),
            self._get_scene(),
            self._get_clock(),
        )
        if controller is None or scene is None or not self._is_chrome_visible():
            return None
        try:
            item = sole_selected(scene)
        except RuntimeError:
            return None
        if item is None:
            return None

        item_id = str(getattr(item, "item_id", "") or "")
        record = controller.sync.records.get(item_id)
        problem = ""
        for skipped in controller.skipped:
            if skipped.item_id == item_id:
                problem = reason_text(str(skipped.reason.value))
        if item_id in controller.failures:
            problem = reason_text(BUILD_FAILED)

        if getattr(item, "object_type", None) is None and record is None:
            has_model = any(
                self.has_model(str(getattr(member, "item_id", "")))
                for member in item.childItems()
            )
        else:
            has_model = not problem and self.has_model(item_id)

        parent_id = record.parent_id if record is not None else None
        plan_date = clock.plan_date if clock is not None else None
        parent_item = self._find_item(parent_id) if parent_id else None
        parent_name = str(getattr(parent_item, "name", "") or "") if parent_item else ""

        return CardSubject(
            item,
            record,
            has_model,
            problem,
            parent_name,
            plan_date,
            self.card_facts(item, record, plan_date),
        )

    def card_facts(self, item: Any, record: Any, plan_date: Any) -> Any:
        heatmap = self._get_sun_heatmap()
        sun: tuple[float, Any] | None = None
        if heatmap is not None and getattr(heatmap, "exposure_reason", "") == "ready":
            minutes = dict(getattr(heatmap, "receiver_minutes", {}) or {}).get(
                str(getattr(item, "item_id", ""))
            )
            day = getattr(heatmap, "computed_day", None)
            if isinstance(minutes, (int, float)) and day is not None:
                sun = (float(minutes), day)
        try:
            return card_facts(item, record, plan_date, self._get_location(), sun)
        except Exception as error:  # noqa: BLE001
            _log_failure("3D info card: the plant facts could not be read", error)
            return None

    def has_model(self, item_id: str) -> bool:
        controller = self._get_controller()
        held = (
            getattr(controller.sync.sink, "item", None)
            if controller is not None
            else None
        )
        if not callable(held):
            return False
        try:
            return any(
                part.mesh.triangle_count and not part.ground_detail
                for part in held(item_id).parts
            )
        except KeyError:
            return False
