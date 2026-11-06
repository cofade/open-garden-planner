"""Read the production workspace's complete rest state for render measurements."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

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
    Each triangle also carries whether its part's material draws both sides
    (``materials.TWO_SIDED_KINDS`` / ``two_sided_kinds``): what Qt 6.12's cull-aware pick needs.
    """
    from open_garden_planner.core.scene3d.materials import two_sided_kinds

    sync = workspace.controller.sync
    cutaway = bool(getattr(workspace.controller, "roofs_hidden", False))
    active_two_sided = two_sided_kinds(cutaway=cutaway)
    visible = {(part.item_id, part.part_index) for part in workspace.host.engine_parts()
               if part.visible and part.has_geometry and part.fade >= 1.0 and part.drawn > 0.0}
    held = {key: tuple(part if (key, index) in visible else replace(part, ground_detail=True, casts_shadow=False)
                       for index, part in enumerate(sync.sink.item(key).parts))
            for key in sync.sink.item_ids()}
    scene = pick_scene(sync.records, lambda record: held[record.item_id])
    two_sided = np.fromiter(
        (held[scene.item_ids[item]][part].material_kind in active_two_sided
         for item, part in zip(scene.item.tolist(), scene.part.tolist(), strict=True)),
        dtype=bool, count=scene.triangle_count)
    np.savez_compressed(path, item_ids=np.asarray(scene.item_ids), corner=scene.corner,
                        edge1=scene.edge1, edge2=scene.edge2, item=scene.item, part=scene.part,
                        two_sided=two_sided)
    return {key: sum(part.mesh.triangle_count for part in parts if not part.ground_detail)
            for key, parts in held.items()}


def load_held_oracle(path: Path) -> tuple[PickScene, NDArray[np.bool_]]:
    """The held oracle and, per triangle, whether its material draws both sides."""
    with np.load(path, allow_pickle=False) as arrays:
        scene = PickScene(tuple(str(key) for key in arrays["item_ids"]),
                          *(arrays[key].copy() for key in ("corner", "edge1", "edge2", "item", "part")))
        return scene, arrays["two_sided"].copy()


def engine_pick_oracle(scene: PickScene, two_sided: NDArray[np.bool_],
                       eye: tuple[float, float, float]) -> PickScene:
    """The triangles Qt 6.12's pick can hit from ``eye``.

    ``qssgrenderray.cpp`` v6.12.0 honours the material's cull mode: a culled
    (``Back``) material is hit on its front faces only, a ``NoCulling`` one on both.
    (v6.11.0 accepted positive Moller-Trumbore determinants alone — front faces of
    every material — so this filter kept front faces only until Phase 17 L7.) Keep
    the general two-sided oracle for collision/analysis and filter only this
    engine-specific selection witness. A triangle faces a perspective eye iff its
    normal points toward that eye.
    """
    normals = np.cross(scene.edge1, scene.edge2)
    front = np.sum(normals * (scene.corner - np.asarray(eye)), axis=1) < 0.0
    keep = front | two_sided
    return PickScene(scene.item_ids, *(array[keep] for array in (
        scene.corner, scene.edge1, scene.edge2, scene.item, scene.part)))
