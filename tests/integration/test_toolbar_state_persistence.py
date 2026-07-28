"""Integration tests for QMainWindow toolbar state persistence (issue #283).

``QMainWindow.saveState()`` serialises every toolbar keyed by its
``objectName`` and logs "'objectName' not set for QToolBar" when that key is
empty. Measured on Qt 6.11 (not assumed): an unnamed toolbar still *reaches*
the saved state — but under an empty, non-unique key, so ``restoreState()``
can only match those entries by **layout position** (which equals creation
order only while every toolbar goes to `TopToolBarArea` via a bare
`addToolBar()`, as all five do today). Change the set of unnamed toolbars and
that mapping shifts: a probe that saved "B hidden"
and restored into a window owning one extra unnamed toolbar created *before*
them hid A instead; dropping one toolbar loses the hidden state entirely.
With unique names both cases hit B.

MainToolbar, ConstraintToolbar and CategoryToolbar shipped without an
objectName until #283; SunSimToolbar and the soil-overlay toolbar always had
one. These tests pin both halves: the console symptom and the aliasing.

Object names are persistence keys — they must stay stable and untranslated.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import pytest
from PyQt6.QtCore import QMessageLogContext, QtMsgType, qInstallMessageHandler
from PyQt6.QtWidgets import QMainWindow, QToolBar

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings

# Every toolbar added to the main window via addToolBar(). Named explicitly so
# the parent-based filter below can never pass vacuously. The mixed casing is
# deliberate: these strings are persistence keys, so the pre-existing
# soil_overlay_toolbar cannot be renamed to match the others.
EXPECTED_TOOLBAR_NAMES = {
    "MainToolbar",
    "ConstraintToolbar",
    "CategoryToolbar",
    "SunSimToolbar",
    "soil_overlay_toolbar",
}


@pytest.fixture(autouse=True)
def _no_welcome_dialog(_reset_app_settings: Any) -> None:
    """Suppress the deferred (singleShot) modal Welcome dialog.

    Depends on the conftest reset so this write survives the per-test store
    clear. Without it, a pumped event loop can block the run on a modal dialog.
    """
    get_settings().show_welcome_on_startup = False


@pytest.fixture()
def window(qtbot: Any) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    return win


def _layout_toolbars(win: GardenPlannerApp) -> list[QToolBar]:
    """Toolbars owned by the main window itself.

    ``addToolBar()`` reparents to the QMainWindow, so this is exactly the set
    ``saveState()`` walks — a QToolBar nested inside some panel is not part of
    the main-window layout and needs no objectName.
    """
    return [tb for tb in win.findChildren(QToolBar) if tb.parent() is win]


class _QtMessageRecorder:
    """Capture Qt's own log output (qWarning etc.) for the duration of a block."""

    def __init__(self) -> None:
        self.messages: list[str] = []
        self._previous: Any = None

    def __enter__(self) -> _QtMessageRecorder:
        self._previous = qInstallMessageHandler(self._handler)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        qInstallMessageHandler(self._previous)

    def _handler(
        self, _mode: QtMsgType, _context: QMessageLogContext, message: str
    ) -> None:
        self.messages.append(message)


class TestToolbarObjectNames:
    def test_every_main_window_toolbar_has_a_unique_object_name(
        self, window: GardenPlannerApp
    ) -> None:
        """Catches any future toolbar added without an objectName — the whole
        point of #283, which sat unnoticed for three toolbars."""
        toolbars = _layout_toolbars(window)
        names = [tb.objectName() for tb in toolbars]

        unnamed = [tb.windowTitle() for tb in toolbars if not tb.objectName()]
        assert unnamed == [], f"toolbars without an objectName: {unnamed}"
        assert len(names) == len(set(names)), f"duplicate objectNames: {names}"
        # Guards the filter itself: if addToolBar ever stops reparenting, this
        # fails loudly instead of asserting over an empty list.
        assert set(names) >= EXPECTED_TOOLBAR_NAMES, f"missing toolbars in {names}"

    def test_save_state_logs_no_object_name_warning(
        self, window: GardenPlannerApp
    ) -> None:
        """The reported symptom: three warnings on stderr at every app exit."""
        with _QtMessageRecorder() as recorder:
            state = window.saveState()

        assert not state.isEmpty()
        offenders = [m for m in recorder.messages if "objectName" in m]
        assert offenders == [], f"saveState() still warns: {offenders}"


class TestToolbarStateRoundTrip:
    def test_restore_tracks_toolbars_by_name_not_position(
        self, window: GardenPlannerApp
    ) -> None:
        """What the empty objectName actually cost — aliasing, not just noise.

        Restoring a state written by a build with a different toolbar set is
        the real-world case: this app keeps gaining them (soil overlay, then
        sun-sim in Phase 14), and a user's persisted state outlives any single
        build. Simulated by dropping one toolbar from the live layout, so the
        saved state knows one more than the window owns.

        Measured pre-fix (objectNames cleared again on the real window): the
        remaining empty-keyed entries shift by one and the "Categories hidden"
        entry is dropped on the floor — Categories comes back visible.
        """
        # Sun-sim and soil-overlay start hidden by design; capture that baseline
        # so the assertion below is "exactly one more toolbar is hidden".
        hidden_before = {
            tb.objectName() for tb in _layout_toolbars(window) if tb.isHidden()
        }
        category = window.category_toolbar
        assert not category.isHidden()

        category.setVisible(False)
        state = window.saveState()
        category.setVisible(True)

        window.removeToolBar(window.main_toolbar)
        window.main_toolbar.setParent(None)  # removeToolBar alone keeps it a child
        try:
            assert window.restoreState(state)

            assert category.isHidden(), "saved state did not follow the toolbar name"
            hidden_after = {
                tb.objectName() for tb in _layout_toolbars(window) if tb.isHidden()
            }
            assert hidden_after == hidden_before | {"CategoryToolbar"}, (
                "restore hid the wrong toolbar"
            )
        finally:
            # Put it back rather than leaving an orphaned top-level QToolBar
            # alive only through the window's Python attribute.
            window.insertToolBar(window.constraint_toolbar, window.main_toolbar)

    def test_round_trip_keeps_every_toolbar_in_its_area(
        self, window: GardenPlannerApp
    ) -> None:
        """Characterisation guard, not a #283 pin (it passes either way): a
        save/restore round trip must not drop or re-home a toolbar — including
        the sun-sim one on its own row (``addToolBarBreak()`` in
        application._setup_central_widget), the open question #283 raised.

        The row must be read via ``toolBarBreak()``: all five toolbars live in
        ``TopToolBarArea``, so an area-only snapshot is a constant map that
        stays green even when a restore flattens the sun-sim toolbar onto the
        first row (measured).
        """

        def snapshot() -> dict[str, tuple[object, bool]]:
            return {
                tb.objectName(): (window.toolBarArea(tb), window.toolBarBreak(tb))
                for tb in _layout_toolbars(window)
            }

        before = snapshot()
        assert before["SunSimToolbar"][1] is True, "sun-sim toolbar lost its own row"

        assert window.restoreState(window.saveState())

        assert snapshot() == before


class TestToolbarVisibilityIsOwnedByTheApp:
    """Restored state may not decide whether a toolbar exists on screen.

    #283 manual test: a stray right-click hid the Categories toolbar — i.e.
    every drawing tool — and, because the layout is saved on exit, it stayed
    gone across restarts with the only way back hidden in the same menu.
    """

    def test_there_is_no_toolbar_context_menu(self, window: GardenPlannerApp) -> None:
        assert window.createPopupMenu() is None

    def test_a_saved_hidden_core_toolbar_is_healed_on_next_launch(
        self, qtbot: Any
    ) -> None:
        first = GardenPlannerApp()
        qtbot.addWidget(first)
        for toolbar in (first.main_toolbar, first.category_toolbar):
            toolbar.setVisible(False)
        first._ui_state.save_geometry(first)

        second = GardenPlannerApp()
        qtbot.addWidget(second)

        # Guards against a vacuous pass: the state must actually be read back.
        assert second._geometry_restored, "no state was restored — test proves nothing"
        assert not second.main_toolbar.isHidden()
        assert not second.category_toolbar.isHidden()
        assert not second.constraint_toolbar.isHidden()

    def test_feature_toolbars_start_hidden_even_when_saved_visible(
        self, qtbot: Any
    ) -> None:
        """#286: the soil-overlay toolbar used to come back visible while its
        menu action stayed unchecked and the canvas tint was off."""
        first = GardenPlannerApp()
        qtbot.addWidget(first)
        first.soil_overlay_toolbar.setVisible(True)
        first._sun_toolbar.setVisible(True)
        first._ui_state.save_geometry(first)

        second = GardenPlannerApp()
        qtbot.addWidget(second)

        assert second._geometry_restored, "no state was restored — test proves nothing"
        assert second.soil_overlay_toolbar.isHidden()
        assert second._sun_toolbar.isHidden()
        assert not second._soil_overlay_action.isChecked()


class TestEmptyNamesAliasInQt:
    """Pins the mechanism §11.4 leads with, on a bare QMainWindow.

    The app's own toolbars are all created in its constructor, so the
    "an unnamed toolbar created *before* the others steals their saved state"
    branch cannot be reproduced against ``GardenPlannerApp``. It is Qt
    behaviour, and the doc entry cites it — so it gets pinned here rather than
    resting on a scratch probe nobody can re-run.
    """

    @staticmethod
    def _build(
        qtbot: Any, named: bool, extra_first: bool
    ) -> tuple[QMainWindow, dict[str, QToolBar]]:
        """A window with toolbars A and B, optionally preceded by X.

        X is created *first*, which is what shifts the positional matching
        empty keys fall back to.
        """
        win = QMainWindow()
        qtbot.addWidget(win)
        bars: dict[str, QToolBar] = {}
        for title in (("X", "A", "B") if extra_first else ("A", "B")):
            tb = QToolBar(title, win)
            if named:
                tb.setObjectName(title)
            win.addToolBar(tb)
            bars[title] = tb
        return win, bars

    def test_unique_names_survive_an_added_toolbar(self, qtbot: Any) -> None:
        src, src_bars = self._build(qtbot, named=True, extra_first=False)
        src_bars["B"].setVisible(False)
        state = src.saveState()

        dst, dst_bars = self._build(qtbot, named=True, extra_first=True)
        assert dst.restoreState(state)

        assert dst_bars["B"].isHidden()
        assert not dst_bars["A"].isHidden()

    def test_empty_names_hide_the_wrong_toolbar(self, qtbot: Any) -> None:
        """The damage, reproduced: "B is hidden" lands on A.

        Also the positive control for ``_QtMessageRecorder`` — without it, the
        "saveState() logs nothing" test above could pass simply because the
        handler never fires.
        """
        src, src_bars = self._build(qtbot, named=False, extra_first=False)
        src_bars["B"].setVisible(False)
        with _QtMessageRecorder() as recorder:
            state = src.saveState()
        assert [m for m in recorder.messages if "objectName" in m], (
            "recorder captured nothing — the no-warning test above proves nothing"
        )

        dst, dst_bars = self._build(qtbot, named=False, extra_first=True)
        assert dst.restoreState(state)

        assert dst_bars["A"].isHidden(), (
            "Qt no longer aliases empty objectNames onto the wrong toolbar. This "
            "pins Qt's fallback for the §11.4 entry — a failure here means Qt "
            "changed, not that Open Garden Planner broke."
        )
        assert not dst_bars["B"].isHidden()
