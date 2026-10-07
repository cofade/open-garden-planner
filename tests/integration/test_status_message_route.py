"""Assert the propagation refusal actually REACHES the user.

Four review rounds of green tests did not catch that the refusal was silent,
because every one of them asserted "nothing was stored" and "the panel
repopulated" — never that a message was delivered. It was not: `CanvasView
.set_status_message` asked `self.parent().statusBar()`, and in the production
layout the canvas's parent is the `QSplitter` from `application.py`, which has no
`statusBar`. The `hasattr` guard swallowed the miss, so all two dozen
`set_status_message` callers were silent no-ops.

These tests pin the delivery route end to end: panel -> signal -> view ->
status bar. A refusal that is only *stored* correctly is not refused *visibly*.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication, QMainWindow, QSplitter

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.views.planting_calendar_view import PlantingCalendarView

TOMATO = {
    "scientific_name": "Solanum lycopersicum", "common_name": "Tomato",
    "source_id": "414", "indoor_sow_start": -8, "indoor_sow_end": -6,
    "transplant_start": 4, "harvest_start": 10, "harvest_end": 18,
}

REFUSAL_PREFIX = "The end date of a propagation step"


def _window(qtbot) -> tuple[QMainWindow, QSplitter, CanvasView]:
    """The real container shape: window -> splitter -> canvas view."""
    window = QMainWindow()
    qtbot.addWidget(window)

    scene = CanvasScene(width_cm=2000, height_cm=2000)
    item = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=ObjectType.TREE, name="Tomato",
    )
    item.metadata["plant_species"] = dict(TOMATO)
    scene.addItem(item)

    splitter = QSplitter()
    view = CanvasView(scene)
    splitter.addWidget(view)
    window.setCentralWidget(splitter)
    window.statusBar()          # the real MainWindow owns one

    # Exactly what application.py does after building the splitter.
    view.status_message.connect(
        lambda message: window.statusBar().showMessage(message)
    )
    window.resize(1200, 900)
    window.show()
    QApplication.processEvents()
    return window, splitter, view


def _calendar(qtbot) -> PlantingCalendarView:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    item = CircleItem(
        center_x=100, center_y=100, radius=20,
        object_type=ObjectType.TREE, name="Tomato",
    )
    item.metadata["plant_species"] = dict(TOMATO)
    scene.addItem(item)
    pm = ProjectManager()
    pm.set_location({"frost_dates": {"last_spring_frost": "04-09"}})

    view = PlantingCalendarView(scene, pm)
    qtbot.addWidget(view)
    view._prop_toggle.setChecked(True)
    view.refresh()
    view.resize(1200, 900)
    view.show()
    QApplication.processEvents()
    return view


class TestTheProductionWiringExists:
    """Pin the connects in `application.py`, which round 6 showed are unpinned.

    Every other test in this file builds its OWN window and its OWN lambda, so
    the whole suite stayed green with `application.py`'s connect replaced by
    `pass` — which is exactly the regression that made the original P0 possible
    (a route that resolves to nothing in the shipping layout). A guard that only
    exercises its own wiring cannot catch the wiring being absent.

    AST rather than a live app so it costs nothing and cannot be satisfied by a
    runtime coincidence.
    """

    #: Derived from ``__file__``, never absolute.
    #:
    #: This was a hardcoded author path, which made the guard fail on
    #: `ubuntu-latest` the moment it landed (round 7 measured 3 failures there):
    #: the guard added to prevent a regression took CI red on arrival.
    APP = (
        Path(__file__).resolve().parents[2]
        / "src" / "open_garden_planner" / "app" / "application.py"
    )

    @staticmethod
    def _source() -> str:
        path = TestTheProductionWiringExists.APP
        assert path.exists(), (
            f"the application module this guard pins is not where the repo says: "
            f"{path}. A hardcoded path here is what broke CI in round 7."
        )
        return path.read_text(encoding="utf-8")

    @staticmethod
    def _connects() -> dict[str, str]:
        tree = ast.parse(TestTheProductionWiringExists._source())
        found: dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "connect":
                continue
            # The SIGNAL is `func.value` (`self.<thing>.status_message`); the
            # argument is the SLOT. Checking the argument for `status_message`
            # finds nothing, because the slot is `_show_status_message`.
            receiver = ast.unparse(func.value)
            if not receiver.endswith(".status_message"):
                continue
            found[receiver[: -len(".status_message")]] = ast.unparse(node.args[0])
        return found

    def test_the_canvas_status_message_is_connected_to_the_sink(self) -> None:
        """Receiver AND slot — a receiver wired to nothing is the original P0."""
        found = self._connects()
        assert "self.canvas_view" in found, (
            f"application.py no longer connects CanvasView.status_message, so "
            f"every status message is dropped again. Connected: {sorted(found)}"
        )
        assert found["self.canvas_view"] == "self._show_status_message", (
            f"CanvasView.status_message is wired to "
            f"{found['self.canvas_view']!r} instead of the status-bar sink. A "
            f"connect to a no-op lambda delivers nothing, which is exactly the "
            f"defect this guard was added to prevent."
        )

    def test_the_calendar_status_message_is_connected_to_the_sink(self) -> None:
        found = self._connects()
        assert "self.calendar_view" in found, (
            f"application.py no longer connects PlantingCalendarView.status_message, "
            f"so the propagation-date refusal is dropped again. Connected: "
            f"{sorted(found)}"
        )
        assert found["self.calendar_view"] == "self._show_status_message", (
            f"PlantingCalendarView.status_message is wired to "
            f"{found['self.calendar_view']!r} instead of the status-bar sink."
        )

    @staticmethod
    def _sink_body() -> str:
        """``_show_status_message``'s **statements**, with the docstring removed.

        The earlier version unparsed the whole node, so the docstring's prose
        mentioning ``statusBar().showMessage`` satisfied the assertion and a body
        of ``pass`` passed — round 7 measured it. A docstring is not code.
        """
        tree = ast.parse(TestTheProductionWiringExists._source())
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if node.name != "_show_status_message":
                continue
            statements = list(node.body)
            if (
                statements
                and isinstance(statements[0], ast.Expr)
                and isinstance(statements[0].value, ast.Constant)
                and isinstance(statements[0].value.value, str)
            ):
                statements = statements[1:]              # drop the docstring
            return "\n".join(ast.unparse(s) for s in statements)
        raise AssertionError("_show_status_message no longer exists")

    def test_the_sink_reaches_the_status_bar(self) -> None:
        """The connected receiver must actually call ``statusBar().showMessage``."""
        body = self._sink_body()
        assert "statusBar()" in body, (
            f"the sink's statements do not reach the status bar:\n{body}"
        )
        assert "showMessage" in body, f"the sink does not call showMessage:\n{body}"

    def test_the_sink_is_more_than_a_pass(self) -> None:
        """The exact defect round 7 measured: the body replaced by ``pass``."""
        assert self._sink_body().strip() not in ("pass", ""), (
            "_show_status_message has an empty body, so every status message is "
            "connected to a function that does nothing"
        )


class TestTheStatusRouteIsAlive:
    def test_the_canvas_parent_has_no_status_bar(self, qtbot) -> None:
        """Why the old lookup failed, pinned so it cannot be reintroduced."""
        _win, _splitter, view = _window(qtbot)
        parent = view.parent()
        assert parent is not None
        assert not hasattr(parent, "statusBar"), (
            "the canvas view's parent now has a statusBar, which means the old "
            "parent-lookup route might work again — revisit this test and the "
            "signal deliberately rather than leaving both paths"
        )

    def test_set_status_message_reaches_the_status_bar(self, qtbot) -> None:
        window, _splitter, view = _window(qtbot)
        view.set_status_message("REFUSAL PROBE")
        QApplication.processEvents()
        assert "REFUSAL PROBE" in window.statusBar().currentMessage()

    def test_the_old_parent_lookup_would_have_delivered_nothing(self, qtbot) -> None:
        """The regression itself, stated as a test so it cannot come back."""
        _win, _splitter, view = _window(qtbot)
        delivered = False
        if view.parent() and hasattr(view.parent(), "statusBar"):   # old code path
            view.parent().statusBar().showMessage("REFUSAL PROBE")
            delivered = True
        assert delivered is False, (
            "the parent lookup now resolves — if that is intended, the signal "
            "route and this test should both be revisited deliberately"
        )


class TestTheRefusalMessageReachesTheUser:
    @staticmethod
    def _refuse(qtbot) -> tuple[PlantingCalendarView, QMainWindow]:
        """The calendar tab, with its own status signal routed to a status bar.

        This is what ``application.py`` does: the tab carries the message, the window
        owns the bar. The calendar and the canvas share one ``CanvasScene``, so a
        ``CanvasView`` route was *reachable* — the tab owning its own signal is
        the right design, not a fix for an unreachable one. (Round 6 measured
        the earlier "the scene has no view" claim false.)
        """
        view = _calendar(qtbot)
        window = QMainWindow()
        qtbot.addWidget(window)
        window.statusBar()
        view.status_message.connect(
            lambda message: window.statusBar().showMessage(message)
        )
        return view, window

    def test_an_inverted_pair_puts_a_message_in_the_status_bar(self, qtbot) -> None:
        view, window = self._refuse(qtbot)
        key = next(iter(view._prop_plans))
        idx = next(i for i, r in enumerate(view._rows) if r.species_key == key)
        view._on_row_clicked(idx)
        QApplication.processEvents()

        start_edit, _end, _reset = view._detail._step_rows["indoor_sow"][0:3]
        start_edit.setDate(QDate(2027, 6, 1))     # far past the calculated end
        view._detail._flush_pending_steps()
        QApplication.processEvents()

        message = window.statusBar().currentMessage()
        assert message, (
            "an inverted pair was refused and the user was told nothing — the "
            "field simply snapped back, which reads as the widget resetting "
            "itself rather than as an error"
        )
        assert REFUSAL_PREFIX in message, message

    def test_nothing_is_shown_for_an_accepted_edit(self, qtbot) -> None:
        """A message on every commit would train users to ignore the bar."""
        view, window = self._refuse(qtbot)
        window.statusBar().clearMessage()
        key = next(iter(view._prop_plans))
        idx = next(i for i, r in enumerate(view._rows) if r.species_key == key)
        view._on_row_clicked(idx)
        QApplication.processEvents()

        panel = view._detail
        s, e, _r = panel._step_rows["indoor_sow"][0:3]
        s.setDate(QDate(2026, 5, 4))
        e.setDate(QDate(2026, 5, 20))
        panel._flush_pending_steps()
        QApplication.processEvents()

        assert REFUSAL_PREFIX not in window.statusBar().currentMessage()
        assert view._project_manager.propagation_overrides.get(key, {}).get(
            "indoor_sow"
        ) == {"start": "2026-05-04", "end": "2026-05-20"}


class TestTheSignalCarriesAnyMessage:
    """The route is message-agnostic: whatever a caller passes is delivered.

    Round 6 noted this class name promised coverage of the ~24 repaired callers
    and delivered none - it called `set_status_message` with a literal, which
    is the same hop already covered above with a different string. It is renamed
    to what it tests rather than expanded; the repaired callers are real product
    code paths with their own owners, and their delivery is proven by the route
    plus `TestTheProductionWiringExists`.
    """

    @pytest.mark.parametrize("message", ["Grouped 3 items", "Select 2 or more items to group"])
    def test_any_message_reaches_the_status_bar(self, qtbot, message: str) -> None:
        window, _splitter, view = _window(qtbot)
        view.set_status_message(message)
        QApplication.processEvents()
        assert message in window.statusBar().currentMessage()
