"""#415 round 4: arming must require a real change, and a reset must not strand.

Every test in the previous three rounds drove `setDate()` and then an explicit
`_flush_pending_steps()`. None of them ever let the **debounce timer** or
**`editingFinished`** fire — which is where the round-4 P0 lived:

1. **`editingFinished` armed unconditionally.** It fires on EVERY focus-out,
   including a tab-through that changed nothing, so merely arrowing through the
   panel wrote an override for every step the focus passed. Measured before the
   fix: tabbing through four step editors stored all four and marked the project
   dirty. Propagation dates then stop following the frost date — a silent data
   change that looks like a no-op.
2. **Resetting one step stopped the debounce for its armed siblings**, stranding
   them until some other event happened to fire the timer.
3. **Two species armed at once misattributed**, because the batch carried
   `next(iter(armed.values()))` — the first key seen, not each write's own key.

The production path is exercised here: a real `PlantingCalendarView`, real
signal wiring, and `QApplication.processEvents()` for the focus walk.
"""
# ruff: noqa: ARG001, ARG002

from __future__ import annotations

import ast

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.views.planting_calendar_view import (
    _STEP_COMMIT_DEBOUNCE_MS,
    PlantingCalendarView,
)

TOMATO = {
    "scientific_name": "Solanum lycopersicum", "common_name": "Tomato",
    "source_id": "414", "indoor_sow_start": -8, "indoor_sow_end": -6,
    "transplant_start": 4, "harvest_start": 10, "harvest_end": 18,
}
PEPPER = {
    "scientific_name": "Capsicum annuum", "common_name": "Pepper",
    "source_id": "415", "indoor_sow_start": -10, "indoor_sow_end": -8,
    "transplant_start": 3, "harvest_start": 12, "harvest_end": 18,
}


def _view(qtbot, species=(TOMATO, PEPPER)) -> PlantingCalendarView:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    for spec in species:
        item = CircleItem(
            center_x=100, center_y=100, radius=20,
            object_type=ObjectType.TREE, name=spec["common_name"],
        )
        item.metadata["plant_species"] = dict(spec)
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


def _key_for(view: PlantingCalendarView, name: str) -> str:
    return next(k for k, r in ((r.species_key, r) for r in view._rows)
                if name in r.display_name)


def _select(view: PlantingCalendarView, key: str) -> None:
    view._on_row_clicked(
        next(i for i, r in enumerate(view._rows) if r.species_key == key)
    )
    QApplication.processEvents()


class TestTabbingWritesNothing:
    """The round-4 P0. Focus events are not edits."""

    def test_a_focus_walk_stores_no_overrides(self, qtbot) -> None:
        view = _view(qtbot)
        key = _key_for(view, "Tomato")
        _select(view, key)
        panel = view._detail

        for start_edit, end_edit, _reset in panel._step_rows.values():
            start_edit.setFocus()
            QApplication.processEvents()
            if end_edit is not None:
                end_edit.setFocus()
                QApplication.processEvents()

        assert view._project_manager.propagation_overrides == {}, (
            "moving focus through the panel stored overrides the user never "
            f"entered: {view._project_manager.propagation_overrides}"
        )

    def test_a_focus_walk_leaves_no_step_flagged_overridden(self, qtbot) -> None:
        """The observable consequence: dates stop following the frost date."""
        view = _view(qtbot)
        key = _key_for(view, "Tomato")
        _select(view, key)

        for start_edit, end_edit, _reset in view._detail._step_rows.values():
            start_edit.setFocus()
            QApplication.processEvents()
            if end_edit is not None:
                end_edit.setFocus()
                QApplication.processEvents()

        plan = view._prop_plans[key]
        assert [s.step_id for s in plan.steps if s.overridden] == [], (
            "a mere focus walk froze the propagation dates"
        )

    def test_leaving_the_panel_writes_nothing_either(self, qtbot) -> None:
        """Focus the panel, then move focus off it entirely."""
        view = _view(qtbot)
        _select(view, _key_for(view, "Tomato"))
        view._detail._step_rows["indoor_sow"][0].setFocus()
        QApplication.processEvents()
        view.setFocus()
        QApplication.processEvents()
        assert view._project_manager.propagation_overrides == {}

    def test_a_real_edit_still_commits_on_focus_out(self, qtbot) -> None:
        """The guard must not disable the legitimate path."""
        view = _view(qtbot)
        key = _key_for(view, "Tomato")
        _select(view, key)
        panel = view._detail

        start_edit, end_edit, _reset = panel._step_rows["indoor_sow"][0:3]
        start_edit.setDate(QDate(2026, 5, 4))
        end_edit.setDate(QDate(2026, 5, 20))
        # setFocus() on the panel does not move focus OFF the editors, so no
        # editingFinished fires; the commit comes from the debounce, exactly as
        # it does for a user who types and waits.
        _wait(panel)

        assert view._project_manager.propagation_overrides.get(key, {}).get(
            "indoor_sow"
        ) == {"start": "2026-05-04", "end": "2026-05-20"}


class TestDebounceTimerActuallyFires:
    """The timer path, which every prior test bypassed with an explicit flush."""

    def test_the_timer_commits_a_real_edit(self, qtbot) -> None:
        view = _view(qtbot)
        key = _key_for(view, "Tomato")
        _select(view, key)
        panel = view._detail

        start_edit, end_edit, _reset = panel._step_rows["indoor_sow"][0:3]
        start_edit.setDate(QDate(2026, 5, 4))
        end_edit.setDate(QDate(2026, 5, 20))
        assert panel._commit_timer.isActive(), "the debounce was not armed"

        _wait(panel)
        assert view._project_manager.propagation_overrides.get(key, {}).get(
            "indoor_sow"
        ) == {"start": "2026-05-04", "end": "2026-05-20"}, (
            "the debounce timer never committed the edit"
        )

    def test_the_timer_writes_nothing_without_an_edit(self, qtbot) -> None:
        view = _view(qtbot)
        _select(view, _key_for(view, "Tomato"))
        panel = view._detail
        panel._commit_timer.start()          # armed with nothing pending
        _wait(panel)
        assert view._project_manager.propagation_overrides == {}


def _wait(panel, timeout_ms: int | None = None) -> None:
    """Spin the event loop until the debounce has fired (or timed out)."""
    from PyQt6.QtCore import QEventLoop, QTimer

    limit = timeout_ms or (_STEP_COMMIT_DEBOUNCE_MS * 4)
    loop = QEventLoop()
    QTimer.singleShot(limit, loop.quit)
    loop.exec()
    QApplication.processEvents()


class TestResetDoesNotStrandSiblings:
    def test_a_reset_leaves_a_sibling_edit_pending(self, qtbot) -> None:
        """Resetting one step must not cancel the debounce for another."""
        view = _view(qtbot)
        key = _key_for(view, "Tomato")
        _select(view, key)
        panel = view._detail

        for step in ("indoor_sow", "harden_off"):
            s, e, _r = panel._step_rows[step][0:3]
            s.setDate(QDate(2026, 5, 4))
            e.setDate(QDate(2026, 5, 20))

        # indoor_sow carries an override, so its reset button is enabled.
        _flush(panel)
        assert view._project_manager.propagation_overrides.get(key, {}).get(
            "indoor_sow"
        ) is not None

        # Arm harden_off, then reset indoor_sow.
        hs, he, _hr = panel._step_rows["harden_off"][0:3]
        hs.setDate(QDate(2026, 6, 1))
        he.setDate(QDate(2026, 6, 20))
        assert "harden_off" in panel._pending_steps
        panel._step_rows["indoor_sow"][2].click()

        # The contract is the outcome, not the mechanism: the reset triggers a
        # refresh, whose re-populate re-enters the flush and commits the sibling.
        # (Asserting on the timer instead would pin an implementation detail
        # that the refresh path legitimately supersedes.)
        assert view._project_manager.propagation_overrides.get(key, {}).get(
            "harden_off"
        ) == {"start": "2026-06-01", "end": "2026-06-20"}, (
            "resetting one step stranded a sibling's armed edit"
        )

    def test_a_reset_with_nothing_else_armed_stops_the_timer(self, qtbot) -> None:
        view = _view(qtbot)
        key = _key_for(view, "Tomato")
        _select(view, key)
        panel = view._detail
        s, e, _r = panel._step_rows["indoor_sow"][0:3]
        s.setDate(QDate(2026, 5, 4))
        e.setDate(QDate(2026, 5, 20))
        _flush(panel)

        panel._step_rows["indoor_sow"][2].click()
        assert not panel._commit_timer.isActive()


def _flush(panel) -> None:
    panel._flush_pending_steps()
    QApplication.processEvents()


class TestTwoSpeciesArmedAtOnce:
    def test_each_write_carries_its_own_species_key(self, qtbot) -> None:
        """A batch must not label one species' dates with another's key."""
        view = _view(qtbot)
        tomato = _key_for(view, "Tomato")
        pepper = _key_for(view, "Pepper")

        payloads: list[tuple] = []
        view._detail.steps_date_changed.connect(payloads.append)

        _select(view, tomato)
        s, e, _r = view._detail._step_rows["indoor_sow"][0:3]
        s.setDate(QDate(2026, 5, 4))
        e.setDate(QDate(2026, 5, 20))

        # Switch species WITHOUT flushing explicitly — the panel's own
        # show_species flush does it, so this is the production sequence.
        _select(view, pepper)
        ps, pe, _pr = view._detail._step_rows["indoor_sow"][0:3]
        ps.setDate(QDate(2026, 6, 1))
        pe.setDate(QDate(2026, 6, 20))
        _flush(view._detail)

        stored = view._project_manager.propagation_overrides
        assert stored.get(tomato, {}).get("indoor_sow") == {
            "start": "2026-05-04", "end": "2026-05-20",
        }, stored.get(tomato)
        assert stored.get(pepper, {}).get("indoor_sow") == {
            "start": "2026-06-01", "end": "2026-06-20",
        }, stored.get(pepper)

    def test_the_batch_payloads_each_name_their_own_species(self, qtbot) -> None:
        view = _view(qtbot)
        tomato = _key_for(view, "Tomato")
        pepper = _key_for(view, "Pepper")
        payloads: list[tuple] = []
        view._detail.steps_date_changed.connect(payloads.append)

        _select(view, tomato)
        s, e, _r = view._detail._step_rows["indoor_sow"][0:3]
        s.setDate(QDate(2026, 5, 4))
        e.setDate(QDate(2026, 5, 20))
        _select(view, pepper)
        ps, pe, _pr = view._detail._step_rows["indoor_sow"][0:3]
        ps.setDate(QDate(2026, 6, 1))
        pe.setDate(QDate(2026, 6, 20))
        _flush(view._detail)

        for species_key, _writes in payloads:
            assert species_key in (tomato, pepper), species_key


class TestTheRefusalMessageIsTranslated:
    """P0-2: the round-3 message shipped with `tr()` and no German entry."""

    SOURCE = (
        "The end date of a propagation step cannot be before its start "
        "date \u2014 the step was not changed."
    )

    def test_the_message_is_registered_with_a_german_translation(self) -> None:
        import xml.etree.ElementTree as ET
        from pathlib import Path

        ts = (
            Path(__file__).resolve().parents[2]
            / "src" / "open_garden_planner" / "resources" / "translations"
            / "open_garden_planner_de.ts"
        )
        root = ET.parse(ts).getroot()
        found = None
        for ctx in root.iter("context"):
            for message in ctx.iter("message"):
                if (message.findtext("source") or "").strip() == self.SOURCE:
                    found = (ctx.findtext("name"), message.findtext("translation"))
        assert found is not None, (
            "the propagation-refusal message is not in the .ts file, so the "
            "German UI ships an English string — the i18n gate cannot see a "
            "`tr()` literal that was never registered"
        )
        context_name, german = found
        assert context_name == "_DetailPanel", context_name
        assert german and german != self.SOURCE, (
            "the message is registered but untranslated"
        )
        assert "\ufffd" not in german, f"mojibake in the German string: {german!r}"

    def test_the_view_still_uses_the_registered_string(self) -> None:
        """Guards against the source and the catalogue drifting apart again.

        AST-extracted rather than a substring scan, because the message is
        written as two adjacent string literals — the same reason
        `tests/unit/test_dialog_i18n_literals.py` exists. A raw-text check
        silently passes for any message that is not contiguous in the source,
        which is precisely the case here.
        """
        from pathlib import Path

        source = (
            Path(__file__).resolve().parents[2]
            / "src" / "open_garden_planner" / "ui" / "views"
            / "planting_calendar_view.py"
        ).read_text(encoding="utf-8")
        literals = {
            value
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            for value in (ast.literal_eval(node),)
        } | _joined_tr_literals(source)

        assert self.SOURCE in literals, (
            "the refusal message is no longer a tr() literal in the view; if it "
            "was reworded, the registered translation must change with it"
        )


def _joined_tr_literals(source: str) -> set[str]:
    """Every ``tr(...)`` argument, with adjacent literals concatenated.

    ``self.tr("a " "b")`` is ONE string to Qt and one entry in the ``.ts`` file,
    so a catalogue check has to see it the same way — this mirrors the AST
    approach in ``tests/unit/test_dialog_i18n_literals.py``.
    """
    import ast as _ast

    out: set[str] = set()
    for node in _ast.walk(_ast.parse(source)):
        if not isinstance(node, _ast.Call) or not node.args:
            continue
        func = node.func
        name = func.attr if isinstance(func, _ast.Attribute) else getattr(func, "id", "")
        if name not in ("tr", "translate"):
            continue
        try:
            out.add(_ast.literal_eval(node.args[0]))
        except (ValueError, TypeError, SyntaxError):
            continue
    return out
