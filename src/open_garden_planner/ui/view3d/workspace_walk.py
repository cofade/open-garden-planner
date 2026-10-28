"""Walk mode coordinator for the 3D workspace (Phase 17 L2, issue #583)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from open_garden_planner.core.scene3d.walk import WalkWorld, build_world, is_solid

from .sync_controller import TickReport
from .workspace_protocols import EngineHost

if TYPE_CHECKING:
    from .walk_mode import WalkMode

_LOG = logging.getLogger(__name__)


def _log_failure(what: str, error: BaseException) -> None:
    _LOG.warning("%s: %s: %s", what, type(error).__name__, error)


class WorkspaceWalkCoordinator:
    """Coordinates WalkMode lifecycle, camera pose updates, collision world, and focus."""

    def __init__(
        self,
        get_host: Callable[[], EngineHost | None],
        get_controller: Callable[[], Any],
        get_orbit: Callable[[], Any],
        get_camera: Callable[[], Any],
        get_pane: Callable[[], Any],
        get_status_label: Callable[[], QLabel | None],
        get_walk_action: Callable[[], QAction | None],
        get_eye_height: Callable[[], float | None],
        apply_camera: Callable[[], None],
        is_pane_showing: Callable[[], bool],
        parent_widget: QWidget,
    ) -> None:
        self._get_host = get_host
        self._get_controller = get_controller
        self._get_orbit = get_orbit
        self._get_camera = get_camera
        self._get_pane = get_pane
        self._get_status_label = get_status_label
        self._get_walk_action = get_walk_action
        self._get_eye_height = get_eye_height
        self._apply_camera = apply_camera
        self._is_pane_showing = is_pane_showing
        self._parent = parent_widget

        self._walk: WalkMode | None = None
        self._focus_before: QWidget | None = None

    @property
    def walk(self) -> WalkMode | None:
        return self._walk

    @walk.setter
    def walk(self, value: WalkMode | None) -> None:
        self._walk = value

    def unwire(self) -> None:
        self.set_walking(False)
        walk, self._walk = self._walk, None
        if walk is not None:
            walk.deleteLater()
        action = self._get_walk_action()
        if action is not None:
            action.setEnabled(False)

    def set_walking(self, on: bool) -> bool:
        action = self._get_walk_action()
        walk = self._walk
        if not on:
            if walk is not None and walk.active:
                walk.leave()
                self._after_walk_change()
                self._give_focus_back()
            if action is not None:
                action.setChecked(False)
            return False

        controller, host = self._get_controller(), self._get_host()
        if controller is None or host is None:
            if action is not None:
                action.setChecked(False)
            return False

        if walk is None:
            from .walk_mode import WalkMode

            walk = WalkMode(self._parent)
            host.install_event_filter(walk)
            walk.changed.connect(self._apply_camera)
            walk.left.connect(lambda: self.set_walking(False))
            orbit = self._get_orbit()
            if orbit is not None:
                walk.turned.connect(orbit.cancel_click)
            eye_h = self._get_eye_height()
            if eye_h is not None:
                walk.set_eye_height(eye_h)
            self._walk = walk

        if not walk.active:
            camera = self._get_camera()
            pose = camera.pose if camera is not None else None
            if pose is None or not walk.enter(self.walk_world(), pose.target, pose.yaw_deg):
                status = self._get_status_label()
                if status is not None:
                    status.setText(
                        QCoreApplication.translate("Workspace", "There is no free ground to walk on.")
                    )
                if action is not None:
                    action.setChecked(False)
                return False

            if not self._is_pane_showing():
                walk.pause()
            self._after_walk_change()
            self._take_focus(host)

        if action is not None:
            action.setChecked(True)
        return True

    def on_showing_changed(self, showing: bool) -> None:
        walk = self._walk
        if walk is not None and walk.active:
            if showing:
                walk.resume()
            else:
                walk.pause()

    def on_applied(self, report: TickReport) -> None:
        walk, changes, controller = self._walk, report.changes, self._get_controller()
        if walk is None or not walk.active or not report.snapshot or controller is None:
            return
        touched = {*changes.added, *changes.removed, *changes.geometry, *changes.transform}
        records = controller.sync.records
        world = walk.world
        was_solid = touched & set(world.solid_ids) if world is not None else touched
        if was_solid or any(is_solid(records[i]) for i in touched if i in records):
            walk.set_world(self.walk_world())
            self._after_walk_change()

    def walk_world(self) -> WalkWorld:
        controller = self._get_controller()
        assert controller is not None
        bounds = controller.plan_bounds()
        return build_world(
            controller.sync.records,
            bounds.max_east,
            bounds.max_north,
            parts_of=self.held_parts(),
        )

    def held_parts(self) -> Callable[[Any], tuple[Any, ...]]:
        controller = self._get_controller()
        held = getattr(controller.sync.sink, "item", None) if controller is not None else None

        def parts_of(record: Any) -> tuple[Any, ...]:
            if not callable(held):
                return ()
            try:
                return tuple(held(record.item_id).parts)
            except KeyError:
                return ()

        return parts_of

    def _take_focus(self, host: EngineHost) -> None:
        before = QApplication.focusWidget()
        pane = self._get_pane()
        engine = getattr(pane, "engine_widget", None) if pane is not None else None
        self._focus_before = before if before is not engine else None
        try:
            host.focus()
        except Exception as error:  # noqa: BLE001
            _log_failure("3D workspace: the 3D view could not take the keyboard focus", error)

    def _give_focus_back(self) -> None:
        before, self._focus_before = self._focus_before, None
        host = self._get_host()
        if before is None or sip.isdeleted(before) or host is None:
            return
        try:
            still_ours = host.has_focus()
        except Exception:  # noqa: BLE001
            still_ours = False
        if still_ours:
            before.activateWindow()
            before.setFocus(Qt.FocusReason.OtherFocusReason)

    def _after_walk_change(self) -> None:
        self._apply_camera()
