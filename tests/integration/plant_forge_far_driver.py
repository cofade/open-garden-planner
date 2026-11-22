"""Real-engine evidence for #948 and #963: a far crop and a dormant bulb.

A 4.2 m cherry at 45 m is rendered at LOD2 in bloom and at ripeness, once with its
far crop parts and once without; a 50 cm tulip is rendered at LOD0 on 15 April and
15 July against the same frame without the plant. The driver writes ``result.json``
with the pixel counts the test gates and the PNGs beside it.
"""

from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path

import numpy as np


def main(out: Path) -> int:
    from open_garden_planner.core.phenology import evaluate_phenology
    from open_garden_planner.core.plant_art import SpriteRef
    from open_garden_planner.core.plant_forge import LOD0, LOD2, forge_plant
    from open_garden_planner.core.scene3d import GroundSpec, Material, SunState, Transform
    from open_garden_planner.core.scene3d.builders import production_registry
    from open_garden_planner.core.scene3d.sync import SceneSync
    from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
    from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost
    from open_garden_planner.ui.view3d.quick3d.offscreen import ensure_application
    from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot
    from tests.integration.test_plant_forge_workspace import tree

    _app = ensure_application()
    out.mkdir(parents=True, exist_ok=True)
    record = tree("plant")
    host = Quick3DHost((1600, 900))
    sink = Quick3DSink(host)
    scene = SceneSync(sink, production_registry())
    result: dict[str, object] = {}
    try:
        scene.apply({record.item_id: record}, ground=GroundSpec(800.0, 800.0),
                    sun=SunState(elevation_deg=45.0, azimuth_deg=225.0))
        host.set_shot(PerspectiveShot(eye=(0.0, 0.0, 0.0), target=(0.0, 0.0, 1.0)))
        host.show()

        def rgb(image) -> np.ndarray:
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            return np.frombuffer(bits, np.uint8).reshape(image.height(), image.width(), 4)[:, :, :3].astype(np.int16)

        def clear() -> None:
            sink.begin()
            if record.item_id in sink.item_ids():
                sink.remove(record.item_id)
            sink.commit()

        def add(parts, transform: Transform) -> None:
            sink.begin()
            if record.item_id in sink.item_ids():
                sink.remove(record.item_id)
            sink.add(record.item_id, parts, transform, Material("plant"))
            sink.commit()

        def shot(image_name: str, shot: PerspectiveShot) -> np.ndarray:
            host.set_shot(shot)
            assert host.wait_ready(20.0)
            image = host.grab(image_name)
            image.save(str(out / f"{image_name}.png"))
            return rgb(image)

        def plant_pixels(image: np.ndarray, background: np.ndarray) -> int:
            return int((np.abs(image - background).sum(axis=2) > 24).sum())

        def crop_pixels(with_crop: np.ndarray, without: np.ndarray) -> int:
            changed = np.abs(with_crop - without).sum(axis=2) > 24
            red = with_crop[:, :, 0] > with_crop[:, :, 1] + 4
            return int((changed & red).sum())

        cherry = SpriteRef("species", "cherry_tree")
        far = PerspectiveShot(eye=(0.0, -4500.0, 170.0), target=(0.0, 0.0, 210.0), fov_deg=40.0)
        for label, day in (("bloom", datetime.date(2026, 4, 20)),
                           ("fruit", datetime.date(2026, 7, 1))):
            state = evaluate_phenology(cherry, day)
            with_crop = forge_plant(cherry, 420.0, 180.0, seed=7, lod=LOD2, cache=None)
            without = forge_plant(cherry, 420.0, 180.0, seed=7, lod=LOD2, cache=None,
                                  include_accents=False)
            add(with_crop, Transform(0.0, 0.0, 0.0))
            host.set_plant_seasons({record.item_id: state})
            image_with = shot(f"cherry_{label}_with", far)
            add(without, Transform(0.0, 0.0, 0.0))
            host.set_plant_seasons({record.item_id: state})
            image_without = shot(f"cherry_{label}_without", far)
            result[f"cherry_{label}_crop_pixels"] = crop_pixels(image_with, image_without)
            result[f"cherry_{label}_changed_pixels"] = int(
                (np.abs(image_with - image_without).sum(axis=2) > 24).sum())

        tulip = SpriteRef("species", "tulip")
        near = PerspectiveShot(eye=(0.0, -320.0, 55.0), target=(0.0, 0.0, 22.0), fov_deg=40.0)
        clear()                                      # no plant: the background
        host.set_plant_seasons({})
        background = shot("tulip_background", near)
        for label, day in (("april", datetime.date(2026, 4, 15)),
                           ("july", datetime.date(2026, 7, 15))):
            state = evaluate_phenology(tulip, day)
            add(forge_plant(tulip, 50.0, 8.0, seed=7, lod=LOD0, cache=None),
                Transform(0.0, 0.0, 0.0))
            host.set_plant_seasons({record.item_id: state})
            result[f"tulip_{label}_pixels"] = plant_pixels(shot(f"tulip_{label}", near), background)
            result[f"tulip_{label}_leaf_density"] = state.leaf_density
            result[f"tulip_{label}_bloom"] = state.bloom

        result["qt"] = None
        (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    finally:
        host.close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.quiet_windows import keep_windows_behind

    keep_windows_behind()
    raise SystemExit(main(Path(sys.argv[1])))
