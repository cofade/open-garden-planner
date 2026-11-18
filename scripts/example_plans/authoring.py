"""Building blocks of the example plans: every item goes through a production path."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPen

from open_garden_planner.core.commands import CreateItemsCommand
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.item_look import restore_stored_look
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.models.harvest_log import HarvestHistory, HarvestRecord
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord
from open_garden_planner.services.bundled_species_db import get_species_db
from open_garden_planner.ui.canvas.items import PolylineItem, RectangleItem, TextItem
from open_garden_planner.ui.plant_creation import build_species_plant

from .i18n import text

#: The moment an example opens at (``core/templates.example_showcase_moment``): its
#: reference date, and a UTC time of day at which the sun stands well up over every one of
#: the four gardens. All four lie in Europe/Berlin, on summer time on both dates:
#: 11:00 UTC is 13:00 on their wall clocks, a quarter of an hour before solar noon in Berlin.
TEACHING_DATE, SHOWCASE_UTC_TIME = "2026-09-21", "11:00"


def plant(scene, key, x, y, parent=None, layer=None, planted="2026-05-20", nursery_size=None):
    item = build_species_plant(scene, QPointF(x, y), get_species_db()[key])
    item.name = item.metadata["plant_species"]["common_name"]
    item.metadata["plant_instance"] = {"planting_date": planted}
    if nursery_size:
        item.metadata["plant_instance"].update(current_height_cm=nursery_size[0],
                                               current_spread_cm=nursery_size[1])
    item.layer_id = (layer or scene.active_layer).id
    CreateItemsCommand(scene, [item]).execute()
    if parent:
        assert item.parent_bed_id == parent.item_id, (key, x, y)
    return item


def rect(scene, x, y, width, height, kind, name, height_cm=None):
    item = RectangleItem(x, y, width, height, object_type=kind, name=name,
                         layer_id=scene.active_layer.id)
    if height_cm is not None:
        item.metadata["object_height_cm"] = height_cm
    if kind is ObjectType.PATH:
        restore_stored_look(item, {"fill_pattern": "GRAVEL", "fill_color": "#c9c2ad",
                                   "stroke_color": "#a49e8c", "stroke_width": 0.5}, fill_pattern=FillPattern.GRAVEL)
        item.setBrush(create_pattern_brush(item.fill_pattern, item.fill_color))
        item.setPen(QPen(item.stroke_color, item.stroke_width))
    scene.addItem(item)
    return item


def line(scene, points, kind, name, height_cm, preset=PathFenceStyle.NONE):
    item = PolylineItem([QPointF(x, y) for x, y in points], object_type=kind,
                        name=name, layer_id=scene.active_layer.id, path_fence_style=preset)
    item.metadata["object_height_cm"] = height_cm
    scene.addItem(item)
    return item


#: A tutorial note's ink. A note has no halo and no card of its own, so its colour has to
#: suit the ground it lies on: dark on the balcony's pale boards, light on a lawn, where the
#: dark ink sank into the grass texture (#795).
NOTE_ON_PALE, NOTE_ON_LAWN = "#243528", "#fdfbee"


def note(scene, x, y, content, size=0.42, ink=NOTE_ON_PALE, bold=False):
    item = TextItem(x, y, content=content, font_size=size, bold=bold,
                    text_color=QColor(ink), layer_id=scene.active_layer.id)
    scene.addItem(item)
    return item


def site(manager, city, latitude, longitude):
    manager.set_location({"name": city, "latitude": latitude, "longitude": longitude,
                          "timezone": "Europe/Berlin", "frost_dates": {
                              "last_spring_frost": "05-15", "first_fall_frost": "10-15"}})


def soil(manager, bed, ph=6.5):
    note = text("Fictional teaching sample, 20 May 2026; not a real soil analysis.",
                "Fiktive Übungsprobe vom 20. Mai 2026; keine echte Bodenanalyse.",
                "Muestra didáctica ficticia del 20 de mayo de 2026; no es un análisis real.")
    history = SoilTestHistory(str(bed.item_id), [SoilTestRecord(
        date="2026-05-20", ph=ph, n_level=1, p_level=2, k_level=3,
        soil_texture="loamy", notes=note)])
    manager.set_soil_test_history(str(bed.item_id), history)


def first(scene, key):
    """The plant of species ``key`` nearest the plan's south-west corner: one fixed plant
    of a species carries that species' harvest history."""
    plants = [item for item in scene.items()
              if species_key((getattr(item, "metadata", None) or {}).get("plant_species") or {}) == key]
    assert plants, key
    return min(plants, key=lambda item: (item.sceneBoundingRect().center().x(),
                                         item.sceneBoundingRect().center().y()))


def harvest(manager, slug, plant, entries):
    """A fictional harvest history on ``plant``: ``(date, quantity, unit[, quality])`` rows.

    The same record the Log Harvest dialog writes, with the species identity it caches
    (the canonical ``species_key`` and the common name). No journal note is linked: an
    example copy carries no journal.
    """
    note = text("Fictional example entry; not a real harvest record.",
                "Fiktiver Beispieleintrag; keine echte Ernteaufzeichnung.",
                "Entrada ficticia de ejemplo; no es un registro real de cosecha.")
    species = plant.metadata["plant_species"]
    target = str(plant.item_id)
    for day, *_rest in entries:
        assert day >= plant.metadata["plant_instance"]["planting_date"], (slug, species["common_name"], day)
    records = [HarvestRecord(
        id=str(uuid5(NAMESPACE_URL, f"ogp-example/{slug}/harvest/{species_key(species)}/{day}")),
        date=day, quantity=quantity, unit=unit, quality=quality[0] if quality else "", notes=note)
        for day, quantity, unit, *quality in entries]
    manager.set_harvest_history(target, HarvestHistory(
        target, records, species_key=species_key(species), species_name=species["common_name"]))


#: Free-text quality remarks of the fictional harvests.
SWEET = text("sweet", "süß", "dulce")
CRISP = text("crisp", "knackig", "crujiente")
AROMATIC = text("aromatic", "aromatisch", "aromático")
TENDER = text("tender", "zart", "tierno")
FIRST_PICK = text("first pick", "erste Pflücke", "primera recogida")
THINNINGS = text("thinnings", "ausgedünnte Jungpflanzen", "aclareo")
OUTER_LEAVES = text("outer leaves", "äußere Blätter", "hojas exteriores")
PETALS = text("flowers for the kitchen", "Blüten für die Küche", "flores para la cocina")
