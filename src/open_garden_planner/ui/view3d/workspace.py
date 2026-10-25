"""The Plan / 3D / Split workspace of the main window (Phase 17 L1.3, ADR-060).

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

Layout rule (ADR-060): the 3D view is a NATIVE window inside a container, and no
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

NOTHING HERE TAKES A FRAME FROM THE LIVE VIEW (ADR-060 decision 17, measured). A
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

WHAT A DESTROYED MODEL LEAVES BEHIND (ADR-060, measured). Qt Quick 3D keeps
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
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Final, Protocol

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QHideEvent,
    QKeySequence,
    QPalette,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLayoutItem,
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

    from .analysis_controller import AnalysisController, ProbeResult
    from .forge_worker import ForgeWorker
    from .growth_jump import GrowthJump
    from .info_card import CardSubject, View3DCardSlot, View3DInfoCard
    from .look_controller import LookController
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
#: Cutaway's X-ray (L2.4) is recomputed this long after the camera, the selection or
#: the records last changed — never per frame of a moving camera (a few to tens of ms
#: of ray tests on the GUI thread).
XRAY_DELAY_MS: Final = 150
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
    def focus(self) -> None: ...
    def has_focus(self) -> bool: ...
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
    # the analysis (L2): ``analysis_controller.AnalysisHost``
    def set_overlay(self, layer: str, mesh: Any) -> None: ...
    def set_roofs_hidden(self, hidden: bool) -> None: ...
    def set_faded_items(self, item_ids: frozenset[str], opacity: float = ...) -> None: ...


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


class _WrapRow(QLayout):
    """The strip's row of controls: left to right, and onto a second line only when the
    pane is too narrow for one (L2). In German a Split pane of a 1366 px window had 7 px
    left beside "Reset 3D View" and "Walk" — L2's Analyze button would have cut the
    notices below (the test of every notice in a 1366 px window found it; the eye-height
    box of L1.8 had once done the same). A wrapping row asks for the widest control's
    width, never for the sum: no control is ever narrower than its text, and the pane
    is never wider than the window gives it."""

    def __init__(self, parent: QWidget | None = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(spacing)

    def addItem(self, item: QLayoutItem | None) -> None:  # noqa: N802 - Qt's name
        if item is not None:
            self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt's name
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt's name
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802 - Qt's name
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt's name
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt's name
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt's name
        shown = [item.sizeHint() for item in self._items if not item.isEmpty()]
        width = sum(size.width() for size in shown) + self.spacing() * max(len(shown) - 1, 0)
        return QSize(width, max((size.height() for size in shown), default=0))

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt's name
        shown = [item.sizeHint() for item in self._items if not item.isEmpty()]
        return QSize(max((size.width() for size in shown), default=0),
                     max((size.height() for size in shown), default=0))

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt's name
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        x, y, line = rect.x(), rect.y(), 0
        for item in self._items:
            if item.isEmpty():
                continue
            size = item.sizeHint()
            if x > rect.x() and x + size.width() > rect.x() + rect.width():
                x, y, line = rect.x(), y + line + self.spacing(), 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), size))
            x += size.width() + self.spacing()
            line = max(line, size.height())
        return y + line - rect.y()


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
        self.strip_layout = _WrapRow(controls)  # wraps only in a narrow pane (L2)
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
        self._forge_worker: ForgeWorker | None = None  # Plant Forge progressive upgrader (L3)
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
        self._forge_timer = QTimer(self)
        self._forge_timer.setSingleShot(True)
        self._forge_timer.timeout.connect(self._step_forge)

        self._build_actions()
        self._init_selection_and_walk()  # L1.8: its state and the Walk action
        self._init_analysis()            # L2: the Analyze menu's actions and its state
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
        ADR-060 decision 5) — and the pipeline listens to the scene. The parameter
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
        _home = QKeySequence(Qt.Key.Key_Home).toString(
            QKeySequence.SequenceFormat.NativeText)
        self._reset_action.setToolTip(
            self.tr("Show the whole garden again ({key})").format(key=_home))
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
        # (L1.8) 3D mode keeps the selection: the ring shows it in 3D and the card names
        # it — so the app's shortcuts (Delete, Ctrl+X, Ctrl+D) act on what is SHOWN.
        # This replaces the workspace's stopgap ``clear_selection_hidden_by_3d_mode``.
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
        # its words, not the menu's icon (the main window gives the action one, L1.9)
        self._reset_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._reset_button.setAutoRaise(True)
        self._reset_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        strip.addWidget(self._reset_button)
        self._build_walk_controls(pane)  # L1.8: the Walk toggle and the eye height
        self._build_analysis_controls(pane)  # L2: the Analyze menu
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
        self._build_legend(pane)  # L2: the sun path's legend, a line of the notices
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
            from .ground_bake import GroundBaker

            # the look (L1.4): the render mode decides sky, wind and the automatic
            # preset together — in compatibility mode no sky (a light probe costs
            # seconds there), no wind (an animated view renders continuously) and
            # ``auto`` = low (ADR-059 addendum)
            look = LookController.from_settings(host, software=software, parent=self)
            # ONE baker for this engine's life: it holds the ground's tiles, and paints
            # for at most its budget (10 ms) a pass — the controller runs the rest
            controller = Scene3DController(scene, clock, self._location, sink, parent=self,
                                           ground_baker=GroundBaker())
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
        if self.engine_factory is quick3d_engine:
            from ...core.plant_forge import ForgeCache
            from .forge_worker import ForgeWorker

            # Render gates use the production path too. The private cache belongs
            # exclusively to this worker's synthesis thread.
            self._forge_worker = ForgeWorker(
                sink, cache=ForgeCache(max_entries=256), background=True,
                season_sink=getattr(host, "set_plant_seasons", None),
            )
        else:
            self._forge_worker = None
        orbit.moved.connect(self._start_camera)
        orbit.reset_requested.connect(self.reset_view)
        self._wire_selection(host, orbit, controller)  # L1.8: the click, the ring, the card
        self._wire_analysis(host, orbit, controller)   # L2: drapes, sun path, probe, jumps
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
        viewing = showing and not self._wipe_shown()  # the wipe stands in the view's place
        if self._look is not None:
            self._look.set_showing(viewing)  # wind and frame sampling: only while shown
        if self._analysis is not None:
            self._analysis.set_active(showing)  # L2: overlays sent only while shown
        controller = self._controller
        if controller is None or self._host is None:
            self._health_timer.stop()
            self._camera_timer.stop()
            self._drop_held_build()
            return
        if not showing:
            self._drop_held_build()
            self._forge_timer.stop()
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
        if self._forge_worker is not None and self._forge_worker.pending_count:
            self._forge_timer.start(10)
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

    def _camera_now(self) -> tuple[Any, Any, float]:
        """``(eye, target, fov)`` the view is shown from: the walker's eye while walking
        (L1.8; the orbit pose rests), else the orbit pose."""
        walk = self._walk
        if walk is not None and walk.active:
            eye, target, fov = walk.camera()
            return eye, target, fov
        pose = self._camera.pose
        return pose.eye, pose.target_scene, FOV_DEG

    def _apply_camera(self) -> None:
        host = self._host
        if host is None:
            return
        eye, target, fov = self._camera_now()
        try:
            host.set_camera(eye, target, fov)
        except Exception:  # noqa: BLE001 - the health poll reports a host that died
            _LOG.debug("3D workspace: the camera could not be set", exc_info=True)
        self._schedule_xray()  # L2.4: the occluders follow the camera once it rests
        worker = self._forge_worker
        if worker is not None:
            forward = (float(target[0] - eye[0]), float(target[1] - eye[1]), float(target[2] - eye[2]))
            worker.update_camera(eye, forward)
            if worker.pending_count and self._pane_is_showing():
                self._forge_timer.start(10)

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
        self._analysis_document_changed()  # L2: the probe, the sweep, the jump, the wipe
        self._forge_timer.stop()
        if self._forge_worker is not None:
            self._forge_worker.clear()
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
        if self._analysis is not None:
            self._analysis.location_changed()  # L2: the sun path is the place's
            self._update_legend()
        self._refresh_forge()

    def _on_applied(self, report: TickReport) -> None:
        # A pass went through: the build is over, and so is a failed update. What the
        # ENGINE reported is not: that notice stays until the engine is gone (it used
        # to be erased by the next pass — one edit, and the only sign of it was lost).
        self._notices.pop(_NOTICE_BUILDING, None)
        self._notices.pop(_NOTICE_SYNC, None)
        self._refresh_notices()
        if report.ground_pass:
            # pending ground tiles painted, nothing else: the sun did not move (a
            # set_sun would restart the look's stale-sky timer on every slice) and no
            # Model was destroyed (taking it as "the pipeline worked" would push the
            # quiet-time release back for as long as the ground paints)
            return
        # the look follows the sun the PIPELINE sent — the same pass, the same sun
        if self._look is not None and self._controller is not None:
            self._look.set_sun(self._controller.sync.sun)
        self._applied_at = _now()
        self._retired += report.retired
        if self._retired >= RELEASE_NOW_RETIRED:
            self._release_engine_caches()  # a flood: not worth waiting for quiet
        if report.snapshot and self._forge_worker is not None:
            worker = self._forge_worker
            if report.recovered and self._controller is not None:
                worker.invalidate(self._controller.sync.records)
            else:
                worker.invalidate((*report.changes.added, *report.changes.geometry))
            self._refresh_forge()

    def _refresh_forge(self) -> None:
        worker, controller = self._forge_worker, self._controller
        if worker is None or controller is None:
            return
        loc = self._location()
        lat = loc.get("latitude") if isinstance(loc, Mapping) else None
        frost = loc.get("frost_dates") if isinstance(loc, Mapping) else None
        eye, target, _fov = self._camera_now()
        forward = (float(target[0] - eye[0]), float(target[1] - eye[1]), float(target[2] - eye[2]))
        worker.submit_snapshot(
            controller.sync.records.values(), camera_pos=eye, camera_forward=forward,
            plan_date=controller.pass_date,
            latitude_deg=float(lat) if isinstance(lat, (int, float)) else 52.52,
            frost_dates=frost if isinstance(frost, Mapping) else None,
        )
        if worker.pending_count and self._pane_is_showing():
            self._forge_timer.start(10)

    def _step_forge(self) -> None:
        """Upgrade up to a small slice of visible plants to forged 3D models per event-loop turn."""
        worker = self._forge_worker
        if worker is None or not self._pane_is_showing() or self._controller is None:
            return
        try:
            upgraded = worker.step(max_items=1)
        except Exception as error:  # recover through SceneSync's one reset path
            _log_failure("Plant Forge could not update the 3D view", error)
            worker.clear()
            self._controller.reset()
            return
        if upgraded:
            self._applied_at = _now()
            self._retired += len(upgraded)
            if self._retired >= RELEASE_NOW_RETIRED:
                self._release_engine_caches()
        if worker.pending_count > 0 and self._pane_is_showing():
            self._forge_timer.start(10)

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
        partial = controller is not None and controller.ground_problems.incomplete
        if count == 0 and not partial:
            self._problems_row.hide()
        else:
            if count == 0:
                text = self.tr("The 3D ground does not show all of the plan")
            elif count == 1:
                text = (self.tr("1 object is not shown in 3D; the 3D ground does not show "
                                "all of the plan") if partial
                        else self.tr("1 object is not shown in 3D"))
            elif partial:
                text = self.tr("{count} objects are not shown in 3D; the 3D ground does not "
                               "show all of the plan").format(count=count)
            else:
                text = self.tr("{count} objects are not shown in 3D").format(count=count)
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
        problems = problems_of(controller.skipped, controller.failures,
                               controller.ground_problems)
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
        from open_garden_planner.ui.canvas.select_by_id import item_with_id

        scene = self._scene
        return None if scene is None else item_with_id(scene, item_id)

    def select_item(self, item_id: str) -> None:
        """Select the item on the plan and scroll the plan to it (a row of the problems
        list was activated) — through the app's ONE select-by-id path,
        ``ui/canvas/select_by_id.py``, which the Diagnostics, Canopy and Guilds panels
        use too: its group when it is in one, nothing when its layer is locked."""
        from open_garden_planner.ui.canvas.select_by_id import select_by_ids

        scene, item = self._scene, self._find_item(item_id)
        if scene is None or item is None:
            return
        if self._mode is WorkspaceMode.VIEW3D:
            # an item of this list is one the 3D view does NOT show — no ring can mark
            # it — so the plan is shown, where it is selected and centred
            self.set_mode(WorkspaceMode.SPLIT)
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
        self._unwire_selection()  # L1.8: walk mode ends, the canvas is let go
        self._unwire_analysis()   # L2: its timers and its sources
        self._camera_timer.stop()
        self._health_timer.stop()
        self._forge_timer.stop()
        if self._forge_worker is not None:
            self._forge_worker.shutdown()
            self._forge_worker = None
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

    # ── selection, the info card and walk mode (L1.8, ADR-060) ───────────────
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
        self._walk_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # The eye height is the Walk button's menu (the arrow beside it). A box of its own
        # beside the button made the strip's row 574 px wide — wider than a 455 px pane,
        # whose notices were then cut — and, hidden while not walking, it had to keep its
        # room to keep the view from resizing (fix round 1, after the workspace's strip
        # became two rows). A menu takes no room and comes and goes with nothing.
        menu = QMenu(self._walk_button)
        menu.addSection(self.tr("Eye height while walking"))
        group = QActionGroup(menu)
        group.setExclusive(True)
        people = (self.tr("Adult"), self.tr("Smaller adult"), self.tr("Child"))
        self._eye_actions: list[QAction] = []
        for who, height in zip(people, EYE_HEIGHTS_CM, strict=True):
            action = QAction(self.tr("{who} – {height}").format(
                who=who, height=format_length(height)), menu)
            action.setCheckable(True)
            action.setData(height)
            action.triggered.connect(lambda _checked=False, cm=height: self.set_eye_height(cm))
            group.addAction(action)
            menu.addAction(action)
            self._eye_actions.append(action)
        self._eye_actions[EYE_HEIGHTS_CM.index(self._eye_height or EYE_HEIGHTS_CM[0])].setChecked(True)
        self._walk_button.setMenu(menu)
        self._walk_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        strip.addWidget(self._walk_button)

    @property
    def eye_height_actions(self) -> list[QAction]:
        """The Walk button's menu: one checkable action per eye height (``EYE_HEIGHTS_CM``,
        in that order; empty before the 3D pane was first built)."""
        return list(getattr(self, "_eye_actions", ()))

    def set_eye_height(self, height_cm: float) -> None:
        """The walker's eye height — now, while walking, and for the next walk."""
        from open_garden_planner.core.scene3d.walk import EYE_HEIGHTS_CM

        if height_cm not in EYE_HEIGHTS_CM:
            raise ValueError(f"an eye height is one of {EYE_HEIGHTS_CM}, got {height_cm!r}")
        self._eye_height = float(height_cm)
        for action in self.eye_height_actions:
            action.setChecked(action.data() == height_cm)
        if self._walk is not None:
            self._walk.set_eye_height(float(height_cm))

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
        self._schedule_xray()  # L2.4: what hides the new selection

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
        """What stands in the card's place while it shows no item — the ground probe's
        reading when there is one (L2.1)."""
        scene = self._scene
        try:
            count = len(scene.selectedItems()) if scene is not None else 0
        except RuntimeError:  # the scene is being torn down
            count = 0
        if count > 1:
            return self.tr("{count} objects selected.").format(count=count)
        probe = self._probe_text()
        if probe:
            return probe
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
        plan_date = clock.plan_date if clock is not None else None
        return CardSubject(item, record, has_model, problem,
                           str(getattr(self._find_item(parent_id), "name", "") or "")
                           if parent_id else "",
                           plan_date, self._card_facts(item, record, plan_date))

    def _card_facts(self, item: Any, record: Any, plan_date: Any) -> Any:
        """The info card v1's facts (L2.3), each from its one home — the height's source
        at the plan date, the growth share, the sun the heatmap measured for the item,
        the sowing and harvest windows of the plan's year (``info_card.card_facts``)."""
        from .info_card import card_facts

        heatmap = self._sun_heatmap
        sun: tuple[float, Any] | None = None
        if heatmap is not None and getattr(heatmap, "exposure_reason", "") == "ready":
            minutes = dict(getattr(heatmap, "receiver_minutes", {}) or {}).get(
                str(getattr(item, "item_id", "")))
            day = getattr(heatmap, "computed_day", None)
            if isinstance(minutes, (int, float)) and day is not None:
                sun = (float(minutes), day)
        try:
            return card_facts(item, record, plan_date, self._location(), sun)
        except Exception as error:  # noqa: BLE001 - a fact the card cannot read is left out
            _log_failure("3D info card: the plant facts could not be read", error)
            return None

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
        self._apply_camera()

    def _walk_world(self) -> WalkWorld:
        """The walker's world: the records the engine was last sent, with the mesh parts
        the ENGINE holds for them — what blocks is what is drawn (``core/scene3d/walk``),
        and nothing is built a second time (a record whose build failed has no parts:
        its footprint blocks)."""
        from open_garden_planner.core.scene3d.walk import build_world

        controller = self._controller
        assert controller is not None
        bounds = controller.plan_bounds()
        return build_world(controller.sync.records, bounds.max_east, bounds.max_north,
                           parts_of=self._held_parts())

    def _held_parts(self) -> Callable[[Any], tuple[Any, ...]]:
        """The mesh parts the ENGINE holds for a record (the sink's own books —
        ``Quick3DSink.item`` / ``RecordingSink.item``, asked as ``_has_model`` asks them:
        not every EngineSink keeps them). Walk mode's world and the X-ray read the same;
        nothing is built a second time."""
        controller = self._controller
        held = getattr(controller.sync.sink, "item", None) if controller is not None else None

        def parts_of(record: Any) -> tuple[Any, ...]:
            if not callable(held):
                return ()
            try:
                return tuple(held(record.item_id).parts)
            except KeyError:
                return ()

        return parts_of

    # ── analyze in 3D (L2, #386) ─────────────────────────────────────────────
    #
    # ONE "Analyze" menu in the strip: what lies on the ground (nothing, the 2D shadows,
    # the hours of sun), the sun path and compass, the day sweep, Cutaway, and the
    # growth jumps. ``AnalysisController`` (engine-free) does the work; this section
    # wires it: the click on the ground that probes, the camera and the selection that
    # the X-ray follows, the growth jump and its before/after wipe, the legend. The
    # sources — the 2D shadow overlay, the heatmap and the shared Hours-of-Sun switch —
    # come from the app (``connect_analysis``).

    def _init_analysis(self) -> None:
        from .analysis_modes import JUMP_YEARS, DrapeMode

        self._analysis: AnalysisController | None = None
        self._jump: GrowthJump | None = None
        self._shadow_source: Any = None
        self._sun_heatmap: Any = None
        self._sun_hours: Any = None   # the shared Hours of Sun (``LiveSunMap``)
        self._wipe: Any = None
        self._legend_row: QWidget | None = None
        # the X-ray waits for a resting camera: restarted by every camera change
        self._xray_timer = QTimer(self)
        self._xray_timer.setSingleShot(True)
        self._xray_timer.setInterval(XRAY_DELAY_MS)
        self._xray_timer.timeout.connect(self._run_xray)
        self._drape_group = QActionGroup(self)
        self._drape_group.setExclusive(True)
        self._drape_actions: dict[DrapeMode, QAction] = {}
        for mode, text, tip in (
            (DrapeMode.NONE, self.tr("Nothing on the Ground"),
             self.tr("Show the garden in 3D without an analysis on the ground")),
            (DrapeMode.SHADOWS, self.tr("2D Shadows on the Ground"),
             self.tr("Lay the plan's 2D shadows on the 3D ground: the sun study's own answer")),
            (DrapeMode.SUN_HOURS, self.tr("Hours of Sun on the Ground"),
             self.tr("Lay the hours-of-sun map on the 3D ground; click the ground to read it")),
        ):
            action = QAction(text, self)
            action.setCheckable(True)
            action.setStatusTip(tip)
            action.triggered.connect(lambda _checked=False, m=mode: self.set_drape_mode(m))
            self._drape_group.addAction(action)
            self._drape_actions[mode] = action
        self._drape_actions[DrapeMode.NONE].setChecked(True)
        self._sun_path_action = QAction(self.tr("Sun Path and Compass"), self)
        self._sun_path_action.setCheckable(True)
        self._sun_path_action.setStatusTip(self.tr(
            "Show where the sun goes today, at both solstices and at the equinox, and a compass"))
        self._sun_path_action.triggered.connect(
            lambda checked=False: self.set_sun_path_visible(bool(checked)))
        self._sweep_action = QAction(self.tr("Sweep the Day"), self)
        self._sweep_action.setCheckable(True)
        self._sweep_action.setStatusTip(self.tr(
            "Play the plan date from sunrise to sunset and watch the hours of sun add up"))
        self._sweep_action.triggered.connect(lambda checked=False: self.set_sweeping(bool(checked)))
        self._cutaway_action = QAction(self.tr("Cutaway"), self)
        self._cutaway_action.setCheckable(True)
        self._cutaway_action.setStatusTip(self.tr(
            "Take the roofs off and let what stands in front of the selection fade"))
        self._cutaway_action.triggered.connect(lambda checked=False: self.set_cutaway(bool(checked)))
        texts = {1: self.tr("+1 Year"), 3: self.tr("+3 Years"), 10: self.tr("+10 Years")}
        self._jump_actions: dict[int, QAction] = {}
        for years in JUMP_YEARS:
            action = QAction(texts[years], self)
            action.setStatusTip(self.tr("Move the plan date forward and compare before and after"))
            action.triggered.connect(lambda _checked=False, y=years: self.jump_years(y))
            self._jump_actions[years] = action
        self._back_action = QAction(self.tr("Back to the Starting Date"), self)
        self._back_action.triggered.connect(lambda _checked=False: self.growth_back())
        for action in self._analysis_actions():
            action.setEnabled(False)

    def _analysis_actions(self) -> list[QAction]:
        return [*self._drape_actions.values(), self._sun_path_action, self._sweep_action,
                self._cutaway_action, *self._jump_actions.values(), self._back_action]

    @property
    def analysis(self) -> AnalysisController | None:
        """The analysis of the running engine (None before 3D was first opened)."""
        return self._analysis

    @property
    def growth(self) -> GrowthJump | None:
        return self._jump

    @property
    def drape_actions(self) -> dict[Any, QAction]:
        return dict(self._drape_actions)

    @property
    def sun_path_action(self) -> QAction:
        return self._sun_path_action

    @property
    def sweep_action(self) -> QAction:
        return self._sweep_action

    @property
    def cutaway_action(self) -> QAction:
        return self._cutaway_action

    @property
    def jump_actions(self) -> dict[int, QAction]:
        return dict(self._jump_actions)

    @property
    def back_action(self) -> QAction:
        return self._back_action

    @property
    def wipe(self) -> Any:
        """The before/after wipe (None until the 3D pane was first built)."""
        return self._wipe

    def connect_analysis(self, shadows: Any = None, heatmap: Any = None,
                         sun_hours: Any = None) -> None:
        """The 2D analysis the 3D view lays on its ground (L2): the shadow overlay's
        controller, the heatmap's controller and the shared Hours of Sun
        (``ui.live_sun_map.LiveSunMap``: its switch, its signal, whether its map is
        current). Kept for every engine this workspace builds."""
        self._shadow_source, self._sun_heatmap = shadows, heatmap
        self._sun_hours = sun_hours
        if self._analysis is not None:
            self._analysis.connect_sources(shadows, heatmap, sun_hours)

    def _build_analysis_controls(self, pane: _Pane3D) -> None:
        from .wipe import BeforeAfterWipe

        self._analyze_button = QToolButton(pane.strip)
        self._analyze_button.setText(self.tr("Analyze"))
        self._analyze_button.setToolTip(self.tr(
            "Sun and shade on the ground, the sun path, a day sweep, Cutaway and growth"))
        self._analyze_button.setAutoRaise(True)
        self._analyze_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._analyze_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self._analyze_button)
        menu.addSection(self.tr("On the ground"))
        menu.addActions(list(self._drape_actions.values()))
        menu.addSeparator()
        menu.addAction(self._sun_path_action)
        menu.addAction(self._sweep_action)
        menu.addAction(self._cutaway_action)
        menu.addSection(self.tr("Growth"))
        menu.addActions(list(self._jump_actions.values()))
        menu.addAction(self._back_action)
        self._analyze_button.setMenu(menu)
        pane.strip_layout.addWidget(self._analyze_button)
        # the before/after of a growth jump stands in the view's place (a page of the body)
        self._wipe = BeforeAfterWipe(pane.body)
        self._wipe.closed.connect(self.close_wipe)
        pane.body.addWidget(self._wipe)

    def _build_legend(self, pane: _Pane3D) -> None:
        from open_garden_planner.core.scene3d.sun_path import ARC_KINDS, ARC_RGBA

        row = QWidget(pane.notices)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        names = {"today": self.tr("Plan date"), "june_solstice": self.tr("21 June"),
                 "december_solstice": self.tr("21 December"), "march_equinox": self.tr("20 March")}
        self._legend_swatches: list[QWidget] = []
        self._legend_names = names
        self._legend_labels: dict[str, QLabel] = {}
        for kind in ARC_KINDS:
            swatch = QFrame(row)  # a bar of the arc's colour (no text: not a label)
            swatch.setFixedSize(16, 4)
            red, green, blue, _alpha = ARC_RGBA[kind]
            palette = swatch.palette()  # the arc's own colour: data, not a theme token
            palette.setColor(QPalette.ColorRole.Window, QColor(red, green, blue))
            swatch.setPalette(palette)
            swatch.setAutoFillBackground(True)
            layout.addWidget(swatch, 0, Qt.AlignmentFlag.AlignVCenter)
            label = QLabel(names[kind], row)
            label.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(label)
            layout.addSpacing(6)
            self._legend_swatches.extend((swatch, label))
            self._legend_labels[kind] = label
        self._legend_note = QLabel(self.tr("Set a garden location to draw the sun path."), row)
        self._legend_note.setTextFormat(Qt.TextFormat.PlainText)
        self._legend_note.setWordWrap(True)
        layout.addWidget(self._legend_note, 1)
        layout.addStretch(1)
        row.hide()
        pane.notice_layout.addWidget(row)
        self._legend_row = row

    def legend_text(self) -> str:
        """What the legend says ("" while it is hidden) — the tests' read."""
        row = self._legend_row
        if row is None or row.isHidden():
            return ""
        if not self._legend_note.isHidden():
            return self._legend_note.text()
        return " ".join(widget.text() for widget in self._legend_swatches
                        if isinstance(widget, QLabel) and widget.text())

    def _update_legend(self) -> None:
        row, analysis = self._legend_row, self._analysis
        if row is None:
            return
        shown = analysis is not None and analysis.sun_path_visible and self._chrome_visible
        if shown and analysis is not None:
            located = analysis.has_location()
            for widget in self._legend_swatches:
                widget.setVisible(located)
            self._legend_note.setVisible(not located)
            twins = _twin_arcs(analysis.arcs())
            for kind, label in self._legend_labels.items():
                name = self._legend_names[kind]
                # within days of a key day the plan date's (thicker) arc covers its twin:
                # the legend says so instead of promising an arc nobody can see
                label.setText(self.tr("{day} — same path as the plan date").format(day=name)
                              if kind in twins else name)
        row.setVisible(shown)
        self._refresh_notices()

    def _wire_analysis(self, host: EngineHost, orbit: OrbitInput,
                       controller: Scene3DController) -> None:
        from .analysis_controller import AnalysisController
        from .compass_glyphs import cardinal_glyphs
        from .growth_jump import GrowthJump

        clock = self._clock
        assert clock is not None
        analysis = AnalysisController(host, clock, self._location, controller.plan_size,
                                      glyphs=cardinal_glyphs, parent=self)
        analysis.connect_sources(self._shadow_source, self._sun_heatmap, self._sun_hours)
        analysis.changed.connect(self._sync_analysis_actions)
        analysis.probe_changed.connect(self._refresh_card)
        orbit.ground_clicked.connect(self._on_ground_clicked)
        jump = GrowthJump(clock, host, self)
        jump.wipe_ready.connect(self._show_wipe)
        jump.changed.connect(self._sync_analysis_actions)
        controller.applied.connect(self._on_applied_for_analysis)
        self._analysis, self._jump = analysis, jump
        for action in self._analysis_actions():
            action.setEnabled(True)
        self._sync_analysis_actions()

    def _unwire_analysis(self) -> None:
        self.close_wipe()
        self._xray_timer.stop()
        analysis, self._analysis = self._analysis, None
        if analysis is not None:
            analysis.shutdown()
            analysis.deleteLater()
        jump, self._jump = self._jump, None
        if jump is not None:
            jump.forget()
            jump.deleteLater()
        for action in self._analysis_actions():
            action.setEnabled(False)
        self._update_legend()

    def _analysis_document_changed(self) -> None:
        self.close_wipe()
        if self._analysis is not None:
            self._analysis.document_changed()
        if self._jump is not None:
            self._jump.forget()

    def _sync_analysis_actions(self) -> None:
        """The menu shows the analysis's state — also when it changed by itself (the
        sweep ended at sunset, a growth jump was made, the map arrived)."""
        analysis, jump = self._analysis, self._jump
        if analysis is not None:
            self._drape_actions[analysis.drape_mode].setChecked(True)
            self._sun_path_action.setChecked(analysis.sun_path_visible)
            self._sweep_action.setChecked(analysis.sweeping)
            self._cutaway_action.setChecked(analysis.cutaway)
        origin = jump.origin if jump is not None else None
        self._back_action.setEnabled(origin is not None)
        self._back_action.setText(
            self.tr("Back to {date}").format(date=_locale_date(origin)) if origin is not None
            else self.tr("Back to the Starting Date"))
        self._update_legend()
        self._refresh_card()

    def set_drape_mode(self, mode: Any) -> None:
        """What lies on the 3D ground (``DrapeMode``)."""
        if self._analysis is not None:
            self._analysis.set_drape_mode(mode)
        self._sync_analysis_actions()

    def set_sun_path_visible(self, visible: bool) -> None:
        if self._analysis is not None:
            self._analysis.set_sun_path_visible(visible)
        self._sync_analysis_actions()

    def set_sweeping(self, on: bool) -> bool:
        """Start (or stop) the day sweep; False when there is no day to sweep — the
        strip says why."""
        analysis = self._analysis
        started = False
        if analysis is not None:
            if on:
                started = analysis.start_sweep()
                if not started:
                    self._say(_NOTICE_SYNC, self.tr(
                        "There is no daylight to sweep on this date here, or the garden has "
                        "no location."))
            else:
                analysis.stop_sweep()
        self._sync_analysis_actions()
        return started

    def set_cutaway(self, on: bool) -> None:
        if self._analysis is not None:
            self._analysis.set_cutaway(on)
        self._sync_analysis_actions()
        self._run_xray()

    def jump_years(self, years: int) -> None:
        """Move the plan date ``years`` forward; the before/after follows (L2.3). From an
        open comparison its after-picture is the new before (the view is not shown, so
        it could give no frame)."""
        if self._jump is None:
            return
        if self._analysis is not None:
            self._analysis.stop_sweep()   # the before-picture shows the whole day's map
        before = self._wipe.after_image() if self._wipe_shown() else None
        self.close_wipe()
        self._jump.jump(years, before)

    def growth_back(self) -> None:
        if self._jump is None:
            return
        self.close_wipe()
        self._jump.back()

    def _on_applied_for_analysis(self, report: TickReport) -> None:
        if report.snapshot:
            self._schedule_xray()
        jump, controller = self._jump, self._controller
        if jump is not None and controller is not None:
            jump.on_applied(report.snapshot, controller.pass_date)

    # … the probe

    def _ground_point(self, x: float, y: float) -> tuple[float, float] | None:
        """Where the view ray through ``(x, y)`` meets the ground (scene E, N), or None
        when it looks above the horizon."""
        from open_garden_planner.core.scene3d.drape import DRAPE_LIFT_CM
        from open_garden_planner.core.scene3d.pick_oracle import perspective_ray

        host = self._host
        if host is None:
            return None
        eye, target, fov = self._camera_now()
        try:
            ray = perspective_ray(eye, target, fov, host.view_size(), x, y)
        except (ValueError, ZeroDivisionError):
            return None
        down = ray.direction[2]
        if down >= -1e-9:
            return None
        # the drape's plane, not z = 0: at a walk-mode grazing angle of 4.6 degrees the
        # 1.5 cm lift is 19 cm — two map cells (senior review of #386)
        reach = (DRAPE_LIFT_CM - ray.origin[2]) / down
        return (ray.origin[0] + reach * ray.direction[0], ray.origin[1] + reach * ray.direction[1])

    def _on_ground_clicked(self, x: float, y: float) -> None:
        """A click that met no item: with the hours of sun on the ground, it probes."""
        from .analysis_modes import DrapeMode

        analysis = self._analysis
        if analysis is None or analysis.drape_mode is not DrapeMode.SUN_HOURS:
            return
        point = self._ground_point(x, y)
        if point is not None:
            analysis.probe(*point)
        self._refresh_card()

    def _probe_text(self) -> str:
        """The probe's reading for the card's place ("" for no probe)."""
        from open_garden_planner.core.measurements import format_length
        from open_garden_planner.ui.sun_exposure_text import sun_requirement_label

        from .analysis_modes import DrapeMode

        analysis = self._analysis
        if analysis is None:
            return ""
        probe: ProbeResult | None = analysis.probe_result
        if probe is None:
            if analysis.drape_mode is DrapeMode.SUN_HOURS:
                return self.tr("Click the ground to read its hours of sun.")
            return ""
        if probe.reason == "outside":
            return self.tr("That spot lies outside the hours-of-sun map.")
        if probe.reason == "updating":
            return self.tr("The hours of sun are being updated for the changed plan.")
        if probe.reason == "unavailable":
            return self.tr("The hours of sun could not be computed for the changed plan.")
        if probe.reason != "ok" or probe.minutes is None or probe.band is None:
            return self.tr("The hours of sun are not computed yet for this plan date.")
        return self.tr("Ground at {east} east, {north} north: {hours} h of direct sun on "
                       "{date} — {band}.").format(
            east=format_length(probe.east_cm), north=format_length(probe.north_cm),
            hours=_locale_number(probe.minutes / 60.0), date=_locale_date(probe.day),
            band=sun_requirement_label(probe.band.value))

    # … the X-ray

    def _schedule_xray(self) -> None:
        analysis = getattr(self, "_analysis", None)
        if analysis is not None and analysis.cutaway:
            self._xray_timer.start()

    def _run_xray(self) -> None:
        from .selection_bridge import selected_record_ids

        analysis, controller, scene = self._analysis, self._controller, self._scene
        if analysis is None or controller is None or scene is None:
            return
        try:
            selected = selected_record_ids(scene)
        except RuntimeError:  # the scene is being torn down
            return
        eye, _target, _fov = self._camera_now()
        parts_of = self._held_parts()
        analysis.update_xray(eye, selected, controller.apply_count,
                             lambda: (controller.sync.records, parts_of))

    # … the before/after wipe

    def _wipe_shown(self) -> bool:
        pane, wipe = self._pane, getattr(self, "_wipe", None)
        return pane is not None and wipe is not None and pane.body.currentWidget() is wipe

    def _show_wipe(self, before: Any, after: Any, from_day: Any, to_day: Any) -> None:
        pane, wipe = self._pane, self._wipe
        if pane is None or wipe is None or pane.engine_widget is None:
            return
        wipe.show_pair(before, after,
                       self.tr("Before: {date}").format(date=_locale_date(from_day)),
                       self.tr("After: {date}").format(date=_locale_date(to_day)))
        pane.body.setCurrentWidget(wipe)
        wipe.setFocus(Qt.FocusReason.OtherFocusReason)
        self._on_pane_showing()

    def close_wipe(self) -> None:
        """Back to the 3D view (the wipe's "Back to 3D View", Escape, a new jump)."""
        pane = self._pane
        if not self._wipe_shown() or pane is None:
            return
        if pane.engine_widget is not None:
            pane.body.setCurrentWidget(pane.engine_widget)
        else:
            pane.body.setCurrentWidget(pane.message_page)
        self._on_pane_showing()


#: Two arcs whose noons lie this close (degrees of elevation) draw as one.
TWIN_ARC_DEG: Final = 0.5


def _twin_arcs(arcs: Sequence[Any]) -> frozenset[str]:
    """The key days whose arc the plan date's arc covers: their solar noon within
    ``TWIN_ARC_DEG`` of the plan date's (3D review round 2 of #386)."""
    today = next((arc for arc in arcs if arc.kind == "today"), None)
    if today is None or today.noon is None:
        return frozenset()
    return frozenset(arc.kind for arc in arcs if arc.kind != "today" and arc.noon is not None
                     and abs(arc.noon.elevation_deg - today.noon.elevation_deg) <= TWIN_ARC_DEG)


def _locale_date(day: Any) -> str:
    """A date in the locale's short format ("" for none)."""
    from PyQt6.QtCore import QDate, QLocale

    if day is None:
        return ""
    return QLocale().toString(QDate(day.year, day.month, day.day), QLocale.FormatType.ShortFormat)


def _locale_number(value: float) -> str:
    from PyQt6.QtCore import QLocale

    return QLocale().toString(float(value), "f", 1)

