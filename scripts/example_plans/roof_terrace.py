"""The roof terrace: a garden that stands in containers.

A timber deck on a city roof with a parapet on three sides and a railing to the view.
Everything green grows in troughs, tubs, wall planters and one raised bed, so the plan
shows the container side: a plant belongs to its vessel, and a vessel has its own soil.
"""

from __future__ import annotations

from . import authoring as a
from .i18n import text
from .plan import FillPattern, ObjectType, PathFenceStyle, Plan

SLUG = "roof-terrace"
#: The stored orbit looks down more steeply than the dialog's 18 degrees: from there
#: the parapet hid the garden behind it (3D review of #940).
ORBIT_PITCH_DEG = 26.0

META = {
    "name_en": "Roof terrace - 10 x 8 m", "name_de": "Dachterrasse - 10 x 8 m",
    "name_es": "Azotea - 10 x 8 m",
    "name_ru": "Терраса на крыше - 10 x 8 м",
    "description_en": "A timber deck on a city roof: herb troughs along the railing, an olive and a fig in tubs, wall planters with strawberries, a raised bed with tomatoes, a climber on a trellis. Picnic table, two loungers, a parasol and a string of lights. Every plant belongs to its container; the raised bed has a fictional soil sample. Vienna reference; opens on 12 July 2026 in daylight. Illustrative layout; check the roof's load limits.",
    "description_de": "Ein Holzdeck auf einem Stadtdach: Kräutertröge am Geländer, eine Olive und eine Feige im Kübel, Wandpflanzgefäße mit Erdbeeren, ein Hochbeet mit Tomaten, eine Kletterpflanze am Spalier. Picknicktisch, zwei Liegen, Sonnenschirm und Lichterkette. Jede Pflanze gehört zu ihrem Gefäß; das Hochbeet hat eine fiktive Bodenprobe. Referenz Wien; öffnet am 12. Juli 2026 bei Tageslicht. Beispielentwurf; Tragfähigkeit des Dachs prüfen.",
    "description_es": "Una tarima de madera en una azotea: jardineras de hierbas junto a la barandilla, un olivo y una higuera en macetones, jardineras de pared con fresas, un bancal elevado con tomates y una trepadora en una espaldera. Mesa de pícnic, dos tumbonas, sombrilla y guirnalda de luces. Cada planta pertenece a su recipiente; el bancal tiene una muestra de suelo ficticia. Referencia Viena; se abre el 12 de julio de 2026 con luz de día. Diseño ilustrativo; compruebe la capacidad de carga.",
    "description_ru": "Деревянный настил на городской крыше: ящики с травами вдоль ограждения, олива и инжир в кадках, настенные кашпо с клубникой, высокая грядка с томатами, вьющееся растение на шпалере. Стол для пикника, два шезлонга, зонт и гирлянда. Каждое растение принадлежит своему контейнеру; у высокой грядки условный образец почвы. Ориентир: Вена; открывается 12 июля 2026 года при дневном свете. Примерный проект; проверьте допустимую нагрузку на крышу.",
    "order": 11,
    "tags": ["roof-terrace", "containers", "city"],
    "showcase_date": "2026-07-12", "showcase_utc_time": "08:30",
}


def build():
    T, plan = ObjectType, Plan(SLUG, 1000, 800, layer=text("Roof terrace", "Dachterrasse", "Azotea"),
                               planted="2026-04-18")
    plan.site("vienna")
    plan.rect(0, 0, 1000, 800, T.TERRACE_PATIO, text("Roof deck", "Dachdeck", "Tarima de azotea"),
              fill=FillPattern.DECKING)
    plan.line([(8, 8), (8, 792), (992, 792), (992, 8)], T.WALL,
              text("Parapet", "Brüstung", "Antepecho"), style=PathFenceStyle.STONE_WALL, tall=110)
    plan.line([(8, 8), (992, 8)], T.FENCE, text("Railing", "Geländer", "Barandilla"),
              style=PathFenceStyle.METAL_FENCE, tall=110)
    plan.shed(20, 560, 250, 225, T.GARAGE_SHED, text("Stair house", "Treppenhaus", "Caja de escalera"),
              tall=260, roof="flat", fill=FillPattern.CONCRETE)

    # ── herb troughs along the railing
    # shrubby herbs came as young plants this spring; thyme and strawberries are in their third year
    for x, name, key, count, size, planted in (
            (60, text("Lavender trough", "Lavendeltrog", "Jardinera de lavanda"),
             "lavandula angustifolia", 3, (40, 50), None),
            (300, text("Rosemary trough", "Rosmarintrog", "Jardinera de romero"),
             "rosmarinus officinalis", 3, (55, 50), None),
            (540, text("Thyme trough", "Thymiantrog", "Jardinera de tomillo"),
             "thymus vulgaris", 4, None, "2024-04-20"),
            (780, text("Strawberry trough", "Erdbeertrog", "Jardinera de fresas"),
             "fragaria ananassa", 3, None, "2024-04-20")):
        trough = plan.rect(x, 30, 190, 65, T.CONTAINER, name, tall=50, meta={"container_material": "wood"})
        plan.row(key, (x + 35, 62), (x + 155, 62), count, parent=trough, size=size, planted=planted)

    # ── two trees in tubs, a raised bed, the wall planters, a climber
    tub = text("Tub", "Kübel", "Macetón")
    olive_tub = plan.circle(620, 665, 42, T.CONTAINER_ROUND, tub, tall=60)
    plan.plant("olea europaea", 620, 665, parent=olive_tub, size=(170, 110))
    fig_tub = plan.circle(360, 700, 42, T.CONTAINER_ROUND, tub, tall=60)
    plan.plant("ficus carica", 360, 700, parent=fig_tub, size=(150, 120))
    bed = plan.rect(700, 420, 230, 95, T.RAISED_BED, text("Raised bed", "Hochbeet", "Bancal elevado"), tall=60)
    plan.row("solanum lycopersicum", (745, 480), (885, 480), 2, parent=bed, planted="2026-05-16", size=(60, 55))
    plan.row("ocimum basilicum", (730, 440), (900, 440), 4, parent=bed, planted="2026-05-16")
    plan.soil(bed, ph=6.4, day="2026-04-25", texture="loamy")
    planter = text("Wall planter", "Wandpflanzgefäß", "Jardinera de pared")
    for x, key in ((330, "petroselinum crispum"), (520, "allium schoenoprasum"), (710, "lactuca sativa")):
        box = plan.rect(x, 750, 150, 32, T.WALL_PLANTER, planter, tall=90)
        plan.row(key, (x + 30, 766), (x + 120, 766), 3, parent=box, planted="2026-05-02")
    trellis = plan.rect(950, 250, 30, 260, T.TRELLIS, text("Trellis", "Rankgitter", "Espaldera"), tall=200)
    plan.row("clematis vitalba", (965, 310), (965, 450), 2, parent=trellis, size=(180, 60))

    # ── the living room under the sky
    plan.rect(330, 330, 190, 150, T.PICNIC_TABLE, text("Picnic table", "Picknicktisch", "Mesa de pícnic"))
    lounger = text("Lounger", "Liege", "Tumbona")
    plan.rect(700, 150, 65, 190, T.LOUNGER, lounger)
    plan.rect(800, 150, 65, 190, T.LOUNGER, lounger)
    plan.circle(782, 245, 125, T.PARASOL, text("Parasol", "Sonnenschirm", "Sombrilla"), tall=240)
    plan.line([(290, 579), (950, 579)], T.STRING_LIGHTS,
              text("String of lights", "Lichterkette", "Guirnalda de luces"), tall=230)
    lantern = text("Lantern", "Laterne", "Farol")
    plan.circle(60, 130, 12, T.GARDEN_LIGHT, lantern)
    plan.circle(940, 130, 12, T.GARDEN_LIGHT, lantern)
    for x in (120, 200):
        clay = plan.circle(x + 27.5, 467.5, 28, T.CONTAINER_ROUND, text("Planter pot", "Pflanztopf", "Maceta"),
                           tall=35, meta={"container_material": "terracotta"})
        plan.plant("pelargonium x hortorum", x + 27.5, 467.5, parent=clay, size=(35, 40))

    plan.hint(40, 262, text(
        "12 Jul 2026 · 1  Drag a plant out of its trough: it leaves the container. Drop it back: it belongs again.\n"
        "2  Right-click the raised bed → Soil Test: a container has its own soil (fictional sample).\n"
        "3  Plan & Sun: move the clock into the evening and the lanterns come on in 3D. Vienna; records are fictional.",
        "12.07.2026 · 1  Pflanze aus dem Trog ziehen: sie verlässt das Gefäß. Zurücklegen: sie gehört wieder dazu.\n"
        "2  Rechtsklick aufs Hochbeet → Bodentest: ein Gefäß hat seine eigene Erde (fiktive Probe).\n"
        "3  Plan & Sonne: Uhr auf den Abend stellen, in 3D gehen die Laternen an. Wien; Einträge sind fiktiv.",
        "12 jul 2026 · 1  Arrastre una planta fuera de su jardinera: deja el recipiente. Suéltela dentro y vuelve a pertenecer.\n"
        "2  Clic derecho en el bancal → Análisis de suelo: un recipiente tiene su propia tierra (muestra ficticia).\n"
        "3  Plan y sol: lleve el reloj a la tarde y los faroles se encienden en 3D. Viena; registros ficticios."),
        size=0.34)

    for key, entries in (
        ("fragaria ananassa", [("2025-06-18", 0.5, "kg"), ("2026-06-12", 0.7, "kg", a.SWEET),
                               ("2026-06-24", 0.4, "kg")]),
        ("ocimum basilicum", [("2026-06-20", 1, "bunch", a.FIRST_PICK), ("2026-07-05", 2, "bunch", a.AROMATIC)]),
        ("lactuca sativa", [("2026-06-10", 150, "g", a.OUTER_LEAVES), ("2026-06-28", 200, "g", a.CRISP)]),
        ("thymus vulgaris", [("2025-06-08", 1, "bunch"), ("2026-06-06", 2, "bunch", a.AROMATIC)]),
    ):
        plan.harvest(key, entries)
    return plan.done()
