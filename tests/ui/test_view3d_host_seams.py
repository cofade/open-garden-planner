"""The three things the workspace story added to the engine host (Phase 17 L1.3, ADR-065).

``Quick3DHost(prefer_software=True)`` — the compatibility mode's switch —,
``install_event_filter`` — how the orbit camera hears the native window's input —
and ``release_cached_resources`` — how the graphics state Qt keeps for destroyed
Models is given back. Offscreen, in process: no pixels here (which adapter a window
REALLY renders on, and what a release frees, are read on a real device in the
render tier, ``test_view3d_workspace_render.py``).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent

from open_garden_planner.ui.view3d.quick3d.host import HostStateError, Quick3DHost

# as tests/ui/test_quick3d_host.py: no QML disk cache in the developer's profile, and no
# Python Qt message handler beside a host (the engine package's rule)
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")
pytestmark = pytest.mark.no_qt_log


@pytest.fixture()
def make_host(qtbot) -> Iterator[type[Quick3DHost]]:  # noqa: ARG001 - Qt init
    made: list[Quick3DHost] = []

    def build(**options: object) -> Quick3DHost:
        host = Quick3DHost((320, 240), **options)  # type: ignore[arg-type]
        made.append(host)
        return host

    yield build  # type: ignore[misc]
    for host in made:
        host.close()


def test_a_host_is_on_the_graphics_card_unless_it_is_told_otherwise(make_host) -> None:
    host = make_host()
    assert host.prefers_software is False
    assert host._view.graphicsConfiguration().prefersSoftwareDevice() is False


def test_prefer_software_asks_qt_for_the_software_adapter_of_this_window(make_host) -> None:
    host = make_host(prefer_software=True)
    assert host.prefers_software is True
    assert host._view.graphicsConfiguration().prefersSoftwareDevice() is True
    # per window: a second host beside it keeps its own choice
    other = make_host()
    assert other._view.graphicsConfiguration().prefersSoftwareDevice() is False


class _Watcher(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.keys: list[int] = []

    def eventFilter(self, _watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        if isinstance(event, QKeyEvent) and event.type() == QEvent.Type.KeyPress:
            self.keys.append(event.key())
            return True
        return False


def test_an_installed_filter_sees_the_views_events_first(make_host) -> None:
    host = make_host()
    watcher = _Watcher()
    host.install_event_filter(watcher)
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_PageUp, Qt.KeyboardModifier.NoModifier)
    assert QCoreApplication.sendEvent(host._view, event) is True
    assert watcher.keys == [Qt.Key.Key_PageUp]


def test_a_closed_host_takes_no_filter(make_host) -> None:
    host = make_host()
    host.close()
    with pytest.raises(HostStateError, match="closed"):
        host.install_event_filter(_Watcher())


def test_releasing_the_cached_graphics_state_is_qts_own_call_for_this_window(
        make_host, monkeypatch: pytest.MonkeyPatch) -> None:
    """``release_cached_resources`` is ``QQuickWindow.releaseResources()`` and nothing
    else: no Model is touched, the host's books stay as they are. (What it frees is
    measured on a real device: the memory soak of ``test_view3d_workspace_render.py``.)"""
    host = make_host()
    asked: list[int] = []
    monkeypatch.setattr(host._view, "releaseResources", lambda: asked.append(1))
    assert host.cache_releases == 0
    host.release_cached_resources()
    assert asked == [1] and host.cache_releases == 1
    assert host.part_count() == 0 and host.state.value == "new"


def test_releasing_on_a_host_that_never_showed_a_frame_is_harmless(make_host) -> None:
    host = make_host()
    host.release_cached_resources()      # the real call: nothing is cached yet
    host.release_cached_resources()
    assert host.state.value == "new" and host.health().scene_graph_error is None


def test_a_closed_host_has_nothing_to_release(make_host) -> None:
    host = make_host()
    host.close()
    with pytest.raises(HostStateError, match="closed"):
        host.release_cached_resources()
