"""THE STATE CONTRACT of the engine host (L1.2, fix rounds 2 to 5). Engine-free.

This docstring is the ONE place the contract is written down. ``host.py``, the
architecture docs, the ADR and the skills link here and do not restate it
(``tests/unit/test_quick3d_packaging.py`` pins that): the last time it stood in
nine places, three of them were wrong.

The contract — three sentences
------------------------------
1. **``grab()`` returns the scene at the window's current size, or it raises
   ``HostStateError``** — never a frame of another size, never another scene.
2. **``wait_ready(timeout_s)`` starts no pass of the event loop once ``timeout_s``
   is up, and True means: a ``grab()`` issued right after it answers.** It
   returns within ``timeout_s`` PLUS whatever was queued on the event loop when
   its last pass began; only ``wait_ready(0)``, which runs no event loop, is
   bounded by itself.
3. **When nothing is on its way, ``wait_ready()`` returns False promptly — after
   ``STALL_S`` (0.5 s) of silence — never at the deadline.**

THE WITNESS IS A FRAME, not a message of the operating system. Whether a frame
can be had is not something the host can know from what Qt reports: Qt resizes
the render target when it next draws the window, and nothing obliges a platform
to ask for that. (Measured: Windows asks for none of a pane that grew beyond the
screen's edge while the display sleeps — and for one, through an update request,
while it is awake.) So the host does not keep a fact "the frame is right". It
takes a frame and looks at its size — ``grab()`` for its caller,
``wait_ready()`` as a probe, ``pick()`` and ``project()`` when they know of none
for the window's size — and a frame of another size is a refusal, never an
answer.

"The window's size", exactly: Qt sizes a render target as the logical size times
the device pixel ratio, rounded per side (``qRound``). The RIGHT frame is
therefore at most HALF a device pixel off ``logical × ratio``, and that is the
check; at a ratio of 1 or more the frame of a window one logical pixel smaller
or larger is further off. (Round 4 allowed "less than one pixel": at 125 % a
pane grown from 442 to 443 px got its old 553 px frame back from ``grab()``.)

What "within" and "promptly" mean, exactly
------------------------------------------
- **``wait_ready()`` is a nested event loop, and it takes user input**: clicks,
  keys, timers and other objects' slots run inside it. The workspace needs it
  nowhere on the GUI thread — a view shows itself, and ``pick()`` / ``project()``
  take the frame they need. It is for a caller that must HAVE a frame and can
  wait: an export, a tool, a test. **Never call it from a timer slot, a sync
  tick, a paint or a resize handler**, and not from a click handler:
  ``try: host.pick(x, y)`` / ``except HostStateError``.
- One pass of Qt's event loop delivers EVERYTHING that is queued, not one
  event: ``wait_ready(0.2)`` behind six queued handlers of 0.3 s each returned
  after 1.80 s. That is the bound of sentence 2, and it cannot be made tighter
  from the thread those handlers run on. ``wait_ready(0)`` delivers nothing and
  waits for nothing: it looks, takes at most one frame (1 to 4 ms; about 0.3 s
  behind a frame Qt is presenting while the display sleeps), and answers.
- The default, ``WAIT_READY_DEFAULT_S`` (1 s), is a default for tools and tests.
  The FIRST show of a process is the slow one — its first expose creates the
  graphics device — and overruns it as a rule: True after 0.70 to 0.92 s for a
  top-level host and after 0.96 to 1.73 s for an embedded one (30 cold starts,
  GPU and WARP). On a slower machine the answer is False while the host IS on
  its way: pass a longer timeout — it costs nothing when nothing comes, the
  next bullet bounds that — or ask again; the test drivers pass 10 s. A timeout
  is clamped to a day; a negative one, or one that is not a number, is 0.
- "A sign of progress" is an event for the view that can change what a frame is
  (resize, expose, update request, show, hide, window state, platform surface)
  or a change of any fact below. "Silence" is time the event loop spent IDLE
  with no such sign: a pass of the loop that overran its step — a handler of
  something else was running: a plan load, a repaint — is not silence, however
  long it took. While signs keep coming the host waits, up to ``timeout_s``;
  after ``STALL_S`` of silence it answers False. That closes "waits for
  something that never comes" for every cause at once: a view that is not on
  any screen, a session that paints nothing, a window that never gets its
  first expose.
- False does not mean "never": the time was up, or nothing was on its way — and
  then the host comes up when the cause goes (the pane is moved back onto a
  screen). Ask again, or simply try the frame.

The facts
---------
``Quick3DHost`` reads nine facts from Qt on every call (``WindowFacts``) and this
module turns them into one of six states. No Qt import: the whole truth table
runs in the GPU-less unit tests, and ``host.py`` contains no state logic.

====  =====================================================================
S     a platform window was EVER created (Qt's ``PlatformSurface`` event —
      the fact behind ``QWindow.handle()``, which PyQt6 does not bind)
V     ``QWindow.isVisible()``
M     minimised (the view, or the top-level window that embeds it)
A     an area: width and height of at least ``MIN_SIDE_PX`` (2) logical px
G     ``QQuickWindow.isSceneGraphInitialized()``
E     ``QWindow.isExposed()``
R     the QML root item has the window's size
====  =====================================================================

The states — first match wins
-----------------------------
============  ==============================================================
``CLOSED``    ``close()`` ran to its end, or Qt destroyed the view
``SPENT``     else: the one offscreen frame was taken (its scene is gone)
``NEW``       else: not S
``HIDDEN``    else: not (V and not M and A) — hidden, minimised, or a pane
              collapsed to nothing
``LIVE``      else: G and E and R
``STARTING``  else — shown with an area, and not live yet
============  ==============================================================

What the states mean
--------------------
- ``LIVE``: a frame may be ASKED for — asking is safe, and sentence 1 holds for
  the answer. It is not a promise that the frame has the window's size: only the
  frame says that. ("The window" is the Qt Quick window itself. An embedded host
  whose PARENT was resized a moment ago still has its old size until the layout
  ran — and is truthfully live at that size until then.)
- ``STARTING``: do not ask for a frame. The first expose is pending (no scene
  graph: a grab now KILLS the process), or the next one is (shown again), or the
  scene has not caught up with a resize (R). The host refuses.
- ``NEW`` has exactly ONE frame, offscreen, and only when the host is not
  embedded; it is ``SPENT`` after. ``SPENT`` refuses ``show()`` and
  ``container()`` (they would kill the process). ``HIDDEN`` and ``SPENT`` give
  no frame.
- After ANY change of size or visibility: try the call and take the refusal —
  or, where a frame must be had and the caller can wait, ``wait_ready()``, and
  look at its answer. Do not reason about passes of the event loop: Qt delivers
  some resizes inside the call that caused them (``showFullScreen()``) and
  others later (a splitter move, ``showMaximized()``).

Which call is legal in which state
----------------------------------
==========================  =====  ========  ======  ======  =====  ======
call                        new    starting  live    hidden  spent  closed
==========================  =====  ========  ======  ======  =====  ======
``grab``                    once*  refuse    frame#  refuse  refuse refuse
``pick``, ``project``       refuse refuse    frame#  refuse  refuse refuse
``show``, ``container``     yes    yes       yes     yes     refuse refuse
``wait_ready``              False  waits+    probes  False+  False  refuse
``destroy_part``, ``clear``,
``close``                   yes    yes       yes     yes     yes    no-op
``state``, ``is_closed``,
``is_visible``, ``health``  yes    yes       yes     yes     yes    yes
every other call            yes    yes       yes     yes     yes    refuse
==========================  =====  ========  ======  ======  =====  ======

``refuse`` is a ``HostStateError`` whose text names the missing fact
(``why_no_frame``). ``once*``: refused when the host is embedded. ``frame#``:
the answer, or ``HostStateError`` when the frame Qt renders has another size
than the window. ``pick`` and ``project`` answer for a frame of the window's
size. In the steady state they take none. When the host knows of none — after
a resize — they take one themselves (measured: without it a pick right after a
resize MISSES). And after a REFUSAL they take no further frame until a sign of
progress is counted or ``REPROBE_S`` (0.25 s) has passed: they refuse on the
evidence of the frame that was just refused — 200 refused calls in a row cost
ONE frame. **A tick that draws stops at its first ``HostStateError``**: the next
call of the same tick would get the same answer. ``probes``: True when a frame
has the window's size; else it waits for a sign of progress.
``waits+``: while signs of progress keep coming (sentence 3). ``False+``: False
at once for a host that is not visible. One that Qt still calls visible
(minimised, a pane collapsed to nothing) gets its pending events first when
``timeout_s`` allows; if it is ``STARTING`` or ``LIVE`` after them (the pane was
reopened), it is treated as such.

What raises what
----------------
``HostStateError``: the call cannot be answered truthfully NOW — the state does
not allow it, or (``grab``, ``pick``, ``project`` on a live host) the frame Qt
rendered has another size than the window: the render target is behind. The
host counts those frames in ``stale_frames``. It keeps no fact about them:
``grab()`` takes a frame every time, and ``pick()`` / ``project()`` let a
refusal stand for ``REPROBE_S`` at most — less when a sign of progress comes.
``EngineError``: the engine failed — the scene file did not load, a property or
a scene function is missing or threw, a Model was refused or not destroyed, no
image came back, this backend renders no 3D at all — or the ONE offscreen frame
of a ``NEW`` host came back in another size than the window (there is no
"later" for it: the host is spent by then).

Why these facts and no fewer — each was paid for with a dead process or a wrong
frame (``docs/11-risks-and-technical-debt`` §11.4.32; ADR-048, addendum L1.2):
"not visible and no scene graph" is not "never shown" (xcb segfaults); a
collapsed splitter pane is visible, exposed and 0 px wide; one pixel draws no
3D; the scene lags the window after an asynchronous resize. ``isVisible()``
alone is neither necessary nor sufficient, and neither is ``isExposed()``: right
after ``hide()`` Qt still calls the window exposed, and a minimised window stays
"visible". And why there is no tenth: round 3 added "an expose arrived after
the last resize" as the sign that the render target had caught up — and Windows
sends no expose to a pane that grows where no screen is. A host that waited for
it waited for ever.

Not measured: platforms that un-expose an occluded window (macOS, Wayland) — a
visible window may read ``STARTING`` there for as long as it is covered;
``wait_ready()`` then answers False after ``STALL_S``, like for every other
cause; a change of the device pixel ratio in mid-session (a window dragged to a
display with another scale) — the frame's size is checked against its own
ratio, so the worst case is a refusal; and real display scaling of the
operating system (the ratios between 1 and 3 were set with ``QT_SCALE_FACTOR``
on a 100 % screen).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Final

#: The smallest window side, in logical pixels, at which Qt Quick 3D draws the scene.
#: Measured (Direct3D 11, GPU and WARP, 100 % scale): at 1 px the frame is the bare
#: clear colour, in either dimension; at 2 px it is the scene.
MIN_SIDE_PX: Final = 2

#: ``wait_ready()``'s default timeout, seconds. A default for tools and tests: the
#: workspace needs ``wait_ready()`` nowhere on the GUI thread (module docstring).
WAIT_READY_DEFAULT_S: Final = 1.0

#: How much SILENCE ``wait_ready()`` accepts before it answers False ("nothing is on its
#: way"): seconds the event loop was idle with no sign of progress — a busy pass is not
#: counted. Measured: on Windows the expose a host waits for arrives in the first pass
#: of the event loop (1 ms after a resize, 12 to 91 ms after ``show()``); on xcb +
#: llvmpipe the longest quiet spell before a host came up is in ADR-048's round-4 table.
STALL_S: Final = 0.5

#: How long a refusal of ``pick()`` / ``project()`` stands without a new frame when no
#: sign of progress was counted: at most four probe frames a second while a render
#: target stays behind — and a host that recovered without a sign the watch counts is
#: refused no longer than this.
REPROBE_S: Final = 0.25


class HostStateError(RuntimeError):
    """A call the host cannot answer truthfully in its current state (module docstring:
    "What raises what"). It lives HERE, in the engine-free module — ``host.py`` raises
    it and exports it — so that a caller which must tell "not now" from a hit can
    name it without loading the engine: the click handler of the 3D view
    (``ui/view3d/orbit_input.py``, L1.8) is ``try: host.pick(x, y)`` /
    ``except HostStateError``."""


class HostState(enum.Enum):
    """Where a host is in its life (module docstring)."""

    NEW = "new"
    STARTING = "starting"
    LIVE = "live"
    HIDDEN = "hidden"
    SPENT = "spent"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class WindowFacts:
    """What Qt says about the view at one moment (``Quick3DHost`` reads it per call)."""

    #: S — a platform window was created at some point.
    surface_created: bool
    #: V — ``QWindow.isVisible()``.
    visible: bool
    #: M — the view itself, or the top-level window that embeds it, is minimised.
    minimised: bool
    #: ``QWindow.width()`` / ``height()``, logical pixels (A: both at least MIN_SIDE_PX).
    width: int
    height: int
    #: G — ``QQuickWindow.isSceneGraphInitialized()``.
    scene_graph: bool
    #: E — ``QWindow.isExposed()``.
    exposed: bool
    #: The QML root item's size (R: it equals the window's).
    root_width: float
    root_height: float

    @property
    def has_area(self) -> bool:
        """Room for a 3D frame: at least ``MIN_SIDE_PX`` in both dimensions."""
        return self.width >= MIN_SIDE_PX and self.height >= MIN_SIDE_PX

    @property
    def root_caught_up(self) -> bool:
        return round(self.root_width) == self.width and round(self.root_height) == self.height

    @property
    def shows(self) -> bool:
        """Something of the view can be on screen: visible, not minimised, with an area."""
        return self.visible and not self.minimised and self.has_area

    @property
    def answerable(self) -> bool:
        """A frame may be ASKED for now: asking is safe, and its size will say the rest."""
        return self.shows and self.scene_graph and self.exposed and self.root_caught_up


def state_of(facts: WindowFacts | None, *, closed: bool = False, spent: bool = False) -> HostState:
    """The state for ``facts`` (``None``: Qt destroyed the view) — a pure function."""
    if closed or facts is None:
        return HostState.CLOSED
    if spent:
        return HostState.SPENT
    if not facts.surface_created:
        return HostState.NEW
    if not facts.shows:
        return HostState.HIDDEN
    return HostState.LIVE if facts.answerable else HostState.STARTING


def why_no_frame(state: HostState, facts: WindowFacts | None, *, embedded: bool,
                 graphics_error: str | None = None) -> str:
    """Why a host in ``state`` cannot give a frame, and what to do — for the error text.

    ``graphics_error``: what Qt said when it could not create the graphics device
    (``HostHealth.scene_graph_error``); such a host is ``STARTING`` for ever, and
    telling its caller to wait would be a lie.
    """
    if state is HostState.CLOSED or facts is None:
        return "the host is closed (or Qt destroyed its view)"
    if state is HostState.SPENT:
        return ("this host took its one offscreen frame and its scene is gone. "
                "Build a new host (offscreen.render_records does, per frame)")
    if state is HostState.NEW:
        if embedded:
            return ("an embedded host has no offscreen frame (its parent may show it at any "
                    "time): show its container and call wait_ready()")
        return "the host was never shown: show() it and call wait_ready()"
    if state is HostState.HIDDEN:
        if not facts.visible:
            return "the host is not visible: make it visible and call wait_ready()"
        if facts.minimised:
            return "the window is minimised: restore it and call wait_ready()"
        return (f"the view has no usable area ({facts.width} x {facts.height} px — a collapsed "
                f"pane? Below {MIN_SIDE_PX} px nothing 3D is drawn): give it room and call "
                "wait_ready()")
    if state is HostState.STARTING:
        if not facts.scene_graph and graphics_error is not None:
            return (f"Qt could not create the graphics device for this window ({graphics_error}): "
                    "the host will never be live. See health().scene_graph_error; wait_ready() "
                    "answers False")
        if not facts.scene_graph:
            return ("the window is shown but not exposed yet — it has no scene graph, and a "
                    "frame taken now would kill the process. Call wait_ready() first")
        if not facts.exposed:
            return ("the window is shown again but not exposed yet (and will not be while no "
                    "part of it is on a screen). Call wait_ready() first")
        return (f"the scene has not caught up with the window's size yet (window "
                f"{facts.width} x {facts.height}, scene {facts.root_width:g} x "
                f"{facts.root_height:g}): a frame taken now would be the old picture. "
                "Call wait_ready() first")
    return f"the host is {state.value}"
