"""US-F3: explicit worker -> badge/panel/wire, invalidation and canopy workflow."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from PyQt6.QtCore import QLocale, QPointF, Qt, QTimer
from PyQt6.QtWidgets import QApplication

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.i18n import load_translator
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.plant_traits import change_trait
from open_garden_planner.ui.theme import ThemeMode, apply_theme

DAY = date(2026, 6, 21)
REFERENCE = Path(__file__).parents[1] / "fixtures" / "sun_reference_berlin.ogp"


def reference_scene():
    scene = CanvasScene(2400, 2400)
    for name, y, radius, height, kind, layer in [
        ("Reference tree", 1200, 300, 1000, ObjectType.TREE, "canopy"),
        ("Northern tomato", 1300, 30, 180, ObjectType.PERENNIAL, "herbaceous"),
        ("Southern tomato", 400, 30, 180, ObjectType.PERENNIAL, "herbaceous"),
    ]:
        species = {"common_name": "Tomato" if kind != ObjectType.TREE else "Apple",
                   "scientific_name": "Solanum lycopersicum" if kind != ObjectType.TREE else "Malus domestica",
                   "max_spread_cm": radius * 2, "max_height_cm": height,
                   "sun_requirement": "full_sun", "permaculture_layer": layer}
        scene.addItem(CircleItem(1200, y, radius, kind, name=name,
                                metadata={"plant_species": species, "object_height_cm": height}))
    return scene


@pytest.fixture
def sun_app(qtbot, monkeypatch):
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    win._load_project_file(str(REFERENCE))
    win._sim_clock.set_date(DAY)
    yield win
    win._sun_heatmap.shutdown()


def compute(win, qtbot):
    with qtbot.waitSignal(win._sun_heatmap.finished, timeout=30000) as blocker:
        win._on_heatmap_requested()
    assert blocker.args == [True]
    qtbot.waitUntil(lambda: bool(win.sun_exposure_coordinator.evaluations)
                   and any(e.hours is not None for e in win.sun_exposure_coordinator.evaluations.values()))


def by_name(win):
    return {item.name: item for item in win.canvas_scene.items() if hasattr(item, "item_id")}


def sun_records(win, kind="sun_mismatch"):
    return [record for record in win.diagnostics_panel.records if record.kind == kind]


def test_explicit_compute_badges_canopy_invalidation_and_requirements(sun_app, qtbot):
    win = sun_app
    items = by_name(win)
    north, south, tree = items["Northern tomato"], items["Southern tomato"], items["Reference tree"]
    original = (north.rect(), north.pos(), north.transformOriginPoint(), north.boundingRect())
    qtbot.waitUntil(lambda: len(sun_records(win, "sun_evaluation")) == 3)
    assert win._sun_heatmap.run_count == 0
    win._sun_toolbar._june_button.click()
    assert win._sim_clock.plan_date == DAY
    compute(win, qtbot)
    assert win.sun_exposure_coordinator.evaluations[str(north.item_id)].hours == 0
    assert win.sun_exposure_coordinator.evaluations[str(south.item_id)].hours == 16.5
    assert north._sun_badge.isVisible() and not getattr(south, "_sun_badge", None)
    assert str(north.item_id) in {r.details["receiver_id"] for r in sun_records(win)}
    assert str(south.item_id) not in {r.details["receiver_id"] for r in sun_records(win)}
    assert original == (north.rect(), north.pos(), north.transformOriginPoint(), north.boundingRect())
    tree.setSelected(True)
    qtbot.waitUntil(lambda: win.canopy_panel.tree.topLevelItemCount() == 1)
    row = win.canopy_panel.tree.topLevelItem(0).child(0)
    assert row.text(0) == "Northern tomato" and QLocale().toString(0.0, "f", 1) in row.text(1) and DAY.isoformat() in row.text(1)
    win.canopy_panel.select_ids(row.data(0, Qt.ItemDataRole.UserRole))
    qtbot.waitUntil(lambda: north.isSelected())
    run_count = win._sun_heatmap.run_count
    win._sim_clock.set_datetime(win._sim_clock.wall + timedelta(hours=1))
    qtbot.wait(120)
    assert win._sun_heatmap.exposure_reason == "ready"
    assert change_trait(north, "sun_requirement", "full_shade")
    qtbot.waitUntil(lambda: not north._sun_badge.isVisible())
    assert win._sun_heatmap.exposure_reason == "ready" and win._sun_heatmap.run_count == run_count
    win.canvas_view.command_manager.undo()
    qtbot.waitUntil(lambda: north._sun_badge.isVisible())
    tree.setPos(200, 0)
    qtbot.waitUntil(lambda: win._sun_heatmap.exposure_reason == "stale", timeout=1000)
    qtbot.waitUntil(lambda: not sun_records(win) and len(sun_records(win, "sun_evaluation")) == 3, timeout=1000)
    assert not north._sun_badge.isVisible() and win._sun_heatmap.heatmap_visible()
    assert win._sun_heatmap.run_count == run_count
    compute(win, qtbot)
    win._sim_clock.set_date(DAY + timedelta(days=1))
    qtbot.waitUntil(lambda: not win._sun_heatmap.heatmap_visible())
    assert not win._sun_heatmap.receiver_minutes


@pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
def test_badge_group_navigation_geometry_and_reload(sun_app, qtbot, tmp_path, mode):
    win = sun_app
    compute(win, qtbot)
    north = by_name(win)["Northern tomato"]
    apply_theme(QApplication.instance(), mode)
    win.canvas_view.scale(.3, .3)
    north.setRotation(45)
    # Rotating a round receiver about its corner changes its centre: invalid.
    qtbot.waitUntil(lambda: win._sun_heatmap.exposure_reason == "stale")
    north.setRotation(0)
    compute(win, qtbot)
    win.canvas_scene.clearSelection()
    north.setSelected(True)
    by_name(win)["Southern tomato"].setSelected(True)
    win.canvas_view._group_selected()
    qtbot.waitUntil(lambda: bool(sun_records(win)))
    root = north.parentItem()
    win.sun_exposure_coordinator.refresh()
    record = next(r for r in sun_records(win) if r.details["receiver_id"] == str(north.item_id))
    assert record.item_ids == [str(root.item_id)]
    win.diagnostics_panel.select_ids(record.item_ids)
    qtbot.waitUntil(lambda: root.isSelected())
    saved = tmp_path / "saved.ogp"
    win._project_manager.save(win.canvas_scene, saved)
    assert "sun_mismatch" not in saved.read_text(encoding="utf-8")
    win._load_project_file(str(saved))
    assert not win._sun_heatmap.receiver_minutes and not win._sun_heatmap.heatmap_visible()


def test_cached_diagnostics_over_real_unauthenticated_mcp(sun_app, qtbot):
    from tests.integration.test_agent_api_lifecycle import _run, _server
    win = sun_app
    compute(win, qtbot)
    run_count = win._sun_heatmap.run_count
    server = _server(win)
    async def body(ctx):
        http_client, client_session, url = ctx
        async with http_client(url) as (read, write, _), client_session(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_diagnostics", {"kind": "sun_mismatch"})
            assert not result.isError
            assert any(d["details"]["hours"] == 0 and d["details"]["measurement_method"] == "ground_cell_centre_excluding_self"
                       for d in result.structuredContent["result"])
    try:
        _run(server, body, qtbot)
    finally:
        server.stop()
    assert win._sun_heatmap.run_count == run_count


def test_german_names_hints_canopy_and_badge(sun_app, qtbot):
    win = sun_app
    north = by_name(win)["Northern tomato"]
    north.name = ""
    app = QApplication.instance()
    try:
        assert load_translator(app, "de")
        compute(win, qtbot)
        win.sun_exposure_coordinator.refresh()
        assert "Tomate" in north._sun_badge.toolTip() and "Boden" in north._sun_badge.toolTip()
        by_name(win)["Reference tree"].setSelected(True)
        qtbot.waitUntil(lambda: win.canopy_panel.tree.topLevelItemCount() == 1)
        assert win.canopy_panel.tree.topLevelItem(0).child(0).text(0) == "Tomate"
        north.setPos(10, 0)
        qtbot.waitUntil(lambda: any("Nicht bewertet" in win.diagnostics_panel.rows.item(i).text()
                                  for i in range(win.diagnostics_panel.rows.count())))
    finally:
        load_translator(app, "en")


def test_guild_and_sun_records_coexist(sun_app, qtbot, tmp_path):
    from open_garden_planner.core.commands import DeleteItemsCommand
    from open_garden_planner.core.guild_commands import prepare_guild
    from open_garden_planner.services.guild_library import GuildLibrary
    from open_garden_planner.services.species_catalog import offline_catalog

    win = sun_app
    command = prepare_guild(win.canvas_scene, GuildLibrary(user_dir=tmp_path).templates["apple-guild"],
                           offline_catalog(), "Orchard", QPointF(1800, 1800))
    win.canvas_view.command_manager.execute(command)
    win.canvas_view.command_manager.execute(DeleteItemsCommand(win.canvas_scene, [command.items[1]]))
    qtbot.waitUntil(lambda: any(r.kind == "guild_role_missing" for r in win.diagnostics_panel.records))
    assert sun_records(win, "sun_evaluation")
    win.sun_exposure_coordinator.refresh()
    win.guild_coordinator.refresh()
    assert any(r.kind == "guild_role_missing" for r in win.diagnostics_panel.records)
    assert sun_records(win, "sun_evaluation")


@pytest.mark.parametrize("edit", ["height", "spread", "visibility", "delete", "add", "location", "bounds"])
def test_geometry_edits_invalidate_without_recompute(sun_app, qtbot, edit):
    win = sun_app
    compute(win, qtbot)
    tree = by_name(win)["Reference tree"]
    runs = win._sun_heatmap.run_count
    if edit == "height":
        tree.metadata["object_height_cm"] = 900
        tree.update()
    elif edit == "spread":
        tree.metadata["plant_instance"] = {"current_spread_cm": 700}
        tree.update()
    elif edit == "visibility":
        tree.setVisible(False)
    elif edit == "delete":
        win.canvas_scene.removeItem(tree)
    elif edit == "add":
        win.canvas_scene.addItem(CircleItem(300, 300, 50, ObjectType.TREE))
    elif edit == "location":
        win._project_manager.set_location({"latitude": 52.4, "longitude": 13.4})
    else:
        win.canvas_scene._width_cm += 100
        win.canvas_scene.update()
    qtbot.waitUntil(lambda: win._sun_heatmap.exposure_reason == "stale", timeout=1000)
    assert win._sun_heatmap.run_count == runs and not win._sun_heatmap.receiver_minutes


def test_explicit_worker_keeps_gui_responsive(sun_app, qtbot):
    ticks = []
    timer = QTimer(sun_app)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    compute(sun_app, qtbot)
    timer.stop()
    assert len(ticks) >= 3


if __name__ == "__main__":
    app = QApplication([])
    manager = ProjectManager()
    manager.set_location({"latitude": 52.52, "longitude": 13.405, "name": "Berlin"})
    manager.save(reference_scene(), REFERENCE)
