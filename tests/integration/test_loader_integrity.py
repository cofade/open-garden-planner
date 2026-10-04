"""Integration tests for loader data integrity (Issue #397, AUD-043, TD-011).

Tests:
1. Missing disk background image loads as placeholder and retains raw dict on re-save.
2. Corrupt base64/bytes background image loads as placeholder and retains raw dict on re-save.
3. Duplicate UUIDs in .ogp are detected and re-minted without losing items.
4. Undecodable items are skipped gracefully and counted in last_load_skipped_items_count.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import (
    BackgroundImageItem,
    CircleItem,
    RectangleItem,
)


def test_missing_background_image_loads_placeholder_and_persists_on_save(
    tmp_path: Path, qtbot: Any
) -> None:
    """Missing disk background image must load as placeholder and not be dropped on re-save (AUD-043)."""
    scene = CanvasScene()
    pm = ProjectManager()

    ogp_data = {
        "version": "1.4",
        "canvas_width": 2000.0,
        "canvas_height": 1500.0,
        "layers": [],
        "objects": [
            {
                "type": "background_image",
                "image_path": "C:/fake/path/does_not_exist_satellite.png",
                "position": {"x": 150.0, "y": 250.0},
                "opacity": 0.75,
                "locked": True,
                "scale_factor": 2.5,
                "geo_metadata": {"source": "test_satellite", "zoom": 19},
            },
            {
                "type": "rectangle",
                "item_id": str(uuid.uuid4()),
                "x": 50.0,
                "y": 50.0,
                "width": 100.0,
                "height": 50.0,
            },
        ],
    }

    plan_file = tmp_path / "missing_bg.ogp"
    plan_file.write_text(json.dumps(ogp_data), encoding="utf-8")

    pm.load(scene, plan_file)

    # Verify background image item is in scene as a placeholder
    bg_items = [it for it in scene.items() if isinstance(it, BackgroundImageItem)]
    assert len(bg_items) == 1
    bg = bg_items[0]
    assert bg.is_placeholder is True
    assert bg.locked is True
    assert bg.opacity == 0.75

    # Re-save to another file
    saved_file = tmp_path / "re_saved.ogp"
    pm.save(scene, saved_file)

    # Check contents of saved file: background image was NOT dropped!
    saved_json = json.loads(saved_file.read_text(encoding="utf-8"))
    saved_bg = [o for o in saved_json["objects"] if o.get("type") == "background_image"]
    assert len(saved_bg) == 1
    assert saved_bg[0]["image_path"] == "C:/fake/path/does_not_exist_satellite.png"
    assert saved_bg[0]["geo_metadata"] == {"source": "test_satellite", "zoom": 19}
    assert saved_bg[0]["scale_factor"] == 2.5


def test_corrupt_background_image_data_loads_placeholder_and_persists(
    tmp_path: Path, qtbot: Any
) -> None:
    """Corrupt embedded background image bytes must load as placeholder and not be dropped (AUD-043)."""
    scene = CanvasScene()
    pm = ProjectManager()

    ogp_data = {
        "version": "1.4",
        "canvas_width": 2000.0,
        "canvas_height": 1500.0,
        "layers": [],
        "objects": [
            {
                "type": "background_image",
                "image_data": "not-valid-base64-corrupt-data",
                "position": {"x": 100.0, "y": 100.0},
                "opacity": 0.5,
                "locked": False,
                "scale_factor": 1.0,
            }
        ],
    }

    plan_file = tmp_path / "corrupt_bg.ogp"
    plan_file.write_text(json.dumps(ogp_data), encoding="utf-8")

    pm.load(scene, plan_file)

    bg_items = [it for it in scene.items() if isinstance(it, BackgroundImageItem)]
    assert len(bg_items) == 1
    bg = bg_items[0]
    assert bg.is_placeholder is True

    # Re-save
    saved_file = tmp_path / "re_saved_corrupt.ogp"
    pm.save(scene, saved_file)

    saved_json = json.loads(saved_file.read_text(encoding="utf-8"))
    saved_bg = [o for o in saved_json["objects"] if o.get("type") == "background_image"]
    assert len(saved_bg) == 1
    assert saved_bg[0]["image_data"] == "not-valid-base64-corrupt-data"


def test_duplicate_uuid_detected_and_reminted(tmp_path: Path, qtbot: Any) -> None:
    """Duplicate UUIDs in an .ogp file must be re-minted to ensure every item has a unique UUID (AUD-043)."""
    scene = CanvasScene()
    pm = ProjectManager()

    shared_uuid = str(uuid.uuid4())
    ogp_data = {
        "version": "1.4",
        "canvas_width": 2000.0,
        "canvas_height": 1500.0,
        "layers": [],
        "objects": [
            {
                "type": "rectangle",
                "item_id": shared_uuid,
                "x": 0.0,
                "y": 0.0,
                "width": 100.0,
                "height": 50.0,
                "name": "Rect1",
            },
            {
                "type": "rectangle",
                "item_id": shared_uuid,  # Collision!
                "x": 200.0,
                "y": 200.0,
                "width": 100.0,
                "height": 50.0,
                "name": "Rect2",
            },
        ],
    }

    plan_file = tmp_path / "dup_uuid.ogp"
    plan_file.write_text(json.dumps(ogp_data), encoding="utf-8")

    pm.load(scene, plan_file)

    rects = [it for it in scene.items() if isinstance(it, RectangleItem)]
    assert len(rects) == 2
    id1, id2 = rects[0].item_id, rects[1].item_id

    # The IDs must now be distinct
    assert id1 != id2
    # At least one must equal the original shared_uuid
    assert str(id1) == shared_uuid or str(id2) == shared_uuid


def test_undecodable_item_skipped_gracefully_and_counted(
    tmp_path: Path, qtbot: Any
) -> None:
    """Undecodable items must be skipped without crashing, with count reflected in last_load_skipped_items_count."""
    scene = CanvasScene()
    pm = ProjectManager()

    ogp_data = {
        "version": "1.4",
        "canvas_width": 2000.0,
        "canvas_height": 1500.0,
        "layers": [],
        "objects": [
            {
                "type": "rectangle",
                "item_id": str(uuid.uuid4()),
                "x": 10.0,
                "y": 10.0,
                "width": 80.0,
                "height": 40.0,
            },
            {
                "type": "unknown_future_unrecognized_geometry_widget",
                "item_id": str(uuid.uuid4()),
                "data": "xyz",
            },
            {
                "type": "circle",
                "item_id": str(uuid.uuid4()),
                "center_x": 100.0,
                "center_y": 100.0,
                "radius": 25.0,
            },
        ],
    }

    plan_file = tmp_path / "undecodable.ogp"
    plan_file.write_text(json.dumps(ogp_data), encoding="utf-8")

    pm.load(scene, plan_file)

    # Valid items loaded successfully
    assert len([it for it in scene.items() if isinstance(it, RectangleItem)]) == 1
    assert len([it for it in scene.items() if isinstance(it, CircleItem)]) == 1
    # Exactly 1 item was skipped
    assert pm.last_load_skipped_items_count == 1


def test_placeholder_background_image_geo_scale_not_applied(
    tmp_path: Path, qtbot: Any
) -> None:
    """Placeholder background image must not be scaled by geo-referencing scale factor (FIND-02)."""
    scene = CanvasScene()
    pm = ProjectManager()

    ogp_data = {
        "version": "1.4",
        "objects": [
            {
                "type": "background_image",
                "image_path": "C:/fake/missing_satellite.png",
                "position": {"x": 0.0, "y": 0.0},
                "geo_metadata": {"meters_per_pixel": 0.0005},
            }
        ],
    }
    plan_file = tmp_path / "placeholder_scale.ogp"
    plan_file.write_text(json.dumps(ogp_data), encoding="utf-8")

    pm.load(scene, plan_file)

    bg_items = [it for it in scene.items() if isinstance(it, BackgroundImageItem)]
    assert len(bg_items) == 1
    bg = bg_items[0]
    assert bg.is_placeholder is True
    # Crucial check: Scale must remain 1.0, not distorted by meters_per_pixel (FIND-02)
    assert bg.scale() == 1.0


def test_recursive_group_duplicate_uuid_and_relink(
    tmp_path: Path, qtbot: Any
) -> None:
    """Duplicate UUID inside GroupItem is deduplicated and parent_bed_id / child_item_ids relinked (FIND-03)."""
    scene = CanvasScene()
    pm = ProjectManager()

    bed_uuid = str(uuid.uuid4())
    plant_uuid = str(uuid.uuid4())
    dup_group_uuid = bed_uuid  # Collision with top-level bed!

    ogp_data = {
        "version": "1.4",
        "objects": [
            {
                "type": "rectangle",
                "item_id": bed_uuid,
                "x": 0.0,
                "y": 0.0,
                "width": 200.0,
                "height": 100.0,
                "name": "MainBed",
                "child_item_ids": [plant_uuid],
            },
            {
                "type": "circle",
                "item_id": plant_uuid,
                "center_x": 50.0,
                "center_y": 50.0,
                "radius": 20.0,
                "parent_bed_id": bed_uuid,
                "name": "BedPlant",
            },
            {
                "type": "group",
                "item_id": str(uuid.uuid4()),
                "name": "TestGroup",
                "x": 300.0,
                "y": 300.0,
                "children": [
                    {
                        "type": "rectangle",
                        "item_id": dup_group_uuid,  # Collision!
                        "x": 0.0,
                        "y": 0.0,
                        "width": 50.0,
                        "height": 50.0,
                        "name": "GroupChild",
                    }
                ],
            },
        ],
        "constraints": [
            {
                "constraint_id": str(uuid.uuid4()),
                "constraint_type": "DISTANCE",
                "target_distance": 150.0,
                "anchor_a": {
                    "item_id": bed_uuid,
                    "anchor_type": "CENTER",
                    "anchor_index": 0,
                },
                "anchor_b": {
                    "item_id": plant_uuid,
                    "anchor_type": "CENTER",
                    "anchor_index": 0,
                },
            }
        ],
    }

    plan_file = tmp_path / "group_dup.ogp"
    plan_file.write_text(json.dumps(ogp_data), encoding="utf-8")

    pm.load(scene, plan_file)

    # Verify all items loaded
    all_items = scene.items()
    assert len(all_items) >= 3

    # Check top-level bed and child plant
    bed = next(it for it in all_items if getattr(it, "name", "") == "MainBed")
    plant = next(it for it in all_items if getattr(it, "name", "") == "BedPlant")

    # UUIDs must all be distinct
    from open_garden_planner.ui.canvas.items.group_item import GroupItem
    group = next(it for it in all_items if isinstance(it, GroupItem))
    group_child = group.childItems()[0]

    assert bed.item_id != group_child.item_id
    # Parent/child relationship was preserved
    assert plant.parent_bed_id == bed.item_id
    assert bed.child_item_ids == [plant.item_id] or bed.child_item_ids == {plant.item_id}
