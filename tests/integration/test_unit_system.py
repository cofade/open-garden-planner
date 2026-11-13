"""One plan, one live preference switch, unchanged saved geometry (#673)."""

import json

import pytest
from PyQt6.QtWidgets import QGraphicsSimpleTextItem

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.config.settings import get_settings
from open_garden_planner.core.constraints import AnchorRef
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.widgets.unit_spin_box import LengthSpinBox


@pytest.mark.parametrize(
    ("text", "expected"), [('12 1/2"', 31.75), ("5' 6\"", 167.64), ("30 cm", 30)]
)
@pytest.mark.parametrize("accept", ["return", "blur"])
def test_family_garden_greenhouse_accepts_prefixed_width(
    qtbot, monkeypatch, tmp_path, text, expected, accept
):
    from pathlib import Path

    from PyQt6.QtCore import Qt

    window = GardenPlannerApp()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    window.resize(1500, 950)
    window.show()
    example = (
        Path(__file__).parents[2] / "src/open_garden_planner/resources/examples/family-garden.ogp"
    )
    window._load_project_file(str(example))
    greenhouse = next(
        item
        for item in window.canvas_scene.items()
        if getattr(item, "object_type", None) == ObjectType.GREENHOUSE
    )
    window.canvas_scene.clearSelection()
    greenhouse.setSelected(True)
    get_settings().unit_system = "imperial"
    window._apply_unit_setting()
    qtbot.wait(1)
    width = next(
        box for box in window.properties_panel.findChildren(LengthSpinBox) if box.prefix() == "W: "
    )
    height = next(
        box for box in window.properties_panel.findChildren(LengthSpinBox) if box.prefix() == "H: "
    )
    manager = window.canvas_view.command_manager
    before = len(manager._undo_stack)
    initial_width = greenhouse.rect().width()
    window.activateWindow()
    width.setFocus()
    qtbot.waitUntil(width.hasFocus)
    width.lineEdit().selectAll()
    for index, char in enumerate(text, 1):
        qtbot.keyClicks(width, char)
        assert width.lineEdit().text() == "W: " + text[:index]
    assert greenhouse.rect().width() == initial_width
    assert len(manager._undo_stack) == before
    if accept == "return":
        qtbot.keyClick(width, Qt.Key.Key_Return)
    else:
        qtbot.mouseClick(height, Qt.MouseButton.LeftButton)
    assert greenhouse.rect().width() == pytest.approx(expected)
    assert len(manager._undo_stack) == before + 1
    manager.undo()
    assert greenhouse.rect().width() == initial_width
    manager.redo()
    assert greenhouse.rect().width() == pytest.approx(expected)
    for _ in range(3):
        for system in ("metric", "imperial"):
            get_settings().unit_system = system
            window._apply_unit_setting()
            qtbot.wait(1)
            assert greenhouse.rect().width() == pytest.approx(expected)
            assert len(manager._undo_stack) == before + 1
    path = tmp_path / "greenhouse-width.ogp"
    window._project_manager.save(window.canvas_scene, path)
    window._project_manager.load(window.canvas_scene, path)
    reopened = next(
        item
        for item in window.canvas_scene.items()
        if getattr(item, "object_type", None) == ObjectType.GREENHOUSE
    )
    assert reopened.rect().width() == pytest.approx(expected)


def test_switching_units_updates_every_surface_and_keeps_the_file(qtbot, monkeypatch, tmp_path):
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    scene, view = window.canvas_scene, window.canvas_view
    bed = RectangleItem(100, 100, 243.84, 121.92, object_type=ObjectType.RAISED_BED)
    other = RectangleItem(465.76, 100, 243.84, 121.92)
    for item in (bed, other):
        scene.addItem(item)
    bed.area_label_visible = True
    scene.constraint_graph.add_constraint(
        AnchorRef(bed.item_id, AnchorType.CENTER),
        AnchorRef(other.item_id, AnchorType.CENTER),
        365.76,
    )
    scene.dimension_line_manager.update_all()
    window.constraints_panel.refresh()
    bed.setSelected(True)
    window.update_coordinates(30.48, 60.96)
    initial_zoom = view._zoom_factor
    metric = (
        window.coord_label.text(),
        bed._area_label_item.text(),
        view._format_distance(view._pick_scale_bar_distance()),
    )
    original = window._project_manager.snapshot_dict(scene)

    get_settings().unit_system = "imperial"
    window._apply_unit_setting()
    qtbot.wait(1)
    assert "'" in window.coord_label.text()
    assert "ft²" in bed._area_label_item.text()
    assert any(
        i.text() == "12' 0\"" for i in scene.items() if isinstance(i, QGraphicsSimpleTextItem)
    )
    assert view._format_distance(view._pick_scale_bar_distance()).endswith((" in", " ft"))
    assert "W: 8' 0\"" in [b.text() for b in window.properties_panel.findChildren(LengthSpinBox)]
    assert view.grid_size == 30.48
    from PyQt6.QtWidgets import QLabel

    constraint_row = window.constraints_panel._list.itemWidget(
        window.constraints_panel._list.item(0)
    )
    assert any("12' 0\"" in label.text() for label in constraint_row.findChildren(QLabel))
    assert window._project_manager.snapshot_dict(scene)["objects"] == original["objects"]
    path = tmp_path / "imperial.ogp"
    window._project_manager.save(scene, path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["version"] == FILE_VERSION

    get_settings().unit_system = "metric"
    window._apply_unit_setting()
    window._project_manager.load(scene, path)
    qtbot.wait(1)
    loaded = window._project_manager.snapshot_dict(scene)
    # Loading a document fits its view. Compare unit text at the same zoom.
    view.set_zoom(initial_zoom)
    geometry_keys = (
        "item_id",
        "type",
        "x",
        "y",
        "width",
        "height",
        "rotation",
        "metadata",
        "area_label_visible",
    )
    assert [{k: obj.get(k) for k in geometry_keys} for obj in loaded["objects"]] == [
        {k: obj.get(k) for k in geometry_keys} for obj in original["objects"]
    ]
    assert loaded["constraints"] == original["constraints"]
    reloaded_bed = next(i for i in scene.items() if getattr(i, "area_label_visible", False))
    assert (
        window.coord_label.text(),
        reloaded_bed._area_label_item.text(),
        view._format_distance(view._pick_scale_bar_distance()),
    ) == metric


def test_switching_units_refreshes_photo_focus_and_tour_rows(canvas, qtbot, tmp_path):
    from open_garden_planner.core.unit_preference import get_unit_preference
    from open_garden_planner.core.units import UnitSystem
    from open_garden_planner.ui.view3d.tour_dialog import TourDialog
    from tests.integration.test_directors_cut import Rig

    rig = Rig(canvas, qtbot, tmp_path)
    rig.open_3d()
    capture = rig.workspace.capture
    capture.set_photo_mode(True)
    capture._blur.setValue(60)
    dialog = TourDialog(capture, rig.workspace)
    qtbot.addWidget(dialog)
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("path"))
    dialog.add_key_button.click()
    keys, camera, photo = tuple(dialog._keys), rig.workspace._camera_now(), capture.settings
    before = capture._focus_label.text(), dialog.keys_list.item(0).text()
    get_unit_preference().set_system(UnitSystem.IMPERIAL)
    qtbot.wait(1)
    assert capture._focus_label.text() != before[0]
    assert dialog.keys_list.item(0).text() != before[1]
    assert tuple(dialog._keys) == keys
    assert rig.workspace._camera_now() == camera
    assert capture.settings == photo


@pytest.mark.parametrize("shape", ["rectangle", "polygon", "polyline", "circle"])
def test_retained_vertex_and_measure_labels_refresh_without_edit(canvas, qtbot, shape):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtWidgets import QGraphicsTextItem

    from open_garden_planner.core.tools.base_tool import ToolType
    from open_garden_planner.core.unit_preference import get_unit_preference
    from open_garden_planner.core.units import UnitSystem

    view, scene = canvas, canvas.scene()
    from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, PolylineItem

    points = [QPointF(0, 0), QPointF(243.84, 0), QPointF(243.84, 121.92), QPointF(0, 121.92)]
    item = {
        "rectangle": lambda: RectangleItem(0, 0, 243.84, 121.92),
        "polygon": lambda: PolygonItem(points),
        "polyline": lambda: PolylineItem(points),
        "circle": lambda: CircleItem(300, 300, 121.92),
    }[shape]()
    scene.addItem(item)
    if shape == "circle":
        item.setSelected(True)
    else:
        item.enter_vertex_edit_mode()
    view.set_active_tool(ToolType.MEASURE)
    measure = view._tool_manager.active_tool
    measure._draw_measurement(QPointF(0, 500), QPointF(365.76, 500))
    from open_garden_planner.core import ProjectManager

    project = ProjectManager()
    geometry = project.snapshot_dict(scene)["objects"]
    undo_count = len(view.command_manager._undo_stack)
    get_unit_preference().set_system(UnitSystem.IMPERIAL)
    qtbot.wait(1)
    if shape == "circle":
        labels = [item._center_label, item._diameter_label]
    elif shape == "rectangle":
        labels = [*item._rect_coord_labels, *item._rect_edge_labels]
    else:
        labels = [*item._coord_labels, *item._edge_labels]
    assert any("8' 0\"" in label._text for label in labels)
    assert all("cm" not in label._text and " m" not in label._text for label in labels)
    assert any(
        text.toPlainText() == "12' 0\""
        for text in measure._graphics_items
        if isinstance(text, QGraphicsTextItem)
    )
    assert project.snapshot_dict(scene)["objects"] == geometry
    assert len(view.command_manager._undo_stack) == undo_count
