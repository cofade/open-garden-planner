"""The host's states as a function of Qt's facts — the whole truth table (L1.2, #385).

``ui/view3d/quick3d/lifecycle.py`` is engine-free: it turns the facts Qt reports
about a window into one of six states, and ``Quick3DHost`` contains no state logic
of its own. So the table can be checked here, without a window, on every machine.
The contract itself is written down in that module's docstring, and only there.

What the table does NOT say since review round 4: that a frame of a live host has
the window's size. Only a frame says that (``Quick3DHost._frame``; the host tier and
the render tier test it). Round 3 had put it into the state — a fact an ``Expose``
event switched on — and Windows sends no expose to a pane that is not on a screen.

Two kinds of test:

- ``MEASURED`` — the rows somebody paid for: each is what Qt 6.11 was MEASURED to
  report in a situation (Direct3D 11 on an RTX 4070 and on WARP; the xcb row on
  GitHub's runner), and the state a truthful host must derive from it. Three of
  them were wrong in the first state machine (review round 2): they are marked.
  Two are rows where the state says "live" and a frame may still have the wrong
  size (rounds 3 and 4): they are marked too.
- invariants over EVERY combination of the facts (3,072) — stated as what must
  never happen, not as a second copy of the function.

That Qt really reports these facts, and what a host does in each state, is the
render tier's (``tests/integration/test_quick3d_lifecycle.py``).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterator
from typing import Any

import pytest

from open_garden_planner.ui.view3d.quick3d import lifecycle
from open_garden_planner.ui.view3d.quick3d.lifecycle import (
    MIN_SIDE_PX,
    STALL_S,
    WAIT_READY_DEFAULT_S,
    HostState,
    WindowFacts,
    state_of,
    why_no_frame,
)

LIVE_FACTS: dict[str, Any] = {
    "surface_created": True, "visible": True, "minimised": False, "width": 447, "height": 500,
    "scene_graph": True, "exposed": True, "root_width": 447.0, "root_height": 500.0}


def facts(**changes: Any) -> WindowFacts:
    return WindowFacts(**{**LIVE_FACTS, **changes})


# (what was done, the facts Qt reported, the state)
MEASURED: list[tuple[str, dict[str, Any], str]] = [
    ("a new QQuickView",
     {"surface_created": False, "visible": False, "scene_graph": False, "exposed": False}, "new"),
    ("show(), no event yet", {"scene_graph": False, "exposed": False}, "starting"),
    ("show(), one pass of the event loop", {}, "live"),
    ("hide(), no event yet: Qt still says exposed", {"visible": False}, "hidden"),
    ("hide(), later", {"visible": False, "exposed": False}, "hidden"),
    ("shown again, no event yet", {"exposed": False}, "starting"),
    ("minimised: Qt still says visible", {"minimised": True, "exposed": False}, "hidden"),
    # review round 2, P1-A — read as "new", took the offscreen frame, segfault on xcb
    ("show(); hide() before any event",
     {"visible": False, "scene_graph": False, "exposed": False}, "hidden"),
    # review round 2, P1-B — read as "live": a blank frame of the old size, a bogus pick
    ("the splitter pane collapsed to width 0: visible AND exposed", {"width": 0}, "hidden"),
    ("the pane reopened, no event yet: the scene is still 0 wide", {"root_width": 0.0}, "starting"),
    ("the pane squeezed to one pixel: no 3D is drawn", {"width": 1, "root_width": 1.0}, "hidden"),
    ("one pixel high", {"height": 1, "root_height": 1.0}, "hidden"),
    ("two pixels wide: the scene is drawn", {"width": 2, "root_width": 2.0}, "live"),
    ("resized, no event yet: the scene has the old size", {"width": 200}, "starting"),
    # Reviews 3 and 4 — two rows where every fact Qt reports is in place and a frame
    # still has the OLD size. The state is "live": a frame may be asked for. That it has
    # the window's size is said by the frame alone (the host checks; the tiers test it).
    ("showFullScreen(): Qt delivered the resize inside the call — a frame is still the old size",
     {"width": 5120, "height": 1440, "root_width": 5120.0, "root_height": 1440.0}, "live"),
    ("a pane that grew beyond the screen's edge: resized, and never drawn again",
     {"width": 137, "root_width": 137.0}, "live"),
    ("a pane SHOWN beyond the screen's edge: Windows never exposes it", {"exposed": False}, "starting"),
    ("the main window was maximised, no event yet: the embedded view has not changed at all",
     {}, "live"),
    # a window closed with its X button loses its platform window and keeps the scene graph
    ("closed by the user", {"visible": False, "exposed": False}, "hidden"),
    # no graphics device: Qt says visible and exposed and never gets a scene graph
    ("the graphics device could not be created", {"scene_graph": False}, "starting"),
]


@pytest.mark.parametrize(("_what", "changes", "expected"), MEASURED,
                         ids=[row[0] for row in MEASURED])
def test_what_qt_was_measured_to_report(_what: str, changes: dict[str, Any], expected: str) -> None:
    assert state_of(facts(**changes)).value == expected


def test_only_live_is_answerable() -> None:
    for _what, changes, expected in MEASURED:
        assert facts(**changes).answerable is (expected == "live"), _what


def every_combination() -> Iterator[WindowFacts]:
    for surface, visible, minimised, width, height, graph, exposed, root_w, root_h in itertools.product(
            (False, True), (False, True), (False, True), (0, 1, 2, 447), (0, 1, 2, 500),
            (False, True), (False, True), ("same", 0.0, 320.0), ("same", 240.0)):
        yield WindowFacts(surface, visible, minimised, width, height, graph, exposed,
                          float(width) if root_w == "same" else root_w,
                          float(height) if root_h == "same" else root_h)


ALL = list(every_combination())


def test_the_table_is_complete() -> None:
    assert len(ALL) == 3072
    assert {state_of(row) for row in ALL} == {
        HostState.NEW, HostState.STARTING, HostState.LIVE, HostState.HIDDEN}


def test_closed_and_spent_win_over_every_fact() -> None:
    assert state_of(None) is HostState.CLOSED and state_of(None, spent=True) is HostState.CLOSED
    for row in ALL:
        assert state_of(row, closed=True) is HostState.CLOSED
        assert state_of(row, closed=True, spent=True) is HostState.CLOSED
        assert state_of(row, spent=True) is HostState.SPENT


def test_new_means_no_platform_window_was_ever_created_and_nothing_else() -> None:
    """Only then is the one offscreen frame safe. "Not visible and no scene graph" is NOT
    new: that is also a window shown and hidden again (the xcb segfault)."""
    for row in ALL:
        assert (state_of(row) is HostState.NEW) is (not row.surface_created)


def test_live_needs_every_fact() -> None:
    """Each term was paid for: take any one away and the frame is fatal, blank or old."""
    for row in ALL:
        everything = (row.surface_created and row.visible and not row.minimised
                      and row.width >= 2 and row.height >= 2 and row.scene_graph and row.exposed
                      and round(row.root_width) == row.width and round(row.root_height) == row.height)
        assert (state_of(row) is HostState.LIVE) is everything, row


def test_no_fact_of_the_state_is_one_only_an_os_message_can_set() -> None:
    """Review round 4, the ruling. Round 3 added a tenth fact — "an expose arrived after
    the last resize" — as the sign that a frame would have the window's size. Only a
    paint message of the operating system could switch it on, and Windows sends none to a
    pane that grows where no screen is: the host waited for it for ever. The frame is the
    witness; the state holds what Qt REPORTS when asked, and nothing else."""
    names = list(WindowFacts.__dataclass_fields__)
    assert names == ["surface_created", "visible", "minimised", "width", "height", "scene_graph",
                     "exposed", "root_width", "root_height"]
    assert not hasattr(facts(), "target_synced")


def test_the_bounds_of_wait_ready_are_stated_once() -> None:
    """Sentences 2 and 3 of the contract name two numbers; they are constants of the
    module whose docstring is the contract, and the docstring quotes them."""
    assert WAIT_READY_DEFAULT_S == 1.0, "small enough for ONE call on the GUI thread; 10 s was not"
    assert STALL_S == 0.5 and STALL_S < WAIT_READY_DEFAULT_S
    assert lifecycle.REPROBE_S == 0.25 and lifecycle.REPROBE_S < STALL_S
    text = lifecycle.__doc__ or ""
    assert "``STALL_S`` (0.5 s)" in text and "``WAIT_READY_DEFAULT_S`` (1 s)" in text
    for sentence in ("returns the scene at the window's current size, or it raises",
                     "starts no pass of the event loop once ``timeout_s``",
                     "returns False promptly"):
        assert sentence in text, sentence
    flat = " ".join(text.split())
    # review round 5: sentence 2 said "within timeout_s" — a pass of the event loop drains
    # the whole queue (0.2 s asked, 1.80 s taken behind six handlers)
    for words in ("PLUS whatever was queued on the event loop when its last pass began",
                  "only ``wait_ready(0)``, which runs no event loop, is bounded by itself",
                  "is a nested event loop, and it takes user input",
                  "needs it nowhere on the GUI thread",
                  "Never call it from a timer slot",
                  "A tick that draws stops at its first ``HostStateError``",
                  "at most HALF a device pixel off ``logical × ratio``",
                  "is not silence"):
        assert words in flat, words


def test_what_raises_what_is_complete() -> None:
    """Review round 4, P2-3: the contract's "What raises what" left out the ONE offscreen
    frame that comes back in another size — an ``EngineError`` (the host is spent by
    then: there is no "later" a ``HostStateError`` could promise). Both errors a frame
    can end in are named, each with its case. (That the host raises them so:
    ``tests/ui/test_quick3d_host.py::TestStateMachine``.)"""
    text = lifecycle.__doc__ or ""
    raises = text[text.index("What raises what"):text.index("Why these facts and no fewer")]
    state_error, engine_error = raises.split("``EngineError``:")
    assert "``HostStateError``:" in state_error and "has another size than the window" in state_error
    assert "the ONE offscreen frame" in engine_error and "another size than the window" in engine_error
    assert "the host is spent by then" in engine_error


def test_without_a_scene_graph_no_state_gives_a_frame_but_new() -> None:
    """THE killer: a grab of a window that has a platform window and no scene graph."""
    for row in ALL:
        if row.surface_created and not row.scene_graph:
            assert state_of(row) in (HostState.STARTING, HostState.HIDDEN), row


def test_starting_means_on_its_way() -> None:
    """``wait_ready()`` waits while the host is starting — so nothing that is KNOWN not to
    come by itself may read as starting: not hidden, not minimised, not collapsed. (What
    cannot be known from Qt's facts — a pane no screen shows, a session that paints nothing
    — is bounded in ``wait_ready()`` itself since round 4: it gives a starting host up
    ``STALL_S`` after the last sign of progress; ``tests/ui/test_quick3d_host.py``.)"""
    for row in ALL:
        if state_of(row) is HostState.STARTING:
            assert row.visible and not row.minimised and row.has_area, row
        if row.surface_created and (not row.visible or row.minimised or not row.has_area):
            assert state_of(row) is HostState.HIDDEN, row


def test_the_smallest_window_that_shows_3d_is_two_pixels() -> None:
    """Measured (Direct3D 11, GPU and WARP): at 1 px the frame is the bare clear colour,
    in either dimension; at 2 px it is the scene."""
    assert MIN_SIDE_PX == 2
    assert not facts(width=1, root_width=1.0).has_area and facts(width=2, root_width=2.0).has_area
    assert not facts(height=1, root_height=1.0).has_area


def test_the_scene_has_caught_up_when_it_rounds_to_the_windows_size() -> None:
    """The root item's size is a real, the window's an int (a fractional scale factor)."""
    assert facts(root_width=446.6).root_caught_up and facts(root_width=447.4).root_caught_up
    assert not facts(root_width=446.4).root_caught_up
    assert not facts(root_height=501.0).root_caught_up


REMEDY = {
    HostState.STARTING: "wait_ready()", HostState.HIDDEN: "wait_ready()",
    HostState.NEW: "wait_ready()", HostState.SPENT: "Build a new host",
    HostState.CLOSED: "closed",
}


def test_every_refusal_says_why_and_what_to_do() -> None:
    for row in ALL:
        state = state_of(row)
        if state is HostState.LIVE:
            continue
        for embedded in (False, True):
            text = why_no_frame(state, row, embedded=embedded)
            assert REMEDY[state] in text, (state, text)
    assert REMEDY[HostState.SPENT] in why_no_frame(HostState.SPENT, facts(), embedded=False)
    assert REMEDY[HostState.CLOSED] in why_no_frame(HostState.CLOSED, None, embedded=False)


@pytest.mark.parametrize(("changes", "embedded", "words"), [
    ({"scene_graph": False, "exposed": False}, False, "would kill the process"),
    ({"exposed": False}, False, "shown again but not exposed yet"),
    ({"root_width": 0.0}, False, "window 447 x 500, scene 0 x 500"),
    # the order of the reasons: the fatal one first, then the exposure, then the scene
    ({"scene_graph": False, "root_width": 0.0}, False, "would kill the process"),
    ({"exposed": False, "root_width": 0.0}, False, "shown again but not exposed yet"),
    # a pane shown where no screen is stays in this state: the text says so
    ({"exposed": False}, False, "will not be while no part of it is on a screen"),
    ({"visible": False}, False, "not visible"),
    ({"minimised": True}, False, "minimised"),
    ({"width": 0}, False, "no usable area (0 x 500 px"),
    ({"surface_created": False, "visible": False}, False, "never shown: show() it"),
    ({"surface_created": False, "visible": False}, True, "embedded host has no offscreen frame"),
])
def test_the_refusal_names_the_fact_that_is_missing(changes: dict[str, Any], embedded: bool,
                                                    words: str) -> None:
    row = facts(**changes)
    assert words in why_no_frame(state_of(row), row, embedded=embedded)


def test_a_host_whose_graphics_device_never_came_is_not_told_to_wait() -> None:
    """Review round 3, P2-6: ``wait_ready()`` answers False for such a host — the refusal
    said "Call wait_ready() first". It names the failure and where to read it instead."""
    row = facts(scene_graph=False)
    assert state_of(row) is HostState.STARTING
    text = why_no_frame(HostState.STARTING, row, embedded=False,
                        graphics_error="Failed to create the D3D11 device")
    assert "could not create the graphics device" in text
    assert "Failed to create the D3D11 device" in text
    assert "health().scene_graph_error" in text and "wait_ready() answers False" in text
    assert "Call wait_ready() first" not in text and "would kill the process" not in text
    # without such a report the same facts are the ordinary "not exposed yet"
    assert "Call wait_ready() first" in why_no_frame(HostState.STARTING, row, embedded=False)
    # and a host that HAS its scene graph is not blamed for an old report
    live_soon = facts(exposed=False)
    assert "graphics device" not in why_no_frame(
        HostState.STARTING, live_soon, embedded=False, graphics_error="an old report")


def test_a_spent_host_is_never_told_to_show_itself() -> None:
    """The first error message recommended ``show()`` — which killed the process."""
    text = why_no_frame(HostState.SPENT, facts(), embedded=False)
    assert "show() it" not in text and "Build a new host" in text
