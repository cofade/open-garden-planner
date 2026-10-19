"""US-F4: real scrubber → shared clock → visibility, history and outputs."""

import json
from datetime import date

import pytest
from PyQt6.QtCore import QDate, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QMouseEvent

from open_garden_planner.agent_api.mapping import plan_summary_from_snapshot
from open_garden_planner.agent_api.queries import list_objects
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plan_timeline import month_number
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.plant_lifetime import change_lifetime_date


@pytest.fixture
def win(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    app = GardenPlannerApp()
    monkeypatch.setattr(app, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(app)
    app._sim_clock.set_date(date(2026, 6, 1))
    return app


def plant(win, name, planted=None, removed=None, x=400):
    item = CircleItem(x, 400, 50, object_type=ObjectType.TREE, name=name)
    item.metadata["plant_species"] = {
        "scientific_name": name, "common_name": name,
        "max_height_cm": 800, "max_spread_cm": 600,
    }
    item.metadata["plant_instance"] = {k: v for k, v in (
        ("planting_date", planted), ("removal_date", removed)) if v}
    item.metadata["plant_instance"]["current_height_cm"] = 150
    win.canvas_scene.addItem(item)
    return item


def scrub(win, year, month):
    win._timeline_toolbar._month_slider.setValue(month_number(date(year, month, 1)))


def test_month_scrub_shared_date_growth_and_half_open_visibility(win):
    from open_garden_planner.ui.view3d.snapshot import collect_scene3d_records

    apple = plant(win, "Apple", "2024-04-01")
    lettuce = plant(win, "Lettuce", "2026-05-01", x=700)
    hazel = plant(win, "Hazel", removed="2027-03-01", x=1000)
    bed = RectangleItem(100, 100, 200, 200, object_type=ObjectType.GARDEN_BED)
    win.canvas_scene.addItem(bed)
    win.canvas_scene.refresh_timeline()
    scrub(win, 2025, 6)
    assert win._sim_clock.plan_date == date(2025, 6, 1)
    assert win._sun_toolbar._date_edit.date() == QDate(2025, 6, 1)
    assert apple.isVisible() and hazel.isVisible() and not lettuce.isVisible()
    assert bed.isVisible()
    young = collect_scene3d_records(win.canvas_scene, win._sim_clock.plan_date)
    assert len(young) == 3
    scrub(win, 2027, 3)
    assert not hazel.isVisible() and lettuce.isVisible()
    scrub(win, 2030, 6)
    grown = collect_scene3d_records(win.canvas_scene, win._sim_clock.plan_date)
    # Exact US-E8 growth values are covered by its own tests; this pins routing.
    from open_garden_planner.core.object_height import effective_height_cm

    assert effective_height_cm(apple.object_type, apple.metadata, date(2030, 6, 1)) > effective_height_cm(
        apple.object_type, apple.metadata, date(2025, 6, 1))
    assert len(grown) == 3
    assert "2030-06" in win._timeline_toolbar._month_label.text()


def test_canvas_sprite_regrows_through_real_render_without_resizing_footprint(win):
    from PyQt6.QtGui import QImage, QPainter

    from open_garden_planner.services.scene_rendering import render_scene_region

    item = plant(win, "Apple", "2024-04-01")
    item.set_global_labels_visible(False)
    win.canvas_scene.set_shadows_enabled(False)
    win._spacing_circles_enabled = False
    win.canvas_scene.set_spacing_circles_visible(False)
    footprint = item.rect()

    def painted_pixels():
        image = QImage(400, 400, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        render_scene_region(win.canvas_scene, painter, QRectF(0, 0, 400, 400), QRectF(0, 0, 800, 800))
        painter.end()
        background = win.canvas_scene.CANVAS_COLOR.rgb()
        return sum(image.pixel(x, y) != background for x in range(100, 300) for y in range(100, 300))

    scrub(win, 2025, 6)
    young = painted_pixels()
    scrub(win, 2030, 6)
    assert painted_pixels() > young
    assert item.rect() == footprint


def test_panel_removal_edit_clear_undo_redo_and_roundtrip(win, qtbot, tmp_path):
    item = plant(win, "Apple", "2024-04-01")
    item.setSelected(True)
    panel = win.plant_database_panel
    panel.set_selected_items([item])
    manager = win.canvas_view.command_manager
    before = len(manager._undo_stack)
    panel.removal_date_edit.setDate(QDate(2027, 3, 1))
    assert len(manager._undo_stack) == before + 1
    assert item.metadata["plant_instance"]["removal_date"] == "2027-03-01"
    scrub(win, 2027, 6)
    assert not item.isVisible() and not item.isSelected()
    manager.undo()
    assert item.isVisible()
    manager.redo()
    assert not item.isVisible()
    path = tmp_path / "timeline.ogp"
    win._project_manager.save(win.canvas_scene, path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "as_of_date" not in saved and "agent_meta" not in saved
    assert saved["objects"][0]["metadata"]["plant_instance"]["removal_date"] == "2027-03-01"
    win._load_project_file(str(path))
    loaded = next(i for i in win.canvas_scene.items() if getattr(i, "name", None) == "Apple")
    assert not loaded.isVisible()
    scrub(win, 2026, 6)
    loaded.setSelected(True)
    panel.set_selected_items([loaded])
    panel.clear_removal_button.click()
    assert "removal_date" not in loaded.metadata["plant_instance"]
    assert panel.removal_date_edit.text() == panel.tr("Not removed")
    manager.undo()
    assert loaded.metadata["plant_instance"]["removal_date"] == "2027-03-01"
    qtbot.wait(20)
    assert panel.removal_date_edit.date() == QDate(2027, 3, 1)


def test_hidden_discovery_reveals_date_and_today_preserves_time(win):
    item = plant(win, "Hazel", "2024-04-01", "2027-03-01")
    scrub(win, 2028, 6)
    toolbar = win._timeline_toolbar
    toolbar._populate_hidden()
    action = toolbar._hidden_menu.actions()[0]
    assert "Hazel" in action.text() and "2027-03-01" in action.text()
    action.trigger()
    assert item.isVisible() and item.isSelected()
    assert win._sim_clock.plan_date == date(2027, 2, 28)
    old_time = win._sim_clock.time_of_day
    toolbar._today_button.click()
    assert win._sim_clock.plan_date == date.today()
    assert win._sim_clock.time_of_day == old_time


def test_layer_changes_marquee_and_undo_do_not_resurrect_hidden_plants(win):
    item = plant(win, "Future", "2028-05-01")
    layer = win.canvas_scene.active_layer
    item.layer_id = layer.id
    win.canvas_scene.update_layer_visibility(layer.id, False)
    win.canvas_scene.update_layer_visibility(layer.id, True)
    assert not item.isVisible()
    from open_garden_planner.core.tools.select_tool import SelectTool

    tool = SelectTool(win.canvas_view)
    event = QMouseEvent(QMouseEvent.Type.MouseButtonRelease, QPointF(),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                        Qt.KeyboardModifier.NoModifier)
    tool._select_items_in_box(QRectF(0, 0, 2000, 2000), True, event)
    assert not item.isSelected()
    change_lifetime_date(item, "planting_date", "2024-04-01")
    assert item.isVisible()
    win.canvas_view.command_manager.undo()
    assert not item.isVisible()
    before = len(win.canvas_view.command_manager._undo_stack)
    with pytest.raises(ValueError):
        change_lifetime_date(item, "removal_date", "2020-01-01")
    assert len(win.canvas_view.command_manager._undo_stack) == before
    assert "removal_date" not in item.metadata["plant_instance"]


def test_group_with_only_absent_plants_has_no_selectable_ghost(win):
    from open_garden_planner.ui.canvas.items.group_item import GroupItem

    item = plant(win, "Future", "2028-05-01")
    group = GroupItem()
    win.canvas_scene.addItem(group)
    group.addToGroup(item)
    win.canvas_scene.refresh_timeline()
    assert not item.isVisible() and not group.isVisible()
    group.setSelected(True)
    assert not group.isSelected()
    scrub(win, 2029, 1)
    assert group.isVisible() and item.isVisible()
    scrub(win, 2026, 1)
    assert not group.isVisible() and not item.isVisible()


def test_api_retains_absent_plants_and_names_the_shared_date(win):
    item = plant(win, "Future", "2028-05-01")
    snapshot = win._project_manager.snapshot_dict(win.canvas_scene)
    summary = plan_summary_from_snapshot(snapshot)
    objects = list_objects(snapshot)
    assert summary.as_of_date == "2026-06-01" and summary.plant_count == 1
    assert objects[0].item_id == str(item.item_id)
    assert objects[0].present is False and objects[0].as_of_date == "2026-06-01"


def test_presence_fields_survive_real_mcp_transport(win, qtbot):
    from tests.integration.test_agent_api_lifecycle import _run, _server

    plant(win, "Future", "2028-05-01")
    server = _server(win)

    async def body(ctx):
        http_client, client_session, url = ctx
        async with http_client(url) as (read, write, _), client_session(read, write) as session:
            await session.initialize()
            summary = await session.call_tool("get_plan_summary", {})
            objects = await session.call_tool("list_objects", {})
            assert not summary.isError and not objects.isError
            assert summary.structuredContent["as_of_date"] == "2026-06-01"
            assert objects.structuredContent["result"][0]["present"] is False
            assert objects.structuredContent["result"][0]["as_of_date"] == "2026-06-01"

    try:
        _run(server, body, qtbot)
    finally:
        server.stop()


def test_fresh_gui_and_agent_plants_use_the_active_date(win):
    from open_garden_planner.ui.plant_creation import build_species_plant

    win._sun_toolbar._date_edit.setDate(QDate(2025, 6, 1))
    item = build_species_plant(win.canvas_scene, QPointF(400, 400), {
        "scientific_name": "Malus domestica", "common_name": "Apple"})
    win.canvas_scene.addItem(item)
    assert item.metadata["plant_instance"]["planting_date"] == "2025-06-01"
    assert item.isVisible()
    result = win._do_agent_create_object("TREE", 700, 700, None, None, 50, "Agent tree", None)
    snapshot = win._project_manager.snapshot_dict(win.canvas_scene)
    agent_tree = next(obj for obj in snapshot["objects"] if obj["item_id"] == result["item_id"])
    assert agent_tree["metadata"]["plant_instance"]["planting_date"] == "2025-06-01"
    assert agent_tree["present"]


def test_season_copy_retains_date_absent_plants_when_requested(win, tmp_path):
    plant(win, "Future", "2028-05-01", "2029-03-01")
    annual = CircleItem(700, 400, 30, object_type=ObjectType.PERENNIAL, name="Annual",
                        metadata={"plant_instance": {"planting_date": "2028-05-01"}})
    win.canvas_scene.addItem(annual)
    win._project_manager.save(win.canvas_scene, tmp_path / "2026.ogp")
    win._project_manager.create_new_season(win.canvas_scene, 2027, tmp_path / "2027.ogp", keep_plants=True)
    copied = json.loads((tmp_path / "2027.ogp").read_text(encoding="utf-8"))
    assert copied["season_year"] == 2027
    assert len(copied["objects"]) == 2
    tree = next(obj for obj in copied["objects"] if obj["name"] == "Future")
    assert tree["metadata"]["plant_instance"]["removal_date"] == "2029-03-01"
    win._project_manager.create_new_season(win.canvas_scene, 2028, tmp_path / "2028.ogp", keep_plants=False)
    remaining = json.loads((tmp_path / "2028.ogp").read_text(encoding="utf-8"))["objects"]
    assert [obj["name"] for obj in remaining] == ["Future"]  # woody plants always carry over


def test_spacing_and_companion_use_visible_set(win):
    a = plant(win, "Tomato", "2024-01-01")
    b = plant(win, "Potato", "2028-01-01", x=420)
    a.metadata["plant_species"]["common_name"] = "Tomato"
    b.metadata["plant_species"]["common_name"] = "Potato"
    win._update_spacing_overlaps()
    win._update_companion_highlights()
    assert a._spacing_overlap != "overlap" and not a._antagonist_warning
    scrub(win, 2029, 1)
    assert a._spacing_overlap == "overlap" and a._antagonist_warning
    scrub(win, 2026, 1)
    assert a._spacing_overlap != "overlap" and not a._antagonist_warning


def test_png_svg_dxf_and_pdf_use_current_presence(win, tmp_path):
    import ezdxf
    from PyQt6.QtCore import QSize
    from PyQt6.QtPdf import QPdfDocument

    from open_garden_planner.services.dxf_service import DxfExportService
    from open_garden_planner.services.export_service import ExportService
    from open_garden_planner.services.pdf_report_service import PdfReportOptions, PdfReportService

    visible = plant(win, "Present", "2024-01-01")
    absent = plant(win, "Absent", "2028-01-01", x=1000)
    for item in (visible, absent):
        item.fill_color = QColor("#ff0000")
        item.setBrush(QColor("#ff0000"))
    png, svg, dxf, pdf = (tmp_path / f"view.{ext}" for ext in ("png", "svg", "dxf", "pdf"))
    ExportService.export_to_png(win.canvas_scene, png)
    ExportService.export_to_svg(win.canvas_scene, svg)
    DxfExportService.export(win.canvas_scene, dxf)
    circles = list(ezdxf.readfile(dxf).modelspace().query("CIRCLE"))
    assert len(circles) == 1
    assert circles[0].dxf.center.x == 400
    assert png.stat().st_size > 1000 and svg.stat().st_size > 1000
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    png_image = QImage(str(png))
    svg_image = QImage(1000, 600, QImage.Format.Format_RGB32)
    svg_image.fill(Qt.GlobalColor.white)
    painter = QPainter(svg_image)
    QSvgRenderer(str(svg)).render(painter)
    painter.end()
    def pixel_at(image, x, y):
        return image.pixelColor(round(x / win.canvas_scene.width_cm * image.width()),
                                round((1 - y / win.canvas_scene.height_cm) * image.height()))
    for image in (png_image, svg_image):
        assert pixel_at(image, 400, 400) != win.canvas_scene.CANVAS_COLOR
        assert pixel_at(image, 1000, 400) == win.canvas_scene.CANVAS_COLOR
    PdfReportService.generate(win.canvas_scene, PdfReportOptions(), pdf)
    doc = QPdfDocument(None)
    assert doc.load(str(pdf)) == QPdfDocument.Error.None_
    text = "\n".join(doc.getAllText(i).text() for i in range(doc.pageCount()))
    # PDF text selection may place line breaks between glyphs, despite correct
    # visual layout (also rendered below). Normalize whitespace only.
    text = "".join(text.split())
    assert "Planasof2026-06-01" in text and "Present" in text and "Absent" not in text
    assert not doc.render(0, QSize(500, 400)).isNull()
    doc.close()
    assert visible.isVisible() and not absent.isVisible()


def test_explicit_api_layer_render_cannot_resurrect_a_date_absent_plant(win):
    from open_garden_planner.agent_api.render import _hidden_layers_not_in

    item = plant(win, "Future", "2028-05-01")
    item.layer_id = win.canvas_scene.active_layer.id
    layer_id = str(item.layer_id)
    with _hidden_layers_not_in(win.canvas_scene, [layer_id]):
        assert not item.isVisible()
    assert not item.isVisible()
