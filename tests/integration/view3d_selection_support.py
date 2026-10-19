"""The judging half of the selection / walk render tier (Phase 17 L1.8) — not a test module.

What the tests of ``test_view3d_selection_render.py`` judge the engine with — and
nothing of it is the engine's: the pick oracle (``core/scene3d/pick_oracle.py``: a
camera model and a ray caster of our own), the top-down projection
(``shots.top_down_pixel``) and plain pixel arithmetic. The driver imports the few
functions that DEFINE where to click (``named_pick_points``), so that both halves
click the same pixels; what is expected there is computed here alone.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from open_garden_planner.core.scene3d import Record, pose_point, pose_ring
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.core.scene3d.pick_oracle import (
    PickScene,
    cast,
    cast_all,
    perspective_ray,
    pick_scene,
    project,
)
from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot, TopDownShot, top_down_pixel
from tests.integration.quick3d_render_support import (
    DRIVER_TIMEOUT_S,
    QML_SOURCE,
    REPO,
    driver_messages,
    keep_artifacts,
    render_env,
)

DRIVER = Path(__file__).resolve().with_name("view3d_selection_driver.py")
PLANT_KINDS = ("TREE", "SHRUB", "PERENNIAL")
#: A view position is judged only when the oracle's answer is the same this far (logical
#: px) around it: a click ON a silhouette edge tests float rounding, not picking.
EDGE_MARGIN_PX = 1.5


def run_selection_driver(out: Path, scenarios: str, *, qml_dir: Path | None = None,
                         env: dict[str, str] | None = None,
                         ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    """``quick3d_render_support.run_driver`` for this story's driver."""
    command = [sys.executable, str(DRIVER), "--out", str(out), "--scenarios", scenarios,
               "--watchdog-s", str(DRIVER_TIMEOUT_S - 60)]
    if qml_dir is not None:
        command += ["--qml-dir", str(qml_dir)]
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        command, env=env if env is not None else render_env(out), capture_output=True, text=True,
        timeout=DRIVER_TIMEOUT_S, cwd=REPO)
    result_file = out / "result.json"
    result = json.loads(result_file.read_text(encoding="utf-8")) if result_file.is_file() else {}
    if result:
        shown = driver_messages(proc.stderr)
        result["qt_messages"] = shown
        result["adapter"] = shown["adapter"]
    keep_artifacts(out, proc)
    return proc, result


# ── the pick oracle, applied ─────────────────────────────────────────────────


def builder_parts(record: Record) -> Sequence[Any]:
    """What the production pipeline builds for a record (a builder that raises builds
    nothing — as ``SceneSync`` shows the item without a solid)."""
    try:
        return _REGISTRY.builder_for(record.kind)(record)
    except Exception:  # noqa: BLE001 - mirrors SceneSync's containment
        return ()


_REGISTRY = production_registry()


def oracle_scene(records: Mapping[str, Record]) -> PickScene:
    return pick_scene(records, builder_parts)


def oracle_answer(scene: PickScene, shot: PerspectiveShot, view: tuple[float, float],
                  x: float, y: float) -> str | None:
    hit = cast(scene, perspective_ray(shot.eye, shot.target, shot.fov_deg, view, x, y))
    return hit.item_id if hit is not None else None


def robust_answer(scene: PickScene, shot: PerspectiveShot, view: tuple[float, float],
                  x: float, y: float, margin: float = EDGE_MARGIN_PX) -> tuple[str | None, bool]:
    """``(the oracle's answer, whether it is the same all round the point)``."""
    answer = oracle_answer(scene, shot, view, x, y)
    for dx, dy in ((margin, margin), (-margin, margin), (margin, -margin), (-margin, -margin),
                   (margin, 0.0), (-margin, 0.0), (0.0, margin), (0.0, -margin)):
        if oracle_answer(scene, shot, view, x + dx, y + dy) != answer:
            return answer, False
    return answer, True


def oracle_chain(scene: PickScene, shot: PerspectiveShot, view: tuple[float, float],
                 x: float, y: float) -> tuple[str, ...]:
    """EVERY item the ray at (x, y) meets, nearest first (``cast_all``)."""
    ray = perspective_ray(shot.eye, shot.target, shot.fov_deg, view, x, y)
    return tuple(hit.item_id for hit in cast_all(scene, ray))


def robust_chain(scene: PickScene, shot: PerspectiveShot, view: tuple[float, float],
                 x: float, y: float, margin: float = EDGE_MARGIN_PX,
                 ) -> tuple[tuple[str, ...], bool]:
    """``(the oracle's chain, whether it is the same all round the point)``."""
    chain = oracle_chain(scene, shot, view, x, y)
    for dx, dy in ((margin, margin), (-margin, margin), (margin, -margin), (-margin, -margin),
                   (margin, 0.0), (-margin, 0.0), (0.0, margin), (0.0, -margin)):
        if oracle_chain(scene, shot, view, x + dx, y + dy) != chain:
            return chain, False
    return chain, True


def in_order(ids: Sequence[str]) -> tuple[str, ...]:
    """``ids`` without repeats, each where it first stands (an item of several parts is
    met several times by one ray)."""
    return tuple(dict.fromkeys(ids))


def broken_qml_copy(folder: Path, file: str, old: str, new: str) -> Path:
    """A copy of the shipped QML directory with ``old`` replaced by ``new`` in ``file``
    — for the controls that show a judge is not deaf."""
    qml = folder / "qml"
    shutil.copytree(QML_SOURCE, qml)
    target = qml / file
    text = target.read_text(encoding="utf-8")
    assert text.count(old) >= 1, f"the control no longer finds {old!r} in {file}"
    target.write_text(text.replace(old, new), encoding="utf-8")
    return qml


def ring_centre(ring: Sequence[Sequence[float]]) -> tuple[float, float]:
    """The area centroid of a simple ring."""
    area = cx = cy = 0.0
    for index, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(index + 1) % len(ring)]
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx / (3.0 * area), cy / (3.0 * area))


def named_pick_points(name: str, records: Mapping[str, Record], shot: PerspectiveShot,
                      view: tuple[float, float] | None = None,
                      ) -> list[tuple[str, tuple[float, float]]]:
    """The view positions gate G1 names, where the plan has them — each computed with
    OUR projection and checked with OUR ray caster, never with the engine:

    - ``plant_on_bed``: a point on a plant that stands on a raised bed or container
      (``base_cm > 0``) — the first such plant the camera sees unobstructed;
    - ``hole``: the middle of a hole of a footprint (the garden inside a closed
      fence), on the ground: whatever the ray meets there — the ground, or what
      stands in the hole — is what must be picked, never the item around it;
    - ``sky``: a position whose ray goes up and meets nothing.
    """
    from tests.integration.view3d_selection_driver import PICK_VIEW

    del name  # the plan's records say what it holds
    size = view if view is not None else (float(PICK_VIEW[0]), float(PICK_VIEW[1]))
    scene = oracle_scene(records)
    points: list[tuple[str, tuple[float, float]]] = []

    def inside(pixel: tuple[float, float] | None) -> bool:
        return (pixel is not None and 6.0 <= pixel[0] <= size[0] - 6.0
                and 6.0 <= pixel[1] <= size[1] - 6.0)

    for item_id, record in records.items():
        if record.kind not in PLANT_KINDS or record.transform.base_cm <= 0.0 or not record.height_cm:
            continue
        east, north = record.transform.east_cm, record.transform.north_cm
        for share in (0.6, 0.4, 0.8, 0.25):
            pixel = project(shot.eye, shot.target, shot.fov_deg, size,
                            (east, north, record.transform.base_cm + share * record.height_cm))
            if inside(pixel) and robust_answer(scene, shot, size, *pixel) == (item_id, True):
                points.append(("plant_on_bed", (round(pixel[0], 2), round(pixel[1], 2))))
                break
        if points:
            break
    for item_id, record in records.items():
        found = False
        for _outer, holes in record.regions:
            for hole in holes:
                centre = ring_centre(hole)
                east, north = pose_point(record.transform, *centre)
                pixel = project(shot.eye, shot.target, shot.fov_deg, size, (east, north, 0.0))
                if not inside(pixel):
                    continue
                answer, robust = robust_answer(scene, shot, size, *pixel)
                if robust and answer != item_id:
                    points.append(("hole", (round(pixel[0], 2), round(pixel[1], 2))))
                    found = True
                    break
            if found:
                break
        if found:
            break
    for column in range(1, 20):
        pixel = (round(size[0] * column / 20.0, 2), 8.0)
        ray = perspective_ray(shot.eye, shot.target, shot.fov_deg, size, *pixel)
        if ray.direction[2] > 0.0 and robust_answer(scene, shot, size, *pixel) == (None, True):
            points.append(("sky", pixel))
            break
    return points


# ── pixels ───────────────────────────────────────────────────────────────────


def image_rgb(image: Any) -> np.ndarray:
    """A ``QImage`` as an (h, w, 3) int array (``quick3d_render_support.load_rgb`` for
    an image that is not a file)."""
    from PyQt6.QtGui import QImage

    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    bits = converted.constBits()
    bits.setsize(converted.sizeInBytes())
    rows = np.frombuffer(bytes(bits), np.uint8).reshape(
        converted.height(), converted.bytesPerLine() // 4, 4)
    return rows[:, :converted.width(), :3].astype(np.int64)


def marker_mask(rgb: np.ndarray) -> np.ndarray:
    """Pixels in the look-through marker's magenta: red AND blue well above green. The
    walls are grey, the ground green or brown, the sky blue with no red above green."""
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (red > green + 60) & (blue > green + 40) & (red > 90)



def ring_mask(rgb: np.ndarray) -> np.ndarray:
    """Pixels in the selection ring's colour: blue well above red and green. The ring
    scenes hold nothing else blue (no water, no sky in a top-down frame)."""
    red, green, blue = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (blue > 110) & (blue > red + 50) & (blue > green + 25)


def outline_pixels(rings: Sequence[Sequence[tuple[float, float]]], step_px: float = 0.5,
                   ) -> np.ndarray:
    """Points every ``step_px`` along closed pixel-space rings, ``(n, 2)``."""
    points: list[tuple[float, float]] = []
    for ring in rings:
        for index, (x1, y1) in enumerate(ring):
            x2, y2 = ring[(index + 1) % len(ring)]
            count = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / step_px))
            points.extend((x1 + (x2 - x1) * k / count, y1 + (y2 - y1) * k / count)
                          for k in range(count))
    return np.array(points, dtype=np.float64).reshape(-1, 2)


def top_down_outline(record: Record, shot: TopDownShot, size: tuple[int, int],
                     dpr: float = 1.0) -> list[list[tuple[float, float]]]:
    """Every outline of ``record`` — outer rings and holes — where OUR top-down
    projection puts it in an image of ``size`` (device pixels)."""
    rings = [ring for outer, holes in record.regions for ring in (outer, *holes)]
    return [[top_down_pixel(x, y, shot, size, dpr) for x, y in pose_ring(record.transform, ring)]
            for ring in rings]


def perspective_outline(record: Record, shot: PerspectiveShot, view: tuple[float, float],
                        height_cm: float, dpr: float = 1.0) -> list[list[tuple[float, float]]]:
    """The same in a perspective frame, with the outline at ``height_cm`` above the
    scene's ground — by ``pick_oracle.project``, our own camera model."""
    out = []
    for outer, holes in record.regions:
        for ring in (outer, *holes):
            pixels = []
            for x, y in pose_ring(record.transform, ring):
                pixel = project(shot.eye, shot.target, shot.fov_deg, view, (x, y, height_cm))
                assert pixel is not None, "the outline is in front of the camera"
                pixels.append((pixel[0] * dpr, pixel[1] * dpr))
            out.append(pixels)
    return out


def distances_to(points: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """For every row of ``points``: the distance to the nearest row of ``targets``."""
    if not len(points):
        return np.zeros(0)
    if not len(targets):
        return np.full(len(points), np.inf)
    best = np.full(len(points), np.inf)
    for start in range(0, len(targets), 2048):
        block = targets[start:start + 2048]
        gap = np.hypot(points[:, None, 0] - block[None, :, 0], points[:, None, 1] - block[None, :, 1])
        best = np.minimum(best, gap.min(axis=1))
    return best


def mask_pixels(mask: np.ndarray) -> np.ndarray:
    """The centres of a mask's pixels, ``(n, 2)`` as (x, y)."""
    rows, columns = np.nonzero(mask)
    return np.stack([columns + 0.5, rows + 0.5], axis=1).astype(np.float64)
