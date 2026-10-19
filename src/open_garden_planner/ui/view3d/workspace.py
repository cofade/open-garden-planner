"""The Plan / 3D / Split workspace of the main window (Phase 17 L1.3, ADR-065).

The area that held the canvas view holds a ``Workspace``: the canvas, and — once
the user first asks for it — a 3D pane beside it. Three modes:

- **Plan**: the canvas alone. Its size and its pixels are what they were without
  the workspace; the only addition on screen is a small floating mode switch.
- **3D**: the 3D pane alone.
- **Split**: canvas | 3D pane in a splitter. Neither side collapses: a collapsed
  3D pane would be a third way of saying "Plan" in which the engine keeps running.

Nothing of the 3D engine is imported or created before the first switch to 3D or
Split; after that ONE engine host is kept for the life of the window and only
hidden and shown. This module imports no Qt Quick binding at all: the engine is
built by ``engine_factory`` — by default ``ui/view3d/quick3d`` — which is also the
seam the tests put a recording sink into.

Layout rule (ADR-065): the 3D view is a NATIVE window inside a container, and no
sibling widget paints over it. So nothing here ever overlays it — every control,
notice and message of the 3D pane sits in a strip ABOVE the view, or replaces it.
L1.8's info card goes into the same pane, beside or below the view, not on top.

What moves the camera: user input (``OrbitInput``), "Reset 3D view", the first
open, and a document change — the four calls in ``_on_document_shown``,
``reset_view`` and the input filter. No edit does.

Timers: the pipeline's tick is ``Scene3DController``'s; this module adds three, and
all stop when the 3D pane is hidden — the camera step (runs only while the camera
is still moving), the health poll (``Quick3DHost.health()``: first frame,
graphics failure, QML warnings — never a Qt message handler, which deadlocks
beside Qt's render thread) and the build notice's fallback (below).

THE FIRST PASS OF A DOCUMENT WAITS FOR ITS NOTICE. A first pass costs the sum of
its items — milliseconds for a garden, seconds for a hostile plan — with the GUI
thread inside it. So "Building the 3D view…" is set, and the pipeline is started
by THE PAINT of that label (``_announce_build`` / ``eventFilter``), not by a timer
that hopes the paint came first; a label that is never painted releases the
pipeline after ``BUILD_NOTICE_WAIT_MS``. The same for a new document while 3D is
shown.

NOTHING HERE TAKES A FRAME FROM THE LIVE VIEW (ADR-065 decision 17, measured). A
readback of the host (``grab()``, and ``wait_ready()`` / ``pick()`` / ``project()``,
which need a frame) renders a frame of its own that is never presented, and what
such a frame holds is given back only when a PRESENTED frame ends — in a view that
presents nothing (the display asleep), never. So the pass, the health poll, the
timers, a resize and the splitter ask the host for none of them: the workspace
tells the engine what the plan is, and Qt draws it when it draws. A picture of the
3D view for a file or a thumbnail goes through ``quick3d/offscreen.py`` (a host of
its own that gives everything back when it closes), never through the shown host.
A click that picks (L1.8) is a user's own action, once. Pinned by a scan of this
package's five modules and by a stand-in host that records such calls.

WHAT A DESTROYED MODEL LEAVES BEHIND (ADR-065, measured). Qt Quick 3D keeps
graphics state for every Model it once drew — about 0.2 MB each on Direct3D 11
with the sun's shadow passes — until ``QQuickWindow.releaseResources()`` is
called; nothing else gives it back (20 rebuilds of the small bench plan in a
presenting view, no readback: 19 MB per rebuild without, 2 with). The
pipeline's passes say how many items lost
their Models (``TickReport.retired``); the workspace counts them and tells the
host to let go — when the pipeline has been quiet for a moment
(``RELEASE_AFTER_RETIRED``), or at once when a flood of them piles up
(``RELEASE_NOW_RETIRED``: an animated date regrows every dated plant per tick).
"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, Final, Protocol

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QHideEvent, QKeySequence, QShowEvent
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.plain_text import clip_text, log_text
from open_garden_planner.core.scene3d.camera import FOV_DEG, OrbitCamera

from .init_guard import Init3DGuard, ModeReason, RenderMode, default_directory

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsScene

    from open_garden_planner.core.scene3d import EngineSink
    from open_garden_planner.core.sim_clock import SimClock

    from .look_controller import LookController
    from .orbit_input import OrbitInput
    from .problems_dialog import View3DProblemsDialog
    from .sync_controller import Scene3DController, TickReport

_LOG: Final = logging.getLogger(__name__)

#: The 3D pane never gets narrower than this in Split mode (it does not collapse).
MIN_PANE_WIDTH: Final = 220
#: The camera is stepped at this interval while it moves.
CAMERA_STEP_MS: Final = 16
#: The health poll: fast until the first frame was presented, then slow.
HEALTH_FAST_MS: Final = 200
HEALTH_SLOW_MS: Final = 2000
#: How long the first pass of a document waits for its notice to be painted before it
#: starts anyway (a label that some platform never paints must not hold 3D back).
BUILD_NOTICE_WAIT_MS: Final = 250
#: The engine's cached graphics state is released once this many items lost their
#: Models AND the pipeline has been quiet for ``RELEASE_IDLE_S`` (the health poll
#: looks) — at about 0.2 MB per Model that is some 13 MB.
RELEASE_AFTER_RETIRED: Final = 64
RELEASE_IDLE_S: Final = 0.5
#: … and at once, with the pass, when this many piled up: a pipeline that is never
#: quiet (an animated date) must not keep hundreds of megabytes waiting for quiet.
#: One release costs 2 to 10 ms and the next frame as much again (measured).
RELEASE_NOW_RETIRED: Final = 512
#: Where the floating mode switch sits over the canvas: clear of the rulers' corner.
_FLOAT_OFFSET: Final = 28
_SPLITTER_KEY: Final = "workspace"
#: The status line's notices, most pressing first. One is shown at a time, and each
#: stays until what it says is over: "building" and "the update failed" until a pass
#: went through, "the engine reported a problem" until that engine is gone.
_NOTICE_BUILDING: Final = "building"
_NOTICE_SYNC: Final = "sync"
_NOTICE_ENGINE: Final = "engine"
_NOTICE_ORDER: Final = (_NOTICE_BUILDING, _NOTICE_SYNC, _NOTICE_ENGINE)
#: The problems list shows at most this many rows (and says how many more there are):
#: a plan can refuse thousands of items — a duplicated id is a reason — and the list
#: is filled on the GUI thread, again whenever the problems change while it is open.
MAX_PROBLEM_ROWS: Final = 200


class WorkspaceMode(enum.Enum):
    PLAN = "plan"
    VIEW3D = "3d"
    SPLIT = "split"


class View3DState(enum.Enum):
    """Where the 3D pane is in its life."""

    NOT_STARTED = "not_started"   # 3D was never asked for (nothing was imported)
    STARTING = "starting"         # the engine is built; no frame was presented yet
    RUNNING = "running"
    UNAVAILABLE = "unavailable"   # Qt could not create the graphics device
    FAILED = "failed"             # building the engine raised (an import, the scene file)


def _now() -> float:
    """The clock "quiet for a moment" is measured on (the tests hold it)."""
    return time.monotonic()


class EngineHost(Protocol):
    """What the workspace needs from the engine's host (``Quick3DHost`` has it all)."""

    def container(self, parent: QWidget | None = None) -> QWidget: ...
    def install_event_filter(self, watcher: QObject) -> None: ...
    def release_cached_resources(self) -> None: ...
    def set_camera(self, eye_scene: tuple[float, float, float],
                   target_scene: tuple[float, float, float], fov_deg: float = ...) -> None: ...
    def view_size(self) -> tuple[float, float]: ...
    def health(self) -> Any: ...
    def close(self) -> None: ...
    # the look (L1.4): ``look_controller.LookHost``
    def set_look(self, look: Any) -> None: ...
    def set_sky(self, sky: Any) -> None: ...
    def set_wind_running(self, running: bool) -> None: ...
    def rest_wind(self) -> None: ...


#: ``factory(prefer_software) -> (host, sink)`` — builds the engine. THE TEST SEAM.
EngineFactory = Callable[[bool], "tuple[EngineHost, EngineSink]"]
LocationProvider = Callable[[], "Mapping[str, Any] | None"]


def _log_failure(what: str, error: BaseException) -> None:
    """ONE line at ERROR — what failed, the exception's type and its message, the
    message normalised and capped — and the traceback at DEBUG only: a traceback's
    last line is the raw message, and ``app.log`` is a file a user sends to
    support (``core/plain_text.py``, §8.11)."""
    _LOG.error("%s (%s: %s)", what, log_text(type(error).__name__), log_text(error))
    _LOG.debug("%s - traceback", what, exc_info=error)


def _command_button(text: str, parent: QWidget) -> QToolButton:
    """A button of the 3D pane's strip: a short command, flat, and never narrower than
    its text (a button cannot wrap; squeezed, it cuts its text with no ellipsis)."""
    button = QToolButton(parent)
    button.setText(text)
    button.setAutoRaise(True)
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    return button


def quick3d_engine(prefer_software: bool) -> tuple[EngineHost, EngineSink]:
    """The production engine: a ``Quick3DHost`` and the ``Quick3DSink`` that drives
    it. Importing the two modules here is what loads Qt Quick 3D — on first use."""
    from .quick3d.adapter import Quick3DSink
    from .quick3d.host import Quick3DHost

    host = Quick3DHost(prefer_software=prefer_software)
    return host, Quick3DSink(host)


class ModeSwitch(QFrame):
    """The segmented control: three buttons that ARE the three mode actions."""

    def __init__(self, actions: list[QAction], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        self.buttons: list[QToolButton] = []
        for action in actions:
            button = QToolButton(self)
            button.setDefaultAction(action)
            button.setAutoRaise(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            layout.addWidget(button)
            self.buttons.append(button)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.adjustSize()


class _Pane3D(QWidget):
    """The 3D side: a strip of controls and notices above the view — or, when there
    is no view, a message in its place. Says when it is shown and hidden.

    The strip has TWO parts, one above the other: a row of controls
    (``strip_layout`` — the mode switch, "Reset 3D View") and, below it, the notices
    (``notice_layout``), one per line. One row for all of it needed 785 px, and in
    Split a 1366 px window gives the pane 455: the last sentence was cut, with no
    ellipsis and no tooltip. So every SENTENCE is a label that wraps its words, and a
    BUTTON holds a short command, is never narrower than its text and, where it
    follows a sentence, has a row of its own (a button cannot wrap: the German
    "try hardware" button alone needed 456 px of text). ``notices`` is hidden while
    it has nothing to say, so the strip is one row high on a healthy machine."""

    showing_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(MIN_PANE_WIDTH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.strip = QWidget(self)
        rows = QVBoxLayout(self.strip)
        rows.setContentsMargins(4, 2, 4, 2)
        rows.setSpacing(2)
        controls = QWidget(self.strip)
        self.strip_layout = QHBoxLayout(controls)
        self.strip_layout.setContentsMargins(0, 0, 0, 0)
        self.strip_layout.setSpacing(6)
        rows.addWidget(controls)
        self.notices = QWidget(self.strip)
        self.notice_layout = QVBoxLayout(self.notices)
        self.notice_layout.setContentsMargins(0, 0, 0, 0)
        self.notice_layout.setSpacing(2)
        rows.addWidget(self.notices)
        self.notices.hide()
        outer.addWidget(self.strip)
        self.body = QStackedWidget(self)
        outer.addWidget(self.body, 1)
        # page 0: a message instead of a view (nothing built yet, or it could not be)
        self.message_page = QWidget(self.body)
        message_layout = QVBoxLayout(self.message_page)
        message_layout.addStretch(1)
        self.message_label = QLabel("", self.message_page)
        # PLAIN text, said out loud: this label shows an exception's message, and a
        # QLabel left on AutoText would render markup found in it (§8.11)
        self.message_label.setTextFormat(Qt.TextFormat.PlainText)
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        message_layout.addWidget(self.message_label)
        self.message_button = QPushButton("", self.message_page)
        self.message_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        message_layout.addWidget(self.message_button, 0, Qt.AlignmentFlag.AlignHCenter)
        message_layout.addStretch(1)
        self.body.addWidget(self.message_page)
        self.engine_widget: QWidget | None = None

    def show_engine(self, widget: QWidget) -> None:
        self.engine_widget = widget
        self.body.addWidget(widget)
        self.body.setCurrentWidget(widget)

    def show_message(self, text: str, button_text: str = "") -> None:
        self.message_label.setText(text)
        self.message_button.setText(button_text)
        self.message_button.setVisible(bool(button_text))
        self.message_button.setEnabled(True)
        self.body.setCurrentWidget(self.message_page)

    def drop_engine(self) -> None:
        widget, self.engine_widget = self.engine_widget, None
        if widget is not None:
            self.body.removeWidget(widget)

    def showEvent(self, event: QShowEvent | None) -> None:  # noqa: N802 - Qt's name
        super().showEvent(event)
        self.showing_changed.emit(True)

    def hideEvent(self, event: QHideEvent | None) -> None:  # noqa: N802 - Qt's name
        super().hideEvent(event)
        self.showing_changed.emit(False)


class Workspace(QWidget):
    """The workspace widget (module docstring). One per main window."""

    mode_changed = pyqtSignal(object)
    #: The 3D pane's state changed (``View3DState``).
    view3d_state_changed = pyqtSignal(object)

    def __init__(self, canvas_view: QWidget, *, engine_factory: EngineFactory | None = None,
                 guard: Init3DGuard | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canvas = canvas_view
        #: THE TEST SEAM: what builds the engine on first use. Replace it BEFORE the
        #: first switch to 3D / Split (``(host, sink) = factory(prefer_software)``).
        self.engine_factory: EngineFactory = engine_factory or quick3d_engine
        self._guard = guard
        self._mode = WorkspaceMode.PLAN
        self._state = View3DState.NOT_STARTED
        self._chrome_visible = True
        self._scene: QGraphicsScene | None = None
        self._clock: SimClock | None = None
        self._location: LocationProvider = lambda: None
        self._ui_state: Any = None
        self._pane: _Pane3D | None = None
        self._host: EngineHost | None = None
        self._controller: Scene3DController | None = None
        self._look: LookController | None = None   # the look of the view (L1.4)
        self._input: OrbitInput | None = None
        self._problems_dialog: View3DProblemsDialog | None = None
        #: The session's one camera: created with the workspace, so its pose survives
        #: hide / show, mode switches and an engine that had to be started again.
        self._camera = OrbitCamera()
        self._camera_stepped_at = 0.0
        self._first_frame_seen = False
        self._qml_warnings_seen = 0
        self._split_sizes: list[int] | None = None
        self._window_watched: QWidget | None = None
        self._build_pending = False   # a first pass waits for its notice to be painted
        self._retired = 0             # items that lost their Models since the last release
        self._applied_at = 0.0        # when the pipeline last worked (``_now``)
        #: What the status line has to say, by kind (``_NOTICE_ORDER``); the first kind
        #: that has a text is shown. A notice stays until what it says is over.
        self._notices: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.addWidget(canvas_view)
        self._splitter.splitterMoved.connect(self._remember_split)
        layout.addWidget(self._splitter)

        self._camera_timer = QTimer(self)
        self._camera_timer.setInterval(CAMERA_STEP_MS)
        self._camera_timer.timeout.connect(self._step_camera)
        self._health_timer = QTimer(self)
        self._health_timer.timeout.connect(self._poll_health)
        # one single-shot timer for both ways a held first pass is let go: 0 ms after
        # its notice was painted, BUILD_NOTICE_WAIT_MS after it was asked for
        self._build_timer = QTimer(self)
        self._build_timer.setSingleShot(True)
        self._build_timer.timeout.connect(self._begin_build)

        self._build_actions()
        # on the widget itself too: the shortcuts work whichever button row is shown
        self.addActions(self.mode_actions())
        self._floating = ModeSwitch(self.mode_actions(), self)
        self._place_floating()

    # ── wiring ───────────────────────────────────────────────────────────────

    def connect_plan(self, scene: QGraphicsScene, clock: SimClock, location: LocationProvider,
                     command_manager: Any = None, ui_state: Any = None) -> None:
        """What the 3D pipeline reads: the canvas scene, the one sim clock, the garden
        location and, optionally, the store the Split position is kept in.

        ``command_manager`` is no longer read: the scene announces every change of
        its plan itself — the undo stack's among them (``CanvasScene.plan_changed``,
        ADR-065 decision 5) — and the pipeline listens to the scene. The parameter
        keeps its place so that a caller written against the first delivery still
        hands ``ui_state`` to ``ui_state``.

        "The document was replaced" has ONE source in the app:
        ``CanvasScene.document_replaced`` (new, open, recovery load — emitted when
        the old document is about to go, and never for an open that FAILED its
        validation). The workspace listens to it here; nobody tells it by hand."""
        del command_manager
        self._scene, self._clock, self._location = scene, clock, location
        self._ui_state = ui_state
        replaced = getattr(scene, "document_replaced", None)  # a CanvasScene has it
        if replaced is not None:
            replaced.connect(self.document_changed)

    def _build_actions(self) -> None:
        self._mode_group = QActionGroup(self)
        self._mode_group.setExclusive(True)
        specs = (
            (WorkspaceMode.PLAN, self.tr("&Plan"), "Alt+1",
             self.tr("Show the plan only")),
            (WorkspaceMode.VIEW3D, self.tr("&3D"), "Alt+2",
             self.tr("Show the garden in 3D")),
            (WorkspaceMode.SPLIT, self.tr("&Split"), "Alt+3",
             self.tr("Show the plan and the 3D view side by side")),
        )
        self._mode_actions: dict[WorkspaceMode, QAction] = {}
        for mode, text, shortcut, tip in specs:
            action = QAction(text, self)
            action.setCheckable(True)
            action.setShortcut(QKeySequence(shortcut))
            action.setStatusTip(tip)
            action.setToolTip(self.tr("{tip} ({shortcut})").format(tip=tip, shortcut=shortcut))
            action.triggered.connect(lambda _checked=False, m=mode: self.set_mode(m))
            self._mode_group.addAction(action)
            self._mode_actions[mode] = action
        self._mode_actions[WorkspaceMode.PLAN].setChecked(True)
        self._reset_action = QAction(self.tr("&Reset 3D View"), self)
        self._reset_action.setStatusTip(self.tr("Show the whole garden in the 3D view again"))
        self._reset_action.setToolTip(self.tr("Show the whole garden again (Home)"))
        self._reset_action.triggered.connect(lambda _checked=False: self.reset_view())
        self._reset_action.setEnabled(False)

    def mode_actions(self) -> list[QAction]:
        """Plan, 3D, Split — checkable and exclusive; the buttons and the menu share them."""
        return [self._mode_actions[mode] for mode in WorkspaceMode]

    @property
    def reset_view_action(self) -> QAction:
        return self._reset_action

    def create_menu(self, parent: QWidget | None = None) -> QMenu:
        """The View menu's entry: a submenu with the three modes and "Reset 3D View"."""
        menu = QMenu(self.tr("&Workspace"), parent)
        menu.addActions(self.mode_actions())
        menu.addSeparator()
        menu.addAction(self._reset_action)
        return menu

    # ── reads ────────────────────────────────────────────────────────────────

    @property
    def mode(self) -> WorkspaceMode:
        return self._mode

    @property
    def view3d_state(self) -> View3DState:
        return self._state

    @property
    def camera(self) -> OrbitCamera:
        return self._camera

    @property
    def controller(self) -> Scene3DController | None:
        """The sync controller — None until 3D was first opened (and after a failed start)."""
        return self._controller

    @property
    def host(self) -> EngineHost | None:
        return self._host

    @property
    def look(self) -> LookController | None:
        """The look controller — None until 3D was first opened (L1.4)."""
        return self._look

    def apply_look_settings(self) -> None:
        """The 3D settings changed (the Preferences dialog was accepted): the look
        follows — quality and reduced motion. Nothing to do before 3D was opened:
        the look controller reads the settings when it is built."""
        if self._look is not None:
            self._look.reload_settings()

    @property
    def guard(self) -> Init3DGuard:
        if self._guard is None:
            self._guard = Init3DGuard(default_directory())
        return self._guard

    @property
    def splitter(self) -> QSplitter:
        return self._splitter

    @property
    def pane(self) -> QWidget | None:
        """The 3D pane (None until it was first asked for)."""
        return self._pane

    def status_text(self) -> str:
        return self._status_label.text() if self._pane is not None else ""

    def message_text(self) -> str:
        """The message shown INSTEAD of the 3D view ("" while a view is shown)."""
        pane = self._pane
        if pane is None or pane.body.currentWidget() is not pane.message_page:
            return ""
        return pane.message_label.text()

    def compat_text(self) -> str:
        if self._pane is None or self._compat_label.isHidden():
            return ""
        return self._compat_label.text()

    def problems_text(self) -> str:
        if self._pane is None or self._problems_row.isHidden():
            return ""
        return self._problems_label.text()

    # ── modes ────────────────────────────────────────────────────────────────

    def set_mode(self, mode: WorkspaceMode) -> None:
        self._mode_actions[mode].setChecked(True)
        if mode is self._mode:
            return
        if self._mode is WorkspaceMode.SPLIT:
            # leaving Split: its position is remembered for this session AND kept for
            # the next one, now — while the splitter still has both sides (it used to
            # be saved only by an app that was closed in Split)
            self._remember_split()
            self.save_state()
        self._mode = mode
        if mode is WorkspaceMode.VIEW3D:
            self.clear_selection_hidden_by_3d_mode()
        if mode is not WorkspaceMode.PLAN:
            self._ensure_pane()
        pane = self._pane
        # show before hide: the splitter is never without a visible side
        if mode is not WorkspaceMode.VIEW3D:
            self._canvas.setVisible(True)
        if pane is not None:
            pane.setVisible(mode is not WorkspaceMode.PLAN)
            self._pane_switch.setVisible(mode is WorkspaceMode.VIEW3D)
        if mode is WorkspaceMode.VIEW3D:
            self._canvas.setVisible(False)
        if mode is WorkspaceMode.SPLIT:
            self._apply_split()
        self._place_floating()
        self.mode_changed.emit(mode)

    def clear_selection_hidden_by_3d_mode(self) -> None:
        """3D mode hides the canvas — the one place a selection is SHOWN — and keeps
        every shortcut: Delete, Ctrl+X and Ctrl+D would act on items nobody can see.
        So entering 3D mode clears the selection.

        A STOPGAP WITH AN OWNER: the selection story (L1.8) shows the selection in the
        3D view itself; when its ring exists it removes this function (and its one
        call, in ``set_mode``) or replaces it. Split is not touched: there the canvas
        still shows what is selected."""
        scene = self._scene
        if scene is not None:
            scene.clearSelection()

    def set_chrome_visible(self, visible: bool) -> None:
        """Fullscreen preview hides the workspace's own controls with the rest of the UI."""
        self._chrome_visible = visible
        if self._pane is not None:
            self._pane.strip.setVisible(visible)
        self._place_floating()

    def reset_view(self) -> None:
        """Frame the whole plan again (the camera glides there)."""
        controller = self._controller
        if controller is None:
            return
        self._camera.frame(controller.plan_bounds(), self._aspect())
        self._start_camera()

    def _place_floating(self) -> None:
        visible = self._chrome_visible and self._mode is not WorkspaceMode.VIEW3D
        self._floating.setVisible(visible)
        if visible:
            self._floating.move(_FLOAT_OFFSET, _FLOAT_OFFSET)
            self._floating.raise_()

    def _apply_split(self) -> None:
        sizes = self._split_sizes
        if sizes is None and self._ui_state is not None and self._ui_state.restore_splitter(
                _SPLITTER_KEY, self._splitter):
            sizes = self._splitter.sizes()
        if sizes is None or len(sizes) != 2 or min(sizes) <= 0:
            half = max(self._splitter.width() // 2, MIN_PANE_WIDTH)
            sizes = [half, half]
        self._splitter.setSizes(sizes)
        self._split_sizes = self._splitter.sizes()

    def _remember_split(self, *_arguments: object) -> None:
        if self._mode is WorkspaceMode.SPLIT and self._pane is not None:
            self._split_sizes = self._splitter.sizes()

    def save_state(self) -> None:
        """Keep the Split position for the next session. Only a real Split is kept:
        called while the mode IS Split — when it is left (``set_mode``) and when the
        app closes in it — and a no-op in the other two modes, whose splitter has one
        side hidden."""
        if (self._ui_state is not None and self._pane is not None
                and self._mode is WorkspaceMode.SPLIT):
            self._ui_state.save_splitter(_SPLITTER_KEY, self._splitter)

    # ── the 3D pane, built on first use ──────────────────────────────────────

    def _ensure_pane(self) -> None:
        if self._pane is None:
            self._build_pane()
        if self._state is View3DState.NOT_STARTED:
            self._start_engine()

    def _build_pane(self) -> None:
        pane = _Pane3D(self._splitter)
        # the row of controls
        strip = pane.strip_layout
        self._pane_switch = ModeSwitch(self.mode_actions(), pane.strip)
        strip.addWidget(self._pane_switch)
        self._reset_button = QToolButton(pane.strip)
        self._reset_button.setDefaultAction(self._reset_action)
        self._reset_button.setAutoRaise(True)
        self._reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        strip.addWidget(self._reset_button)
        strip.addStretch(1)
        # the notices, one per line; every sentence wraps (class docstring of the pane)
        notices = pane.notice_layout
        status = QLabel("", pane.notices)
        status.setTextFormat(Qt.TextFormat.PlainText)
        status.setWordWrap(True)
        status.installEventFilter(self)  # its paint starts a held first pass
        status.hide()
        notices.addWidget(status)
        self._status_label = status
        # what 3D could not show: the sentence wraps; "Show List" opens the list
        self._problems_row = QWidget(pane.notices)
        problems = QHBoxLayout(self._problems_row)
        problems.setContentsMargins(0, 0, 0, 0)
        problems.setSpacing(6)
        self._problems_label = QLabel("", self._problems_row)
        self._problems_label.setTextFormat(Qt.TextFormat.PlainText)
        self._problems_label.setWordWrap(True)
        problems.addWidget(self._problems_label, 1)
        self._problems_button = _command_button(self.tr("Show List"), self._problems_row)
        self._problems_button.setToolTip(self.tr("Show which objects are missing from the 3D view"))
        self._problems_button.clicked.connect(self.show_problems)
        problems.addWidget(self._problems_button, 0, Qt.AlignmentFlag.AlignTop)
        self._problems_row.hide()
        notices.addWidget(self._problems_row)
        # the compatibility line, and below it — a row of its own — the way back
        self._compat_label = QLabel("", pane.notices)
        self._compat_label.setTextFormat(Qt.TextFormat.PlainText)
        self._compat_label.setWordWrap(True)
        self._compat_label.hide()
        notices.addWidget(self._compat_label)
        self._compat_button = _command_button("", pane.notices)
        self._compat_button.clicked.connect(self._on_compat_button)
        self._compat_button.hide()
        notices.addWidget(self._compat_button, 0, Qt.AlignmentFlag.AlignLeft)
        pane.message_button.clicked.connect(self._on_message_button)
        pane.showing_changed.connect(self._on_pane_showing)
        pane.strip.setVisible(self._chrome_visible)
        pane.hide()
        self._splitter.addWidget(pane)
        self._splitter.setCollapsible(self._splitter.indexOf(pane), False)
        self._pane = pane

    def _start_engine(self) -> None:
        """Build the engine and the pipeline — the first time 3D is asked for, and
        again after "Try again". Opening 3D never takes the 2D app down: whatever
        this raises becomes a message in the pane."""
        pane, scene, clock = self._pane, self._scene, self._clock
        if pane is None:
            return
        if scene is None or clock is None:
            _LOG.error("The 3D workspace was asked for 3D before connect_plan() gave it a plan")
            return
        guard = self.guard
        mode = guard.begin()
        if mode is RenderMode.OFF:
            # a start in software mode died too: nothing is left to fall back to, and
            # trying again would be the same death. The way back is in the strip.
            self._set_state(View3DState.UNAVAILABLE)
            pane.show_message(self.tr(
                "3D is switched off on this computer: it did not start, not even in "
                "compatibility mode (software rendering). The rest of the application is "
                "not affected."))
            self._update_compat_notice()
            return
        software = mode is RenderMode.SOFTWARE
        host: EngineHost | None = None
        orbit: OrbitInput | None = None
        look: LookController | None = None
        try:
            from .look_controller import LookController
            from .orbit_input import OrbitInput
            from .sync_controller import Scene3DController

            host, sink = self.engine_factory(software)
            container = host.container(pane)
            orbit = OrbitInput(self._camera, self._view_height, parent=self)
            host.install_event_filter(orbit)
            # the look (L1.4): the render mode decides sky, wind and the automatic
            # preset together — in compatibility mode no sky (a light probe costs
            # seconds there), no wind (an animated view renders continuously) and
            # ``auto`` = low (ADR-064 addendum)
            look = LookController.from_settings(host, software=software, parent=self)
            controller = Scene3DController(scene, clock, self._location, sink, parent=self)
        except Exception as error:  # noqa: BLE001 - an import, the scene file, anything
            guard.init_failed()
            _log_failure("The 3D view could not be started", error)
            if look is not None:
                look.shutdown()
                look.deleteLater()
            if orbit is not None:
                orbit.deleteLater()
            if host is not None:
                self._close_host(host)
            self._set_state(View3DState.FAILED)
            pane.show_message(
                self.tr("The 3D view could not be started. The rest of the application "
                        "is not affected.\n\nDetails: {error}").format(error=clip_text(error)),
                self.tr("Try Again"))
            # "Try Again" asks for the same mode again. When that mode is compatibility
            # mode, the way back to the graphics card must be on screen here too.
            self._update_compat_notice()
            return
        self._host, self._controller, self._input = host, controller, orbit
        self._look = look
        orbit.moved.connect(self._start_camera)
        orbit.reset_requested.connect(self.reset_view)
        controller.applied.connect(self._on_applied)
        controller.problems_changed.connect(self._update_problems)
        controller.document_shown.connect(self._on_document_shown)
        controller.failed.connect(self._on_sync_failed)
        pane.show_engine(container)
        self._first_frame_seen = False
        self._qml_warnings_seen = 0
        self._reset_action.setEnabled(True)
        self._set_state(View3DState.STARTING)
        self._update_compat_notice()
        self._watch_window()
        self._on_pane_showing(pane.isVisible())

    # ── shown / hidden ───────────────────────────────────────────────────────

    def _pane_is_showing(self) -> bool:
        pane = self._pane
        if pane is None or not pane.isVisible():
            return False
        window = self.window()
        return not (window is not None and window.isMinimized())

    def _on_pane_showing(self, _shown: bool = False) -> None:
        showing = self._pane_is_showing()
        if self._look is not None:
            self._look.set_showing(showing)  # wind and frame sampling: only while shown
        controller = self._controller
        if controller is None or self._host is None:
            self._health_timer.stop()
            self._camera_timer.stop()
            self._drop_held_build()
            return
        if not showing:
            self._drop_held_build()
            controller.set_active(False)
            self._health_timer.stop()
            self._camera_timer.stop()
            if not self._first_frame_seen:
                # The poll that confirms the first frame has just stopped. A start
                # marker left on disk now would be read as a death by a second
                # instance ten minutes from here (``init_guard``): take it away …
                self.guard.abandon()
            return
        if not self._first_frame_seen:
            self.guard.mark_again()  # … and put it back while a first frame is awaited
        self._health_timer.start(HEALTH_SLOW_MS if self._first_frame_seen else HEALTH_FAST_MS)
        self._apply_camera()
        self._start_camera()
        if controller.active or self._build_pending:
            return
        if controller.dirty:
            self._announce_build()  # a pass is owed: its notice is painted first
        else:
            controller.set_active(True)

    def _announce_build(self) -> None:
        """Say "Building the 3D view…" and start the pipeline only once that was
        PAINTED (module docstring). The controller stays paused until then."""
        controller = self._controller
        if controller is None or self._build_pending:
            return
        self._say(_NOTICE_BUILDING, self.tr("Building the 3D view…"))
        label = self._status_label
        if not label.isVisible():
            # the controls are hidden (fullscreen preview): there is no notice to wait for
            controller.set_active(True)
            return
        self._build_pending = True
        label.update()
        self._build_timer.start(BUILD_NOTICE_WAIT_MS)

    def _begin_build(self) -> None:
        """The notice was painted (or will not be): let the held pass go."""
        if not self._build_pending:
            return
        self._drop_held_build()
        controller = self._controller
        if controller is not None and self._pane_is_showing():
            controller.set_active(True)

    def _drop_held_build(self) -> None:
        self._build_pending = False
        self._build_timer.stop()

    # ── the status line: one notice at a time, each until what it says is over ──

    def _say(self, kind: str, text: str) -> None:
        """Set one notice of the status line — or, with an empty text, withdraw it."""
        if text:
            self._notices[kind] = text
        else:
            self._notices.pop(kind, None)
        self._refresh_notices()

    def _refresh_notices(self) -> None:
        """Show the first notice that has something to say (``_NOTICE_ORDER``), and the
        notices' part of the strip only while anything in it does."""
        pane = self._pane
        if pane is None:
            return
        text = next((self._notices[kind] for kind in _NOTICE_ORDER if kind in self._notices), "")
        label = self._status_label
        if label.text() != text:
            label.setText(text)
        label.setVisible(bool(text))
        pane.notices.setVisible(bool(text) or not (
            self._problems_row.isHidden() and self._compat_label.isHidden()
            and self._compat_button.isHidden()))

    def _watch_window(self) -> None:
        window = self.window()
        if window is not None and window is not self._window_watched:
            if self._window_watched is not None:
                self._window_watched.removeEventFilter(self)
            window.installEventFilter(self)
            self._window_watched = window

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        if event is None:
            return False
        # a minimised window still calls its children "visible": the pipeline pauses anyway
        if watched is self._window_watched and event.type() == QEvent.Type.WindowStateChange:
            self._on_pane_showing()
        elif (self._build_pending and event.type() == QEvent.Type.Paint
              and watched is self._status_label):
            # A filter runs BEFORE the label paints. The held pass starts from the
            # event loop — after this paint, and the flush that follows it, are done.
            self._build_timer.start(0)
        return False

    # ── camera ───────────────────────────────────────────────────────────────

    def _view_height(self) -> float:
        host = self._host
        if host is None:
            return 0.0
        try:
            return float(host.view_size()[1])
        except Exception:  # noqa: BLE001 - a host that is gone has no size
            return 0.0

    def _aspect(self) -> float:
        host = self._host
        if host is not None:
            try:
                width, height = host.view_size()
                if width > 0.0 and height > 0.0:
                    return float(width) / float(height)
            except Exception:  # noqa: BLE001 - as above
                _LOG.debug("3D workspace: no view size for the aspect", exc_info=True)
        return 16.0 / 9.0

    def _apply_camera(self) -> None:
        host = self._host
        if host is None:
            return
        pose = self._camera.pose
        try:
            host.set_camera(pose.eye, pose.target_scene, FOV_DEG)
        except Exception:  # noqa: BLE001 - the health poll reports a host that died
            _LOG.debug("3D workspace: the camera could not be set", exc_info=True)

    def _start_camera(self) -> None:
        if self._camera.moving and self._pane_is_showing() and not self._camera_timer.isActive():
            self._camera_stepped_at = time.perf_counter()
            self._camera_timer.start()

    def _step_camera(self) -> None:
        now = time.perf_counter()
        moving = self._camera.step(now - self._camera_stepped_at)
        self._camera_stepped_at = now
        self._apply_camera()
        if not moving or not self._pane_is_showing():
            self._camera_timer.stop()  # at rest: no idle wake-ups

    def _on_document_shown(self) -> None:
        """The first pass of a document is in the engine: frame it, at once."""
        controller = self._controller
        if controller is None:
            return
        self._camera.frame(controller.plan_bounds(), self._aspect(), snap=True)
        self._apply_camera()

    # ── the pipeline's reports ───────────────────────────────────────────────

    def document_changed(self) -> None:
        """A new, opened or recovered plan replaces the scene's content — the slot of
        ``CanvasScene.document_replaced`` (``connect_plan``).

        The signal comes when the OLD document is about to go, so nothing is read
        from the scene here: this sets flags, and the pass they ask for runs with a
        later turn of the event loop, when the new document is in the scene. While
        3D is shown, that first pass is held like the very first one: it costs the
        sum of the plan's items, so its notice is painted first. While 3D is hidden
        this leaves flags only (the controller is paused). An open that fails its
        validation never gets here: the view, its camera and what it remembers of
        the plan stay as they were."""
        controller = self._controller
        if controller is None:
            return
        controller.document_changed()
        if controller.active and self._pane_is_showing():
            controller.set_active(False)  # whatever pass is on its way finds it paused
            self._announce_build()

    def location_changed(self, *_arguments: object) -> None:
        if self._controller is not None:
            self._controller.refresh_sun()

    def _on_applied(self, report: TickReport) -> None:
        # the look follows the sun the PIPELINE sent — the same pass, the same sun
        if self._look is not None and self._controller is not None:
            self._look.set_sun(self._controller.sync.sun)
        # A pass went through: the build is over, and so is a failed update. What the
        # ENGINE reported is not: that notice stays until the engine is gone (it used
        # to be erased by the next pass — one edit, and the only sign of it was lost).
        self._notices.pop(_NOTICE_BUILDING, None)
        self._notices.pop(_NOTICE_SYNC, None)
        self._refresh_notices()
        self._applied_at = _now()
        self._retired += report.retired
        if self._retired >= RELEASE_NOW_RETIRED:
            self._release_engine_caches()  # a flood: not worth waiting for quiet

    def _release_engine_caches(self) -> None:
        """Tell the engine to let go of the graphics state Qt keeps for Models that
        were destroyed (module docstring). The count starts again whatever the host
        says: a host that cannot release is asked once per threshold, never in a loop."""
        host = self._host
        self._retired = 0
        if host is None:
            return
        try:
            host.release_cached_resources()
        except Exception as error:  # noqa: BLE001 - memory hygiene must never take the view down
            _log_failure("The 3D view could not release its cached graphics state", error)

    def _on_sync_failed(self, _message: str) -> None:
        self._say(_NOTICE_SYNC, self.tr(
            "The 3D view could not be updated. It will try again with the next change."))

    def _update_problems(self) -> None:
        controller = self._controller
        count = controller.problem_count if controller is not None else 0
        if count == 0:
            self._problems_row.hide()
        else:
            text = (self.tr("1 object is not shown in 3D") if count == 1
                    else self.tr("{count} objects are not shown in 3D").format(count=count))
            self._problems_label.setText(text)
            self._problems_row.show()
        self._refresh_notices()
        dialog = self._problems_dialog
        if dialog is not None and dialog.isVisible():
            self._fill_problems(dialog)

    def show_problems(self) -> None:
        """Open (or raise) the list of what 3D could not show."""
        from .problems_dialog import View3DProblemsDialog

        dialog = self._problems_dialog
        if dialog is None:
            dialog = View3DProblemsDialog(self)
            dialog.item_chosen.connect(self.select_item)
            self._problems_dialog = dialog
        self._fill_problems(dialog)
        dialog.show()
        dialog.raise_()

    @property
    def problems_dialog(self) -> View3DProblemsDialog | None:
        return self._problems_dialog

    def _fill_problems(self, dialog: View3DProblemsDialog) -> None:
        """Fill the list: at most ``MAX_PROBLEM_ROWS`` rows, and ONE walk over the scene
        for all their names. (It looked every row's item up by walking the scene: rows
        x items on the GUI thread, again on every change while the list was open —
        3,000 rows over 3,000 items took 3.1 s, and one plan with duplicated ids is
        enough to get them.)"""
        from .problems_dialog import problems_of

        controller = self._controller
        if controller is None:
            dialog.set_problems((), lambda _item_id: "")
            return
        problems = problems_of(controller.skipped, controller.failures)
        wanted = {problem.item_id for problem in problems[:MAX_PROBLEM_ROWS]}
        names: dict[str, str] = {}
        scene = self._scene
        if scene is not None and wanted:
            for item in scene.items():
                item_id = str(getattr(item, "item_id", ""))
                if item_id in wanted and item_id not in names:  # the topmost of a duplicated id
                    names[item_id] = str(getattr(item, "name", "") or "")
        dialog.set_problems(problems, lambda item_id: names.get(item_id, ""),
                            max_rows=MAX_PROBLEM_ROWS)

    def _find_item(self, item_id: str) -> Any:
        scene = self._scene
        if scene is None:
            return None
        for item in scene.items():
            if str(getattr(item, "item_id", "")) == item_id:
                return item
        return None

    def select_item(self, item_id: str) -> None:
        """Select the item on the plan (a row of the problems list was activated)."""
        scene, item = self._scene, self._find_item(item_id)
        if scene is None or item is None:
            return
        if self._mode is WorkspaceMode.VIEW3D:
            # the plan is hidden in 3D mode, and a selection nobody can see is what
            # ``clear_selection_hidden_by_3d_mode`` exists to prevent: show the plan
            self.set_mode(WorkspaceMode.SPLIT)
        scene.clearSelection()
        item.setSelected(True)
        center_on = getattr(self._canvas, "centerOn", None)
        if callable(center_on) and self._canvas.isVisible():
            center_on(item)

    # ── health: first frame, graphics failure, QML warnings ──────────────────

    def _poll_health(self) -> None:
        host = self._host
        if host is None:
            self._health_timer.stop()
            return
        health = host.health()
        error = getattr(health, "scene_graph_error", None)
        if error:
            self._graphics_failed(str(error))
            return
        if not self._first_frame_seen and int(getattr(health, "frames_presented", 0)) >= 1:
            self._first_frame_seen = True
            self.guard.confirm_first_frame()
            self._set_state(View3DState.RUNNING)
            self._health_timer.setInterval(HEALTH_SLOW_MS)
        warnings = int(getattr(health, "qml_warning_count", 0))
        if warnings > self._qml_warnings_seen:
            self._qml_warnings_seen = warnings
            self._say(_NOTICE_ENGINE, self.tr(
                "The 3D view reported a problem. Details are in the log file."))
        if (self._retired >= RELEASE_AFTER_RETIRED and self._pane_is_showing()
                and _now() - self._applied_at >= RELEASE_IDLE_S):
            self._release_engine_caches()

    def _graphics_failed(self, error: str) -> None:
        """Qt could not create the graphics device: this host will never show a frame.
        Not a crash — the marker goes; the view is closed for the session, no retry."""
        guard, pane = self.guard, self._pane
        guard.graphics_failed()
        _LOG.error("3D is unavailable on this graphics device: %s", log_text(error))
        self._stop_engine()
        self._set_state(View3DState.UNAVAILABLE)
        if pane is None:
            return
        offer = guard.mode is RenderMode.HARDWARE and not guard.software_requested()
        pane.show_message(
            self.tr("3D is unavailable on this graphics device. The rest of the application "
                    "is not affected.\n\nDetails: {error}").format(error=clip_text(error)),
            self.tr("Use Compatibility Mode Next Time") if offer else "")
        self._update_compat_notice()

    def _update_compat_notice(self) -> None:
        """The compatibility line of the strip, and "Try Hardware Next Time".

        Shown in EVERY state of the pane — running, failed to start, no graphics
        device, switched off — whenever this session does not render on the graphics
        card or the next one will not (the compat flag is on). The button is there
        whenever the flag is: a machine that cannot start in software mode either had
        no way back otherwise (only "Try Again", which asked for software again)."""
        if self._pane is None:
            return
        guard = self.guard
        flagged = guard.software_requested()
        died = guard.reason is ModeReason.PREVIOUS_START_DIED
        running = self._state in (View3DState.STARTING, View3DState.RUNNING)
        if guard.mode is RenderMode.SOFTWARE and running:
            text = (self.tr("3D is running in compatibility mode (software rendering) because "
                            "it did not start properly last time.") if died
                    else self.tr("3D is running in compatibility mode (software rendering)."))
        elif guard.mode is RenderMode.SOFTWARE:  # … and it did not get as far as running
            text = self.tr("Compatibility mode (software rendering) is switched on.")
        elif guard.mode is RenderMode.OFF:
            text = self.tr("3D is switched off: it did not start in compatibility mode "
                           "(software rendering) either.")
        elif flagged:  # this session is on the graphics card; the next one will not be
            text = self.tr("Compatibility mode will be used the next time the application starts.")
        else:
            self._hide_compat_notice()
            return
        self._compat_label.setText(text)
        self._compat_label.show()
        self._compat_button.setText(self.tr("Try Hardware Next Time"))
        self._compat_button.setVisible(flagged)
        self._refresh_notices()

    def _hide_compat_notice(self) -> None:
        self._compat_label.hide()
        self._compat_button.hide()
        self._refresh_notices()

    def _on_compat_button(self) -> None:
        """"Try Hardware Next Time": say what really happened to the flag."""
        if self.guard.try_hardware_next_time():
            self._compat_button.hide()
            self._compat_label.setText(self.tr(
                "Hardware rendering will be tried the next time the application starts."))
            self._compat_label.show()
            self._refresh_notices()
        else:  # the flag is still there (a folder that cannot be written): the button stays
            self._say_the_setting_was_not_changed()

    def _say_the_setting_was_not_changed(self) -> None:
        """One of the two switches could not write its file: say so in the strip (the
        log has why). The button that asked stays, so the user can try again."""
        self._compat_label.setText(self.tr(
            "The setting could not be changed. Details are in the log file."))
        self._compat_label.show()
        self._refresh_notices()

    def _on_message_button(self) -> None:
        pane = self._pane
        if pane is None:
            return
        if self._state is View3DState.FAILED:
            self._set_state(View3DState.NOT_STARTED)
            self._start_engine()
        elif self._state is View3DState.UNAVAILABLE:
            # What came of it is said in the strip, whose sentences wrap — never on the
            # button: a button cannot wrap, and a sentence on it made the pane as wide
            # as the sentence.
            if self.guard.use_software_next_time():
                pane.message_button.hide()
                # "Compatibility mode will be used …", with the way back beside it
                self._update_compat_notice()
            else:
                self._say_the_setting_was_not_changed()

    # ── teardown ─────────────────────────────────────────────────────────────

    def _close_host(self, host: EngineHost) -> None:
        try:
            host.close()
        except Exception as error:  # noqa: BLE001 - closing must never stop a shutdown
            _log_failure("3D workspace: the engine host did not close cleanly", error)

    def _stop_engine(self) -> None:
        self._camera_timer.stop()
        self._health_timer.stop()
        self._drop_held_build()
        self._retired = 0  # the host goes, and what it cached with it
        self._notices.clear()  # … and whatever the status line said about it
        self._refresh_notices()
        look, self._look = self._look, None
        if look is not None:
            look.shutdown()
            look.deleteLater()
        controller, self._controller = self._controller, None
        if controller is not None:
            controller.shutdown()
            controller.deleteLater()
        host, self._host = self._host, None
        orbit, self._input = self._input, None
        if orbit is not None:
            orbit.deleteLater()
        if self._pane is not None:
            self._pane.drop_engine()
        if host is not None:
            self._close_host(host)
        self._reset_action.setEnabled(False)

    def shutdown(self) -> None:
        """The main window is closing. Order: the pipeline stops, the pending start
        marker goes (a clean close is not a crash), the host destroys its Models
        and its window — while the main window still exists."""
        self.save_state()
        if self._guard is not None:
            self._guard.abandon()
        dialog, self._problems_dialog = self._problems_dialog, None
        if dialog is not None:
            dialog.close()
        self._stop_engine()
        if self._window_watched is not None:
            self._window_watched.removeEventFilter(self)
            self._window_watched = None

    def _set_state(self, state: View3DState) -> None:
        if state is not self._state:
            self._state = state
            self.view3d_state_changed.emit(state)
