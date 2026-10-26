"""Author the three offline example plans and thumbnails through production paths.

Run from the repository root. Layouts are illustrative, not climate prescriptions.
Deterministic IDs and dates keep content reviewable across regenerations.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

os.environ.setdefault("QT_QPA_PLATFORM", "minimal:enable_fonts")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import script_isolation

if __name__ == "__main__":
    script_isolation.isolate_profile()

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.commands import CreateItemsCommand
from open_garden_planner.core.guild_commands import prepare_guild
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plan_io import write_plan
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.templates import template_plan
from open_garden_planner.models.layer import Layer
from open_garden_planner.models.plant_data import PermacultureLayer
from open_garden_planner.models.succession import SuccessionEntry, SuccessionPlan
from open_garden_planner.services.bundled_species_db import get_species_db
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.plant_creation import build_species_plant


def _stable_ids(value, slug, identities=None):
    identities = {} if identities is None else identities
    if isinstance(value, str):
        try:
            UUID(value)
        except ValueError:
            return value
        if value not in identities:
            identities[value] = str(uuid5(NAMESPACE_URL, f"ogp-example/{slug}/{len(identities)}"))
        return identities[value]
    if isinstance(value, dict):
        return {_stable_ids(k, slug, identities): _stable_ids(v, slug, identities)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_stable_ids(v, slug, identities) for v in value]
    return value


def _plant(scene, key, x, y, parent=None, layer=None):
    item = build_species_plant(scene, QPointF(x, y), get_species_db()[key])
    item.metadata["plant_instance"] = {"planting_date": "2026-03-01"}
    if layer:
        item.layer_id = layer.id
    CreateItemsCommand(scene, [item]).execute()
    if parent:
        assert item.parent_bed_id == parent.item_id
    return item


def _rect(scene, x, y, width, height, kind, name):
    item = RectangleItem(x, y, width, height, object_type=kind, name=name,
                         layer_id=scene.active_layer.id)
    scene.addItem(item)
    return item


def food_forest():
    scene = CanvasScene(width_cm=2000, height_cm=1000)
    layers = [Layer(name=p.value.replace("_", " ").title(), z_order=i,
                    permaculture_layer=p.value) for i, p in enumerate(PermacultureLayer)
              if p is not PermacultureLayer.UNKNOWN]
    scene.set_layers(layers)
    _rect(scene, 0, 0, 2000, 1000, ObjectType.LAWN, "Food forest floor")
    # Never read the owner's local guild directory while generating bundled content.
    library = GuildLibrary(user_dir=BUNDLED_EXAMPLES / "_no_user_guilds")
    command = prepare_guild(scene, library.templates["apple-guild"], get_species_db(),
                            "Apple guild", QPointF(600, 500), auto_assign=True)
    command.execute()
    for item in command.items:
        item.metadata["plant_instance"] = {
            "planting_date": "2026-03-01", "current_height_cm": 60, "current_spread_cm": 30,
        }
    for key, x, y, layer in [
        ("prunus persica", 1500, 680, layers[1]),
        ("ribes rubrum", 1500, 200, layers[2]),
        ("fragaria ananassa", 1050, 200, layers[4]),
        ("solanum tuberosum", 1100, 650, layers[5]),
        ("phaseolus coccineus", 1850, 500, layers[6]),
    ]:
        _plant(scene, key, x, y, layer=layer)
    # A temporary nurse plant demonstrates removal across a ten-year plan timeline.
    command.items[1].metadata["plant_instance"]["removal_date"] = "2036-03-01"
    return scene, ProjectManager()


def raised_bed():
    scene = CanvasScene(width_cm=700, height_cm=500)
    bed = _rect(scene, 150, 150, 400, 200, ObjectType.RAISED_BED, "Polyculture 4 x 2 m")
    bed.metadata["object_height_cm"] = 45
    for row, key in enumerate(["daucus carota", "lactuca sativa", "raphanus sativus"]):
        for column in range(7):
            _plant(scene, key, 185 + column * 53, 185 + row * 65, parent=bed)
    entries = [SuccessionEntry(species_key=key, common_name=name, scientific_name=key,
                              start_date=start, end_date=end)
               for key, name, start, end in [
                   ("raphanus sativus", "Radish", "2027-02-01", "2027-03-31"),
                   ("phaseolus vulgaris", "Bean (Bush)", "2027-06-01", "2027-08-31"),
                   ("lactuca sativa", "Lettuce", "2027-09-01", "2027-11-15"),
               ]]
    manager = ProjectManager()
    manager.set_succession_plan(str(bed.item_id), SuccessionPlan(str(bed.item_id), 2027, entries).to_dict())
    return scene, manager


def balcony():
    scene = CanvasScene(width_cm=500, height_cm=300)
    _rect(scene, 0, 0, 500, 300, ObjectType.TERRACE_PATIO, "Balcony")
    for x, key in [(65, "ocimum basilicum"), (205, "petroselinum crispum"),
                   (345, "thymus vulgaris")]:
        pot = _rect(scene, x, 185, 90, 60, ObjectType.CONTAINER, "Herb container")
        pot.metadata["object_height_cm"] = 35
        _plant(scene, key, x + 45, 215, parent=pot)
    _rect(scene, 175, 40, 140, 65, ObjectType.TABLE_RECTANGULAR, "Balcony table")
    return scene, ProjectManager()


METADATA = {
    "food-forest": {
        "name_en": "Food forest - 200 m²", "name_de": "Waldgarten - 200 m²",
        "name_es": "Bosque comestible - 200 m²",
        "description_en": "Seven layers, an apple guild and planting/removal dates from 2026 to 2036. Illustrative layout; adapt species and spacing to your site.",
        "description_de": "Sieben Schichten, eine Apfelbaumgilde und Pflanz-/Entnahmedaten von 2026 bis 2036. Beispielentwurf; Arten und Abstände an den Standort anpassen.",
        "description_es": "Siete estratos, un gremio de manzano y fechas de plantación/retirada de 2026 a 2036. Diseño ilustrativo; adapte especies y distancias al lugar.",
        "tags": ["food-forest", "guild", "timeline"],
    },
    "raised-bed": {
        "name_en": "Raised-bed polyculture - 4 x 2 m", "name_de": "Hochbeet-Mischkultur - 4 x 2 m",
        "name_es": "Policultivo en bancal elevado - 4 x 2 m",
        "description_en": "Carrots, lettuce and radishes with a 2027 succession plan. Dates are illustrative calendar dates, not a local frost forecast.",
        "description_de": "Möhren, Salat und Radieschen mit einem Nachfolgeplan für 2027. Die Beispieldaten sind Kalenderdaten, keine lokale Frostprognose.",
        "description_es": "Zanahorias, lechugas y rábanos con un plan de sucesión para 2027. Las fechas son ejemplos de calendario, no una previsión local de heladas.",
        "tags": ["raised-bed", "polyculture", "succession"],
    },
    "balcony": {
        "name_en": "Balcony herb containers", "name_de": "Balkon mit Kräutergefäßen",
        "name_es": "Macetas de hierbas en el balcón",
        "description_en": "A 5 x 3 m balcony with basil, parsley and thyme in linked containers. Illustrative layout; check the site's light and load limits.",
        "description_de": "Ein 5 x 3 m großer Balkon mit Basilikum, Petersilie und Thymian in verknüpften Gefäßen. Beispielentwurf; Licht und Tragfähigkeit vor Ort prüfen.",
        "description_es": "Un balcón de 5 x 3 m con albahaca, perejil y tomillo en macetas vinculadas. Diseño ilustrativo; compruebe la luz y la capacidad de carga del lugar.",
        "tags": ["balcony", "containers", "herbs"],
    },
}


def main():
    script_isolation.isolate()
    app = QApplication.instance() or QApplication([])
    BUNDLED_EXAMPLES.mkdir(parents=True, exist_ok=True)
    for slug, author in [("food-forest", food_forest), ("raised-bed", raised_bed), ("balcony", balcony)]:
        scene, manager = author()
        for item in scene.items():
            if hasattr(item, "label_visible"):
                item.label_visible = False
        plan = _stable_ids(template_plan(manager._build_project_data(scene).to_dict()), slug)
        write_plan(BUNDLED_EXAMPLES / (slug + ".ogp"), plan)
        # Render the saved content itself, including its stable sprite seed IDs.
        manager.load(scene, BUNDLED_EXAMPLES / (slug + ".ogp"), as_template=True)
        meta = METADATA[slug] | {
            "license": "CC-BY-SA-4.0",
            "attribution": "Open Garden Planner contributors; species data from the bundled CC-BY-SA-4.0 database; see PROVENANCE.md.",
        }
        (BUNDLED_EXAMPLES / (slug + ".meta.json")).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        image = QImage(640, 360, QImage.Format.Format_RGB32)
        image.fill(QColor("#f2f0e8"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        render_scene_region(scene, painter, QRectF(0, 0, 640, 360), scene.canvas_rect)
        painter.end()
        assert image.save(str(BUNDLED_EXAMPLES / (slug + ".png")))
        scene.clear()
    app.processEvents()


if __name__ == "__main__":
    main()
