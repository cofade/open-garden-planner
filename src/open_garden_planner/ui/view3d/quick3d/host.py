"""``Quick3DHost`` — the ``QQuickView`` that shows the garden (L1.2). ENGINE module.

One object owns the Qt Quick window, the loaded ``qml/Garden.qml`` and every
engine ``Model``. It is the ``EngineScene`` a ``Quick3DSink`` drives, and it is
what the workspace embeds (L1.3: ``container()``) and what a render reads back
(``grab()``).

Host choice (ADR-048 criterion 3): a ``QQuickView`` in a
``QWidget.createWindowContainer`` — never a ``QQuickWidget``, which moves the
whole top-level window onto RHI composition. Create it once and keep it: hide
and show it, never rebuild it per open.

THE STATE MACHINE. A Qt Quick window can be asked for a frame in situations where
answering kills the process or returns a picture that is not the scene, so the
host never guesses: ``state`` is derived on every call from what Qt reports
(``_facts()`` → ``lifecycle.state_of``), and every public method either answers
truthfully or raises ``HostStateError``. **The contract — the facts, the states,
what each promises, which call is legal in which, what ``wait_ready()`` means,
what raises what — is the docstring of ``lifecycle.py``, and only there.** This
module supplies the facts and nothing else.

What Qt was measured to do, and why each fact is read (Qt 6.11; Direct3D 11 on
an RTX 4070 and on WARP; xcb + OpenGL on llvmpipe):

- ``grabWindow()`` on a window WITHOUT a scene graph renders one frame offscreen
  and tears everything down. For a window whose platform window was never
  created that is the one offscreen frame (correct, pixel-identical to a shown
  grab); a second one is the bare background. For a window that IS shown and
  waits for its first expose — or is shown afterwards — the process dies in the
  next event-loop pass (abort, access violation or heap corruption). On xcb the
  same death follows a window that was shown and hidden again before any event.
- A window closed by the user keeps its scene graph and loses its platform
  window; a raw grab of it is an access violation.
- A ``QSplitter`` pane collapsed to width 0 leaves the window visible, exposed
  and 0 px wide: a raw grab returns a blank image of the OLD size and a pick
  returns a bogus hit. One pixel wide, nothing 3D is drawn.
- A resize reaches the window in one of two ways, and each leaves something
  behind for a moment. ASYNCHRONOUSLY (a splitter move, ``resize()``,
  ``showMaximized()``): the window has the new size at once, the QML root item
  only when the event loop delivered the resize event. SYNCHRONOUSLY
  (``showFullScreen()``): window and root item agree at once — and a grab still
  comes back in the OLD size, because ``grabWindow()`` on a shown window renders
  into the swap chain as it is, and Qt resizes that when it next draws the
  window (20 of 20).
- Qt draws the window when the platform asks for it — and nothing obliges a
  platform to ask: a pane that GROWS beyond the screen's edge gets its resize
  event and no expose, and with the display asleep its swap chain keeps the old
  size for as long as it stays there (a raw grab: 49 x 500 px for a 136 x 500
  window). Round 3 waited for that expose; it never came. So the host keeps no
  fact "the render target has caught up": it takes a frame and looks at its
  size (``_frame``) — against Qt's own rounding, half a device pixel
  (``_other_size``).
- A pick right after a resize, with no frame in between, MISSES the box under
  the cursor (the engine picks with the viewport of the frame it rendered last);
  after one frame — even one of the old size — it hits. Hence ``pick`` and
  ``project`` take a frame themselves when the host knows of none for the
  window's size: one after a resize, none in the steady state, and ONE per
  refusal — not one per call — while the render target stays behind
  (``_require_frame``).
- Under the SOFTWARE scene graph (``QT_QPA_PLATFORM=offscreen``) Qt Quick 3D
  draws nothing. ``renders_3d()`` is False there, and ``grab`` / ``pick`` /
  ``project`` raise ``EngineError``: a frame without the garden must not pass
  for one.

Do not wait for ``frameSwapped`` to be sure of a frame: on Windows, update
requests come from a display-vblank thread, and with the monitor asleep a live
window presents its first frame and then none. ``grab()`` on a ``LIVE`` host
renders the current state synchronously — it is the synchronisation point.

TROUBLE IN A LIVE VIEW — ``health()``, on the GUI thread. A shown view has
nobody to raise to, and a frozen exe has no stderr. What Qt itself reports on
the GUI thread is collected and logged (Python ``logging``, hence ``app.log``):
QML warnings (the engine's ``warnings`` signal), a graphics device that could
not be created (``sceneGraphError`` — the host CONNECTS it: with nothing
connected Qt shows a modal error box and then aborts the process, measured:
exit ``0xC0000409``), and how many frames were presented.

There is deliberately NO Qt message recorder for a shown host. Qt renders on a
thread of its own (the threaded render loop — measured on Direct3D 11, GPU and
WARP); PyQt's message-handler trampoline needs the GIL; and a render-thread
message that arrives while the GUI thread sits in a Python-called ``hide()``
deadlocks the process for good (5 of 5). Shader compile errors of the shipped
shaders are therefore caught BEFORE release — the render tier and the frozen
self-test compile every one — not at run time.

No input handling and no orbit camera here: L1.3.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple, cast

import numpy as np
from PyQt6 import sip
from PyQt6.QtCore import (
    Q_ARG,
    Q_RETURN_ARG,
    QCoreApplication,
    QEvent,
    QEventLoop,
    QMetaObject,
    QObject,
    Qt,
    QTimer,
    QUrl,
)
from PyQt6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QPlatformSurfaceEvent,
    QQuaternion,
    QVector3D,
    QWindow,
)
from PyQt6.QtQuick import (
    QQuickGraphicsConfiguration,
    QQuickItem,
    QQuickView,
    QQuickWindow,
    QSGRendererInterface,
)

from open_garden_planner.core.scene3d import (
    EngineBuffers,
    EnginePose,
    Rgba,
    engine_to_scene_points,
    scene_to_engine_points,
    scene_to_engine_vectors,
)
from open_garden_planner.core.scene3d.selection import SELECTION_RGBA

from .adapter import GroundPlacement, PartSpec
from .geometry import BufferGeometry, ReloadableGeometry
from .ground_tiles import GroundTileError, GroundTiles
from .lifecycle import (
    REPROBE_S,
    STALL_S,
    WAIT_READY_DEFAULT_S,
    HostState,
    HostStateError,
    WindowFacts,
    state_of,
    why_no_frame,
)
from .look import (
    COLOR_PROPERTIES,
    LINEAR_COLOR_PROPERTIES,
    NEUTRAL_DAY,
    LookSpec,
    SkySpec,
    scene_properties,
    sky_properties,
)
from .materials import PART_COMPONENTS, tint_uniform
from .shots import PerspectiveShot, Shot, TopDownShot

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

QML_DIR: Final = Path(__file__).resolve().parent / "qml"
SCENE_FILE: Final = "Garden.qml"

_DIRECT: Final = Qt.ConnectionType.DirectConnection
_QUEUED: Final = Qt.ConnectionType.QueuedConnection
_LIGHT_FORWARD: Final = (0.0, 0.0, -1.0)  # a DirectionalLight shines down its local -Z
_LOG: Final = logging.getLogger(__name__)
_KEEP_WARNINGS: Final = 50  # QML warnings kept for health() and logged; the rest are only counted
_WAIT_STEP_MS: Final = 5    # wait_ready(): how long one pass of its event loop may block
#: A pass of ``wait_ready()``'s event loop that took this much longer than its step was
#: BUSY — a handler of something else ran in it — and is not counted as silence. (An idle
#: 5 ms pass takes 5 to 16 ms on Windows.)
_BUSY_PASS_S: Final = 0.05
#: The longest timeout ``wait_ready()`` takes, seconds: a day. Qt's ``processEvents``
#: takes milliseconds in a C int; ``inf`` and 3e6 s overflowed it.
_LONGEST_WAIT_S: Final = 86_400.0
#: The selection ring's vertex shader moves vertices outwards by pixels, which at a
#: distance are centimetres; the engine culls by the bounds it is told. So the ring's
#: bounds are this much wider than its mesh on every side (L1.8).
RING_BOUNDS_MARGIN_CM: Final = 500.0
#: The analysis overlays of L2 (#386) — layer → the scene property that shows it.
#: ``"shade"`` multiplies the frame under it (the 2D shadows), ``"drape"`` blends over
#: it (the hours-of-sun map), ``"lines"`` is opaque (``Garden.qml``).
OVERLAY_LAYERS: Final = {"shade": "shadeVisible", "drape": "drapeVisible",
                         "lines": "linesVisible"}
#: Qt sizes a render target as ``qRound(logical × ratio)`` per side: the RIGHT frame is
#: at most half a device pixel off ``logical × ratio``. The rest is the float error of
#: that product (3000 × 1.1 is not exact; a neighbour's frame is at least 0.1 px further).
_HALF_PIXEL: Final = 0.5 + 1e-6

_API: Final = QSGRendererInterface.GraphicsApi
#: Our names for Qt's graphics APIs — keyed by the enum MEMBER, never by its
#: ``.name``: PyQt6 6.11 calls value 3 ``OpenGL`` but value 4 ``Direct3D11Rhi``
#: (the ``…Rhi`` aliases win or lose by declaration order). CI found it: the
#: Linux run reported ``OpenGL`` where a list written on Windows said ``OpenGLRhi``.
GRAPHICS_API_NAMES: Final = {
    _API.Unknown: "Unknown", _API.Software: "Software", _API.OpenVG: "OpenVG",
    _API.OpenGL: "OpenGL", _API.Direct3D11: "Direct3D11", _API.Vulkan: "Vulkan",
    _API.Metal: "Metal", _API.Null: "Null", _API.Direct3D12: "Direct3D12",
}
#: The APIs Qt Quick 3D draws with (RHI-based, and not the null backend).
RENDERING_APIS: Final = frozenset({"OpenGL", "Direct3D11", "Vulkan", "Metal", "Direct3D12"})

__all__ = [
    "GRAPHICS_API_NAMES", "QML_DIR", "RENDERING_APIS", "SCENE_FILE", "EngineError", "EnginePart",
    "HostHealth", "HostState", "HostStateError", "PickHit", "Quick3DHost", "shown_quick_windows",
]


class EngineError(RuntimeError):
    """The engine could not do what it was asked (QML did not load, a part was
    refused or could not be destroyed, a property is missing, a scene function
    failed, this backend cannot render 3D)."""


@dataclass(frozen=True, slots=True)
class PickHit:
    """What is under a view position: the item, its mesh part and the hit point in
    the SCENE frame (east, north, up — centimetres).

    ``behind`` (L1.8): what the same ray meets AFTER this hit, nearest first — every
    further Model, also further parts of the same item. A click on an item of a
    locked layer falls through to the first selectable item behind it, as it does
    on the 2D canvas (``ui/view3d/selection_bridge.py``); the hits in ``behind``
    carry no ``behind`` of their own."""

    item_id: str
    part_index: int
    point: tuple[float, float, float]
    behind: tuple[PickHit, ...] = ()


@dataclass(frozen=True, slots=True)
class EnginePart:
    """One Model as the ENGINE holds it — read back from the QML scene, not from
    the sink's books (``Quick3DHost.engine_parts``)."""

    item_id: str
    part_index: int
    kind: str
    position: tuple[float, float, float]  # engine frame
    yaw_deg: float
    tint_rgb: tuple[int, int, int]
    casts_shadow: bool
    has_geometry: bool
    visible: bool
    #: 1.0, or how opaque the part is drawn while it fades as an occluder (L2.4)
    fade: float = 1.0
    #: The share of its pixels the part's ACTIVE material draws: 1 for its look, the
    #: screen door's opacity while it fades, 0 for a roof Cutaway cuts (L2.4)
    drawn: float = 1.0


@dataclass(frozen=True, slots=True)
class HostHealth:
    """What Qt reported about a host on the GUI thread (``Quick3DHost.health``).

    Poll it — a timer in the workspace (L1.3) turns it into a notice. Everything
    in it was also written to the log when it arrived.
    """

    #: Frames Qt presented so far. 0 some time after ``wait_ready()`` returned
    #: True means nothing reaches the screen. (With the display asleep it stays
    #: at 1: never wait for a particular count.)
    frames_presented: int
    #: The QML engine's warnings since the host was built — a binding that
    #: failed, a scene function that threw. The first ones; ``qml_warning_count``
    #: counts all.
    qml_warnings: tuple[str, ...]
    qml_warning_count: int
    #: Qt could not create the graphics device for this window
    #: (``QQuickWindow.sceneGraphError``); the host will never become live.
    scene_graph_error: str | None

    @property
    def ok(self) -> bool:
        """No QML warning and no graphics failure (says nothing about frames)."""
        return self.scene_graph_error is None and self.qml_warning_count == 0


class _Part:
    """The handle of one engine Model: the Model and the geometry only it uses, and
    whose part it is (the X-ray of L2.4 fades parts by item).

    The HOST owns both (``Quick3DHost._parts``); a sink holds handles as names.
    """

    __slots__ = ("geometry", "item_id", "kind", "model")

    def __init__(self, model: QObject, geometry: BufferGeometry, kind: str,
                 item_id: str = "") -> None:
        self.model: QObject | None = model
        self.geometry: BufferGeometry | None = geometry
        self.kind = kind
        self.item_id = item_id

    def forget(self) -> None:
        self.model = None
        self.geometry = None


#: The events of a view that can change what a frame of it is.
_SIGNS: Final = frozenset({
    QEvent.Type.Resize, QEvent.Type.Expose, QEvent.Type.UpdateRequest, QEvent.Type.Show,
    QEvent.Type.Hide, QEvent.Type.WindowStateChange, QEvent.Type.PlatformSurface})


class _WindowWatch(QObject):
    """What only the view's own event stream can tell (an event filter runs on the GUI
    thread, before the window handles the event).

    ``created``: a platform window was created at some point (Qt's
    ``PlatformSurface`` event). ``QWindow.handle()`` is the same fact and PyQt6
    does not bind it; ``winId()`` would CREATE the window.

    Two COUNTERS, and nothing an event could switch on:

    - ``resizes``: resize events so far. A frame taken before the last one says
      nothing about a frame now (``Quick3DHost._frame_at``).
    - ``signs``: events so far that can change what a frame is (``_SIGNS``).
      ``wait_ready()`` reads it as "something happened since I looked".

    No event here ever says "a frame can be had": only a frame says that. Round 3
    latched "an expose arrived after the last resize" into the state — and Windows
    sends none to a window that is not on a screen (``lifecycle.py``).
    """

    def __init__(self, parent: QWindow) -> None:
        super().__init__(parent)
        self.created = False
        self.resizes = 0
        self.signs = 0

    def eventFilter(self, _watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802 - Qt's name
        if event is None:
            return False
        kind = event.type()
        if kind in _SIGNS:
            self.signs += 1
        if kind == QEvent.Type.Resize:
            self.resizes += 1
        elif (isinstance(event, QPlatformSurfaceEvent) and event.surfaceEventType()
                == QPlatformSurfaceEvent.SurfaceEventType.SurfaceCreated):
            self.created = True
        return False


def _connect_queued(signal: Any, slot: Callable[..., None]) -> None:
    """``signal.connect(slot, QueuedConnection)``: the slot runs in the event loop of the
    thread that connected — the GUI thread — wherever Qt emits the signal. (PyQt takes
    the connection type as a second argument; its type stubs do not declare it, hence
    the untyped ``signal``.)"""
    signal.connect(slot, _QUEUED)


def _js_object(value: Any) -> Any:
    """A QML function's JS return value arrives as ``QJSValue``: unwrap it."""
    return value.toVariant() if hasattr(value, "toVariant") else value


def _set(target: QObject, name: str, value: object) -> None:
    """Write a DECLARED property; a missing one is an error, not a silent dynamic
    property (a renamed QML property would otherwise be set into the void)."""
    meta = target.metaObject()
    if meta is None or meta.indexOfProperty(name) < 0:
        raise EngineError(f"the scene has no property {name!r} (renamed in {SCENE_FILE}?)")
    if not target.setProperty(name, value):
        raise EngineError(f"the scene refused {value!r} for its property {name!r}")


def _get(target: QObject, name: str) -> Any:
    meta = target.metaObject()
    if meta is None or meta.indexOfProperty(name) < 0:
        raise EngineError(f"the scene has no property {name!r} (renamed in {SCENE_FILE}?)")
    return target.property(name)


class _Behind(NamedTuple):
    """A frame that was refused for its size: what the host saw then (module docstring of
    ``lifecycle.py``, ``REPROBE_S``)."""

    facts: WindowFacts
    signs: int      # ``_WindowWatch.signs`` at that moment
    at: float       # ``time.perf_counter()``
    found: str      # what Qt rendered instead


def _behind_text(call: str, found: str) -> str:
    return (f"{call}(): {found}: the render target has not caught up with the window's size "
            "(Qt resizes it when it next draws the window — which it may not do while the "
            "view is not on a screen). Not now; wait_ready() says when a frame can be had")


class Quick3DHost:
    """The garden's Qt Quick 3D view (module docstring). GUI thread only.

    ``size``: logical pixels of a standalone window. ``qml_dir``: where
    ``Garden.qml`` and its shaders are loaded from (tests point it at a copy).
    ``log``: an optional ``log(phase, **fields)`` callable.
    """

    def __init__(self, size: tuple[int, int] = (1280, 720), *, qml_dir: Path | None = None,
                 look: LookSpec = NEUTRAL_DAY, log: Callable[..., None] | None = None,
                 prefer_software: bool = False) -> None:
        self._log: Callable[..., None] = log if log is not None else (lambda *_a, **_k: None)
        self._parts: set[_Part] = set()  # THE owner of every Model and geometry
        #: The analysis overlays' geometries by layer (L2, ``set_overlay``), and the
        #: items whose parts are drawn faded with their opacity (``set_faded_items``).
        self._overlays: dict[str, ReloadableGeometry] = {}
        self._faded: frozenset[str] = frozenset()
        self._fade_opacity = 1.0
        #: The look on screen, and the sun the pipeline sent last (engine frame; None:
        #: no sun, or it is down). Together they decide the key light (``_apply_light``).
        self._shown_look: LookSpec = NEUTRAL_DAY   # the scene file's own defaults
        self._sun_travel: tuple[float, float, float] | None = None
        #: The sky that lights and backs the perspective view — None: no sky texture
        #: (a plain background and a flat fill; the software fallback, the self-test).
        self._sky: SkySpec | None = None
        #: Sky textures built so far — each is a whole procedural sky and a light probe
        #: Qt filters once: the instrument behind "one build per noticeable sun move".
        self.sky_builds = 0
        #: How long the last ``set_sky`` took on the GUI thread, milliseconds (the
        #: generation; the probe's filtering lands in the next frame Qt renders).
        self.last_sky_build_ms = 0.0
        self._container: QWidget | None = None
        self._spent = False   # the one offscreen frame was taken (Qt cannot tell us)
        self._closed = False  # close() ran to its end (Qt deletes the view only later)
        self._qml_warnings: list[str] = []
        self._qml_warning_count = 0
        self._scene_graph_error: str | None = None
        self._gui_thread = threading.get_ident()
        #: Slot calls that arrived on another thread than the one that built the host.
        #: Must stay 0 — the render tier asserts it: no Python on Qt's render thread.
        self.slot_calls_off_the_gui_thread = 0
        self.frames_presented = 0
        self.grabs = 0
        #: Frames of a live host that came back in another size than the window's and
        #: were refused (``grab``, ``pick``, ``project``, ``wait_ready()``'s probe). Not
        #: an error count: this is HOW the host learns that the render target is behind —
        #: right after a resize Qt delivered inside the call, or while no part of the
        #: view is on a screen.
        self.stale_frames = 0
        #: Frames the host took for itself, to know (``wait_ready``, ``pick``, ``project``).
        self.probes = 0
        #: The longest ``wait_ready()`` waited without a sign of progress before the host
        #: came up, seconds — what ``STALL_S`` has to stay clear of (a diagnostic).
        self.longest_quiet_s = 0.0
        #: (width, height, resize events) of the last frame that had the window's size.
        self._frame_at: tuple[int, int, int] | None = None
        #: The last frame that was REFUSED for its size, and what the host saw then — so
        #: that ``pick()`` / ``project()`` do not take a frame per call while nothing changes.
        self._behind: _Behind | None = None
        started = time.perf_counter()
        self._view = QQuickView()
        self._watch = _WindowWatch(self._view)
        self._view.installEventFilter(self._watch)
        self._view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
        # A hidden window keeps its scene graph (both are Qt's defaults; said out loud
        # because "scene graph up" must not flicker with visibility).
        self._view.setPersistentSceneGraph(True)
        self._view.setPersistentGraphics(True)
        self._view.resize(*size)
        # What Qt tells the GUI thread — connected BEFORE the scene loads. Queued where
        # Qt may emit from its render thread: no Python ever runs there (module docstring).
        engine = self._view.engine()
        if engine is not None:
            engine.warnings.connect(self._on_qml_warnings)
        _connect_queued(self._view.sceneGraphError, self._on_scene_graph_error)
        _connect_queued(self._view.frameSwapped, self._on_frame_swapped)
        #: True when this window was asked to render on the SOFTWARE adapter of its
        #: graphics API (WARP on Direct3D; L1.3's compatibility mode, ADR-060). Per
        #: window, and set before its scene graph exists — measured: this works for a
        #: window created at any time, while QSG_RHI_PREFER_SOFTWARE_RENDERER is read
        #: once per process and does nothing after the first Qt Quick window.
        self.prefers_software = bool(prefer_software)
        #: How often ``release_cached_resources()`` was called (L1.3; the soak reads it).
        self.cache_releases = 0
        if prefer_software:
            configuration = QQuickGraphicsConfiguration()
            configuration.setPreferSoftwareDevice(True)
            self._view.setGraphicsConfiguration(configuration)
        source = (qml_dir if qml_dir is not None else QML_DIR) / SCENE_FILE
        self._view.setSource(QUrl.fromLocalFile(str(source)))
        root = self._view.rootObject()
        if root is None:
            errors = "; ".join(error.toString() for error in self._view.errors())
            self._view.deleteLater()
            self._closed = True
            raise EngineError(f"{source} did not load: {errors or 'no root object'}")
        self._root: QQuickItem = root
        #: The baked ground this host shows — its tile Models and their textures (L1.5).
        self.ground = GroundTiles(root)
        self.qml_load_ms = (time.perf_counter() - started) * 1000.0
        self._log("qml_loaded", ms=round(self.qml_load_ms, 1), source=source.name)
        try:
            self.set_look(look)
        except Exception:
            self.close()  # a scene file without the look's properties: no half-built host
            raise

    # ── state ────────────────────────────────────────────────────────────────

    def _facts(self) -> WindowFacts | None:
        """What Qt says right now — the ONLY input of the state (None: the view is gone)."""
        view = self._view
        if sip.isdeleted(view):
            return None
        minimised = view.visibility() == QWindow.Visibility.Minimized
        container = self._container
        if not minimised and container is not None and not sip.isdeleted(container):
            top_level = container.window()
            minimised = top_level is not None and top_level.isMinimized()
        return WindowFacts(
            surface_created=self._watch.created, visible=bool(view.isVisible()),
            minimised=bool(minimised), width=int(view.width()), height=int(view.height()),
            scene_graph=bool(view.isSceneGraphInitialized()), exposed=bool(view.isExposed()),
            root_width=float(self._root.width()), root_height=float(self._root.height()))

    @property
    def state(self) -> HostState:
        """Derived from Qt on every call — the contract is ``lifecycle.py``'s docstring."""
        return state_of(self._facts(), closed=self._closed, spent=self._spent)

    @property
    def is_closed(self) -> bool:
        """True after ``close()`` — and when Qt destroyed the view itself, which happens
        when the widget that parents ``container()`` is destroyed."""
        return self.state is HostState.CLOSED

    def is_visible(self) -> bool:
        facts = self._facts()
        return facts is not None and not self._closed and facts.visible

    def _look(self, call: str) -> tuple[HostState, WindowFacts]:
        """State and facts of an OPEN host — ``HostStateError`` when it is closed."""
        facts = self._facts()
        state = state_of(facts, closed=self._closed, spent=self._spent)
        if facts is None or state is HostState.CLOSED:
            raise HostStateError(f"{call}(): the host is closed (or Qt destroyed its view)")
        return state, facts

    def _open(self, call: str) -> HostState:
        return self._look(call)[0]

    # ── EngineScene (driven by Quick3DSink) ──────────────────────────────────

    def create_part(self, spec: PartSpec, pose: EnginePose, tint_rgba: Rgba) -> object:
        self._open("create_part")
        if spec.kind not in PART_COMPONENTS:
            raise EngineError(f"no part component for material kind {spec.kind!r}")
        geometry = BufferGeometry(spec.buffers)
        model = QMetaObject.invokeMethod(
            self._root, "createPart", _DIRECT, Q_RETURN_ARG("QVariant"),
            Q_ARG("QVariant", spec.kind), Q_ARG("QVariant", spec.item_id),
            Q_ARG("QVariant", spec.part_index), Q_ARG("QVariant", geometry),
            Q_ARG("QVariant", spec.casts_shadow))
        if not isinstance(model, QObject):
            raise EngineError(
                f"the scene created no Model for part {spec.part_index} ({spec.kind}) "
                f"of item {spec.item_id!r}")
        part = _Part(model, geometry, spec.kind, spec.item_id)
        self._parts.add(part)
        try:
            self.pose_part(part, pose)
            self.tint_part(part, tint_rgba)
            if spec.item_id in self._faded:
                # a part rebuilt while its item fades (L2.4) is born faded
                _set(model, "fade", self._fade_opacity)
        except Exception:
            self._destroy(part)  # never a Model on screen that no caller holds a handle to
            raise
        return part

    def destroy_part(self, handle: object) -> None:
        """Destroy one Model. On a closed host: a no-op — it is gone already."""
        if self.state is HostState.CLOSED:
            if isinstance(handle, _Part):
                handle.forget()
            return
        self._destroy(self._part(handle))

    def part_count(self) -> int:
        """How many Models the engine holds for this host (its own books — which a failed
        destroy keeps in step with the engine: ``_destroy``)."""
        self._open("part_count")
        return len(self._parts)

    def clear(self) -> None:
        """Destroy EVERY Model, switch the sun off, drop the plan ground, hide the
        selection ring. On a closed host: a no-op. This is the sink's teardown
        (``Quick3DSink.clear``).

        It finishes whatever fails: every Model is tried, then the sun, the ground
        and the ring, and only then the first failure is raised (``EngineError``). A Model
        the engine did not destroy STAYS in the host's books — books and engine agree
        after a failure, and the next ``clear()`` tries it again.
        """
        if self.state is HostState.CLOSED:
            self._forget_parts()
            self.ground.forget()
            return
        total = len(self._parts)
        failures: list[Exception] = []
        for part in list(self._parts):
            try:
                self._destroy(part)
            except Exception as error:  # noqa: BLE001 - finish the teardown, then report
                failures.append(error)
        steps: tuple[Callable[[], None], ...] = (
            lambda: self.set_sun(None), lambda: self.set_ground(None),
            lambda: self.set_selection_ring(None))  # the ring is no item's: hidden, not destroyed
        for step in steps:
            try:
                step()
            except Exception as error:  # noqa: BLE001 - as above
                failures.append(error)
        if failures:
            raise EngineError(
                f"clear(): {len(failures)} of {total + len(steps)} steps failed; the engine still holds "
                f"{len(self._parts)} Model(s), and so do the host's books. First: "
                f"{failures[0]}") from failures[0]

    def pose_part(self, handle: object, pose: EnginePose) -> None:
        self._open("pose_part")
        model = self._model(handle)
        _set(model, "position", QVector3D(*pose.position))
        _set(model, "eulerRotation", QVector3D(0.0, pose.yaw_deg, 0.0))

    def tint_part(self, handle: object, tint_rgba: Rgba) -> None:
        self._open("tint_part")
        model = self._model(handle)
        _set(model, "tint", QColor(tint_rgba[0], tint_rgba[1], tint_rgba[2]))
        _set(model, "tintLinear", QVector3D(*tint_uniform(tint_rgba)))

    def set_sun(self, travel: tuple[float, float, float] | None) -> None:
        """Where the sunlight travels (engine frame) — or None: no sun, or it is down."""
        self._open("set_sun")
        self._sun_travel = travel
        self._apply_light()

    def _apply_light(self) -> None:
        """Aim the key light — the ONE place that does. A night look's moon (its stated
        direction, mapped to the engine frame here); else the sun the pipeline sent
        (light travel = -sun vector, ``core/solar``); else no key light at all. A look
        never aims the sun: by day ``LookSpec.moon_travel_scene`` is None."""
        travel = self._sun_travel
        moon = self._shown_look.moon_travel_scene
        if moon is not None:
            engine = scene_to_engine_vectors(np.array(moon, dtype=np.float64))
            travel = (float(engine[0]), float(engine[1]), float(engine[2]))
        if travel is None:
            _set(self._root, "sunUp", False)
            return
        rotation = QQuaternion.rotationTo(QVector3D(*_LIGHT_FORWARD), QVector3D(*travel))
        _set(self._root, "sunRotation", rotation)
        _set(self._root, "sunUp", True)

    def set_ground(self, ground: GroundPlacement | None) -> None:
        self._open("set_ground")
        try:
            if ground is None:
                self.ground.clear()
                _set(self._root, "groundVisible", False)
                _set(self._root, "groundCenter", QVector3D(0.0, 0.0, 0.0))
                return
            _set(self._root, "groundCenter", QVector3D(*ground.center))
            _set(self._root, "groundWidth", float(ground.width_cm))
            _set(self._root, "groundDepth", float(ground.depth_cm))
            _set(self._root, "groundVisible", True)
            self.ground.show(ground.tiles)  # the baked tiles (L1.5); none: bare ground
        except GroundTileError as error:  # an engine failure like any other
            raise EngineError(f"set_ground(): {error}") from error

    def request_frame(self) -> None:
        """A transaction closed. A live view is asked to repaint; any other open
        state shows the new scene with its next frame anyway."""
        if self._open("request_frame") is HostState.LIVE:
            self._view.update()

    # ── the selection ring (L1.8, ADR-060) ───────────────────────────────────

    #: The ONE geometry of the selection ring: created with the first selection, as
    #: a child of the scene's ring Model (they go together), and re-loaded for every
    #: later one. A class default, so that no host starts with one.
    _ring: ReloadableGeometry | None = None
    #: How often the ring's data was loaded into the engine (the gates read it).
    ring_loads = 0

    def set_selection_ring(self, ring: EngineBuffers | None) -> None:
        """Show ``ring`` (engine frame) as the selection ring, or hide it (None).

        ``Garden.qml`` declares ONE ring Model for the life of the scene. This
        loads new vertex data into the one geometry that Model has: a selection
        change creates and destroys no engine object — not a Model (Qt keeps
        graphics state for every Model it once drew until it is told to let go,
        and about 15 to 20 kB per destroyed Model for good; ADR-060), not a
        geometry. The first selection of a host creates that one geometry.

        ``clear()`` hides the ring too (the engine then holds nothing to draw).
        """
        self._open("set_selection_ring")
        if ring is None or ring.is_empty:
            _set(self._root, "selectionVisible", False)
            return
        geometry = self._ring
        if geometry is None or sip.isdeleted(geometry):
            model = self._call("selectionRingModel")
            try:
                geometry = ReloadableGeometry(model)
            except TypeError as error:
                raise EngineError(f"the scene's selection ring is no 3D object ({error})") from error
            geometry.load(ring, RING_BOUNDS_MARGIN_CM)
            self._call("setSelectionGeometry", geometry)
            _set(self._root, "selectionColorLinear", QVector3D(*tint_uniform(SELECTION_RGBA)))
            self._ring = geometry
        else:
            geometry.load(ring, RING_BOUNDS_MARGIN_CM)
        self.ring_loads += 1
        _set(self._root, "selectionVisible", True)

    # ── the analysis overlays, Cutaway and X-ray (L2, #386) ──────────────────

    #: How often an overlay's data was loaded into the engine (the gates read it).
    overlay_loads = 0

    def set_overlay(self, layer: str, mesh: EngineBuffers | None) -> None:
        """Show ``mesh`` (engine frame) as the analysis overlay ``layer`` — ``"shade"``
        (the 2D shadows on the ground: its vertex colour MULTIPLIES the frame),
        ``"drape"`` (the hours-of-sun map, blended over) or ``"lines"`` (the sun path,
        the compass, the probe's pin) — or hide it (None).

        Like the selection ring: ``Garden.qml`` declares ONE Model per layer for the
        life of the scene, and this loads new vertex data into the one geometry that
        Model has — an analysis change creates and destroys no engine object (Qt keeps
        state for every Model it once drew, and about 15 to 20 kB per destroyed Model
        for good, ADR-060). The overlays are not items: the sink's ``clear()`` leaves
        them as it leaves the sky, and the analysis controller says what they show.
        """
        self._open("set_overlay")
        if layer not in OVERLAY_LAYERS:
            raise EngineError(f"no analysis overlay {layer!r} (one of {OVERLAY_LAYERS})")
        visible = OVERLAY_LAYERS[layer]
        if mesh is None or mesh.is_empty:
            _set(self._root, visible, False)
            return
        overlays = self._overlays
        geometry = overlays.get(layer)
        if geometry is None or sip.isdeleted(geometry):
            model = self._call("overlayModel", layer)
            try:
                geometry = ReloadableGeometry(model)
            except TypeError as error:
                raise EngineError(f"the scene's {layer} overlay is no 3D object ({error})") from error
            geometry.load(mesh)
            if self._call("setOverlayGeometry", layer, geometry) is not True:
                raise EngineError(f"the scene refused the {layer} overlay's geometry")
            overlays[layer] = geometry
        else:
            geometry.load(mesh)
        self.overlay_loads += 1
        _set(self._root, visible, True)

    def set_roofs_hidden(self, hidden: bool) -> None:
        """Cutaway (L2.4): hide every roof part — one property of the scene, bound by
        each roof Model, so a roof built while it is on is born hidden too."""
        self._open("set_roofs_hidden")
        _set(self._root, "roofsHidden", bool(hidden))

    def set_faded_items(self, item_ids: frozenset[str] | set[str], opacity: float = 1.0) -> None:
        """X-ray (L2.4): draw every part of ``item_ids`` at ``opacity`` (blended, and not
        pickable: a click meets what is behind), every other part as it is. Parts a
        later ``create_part`` builds for a faded item are born faded."""
        self._open("set_faded_items")
        if not 0.0 <= opacity <= 1.0:
            raise ValueError(f"opacity must lie in [0, 1], got {opacity!r}")
        wanted = frozenset(str(item_id) for item_id in item_ids)
        changed = wanted ^ self._faded if opacity == self._fade_opacity else wanted | self._faded
        self._faded, self._fade_opacity = wanted, float(opacity)
        for part in self._parts:
            if part.model is not None and part.item_id in changed:
                _set(part.model, "fade", self._fade_opacity if part.item_id in wanted else 1.0)

    @property
    def faded_items(self) -> frozenset[str]:
        """The items whose parts are drawn faded (X-ray, L2.4)."""
        return self._faded

    # ── lifecycle ────────────────────────────────────────────────────────────

    def container(self, parent: QWidget | None = None) -> QWidget:
        """The widget that embeds the view in a QWidget layout (created once).

        It wraps a NATIVE window: sibling widgets do not paint over it. After
        this call ``show()`` / ``hide()`` act on the container, the parent may
        show, hide, resize and collapse it as it likes — the state follows Qt —
        and the host has no offscreen frame any more. Legal in every open state
        but ``SPENT``: a host whose scene is gone would die when its parent
        shows it (measured: embedding a view that is live, starting or hidden is
        fine).
        """
        state = self._open("container")
        if self._container is None:
            if state is HostState.SPENT:
                raise HostStateError(
                    "container(): this host took its one offscreen frame and its scene is "
                    "gone; embedded, it would die when its parent shows it. Build a new host")
            from PyQt6.QtWidgets import QWidget

            self._container = QWidget.createWindowContainer(self._view, parent)
        return self._container

    def show(self) -> None:
        state = self._open("show")
        if state is HostState.SPENT:
            raise HostStateError(
                "show(): this host took its one offscreen frame and its scene is gone; "
                "showing it now would kill the process. Build a new host for a window")
        if self._container is not None:
            self._container.show()
        else:
            self._view.show()

    def hide(self) -> None:
        self._open("hide")
        if self._container is not None:
            self._container.hide()
        else:
            self._view.hide()

    def wait_ready(self, timeout_s: float = WAIT_READY_DEFAULT_S) -> bool:
        """True: a frame of the window's size was just taken — a ``grab()`` issued right
        after this answers. It starts no pass of the event loop once ``timeout_s`` is up,
        and says False after ``STALL_S`` of silence, whatever the timeout. The contract,
        with its exact bounds, is ``lifecycle.py``'s docstring.

        It is a NESTED EVENT LOOP (not for ``timeout_s <= 0``) and takes user input: the
        workspace needs it nowhere on the GUI thread. Never call it from a timer slot, a
        sync tick, a paint or a resize handler; a click handler calls
        ``try: host.pick(x, y)`` / ``except HostStateError`` instead. What is queued on
        the event loop is delivered in whole passes: it returns within ``timeout_s`` PLUS
        whatever was queued when its last pass began.

        ``timeout_s`` is clamped to a day; a negative one, or one that is not a number, is 0.
        """
        self._open("wait_ready")
        started = time.perf_counter()
        timeout_s = float(timeout_s)
        timeout_s = min(timeout_s, _LONGEST_WAIT_S) if timeout_s > 0.0 else 0.0  # nan: 0
        if timeout_s > 0.0 and self.is_visible():
            # What is queued already — the resize a parent's layout is about to hand this
            # window, the expose after one — ONCE, and inside the time: a host that reads
            # live at its old size would otherwise answer for that size.
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents,
                                           max(1, int(timeout_s * 1000.0)))
        ready = self._await_frame(started + timeout_s, timeout_s)
        self._log("ready", ok=ready, state=self.state.value,
                  ms=round((time.perf_counter() - started) * 1000.0, 1))
        return ready

    def _await_frame(self, deadline: float, timeout_s: float) -> bool:
        """Look; on a live host take a frame; wait for a sign of progress; again.

        Ends with True when a frame has the window's size. Ends with False when the host
        is not on its way (hidden, new, spent, closed, no graphics device), when the time
        is up, after ``STALL_S`` of SILENCE, or when no event loop can run.
        A frame is taken only when something happened since the last one: two frames of
        another size with nothing in between is how "nothing is on its way" looks.

        Silence is time the event loop was IDLE with no sign of progress — counted pass
        by pass, never as wall time: a pass that overran its step was busy with a handler
        of something else (a plan load, a repaint), and the repaint this host waits for
        may be queued right behind it. (Counted as wall time, a GUI thread busy for 0.7 s
        inside the wait made ``wait_ready(5)`` say False after 0.75 s — and True when
        asked again.)
        """
        seen: object = None  # what the last look saw: (state, facts, signs)
        silence = longest = 0.0
        probed_at_sign: int | None = None
        passes_left = int(timeout_s * 1000.0 / _WAIT_STEP_MS) + 2
        while True:
            facts = self._facts()
            state = state_of(facts, closed=self._closed, spent=self._spent)
            look = (state, facts, self._watch.signs)
            if look != seen:
                seen, longest, silence = look, max(longest, silence), 0.0
            if state is HostState.LIVE and facts is not None:
                if probed_at_sign != self._watch.signs:
                    probed_at_sign = self._watch.signs
                    if self._frame_fits(facts):
                        self.longest_quiet_s = max(self.longest_quiet_s, longest)
                        return True
            elif state is not HostState.STARTING or self._scene_graph_error is not None:
                return False
            now = time.perf_counter()
            left = min(deadline - now, STALL_S - silence)
            if left <= 0.0 or passes_left <= 0:
                return False  # the time is up, or nothing is on its way
            passes_left -= 1
            step = max(1, min(_WAIT_STEP_MS, int(left * 1000.0)))
            if not self._run_events(step):
                return False  # the application is quitting: no event loop will run
            took = time.perf_counter() - now
            if took <= step / 1000.0 + _BUSY_PASS_S:
                silence += took  # an idle pass; a longer one was busy: that is not silence

    def _frame_fits(self, facts: WindowFacts) -> bool:
        """THE witness, taken as a probe: a frame of this live host has the window's size.
        (On a backend that draws no 3D there is no frame to ask: ``grab`` raises
        ``EngineError`` there whatever the state, and the state alone answers.)"""
        if self.graphics_api() not in RENDERING_APIS:
            return True
        self.probes += 1
        try:
            self._frame("wait_ready", "probe", facts)
        except HostStateError:
            return False
        return True

    def close(self) -> None:
        """Destroy every Model, then the view (and its container). The host is dead after.

        Safe when Qt got there first (the container's parent widget was destroyed, and
        the window with it): then only the Python side is released. Exception-safe
        and retryable: the window goes whatever a Model's teardown said (a Model that
        could not be destroyed dies with the view; its geometry stays referenced
        until then), and the host counts as closed only once hiding and deleting the
        window went through — a ``close()`` that raised can simply be called again.
        """
        if self._closed:
            return
        if sip.isdeleted(self._view):
            self._forget_parts()  # the Models died with the scene
            self.ground.forget()
            self._container = None
            self._closed = True
            return
        for part in list(self._parts):
            try:
                self._destroy(part)
            except Exception as error:  # noqa: BLE001 - the Model dies with the view
                _LOG.warning("close(): a Model could not be destroyed (%s); it goes with the view",
                             error)
        self.ground.forget()  # its Models die with the view; the textures are Python's
        self._view.hide()
        self._view.removeEventFilter(self._watch)
        container, self._container = self._container, None
        if container is not None and not sip.isdeleted(container):
            container.deleteLater()  # owns the window
        else:
            self._view.deleteLater()
        self._closed = True

    # ── frames ───────────────────────────────────────────────────────────────

    def graphics_api(self) -> str:
        """``Direct3D11``, ``OpenGL``, ``Vulkan``, ``Metal``, ``Direct3D12`` — or
        ``Software`` / ``Null`` / ``OpenVG`` / ``Unknown`` (``GRAPHICS_API_NAMES``).
        Known before the first frame: it is the API the window WILL use."""
        self._open("graphics_api")
        interface = self._view.rendererInterface()
        if interface is None:
            return "Unknown"
        return GRAPHICS_API_NAMES.get(interface.graphicsApi(), "Unknown")

    def renders_3d(self) -> bool:
        """False where Qt Quick 3D draws nothing — the software scene graph (what the
        ``offscreen`` platform selects), the null backend. A frame from such a host
        would show the scene's 2D items and no garden."""
        return self.graphics_api() in RENDERING_APIS

    def grab(self, label: str = "") -> QImage:
        """Render the current state NOW and read it back (device pixels): the scene at
        the window's current size, or ``HostStateError`` (``lifecycle.py``).

        Legal on a ``LIVE`` host, and ONCE on a ``NEW`` host that is not embedded
        (the offscreen frame; the host is ``SPENT`` after). ``EngineError`` when
        this backend cannot render 3D at all, or no image comes back.

        The image's size is checked against the window's, always: that check — not
        the state — is what sentence 1 of the contract rests on. On a live host a
        frame of another size raises ``HostStateError`` (the render target is behind
        the window); it is never handed out.
        """
        state, facts = self._look("grab")
        self._require_3d("grab")
        if state is HostState.NEW and self._container is None:
            self._spent = True  # before the grab: whatever happens, never a second one
            self._view.create()
            image = self._render("grab", label, state)
            found = self._other_size(image, facts)
            if found is not None:  # the one offscreen frame: there is no "later" for it
                raise EngineError(f"grab({label!r}): {found} — not the scene at this size")
        elif state is not HostState.LIVE:
            raise HostStateError(f"grab(): {self._why(state, facts)}")
        else:
            image = self._frame("grab", label, facts)
        self.grabs += 1
        return image

    def _render(self, call: str, label: str, state: HostState) -> QImage:
        """Render now and read back; ``EngineError`` when Qt hands back no image."""
        started = time.perf_counter()
        image = self._view.grabWindow()
        elapsed = (time.perf_counter() - started) * 1000.0
        self._log("grab", call=call, label=label, ms=round(elapsed, 1), state=state.value,
                  px=f"{image.width()}x{image.height()}")
        if image.isNull() or image.width() == 0 or image.height() == 0:
            raise EngineError(f"{call}({label!r}) returned no image")
        return image

    @staticmethod
    def _other_size(image: QImage, facts: WindowFacts) -> str | None:
        """None when the image is the frame of a window of this size (at the image's own
        pixel ratio), else what Qt rendered instead.

        Qt sizes a render target as ``QSize(logical) * ratio`` — ``qRound`` per side — so
        the right frame is at most HALF a device pixel off ``logical × ratio``; and at a
        ratio of 1 or more the frame of a window one logical pixel smaller or larger is
        further off than that. (The check allowed two pixels until review round 4, and
        "less than one" until round 5: at 125 % a pane grown from 442 to 443 px got its
        old frame back — 553 px, 0.75 px off 553.75; its own is 554.)"""
        ratio = float(image.devicePixelRatio())
        if (abs(image.width() - facts.width * ratio) <= _HALF_PIXEL
                and abs(image.height() - facts.height * ratio) <= _HALF_PIXEL):
            return None
        return (f"Qt rendered a {image.width()} x {image.height()} px image for a "
                f"{facts.width} x {facts.height} window at ratio {ratio:g}")

    def _frame(self, call: str, label: str, facts: WindowFacts) -> QImage:
        """One frame of a LIVE host, checked — THE witness (``lifecycle.py``). It has the
        window's size, and the host knows that for this size until the next resize; or
        ``HostStateError``: the render target is behind the window. ``grab()`` and
        ``wait_ready()`` take a frame again whenever they are asked; ``pick()`` and
        ``project()`` let the refusal stand for a moment (``_require_frame``)."""
        image = self._render(call, label, HostState.LIVE)
        found = self._other_size(image, facts)
        if found is None:
            self._frame_at = (facts.width, facts.height, self._watch.resizes)
            self._behind = None
            return image
        self._frame_at = None
        self._behind = _Behind(facts, self._watch.signs, time.perf_counter(), found)
        self.stale_frames += 1
        self._log("stale_frame", call=call, label=label, px=f"{image.width()}x{image.height()}",
                  window=f"{facts.width}x{facts.height}")
        raise HostStateError(_behind_text(call, found))

    def device_pixel_ratio(self) -> float:
        self._open("device_pixel_ratio")
        return float(self._view.effectiveDevicePixelRatio())

    def view_size(self) -> tuple[float, float]:
        """The view's actual LOGICAL size (a window larger than the screen is clamped)."""
        self._open("view_size")
        return float(self._root.width()), float(self._root.height())

    # ── camera and look ──────────────────────────────────────────────────────

    def set_shot(self, shot: Shot) -> None:
        if isinstance(shot, TopDownShot):
            self.set_top_down(shot.center, shot.px_per_cm)
        else:
            self.set_camera(shot.eye, shot.target, shot.fov_deg)

    def set_camera(self, eye_scene: tuple[float, float, float],
                   target_scene: tuple[float, float, float], fov_deg: float = 40.0) -> None:
        """Perspective: the eye and the point it looks at, scene frame (E, N, up)."""
        self._open("set_camera")
        shot = PerspectiveShot(eye_scene, target_scene, fov_deg)  # validates
        _set(self._root, "topDown", False)
        _set(self._root, "camPos", _engine_vector(shot.eye))
        _set(self._root, "camTarget", _engine_vector(shot.target))
        _set(self._root, "camFov", float(shot.fov_deg))
        _set(self._root, "camVersion", int(_get(self._root, "camVersion")) + 1)

    def set_top_down(self, center_scene: tuple[float, float], px_per_cm: float) -> None:
        """Orthographic, straight down, north up: the truth view (``shots.TopDownShot``)."""
        self._open("set_top_down")
        shot = TopDownShot(center_scene, px_per_cm)  # validates
        _set(self._root, "camTarget", _engine_vector((*shot.center, 0.0)))
        _set(self._root, "topDownScale", float(shot.px_per_cm))
        _set(self._root, "topDown", True)

    def set_look(self, look: LookSpec) -> None:
        """Apply a look — plain data from ``core.scene3d.look.look_for``; the mapping
        onto the scene is ``look.scene_properties``. It moves no camera, touches no
        Model and builds no sky (``set_sky``); at night it aims the key light at the
        look's moon, by day it leaves the sun where the pipeline put it."""
        self._open("set_look")
        for name, value in scene_properties(look).items():
            if name in COLOR_PROPERTIES:
                value = QColor(str(value))
            elif name in LINEAR_COLOR_PROPERTIES:
                red, green, blue = cast("tuple[float, float, float]", value)  # sRGB-space floats
                value = QColor.fromRgbF(float(red), float(green), float(blue))
            _set(self._root, name, value)
        previous, self._shown_look = self._shown_look, look
        if look.moon_travel_scene != previous.moon_travel_scene:
            self._apply_light()   # dusk or dawn: the key light changes hands

    @property
    def look(self) -> LookSpec:
        """The look on screen."""
        return self._shown_look

    def set_sky(self, sky: SkySpec | None) -> None:
        """Build the sky that backs and lights the perspective view — or None: none
        (a plain background and the look's flat fill instead).

        EVERY call with a sky builds one: a whole procedural sky on the GUI thread,
        and a light probe Qt filters in the next frame it renders. WHEN to build is
        the caller's policy (``core.scene3d.look.sky_is_stale``: once per noticeable
        sun move) — and so is never building one on a software adapter, where the
        probe's filtering was measured in tens of seconds (``ogp-3d-renderer`` §8).
        The old sky's Texture goes with its data object, after the scene shows the
        new one (``Garden.qml``: ``buildSky``).
        """
        self._open("set_sky")
        if sky is None:
            # always: after a FAILED first build there is no sky recorded here, and
            # whatever half a sky the scene kept must go all the same (dropSky is a
            # no-op on a scene without one)
            self._call("dropSky")
            self._sky = None
            return
        started = time.perf_counter()
        self._call("buildSky", sky_properties(sky))
        self.last_sky_build_ms = (time.perf_counter() - started) * 1000.0
        self._sky = sky
        self.sky_builds += 1
        self._log("sky_built", n=self.sky_builds, ms=round(self.last_sky_build_ms, 1),
                  elevation=round(sky.sun_elevation_deg, 2), azimuth=round(sky.sun_azimuth_deg, 2),
                  night=sky.night)

    @property
    def sky(self) -> SkySpec | None:
        """The sky on screen (None: no sky texture)."""
        return self._sky

    def set_wind_running(self, running: bool) -> None:
        """Start or stop the wind's clock. Stopped, nothing ticks: the clock holds its
        value (a hidden view goes on where it was) — which is NOT rest."""
        self._open("set_wind_running")
        _set(self._root, "windRunning", bool(running))

    def rest_wind(self) -> None:
        """Stop the wind and put its clock back to 0: every vertex exactly where its
        mesh puts it. What reduced motion, a truth probe and a still picture need."""
        self._open("rest_wind")
        _set(self._root, "windRunning", False)
        _set(self._root, "windTime", 0.0)

    # ── picking and readback ─────────────────────────────────────────────────

    def pick(self, x: float, y: float) -> PickHit | None:
        """The item under view position ``(x, y)`` (LOGICAL pixels), or None for
        empty space — for the frame rendered last.

        ``LIVE`` hosts only; anything else raises ``HostStateError`` (a backend
        that renders no 3D, or a scene whose pick function failed,
        ``EngineError``): "no hit" must never mean "could not look".

        The hit carries what lies ``behind`` it along the same ray (``PickHit``).
        """
        self._require_frame("pick")
        result = self._call("pickAt", float(x), float(y))
        if not result.get("hit"):
            return None
        first = _pick_hit(result)
        behind = tuple(_pick_hit(row) for row in result.get("behind") or ())
        return PickHit(first.item_id, first.part_index, first.point, behind)

    def project(self, east_cm: float, north_cm: float, up_cm: float) -> tuple[float, float]:
        """Scene point → view position in LOGICAL pixels (the space ``pick`` takes),
        by the ENGINE's projection of the frame rendered last. ``LIVE`` hosts only."""
        self._require_frame("project")
        engine = _engine_vector((east_cm, north_cm, up_cm))
        result = self._call("projectToView", engine.x(), engine.y(), engine.z())
        return float(result["x"]), float(result["y"])

    def engine_parts(self) -> list[EnginePart]:
        """Every Model of the QML scene that was not destroyed — what the engine holds,
        read from it (a Model a later story hides is still listed, ``visible=False``)."""
        self._open("engine_parts")
        rows = self._call("listParts")
        return [EnginePart(
            item_id=str(row["id"]), part_index=int(row["part"]), kind=str(row["kind"]),
            position=(float(row["x"]), float(row["y"]), float(row["z"])),
            yaw_deg=float(row["yaw"]),
            tint_rgb=(round(row["r"] * 255.0), round(row["g"] * 255.0), round(row["b"] * 255.0)),
            casts_shadow=bool(row["casts"]), has_geometry=bool(row["geometry"]),
            visible=bool(row["visible"]), fade=float(row["fade"]), drawn=float(row["drawn"]),
        ) for row in rows]

    def scene_property(self, name: str) -> Any:
        """A root property of ``Garden.qml`` (tests and diagnostics); ``EngineError``
        for a name the scene does not declare."""
        self._open("scene_property")
        return _get(self._root, name)

    def focus(self) -> None:
        """Give the view the keyboard focus (L1.8: walk mode is walked with the keys):
        ``requestActivate()`` on the view. Measured on the real main window (Windows,
        fix round 1): afterwards ``QGuiApplication.focusWindow()`` is the view, the
        widget with the focus is its container, and a key reaches the view's event
        filters (``ShortcutOverride`` first); the container's ``setFocus()`` does the
        same there."""
        self._open("focus")
        self._view.requestActivate()

    def has_focus(self) -> bool:
        """True while the view is the window with the keyboard focus."""
        from PyQt6.QtGui import QGuiApplication

        self._open("has_focus")
        return QGuiApplication.focusWindow() is self._view

    def install_event_filter(self, watcher: QObject) -> None:
        """Let ``watcher`` see the view's events before the view does (L1.3: the orbit
        camera's mouse, wheel and key input). The view is a native window: its input
        never reaches the widget that embeds it. An event filter runs on the GUI
        thread — unlike a message handler it is safe beside the render thread."""
        self._open("install_event_filter")
        self._view.installEventFilter(watcher)

    def release_cached_resources(self) -> None:
        """Tell Qt to let go of the graphics state it caches for this window
        (``QQuickWindow.releaseResources()``). Legal in every open state; the scene,
        the Models and the host's state are untouched, and the next frame is the
        same frame (L1.3, measured on Direct3D 11, GPU and WARP: the readback after
        a release identical to the one before it, every time it was looked at).

        WHY (L1.3, ADR-060): Qt Quick 3D keeps per-draw-call state for every Model
        it ever DREW — and keeps it after the Model was destroyed. About 0.2 MB per
        Model with the sun's shadow passes on, independent of the mesh's size;
        nothing but this call gives it back (20 rebuilds of the small bench plan in
        a presenting view, no readback: 19 MB per rebuild without it, 2 with one
        call per rebuild). The call takes 2 to 10 ms on the GUI thread and the next
        frame as much again. WHEN to call it is the caller's policy
        (``ui/view3d/workspace.py``).

        What it does NOT do: it frees no mesh buffer of a destroyed Model — Qt does
        that itself at the END OF A PRESENTED FRAME, and a readback (``grab()``) is
        not one: a frame rendered for a readback is never presented, and what it
        holds waits for the next frame that is. Which is why nothing takes a frame
        from a live, shown host on its own (the workspace's rule, ADR-060).
        """
        self._open("release_cached_resources")
        self._view.releaseResources()
        self.cache_releases += 1

    # ── trouble in a live view (GUI thread; module docstring) ────────────────

    def health(self) -> HostHealth:
        """What Qt reported so far: frames presented, QML warnings, a graphics device
        that could not be created. Answers in every state, also on a closed host."""
        return HostHealth(self.frames_presented, tuple(self._qml_warnings),
                          self._qml_warning_count, self._scene_graph_error)

    # ── internals ────────────────────────────────────────────────────────────

    def _on_gui_thread(self) -> None:
        if threading.get_ident() != self._gui_thread:
            self.slot_calls_off_the_gui_thread += 1

    def _on_frame_swapped(self) -> None:
        self._on_gui_thread()
        self.frames_presented += 1
        self.ground.frame_presented()  # the scene shows the new tiles: the replaced ones go

    def _on_qml_warnings(self, warnings: Any) -> None:
        self._on_gui_thread()
        for warning in warnings:
            text = str(warning.toString())
            self._qml_warning_count += 1
            if len(self._qml_warnings) < _KEEP_WARNINGS:
                self._qml_warnings.append(text)
                _LOG.warning("3D view: QML warning: %s", text)
            elif self._qml_warning_count == _KEEP_WARNINGS + 1:
                _LOG.warning("3D view: more than %d QML warnings; further ones are only counted "
                             "(health().qml_warning_count)", _KEEP_WARNINGS)
        self._log("qml_warnings", count=self._qml_warning_count)

    def _on_scene_graph_error(self, _error: Any, message: str) -> None:
        self._on_gui_thread()
        self._scene_graph_error = str(message) or "the graphics device could not be created"
        _LOG.error("3D view: the graphics device could not be created: %s",
                   self._scene_graph_error)
        self._log("scene_graph_error", message=self._scene_graph_error)

    @staticmethod
    def _run_events(milliseconds: int) -> bool:
        """One pass of a local event loop that BLOCKS for events — never a busy spin.

        False when the loop could not run: once the application is quitting,
        ``QEventLoop.exec()`` returns -1 at once (measured: 2 microseconds a pass),
        and a caller that went on asking would spin.
        """
        loop = QEventLoop()
        QTimer.singleShot(milliseconds, loop.quit)
        return loop.exec() == 0

    def _call(self, function: str, *arguments: object) -> Any:
        """Call a function of ``Garden.qml`` that returns an object. A function that is
        missing raises in PyQt; one that THROWS returns nothing, silently (the QML
        engine only warns) — both are an ``EngineError`` here, never an empty answer."""
        try:
            result = _js_object(QMetaObject.invokeMethod(
                self._root, function, _DIRECT, Q_RETURN_ARG("QVariant"),
                *(Q_ARG("QVariant", argument) for argument in arguments)))
        except RuntimeError as error:
            raise EngineError(f"the scene has no function {function}() ({error})") from error
        if result is None:
            raise EngineError(f"the scene's {function}() returned nothing — it failed "
                              f"(see health().qml_warnings)")
        return result

    def _require_3d(self, call: str) -> None:
        api = self.graphics_api()
        if api not in RENDERING_APIS:
            raise EngineError(
                f"{call}(): Qt Quick runs on the {api} backend here, where Qt Quick 3D draws "
                "nothing (QT_QPA_PLATFORM=offscreen selects the software scene graph)")

    def _why(self, state: HostState, facts: WindowFacts) -> str:
        return why_no_frame(state, facts, embedded=self._container is not None,
                            graphics_error=self._scene_graph_error)

    def _require_frame(self, call: str) -> None:
        """``pick`` / ``project`` answer for a frame of the window's size. The host knows
        of one when it took it since the last resize; if not, it takes one now — measured:
        without a frame after a resize the engine picks with the OLD viewport and misses
        (module docstring). ``HostStateError`` when that frame has another size.

        ONE frame per refusal, not per call: while the host sees what it saw when a frame
        was refused — the same facts, no sign of progress counted — and ``REPROBE_S`` has
        not passed, the call is refused on the evidence of that frame. (Review round 5:
        200 ``project()`` calls of one tick took 200 frames, all refused.) The time bound
        is for a host that recovered without a sign the watch counts: it is refused for
        ``REPROBE_S`` at most."""
        state, facts = self._look(call)
        self._require_3d(call)
        if state is not HostState.LIVE:
            raise HostStateError(f"{call}(): {self._why(state, facts)}")
        if self._frame_at == (facts.width, facts.height, self._watch.resizes):
            return
        behind = self._behind
        if (behind is not None and behind.facts == facts and behind.signs == self._watch.signs
                and time.perf_counter() - behind.at < REPROBE_S):
            raise HostStateError(_behind_text(call, behind.found))
        self.probes += 1
        self._frame(call, "its own frame", facts)

    def _destroy(self, part: _Part) -> None:
        """Destroy one Model in the engine. The part leaves the host's books ONLY when the
        engine confirms it — the Model is retired (or already deleted). After a failure
        books and engine still agree: both hold it, and the caller may try again."""
        model = part.model
        if model is None or sip.isdeleted(model):
            self._parts.discard(part)
            part.forget()
            return
        # The Model lets go of the geometry before either dies: the geometry is
        # owned by Python, and a Model must never outlive the buffers it draws.
        try:
            QMetaObject.invokeMethod(self._root, "destroyPart", _DIRECT, Q_ARG("QVariant", model))
        except RuntimeError as error:
            raise EngineError(f"the scene has no function destroyPart() ({error})") from error
        if not sip.isdeleted(model) and model.property("retired") is not True:
            raise EngineError("the scene's destroyPart() did not retire the Model — it failed "
                              "(see health().qml_warnings); the engine still holds it")
        self._parts.discard(part)
        part.forget()

    def _forget_parts(self) -> None:
        for part in self._parts:
            part.forget()
        self._parts.clear()

    def _part(self, handle: object) -> _Part:
        if not isinstance(handle, _Part) or handle.model is None or handle not in self._parts:
            raise EngineError(f"not a live part of this host: {handle!r}")
        return handle

    def _model(self, handle: object) -> QObject:
        model = self._part(handle).model
        if model is None:  # _part() checked it; this narrows the type
            raise EngineError(f"not a live part of this host: {handle!r}")
        return model


def shown_quick_windows() -> int:
    """How many Qt Quick windows are visible in this process right now. Each renders on
    a thread of its own (the threaded render loop), beside which no process-wide Qt
    message recorder may be installed (``qt_messages.py``)."""
    return sum(1 for window in QGuiApplication.allWindows()
               if isinstance(window, QQuickWindow) and window.isVisible())


def _pick_hit(row: Any) -> PickHit:
    """One row of the scene's ``pickAt`` answer (engine frame) as a hit in the SCENE frame."""
    point = engine_to_scene_points(np.array([row["x"], row["y"], row["z"]], dtype=np.float64))
    return PickHit(item_id=str(row.get("id", "")), part_index=int(row.get("part", -1)),
                   point=(float(point[0]), float(point[1]), float(point[2])))


def _engine_vector(point_scene: tuple[float, float, float]) -> QVector3D:
    engine = scene_to_engine_points(np.array(point_scene, dtype=np.float64))
    return QVector3D(float(engine[0]), float(engine[1]), float(engine[2]))
