"""The balcony: herb troughs, furniture and three kinds of shadow."""

from __future__ import annotations

from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.geometry_apply import apply_rotation
from open_garden_planner.ui.canvas.items import CircleItem

from . import authoring as a
from .i18n import text

SLUG = "balcony"
IDS = "serial"

META = {
    "name_en": "Balcony herb containers", "name_de": "Balkon mit Kräutergefäßen",
    "name_es": "Macetas de hierbas en el balcón",
    "name_ru": "Балкон с контейнерами для трав",
    "description_en": "A furnished 5 x 3 m balcony: 4 basil, 6 parsley and 4 thyme plants, three rails, a north wall and a parasol. Soil-test and shadow tutorial; Freiburg reference. Opens on its teaching date, 21 September 2026, in daylight. Illustrative layout; check the site's light and load limits.",
    "description_de": "Ein möblierter 5 x 3 m Balkon: 4 Basilikum-, 6 Petersilien- und 4 Thymianpflanzen, drei Geländerseiten, Nordwand und Schirm. Bodentest- und Schattenübung; Referenz Freiburg. Öffnet am Übungsdatum, dem 21. September 2026, bei Tageslicht. Beispielentwurf; Licht und Tragfähigkeit vor Ort prüfen.",
    "description_es": "Un balcón amueblado de 5 x 3 m: 4 albahacas, 6 perejiles y 4 tomillos, tres barandillas, pared norte y sombrilla. Tutorial de suelo y sombras; referencia Friburgo. Se abre en su fecha didáctica, el 21 de septiembre de 2026, con luz de día. Diseño ilustrativo; compruebe la luz y la capacidad de carga del lugar.",
    "description_ru": "Обустроенный балкон 5 x 3 м: 4 базилика, 6 петрушек и 4 тимьяна, три ограждения, северная стена и зонт. Обучение анализу почвы и теням; координаты Фрайбурга. Открывается на учебную дату, 21 сентября 2026 года, при дневном свете. Пример планировки; проверьте освещенность и допустимую нагрузку на месте.",
    "order": 13,
    "tags": ["balcony", "containers", "herbs"],
    "showcase_date": a.TEACHING_DATE, "showcase_utc_time": a.SHOWCASE_UTC_TIME,
}


def build():
    scene = CanvasScene(width_cm=500, height_cm=300)
    scene.active_layer.name = text("Balcony garden", "Balkongarten", "Huerto de balcón")
    a.rect(scene, 0, 0, 500, 300, ObjectType.TERRACE_PATIO, text("Balcony 5 x 3 m", "Balkon 5 x 3 m", "Balcón 5 x 3 m"))
    # North wall; east, south and west rails. Geometry remains a balcony, not a house footprint.
    a.line(scene, [(8, 292), (492, 292)], ObjectType.WALL,
          text("North house wall", "Nördliche Hauswand", "Pared norte de la casa"), 260)
    a.line(scene, [(8, 285), (8, 8), (492, 8), (492, 285)], ObjectType.FENCE,
          text("Three balcony rails", "Dreiseitiges Balkongeländer", "Barandilla en tres lados"), 110, PathFenceStyle.METAL_FENCE)
    pots = []
    for x, width, key, count, spacing, name in [
        (25, 110, "ocimum basilicum", 4, 40, text("Basil: moist compost", "Basilikum: feuchtes Substrat", "Albahaca: sustrato húmedo")),
        (170, 110, "petroselinum crispum", 6, 30, text("Parsley: moist compost", "Petersilie: feuchtes Substrat", "Perejil: sustrato húmedo")),
        (325, 110, "thymus vulgaris", 4, 40, text("Thyme: free-draining compost", "Thymian: durchlässiges Substrat", "Tomillo: sustrato drenante"))]:
        pot = a.rect(scene, x, 35, width, 90, ObjectType.CONTAINER, name, 35)
        pot.metadata["container_material"] = "wood"
        columns = 3 if count == 6 else 2
        for row in range(2):
            for column in range(columns):
                a.plant(scene, key, x + (width - (columns - 1) * spacing) / 2 + column * spacing,
                       60 + row * 40, parent=pot, planted={"thymus vulgaris": "2023-05-20", "petroselinum crispum": "2026-08-20", "ocimum basilicum": "2026-05-20"}[key])
        pots.append(pot)
    a.rect(scene, 175, 205, 100, 65, ObjectType.TABLE_RECTANGULAR,
          text("Breakfast table", "Frühstückstisch", "Mesa de desayuno"))
    for x in (120, 292):
        chair = a.rect(scene, x, 215, 42, 42, ObjectType.CHAIR,
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
    a.site(manager, "Freiburg im Breisgau", 47.9990, 7.8421)
    a.soil(manager, pots[0])
    a.note(scene, 20, 196, text(
        "21 Sep 2026 · 4 basil / 6 parsley / 4 thyme.\nWater separately. Basil trough → Soil Test: fictional sample.\nFreiburg / frost: demo data. Plan & Sun → 21 June, 15:00.\nCompare wall, rails and parasol shadows.",
        "21.09.2026 · 4 Basilikum / 6 Petersilien / 4 Thymiane.\nGetrennt gießen. Basilikumtrog → Bodentest: Übungsprobe.\nFreiburg / Frost: fiktiv. Plan & Sonne → 21. Juni, 15 Uhr.\nWand, Geländer und Schirm vergleichen.",
        "21 sep 2026 · 4 albahacas / 6 perejiles / 4 tomillos.\nRiego separado. Albahaca → Análisis de suelo: ficticio.\nFriburgo / heladas: ejemplo. Plan y sol → 21 junio, 15:00.\nComparar pared, barandilla y sombrilla."), 0.24, layer=a.hint_layer(scene, SLUG))
    for key, entries in (
        ("ocimum basilicum", [("2026-06-28", 1, "bunch", a.FIRST_PICK), ("2026-07-19", 2, "bunch", a.AROMATIC),
                              ("2026-08-15", 2, "bunch"), ("2026-09-06", 1, "bunch")]),
        ("thymus vulgaris", [("2025-06-14", 2, "bunch"), ("2025-08-23", 1, "bunch"),
                             ("2026-06-06", 2, "bunch", a.AROMATIC), ("2026-08-29", 1, "bunch")]),
        ("petroselinum crispum", [("2026-09-14", 1, "bunch", a.FIRST_PICK)]),
    ):
        a.harvest(manager, "balcony", a.first(scene, key), entries)
    return scene, manager
