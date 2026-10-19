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

Selection, the info card and walk mode (L1.8) are the class's last section. There is
ONE selection — the canvas scene's: a click in the 3D view becomes a canvas
selection by the canvas's own rules, the canvas's selection becomes the ring in 3D
and the card BELOW the view. Walk mode is a second source for ``_apply_camera``
(the walker's eye instead of the orbit pose) and touches nothing else — not the
orbit camera, not the plan, not the undo stack.

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
A click that picks (L1.8) is a user's own action, once — and it is made in
``orbit_input.py``, nowhere else. Pinned by a scan of this package's modules and by
a stand-in host that records such calls.

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
    QComboBox,
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
    from open_garden_planner.core.scene3d.walk import WalkWorld
    from open_garden_planner.core.sim_clock import SimClock

    from .info_card import CardSubject, View3DCardSlot, View3DInfoCard
    from .orbit_input import OrbitInput
    from .problems_dialog import View3DProblemsDialog
    from .sync_controller import Scene3DController, TickReport
    from .walk_mode import WalkMode

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
    def focus(self) -> None: ...
    def has_focus(self) -> bool: ...
    def release_cached_resources(self) -> None: ...
    def set_camera(self, eye_scene: tuple[float, float, float],
                   target_scene: tuple[float, float, float], fov_deg: float = ...) -> None: ...
    def view_size(self) -> tuple[float, float]: ...
    def health(self) -> Any: ...
    def close(self) -> None: ...


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
    is no view, a message in its place. Says when it is shown and hidden."""

    showing_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(MIN_PANE_WIDTH)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.strip = QWidget(self)
        self.strip_layout = QHBoxLayout(self.strip)
        self.strip_layout.setContentsMargins(4, 2, 4, 2)
        self.strip_layout.setSpacing(6)
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
        self._command_manager: Any = None
        self._ui_state: Any = None
        self._pane: _Pane3D | None = None
        self._host: EngineHost | None = None
        self._controller: Scene3DController | None = None
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
        self._init_selection_and_walk()  # L1.8: its state and the Walk action
        # on the widget itself too: the shortcuts work whichever button row is shown
        self.addActions(self.mode_actions())
        self._floating = ModeSwitch(self.mode_actions(), self)
        self._place_floating()

    # ── wiring ───────────────────────────────────────────────────────────────

    def connect_plan(self, scene: QGraphicsScene, clock: SimClock, location: LocationProvider,
                     command_manager: Any, ui_state: Any = None) -> None:
        """What the 3D pipeline reads: the canvas scene, the one sim clock, the garden
        location, the undo stack (its ``stack_changed`` marks the plan dirty) and,
        optionally, the store the Split position is kept in.

        "The document was replaced" has ONE source in the app:
        ``CanvasScene.document_replaced`` (new, open, recovery load — emitted when
        the old document is about to go, and never for an open that FAILED its
        validation). The workspace listens to it here; nobody tells it by hand."""
        self._scene, self._clock, self._location = scene, clock, location
        self._command_manager, self._ui_state = command_manager, ui_state
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
        if self._pane is None or self._problems_button.isHidden():
            return ""
        return self._problems_button.text()

    # ── modes ────────────────────────────────────────────────────────────────

    def set_mode(self, mode: WorkspaceMode) -> None:
        self._mode_actions[mode].setChecked(True)
        if mode is self._mode:
            return
        if self._mode is WorkspaceMode.SPLIT:
            self._remember_split()
        self._mode = mode
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

    def set_chrome_visible(self, visible: bool) -> None:
        """Fullscreen preview hides the workspace's own controls with the rest of the UI."""
        self._chrome_visible = visible
        if self._pane is not None:
            self._pane.strip.setVisible(visible)
        self._place_floating()
        self._refresh_card()  # L1.8: the card is one of the pane's controls

    def reset_view(self) -> None:
        """Frame the whole plan again (the camera glides there). Asked while walking,
        it leaves walk mode first: "show the whole garden" is the orbit view's."""
        controller = self._controller
        if controller is None:
            return
        self.set_walking(False)
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
        """Keep the Split position for the next session (only a real Split is kept)."""
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
        strip = pane.strip_layout
        self._pane_switch = ModeSwitch(self.mode_actions(), pane.strip)
        strip.addWidget(self._pane_switch)
        self._reset_button = QToolButton(pane.strip)
        self._reset_button.setDefaultAction(self._reset_action)
        self._reset_button.setAutoRaise(True)
        self._reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        strip.addWidget(self._reset_button)
        self._build_walk_controls(pane)  # L1.8: the Walk toggle and the eye height
        status = QLabel("", pane.strip)
        status.setTextFormat(Qt.TextFormat.PlainText)
        status.installEventFilter(self)  # its paint starts a held first pass
        strip.addWidget(status)
        self._status_label = status
        strip.addStretch(1)
        self._problems_button = QToolButton(pane.strip)
        self._problems_button.setAutoRaise(True)
        self._problems_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._problems_button.setToolTip(self.tr("Show which objects are missing from the 3D view"))
        self._problems_button.clicked.connect(self.show_problems)
        self._problems_button.hide()
        strip.addWidget(self._problems_button)
        self._compat_label = QLabel("", pane.strip)
        self._compat_label.setTextFormat(Qt.TextFormat.PlainText)
        self._compat_label.hide()
        strip.addWidget(self._compat_label)
        self._compat_button = QToolButton(pane.strip)
        self._compat_button.setAutoRaise(True)
        self._compat_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._compat_button.clicked.connect(self._on_compat_button)
        self._compat_button.hide()
        strip.addWidget(self._compat_button)
        pane.message_button.clicked.connect(self._on_message_button)
        pane.showing_changed.connect(self._on_pane_showing)
        pane.strip.setVisible(self._chrome_visible)
        pane.hide()
        self._splitter.addWidget(pane)
        self._splitter.setCollapsible(self._splitter.indexOf(pane), False)
        self._build_card(pane)  # L1.8: the info card, BELOW the view
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
        software = guard.begin() is RenderMode.SOFTWARE
        host: EngineHost | None = None
        orbit: OrbitInput | None = None
        try:
            from .orbit_input import OrbitInput
            from .sync_controller import Scene3DController

            host, sink = self.engine_factory(software)
            container = host.container(pane)
            orbit = OrbitInput(self._camera, self._view_height, parent=self)
            host.install_event_filter(orbit)
            controller = Scene3DController(scene, clock, self._location, sink, parent=self)
        except Exception as error:  # noqa: BLE001 - an import, the scene file, anything
            guard.init_failed()
            _log_failure("The 3D view could not be started", error)
            if orbit is not None:
                orbit.deleteLater()
            if host is not None:
                self._close_host(host)
            self._set_state(View3DState.FAILED)
            pane.show_message(
                self.tr("The 3D view could not be started. The rest of the application "
                        "is not affected.\n\nDetails: {error}").format(error=clip_text(error)),
                self.tr("Try Again"))
            return
        self._host, self._controller, self._input = host, controller, orbit
        orbit.moved.connect(self._start_camera)
        orbit.reset_requested.connect(self.reset_view)
        self._wire_selection(host, orbit, controller)  # L1.8: the click, the ring, the card
        if self._command_manager is not None:
            self._command_manager.stack_changed.connect(controller.mark_dirty)
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
            return
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
        label = self._status_label
        label.setText(self.tr("Building the 3D view…"))
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
        walk = self._walk
        if walk is not None and walk.active:
            eye, target, fov = walk.camera()  # L1.8: the walker's eye; the orbit pose rests
        else:
            pose = self._camera.pose
            eye, target, fov = pose.eye, pose.target_scene, FOV_DEG
        try:
            host.set_camera(eye, target, fov)
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
        self.set_walking(False)  # L1.8: the walker's world is gone with the document
        controller.document_changed()
        # … and so is what was selected. NOT read from the scene: the old items are
        # still in it (and still selected) when the signal comes. The new document
        # starts with nothing selected; a selection made in it arrives as the canvas's
        # own selectionChanged, and the card is refreshed with the document's first pass.
        controller.set_selection(())
        if controller.active and self._pane_is_showing():
            controller.set_active(False)  # whatever pass is on its way finds it paused
            self._announce_build()

    def location_changed(self, *_arguments: object) -> None:
        if self._controller is not None:
            self._controller.refresh_sun()

    def _on_applied(self, report: TickReport) -> None:
        self._status_label.setText("")
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
        self._status_label.setText(self.tr(
            "The 3D view could not be updated. It will try again with the next change."))

    def _update_problems(self) -> None:
        controller = self._controller
        count = controller.problem_count if controller is not None else 0
        if count == 0:
            self._problems_button.hide()
        else:
            text = (self.tr("1 object is not shown in 3D") if count == 1
                    else self.tr("{count} objects are not shown in 3D").format(count=count))
            self._problems_button.setText(text)
            self._problems_button.show()
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
        from .problems_dialog import problems_of

        controller = self._controller
        if controller is None:
            dialog.set_problems((), self._item_name)
            return
        dialog.set_problems(problems_of(controller.skipped, controller.failures), self._item_name)

    def _find_item(self, item_id: str) -> Any:
        from open_garden_planner.ui.canvas.select_by_id import item_with_id

        scene = self._scene
        return None if scene is None else item_with_id(scene, item_id)

    def _item_name(self, item_id: str) -> str:
        return str(getattr(self._find_item(item_id), "name", "") or "")

    def select_item(self, item_id: str) -> None:
        """Select the item on the plan and scroll the plan to it (a row of the problems
        list was activated) — through the app's ONE select-by-id path,
        ``ui/canvas/select_by_id.py``, which the Diagnostics, Canopy and Guilds panels
        use too: its group when it is in one, nothing when its layer is locked."""
        from open_garden_planner.ui.canvas.select_by_id import select_by_ids

        scene, item = self._scene, self._find_item(item_id)
        if scene is None or item is None:
            return
        select_by_ids(scene, (item_id,))
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
            self._status_label.setText(self.tr(
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
        self._hide_compat_notice()

    def _update_compat_notice(self) -> None:
        guard = self.guard
        if guard.mode is not RenderMode.SOFTWARE:
            self._hide_compat_notice()
            return
        if guard.reason is ModeReason.PREVIOUS_START_DIED:
            text = self.tr("3D is running in compatibility mode (software rendering) because "
                           "it did not start properly last time.")
        else:
            text = self.tr("3D is running in compatibility mode (software rendering).")
        self._compat_label.setText(text)
        self._compat_label.show()
        self._compat_button.setText(self.tr("Try Hardware Next Time"))
        self._compat_button.setVisible(guard.software_requested())

    def _hide_compat_notice(self) -> None:
        self._compat_label.hide()
        self._compat_button.hide()

    def _on_compat_button(self) -> None:
        self.guard.try_hardware_next_time()
        self._compat_button.hide()
        self._compat_label.setText(self.tr(
            "Hardware rendering will be tried the next time the application starts."))

    def _on_message_button(self) -> None:
        pane = self._pane
        if pane is None:
            return
        if self._state is View3DState.FAILED:
            self._set_state(View3DState.NOT_STARTED)
            self._start_engine()
        elif self._state is View3DState.UNAVAILABLE:
            self.guard.use_software_next_time()
            pane.message_button.setEnabled(False)
            pane.message_button.setText(self.tr(
                "Compatibility mode will be used the next time the application starts."))

    # ── teardown ─────────────────────────────────────────────────────────────

    def _close_host(self, host: EngineHost) -> None:
        try:
            host.close()
        except Exception as error:  # noqa: BLE001 - closing must never stop a shutdown
            _log_failure("3D workspace: the engine host did not close cleanly", error)

    def _stop_engine(self) -> None:
        self._unwire_selection()  # L1.8: walk mode ends, the canvas is let go
        self._camera_timer.stop()
        self._health_timer.stop()
        self._drop_held_build()
        self._retired = 0  # the host goes, and what it cached with it
        controller, self._controller = self._controller, None
        if controller is not None:
            controller.shutdown()
            if self._command_manager is not None:
                try:
                    self._command_manager.stack_changed.disconnect(controller.mark_dirty)
                except (RuntimeError, TypeError):
                    _LOG.debug("3D workspace: the undo stack was already disconnected")
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

    # ── selection, the info card and walk mode (L1.8, ADR-065) ───────────────
    #
    # ONE selection: the canvas scene's. A click in the 3D view becomes a canvas
    # selection by the canvas's own rules (``selection_bridge``); the canvas's
    # ``selectionChanged`` becomes the ring in 3D (``Scene3DController.set_selection``
    # — a flag while 3D is hidden) and the info card below the view. Walk mode is a
    # second source for ``_apply_camera`` and nothing more: it never touches the orbit
    # camera, the plan or the undo stack.

    def _init_selection_and_walk(self) -> None:
        self._walk: WalkMode | None = None
        self._card: View3DInfoCard | None = None
        self._card_slot: View3DCardSlot | None = None
        self._selection_wired = False
        self._eye_height: float | None = None  # None: the walk's default (the first preset)
        #: Where the keyboard focus was when walk mode began (it goes back there).
        self._focus_before: QWidget | None = None
        self._walk_action = QAction(self.tr("&Walk"), self)
        self._walk_action.setCheckable(True)
        self._walk_action.setStatusTip(self.tr("Walk through the garden at eye height"))
        self._walk_action.setToolTip(self.tr(
            "Walk through the garden at eye height (W A S D or the arrow keys walk, "
            "drag to look around, Shift runs, Esc leaves)"))
        self._walk_action.triggered.connect(lambda checked=False: self.set_walking(bool(checked)))
        self._walk_action.setEnabled(False)

    @property
    def walk_action(self) -> QAction:
        """The checkable "Walk" action (the 3D pane's strip shows it)."""
        return self._walk_action

    @property
    def walk(self) -> WalkMode | None:
        """Walk mode's state — None until walk mode was first entered."""
        return self._walk

    @property
    def walking(self) -> bool:
        return self._walk is not None and self._walk.active

    @property
    def info_card(self) -> View3DInfoCard | None:
        """The info card (None until the 3D pane was first asked for)."""
        return self._card

    def _build_walk_controls(self, pane: _Pane3D) -> None:
        from open_garden_planner.core.measurements import format_length
        from open_garden_planner.core.scene3d.walk import EYE_HEIGHTS_CM

        strip = pane.strip_layout
        self._walk_button = QToolButton(pane.strip)
        self._walk_button.setDefaultAction(self._walk_action)
        self._walk_button.setAutoRaise(True)
        self._walk_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        strip.addWidget(self._walk_button)
        self._eye_combo = QComboBox(pane.strip)
        self._eye_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._eye_combo.setToolTip(self.tr("Eye height while walking"))
        people = (self.tr("Adult"), self.tr("Smaller adult"), self.tr("Child"))
        for who, height in zip(people, EYE_HEIGHTS_CM, strict=True):
            self._eye_combo.addItem(self.tr("{who} – {height}").format(
                who=who, height=format_length(height)), height)
        self._eye_combo.currentIndexChanged.connect(self._on_eye_height)
        # its room is kept while it is hidden: entering walk mode must not make the
        # strip taller and the 3D view smaller (measured: 4 px, and a resize each time)
        policy = self._eye_combo.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self._eye_combo.setSizePolicy(policy)
        self._eye_combo.hide()
        strip.addWidget(self._eye_combo)

    def _build_card(self, pane: _Pane3D) -> None:
        from .info_card import View3DCardSlot

        # The card's PLACE, of one constant height: a card that came and went with the
        # selection resized the 3D view under the pointer (info_card's docstring).
        slot = View3DCardSlot(pane)
        slot.card.show_in_plan.connect(self.show_in_plan)
        slot.hide()  # until there is an engine view to stand below
        layout = pane.layout()
        if layout is not None:
            layout.addWidget(slot)  # BELOW the view: nothing is ever drawn over it
        pane.showing_changed.connect(self._on_showing_for_selection)
        self._card_slot = slot
        self._card = slot.card

    def _wire_selection(self, host: EngineHost, orbit: OrbitInput,
                        controller: Scene3DController) -> None:
        orbit.watch(host)
        orbit.picked.connect(self._on_picked)
        controller.applied.connect(self._on_applied_for_selection)
        controller.problems_changed.connect(self._refresh_card)
        scene = self._scene
        if scene is not None and not self._selection_wired:
            scene.selectionChanged.connect(self._on_canvas_selection)
            self._selection_wired = True
        self._walk_action.setEnabled(True)
        self._on_canvas_selection()  # what is selected NOW — a flag until 3D is shown

    def _unwire_selection(self) -> None:
        self.set_walking(False)
        walk, self._walk = self._walk, None
        if walk is not None:
            walk.deleteLater()  # it filtered the host that is going
        scene = self._scene
        if scene is not None and self._selection_wired:
            try:
                scene.selectionChanged.disconnect(self._on_canvas_selection)
            except (RuntimeError, TypeError):
                _LOG.debug("3D workspace: the canvas selection was already disconnected")
        self._selection_wired = False
        self._walk_action.setEnabled(False)
        if self._card_slot is not None:
            self._card_slot.show_hint("")
            self._card_slot.hide()  # no engine view: nothing to stand below

    def _on_canvas_selection(self) -> None:
        """The canvas selection changed: the ring follows, and the card."""
        from .selection_bridge import selected_record_ids

        controller, scene = self._controller, self._scene
        if controller is None or scene is None:
            return
        try:
            ids = selected_record_ids(scene)
        except RuntimeError:  # the scene is being torn down under the signal
            return
        controller.set_selection(ids)
        self._refresh_card()

    def _on_picked(self, hit: object, modifiers: object) -> None:
        """A click in the 3D view picked ``hit`` (None: the ground, the sky) with
        ``modifiers`` held: it becomes what a click on the canvas there would have
        become."""
        from .selection_bridge import apply_click, hit_ids

        scene = self._scene
        if scene is not None:
            held = (modifiers if isinstance(modifiers, Qt.KeyboardModifier)
                    else Qt.KeyboardModifier.NoModifier)
            apply_click(scene, hit_ids(hit), held)

    def show_in_plan(self, item_id: str) -> None:
        """The info card's action: the plan centred on the item. From 3D-only mode the
        workspace goes to Split first — there is no plan to show it in otherwise."""
        if self._mode is WorkspaceMode.VIEW3D:
            self.set_mode(WorkspaceMode.SPLIT)
        item = self._find_item(item_id)
        center_on = getattr(self._canvas, "centerOn", None)
        if item is not None and callable(center_on) and self._canvas.isVisible():
            center_on(item)

    def _on_showing_for_selection(self, showing: bool) -> None:
        walk = self._walk
        if walk is not None and walk.active:
            if showing:
                walk.resume()
            else:
                walk.pause()  # a hidden view gets no key release: every key is let go
        if showing:
            self._refresh_card()

    def _on_applied_for_selection(self, report: TickReport) -> None:
        """A pass reached the engine: the card's numbers may be another day's, and a
        walker's world may have moved — rebuilt only when what moved was, or now is, a
        solid (a date change regrows plants, which the walker walks through)."""
        from open_garden_planner.core.scene3d.walk import is_solid

        self._refresh_card()
        walk, changes, controller = self._walk, report.changes, self._controller
        if walk is None or not walk.active or not report.snapshot or controller is None:
            return
        touched = {*changes.added, *changes.removed, *changes.geometry, *changes.transform}
        records = controller.sync.records
        world = walk.world
        was_solid = touched & set(world.solid_ids) if world is not None else touched
        if was_solid or any(is_solid(records[i]) for i in touched if i in records):
            walk.set_world(self._walk_world())
            self._after_walk_change()

    def _refresh_card(self) -> None:
        slot = self._card_slot
        if slot is None:
            return
        # the card's place is there with the view's other controls, card or no card:
        # a selection never changes the size of the 3D view
        slot.setVisible(self._chrome_visible and self._controller is not None)
        if not self._pane_is_showing():
            return  # hidden: nothing is computed; the card is refreshed when it shows
        subject = self._card_subject()
        if subject is None:
            slot.show_hint(self._selection_hint())
        else:
            slot.show_subject(subject)

    def _selection_hint(self) -> str:
        """What stands in the card's place while it shows no item."""
        scene = self._scene
        try:
            count = len(scene.selectedItems()) if scene is not None else 0
        except RuntimeError:  # the scene is being torn down
            count = 0
        if count > 1:
            return self.tr("{count} objects selected.").format(count=count)
        return self.tr("Click an object to see what the 3D view shows of it.")

    def _card_subject(self) -> CardSubject | None:
        """What the card shows: the ONE selected item, with the record the engine was
        last sent for it — None when the card shows nothing."""
        from .info_card import CardSubject
        from .problems_dialog import BUILD_FAILED, reason_text
        from .selection_bridge import sole_selected

        controller, scene, clock = self._controller, self._scene, self._clock
        if controller is None or scene is None or not self._chrome_visible:
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
            # a group: it covers no ground itself — its members are what 3D shows
            has_model = any(self._has_model(str(getattr(member, "item_id", "")))
                            for member in item.childItems())
        else:
            has_model = not problem and self._has_model(item_id)
        parent_id = record.parent_id if record is not None else None
        return CardSubject(item, record, has_model, problem,
                           self._item_name(parent_id) if parent_id else "",
                           clock.plan_date if clock is not None else None)

    def _has_model(self, item_id: str) -> bool:
        """True when the engine holds at least one mesh for the item (asked of the
        sink's own books — the recording double answers the same question)."""
        controller = self._controller
        held = getattr(controller.sync.sink, "item", None) if controller is not None else None
        if not callable(held):
            return False
        try:
            return any(part.mesh.triangle_count for part in held(item_id).parts)
        except KeyError:
            return False

    # … walk mode

    def set_walking(self, on: bool) -> bool:
        """Enter or leave walk mode; returns whether the view is walking afterwards.

        Entering puts the walker where the orbit camera looks (its target), facing
        the way it looks — or on the nearest free ground when that spot is inside a
        solid — and is refused (False) when 3D is not running or the plan has no
        free ground. Leaving shows the orbit pose again: walking never touched it.
        """
        action = self._walk_action
        walk = self._walk
        if not on:
            if walk is not None and walk.active:
                walk.leave()
                self._after_walk_change()
                self._give_focus_back()
            action.setChecked(False)
            return False
        controller, host = self._controller, self._host
        if controller is None or host is None:
            action.setChecked(False)
            return False
        if walk is None:
            from .walk_mode import WalkMode

            walk = WalkMode(self)
            # installed AFTER the orbit filter, so it sees every event first; it passes
            # everything on while not walking
            host.install_event_filter(walk)
            walk.changed.connect(self._apply_camera)
            walk.left.connect(lambda: self.set_walking(False))
            orbit = self._input
            if orbit is not None:
                walk.turned.connect(orbit.cancel_click)  # a drag that turned is no click
            if self._eye_height is not None:
                walk.set_eye_height(self._eye_height)
            self._walk = walk
        if not walk.active:
            pose = self._camera.pose
            if not walk.enter(self._walk_world(), pose.target, pose.yaw_deg):
                self._status_label.setText(self.tr("There is no free ground to walk on."))
                action.setChecked(False)
                return False
            if not self._pane_is_showing():
                walk.pause()
            self._after_walk_change()
            self._take_focus(host)
        action.setChecked(True)
        return True

    def _take_focus(self, host: EngineHost) -> None:
        """Walking is done with the keyboard: the 3D view takes the focus (else W picks
        the Wall tool on the plan and Escape reaches the canvas), and it goes back where
        it was when walk mode ends."""
        from PyQt6.QtWidgets import QApplication

        before = QApplication.focusWidget()
        engine = self._pane.engine_widget if self._pane is not None else None
        self._focus_before = before if before is not engine else None
        try:
            host.focus()
        except Exception as error:  # noqa: BLE001 - a view that cannot take focus still walks
            _log_failure("3D workspace: the 3D view could not take the keyboard focus", error)

    def _give_focus_back(self) -> None:
        """Walk mode ended: if the 3D view still has the keyboard, it goes back to the
        widget that had it before (a document change or a hidden pane leaves it alone)."""
        from PyQt6 import sip

        before, self._focus_before = self._focus_before, None
        host = self._host
        if before is None or sip.isdeleted(before) or host is None:
            return
        try:
            still_ours = host.has_focus()
        except Exception:  # noqa: BLE001 - a host that cannot say keeps the focus where it is
            still_ours = False
        if still_ours:
            before.activateWindow()
            before.setFocus(Qt.FocusReason.OtherFocusReason)

    def _after_walk_change(self) -> None:
        if self._pane is not None:
            self._eye_combo.setVisible(self.walking)
        self._apply_camera()

    def _walk_world(self) -> WalkWorld:
        """The walker's world: the records the engine was last sent, with the mesh parts
        the ENGINE holds for them — what blocks is what is drawn (``core/scene3d/walk``),
        and nothing is built a second time (a record whose build failed has no parts:
        its footprint blocks)."""
        from open_garden_planner.core.scene3d.mesh import MeshPart
        from open_garden_planner.core.scene3d.record import Record
        from open_garden_planner.core.scene3d.walk import build_world

        controller = self._controller
        assert controller is not None
        bounds, sink = controller.plan_bounds(), controller.sync.sink

        def held_parts(record: Record) -> tuple[MeshPart, ...]:
            try:
                return tuple(sink.item(record.item_id).parts)
            except KeyError:
                return ()

        return build_world(controller.sync.records, bounds.max_east, bounds.max_north,
                           parts_of=held_parts)

    def _on_eye_height(self, index: int) -> None:
        height = self._eye_combo.itemData(index)
        if not isinstance(height, (int, float)):
            return
        self._eye_height = float(height)
        if self._walk is not None:
            self._walk.set_eye_height(float(height))
