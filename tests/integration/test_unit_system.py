"""One plan, one live preference switch, unchanged saved geometry (#673)."""

import json

from PyQt6.QtWidgets import QGraphicsSimpleTextItem

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.config.settings import get_settings
from open_garden_planner.core.constraints import AnchorRef
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import FILE_VERSION
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.widgets.unit_spin_box import LengthSpinBox


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
    bed.setSelected(True)
    window.update_coordinates(30.48, 60.96)
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
