"""Author the offline example plans and thumbnails through production paths.

Run from the repository root. Layouts are illustrative, not climate prescriptions.
Deterministic IDs and dates keep content reviewable across regenerations.

Three are teaching plans authored here. The fourth, ``family-garden``, is the 3D view's
showcase: the very plan the bench fixture ``bench_small.ogp`` is, built by the same
``make_bench_plans.build_small`` so that it cannot drift from what every Beauty Board shows,
and with that fixture's item ids, because a plant's procedural shape is seeded by its id.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

os.environ.setdefault("QT_QPA_PLATFORM", "minimal:enable_fonts")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import script_isolation

if __name__ == "__main__":
    script_isolation.isolate_profile()

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.commands import CreateItemsCommand
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.growth_model import years_to_maturity
from open_garden_planner.core.guild_commands import GuildMembershipCommand
from open_garden_planner.core.item_look import adopt_pen, restore_stored_look
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.plan_io import write_plan
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.harvest_log import HarvestHistory, HarvestRecord
from open_garden_planner.models.layer import Layer
from open_garden_planner.models.plant_data import PermacultureLayer, species_key
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord
from open_garden_planner.models.succession import SuccessionEntry, SuccessionPlan
from open_garden_planner.services.bundled_species_db import get_species_db
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.geometry_apply import apply_rotation
from open_garden_planner.ui.canvas.items import CircleItem, PolylineItem, RectangleItem, TextItem
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


# Explicit authored translations: botanical keys and renderer species strings stay canonical.
TRANSLATIONS = {}


def text(en, de, es):
    """Register one English string's translations. One string has ONE translation per
    language: every plan is localized from this single table, so a second, different
    entry would silently win for whichever plan is authored later (it turned the
    showcase's "Compostador" into "Compost" whenever all four plans were regenerated)."""
    entry = {"de": de, "es": es}
    assert TRANSLATIONS.setdefault(en, entry) == entry, (en, TRANSLATIONS[en], entry)
    return en


SPECIES_NAMES = {
    "Carrot": ("Möhre", "Zanahoria"), "Radish": ("Radieschen", "Rábano"),
    "Lettuce": ("Salat", "Lechuga"), "Garlic": ("Knoblauch", "Ajo"),
    "Chives": ("Schnittlauch", "Cebollino"), "Parsley": ("Petersilie", "Perejil"),
    "Basil": ("Basilikum", "Albahaca"), "Thyme": ("Thymian", "Tomillo"),
    "Strawberry": ("Erdbeere", "Fresa"), "Runner Bean": ("Feuerbohne", "Judía escarlata"),
    "Borage": ("Borretsch", "Borraja"), "Pot Marigold": ("Ringelblume", "Caléndula"),
    "Apple Tree": ("Apfelbaum", "Manzano"), "Peach Tree": ("Pfirsichbaum", "Melocotonero"),
    "Currant": ("Johannisbeere", "Grosellero"), "Bean (Bush)": ("Buschbohne", "Judía de mata baja"),
}
for _en, (_de, _es) in SPECIES_NAMES.items():
    text(_en, _de, _es)


def _plant(scene, key, x, y, parent=None, layer=None, planted="2026-05-20", nursery_size=None):
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


def _rect(scene, x, y, width, height, kind, name, height_cm=None):
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


def _line(scene, points, kind, name, height_cm, preset=PathFenceStyle.NONE):
    item = PolylineItem([QPointF(x, y) for x, y in points], object_type=kind,
                        name=name, layer_id=scene.active_layer.id, path_fence_style=preset)
    item.metadata["object_height_cm"] = height_cm
    scene.addItem(item)
    return item


#: A tutorial note's ink. A note has no halo and no card of its own, so its colour has to
#: suit the ground it lies on: dark on the balcony's pale boards, light on a lawn, where the
#: dark ink sank into the grass texture (#795).
NOTE_ON_PALE, NOTE_ON_LAWN = "#243528", "#fdfbee"


def _note(scene, x, y, content, size=0.42, ink=NOTE_ON_PALE, bold=False):
    item = TextItem(x, y, content=content, font_size=size, bold=bold,
                    text_color=QColor(ink), layer_id=scene.active_layer.id)
    scene.addItem(item)
    return item


def _site(manager, city, latitude, longitude):
    manager.set_location({"name": city, "latitude": latitude, "longitude": longitude,
                          "timezone": "Europe/Berlin", "frost_dates": {
                              "last_spring_frost": "05-15", "first_fall_frost": "10-15"}})


def _soil(manager, bed, ph=6.5):
    note = text("Fictional teaching sample, 20 May 2026; not a real soil analysis.",
                "Fiktive Übungsprobe vom 20. Mai 2026; keine echte Bodenanalyse.",
                "Muestra didáctica ficticia del 20 de mayo de 2026; no es un análisis real.")
    history = SoilTestHistory(str(bed.item_id), [SoilTestRecord(
        date="2026-05-20", ph=ph, n_level=1, p_level=2, k_level=3,
        soil_texture="loamy", notes=note)])
    manager.set_soil_test_history(str(bed.item_id), history)


def _first(scene, key):
    """The plant of species ``key`` nearest the plan's south-west corner: one fixed plant
    of a species carries that species' harvest history."""
    plants = [item for item in scene.items()
              if species_key((getattr(item, "metadata", None) or {}).get("plant_species") or {}) == key]
    assert plants, key
    return min(plants, key=lambda item: (item.sceneBoundingRect().center().x(),
                                         item.sceneBoundingRect().center().y()))


def _harvest(manager, slug, plant, entries):
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


def food_forest():
    scene = CanvasScene(width_cm=2000, height_cm=1000)
    layer_names = [
        ("Canopy", "Baumschicht", "Dosel"), ("Sub Canopy", "Untere Baumschicht", "Subdosel"),
        ("Shrub", "Strauchschicht", "Arbustos"), ("Herbaceous", "Krautschicht", "Herbáceas"),
        ("Ground Cover", "Bodendecker", "Cubresuelos"), ("Root", "Wurzelschicht", "Raíces"),
        ("Vine", "Kletterschicht", "Trepadoras")]
    layers = [Layer(name=text(*names), z_order=i, permaculture_layer=p.value)
              for i, (p, names) in enumerate(zip(
                  [p for p in PermacultureLayer if p is not PermacultureLayer.UNKNOWN], layer_names, strict=True))]
    scene.set_layers(layers)
    _rect(scene, 0, 0, 2000, 1000, ObjectType.LAWN,
          text("Forest garden", "Waldgarten", "Bosque comestible"))
    main_bed = _rect(scene, 70, 330, 1860, 600, ObjectType.GARDEN_BED,
                     text("Continuous mulched tree bed", "Zusammenhängendes gemulchtes Baumbeet", "Bancal continuo de árboles con acolchado"))
    main_bed.fill_pattern = FillPattern.MULCH
    main_bed.setBrush(create_pattern_brush(main_bed.fill_pattern, main_bed.fill_color))
    front_bed = _rect(scene, 70, 110, 1860, 140, ObjectType.GARDEN_BED,
                      text("Sunny edible edge", "Sonniger essbarer Saum", "Borde comestible soleado"))
    _rect(scene, 70, 250, 1860, 80, ObjectType.PATH,
          text("80 cm harvest path", "80 cm Ernteweg", "Sendero de cosecha de 80 cm"))
    _rect(scene, 1080, 330, 90, 600, ObjectType.PATH,
          text("90 cm access between trees", "90 cm Zugang zwischen den Bäumen", "Acceso de 90 cm entre árboles"))
    apple = _plant(scene, "malus domestica", 550, 650, parent=main_bed, layer=layers[0], planted="2014-11-15", nursery_size=(120, 70))
    _plant(scene, "prunus persica", 1470, 650, parent=main_bed, layer=layers[1], planted="2016-03-15", nursery_size=(140, 80))
    for x in (180, 950, 1800):
        _plant(scene, "ribes rubrum", x, 650, parent=main_bed, layer=layers[2], planted="2019-11-10", nursery_size=(40, 30))
    guild_id = str(uuid5(NAMESPACE_URL, "ogp-example/apple-guild"))
    template = deepcopy(GuildLibrary(user_dir=BUNDLED_EXAMPLES / "_no_user_guilds").templates["apple-guild"].to_dict())
    text(template["description"],
         "Ein Apfelbaum mit Feuerbohne, Borretsch und Erdbeere. Die erfassten Funktionen beschreiben Rollen, keine Erfolgsgarantie.",
         "Un manzano con judía escarlata, borraja y fresa. Las funciones registradas describen roles previstos, no garantizan el éxito del cultivo.")
    text(template["attribution"],
         "Mitwirkende von Open Garden Planner; botanische Angaben von RHS und Cornell Cooperative Extension.",
         "Colaboradores de Open Garden Planner; datos botánicos de RHS y Cornell Cooperative Extension.")
    # Only near-tree groups belong to the apple guild; the template fixer role stays unfilled.
    changes = [(apple, {"guild_id": guild_id, "role": "centre", "name": text(
        "Apple guild", "Apfelgilde", "Gremio del manzano"), "template": template})]
    for origin_x, columns in ((350, 8), (1300, 4)):
        for y in (365, 425):
            for column in range(columns):
                plant = _plant(scene, "fragaria ananassa", origin_x + 60 * column, y,
                               parent=main_bed, layer=layers[4], planted="2024-04-15")
                if origin_x == 350:
                    changes.append((plant, {"guild_id": guild_id, "role": "ground_cover"}))
    for origin_x in (130, 850, 1660):
        for row in range(2):
            for column in range(2):
                _plant(scene, "allium schoenoprasum", origin_x + 35 * column, 390 + 35 * row,
                       parent=main_bed, layer=layers[3], planted="2021-04-15")
    for x in (180, 250, 880, 950, 1730, 1800):
        plant = _plant(scene, "borago officinalis", x, 185, parent=front_bed, layer=layers[3])
    for x in (230, 300):
        for y in (475, 545):
            plant = _plant(scene, "borago officinalis", x, y, parent=main_bed, layer=layers[3])
            changes.append((plant, {"guild_id": guild_id, "role": "pollinator_attractor"}))
    for row in range(3):
        for column in range(20):
            _plant(scene, "daucus carota", 370 + 20 * column, 145 + 35 * row,
                   parent=front_bed, layer=layers[5], planted="2026-06-15")
    # The support is outside the apple crown, in the same bed and beside the harvest path.
    trellis = _rect(scene, 860, 480, 200, 70, ObjectType.TRELLIS,
                    text("Bean support", "Bohnenrankhilfe", "Soporte de judías"), 220)
    for x in (890, 950, 1010):
        plant = _plant(scene, "phaseolus coccineus", x, 515, parent=trellis, layer=layers[6])
    GuildMembershipCommand(changes).execute()
    _rect(scene, 1200, 145, 150, 55, ObjectType.BENCH, text("Harvest bench", "Erntebank", "Banco de cosecha"))
    _note(scene, 70, 95, text(
        "21 Sep 2026 · 1  Apple guild: select apple → Guilds; inspect grouped plants and the unfilled fixer role.\n2  Plan & Sun: scrub 2014–2026; inspect the established trees (planted 2014 / 2016).\n3  Hours of Sun: compare the south edge with the tree shade. Bonn reference; frost dates are fictional.",
        "21.09.2026 · 1  Apfelgilde: Apfelbaum → Gilden; Pflanzgruppen und die unbesetzte Stickstoffbinder-Rolle prüfen.\n2  Plan & Sonne: 2014–2026 durchgehen; alte Bäume prüfen (gepflanzt 2014 / 2016).\n3  Sonnenstunden: Südsaum mit Baumschatten vergleichen. Referenz Bonn; Frostdaten sind fiktiv.",
        "21 sep 2026 · 1  Gremio: manzano → Gremios; observe los grupos y el rol de fijador sin cubrir.\n2  Plan y sol: recorra 2014–2026; observe los árboles establecidos (plantados en 2014 / 2016).\n3  Horas de sol: compare el borde sur y la sombra. Referencia Bonn; heladas ficticias."), 0.65, NOTE_ON_LAWN, bold=True)
    manager = ProjectManager()
    _site(manager, "Bonn", 50.7374, 7.0982)
    # Two seasons of the perennials, one of this year's sowings; nothing after 21 September.
    for key, entries in (
        ("malus domestica", [("2025-09-20", 38, "kg"), ("2025-10-04", 22, "kg", SWEET),
                             ("2026-09-12", 31, "kg", FIRST_PICK)]),
        ("prunus persica", [("2025-08-16", 14, "kg"), ("2026-08-12", 9, "kg", SWEET),
                            ("2026-08-22", 7.5, "kg")]),
        ("ribes rubrum", [("2025-07-06", 3.2, "kg"), ("2026-07-04", 2.8, "kg"),
                          ("2026-07-11", 1.6, "kg")]),
        ("fragaria ananassa", [("2025-06-10", 1.8, "kg"), ("2025-06-20", 2.4, "kg", SWEET),
                               ("2026-06-08", 2.1, "kg"), ("2026-06-17", 2.9, "kg", AROMATIC)]),
        ("phaseolus coccineus", [("2026-08-05", 1.2, "kg", TENDER), ("2026-08-26", 1.9, "kg"),
                                 ("2026-09-14", 1.1, "kg")]),
        ("allium schoenoprasum", [("2025-05-10", 4, "bunch"), ("2026-05-02", 3, "bunch"),
                                  ("2026-07-25", 2, "bunch")]),
        ("daucus carota", [("2026-09-18", 1.4, "kg", THINNINGS)]),
    ):
        _harvest(manager, "food-forest", _first(scene, key), entries)
    return scene, manager


def raised_bed():
    scene = CanvasScene(width_cm=900, height_cm=650)
    scene.active_layer.name = text("Kitchen garden", "Küchengarten", "Huerto de cocina")
    _rect(scene, 0, 0, 900, 650, ObjectType.LAWN, text("Kitchen garden lawn", "Küchengartenrasen", "Césped del huerto"))
    _rect(scene, 135, 165, 550, 330, ObjectType.PATH, text("Harvest access", "Erntezugang", "Acceso de cosecha"))
    bed = _rect(scene, 210, 230, 400, 200, ObjectType.RAISED_BED,
                text("1  Polyculture 4 x 2 m", "1  Mischkultur 4 x 2 m", "1  Policultivo 4 x 2 m"), 45)
    # Sprite soil: x=11/120..109/120, y=11/80..69/80 of the full footprint.
    # These mature circles fit the stricter 2D inset, also clearing the 5 cm 3D planks.
    for row in range(4):
        for column in range(4):
            _plant(scene, "lactuca sativa", 265 + 30 * column, 280 + 30 * row, parent=bed, planted="2026-08-01")
    for row in range(6):
        for column in range(10):
            _plant(scene, "daucus carota", 390 + 10 * column, 270 + 25 * row, parent=bed, planted="2026-06-15")
    for row in range(11):
        for column in range(8):
            _plant(scene, "raphanus sativus", 495 + 10 * column, 265 + 13 * row, parent=bed, planted="2026-08-20")
    border = _rect(scene, 710, 180, 130, 310, ObjectType.GARDEN_BED,
                   text("Pollinator and kitchen border", "Blühender Küchensaum", "Borde de flores y hierbas"))
    for y in (215, 275, 335, 395, 455):
        for x, key in ((745, "calendula officinalis"), (805, "allium schoenoprasum")):
            _plant(scene, key, x, y, parent=border, planted="2023-04-15" if x == 805 else "2026-05-20")
    _rect(scene, 70, 535, 150, 55, ObjectType.BENCH, text("Garden bench", "Gartenbank", "Banco de jardín"))
    _rect(scene, 15, 240, 120, 100, ObjectType.TOOL_SHED,
          text("Tool shed: afternoon shadow", "Geräteschuppen: Nachmittagsschatten", "Caseta: sombra de tarde"), 210)
    _rect(scene, 270, 535, 90, 80, ObjectType.COMPOST_BIN, text("Compost", "Kompost", "Compostador"), 90)
    entries = [SuccessionEntry(species_key=key, common_name=name, scientific_name=key,
                              start_date=start, end_date=end)
               for key, name, start, end in [
                   ("raphanus sativus", "Radish", "2027-03-15", "2027-05-15"),
                   ("phaseolus vulgaris", "Bean (Bush)", "2027-06-01", "2027-08-31"),
                   ("lactuca sativa", "Lettuce", "2027-09-01", "2027-10-31")]]
    manager = ProjectManager()
    manager.set_succession_plan(str(bed.item_id), SuccessionPlan(str(bed.item_id), 2027, entries).to_dict())
    _soil(manager, bed)
    _site(manager, "Berlin", 52.5200, 13.4050)
    _note(scene, 80, 145, text(
        "21 Sep 2026 · 1  16 lettuces + 60 carrots + 88 radishes; sow radish sections in batches.\n2  Right-click the bed: Succession Plan (2027), then Soil Test (fictional sample).\n3  Plan & Sun: 21 Sep, 17:30 → shed shade on the bed. Berlin / frost: demo data.",
        "21.09.2026 · 1  16 Salate + 60 Möhren + 88 Radieschen; Radieschen abschnittsweise säen.\n2  Rechtsklick aufs Beet: Nachfolgeplanung (2027), dann Bodentest (fiktive Probe).\n3  Plan & Sonne: 21.09., 17:30 Uhr → Beetschatten. Berlin / Frost: Beispieldaten.",
        "21 sep 2026 · 1  16 lechugas + 60 zanahorias + 88 rábanos; siembre rábanos por tandas.\n2  Clic derecho en bancal: sucesión (2027), después análisis de suelo (muestra ficticia).\n3  Plan y sol: 21 sep, 17:30 → sombra sobre el bancal. Berlín / heladas: ejemplo."), 0.47, NOTE_ON_LAWN, bold=True)
    # The bed stays fully planted on 21 September: what was taken so far are leaves and
    # thinnings, and the border's perennial chives have a season behind them.
    for key, entries in (
        ("lactuca sativa", [("2026-09-05", 350, "g", OUTER_LEAVES), ("2026-09-16", 420, "g", CRISP)]),
        ("daucus carota", [("2026-09-10", 1.1, "kg", THINNINGS), ("2026-09-19", 1.6, "kg", SWEET)]),
        ("allium schoenoprasum", [("2025-05-18", 3, "bunch"), ("2025-08-09", 2, "bunch"),
                                  ("2026-04-28", 2, "bunch"), ("2026-06-15", 2, "bunch"),
                                  ("2026-08-30", 1, "bunch")]),
        ("calendula officinalis", [("2026-07-12", 30, "pcs", PETALS), ("2026-08-18", 25, "pcs")]),
    ):
        _harvest(manager, "raised-bed", _first(scene, key), entries)
    return scene, manager


def balcony():
    scene = CanvasScene(width_cm=500, height_cm=300)
    scene.active_layer.name = text("Balcony garden", "Balkongarten", "Huerto de balcón")
    _rect(scene, 0, 0, 500, 300, ObjectType.TERRACE_PATIO, text("Balcony 5 x 3 m", "Balkon 5 x 3 m", "Balcón 5 x 3 m"))
    # North wall; east, south and west rails. Geometry remains a balcony, not a house footprint.
    _line(scene, [(8, 292), (492, 292)], ObjectType.WALL,
          text("North house wall", "Nördliche Hauswand", "Pared norte de la casa"), 260)
    _line(scene, [(8, 285), (8, 8), (492, 8), (492, 285)], ObjectType.FENCE,
          text("Three balcony rails", "Dreiseitiges Balkongeländer", "Barandilla en tres lados"), 110, PathFenceStyle.METAL_FENCE)
    pots = []
    for x, width, key, count, spacing, name in [
        (25, 110, "ocimum basilicum", 4, 40, text("Basil: moist compost", "Basilikum: feuchtes Substrat", "Albahaca: sustrato húmedo")),
        (170, 110, "petroselinum crispum", 6, 30, text("Parsley: moist compost", "Petersilie: feuchtes Substrat", "Perejil: sustrato húmedo")),
        (325, 110, "thymus vulgaris", 4, 40, text("Thyme: free-draining compost", "Thymian: durchlässiges Substrat", "Tomillo: sustrato drenante"))]:
        pot = _rect(scene, x, 35, width, 90, ObjectType.CONTAINER, name, 35)
        pot.metadata["container_material"] = "wood"
        columns = 3 if count == 6 else 2
        for row in range(2):
            for column in range(columns):
                _plant(scene, key, x + (width - (columns - 1) * spacing) / 2 + column * spacing,
                       60 + row * 40, parent=pot, planted={"thymus vulgaris": "2023-05-20", "petroselinum crispum": "2026-08-20", "ocimum basilicum": "2026-05-20"}[key])
        pots.append(pot)
    _rect(scene, 175, 205, 100, 65, ObjectType.TABLE_RECTANGULAR,
          text("Breakfast table", "Frühstückstisch", "Mesa de desayuno"))
    for x in (120, 292):
        chair = _rect(scene, x, 215, 42, 42, ObjectType.CHAIR,
                      text("Balcony chair", "Balkonstuhl", "Silla de balcón"))
        # Through the canonical rotate path, about the seat's centre. A bare
        # ``setRotation`` turned about the item's origin and was never saved as the
        # item's angle: the shipped chairs stood unrotated, and a regeneration under the
        # current serializer moved them off the balcony.
        apply_rotation(chair, 90 if x == 120 else -90)
    parasol = CircleItem(center_x=410, center_y=215, radius=72,
                        object_type=ObjectType.PARASOL,
                        name=text("Parasol: 21 June at 15:00", "Sonnenschirm: 21. Juni um 15 Uhr", "Sombrilla: 21 de junio a las 15:00"), layer_id=scene.active_layer.id)
    parasol.metadata["object_height_cm"] = 230
    scene.addItem(parasol)
    manager = ProjectManager()
    _site(manager, "Freiburg im Breisgau", 47.9990, 7.8421)
    _soil(manager, pots[0])
    _note(scene, 20, 196, text(
        "21 Sep 2026 · 4 basil / 6 parsley / 4 thyme; water separately.\nBasil trough → Soil Test: fictional sample; Freiburg / frost: demo data.\nPlan & Sun: 21 June, 15:00 → compare wall, rails and parasol shadows.",
        "21.09.2026 · 4 Basilikum, 6 Petersilien, 4 Thymiane; getrennt gießen.\nBasilikumtrog → Bodentest: Übungsprobe; Freiburg / Frost: fiktiv.\nPlan & Sonne: 21. Juni, 15 Uhr → Wand, Geländer und Schirm.",
        "21 sep 2026 · 4 albahacas, 6 perejiles, 4 tomillos; riego separado.\nAlbahaca → Análisis de suelo: ficticio; Friburgo / heladas: ejemplo.\nPlan y sol: 21 junio, 15:00 → pared, barandilla y sombrilla."), 0.24)
    for key, entries in (
        ("ocimum basilicum", [("2026-06-28", 1, "bunch", FIRST_PICK), ("2026-07-19", 2, "bunch", AROMATIC),
                              ("2026-08-15", 2, "bunch"), ("2026-09-06", 1, "bunch")]),
        ("thymus vulgaris", [("2025-06-14", 2, "bunch"), ("2025-08-23", 1, "bunch"),
                             ("2026-06-06", 2, "bunch", AROMATIC), ("2026-08-29", 1, "bunch")]),
        ("petroselinum crispum", [("2026-09-14", 1, "bunch", FIRST_PICK)]),
    ):
        _harvest(manager, "balcony", _first(scene, key), entries)
    return scene, manager


# The showcase garden's own words (``family_garden``): every item name of the builder and
# every species name beyond the teaching plans'.
for _en, _de, _es in (
    ("Layer 1", "Ebene 1", "Capa 1"), ("Lawn", "Rasen", "Césped"), ("Terrace", "Terrasse", "Terraza"),
    ("Gravel yard", "Kieshof", "Patio de grava"), ("Pond", "Teich", "Estanque"),
    ("House", "Haus", "Casa"), ("Greenhouse", "Gewächshaus", "Invernadero"),
    ("Shed", "Schuppen", "Cobertizo"), ("Pergola", "Holzpergola", "Pérgola"),
    ("South fence", "Südzaun", "Valla sur"), ("East fence", "Ostzaun", "Valla este"),
    ("Beech hedge", "Buchenhecke", "Seto de haya"), ("Yard wall", "Hofmauer", "Muro del patio"),
    ("Gravel path", "Kiesweg", "Camino de grava"), ("Stepping stones", "Trittsteine", "Pasaderas"),
    ("Herb strip", "Kräuterstreifen", "Franja de hierbas"),
    ("Perennial border", "Staudenrabatte", "Arriate de vivaces"),
    ("Flower bed", "Blumenbeet", "Parterre de flores"),
    ("Raised bed 1", "Hochbeet 1", "Bancal elevado 1"), ("Raised bed 2", "Hochbeet 2", "Bancal elevado 2"),
    ("Raised bed 3", "Hochbeet 3", "Bancal elevado 3"), ("Pot 1", "Topf 1", "Maceta 1"),
    ("Pot 2", "Topf 2", "Maceta 2"), ("Pot 3", "Topf 3", "Maceta 3"),
    ("Trellis", "Rankgitter", "Espaldera"), ("Table", "Tisch", "Mesa"), ("Chair", "Stuhl", "Silla"),
    ("BBQ", "Grill", "Barbacoa"), ("Fire pit", "Feuerstelle", "Hoguera"), ("Bench", "Sitzbank", "Banco"),
    ("Bird bath", "Vogeltränke", "Bebedero de pájaros"), ("Trampoline", "Trampolin", "Cama elástica"),
    ("Compost", "Kompost", "Compostador"), ("Wheelbarrow", "Schubkarre", "Carretilla"),
    ("Rain barrel", "Regentonne", "Barril de lluvia"),
    # species the teaching plans do not have; a name both languages share stays as it is
    ("Sage", "Salbei", "Salvia"), ("Oregano", "Oregano", "Orégano"), ("Lavender", "Lavendel", "Lavanda"),
    ("Peony", "Pfingstrose", "Peonía"), ("Iris", "Schwertlilie", "Lirio"),
    ("Echinacea", "Sonnenhut", "Equinácea"), ("Aster", "Aster", "Áster"),
    ("Geranium", "Geranie", "Geranio"), ("Chrysanthemum", "Chrysantheme", "Crisantemo"),
    ("Lily", "Lilie", "Azucena"), ("Pansy", "Stiefmütterchen", "Pensamiento"),
    ("Sunflower", "Sonnenblume", "Girasol"), ("Dahlia", "Dahlie", "Dalia"),
    ("Marigold", "Studentenblume", "Tagete"), ("Cosmos", "Schmuckkörbchen", "Cosmos"),
    ("Zinnia", "Zinnie", "Zinnia"), ("Tulip", "Tulpe", "Tulipán"), ("Tomato", "Tomate", "Tomate"),
    ("Sweet Pepper", "Paprika", "Pimiento"), ("Cabbage", "Kohl", "Col"), ("Kale", "Grünkohl", "Col rizada"),
    ("Onion", "Zwiebel", "Cebolla"), ("Beet", "Rote Bete", "Remolacha"), ("Zucchini", "Zucchini", "Calabacín"),
    ("Leek", "Lauch", "Puerro"), ("Spinach", "Spinat", "Espinaca"), ("Rosemary", "Rosmarin", "Romero"),
    ("Cucumber", "Gurke", "Pepino"), ("Hydrangea", "Hortensie", "Hortensia"), ("Rose", "Rose", "Rosal"),
    ("Lilac", "Flieder", "Lila"), ("Boxwood", "Buchsbaum", "Boj"), ("Forsythia", "Forsythie", "Forsitia"),
    ("Rhododendron", "Rhododendron", "Rododendro"), ("Blueberry", "Heidelbeere", "Arándano"),
    ("Raspberry", "Himbeere", "Frambuesa"), ("Gooseberry", "Stachelbeere", "Grosella espinosa"),
    ("Cherry Tree", "Kirschbaum", "Cerezo"), ("Birch", "Birke", "Abedul"), ("Pear Tree", "Birnbaum", "Peral"),
    ("Spruce", "Fichte", "Picea"), ("Magnolia", "Magnolie", "Magnolia"),
):
    text(_en, _de, _es)


#: Before the first day of a tour's default time-lapse (``tour_dialog.DEFAULT_SEASON``).
ESTABLISHED = "2026-03-01"


def _establish(item):
    """A tree, a shrub, a perennial stood here before the season: a time-lapse from March shows
    it leafing out, not popping in on the fixture's one date. What ripens within a season keeps
    its planting day and comes up in the beds."""
    metadata = getattr(item, "metadata", None) or {}
    instance, species = metadata.get("plant_instance"), metadata.get("plant_species")
    if not instance or not species:
        return
    kind = item.object_type.name if getattr(item, "object_type", None) is not None else ""
    if years_to_maturity(species, kind) >= 1.0:
        instance["planting_date"] = ESTABLISHED


#: The showcase's two paths, as wide as a path one walks on. The bench fixture keeps the
#: 8 and 6 cm it was made with (``make_bench_plans.LEGACY_PATH_WIDTH_CM``: its pinned
#: numbers), and they were hairlines in the plan and in 3D (#795).
FAMILY_PATH_WIDTH_CM = {"Gravel path": 80.0, "Stepping stones": 50.0}


#: What stood in the 50 cm stepping-stone walk, and where it stands in the showcase: the
#: object's name or the plant's common name, and its centre. In the bench plan the walk is
#: a 6 cm line, so a bird bath 26 cm from it and two perennials beside it were clear; as a
#: walk it ran over them (review of #795). The path's own points stay: test data is pinned
#: to them, and so does the bench fixture's layout. The lily moves so that the
#: chrysanthemum, now east of the walk, keeps its distance from it.
FAMILY_MOVED_CM = {
    "Bird bath": (620.0, 450.0),         # was (560, 470): east of the walk, by the pond's end
    "Geranium": (612.0, 681.0),          # was x 630: the border's last plant west of the walk
    "Chrysanthemum": (746.0, 681.0),     # was x 712: the first plant east of it
    "Lily": (811.0, 681.0),              # was x 794
}

#: The cherry bears fruit in June (its fictional harvest below), so it is no tree of this
#: spring: planted in autumn 2022 as a nursery tree of this size (the growth model's low
#: end is the size AT planting). On the reference date its crown is the 3.7 m the plan was
#: drawn with; it is 6.4 m tall, where the spring-planted tree stood at 5.1 m.
FAMILY_CHERRY = {"planting_date": "2022-11-05", "current_spread_cm": 130.0,
                 "current_height_cm": 150.0}


def _name_of(item):
    """An object's name, or a plant's common name (the bench builder names no plant)."""
    species = (getattr(item, "metadata", None) or {}).get("plant_species") or {}
    return getattr(item, "name", "") or species.get("common_name", "")


def family_garden():
    """The bench plan as an example: ``make_bench_plans.build_small``, one builder for both."""
    from make_bench_plans import BERLIN, build_small

    builder = build_small()
    widened, moved, cherries = set(), set(), 0
    for item in builder.scene.items():
        _establish(item)
        name = _name_of(item)
        if getattr(item, "object_type", None) is ObjectType.PATH and item.name in FAMILY_PATH_WIDTH_CM:
            pen = item.pen()
            pen.setWidthF(FAMILY_PATH_WIDTH_CM[item.name])
            adopt_pen(item, pen)
            widened.add(item.name)
        if name in FAMILY_MOVED_CM and isinstance(item, CircleItem):
            assert name not in moved, name          # each name stands for one object
            centre = item.mapToParent(item.rect().center())
            item.moveBy(FAMILY_MOVED_CM[name][0] - centre.x(), FAMILY_MOVED_CM[name][1] - centre.y())
            moved.add(name)
        if name == "Cherry Tree":
            item.metadata["plant_instance"] = dict(FAMILY_CHERRY)
            cherries += 1
    assert widened == set(FAMILY_PATH_WIDTH_CM), widened
    assert moved == set(FAMILY_MOVED_CM) and cherries == 1, (moved, cherries)
    manager = ProjectManager()
    manager.set_location(dict(BERLIN) | {"timezone": "Europe/Berlin"})
    # What a Berlin garden planted on 15 April (its trees stood before) has given by 21 June.
    for key, entries in (
        ("lactuca sativa", [("2026-05-30", 180, "g", OUTER_LEAVES), ("2026-06-12", 220, "g", CRISP)]),
        ("spinacia oleracea", [("2026-05-22", 250, "g", TENDER), ("2026-06-05", 300, "g")]),
        ("allium schoenoprasum", [("2026-05-15", 1, "bunch"), ("2026-06-08", 2, "bunch")]),
        ("petroselinum crispum", [("2026-06-02", 1, "bunch")]),
        ("ocimum basilicum", [("2026-06-14", 1, "bunch", AROMATIC)]),
        ("prunus avium", [("2026-06-13", 2.5, "kg", FIRST_PICK), ("2026-06-19", 4, "kg", SWEET)]),
    ):
        _harvest(manager, "family-garden", _first(builder.scene, key), entries)
    return builder.scene, manager


def localized_plan(plan, language):
    def localize(value, key=""):
        if key == "plant_species" and isinstance(value, dict):
            # botany stays canonical: a genus may read like a name ("Iris" the plant, "Iris"
            # the genus), and only the common name is ever shown in the user's language
            return value | {"common_name": localize(value.get("common_name"))}
        if isinstance(value, dict):
            return {k: localize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [localize(v, key) for v in value]
        if isinstance(value, str) and key != "plant_species":
            return TRANSLATIONS.get(value, {}).get(language, value)
        return value
    return localize(plan)


#: The moment an example opens at (``core/templates.example_showcase_moment``): its
#: reference date, and a UTC time of day at which the sun stands well up over every one of
#: the four gardens. All four lie in Europe/Berlin, on summer time on both dates:
#: 11:00 UTC is 13:00 on their wall clocks, a quarter of an hour before solar noon in Berlin.
TEACHING_DATE, SHOWCASE_UTC_TIME = "2026-09-21", "11:00"

METADATA = {
    "family-garden": {
        "name_en": "Family garden - 24 x 16 m", "name_de": "Familiengarten - 24 x 16 m",
        "name_es": "Jardín familiar - 24 x 16 m",
        "name_ru": "Семейный сад - 24 x 16 м",
        "description_en": "A whole garden to explore in 3D: house, greenhouse, shed, terrace with pergola, lawn with pond and trampoline, three raised vegetable beds, fruit trees, hedge and fences. 61 plants. Berlin reference; opens on 21 June 2026 in daylight, ready for the 3D view. Illustrative layout.",
        "description_de": "Ein ganzer Garten zum Erkunden in 3D: Haus, Gewächshaus, Schuppen, Terrasse mit Pergola, Rasen mit Teich und Trampolin, drei Hochbeete, Obstbäume, Hecke und Zäune. 61 Pflanzen. Referenz Berlin; öffnet am 21. Juni 2026 bei Tageslicht, bereit für die 3D-Ansicht. Beispielentwurf.",
        "description_es": "Un jardín entero para explorar en 3D: casa, invernadero, cobertizo, terraza con pérgola, césped con estanque y cama elástica, tres bancales elevados, frutales, seto y vallas. 61 plantas. Referencia Berlín; se abre el 21 de junio de 2026 con luz de día, listo para la vista 3D. Diseño ilustrativo.",
        "description_ru": "Целый сад для изучения в 3D: дом, теплица, сарай, терраса с перголой, газон с прудом и батутом, три высокие грядки с овощами, плодовые деревья, живая изгородь и заборы. 61 растение. Ориентир: Берлин; открывается на 21 июня 2026 года при дневном свете, готов к просмотру в 3D. Примерный проект.",
        "tags": ["showcase", "3d", "family-garden"],
        "showcase_date": "2026-06-21", "showcase_utc_time": SHOWCASE_UTC_TIME,
    },
    "food-forest": {
        "name_en": "Food forest - 200 m²", "name_de": "Waldgarten - 200 m²",
        "name_es": "Bosque comestible - 200 m²",
        "name_ru": "Лесосад - 200 м²",
        "description_en": "Established trees, a grouped apple guild, accessible mulched beds and a sunny edible edge. Opens on 21 September 2026 in daylight; Bonn reference coordinates, fictional frost dates and harvest log. Illustrative layout; adapt species and spacing to your site.",
        "description_de": "Alte Bäume, eine Apfelgilde in Pflanzgruppen, gemulchte Beete mit Erntewegen und ein sonniger essbarer Saum. Öffnet am 21. September 2026 bei Tageslicht; Referenzkoordinaten Bonn, fiktive Frostdaten und fiktives Erntebuch. Beispielentwurf; Arten und Abstände an den Standort anpassen.",
        "description_es": "Árboles establecidos, un gremio de manzano en grupos y bancales acolchados con acceso. Se abre el 21 de septiembre de 2026 con luz de día; coordenadas de referencia de Bonn, heladas y cosechas ficticias. Diseño ilustrativo; adapte especies y distancias al lugar.",
        "description_ru": "Взрослые деревья, гильдия яблони в группах посадки, мульчированные грядки с проходами и солнечная съедобная опушка. Открывается на 21 сентября 2026 года при дневном свете; координаты Бонна, условные даты заморозков и условный журнал урожая. Пример планировки; адаптируйте виды и расстояния под ваш участок.",
        "tags": ["food-forest", "guild", "timeline"],
        "showcase_date": TEACHING_DATE, "showcase_utc_time": SHOWCASE_UTC_TIME,
    },
    "raised-bed": {
        "name_en": "Raised-bed polyculture - 4 x 2 m", "name_de": "Hochbeet-Mischkultur - 4 x 2 m",
        "name_es": "Policultivo en bancal elevado - 4 x 2 m",
        "name_ru": "Поликультура в высокой грядке - 4 x 2 м",
        "description_en": "164 crops in a 4 x 2 m bed: 16 lettuces, 60 carrots and 88 radishes. Autumn crops, a 2027 succession, a fictional soil sample and harvest log. Opens on 21 September 2026 in daylight; Berlin reference. Dates are illustrative calendar dates, not a local frost forecast.",
        "description_de": "164 Pflanzen im 4 x 2 m Beet: 16 Salate, 60 Möhren und 88 Radieschen. Herbstbestand, Nachfolgeplan 2027, fiktive Bodenprobe und fiktives Erntebuch. Öffnet am 21. September 2026 bei Tageslicht; Referenz Berlin. Die Beispieldaten sind Kalenderdaten, keine lokale Frostprognose.",
        "description_es": "164 plantas en un bancal de 4 x 2 m: 16 lechugas, 60 zanahorias y 88 rábanos. Sucesión de 2027, muestra de suelo y cosechas ficticias. Se abre el 21 de septiembre de 2026 con luz de día; referencia Berlín. Las fechas son ejemplos de calendario, no una previsión local de heladas.",
        "description_ru": "164 культуры на грядке 4 x 2 м: 16 салатов, 60 морковей и 88 редисов. Осенние посадки, севооборот на 2027 год, условные образец почвы и журнал урожая. Открывается на 21 сентября 2026 года при дневном свете; координаты Берлина. Указаны примерные календарные даты, а не прогноз местных заморозков.",
        "tags": ["raised-bed", "polyculture", "succession"],
        "showcase_date": TEACHING_DATE, "showcase_utc_time": SHOWCASE_UTC_TIME,
    },
    "balcony": {
        "name_en": "Balcony herb containers", "name_de": "Balkon mit Kräutergefäßen",
        "name_es": "Macetas de hierbas en el balcón",
        "name_ru": "Балкон с контейнерами для трав",
        "description_en": "A furnished 5 x 3 m balcony: 4 basil, 6 parsley and 4 thyme plants, three rails, a north wall and a parasol. Soil-test and shadow tutorial; Freiburg reference. Opens on its teaching date, 21 September 2026, in daylight. Illustrative layout; check the site's light and load limits.",
        "description_de": "Ein möblierter 5 x 3 m Balkon: 4 Basilikum-, 6 Petersilien- und 4 Thymianpflanzen, drei Geländerseiten, Nordwand und Schirm. Bodentest- und Schattenübung; Referenz Freiburg. Öffnet am Übungsdatum, dem 21. September 2026, bei Tageslicht. Beispielentwurf; Licht und Tragfähigkeit vor Ort prüfen.",
        "description_es": "Un balcón amueblado de 5 x 3 m: 4 albahacas, 6 perejiles y 4 tomillos, tres barandillas, pared norte y sombrilla. Tutorial de suelo y sombras; referencia Friburgo. Se abre en su fecha didáctica, el 21 de septiembre de 2026, con luz de día. Diseño ilustrativo; compruebe la luz y la capacidad de carga del lugar.",
        "description_ru": "Обустроенный балкон 5 x 3 м: 4 базилика, 6 петрушек и 4 тимьяна, три ограждения, северная стена и зонт. Обучение анализу почвы и теням; координаты Фрайбурга. Открывается на учебную дату, 21 сентября 2026 года, при дневном свете. Пример планировки; проверьте освещенность и допустимую нагрузку на месте.",
        "tags": ["balcony", "containers", "herbs"],
        "showcase_date": TEACHING_DATE, "showcase_utc_time": SHOWCASE_UTC_TIME,
    },
}


def _thumbnail(scene, path):
    image = QImage(640, 360, QImage.Format.Format_RGB32)
    image.fill(QColor("#f2f0e8"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = min(640 / scene.width_cm, 360 / scene.height_cm)
    target = QRectF((640 - scene.width_cm * scale) / 2,
                    (360 - scene.height_cm * scale) / 2,
                    scene.width_cm * scale, scene.height_cm * scale)
    render_scene_region(scene, painter, target, scene.canvas_rect)
    painter.end()
    assert image.save(str(path))


AUTHORS = {"food-forest": food_forest, "raised-bed": raised_bed, "balcony": balcony,
           "family-garden": family_garden}
LANGUAGES = ("de", "es")
ATTRIBUTION = {
    "license": "CC-BY-SA-4.0",
    "attribution": "Open Garden Planner contributors; CC-BY-SA-4.0; see PROVENANCE.md.",
    "attribution_en": "Open Garden Planner contributors; bundled CC-BY-SA-4.0 species data; see PROVENANCE.md.",
    "attribution_de": "Mitwirkende von Open Garden Planner; mitgelieferte Artendaten unter CC-BY-SA-4.0; siehe PROVENANCE.md.",
    "attribution_es": "Colaboradores de Open Garden Planner; datos de especies incluidos bajo CC-BY-SA-4.0; véase PROVENANCE.md.",
    "attribution_ru": "Авторы Open Garden Planner; встроенные данные видов под лицензией CC-BY-SA-4.0; см. PROVENANCE.md.",
}


def example_content(slug):
    """What ships for ``slug``, as data: ``{file name under examples/: JSON content}``.

    The canonical English plan, its ``de/`` and ``es/`` copies and the sidecar. The one
    place the shipped files come from: ``main`` writes it, ``--check`` and
    ``tests/unit/test_example_content.py`` compare the shipped files with it.
    """
    scene, manager = AUTHORS[slug]()
    for item in scene.items():
        if hasattr(item, "label_visible"):
            item.label_visible = False
    raw = manager._build_project_data(scene).to_dict()
    raw["metadata"] = {"modified": "2026-10-26T00:00:00+00:00"}
    scene.clear()
    # the showcase keeps the bench plan's ids: they seed its plants' shapes
    plan = raw if slug == "family-garden" else _stable_ids(raw, slug)
    content = {slug + ".ogp": plan, slug + ".meta.json": METADATA[slug] | ATTRIBUTION}
    for language in LANGUAGES:
        content[f"{language}/{slug}.ogp"] = localized_plan(plan, language)
    return content


def stale_files(slugs):
    """The shipped plan and sidecar files that are not what the generator makes now."""
    stale = []
    for slug in slugs:
        for name, expected in example_content(slug).items():
            shipped = BUNDLED_EXAMPLES / name
            if not shipped.is_file() or json.loads(shipped.read_text(encoding="utf-8")) != expected:
                stale.append(name)
    return stale


def main(argv=None):
    script_isolation.isolate()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("slugs", nargs="*", metavar="slug",
                        help="the example plans to regenerate (default: all): " + ", ".join(AUTHORS))
    parser.add_argument("--check", action="store_true",
                        help="compare the shipped plans and sidecars with what the generator makes; "
                             "write nothing (thumbnails are not compared: fonts differ by machine)")
    args = parser.parse_args(argv)
    if unknown := set(args.slugs) - set(AUTHORS):
        parser.error(f"no such example: {', '.join(sorted(unknown))}")
    app = QApplication.instance() or QApplication([])
    slugs = args.slugs or list(AUTHORS)
    if args.check:
        stale = stale_files(slugs)
        for name in stale:
            print(f"STALE: {name} - rerun scripts/generate_examples.py")
        print("examples: " + ("FAIL" if stale else "OK"))
        return 1 if stale else 0
    BUNDLED_EXAMPLES.mkdir(parents=True, exist_ok=True)
    manager = ProjectManager()
    scene = CanvasScene()
    for slug in slugs:
        for name, content in example_content(slug).items():
            path = BUNDLED_EXAMPLES / name
            path.parent.mkdir(exist_ok=True)
            if path.suffix == ".ogp":
                write_plan(path, content)
            else:
                path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Render the saved content itself, including its stable sprite seed IDs.
        for folder in ("", *LANGUAGES):
            path = BUNDLED_EXAMPLES / folder / (slug + ".ogp")
            manager.load(scene, path, as_template=True)
            _thumbnail(scene, path.with_suffix(".png"))
        scene.clear()
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
