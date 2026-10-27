"""Author the three offline example plans and thumbnails through production paths.

Run from the repository root. Layouts are illustrative, not climate prescriptions.
Deterministic IDs and dates keep content reviewable across regenerations.
"""

from __future__ import annotations

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
from open_garden_planner.core.guild_commands import GuildMembershipCommand
from open_garden_planner.core.item_look import restore_stored_look
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.plan_io import write_plan
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.layer import Layer
from open_garden_planner.models.plant_data import PermacultureLayer
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord
from open_garden_planner.models.succession import SuccessionEntry, SuccessionPlan
from open_garden_planner.services.bundled_species_db import get_species_db
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
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
    TRANSLATIONS[en] = {"de": de, "es": es}
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


def _note(scene, x, y, content, size=0.42):
    item = TextItem(x, y, content=content, font_size=size,
                    text_color=QColor("#243528"), layer_id=scene.active_layer.id)
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
        "21 sep 2026 · 1  Gremio: manzano → Gremios; observe los grupos y el rol de fijador sin cubrir.\n2  Plan y sol: recorra 2014–2026; observe los árboles establecidos (plantados en 2014 / 2016).\n3  Horas de sol: compare el borde sur y la sombra. Referencia Bonn; heladas ficticias."), 0.65)
    manager = ProjectManager()
    _site(manager, "Bonn", 50.7374, 7.0982)
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
    _rect(scene, 270, 535, 90, 80, ObjectType.COMPOST_BIN, text("Compost", "Kompost", "Compost"), 90)
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
        "21 sep 2026 · 1  16 lechugas + 60 zanahorias + 88 rábanos; siembre rábanos por tandas.\n2  Clic derecho en bancal: sucesión (2027), después análisis de suelo (muestra ficticia).\n3  Plan y sol: 21 sep, 17:30 → sombra sobre el bancal. Berlín / heladas: ejemplo."), 0.47)
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
        chair.setRotation(90 if x == 120 else -90)
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
    return scene, manager


def localized_plan(plan, language):
    def localize(value, key=""):
        if isinstance(value, dict):
            return {k: localize(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [localize(v, key) for v in value]
        if isinstance(value, str) and key != "plant_species":
            return TRANSLATIONS.get(value, {}).get(language, value)
        return value
    return localize(plan)


METADATA = {
    "food-forest": {
        "name_en": "Food forest - 200 m²", "name_de": "Waldgarten - 200 m²",
        "name_es": "Bosque comestible - 200 m²",
        "description_en": "Established trees, a grouped apple guild, accessible mulched beds and a sunny edible edge. Set Plan & Sun to 21 September 2026; Bonn reference coordinates and fictional frost dates. Illustrative layout; adapt species and spacing to your site.",
        "description_de": "Alte Bäume, eine Apfelgilde in Pflanzgruppen, gemulchte Beete mit Erntewegen und ein sonniger essbarer Saum. Plan & Sonne auf den 21. September 2026 stellen; Referenzkoordinaten Bonn und fiktive Frostdaten. Beispielentwurf; Arten und Abstände an den Standort anpassen.",
        "description_es": "Árboles establecidos, un gremio de manzano en grupos y bancales acolchados con acceso. Ajuste Plan y sol al 21 de septiembre de 2026; coordenadas de referencia de Bonn y heladas ficticias. Diseño ilustrativo; adapte especies y distancias al lugar.",
        "tags": ["food-forest", "guild", "timeline"],
    },
    "raised-bed": {
        "name_en": "Raised-bed polyculture - 4 x 2 m", "name_de": "Hochbeet-Mischkultur - 4 x 2 m",
        "name_es": "Policultivo en bancal elevado - 4 x 2 m",
        "description_en": "164 crops in a 4 x 2 m bed: 16 lettuces, 60 carrots and 88 radishes. Autumn crops, a 2027 succession and fictional soil sample. Set Plan & Sun to 21 September 2026; Berlin reference. Dates are illustrative calendar dates, not a local frost forecast.",
        "description_de": "164 Pflanzen im 4 x 2 m Beet: 16 Salate, 60 Möhren und 88 Radieschen. Herbstbestand, Nachfolgeplan 2027 und fiktive Bodenprobe. Plan & Sonne: 21. September 2026; Referenz Berlin. Die Beispieldaten sind Kalenderdaten, keine lokale Frostprognose.",
        "description_es": "164 plantas en un bancal de 4 x 2 m: 16 lechugas, 60 zanahorias y 88 rábanos. Sucesión de 2027 y muestra ficticia de suelo. Plan y sol: 21 de septiembre de 2026; referencia Berlín. Las fechas son ejemplos de calendario, no una previsión local de heladas.",
        "tags": ["raised-bed", "polyculture", "succession"],
    },
    "balcony": {
        "name_en": "Balcony herb containers", "name_de": "Balkon mit Kräutergefäßen",
        "name_es": "Macetas de hierbas en el balcón",
        "description_en": "A furnished 5 x 3 m balcony: 4 basil, 6 parsley and 4 thyme plants, three rails, a north wall and a parasol. Soil-test and shadow tutorial; Freiburg reference. Teaching date: 21 September 2026. Illustrative layout; check the site's light and load limits.",
        "description_de": "Ein möblierter 5 x 3 m Balkon: 4 Basilikum-, 6 Petersilien- und 4 Thymianpflanzen, drei Geländerseiten, Nordwand und Schirm. Bodentest- und Schattenübung; Referenz Freiburg. Übungsdatum: 21. September 2026. Beispielentwurf; Licht und Tragfähigkeit vor Ort prüfen.",
        "description_es": "Un balcón amueblado de 5 x 3 m: 4 albahacas, 6 perejiles y 4 tomillos, tres barandillas, pared norte y sombrilla. Tutorial de suelo y sombras; referencia Friburgo. Fecha didáctica: 21 de septiembre de 2026. Diseño ilustrativo; compruebe la luz y la capacidad de carga del lugar.",
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
        raw = manager._build_project_data(scene).to_dict()
        raw["metadata"] = {"modified": "2026-10-26T00:00:00+00:00"}
        plan = _stable_ids(raw, slug)
        write_plan(BUNDLED_EXAMPLES / (slug + ".ogp"), plan)
        for language in ("de", "es"):
            folder = BUNDLED_EXAMPLES / language
            folder.mkdir(exist_ok=True)
            write_plan(folder / (slug + ".ogp"), localized_plan(plan, language))
        # Render the saved content itself, including its stable sprite seed IDs.
        manager.load(scene, BUNDLED_EXAMPLES / (slug + ".ogp"), as_template=True)
        meta = METADATA[slug] | {
            "license": "CC-BY-SA-4.0",
            "attribution": "Open Garden Planner contributors; CC-BY-SA-4.0; see PROVENANCE.md.",
            "attribution_en": "Open Garden Planner contributors; bundled CC-BY-SA-4.0 species data; see PROVENANCE.md.",
            "attribution_de": "Mitwirkende von Open Garden Planner; mitgelieferte Artendaten unter CC-BY-SA-4.0; siehe PROVENANCE.md.",
            "attribution_es": "Colaboradores de Open Garden Planner; datos de especies incluidos bajo CC-BY-SA-4.0; véase PROVENANCE.md.",
        }
        (BUNDLED_EXAMPLES / (slug + ".meta.json")).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        assert image.save(str(BUNDLED_EXAMPLES / (slug + ".png")))
        scene.clear()
    app.processEvents()


if __name__ == "__main__":
    main()
