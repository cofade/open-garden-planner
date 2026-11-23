"""The raised bed: a dense polyculture with a succession plan and a soil sample."""

from __future__ import annotations

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.succession import SuccessionEntry, SuccessionPlan
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

from . import authoring as a
from .i18n import text

SLUG = "raised-bed"
IDS = "serial"

META = {
    "name_en": "Raised-bed polyculture - 4 x 2 m", "name_de": "Hochbeet-Mischkultur - 4 x 2 m",
    "name_es": "Policultivo en bancal elevado - 4 x 2 m",
    "name_ru": "Поликультура в высокой грядке - 4 x 2 м",
    "name_fr": "Polyculture en bac surélevé - 4 x 2 m",
    "description_en": "164 crops in a 4 x 2 m bed: 16 lettuces, 60 carrots and 88 radishes. Autumn crops, a 2027 succession, a fictional soil sample and harvest log. Opens on 21 September 2026 in daylight; Berlin reference. Dates are illustrative calendar dates, not a local frost forecast.",
    "description_de": "164 Pflanzen im 4 x 2 m Beet: 16 Salate, 60 Möhren und 88 Radieschen. Herbstbestand, Nachfolgeplan 2027, fiktive Bodenprobe und fiktives Erntebuch. Öffnet am 21. September 2026 bei Tageslicht; Referenz Berlin. Die Beispieldaten sind Kalenderdaten, keine lokale Frostprognose.",
    "description_es": "164 plantas en un bancal de 4 x 2 m: 16 lechugas, 60 zanahorias y 88 rábanos. Sucesión de 2027, muestra de suelo y cosechas ficticias. Se abre el 21 de septiembre de 2026 con luz de día; referencia Berlín. Las fechas son ejemplos de calendario, no una previsión local de heladas.",
    "description_ru": "164 культуры на грядке 4 x 2 м: 16 салатов, 60 морковей и 88 редисов. Осенние посадки, севооборот на 2027 год, условные образец почвы и журнал урожая. Открывается на 21 сентября 2026 года при дневном свете; координаты Берлина. Указаны примерные календарные даты, а не прогноз местных заморозков.",
    "description_fr": "164 cultures dans un bac de 4 x 2 m : 16 laitues, 60 carottes et 88 radis. Cultures d’automne, une succession 2027, un échantillon de sol et un journal de récolte fictifs. S’ouvre le 21 septembre 2026 en plein jour ; référence : Berlin. Les dates sont des dates de calendrier illustratives, pas une prévision locale de gel.",
    "order": 12,
    "tags": ["raised-bed", "polyculture", "succession"],
    "showcase_date": a.TEACHING_DATE, "showcase_utc_time": a.SHOWCASE_UTC_TIME,
}


def build():
    scene = CanvasScene(width_cm=900, height_cm=650)
    scene.active_layer.name = text("Kitchen garden", "Küchengarten", "Huerto de cocina")
    a.rect(scene, 0, 0, 900, 650, ObjectType.LAWN, text("Kitchen garden lawn", "Küchengartenrasen", "Césped del huerto"))
    a.rect(scene, 135, 165, 550, 330, ObjectType.PATH, text("Harvest access", "Erntezugang", "Acceso de cosecha"))
    bed = a.rect(scene, 210, 230, 400, 200, ObjectType.RAISED_BED,
                text("1  Polyculture 4 x 2 m", "1  Mischkultur 4 x 2 m", "1  Policultivo 4 x 2 m"), 45)
    # Sprite soil: x=11/120..109/120, y=11/80..69/80 of the full footprint.
    # These mature circles fit the stricter 2D inset, also clearing the 5 cm 3D planks.
    for row in range(4):
        for column in range(4):
            a.plant(scene, "lactuca sativa", 265 + 30 * column, 280 + 30 * row, parent=bed, planted="2026-08-01")
    for row in range(6):
        for column in range(10):
            a.plant(scene, "daucus carota", 390 + 10 * column, 270 + 25 * row, parent=bed, planted="2026-06-15")
    for row in range(11):
        for column in range(8):
            a.plant(scene, "raphanus sativus", 495 + 10 * column, 265 + 13 * row, parent=bed, planted="2026-08-20")
    border = a.rect(scene, 710, 180, 130, 310, ObjectType.GARDEN_BED,
                   text("Pollinator and kitchen border", "Blühender Küchensaum", "Borde de flores y hierbas"))
    for y in (215, 275, 335, 395, 455):
        for x, key in ((745, "calendula officinalis"), (805, "allium schoenoprasum")):
            a.plant(scene, key, x, y, parent=border, planted="2023-04-15" if x == 805 else "2026-05-20")
    a.rect(scene, 70, 535, 150, 55, ObjectType.BENCH, text("Garden bench", "Gartenbank", "Banco de jardín"))
    a.rect(scene, 15, 240, 120, 100, ObjectType.TOOL_SHED,
          text("Tool shed: afternoon shadow", "Geräteschuppen: Nachmittagsschatten", "Caseta: sombra de tarde"), 210)
    a.rect(scene, 270, 535, 90, 80, ObjectType.COMPOST_BIN, text("Compost", "Kompost", "Compostador"), 90)
    entries = [SuccessionEntry(species_key=key, common_name=name, scientific_name=key,
                              start_date=start, end_date=end)
               for key, name, start, end in [
                   ("raphanus sativus", "Radish", "2027-03-15", "2027-05-15"),
                   ("phaseolus vulgaris", "Bean (Bush)", "2027-06-01", "2027-08-31"),
                   ("lactuca sativa", "Lettuce", "2027-09-01", "2027-10-31")]]
    manager = ProjectManager()
    manager.set_succession_plan(str(bed.item_id), SuccessionPlan(str(bed.item_id), 2027, entries).to_dict())
    a.soil(manager, bed)
    a.site(manager, "Berlin", 52.5200, 13.4050)
    a.note(scene, 80, 145, text(
        "21 Sep 2026 · 1  16 lettuces + 60 carrots + 88 radishes; sow radish sections in batches.\n2  Right-click the bed: Succession Plan (2027), then Soil Test (fictional sample).\n3  Plan & Sun: 21 Sep, 17:30 → shed shade on the bed. Berlin / frost: demo data.",
        "21.09.2026 · 1  16 Salate + 60 Möhren + 88 Radieschen; Radieschen abschnittsweise säen.\n2  Rechtsklick aufs Beet: Nachfolgeplanung (2027), dann Bodentest (fiktive Probe).\n3  Plan & Sonne: 21.09., 17:30 Uhr → Beetschatten. Berlin / Frost: Beispieldaten.",
        "21 sep 2026 · 1  16 lechugas + 60 zanahorias + 88 rábanos; siembre rábanos por tandas.\n2  Clic derecho en bancal: sucesión (2027), después análisis de suelo (muestra ficticia).\n3  Plano y sol: 21 sep, 17:30 → sombra sobre el bancal. Berlín / heladas: ejemplo."), 0.47, a.NOTE_ON_LAWN, bold=True, layer=a.hint_layer(scene, SLUG))
    # The bed stays fully planted on 21 September: what was taken so far are leaves and
    # thinnings, and the border's perennial chives have a season behind them.
    for key, entries in (
        ("lactuca sativa", [("2026-09-05", 350, "g", a.OUTER_LEAVES), ("2026-09-16", 420, "g", a.CRISP)]),
        ("daucus carota", [("2026-09-10", 1.1, "kg", a.THINNINGS), ("2026-09-19", 1.6, "kg", a.SWEET)]),
        ("allium schoenoprasum", [("2025-05-18", 3, "bunch"), ("2025-08-09", 2, "bunch"),
                                  ("2026-04-28", 2, "bunch"), ("2026-06-15", 2, "bunch"),
                                  ("2026-08-30", 1, "bunch")]),
        ("calendula officinalis", [("2026-07-12", 30, "pcs", a.PETALS), ("2026-08-18", 25, "pcs")]),
    ):
        a.harvest(manager, "raised-bed", a.first(scene, key), entries)
    return scene, manager
