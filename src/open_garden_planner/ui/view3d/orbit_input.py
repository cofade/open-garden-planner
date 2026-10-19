"""Mouse, wheel and keys of the 3D view → the orbit camera (Phase 17 L1.3, ADR-060).

An event filter the workspace installs on the engine's window
(``Quick3DHost.install_event_filter``): the 3D view is a native window, so its
input never reaches the widget that embeds it. Engine-free — it needs
``QEvent`` and friends, not Qt Quick — and it holds no camera state of its own:
every gesture calls a method of ``core.scene3d.camera.OrbitCamera`` and then
says ``moved`` so the workspace starts stepping the damped pose.

The gestures follow the shipped Qt 3D view (``QOrbitCameraController``) where it
has one, and the 2D canvas for the rest:

==========================  ====================================================
left drag, middle drag      pan — the ground follows the hand
right drag                  orbit around the point looked at
left + right drag           zoom (down = away)
wheel                       zoom (up = closer)
arrow keys                  pan by a tenth of the view
Alt + arrow keys            orbit by ``KEY_ORBIT_DEG``
Page Up / Page Down         zoom in / out
Home                        reset the view (``reset_requested``)
==========================  ====================================================

Not taken from the Qt 3D controller: Escape (there: "show everything"). It is
left free for L1.8's walk mode, which the shipped view already leaves with it.

THE CLICK (L1.8, ADR-060). A left press and a left release — no other button down,
at most ``CLICK_SLOP_PX`` apart, at most ``CLICK_MAX_S`` apart in time — are a
click, and a click PICKS: ``host.pick(x, y)``, once, and ``picked`` carries the
hit (or None: the ground, the sky) and the modifiers that were held (the canvas's
rules differ for Ctrl and Shift — ``selection_bridge.apply_click``). It is the
ONE place of the workspace that takes a frame from the live view, and it does so
on a user's own action only — never on a move, a timer or a resize (the memory
rule; a scan test allows ``pick`` in this module, by name). A host that cannot
answer (``HostStateError``: mid-resize, collapsed, minimised) means "not now":
nothing is emitted and nothing is said. While a left press may still become a
click the camera does not move: a drag starts when the pointer leaves the slop —
with all of the way it has come, so no drag is ever shortened by it. Walk mode,
which turns the view on a drag and keeps the move to itself, ends a click in the
making that way too (``cancel_click``).
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from typing import Any, Final

from PyQt6.QtCore import QEvent, QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QWheelEvent

from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d.camera import FOV_DEG, OrbitCamera

from .quick3d.lifecycle import HostStateError  # engine-free: the state contract's module

_LOG: Final = logging.getLogger(__name__)

#: Degrees of orbit per pixel of a right drag.
DRAG_ORBIT_DEG_PER_PX: Final = 0.3
#: One wheel notch (120 eighths of a degree) multiplies the distance by this.
WHEEL_ZOOM_PER_NOTCH: Final = 0.85
#: A two-button drag: the distance grows by e^(this x pixels moved down).
DRAG_ZOOM_PER_PX: Final = 0.005
KEY_ORBIT_DEG: Final = 5.0
KEY_ZOOM: Final = 0.85
#: An arrow key pans by this share of what the view shows from top to bottom.
KEY_PAN_SHARE: Final = 0.1
#: A press and a release are a click when the pointer moved at most this far between
#: them (logical pixels, at any moment of the gesture) …
CLICK_SLOP_PX: Final = 4.0
#: … and at most this many seconds lie between them.
CLICK_MAX_S: Final = 0.4
_LEFT: Final = Qt.MouseButton.LeftButton
_RIGHT: Final = Qt.MouseButton.RightButton
_MIDDLE: Final = Qt.MouseButton.MiddleButton
#: key → (right, forward) of a pan, or (yaw, pitch) of an orbit, in unit steps
_ARROWS: Final = {
    Qt.Key.Key_Left: (-1.0, 0.0), Qt.Key.Key_Right: (1.0, 0.0),
    Qt.Key.Key_Up: (0.0, 1.0), Qt.Key.Key_Down: (0.0, -1.0),
}


class OrbitInput(QObject):
    """The event filter (module docstring). ``viewport_height`` answers the view's
    height in logical pixels when a drag needs it."""

    #: The camera's goal moved: step it.
    moved = pyqtSignal()
    #: Home was pressed: frame the plan again.
    reset_requested = pyqtSignal()
    #: A click picked (module docstring): the host's hit — ``PickHit``, or None for the
    #: ground and the sky — and the click's ``Qt.KeyboardModifier``s.
    picked = pyqtSignal(object, object)

    def __init__(self, camera: OrbitCamera, viewport_height: Callable[[], float],
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._camera = camera
        self._viewport_height = viewport_height
        self._last: QPointF | None = None  # where the drag was last seen
        self._host: Any = None             # whose view is clicked into (``watch``)
        self._press: tuple[QPointF, float] | None = None  # a left press that may be a click
        #: The clock the click's duration is measured on (the tests hold it).
        self.clock: Callable[[], float] = time.monotonic

    def watch(self, host: Any) -> None:
        """The host whose view a click picks in (``host.pick(x, y)``); None: no picking."""
        self._host = host

    def cancel_click(self) -> None:
        """The press in progress is no click (walk mode turned the view with it)."""
        self._press = None

    def eventFilter(self, _watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802 - Qt's name
        if event is None:
            return False
        kind = event.type()
        if isinstance(event, QMouseEvent):
            if kind == QEvent.Type.MouseButtonPress:
                self._last = event.position()
                alone = event.button() == _LEFT and event.buttons() == _LEFT
                self._press = (event.position(), self.clock()) if alone else None
                return True
            if kind == QEvent.Type.MouseButtonRelease:
                self._last = event.position() if event.buttons() != Qt.MouseButton.NoButton else None
                self._release(event)
                return True
            if kind == QEvent.Type.MouseMove:
                return self._drag(event)
            return False
        if isinstance(event, QWheelEvent):
            return self._wheel(event)
        if isinstance(event, QKeyEvent) and kind == QEvent.Type.KeyPress:
            return self._key(event)
        if kind == QEvent.Type.FocusOut:
            self._last = None  # the release of a held button never arrives
            self._press = None
        return False

    # ── the click ────────────────────────────────────────────────────────────

    def _release(self, event: QMouseEvent) -> None:
        press, self._press = self._press, None
        if press is None or event.button() != _LEFT:
            return
        at = event.position()
        if (math.hypot(at.x() - press[0].x(), at.y() - press[0].y()) > CLICK_SLOP_PX
                or self.clock() - press[1] > CLICK_MAX_S):
            return  # a drag, or a press that was held: not a click
        host = self._host
        if host is None:
            return
        try:
            hit = host.pick(at.x(), at.y())
        except HostStateError:
            return  # "not now" (mid-resize, collapsed, minimised): nothing happens, nothing is said
        except Exception as error:  # noqa: BLE001 - a click must never take the view down
            _LOG.error("3D view: a click could not be picked (%s: %s)",
                       log_text(type(error).__name__), log_text(error))
            return
        self.picked.emit(hit, event.modifiers())

    # ── gestures ─────────────────────────────────────────────────────────────

    def _drag(self, event: QMouseEvent) -> bool:
        buttons = event.buttons()
        last, now = self._last, event.position()
        if last is None or buttons == Qt.MouseButton.NoButton:
            return False  # a hover: not ours
        press = self._press
        if press is not None:
            if (buttons == _LEFT and math.hypot(now.x() - press[0].x(), now.y() - press[0].y())
                    <= CLICK_SLOP_PX):
                return True  # still a click in the making: the camera stays where it is
            self._press = None  # it became a drag: all of the way so far is applied below
        self._last = now
        dx, dy = now.x() - last.x(), now.y() - last.y()
        if dx == 0.0 and dy == 0.0:
            return True
        camera = self._camera
        if (buttons & _LEFT) and (buttons & _RIGHT):
            camera.zoom(math.exp(dy * DRAG_ZOOM_PER_PX))
        elif buttons & _RIGHT:
            camera.orbit(dx * DRAG_ORBIT_DEG_PER_PX, dy * DRAG_ORBIT_DEG_PER_PX)
        elif buttons & (_LEFT | _MIDDLE):
            camera.drag_pixels(dx, dy, viewport_height_px=self._viewport_height())
        else:
            return False
        self._announce()
        return True

    def _wheel(self, event: QWheelEvent) -> bool:
        notches = event.angleDelta().y() / 120.0
        if notches == 0.0:
            return False
        self._camera.zoom(WHEEL_ZOOM_PER_NOTCH ** notches)
        self._announce()
        return True

    def _key(self, event: QKeyEvent) -> bool:
        key = event.key()
        modifiers = event.modifiers()
        camera = self._camera
        if key in _ARROWS:
            across, along = _ARROWS[Qt.Key(key)]
            if modifiers & Qt.KeyboardModifier.AltModifier:
                camera.orbit(across * KEY_ORBIT_DEG, along * KEY_ORBIT_DEG)
            else:
                step = (KEY_PAN_SHARE * 2.0 * camera.goal.distance_cm
                        * math.tan(math.radians(FOV_DEG) / 2.0))
                camera.pan(across * step, along * step)
        elif key == Qt.Key.Key_PageUp:
            camera.zoom(KEY_ZOOM)
        elif key == Qt.Key.Key_PageDown:
            camera.zoom(1.0 / KEY_ZOOM)
        elif key == Qt.Key.Key_Home:
            self.reset_requested.emit()
            return True
        else:
            return False  # not a camera key: Qt's shortcuts and the scene get it
        self._announce()
        return True

    def _announce(self) -> None:
        if self._camera.moving:
            self.moved.emit()
