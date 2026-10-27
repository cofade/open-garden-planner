"""Read the production workspace's complete rest state for render measurements."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from open_garden_planner.core.scene3d.pick_oracle import PickScene, pick_scene


def workspace_settled(workspace: Any) -> bool:
    """Geometry, ground AND camera-driven forge admissions have finished (#600/#603)."""
    controller = workspace.controller
    if controller is None or controller.dirty or controller.ground_owed:
        return False
    worker = workspace._forge_worker
    return (not workspace.camera.moving and (worker is None or worker.pending_count == 0)
            and not workspace._forge_timer.isActive())


def save_held_oracle(workspace: Any, path: Path) -> dict[str, int]:
    """Export triangles from the sink's actual held parts, independent of engine picks.

    A registry rebuild would silently substitute the v0 plants for forged LODs.
    The CPU oracle keeps its own ray math and poses the admitted meshes itself.
    """
    sync = workspace.controller.sync
    visible = {(part.item_id, part.part_index) for part in workspace.host.engine_parts()
               if part.visible and part.has_geometry and part.fade >= 1.0 and part.drawn > 0.0}
    held = {key: tuple(part if (key, index) in visible else replace(part, ground_detail=True, casts_shadow=False)
                       for index, part in enumerate(sync.sink.item(key).parts))
            for key in sync.sink.item_ids()}
    scene = pick_scene(sync.records, lambda record: held[record.item_id])
    np.savez_compressed(path, item_ids=np.asarray(scene.item_ids), corner=scene.corner,
                        edge1=scene.edge1, edge2=scene.edge2, item=scene.item, part=scene.part)
    return {key: sum(part.mesh.triangle_count for part in parts if not part.ground_detail)
            for key, parts in held.items()}


def load_held_oracle(path: Path) -> PickScene:
    with np.load(path, allow_pickle=False) as arrays:
        return PickScene(tuple(str(key) for key in arrays["item_ids"]),
                         *(arrays[key].copy() for key in ("corner", "edge1", "edge2", "item", "part")))


def front_facing_oracle(scene: PickScene, eye: tuple[float, float, float]) -> PickScene:
    """Qt 6.11 picks front faces even when a material renders both sides.

    qssgrenderray.cpp v6.11.0 accepts only positive Moller-Trumbore determinants;
    its back-face branch is commented out. Keep the general two-sided oracle for
    collision/analysis and filter only this engine-specific selection witness.
    A triangle faces a perspective eye iff its normal points toward that eye.
    """
    normals = np.cross(scene.edge1, scene.edge2)
    keep = np.sum(normals * (scene.corner - np.asarray(eye)), axis=1) < 0.0
    return PickScene(scene.item_ids, *(array[keep] for array in (
        scene.corner, scene.edge1, scene.edge2, scene.item, scene.part)))
