"""Records in, one ``QImage`` out — without showing a window (L1.2). ENGINE module.

``render_records`` runs the real pipeline — ``SceneSync`` → ``Quick3DSink`` →
``Quick3DHost`` — on a host that is never shown, and reads the frame back. It is
what the render tests, the frozen exe's ``--selftest`` and scripts call.

FOR PROCESSES THAT OWN THEMSELVES — the self-test, a tool, a test. Not for the
running app: each call blocks the GUI thread for 0.4–1.3 s (it creates a
graphics device, compiles shaders, renders one frame and destroys the device
again), and creating and destroying a device per call is the pattern behind the
memory growth ADR-048 criterion 10 still has open. The app shows a
``Quick3DHost`` and keeps it.

What it guarantees:

- **One host per frame.** A never-shown Qt Quick window renders exactly one
  frame (``host.py``: ``NEW`` → ``SPENT``); every call builds its own host and
  closes it.
- **The clock stops at the finished READBACK** (``open_ms``), never at a frame
  being submitted: on a software rasteriser the real cost lands in the readback.
- **Errors are loud.** Every Qt message of the render is recorded; a QML error or
  a shader that does not compile raises ``RenderError`` — the frame would still
  have rendered, in the wrong colours (``qt_messages.py``). So does a backend
  that cannot render 3D at all (the software scene graph).
- **Nothing is silently missing.** A builder that failed left its item without a
  solid; ``OffscreenFrame.build_failures`` names every such item.
- **It leaves the process as it found it.** No output unless a ``log`` is passed;
  the message handler and Qt's logging rules are put back.
- **Never beside a shown Qt Quick window.** The call installs a process-wide Qt
  message recorder for its duration — safe only because everything it renders is
  rendered on the calling thread (measured: every message of a one-shot frame,
  shader errors included, arrives there; ``frame.qt["other_threads"]`` is the
  count of those that did not, and the render tier asserts 0). A SHOWN Qt Quick
  window renders on a thread of its own, and a Python message handler beside it
  deadlocks the process (``qt_messages.py``). So the call refuses
  (``RenderError``) while one is visible in this process.
- **It cannot hang silently** when the caller bounds it: ``runlog.RenderLog`` is
  flushed per line, and ``runlog.watchdog`` (around the call) dumps every
  thread's stack into it and exits with a non-zero code when the time is up. A
  frozen GUI exe has no stdout and no stderr; the log file is the only witness.
"""

from __future__ import annotations

import contextlib
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QImage

from open_garden_planner.core.scene3d import (
    BuilderRegistry,
    GroundBaking,
    GroundSpec,
    Record,
    SceneSync,
    SunState,
)

from . import qt_messages
from .adapter import Quick3DSink
from .host import Quick3DHost, shown_quick_windows
from .look import NEUTRAL_DAY, LookSpec
from .runlog import RenderLog, watchdog
from .shots import Shot

__all__ = ["OffscreenFrame", "RenderError", "RenderLog", "ensure_application", "image_rgba",
           "render_records", "watchdog"]


class RenderError(RuntimeError):
    """An offscreen render that must not be trusted (QML or shader error, no image).

    ``qt``: the recorder's report (``QtMessages.report()``) when Qt's messages are the
    reason — the errors themselves, and on which thread they arrived; empty otherwise.
    """

    def __init__(self, message: str, qt: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.qt: Mapping[str, Any] = dict(qt) if qt is not None else {}


_APPLICATION: list[QCoreApplication] = []  # keeps an application we had to create alive


def ensure_application() -> QCoreApplication:
    """The running application, or a new ``QApplication`` when there is none
    (a self-test, a script). Never call anything of Qt Quick 3D before this:
    ``QQuick3D.idealSurfaceFormat()`` without an application segfaults on Linux."""
    app = QCoreApplication.instance()
    if app is None:
        from PyQt6.QtWidgets import QApplication

        app = QApplication(sys.argv[:1])
        _APPLICATION.append(app)
    return app


def image_rgba(image: QImage) -> NDArray[np.uint8]:
    """A ``QImage`` as an ``(height, width, 4)`` uint8 array, RGBA, row 0 on top."""
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = converted.constBits()
    if bits is None:
        raise RenderError("the image has no pixel data")
    rows = np.frombuffer(bits.asstring(converted.sizeInBytes()), np.uint8).reshape(
        converted.height(), converted.bytesPerLine() // 4, 4)
    return rows[:, :converted.width(), :].copy()


@dataclass(frozen=True, slots=True)
class OffscreenFrame:
    """One rendered frame and what is known about how it came to be."""

    image: QImage
    #: Request → finished readback, milliseconds (QML load, builders, uploads, the frame).
    open_ms: float
    breakdown_ms: Mapping[str, float]
    #: ``Direct3D11``, ``OpenGL``, … (``host.GRAPHICS_API_NAMES``).
    graphics_api: str
    #: The device Qt rendered on, when ``graphics_info`` was asked for — e.g.
    #: ``NVIDIA GeForce RTX 4070``, ``Microsoft Basic Render Driver`` (WARP), ``llvmpipe …``.
    adapter: str | None
    device_pixel_ratio: float
    view_size: tuple[float, float]
    items: int
    parts: int
    #: Items whose builder failed — ``item_id`` → ``"ErrorType: message"``. Such an item
    #: is in the frame WITHOUT a solid; an empty mapping means every item was built.
    build_failures: Mapping[str, str] = field(default_factory=dict)
    #: ``QtMessages.report()``: counts per class, the errors, warnings, environment.
    qt: Mapping[str, Any] = field(default_factory=dict)
    #: Ground tiles the frame shows (0: bare plan ground, or no ground at all).
    ground_tiles: int = 0
    #: ``(ErrorType, message)`` when a ground baker was given and its bake failed — the
    #: frame then shows the plan ground BARE; None: baked, or nothing to bake with.
    ground_failure: tuple[str, str] | None = None
    #: Sky textures built for this frame: 1 with ``sky_light=True``, else 0 (L1.4).
    sky_builds: int = 0

    def rgba(self) -> NDArray[np.uint8]:
        return image_rgba(self.image)


def _silent(_phase: str, **_fields: Any) -> None:
    """The default log: nothing. A library call does not write to stdout."""


def render_records(
    records: Mapping[str, Record],
    *,
    shot: Shot,
    sun: SunState | None = None,
    ground: GroundSpec | None = None,
    size: tuple[int, int] = (640, 360),
    registry: BuilderRegistry | None = None,
    look: LookSpec = NEUTRAL_DAY,
    qml_dir: Path | None = None,
    log: Callable[..., None] | None = None,
    graphics_info: bool = False,
    ground_baker: GroundBaking | None = None,
    sky_light: bool = False,
    prefer_software: bool = False,
) -> OffscreenFrame:
    """Render ``records`` from ``shot`` under ``sun`` into an image of ``size``
    (logical pixels), through the real ``SceneSync`` → ``Quick3DSink`` path.

    For a process that owns itself — see the module docstring before calling
    this inside the running app.

    ``sun=None``: no sunlight (fill only). ``ground=None``: the endless meadow
    without a plan rectangle. ``ground_baker``: paints the plan's flat surfaces
    onto that rectangle (``ui.view3d.ground_bake.GroundBaker()``, L1.5); without
    one the plan ground is bare. The picture shows the finished ground: a baker
    with a time budget is run until nothing is pending (``GroundBaker(budget_s=
    None)`` does it in one pass). ``log``: a ``log(phase, **fields)`` callable
    (``runlog.RenderLog``); without one nothing is written anywhere.
    ``graphics_info=True`` also reports the graphics adapter (it switches Qt's
    ``qt.rhi.general`` debug output on for the duration of the call).
    ``sky_light=True`` builds ``look.sky`` and lets it back and light a perspective
    frame (L1.4); the default is the plain background and the look's flat fill —
    what the self-test and every truth probe render. ``prefer_software=True``
    renders on the software adapter of the graphics API (WARP on Direct3D), where
    no sky is ever built: the two together are refused (``ValueError``).

    Raises ``RenderError`` on a QML or shader error, when this backend cannot
    render 3D, when a Qt Quick window is shown in this process (module
    docstring), and when no image comes back. A blank-looking frame is NOT judged
    here: the caller knows what the frame must contain. A failed BUILDER does not
    raise (the pipeline contains it): read ``build_failures``.
    """
    if sky_light and prefer_software:
        raise ValueError("render_records: no sky light on the software adapter — a light probe "
                         "costs tens of seconds there (the compatibility mode's rule)")
    emit: Callable[..., None] = log if log is not None else _silent
    started = time.perf_counter()
    breakdown: dict[str, float] = {}
    ensure_application()
    shown = shown_quick_windows()
    if shown:
        raise RenderError(
            f"{shown} Qt Quick window(s) are shown in this process. An offscreen render records "
            "Qt's messages with a process-wide Python handler, and beside a window's render "
            "thread that deadlocks the process: close or hide the window first, or render in "
            "another process")
    messages = qt_messages.QtMessages(emit)
    previous = qt_messages.install(messages)
    host: Quick3DHost | None = None
    try:
        with qt_messages.graphics_info() if graphics_info else contextlib.nullcontext():
            host = Quick3DHost(size, qml_dir=qml_dir, look=look, log=emit,
                               prefer_software=prefer_software)
            breakdown["qml_load"] = host.qml_load_ms
            api = host.graphics_api()
            if not host.renders_3d():
                raise RenderError(
                    f"Qt Quick runs on the {api} backend here, where Qt Quick 3D draws nothing "
                    "(QT_QPA_PLATFORM=offscreen selects the software scene graph): no 3D frame "
                    "can be rendered")
            mark = time.perf_counter()
            sink = Quick3DSink(host)
            sync = SceneSync(sink, registry, ground_baker=ground_baker)
            sync.apply(records, sun=sun, ground=ground)  # one transaction
            while sync.ground_pending:  # a baker with a time budget: a still picture
                sync.continue_ground()  # shows the FINISHED ground, however many passes
            host.set_shot(shot)
            breakdown["scene_apply"] = (time.perf_counter() - mark) * 1000.0
            if sky_light:
                host.set_sky(look.sky)
                breakdown["sky_build"] = host.last_sky_build_ms
            parts = sum(sink.part_count(item_id) for item_id in sink.item_ids())
            failures = {item_id: f"{type(failure.error).__name__}: {failure.error}"
                        for item_id, failure in sync.failures.items()}
            emit("scene_applied", ms=round(breakdown["scene_apply"], 1),
                 items=len(sink.item_ids()), parts=parts, build_failures=sorted(failures))
            mark = time.perf_counter()
            image = host.grab("offscreen")
            breakdown["grab"] = (time.perf_counter() - mark) * 1000.0
            open_ms = (time.perf_counter() - started) * 1000.0
            frame = OffscreenFrame(
                image=image, open_ms=open_ms, breakdown_ms=breakdown, graphics_api=api,
                adapter=qt_messages.graphics_adapter(messages.info_lines()),
                device_pixel_ratio=host.device_pixel_ratio(), view_size=host.view_size(),
                items=len(sink.item_ids()), parts=parts, build_failures=failures,
                qt=messages.report(), sky_builds=host.sky_builds,
                ground_tiles=len(host.ground.keys()), ground_failure=sync.ground_failure,
            )
            emit("rendered", open_ms=round(open_ms, 1), api=api, adapter=frame.adapter,
                 px=f"{image.width()}x{image.height()}", qt=messages.report()["counts"],
                 other_threads=messages.other_threads)
    except Exception as error:
        emit("render_failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if host is not None:
            host.close()
        # Detach the recorder before anything can close the log it writes to: a Qt
        # message handler that raises is turned into qFatal by PyQt.
        qt_messages.uninstall(previous)
    if messages.errors:
        raise RenderError(
            f"{len(messages.errors)} Qt error(s) during the render — the frame is not the one "
            f"the QML and its shaders describe. First: {messages.errors[0]}", messages.report())
    return frame
