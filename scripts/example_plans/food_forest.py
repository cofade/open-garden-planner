"""The food forest: established trees, an apple guild, mulched beds and harvest paths."""

from __future__ import annotations

from copy import deepcopy
from uuid import NAMESPACE_URL, uuid5

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.guild_commands import GuildMembershipCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.layer import Layer
from open_garden_planner.models.plant_data import PermacultureLayer
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

from . import authoring as a
from .i18n import text

SLUG = "food-forest"

META = {
    "name_en": "Food forest - 200 m²", "name_de": "Waldgarten - 200 m²",
    "name_es": "Bosque comestible - 200 m²",
    "name_ru": "Лесосад - 200 м²",
    "description_en": "Established trees, a grouped apple guild, accessible mulched beds and a sunny edible edge. Opens on 21 September 2026 in daylight; Bonn reference coordinates, fictional frost dates and harvest log. Illustrative layout; adapt species and spacing to your site.",
    "description_de": "Alte Bäume, eine Apfelgilde in Pflanzgruppen, gemulchte Beete mit Erntewegen und ein sonniger essbarer Saum. Öffnet am 21. September 2026 bei Tageslicht; Referenzkoordinaten Bonn, fiktive Frostdaten und fiktives Erntebuch. Beispielentwurf; Arten und Abstände an den Standort anpassen.",
    "description_es": "Árboles establecidos, un gremio de manzano en grupos y bancales acolchados con acceso. Se abre el 21 de septiembre de 2026 con luz de día; coordenadas de referencia de Bonn, heladas y cosechas ficticias. Diseño ilustrativo; adapte especies y distancias al lugar.",
    "description_ru": "Взрослые деревья, гильдия яблони в группах посадки, мульчированные грядки с проходами и солнечная съедобная опушка. Открывается на 21 сентября 2026 года при дневном свете; координаты Бонна, условные даты заморозков и условный журнал урожая. Пример планировки; адаптируйте виды и расстояния под ваш участок.",
    "tags": ["food-forest", "guild", "timeline"],
    "showcase_date": a.TEACHING_DATE, "showcase_utc_time": a.SHOWCASE_UTC_TIME,
}


def build():
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
    a.rect(scene, 0, 0, 2000, 1000, ObjectType.LAWN,
          text("Forest garden", "Waldgarten", "Bosque comestible"))
    main_bed = a.rect(scene, 70, 330, 1860, 600, ObjectType.GARDEN_BED,
                     text("Continuous mulched tree bed", "Zusammenhängendes gemulchtes Baumbeet", "Bancal continuo de árboles con acolchado"))
    main_bed.fill_pattern = FillPattern.MULCH
    main_bed.setBrush(create_pattern_brush(main_bed.fill_pattern, main_bed.fill_color))
    front_bed = a.rect(scene, 70, 110, 1860, 140, ObjectType.GARDEN_BED,
                      text("Sunny edible edge", "Sonniger essbarer Saum", "Borde comestible soleado"))
    a.rect(scene, 70, 250, 1860, 80, ObjectType.PATH,
          text("80 cm harvest path", "80 cm Ernteweg", "Sendero de cosecha de 80 cm"))
    a.rect(scene, 1080, 330, 90, 600, ObjectType.PATH,
          text("90 cm access between trees", "90 cm Zugang zwischen den Bäumen", "Acceso de 90 cm entre árboles"))
    apple = a.plant(scene, "malus domestica", 550, 650, parent=main_bed, layer=layers[0], planted="2014-11-15", nursery_size=(120, 70))
    a.plant(scene, "prunus persica", 1470, 650, parent=main_bed, layer=layers[1], planted="2016-03-15", nursery_size=(140, 80))
    for x in (180, 950, 1800):
        a.plant(scene, "ribes rubrum", x, 650, parent=main_bed, layer=layers[2], planted="2019-11-10", nursery_size=(40, 30))
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
                plant = a.plant(scene, "fragaria ananassa", origin_x + 60 * column, y,
                               parent=main_bed, layer=layers[4], planted="2024-04-15")
                if origin_x == 350:
                    changes.append((plant, {"guild_id": guild_id, "role": "ground_cover"}))
    for origin_x in (130, 850, 1660):
        for row in range(2):
            for column in range(2):
                a.plant(scene, "allium schoenoprasum", origin_x + 35 * column, 390 + 35 * row,
                       parent=main_bed, layer=layers[3], planted="2021-04-15")
    for x in (180, 250, 880, 950, 1730, 1800):
        plant = a.plant(scene, "borago officinalis", x, 185, parent=front_bed, layer=layers[3])
    for x in (230, 300):
        for y in (475, 545):
            plant = a.plant(scene, "borago officinalis", x, y, parent=main_bed, layer=layers[3])
            changes.append((plant, {"guild_id": guild_id, "role": "pollinator_attractor"}))
    for row in range(3):
        for column in range(20):
            a.plant(scene, "daucus carota", 370 + 20 * column, 145 + 35 * row,
                   parent=front_bed, layer=layers[5], planted="2026-06-15")
    # The support is outside the apple crown, in the same bed and beside the harvest path.
    trellis = a.rect(scene, 860, 480, 200, 70, ObjectType.TRELLIS,
                    text("Bean support", "Bohnenrankhilfe", "Soporte de judías"), 220)
    for x in (890, 950, 1010):
        plant = a.plant(scene, "phaseolus coccineus", x, 515, parent=trellis, layer=layers[6])
    GuildMembershipCommand(changes).execute()
    a.rect(scene, 1200, 145, 150, 55, ObjectType.BENCH, text("Harvest bench", "Erntebank", "Banco de cosecha"))
    a.note(scene, 70, 95, text(
        "21 Sep 2026 · 1  Apple guild: select apple → Guilds; inspect grouped plants and the unfilled fixer role.\n2  Plan & Sun: scrub 2014–2026; inspect the established trees (planted 2014 / 2016).\n3  Hours of Sun: compare the south edge with the tree shade. Bonn reference; frost dates are fictional.",
        "21.09.2026 · 1  Apfelgilde: Apfelbaum → Gilden; Pflanzgruppen und die unbesetzte Stickstoffbinder-Rolle prüfen.\n2  Plan & Sonne: 2014–2026 durchgehen; alte Bäume prüfen (gepflanzt 2014 / 2016).\n3  Sonnenstunden: Südsaum mit Baumschatten vergleichen. Referenz Bonn; Frostdaten sind fiktiv.",
        "21 sep 2026 · 1  Gremio: manzano → Gremios; observe los grupos y el rol de fijador sin cubrir.\n2  Plan y sol: recorra 2014–2026; observe los árboles establecidos (plantados en 2014 / 2016).\n3  Horas de sol: compare el borde sur y la sombra. Referencia Bonn; heladas ficticias."), 0.65, a.NOTE_ON_LAWN, bold=True)
    manager = ProjectManager()
    a.site(manager, "Bonn", 50.7374, 7.0982)
    # Two seasons of the perennials, one of this year's sowings; nothing after 21 September.
    for key, entries in (
        ("malus domestica", [("2025-09-20", 38, "kg"), ("2025-10-04", 22, "kg", a.SWEET),
                             ("2026-09-12", 31, "kg", a.FIRST_PICK)]),
        ("prunus persica", [("2025-08-16", 14, "kg"), ("2026-08-12", 9, "kg", a.SWEET),
                            ("2026-08-22", 7.5, "kg")]),
        ("ribes rubrum", [("2025-07-06", 3.2, "kg"), ("2026-07-04", 2.8, "kg"),
                          ("2026-07-11", 1.6, "kg")]),
        ("fragaria ananassa", [("2025-06-10", 1.8, "kg"), ("2025-06-20", 2.4, "kg", a.SWEET),
                               ("2026-06-08", 2.1, "kg"), ("2026-06-17", 2.9, "kg", a.AROMATIC)]),
        ("phaseolus coccineus", [("2026-08-05", 1.2, "kg", a.TENDER), ("2026-08-26", 1.9, "kg"),
                                 ("2026-09-14", 1.1, "kg")]),
        ("allium schoenoprasum", [("2025-05-10", 4, "bunch"), ("2026-05-02", 3, "bunch"),
                                  ("2026-07-25", 2, "bunch")]),
        ("daucus carota", [("2026-09-18", 1.4, "kg", a.THINNINGS)]),
    ):
        a.harvest(manager, "food-forest", a.first(scene, key), entries)
    return scene, manager
