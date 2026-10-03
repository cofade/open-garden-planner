"""Integration test: crop-rotation panel shows a succession plan (issue #378).

End-to-end: a real ``ProjectManager`` carries a succession plan for a real bed,
the panel is pointed at that bed, and the plan appears as a separate
"planned this season" section — while ``CropRotationService`` advice is
unchanged. This is the GUI-visible half of the `suggest_succession` exclusions
that US-D3.2's manual pass surfaced.
"""

from __future__ import annotations

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.crop_rotation_service import CropRotationService
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.panels.crop_rotation_panel import CropRotationPanel


def _plan(bed_id: str, species_key: str, common_name: str, scientific: str) -> dict:
    return {
        "bed_id": bed_id,
        "year": 2026,
        "entries": [
            {
                "id": "e1",
                "species_key": species_key,
                "common_name": common_name,
                "scientific_name": scientific,
                "start_date": "2026-04-01",
                "end_date": "2026-06-15",
            }
        ],
    }


def test_panel_shows_plan_through_real_project_manager(qtbot: object) -> None:
    scene = CanvasScene(width_cm=2000, height_cm=1500)
    bed = RectangleItem(100, 100, 300, 200, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    bed_id = str(bed.item_id)

    pm = ProjectManager()
    tomato_key = "solanum lycopersicum"
    pm.set_succession_plan(bed_id, _plan(bed_id, tomato_key, "Tomato", "Solanum lycopersicum"))

    service = CropRotationService()
    before = service.get_recommendation(bed_id)

    panel = CropRotationPanel(service)
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel.set_project_manager(pm)
    panel.update_for_bed(bed, bed_id)

    # The plan is visible as its own section, clearly not history.
    assert panel._plan_header.isVisibleTo(panel)
    assert panel._plan_list.count() == 1
    assert "tomato" in panel._plan_list.item(0).text().lower()
    assert "solanaceae" in panel._plan_list.item(0).text().lower()

    # The explicit gap message replaced the bare "any crop is suitable".
    assert "planned crops" in panel._recommendation_label.text().lower()

    # Advice is byte-for-byte unchanged: the plan is NOT fed into the service.
    after = service.get_recommendation(bed_id)
    assert after.status == before.status
    assert after.suggested_demand == before.suggested_demand
    assert after.avoid_families == before.avoid_families


def test_panel_clears_plan_when_bed_changes(qtbot: object) -> None:
    scene = CanvasScene(width_cm=2000, height_cm=1500)
    bed_a = RectangleItem(100, 100, 300, 200, object_type=ObjectType.RAISED_BED)
    bed_b = RectangleItem(600, 100, 300, 200, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed_a)
    scene.addItem(bed_b)
    bed_a_id = str(bed_a.item_id)

    pm = ProjectManager()
    pm.set_succession_plan(
        bed_a_id,
        _plan(bed_a_id, "solanum lycopersicum", "Tomato", "Solanum lycopersicum"),
    )

    panel = CropRotationPanel(CropRotationService())
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel.set_project_manager(pm)

    panel.update_for_bed(bed_a, bed_a_id)
    assert panel._plan_header.isVisibleTo(panel)

    panel.update_for_bed(bed_b, str(bed_b.item_id))
    assert not panel._plan_header.isVisibleTo(panel)


def test_plan_change_signal_refreshes_panel(qtbot: object) -> None:
    scene = CanvasScene(width_cm=2000, height_cm=1500)
    bed = RectangleItem(100, 100, 300, 200, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    bed_id = str(bed.item_id)

    pm = ProjectManager()
    panel = CropRotationPanel(CropRotationService())
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel.set_project_manager(pm)
    panel.update_for_bed(bed, bed_id)
    assert not panel._plan_header.isVisibleTo(panel)

    # Writing through the real manager emits succession_plans_changed.
    pm.set_succession_plan(
        bed_id, _plan(bed_id, "solanum lycopersicum", "Tomato", "Solanum lycopersicum")
    )

    assert panel._plan_header.isVisibleTo(panel)
    assert panel._plan_list.count() == 1
