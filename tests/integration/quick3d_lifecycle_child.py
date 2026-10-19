"""One call order of the host's lifecycle, in a process of its own — not a test module.

    python tests/integration/quick3d_lifecycle_child.py <order> [<qml dir>]
    python tests/integration/quick3d_lifecycle_child.py random_walk <seed> <steps> <fit|1024x768>

Why a process per order: the failures this matrix exists for are not exceptions.
A Qt Quick window grabbed at the wrong moment returns a perfectly good image, and
the PROCESS dies in the next pass of the event loop (abort, access violation,
heap corruption, segfault); a Python Qt message handler beside a shown window
deadlocks it for good (ADR-048 addendum L1.2). A test in the pytest process would
take the whole run down with it; here a death is an exit code and a deadlock is
a timeout.

Each order drives a real ``Quick3DHost`` and records what every step answered —
for a frame its size and WHERE the red probe box is, for a refusal the exception
— together with what the host said its state was. Then the event loop runs for
half a second (that is when a doomed process dies), the observations go to stdout
as one ``RESULT {json}`` line, and ``END`` is the last line of a process that
survived. ``test_quick3d_lifecycle.py`` judges — against a table of what a
truthful host must answer, NOT against the state the host reported.

Orders named ``unguarded_…`` / ``deadlock_…`` are CONTROLS: they reach past the
host to the raw ``QQuickView`` and do what the host forbids. They must fail —
die, hang, or answer with a wrong frame — which is what shows the matrix can see
the failure it guards against.

No Python Qt message handler is ever installed in here, except in the two orders
that exist to show what one does.
"""

from __future__ import annotations

import faulthandler
import json
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if __name__ == "__main__":  # run as a script: make this checkout's code importable
    for entry in (str(REPO / "src"), str(REPO)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

RING = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
SIZE = (320, 240)
#: The probe: a 100 x 100 cm red box at the origin, seen from straight above at
#: PX_PER_CM, the view centred on it — a red square of BOX_SIDE_PX logical pixels in
#: the middle of the frame, whatever the frame's size.
PX_PER_CM = 0.5
BOX_SIDE_PX = 50.0

#: Every public call of the host, for the "closed host" rows: name → how to call it.
HOST_CALLS: dict[str, Callable[[Any, Any], Any]] = {}


def _register_calls() -> None:
    from open_garden_planner.core.scene3d import EnginePose, engine_buffers, prism_mesh
    from open_garden_planner.ui.view3d.quick3d.adapter import GroundPlacement, PartSpec
    from open_garden_planner.ui.view3d.quick3d.look import NEUTRAL_DAY
    from open_garden_planner.ui.view3d.quick3d.shots import TopDownShot

    pose = EnginePose((0.0, 0.0, 0.0), 0.0)
    spec = PartSpec("x", 0, "vc", engine_buffers(prism_mesh([RING], 10.0)), True)
    HOST_CALLS.update({
        "create_part": lambda host, _part: host.create_part(spec, pose, (255, 255, 255, 255)),
        "pose_part": lambda host, part: host.pose_part(part, pose),
        "tint_part": lambda host, part: host.tint_part(part, (1, 2, 3, 255)),
        "part_count": lambda host, _part: host.part_count(),
        "set_sun": lambda host, _part: host.set_sun((0.0, -1.0, 0.0)),
        "set_ground": lambda host, _part: host.set_ground(GroundPlacement((0.0, 0.0, 0.0), 10.0, 10.0)),
        "request_frame": lambda host, _part: host.request_frame(),
        "container": lambda host, _part: host.container(),
        "show": lambda host, _part: host.show(),
        "hide": lambda host, _part: host.hide(),
        "wait_ready": lambda host, _part: host.wait_ready(0.2),
        "grab": lambda host, _part: host.grab("closed"),
        "graphics_api": lambda host, _part: host.graphics_api(),
        "renders_3d": lambda host, _part: host.renders_3d(),
        "device_pixel_ratio": lambda host, _part: host.device_pixel_ratio(),
        "view_size": lambda host, _part: host.view_size(),
        "set_shot": lambda host, _part: host.set_shot(TopDownShot((0.0, 0.0), PX_PER_CM)),
        "set_camera": lambda host, _part: host.set_camera((0.0, -5.0, 5.0), (0.0, 0.0, 0.0)),
        "set_top_down": lambda host, _part: host.set_top_down((0.0, 0.0), PX_PER_CM),
        "set_look": lambda host, _part: host.set_look(NEUTRAL_DAY),
        "set_sky": lambda host, _part: host.set_sky(NEUTRAL_DAY.sky),
        "set_wind_running": lambda host, _part: host.set_wind_running(True),
        "rest_wind": lambda host, _part: host.rest_wind(),
        "pick": lambda host, _part: host.pick(1.0, 1.0),
        "project": lambda host, _part: host.project(0.0, 0.0, 0.0),
        "engine_parts": lambda host, _part: host.engine_parts(),
        "scene_property": lambda host, _part: host.scene_property("sunUp"),
        "install_event_filter": lambda host, _part: host.install_event_filter(_input_watcher()),
        "release_cached_resources": lambda host, _part: host.release_cached_resources(),
        # the three releases: legal on a closed host, and they do nothing there
        "destroy_part": lambda host, part: host.destroy_part(part),
        "clear": lambda host, _part: host.clear(),
        "close": lambda host, _part: host.close(),
    })


def _input_watcher() -> Any:
    """Something to hand ``install_event_filter`` (L1.3): a QObject that filters nothing."""
    from PyQt6.QtCore import QObject

    return QObject()


def _pump(app: Any, ms: int = 300) -> None:
    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.005)


def _frame(image: Any) -> dict[str, Any]:
    """What a frame shows, for the judge: its size, its pixel ratio, how many pixels
    are the probe's red and the box they span (device pixels; x1 / y1 exclusive)."""
    import numpy as np

    from open_garden_planner.ui.view3d.quick3d.offscreen import image_rgba

    pixels = image_rgba(image).astype(int)
    red = (pixels[..., 0] > 150) & (pixels[..., 1] < 70) & (pixels[..., 2] < 70)
    rows, cols = np.nonzero(red)
    box = [int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1] if rows.size else None
    return {"w": int(image.width()), "h": int(image.height()), "dpr": float(image.devicePixelRatio()),
            "red": int(red.sum()), "box": box}


def _attempt(call: Callable[[], Any]) -> Any:
    """What a step answered: its value (JSON-able), or ``"<ErrorType>: message"``."""
    try:
        value = call()
    except Exception as error:  # noqa: BLE001 - the matrix records every outcome
        return f"{type(error).__name__}: {error}"
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if hasattr(value, "item_id"):  # a PickHit
        return {"hit": value.item_id, "point": [round(v, 2) for v in value.point]}
    if hasattr(value, "devicePixelRatio"):  # a QImage
        return _frame(value)
    if isinstance(value, tuple) and all(isinstance(v, int | float) for v in value):
        return [round(float(v), 2) for v in value]
    return repr(value)[:80]


def _record() -> Any:
    from open_garden_planner.core.scene3d import Material, Params, Record, Transform

    return Record(item_id="w", kind="SHED", shape="rectangle", footprints=(RING,),
                  transform=Transform(), material=Material("SHED", fill_rgba=(230, 20, 20, 255)),
                  height_cm=20.0, params=Params({"seed": "w"}))


def _host(size: tuple[int, int] = SIZE, qml_dir: Path | None = None) -> tuple[Any, Any, Any]:
    """A host with one red box under a sun, seen from above; its sink and sync."""
    from open_garden_planner.core.scene3d import SceneSync, SunState
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost
    from open_garden_planner.ui.view3d.quick3d.shots import TopDownShot

    host = Quick3DHost(size, qml_dir=qml_dir)
    sink = Quick3DSink(host)
    sync = SceneSync(sink)
    sync.apply({"w": _record()}, sun=SunState(45.0, 225.0))
    host.set_shot(TopDownShot((0.0, 0.0), PX_PER_CM))
    return host, sink, sync


def _grab(host: Any) -> Any:
    return _attempt(lambda: host.grab("matrix"))


def _centre_pick(host: Any) -> Any:
    def pick() -> Any:
        width, height = host.view_size()
        return host.pick(width / 2.0, height / 2.0)

    return _attempt(pick)


def _window_size(host: Any) -> list[int] | None:
    """The Qt Quick window's logical size, asked of QT — never of the host (the judge
    compares a frame with this; ``host.view_size()`` is the scene's size, which may lag)."""
    from PyQt6 import sip

    view = host._view  # noqa: SLF001 - the matrix asks Qt directly
    return None if sip.isdeleted(view) else [int(view.width()), int(view.height())]


def _on_screen(host: Any) -> str:
    """How much of the Qt Quick window lies on a screen: ``all``, ``part`` or ``none`` —
    geometry asked of QT, never of the host (which has no such notion: it takes a frame
    and looks at it). The judge uses it to know where a host MUST come up, and where a
    prompt refusal is the truthful answer."""
    from PyQt6 import sip
    from PyQt6.QtCore import QPoint, QRect
    from PyQt6.QtGui import QGuiApplication

    view = host._view  # noqa: SLF001 - the matrix asks Qt directly
    if sip.isdeleted(view):
        return "none"
    rect = QRect(view.mapToGlobal(QPoint(0, 0)), view.size())
    area = max(rect.width(), 0) * max(rect.height(), 0)
    seen = 0
    for screen in QGuiApplication.screens():
        part = rect.intersected(screen.geometry())
        seen += max(part.width(), 0) * max(part.height(), 0)
    return "none" if seen <= 0 or area <= 0 else ("all" if seen >= area else "part")


def _look(host: Any) -> dict[str, Any]:
    """Everything a caller can ask a host at one moment: state, frame, pick, projection —
    and, asked of Qt BEFORE the grab, the size the window has at that moment and how
    much of it is on a screen."""
    return {"state": host.state.value, "window": _window_size(host), "on_screen": _on_screen(host),
            "grab": _grab(host), "pick": _centre_pick(host),
            "project": _attempt(lambda: host.project(0.0, 0.0, 20.0)),
            "view": _attempt(host.view_size)}


def _timed_wait(host: Any, timeout_s: float) -> tuple[Any, float]:
    """``wait_ready(timeout_s)`` and how long it took, seconds."""
    started = time.perf_counter()
    answer = _attempt(lambda: host.wait_ready(timeout_s))
    return answer, round(time.perf_counter() - started, 3)


# ── the orders ───────────────────────────────────────────────────────────────


def show_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """The first killer: show(), then grab() before the first expose."""
    host, _sink, _sync = _host()
    host.show()
    out = {"at_once": _look(host)}
    out["ready"] = host.wait_ready(10.0)
    out["after_wait"] = _look(host)
    _pump(app, 500)
    out["later"] = _look(host)
    host.close()
    return out


def grab_show(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """The second killer: the one offscreen frame, then show() — what the first error
    message recommended."""
    host, _sink, _sync = _host()
    out = {"state_new": host.state.value, "offscreen": _grab(host), "state_after": host.state.value,
           "show": _attempt(host.show), "container": _attempt(host.container),
           "second": _look(host), "wait_ready": _attempt(lambda: host.wait_ready(0.3)),
           "hide": _attempt(host.hide)}
    _pump(app, 500)
    out["state_end"] = host.state.value
    host.close()
    return out


def show_wait_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    host, _sink, _sync = _host()
    host.show()
    out = {"ready": host.wait_ready(10.0), "live": _look(host), "renders_3d": host.renders_3d(),
           "api": host.graphics_api()}
    _pump(app, 300)
    out["later"] = _look(host)
    host.close()
    return out


def hide_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Shown, live, hidden: asked for a frame at once and after the event loop ran."""
    host, _sink, _sync = _host()
    host.show()
    out = {"ready": host.wait_ready(10.0), "live": _look(host)}
    host.hide()
    out["hidden_at_once"] = _look(host)
    _pump(app, 100)
    out.update(hidden=_look(host), wait_hidden=_attempt(lambda: host.wait_ready(0.3)))
    host.close()
    return out


def show_hide_show_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    host, _sink, _sync = _host()
    host.show()
    out = {"ready": host.wait_ready(10.0), "first": _look(host)}
    host.hide()
    _pump(app, 100)
    host.show()
    out["reshown_at_once"] = _look(host)
    out["ready_again"] = host.wait_ready(10.0)
    out["reshown"] = _look(host)
    host.close()
    return out


def show_hide_before_expose_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Shown and hidden again with no event in between. The window never got a scene
    graph — and it HAS a platform window: on xcb the offscreen frame taken now is
    followed by a segfault. A truthful host refuses, and comes up when shown again."""
    host, _sink, _sync = _host()
    host.show()
    host.hide()
    out = {"hidden_at_once": _look(host), "wait": _attempt(lambda: host.wait_ready(0.3))}
    _pump(app, 300)
    out["hidden"] = _look(host)
    out["show"] = _attempt(host.show)
    out["ready"] = host.wait_ready(10.0)
    out["shown"] = _look(host)
    _pump(app, 300)
    host.close()
    return out


def grab_twice_hidden(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    host, _sink, _sync = _host()
    out = {"first": _grab(host), "second": _look(host), "third": _look(host)}
    _pump(app, 300)
    host.close()
    return out


def user_closes_window(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """A standalone window closed with its X button: Qt destroys the platform window and
    keeps the scene graph. A raw grab of it is an access violation."""
    host, _sink, _sync = _host()
    host.show()
    out = {"ready": host.wait_ready(10.0), "live": _look(host)}
    host._view.close()  # noqa: SLF001 - the user's X button; the host has no such call
    out["closed_by_user_at_once"] = _look(host)
    _pump(app, 300)
    out["closed_by_user"] = _look(host)
    out["show"] = _attempt(host.show)
    out["ready_again"] = host.wait_ready(10.0)
    out["shown_again"] = _look(host)
    _pump(app, 300)
    host.close()
    return out


def _every_call(host: Any, part: Any) -> dict[str, Any]:
    return {name: _attempt(lambda call=call: call(host, part)) for name, call in HOST_CALLS.items()}


def _extra_part(host: Any) -> Any:
    from open_garden_planner.core.scene3d import EnginePose, engine_buffers, prism_mesh
    from open_garden_planner.ui.view3d.quick3d.adapter import PartSpec

    return host.create_part(PartSpec("p", 0, "vc", engine_buffers(prism_mesh([RING], 10.0)), True),
                            EnginePose((0.0, 0.0, 0.0), 0.0), (255, 255, 255, 255))


def close_anything(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    host, _sink, _sync = _host()
    host.show()
    ready = host.wait_ready(10.0)
    part = _extra_part(host)
    host.close()
    out = {"ready": ready, "state": host.state.value, "is_closed": host.is_closed,
           "is_visible": host.is_visible(), "health_ok": host.health().ok,
           "calls": _every_call(host, part)}
    _pump(app, 300)
    out["calls_after_events"] = _every_call(host, part)
    return out


def parent_destroyed_anything(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    from PyQt6 import sip
    from PyQt6.QtWidgets import QWidget

    host, _sink, _sync = _host()
    parent = QWidget()
    parent.resize(400, 300)
    host.container(parent)
    parent.show()
    ready = host.wait_ready(10.0)
    part = _extra_part(host)
    sip.delete(parent)  # what closing the main window does to the workspace
    out = {"ready": ready, "state": host.state.value, "is_closed": host.is_closed,
           "is_visible": host.is_visible(), "calls": _every_call(host, part)}
    _pump(app, 300)
    return out


#: Where the matrix puts a main window: this far inside the screen's available area.
HOME = (20, 40)


def _available() -> Any:
    from PyQt6.QtGui import QGuiApplication

    return QGuiApplication.primaryScreen().availableGeometry()


def _splitter_window() -> tuple[Any, Any]:
    """A main window with a splitter — put ON the screen on purpose (round 4: where the
    window system would have put it is not something a test may depend on; on a 1024 px
    wide runner a pane ended up beyond the screen's edge, where Windows may ask for no
    drawing)."""
    from PyQt6.QtWidgets import QMainWindow, QSplitter, QWidget

    window = QMainWindow()
    splitter = QSplitter()
    splitter.addWidget(QWidget())
    window.setCentralWidget(splitter)
    window.resize(900, 500)
    area = _available()
    window.move(area.left() + HOME[0], area.top() + HOME[1])
    return window, splitter


def _in_splitter() -> tuple[Any, Any, Any]:
    """The Split workspace's shape: a shown main window, the host in the right pane."""
    window, splitter = _splitter_window()
    host, _sink, _sync = _host((450, 500))
    splitter.addWidget(host.container(splitter))
    splitter.setSizes([450, 450])
    window.show()
    return window, splitter, host


def embedded_splitter(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """L1.3's first open: the app is up, the host is created, embedded in a splitter
    beside a widget and shown — then asked for a frame at once. Then the PARENT hides
    and shows the container and the window; host.hide() / show() are never called."""
    window, splitter = _splitter_window()
    window.show()
    _pump(app, 300)
    host, _sink, _sync = _host((450, 500))
    splitter.addWidget(host.container(splitter))
    splitter.setSizes([450, 450])
    host.show()
    out = {"at_once": _look(host)}
    out["ready"] = host.wait_ready(10.0)
    out["live"] = _look(host)
    host.container().hide()
    out["parent_hid_at_once"] = _look(host)
    _pump(app, 100)
    out["parent_hid"] = _look(host)
    host.container().show()
    out["parent_showed_at_once"] = _look(host)
    out["ready_again"] = host.wait_ready(10.0)
    out["parent_showed"] = _look(host)
    window.hide()
    out["window_hidden_at_once"] = _look(host)
    _pump(app, 100)
    out["window_hidden"] = _look(host)
    window.show()
    out["window_shown_at_once"] = _look(host)
    out["ready_window"] = host.wait_ready(10.0)
    out["window_shown"] = _look(host)
    _pump(app, 500)
    host.close()
    window.close()
    return out


def collapsed_pane(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """P1-B. The pane that holds the 3D view is dragged shut (QSplitter panes collapse
    by default), reopened, squeezed to one pixel and opened again. For Qt a collapsed
    pane is visible, exposed and 0 px wide; a raw grab is a blank image of the old
    size and a raw pick hits something. After each change the scene lags the window
    by one pass of the event loop."""
    window, splitter, host = _in_splitter()
    out: dict[str, Any] = {"ready": host.wait_ready(10.0), "open": _look(host)}
    splitter.setSizes([900, 0])
    out["collapsed_at_once"] = _look(host)
    out["wait_collapsed"] = _attempt(lambda: host.wait_ready(0.5))
    _pump(app, 300)
    out["collapsed"] = _look(host)
    splitter.setSizes([450, 450])
    out["reopened_at_once"] = _look(host)
    out["ready_reopened"] = host.wait_ready(10.0)
    out["reopened"] = _look(host)
    splitter.setSizes([899, 1])
    out["one_pixel_at_once"] = _look(host)
    out["ready_one_pixel"] = host.wait_ready(10.0)
    out["one_pixel"] = _look(host)
    splitter.setSizes([700, 200])
    out["narrow_at_once"] = _look(host)
    out["ready_narrow"] = host.wait_ready(10.0)
    out["narrow"] = _look(host)
    _pump(app, 300)
    out["narrow_later"] = _look(host)
    host.close()
    window.close()
    return out


def tiny_pane(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Review round 4. A pane 2 px wide and 60 px high — the smallest that shows 3D — ON
    the screen: hidden and shown again by the host, then with its window. (On a 1024 px
    runner this very pane lay beyond the screen's edge and three ``wait_ready()`` calls
    in a row took their whole 5 s.)"""
    window, splitter, host = _in_splitter()
    out: dict[str, Any] = {"ready": host.wait_ready(10.0), "open": _look(host)}
    window.resize(901, 60)
    splitter.setSizes([sum(splitter.sizes()) - 2, 2])
    out["tiny_at_once"] = _look(host)
    out["ready_tiny"], out["wait_tiny_s"] = _timed_wait(host, 5.0)
    out["tiny"] = _look(host)
    host.hide()
    out["host_hidden"] = _look(host)
    host.show()
    out["host_reshown_at_once"] = _look(host)
    out["ready_host"], out["wait_host_s"] = _timed_wait(host, 5.0)
    out["host_reshown"] = _look(host)
    window.hide()
    out["window_hidden"] = _look(host)
    window.show()
    out["window_reshown_at_once"] = _look(host)
    out["ready_window"], out["wait_window_s"] = _timed_wait(host, 5.0)
    out["window_reshown"] = _look(host)
    _pump(app, 300)
    out["later"] = _look(host)
    out["health"] = _health(host)
    host.close()
    window.close()
    return out


def pane_without_paint(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Review round 4 — the stuck class, made ON PURPOSE, on any machine and any day.

    Qt resizes the render target when it next DRAWS the window, and it draws when the
    platform asks: an expose, an update request. A view gets neither while no part of it
    is on a screen AND no frame is due (a runner without a display, a display asleep) —
    that is where the walk stuck on CI. Whether a given machine is in that condition
    changes within a day (measured: the same pane beyond the same screen's edge kept its
    old render target while the display slept, and got the new one through an update
    request while it was awake). So this order does not wait for the platform to be in
    it: an event filter eats the view's expose, update-request and paint events — the
    view is on the screen, shown, exposed, and nothing draws it.

    Then the pane is resized. A truthful host refuses — on the evidence of the frame —
    and ``wait_ready()`` says False promptly, whatever its timeout; when painting resumes
    the host answers again. Nothing is judged in here."""
    from PyQt6.QtCore import QEvent, QObject

    class NoPaint(QObject):
        eaten = 0

        def eventFilter(self, _watched: Any, event: Any) -> bool:  # noqa: N802 - Qt's name
            if event.type() in (QEvent.Type.Expose, QEvent.Type.UpdateRequest, QEvent.Type.Paint):
                NoPaint.eaten += 1
                return True
            return False

    window, splitter, host = _in_splitter()
    view = host._view  # noqa: SLF001 - the matrix asks Qt directly
    out: dict[str, Any] = {"ready": host.wait_ready(10.0), "open": _look(host)}
    total = sum(splitter.sizes())
    blocker = NoPaint(view)
    view.installEventFilter(blocker)  # installed last: it runs before the host's own watch
    for step, width in (("grown", 600), ("shrunk", 200)):
        splitter.setSizes([total - width, width])
        _pump(app, 250)  # the resize arrives, the scene follows; nothing draws
        out[f"{step}_at_once"] = _look(host)
        out[f"ready_{step}"], out[f"wait_{step}_s"] = _timed_wait(host, 5.0)
        out[step] = _look(host)
    out["ready_zero"], out["wait_zero_s"] = _timed_wait(host, 0.0)
    out["ready_default"], out["wait_default_s"] = _timed_wait(host, 1.0)
    out["ready_long"], out["wait_long_s"] = _timed_wait(host, 60.0)
    out["without_paint"] = _look(host)
    out["eaten"] = NoPaint.eaten
    view.removeEventFilter(blocker)
    splitter.setSizes([total // 2, total - total // 2])  # painting resumes with the next resize
    out["ready_painting"], out["wait_painting_s"] = _timed_wait(host, 5.0)
    out["painting"] = _look(host)
    _pump(app, 300)
    out["later"] = _look(host)
    out.update(stale_frames=host.stale_frames, probes=host.probes, health=_health(host))
    host.close()
    window.close()
    return out


#: Logical pane widths whose frame at 125 % rounds UP by half a pixel (width x 1.25 ends in
#: .5): there the frame of the pane is less than one device pixel off the size of a pane one
#: logical pixel WIDER — the pairs review round 5 found handed out.
HALF_PIXEL_WIDTHS = (442, 446)


def pane_one_pixel_wider(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Review round 5 — sentence 1 at a FRACTIONAL pixel ratio. Run with
    ``QT_SCALE_FACTOR=1.25``.

    Qt sizes the render target as the logical size times the ratio, rounded: a 442 px pane
    has a 553 px frame (552.5 rounds up), a 443 px pane a 554 px one. The pane is made
    ONE logical pixel wider while nothing draws the view (round 4's no-paint filter), so
    Qt's frame is still the narrower pane's. Round 4's host — "less than one device pixel
    off" — handed that frame out for the wider pane (553 is 0.75 off 553.75) and picked
    with the old viewport. Nothing is judged in here: a RAW grab is recorded beside the
    host's answers, and what QT says the window's size and ratio are."""
    from PyQt6.QtCore import QEvent, QObject

    class NoPaint(QObject):
        def eventFilter(self, _watched: Any, event: Any) -> bool:  # noqa: N802 - Qt's name
            return event.type() in (QEvent.Type.Expose, QEvent.Type.UpdateRequest, QEvent.Type.Paint)

    window, splitter, host = _in_splitter()
    view = host._view  # noqa: SLF001 - the matrix asks Qt directly
    out: dict[str, Any] = {"ready": host.wait_ready(10.0), "dpr": host.device_pixel_ratio(),
                           "open": _look(host), "pairs": []}
    total = sum(splitter.sizes())
    blocker = NoPaint(view)
    for width in HALF_PIXEL_WIDTHS:
        splitter.setSizes([total - width, width])
        pair: dict[str, Any] = {"ready": host.wait_ready(5.0), "before": _look(host)}
        view.installEventFilter(blocker)  # installed last: it runs before the host's own watch
        splitter.setSizes([total - width - 1, width + 1])
        _pump(app, 150)  # the resize arrives, the scene follows; nothing draws the view
        raw = view.grabWindow()  # what Qt's render target IS, asked without the host
        pair["raw"] = [int(raw.width()), int(raw.height()), float(raw.devicePixelRatio())]
        pair["wider"] = _look(host)
        view.removeEventFilter(blocker)
        out["pairs"].append(pair)
    splitter.setSizes([total // 2, total - total // 2])  # painting resumes with the next resize
    out["ready_painting"], out["wait_painting_s"] = _timed_wait(host, 5.0)
    out["painting"] = _look(host)
    out.update(stale_frames=host.stale_frames, probes=host.probes, health=_health(host))
    host.close()
    window.close()
    return out


def pane_off_screen(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Review round 4 — where CI found it. The main window is moved so that the 3D pane
    lies entirely beyond the right edge of every screen. Then the pane is made smaller,
    larger, hidden and shown — and the window is moved back.

    What the platform does there is NOT one fact (measured on one Windows machine, on two
    days): a pane that grows beyond the edge gets its resize event and no expose; with
    the display asleep nothing else arrives either and Qt's frame keeps the old size for
    as long as the pane stays there; with the display awake an update request arrives
    and the frame is right. A pane SHOWN there was not exposed on either day. A truthful
    host gives a frame of the window's size or refuses — promptly: no ``wait_ready()``
    may wait for what will not come — and answers again once the pane is back on a
    screen. Nothing is judged in here."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QGuiApplication

    window, splitter, host = _in_splitter()
    view = host._view  # noqa: SLF001 - the matrix asks Qt directly
    out: dict[str, Any] = {"ready": host.wait_ready(10.0), "open": _look(host)}
    home = window.pos()
    total = sum(splitter.sizes())
    # the pane is the right part of the window: its left edge goes past the last screen
    edge = max(screen.geometry().right() for screen in QGuiApplication.screens()) + 1
    window.move(edge + 20 - (view.mapToGlobal(QPoint(0, 0)).x() - window.x()), window.y())
    _pump(app, 300)
    out["moved"] = _look(host)
    for step, sizes in (("shrunk", [total - 49, 49]), ("grown", [total - 137, 137]),
                        ("grown_more", [total // 2, total - total // 2])):
        splitter.setSizes(sizes)
        _pump(app, 250)  # the resize is delivered; whether an expose follows is the platform's
        out[f"{step}_at_once"] = _look(host)
        out[f"ready_{step}"], out[f"wait_{step}_s"] = _timed_wait(host, 5.0)
        out[step] = _look(host)
    out["ready_zero"], out["wait_zero_s"] = _timed_wait(host, 0.0)
    out["ready_default"], out["wait_default_s"] = _timed_wait(host, 1.0)
    host.hide()
    _pump(app, 100)
    host.show()
    _pump(app, 250)
    out["reshown_at_once"] = _look(host)
    out["ready_reshown"], out["wait_reshown_s"] = _timed_wait(host, 5.0)
    out["reshown"] = _look(host)
    window.move(home)
    out["ready_back"], out["wait_back_s"] = _timed_wait(host, 5.0)
    out["back"] = _look(host)
    _pump(app, 300)
    out["later"] = _look(host)
    out.update(stale_frames=host.stale_frames, probes=host.probes, health=_health(host))
    host.close()
    window.close()
    return out


def minimised_window(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """The main window of the Split workspace is minimised and restored; then the same
    for a standalone host. A minimised window stays "visible" for Qt."""
    from PyQt6.QtGui import QWindow

    window, _splitter, host = _in_splitter()
    out: dict[str, Any] = {"ready": host.wait_ready(10.0), "open": _look(host)}
    window.showMinimized()
    _pump(app, 300)
    # asked of Qt, not of the host: did the window system minimise the window at all?
    out["platform_minimised"] = bool(window.isMinimized())
    started = time.perf_counter()
    out["wait_minimised"] = _attempt(lambda: host.wait_ready(3.0))
    out["wait_minimised_s"] = round(time.perf_counter() - started, 2)
    out["minimised"] = _look(host)
    out["is_visible_minimised"] = host.is_visible()
    window.showNormal()
    out["ready_restored"] = host.wait_ready(10.0)
    out["restored"] = _look(host)
    host.close()
    window.close()
    alone, _sink, _sync = _host()
    alone.show()
    out["alone_ready"] = alone.wait_ready(10.0)
    alone._view.showMinimized()  # noqa: SLF001 - the user's button; the host has no such call
    _pump(app, 300)
    out["platform_minimised_alone"] = (
        alone._view.visibility() == QWindow.Visibility.Minimized)  # noqa: SLF001
    out["alone_minimised"] = _look(alone)
    alone._view.showNormal()  # noqa: SLF001
    out["alone_ready_restored"] = alone.wait_ready(10.0)
    out["alone_restored"] = _look(alone)
    alone.close()
    return out


def embedded_never_shown_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Embedded, parent not shown yet: an offscreen frame now, and the process would die
    when the parent shows the container. The host has none to give."""
    window, splitter = _splitter_window()
    host, _sink, _sync = _host((450, 500))
    splitter.addWidget(host.container(splitter))
    splitter.setSizes([450, 450])
    out = {"before_parent": _look(host), "wait_before_parent": _attempt(lambda: host.wait_ready(0.3))}
    window.show()  # the parent shows the container: host.show() was never called
    out["parent_shown_at_once"] = _look(host)
    out["ready"] = host.wait_ready(10.0)
    out["live"] = _look(host)
    _pump(app, 500)
    host.close()
    window.close()
    return out


def embed_after_show(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """A host shown standalone first and embedded afterwards — legal: only a spent host
    cannot be embedded."""
    host, _sink, _sync = _host((450, 500))
    host.show()
    out = {"ready_standalone": host.wait_ready(10.0), "standalone": _look(host)}
    window, splitter = _splitter_window()
    window.show()
    _pump(app, 200)
    splitter.addWidget(host.container(splitter))
    splitter.setSizes([450, 450])
    host.show()
    out["embedded_at_once"] = _look(host)
    out["ready"] = host.wait_ready(10.0)
    out["embedded"] = _look(host)
    _pump(app, 500)
    host.close()
    window.close()
    return out


def _through_window_states(app: Any, host: Any, target: Any, out: dict[str, Any]) -> None:
    """Full screen, normal, maximised, full screen from maximised, normal — each asked at
    once, then after ``wait_ready()``. ``target``: the top-level window whose state changes
    (the host's own view, or the main window that embeds it)."""
    for step, change in (("fullscreen", target.showFullScreen), ("normal", target.showNormal),
                         ("maximised", target.showMaximized),
                         ("fullscreen_from_maximised", target.showFullScreen),
                         ("normal_again", target.showNormal)):
        change()
        out[f"{step}_at_once"] = _look(host)
        # no event is delivered by a zero timeout: what the host says is what a frame says
        out[f"ready0_{step}"], out[f"wait0_{step}_s"] = _timed_wait(host, 0.0)
        out[f"ready_{step}"], out[f"wait_{step}_s"] = _timed_wait(host, 10.0)
        out[step] = _look(host)
        _pump(app, 200)
        out[f"{step}_later"] = _look(host)
    out["stale_frames"] = host.stale_frames


def window_states_standalone(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Review round 3, P1-1 — the app's own F11 path. ``showFullScreen()`` resizes the window
    SYNCHRONOUSLY: window and scene agree at once, and a grab still comes back in the old
    size until the next expose. A truthful host refuses in between, and after
    ``wait_ready()`` said yes the frame has the window's NEW size."""
    host, _sink, _sync = _host()
    host.show()
    out: dict[str, Any] = {"ready": host.wait_ready(10.0), "open": _look(host)}
    _through_window_states(app, host, host._view, out)  # noqa: SLF001 - the user's F11; no host call
    host.close()
    return out


def window_states_embedded(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """The same for the Split workspace's shape: the MAIN window goes full screen, normal,
    maximised — the host in its splitter pane is resized by the layout, at once for one
    transition and one event-loop pass later for another."""
    window, _splitter, host = _in_splitter()
    out: dict[str, Any] = {"ready": host.wait_ready(10.0), "open": _look(host)}
    _through_window_states(app, host, window, out)
    host.close()
    window.close()
    return out


#: The window sizes the walk asks for (it picks one of each list).
WALK_WIDTHS, WALK_HEIGHTS = (320, 500, 901, 1203, 1500), (60, 120, 333, 500, 701)
#: How the walk meets the screen (``random_walk``).
WALK_SCREENS = ("fit", "1024x768")


def random_walk(app: Any, seed: str = "1", steps: str = "250", screen: str = "fit") -> dict[str, Any]:
    """Review rounds 3 and 4 — the host under a SEEDED random order of everything a
    parent can do to an embedded host: move the splitter (to nothing, to one pixel, wide),
    resize, maximise, full screen, minimise, hide and show the pane, the host, the window.
    After every operation the host is asked for a frame, a pick and a projection — at once,
    after ``wait_ready()`` (with a timeout of 5 s, 0.3 s or none), or after the event loop
    ran. Nothing is judged in here: every answer is recorded beside what QT said about the
    window at that moment — its size, and how much of it is on a screen.

    ``screen`` — the walk must not depend on the screen it happens to find (round 4: it
    asked for 1203 and 1500 px wide windows on whatever was there; on a 1024 px runner the
    pane ended up beyond the edge):

    - ``fit``: every size is capped by the screen's AVAILABLE area and the window is put
      at its top-left, so that the whole window is on the screen on any screen.
    - ``1024x768``: the window where such a screen leaves it — the sizes as asked,
      capped as Windows caps them there, the window placed so that this screen's right
      and bottom edges are where that screen's would be. Parts of this walk have the
      pane beyond the edge, on every machine.

    The ORDER of operations is the same for both and for every screen: one generator
    draws the operations, a second one the timeouts.
    """
    import random

    if screen not in WALK_SCREENS:
        raise ValueError(f"screen must be one of {WALK_SCREENS}, not {screen!r}")
    rng = random.Random(int(seed))
    timeouts = random.Random(int(seed) + 1)
    window, splitter, host = _in_splitter()
    view = host._view  # noqa: SLF001 - the matrix asks Qt directly
    records: list[dict[str, Any]] = []
    if screen == "fit":
        area = _available()
        widths = [min(width, area.width() - 2 * HOME[0]) for width in WALK_WIDTHS]
        heights = [min(height, area.height() - HOME[1] - 60) for height in WALK_HEIGHTS]
    else:
        widths, heights = list(WALK_WIDTHS), list(WALK_HEIGHTS)
        whole = window.screen().geometry()
        window.setMaximumSize(1040, 784)  # what Windows lets a window be on 1024 x 768
        window.move(whole.right() + 1 - 1024 + 78, whole.bottom() + 1 - 768 + 60)

    def qt_says() -> dict[str, Any]:
        return {"window": [int(view.width()), int(view.height())], "visible": bool(view.isVisible()),
                "exposed": bool(view.isExposed()), "minimised": bool(window.isMinimized()),
                "on_screen": _on_screen(host)}

    def observe(what: str, **extra: Any) -> None:
        said = qt_says()  # before the grab
        records.append({"what": what, "qt": said, "look": _look(host), **extra})

    def sizes() -> str:
        width = rng.choice([0, 0, 1, 1, 2, 3, 5, 24, 49, 50, 51, 137, 450, 899, 900])
        splitter.setSizes([900 - width, width])
        return f"setSizes(.., {width})"

    def window_resize() -> str:
        width, height = rng.choice(widths), rng.choice(heights)
        window.resize(width, height)
        return f"window.resize({width}, {height})"

    def named(call: Callable[[], Any], label: str) -> Callable[[], str]:
        def run() -> str:
            call()
            return label
        return run

    container = host.container()
    operations: dict[str, Callable[[], str]] = {
        "sizes": sizes, "sizes2": sizes, "sizes3": sizes, "window_resize": window_resize,
        "minimise": named(window.showMinimized, "showMinimized"),
        "normal": named(window.showNormal, "showNormal"),
        "maximise": named(window.showMaximized, "showMaximized"),
        "fullscreen": named(window.showFullScreen, "showFullScreen"),
        "hide_container": named(container.hide, "container.hide"),
        "show_container": named(container.show, "container.show"),
        "host_hide": named(host.hide, "host.hide"), "host_show": named(host.show, "host.show"),
        "hide_window": named(window.hide, "window.hide"),
        "show_window": named(window.show, "window.show"),
    }
    names = sorted(operations)
    out: dict[str, Any] = {"seed": int(seed), "steps": int(steps), "screen": screen,
                           "ready": host.wait_ready(10.0), "api": host.graphics_api(),
                           "dpr": host.device_pixel_ratio()}
    observe("open", mode="open")
    for _ in range(int(steps)):
        label = operations[rng.choice(names)]()
        mode = rng.choice(["at_once", "wait", "pump", "wait", "pump_wait"])
        if mode == "at_once":
            observe(label, mode=mode)
            continue
        if mode in ("pump", "pump_wait"):
            _pump(app, 120)
        if mode in ("wait", "pump_wait"):
            timeout = timeouts.choice([5.0, 5.0, 5.0, 0.3, 0.0])
            ready, took = _timed_wait(host, timeout)
            observe(label, mode=mode, ready=ready, took=took, timeout=timeout)
        else:
            observe(label, mode=mode)
        # liveness: Qt says the window can show something, and the event loop has run.
        # WHERE the window is decides what must follow (the judge): all of it on a screen
        # — the host must come up; else it may refuse, but promptly.
        _pump(app, 150)
        said = qt_says()
        if (said["visible"] and said["exposed"] and not said["minimised"]
                and min(said["window"]) >= 2):
            settles, took = _timed_wait(host, 3.0)
            records[-1].update(settles=settles, settle_took=took, settle_on_screen=said["on_screen"])
            if settles is not True:
                records[-1]["stuck"] = f"{host.state.value}: {host._facts()}"  # noqa: SLF001
    window.showNormal()
    window.show()
    container.show()
    area = _available()
    window.move(area.left() + HOME[0], area.top() + HOME[1])  # back on the screen, whatever the walk did
    window.resize(min(900, area.width() - 2 * HOME[0]), min(500, area.height() - HOME[1] - 60))
    splitter.setSizes([450, 450])
    out["final_ready"], took = _timed_wait(host, 10.0)
    observe("final", mode="wait", ready=out["final_ready"], took=took, timeout=10.0)
    _pump(app, 300)
    out.update(records=records, stale_frames=host.stale_frames, probes=host.probes,
               longest_quiet_s=round(host.longest_quiet_s, 3), health=_health(host))
    host.close()
    window.close()
    return out


def wait_while_it_goes(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """wait_ready() is inside its event loop when the window is hidden, minimised, closed
    or destroyed: it must come back at once with False, not spin to its timeout."""
    from PyQt6 import sip
    from PyQt6.QtCore import QTimer

    out: dict[str, Any] = {}
    for how in ("hide", "close", "delete"):
        window, splitter = _splitter_window()
        host, _sink, _sync = _host((450, 500))
        splitter.addWidget(host.container(splitter))
        splitter.setSizes([450, 450])
        if how == "hide":
            QTimer.singleShot(0, window.hide)
        elif how == "close":
            QTimer.singleShot(0, host.close)
        else:
            QTimer.singleShot(0, lambda window=window: sip.delete(window))
        window.show()
        started = time.perf_counter()
        answer = _attempt(lambda host=host: host.wait_ready(5.0))
        out[how] = {"wait_ready": answer, "seconds": round(time.perf_counter() - started, 2),
                    "state": host.state.value, "grab": _grab(host)}
        _pump(app, 200)
        host.close()
        if how != "delete":
            window.close()
    return out


def sink_clear_orders(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """The sink's teardown in every order relative to the host's death — and
    ``SceneSync.reset()`` alone on a dead engine, then a fresh host through the same
    sink and sync."""
    from PyQt6 import sip
    from PyQt6.QtWidgets import QWidget

    from open_garden_planner.core.scene3d import Material, Params, Record, SunState, Transform
    from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost
    from open_garden_planner.ui.view3d.quick3d.shots import TopDownShot

    out: dict[str, Any] = {}

    def dead_host(kill: Callable[[Any, Any], None]) -> tuple[Any, Any, Any]:
        host, sink, sync = _host()
        parent = QWidget()
        parent.resize(400, 300)
        host.container(parent)
        parent.show()
        host.wait_ready(10.0)
        kill(host, parent)
        return host, sink, sync

    def teardown(label: str, kill: Callable[[Any, Any], None]) -> None:
        host, sink, sync = dead_host(kill)
        out[label] = {"first_clear": _attempt(sink.clear), "items": list(sink.item_ids()),
                      "in_transaction": sink.in_transaction, "second_clear": _attempt(sink.clear),
                      "host_close": _attempt(host.close), "third_clear": _attempt(sink.clear),
                      "reset": _attempt(sync.reset), "state": host.state.value}

    teardown("parent_destroyed_then_clear", lambda _unused, parent: sip.delete(parent))
    teardown("parent_destroyed_close_then_clear",
             lambda host, parent: (sip.delete(parent), host.close()))
    teardown("close_then_clear", lambda host, _parent: host.close())
    _pump(app, 200)

    # THE recovery, as L1.3 will run it: the main window took the engine with it, the
    # next tick's apply fails, and SceneSync.reset() ALONE (it calls the sink's clear())
    # must bring sink and sync back — then a fresh host, the same sink, the same sync.
    moved = Record(item_id="w", kind="SHED", shape="rectangle", footprints=(RING,),
                   transform=Transform(east_cm=10.0),
                   material=Material("SHED", fill_rgba=(230, 20, 20, 255)),
                   height_cm=20.0, params=Params({"seed": "w"}))
    host, sink, sync = dead_host(lambda _unused, parent: sip.delete(parent))
    row: dict[str, Any] = {"apply_on_dead_engine": _attempt(lambda: sync.apply({"w": moved}))}
    row.update(poisoned=sync.poisoned, reset=_attempt(sync.reset))
    row.update(poisoned_after_reset=sync.poisoned, items=list(sink.item_ids()),
               in_transaction=sink.in_transaction, state=host.state.value)
    out["reset_alone_on_a_dead_engine"] = row

    fresh = Quick3DHost(SIZE)
    sink.attach(fresh)
    sync.apply({"w": _record()}, sun=SunState(45.0, 225.0))
    fresh.set_shot(TopDownShot((0.0, 0.0), PX_PER_CM))
    fresh.show()
    out["fresh"] = {"ready": fresh.wait_ready(10.0), "look": _look(fresh),
                    "parts": len(fresh.engine_parts()), "items": list(sink.item_ids()),
                    "state_equals_expected": sink.state() == sync.expected_state()}
    _pump(app, 300)
    fresh.close()
    return out


def health(app: Any, qml: Path | None = None) -> dict[str, Any]:
    """What a SHOWN host learns about itself on the GUI thread — with the shipped scene,
    with a scene whose binding fails (``qml``), or with a graphics device that cannot
    be created (the environment decides)."""
    gui_thread = threading.get_ident()
    slot_threads: list[bool] = []
    from PyQt6.QtCore import Qt

    host, _sink, _sync = _host(qml_dir=qml)
    # a second slot, connected the way the host connects its own (queued): WHERE does it run?
    host._view.frameSwapped.connect(  # noqa: SLF001
        lambda: slot_threads.append(threading.get_ident() == gui_thread),
        Qt.ConnectionType.QueuedConnection)
    out: dict[str, Any] = {"before_show": _health(host)}
    host.show()
    started = time.perf_counter()
    out["ready"] = host.wait_ready(5.0)
    out["wait_s"] = round(time.perf_counter() - started, 2)
    out["shown"] = _look(host)
    _pump(app, 500)
    out["health"] = _health(host)
    out["frame_slot_on_gui_thread"] = all(slot_threads) if slot_threads else None
    host.close()
    out["health_after_close"] = _health(host)
    return out


def _health(host: Any) -> dict[str, Any]:
    report = host.health()
    return {"ok": report.ok, "frames_presented": report.frames_presented,
            "qml_warnings": [text[-160:] for text in report.qml_warnings],
            "qml_warning_count": report.qml_warning_count,
            "scene_graph_error": report.scene_graph_error,
            # the host's OWN slots: how often one of them ran on another thread than the GUI's
            "slots_off_gui_thread": host.slot_calls_off_the_gui_thread}


def render_loop(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """Which thread renders a shown window? No Python runs on it: Qt's own log
    (``qt.scenegraph.general``, on stderr) names the loop — the judge reads it."""
    host, _sink, _sync = _host()
    host.show()
    out = {"ready": host.wait_ready(10.0), "live": _look(host), "api": host.graphics_api()}
    _pump(app, 300)
    host.close()
    return out


# ── controls: what the host forbids, done on the raw view ────────────────────


def unguarded_show_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """CONTROL — shown, grabbed before the first expose. The image is fine; the process
    dies in the event loop that follows."""
    host, _sink, _sync = _host()
    host.show()
    image = host._view.grabWindow()  # noqa: SLF001 - the control reaches past the guard
    out = {"state": host.state.value, "grab": _frame(image)}
    print("GRABBED " + json.dumps(out), flush=True)  # the last sign of life, if the control works
    _pump(app, 1000)  # with the window ALIVE: a host that went out of scope would hide the death
    host.close()
    return out


def unguarded_grab_show(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """CONTROL — the one offscreen frame, then the raw view is shown."""
    host, _sink, _sync = _host()
    image = host.grab("offscreen")
    host._view.show()  # noqa: SLF001 - the control reaches past the guard
    out = {"state": host.state.value, "grab": _frame(image)}
    print("GRABBED " + json.dumps(out), flush=True)
    _pump(app, 1000)
    host.close()
    return out


def unguarded_show_hide_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """CONTROL — shown, hidden, then the offscreen grab the first state machine allowed
    ("no scene graph, not visible: new"). On xcb the process segfaults in the next
    event-loop pass; on Direct3D 11 it was measured to survive."""
    host, _sink, _sync = _host()
    host._view.show()  # noqa: SLF001
    host._view.hide()  # noqa: SLF001
    host._view.create()  # noqa: SLF001
    image = host._view.grabWindow()  # noqa: SLF001
    out = {"state": host.state.value, "grab": _frame(image)}
    print("GRABBED " + json.dumps(out), flush=True)
    _pump(app, 1000)
    host.close()
    return out


def unguarded_user_close_grab(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """CONTROL — a window the user closed, grabbed raw: an access violation in the grab
    (Direct3D 11, 2 of 2)."""
    host, _sink, _sync = _host()
    host.show()
    host.wait_ready(10.0)
    host._view.close()  # noqa: SLF001
    _pump(app, 300)
    print("GRABBING " + json.dumps({"state": host.state.value}), flush=True)
    image = host._view.grabWindow()  # noqa: SLF001
    out = {"state": host.state.value, "grab": _frame(image)}
    _pump(app, 1000)
    host.close()
    return out


def unguarded_collapsed_pane(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """CONTROL — not a death, a LIE: what the raw view answers in a collapsed pane and
    right after it reopened. The judge must find these frames wrong by their pixels."""
    window, splitter, host = _in_splitter()
    view = host._view  # noqa: SLF001
    out: dict[str, Any] = {"ready": host.wait_ready(10.0)}
    splitter.setSizes([900, 0])
    _pump(app, 300)
    out["collapsed"] = {"window": [view.width(), view.height()], "visible": view.isVisible(),
                        "exposed": view.isExposed(), "grab": _frame(view.grabWindow())}
    splitter.setSizes([450, 450])
    out["reopened_at_once"] = {"window": [view.width(), view.height()],
                               "root": [host._root.width(), host._root.height()],  # noqa: SLF001
                               "grab": _frame(view.grabWindow())}
    _pump(app, 300)
    out["reopened_later"] = {"grab": _frame(view.grabWindow())}
    host.close()
    window.close()
    return out


def unguarded_device_failure(app: Any, _qml: Path | None = None) -> dict[str, Any]:
    """CONTROL — a graphics device that cannot be created, and NOTHING connected to the
    window's sceneGraphError: Qt opens a modal error box and aborts when it is dismissed.
    This order never reaches its end by itself."""
    from PyQt6.QtCore import QUrl
    from PyQt6.QtQuick import QQuickView

    from open_garden_planner.ui.view3d.quick3d.host import QML_DIR, SCENE_FILE

    view = QQuickView()
    view.resize(*SIZE)
    view.setSource(QUrl.fromLocalFile(str(QML_DIR / SCENE_FILE)))
    view.show()
    print("SHOWN", flush=True)
    _pump(app, 60000)
    return {"survived": True}


def deadlock(app: Any, _qml: Path | None = None, *, handler: bool = True,
             supervised: bool = False) -> dict[str, Any]:
    """CONTROL (P1-C) — a Python Qt message handler, a message from Qt's render thread,
    and a GUI-thread call that waits for that thread: ``hide()``. With the handler it
    never returns. ``supervised``: under ``runlog.watchdog(supervised=True)``, whose
    second process ends what the first line of defence cannot."""
    from PyQt6.QtCore import QLoggingCategory, qInstallMessageHandler

    host, _sink, _sync = _host()
    host.show()
    out: dict[str, Any] = {"ready": host.wait_ready(10.0)}
    seen: list[str] = []
    if handler:
        qInstallMessageHandler(lambda _mode, _context, text: seen.append(text or ""))
    # any message from the render thread will do; this category makes it talk on every sync
    QLoggingCategory.setFilterRules("qt.scenegraph.renderloop.debug=true")
    print("HIDING " + json.dumps(out), flush=True)
    started = time.perf_counter()
    if supervised:
        from open_garden_planner.ui.view3d.quick3d import runlog

        runlog.GRACE_S = 3.0
        log = runlog.RenderLog(Path(sys.argv[2]), mirror=False)
        with runlog.watchdog(4.0, log, what="the deadlock control", supervised=True):
            host.request_frame()
            host.hide()
    else:
        if handler:
            faulthandler.cancel_dump_traceback_later()
            faulthandler.dump_traceback_later(4.0, exit=True)  # the first line of defence, alone
        host.request_frame()
        host.hide()
    out.update(returned_after_s=round(time.perf_counter() - started, 3), messages=len(seen))
    QLoggingCategory.setFilterRules("")
    if handler:
        qInstallMessageHandler(None)
    faulthandler.cancel_dump_traceback_later()
    host.close()
    return out


ORDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "show_grab": show_grab,
    "grab_show": grab_show,
    "show_wait_grab": show_wait_grab,
    "hide_grab": hide_grab,
    "show_hide_show_grab": show_hide_show_grab,
    "show_hide_before_expose_grab": show_hide_before_expose_grab,
    "grab_twice_hidden": grab_twice_hidden,
    "user_closes_window": user_closes_window,
    "close_anything": close_anything,
    "parent_destroyed_anything": parent_destroyed_anything,
    "embedded_splitter": embedded_splitter,
    "collapsed_pane": collapsed_pane,
    "tiny_pane": tiny_pane,
    "pane_off_screen": pane_off_screen,
    "pane_without_paint": pane_without_paint,
    "pane_one_pixel_wider": pane_one_pixel_wider,
    "minimised_window": minimised_window,
    "embedded_never_shown_grab": embedded_never_shown_grab,
    "embed_after_show": embed_after_show,
    "window_states_standalone": window_states_standalone,
    "window_states_embedded": window_states_embedded,
    "random_walk": random_walk,
    "wait_while_it_goes": wait_while_it_goes,
    "sink_clear_orders": sink_clear_orders,
    "health": health,
    "render_loop": render_loop,
    "unguarded_show_grab": unguarded_show_grab,
    "unguarded_grab_show": unguarded_grab_show,
    "unguarded_show_hide_grab": unguarded_show_hide_grab,
    "unguarded_user_close_grab": unguarded_user_close_grab,
    "unguarded_collapsed_pane": unguarded_collapsed_pane,
    "unguarded_device_failure": unguarded_device_failure,
    "deadlock_with_handler": lambda app, qml=None: deadlock(app, qml, handler=True),
    "deadlock_without_handler": lambda app, qml=None: deadlock(app, qml, handler=False),
    "deadlock_supervised": lambda app, _log=None: deadlock(app, None, handler=True, supervised=True),
}


#: Orders whose arguments are their own (a log path; a seed, a number of steps and how the
#: walk meets the screen) and not a QML directory.
OWN_ARGUMENTS = {"deadlock_supervised": 1, "random_walk": 3}


def main(argv: list[str]) -> int:
    order = argv[0] if argv else ""
    wanted = (OWN_ARGUMENTS[order],) if order in OWN_ARGUMENTS else (0, 1)
    if order not in ORDERS or len(argv) - 1 not in wanted:
        print(f"usage: quick3d_lifecycle_child.py <{'|'.join(ORDERS)}> [<qml dir>] "
              f"(random_walk: <seed> <steps> <{'|'.join(WALK_SCREENS)}>; deadlock_supervised: <log>)",
              file=sys.stderr)
        return 2
    faulthandler.enable(all_threads=True)
    # a hang is a failure too (the random walk is the long one)
    faulthandler.dump_traceback_later(600 if order == "random_walk" else 120, exit=True)
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv[:1])
    _register_calls()
    if order == "random_walk":
        result = random_walk(app, argv[1], argv[2], argv[3])
    else:
        qml_dir = Path(argv[1]).resolve() if len(argv) == 2 and order not in OWN_ARGUMENTS else None
        result = ORDERS[order](app, qml_dir)
    _pump(app, 500)  # a process doomed by a bad grab dies HERE, in the next event-loop passes
    print("RESULT " + json.dumps(result, default=str), flush=True)
    print("END", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
