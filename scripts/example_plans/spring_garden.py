"""The spring garden: a garden seen on one April day, and through one year.

Crocus and daffodils drift through the lawn, tulips line the terrace, and magnolia,
cherry, plum and apple stand in blossom. The plan shows the time side: the same garden
looks different on every date, and a stored tour runs the whole year past a still camera.
"""

from __future__ import annotations

from datetime import date

from . import authoring as a
from .i18n import text
from .plan import FillPattern, ObjectType, PathFenceStyle, Plan
from .tours import held_tour

SLUG = "spring-garden"
YEAR = text("A year in the garden", "Ein Jahr im Garten", "Un año en el jardín")
#: The bulbs went into the ground in the autumn before, and the woody plants were moved
#: here then at the size they have: they stand, bare, when the year's time-lapse starts.
BULBS = "2025-10-11"
WOODY = "2025-10-25"

META = {
    "name_en": "Spring garden - 14 x 10 m", "name_de": "Frühlingsgarten - 14 x 10 m",
    "name_es": "Jardín de primavera - 14 x 10 m",
    "name_ru": "Весенний сад - 14 x 10 м",
    "description_en": "A garden on an April day: crocus and daffodils in the lawn, two tulip beds by the terrace, magnolia, cherry, plum and apple in blossom, forsythia along the fence. Open the 3D view to see it flower, then scrub the date: the plan looks different in every month. A stored tour runs the year 2026 past a still camera. Heidelberg reference; opens on 18 April 2026 in daylight. Illustrative layout.",
    "description_de": "Ein Garten an einem Apriltag: Krokusse und Narzissen im Rasen, zwei Tulpenbeete an der Terrasse, Magnolie, Kirsche, Pflaume und Apfel in Blüte, Forsythien am Zaun. In der 3D-Ansicht blüht er; dann das Datum verschieben: der Plan sieht in jedem Monat anders aus. Eine gespeicherte Kamerafahrt zeigt das Jahr 2026 aus fester Position. Referenz Heidelberg; öffnet am 18. April 2026 bei Tageslicht. Beispielentwurf.",
    "description_es": "Un jardín en un día de abril: crocos y narcisos en el césped, dos parterres de tulipanes junto a la terraza, magnolio, cerezo, ciruelo y manzano en flor, forsitias junto a la valla. Abra la vista 3D para verlo florecer y mueva la fecha: el plan cambia cada mes. Un recorrido guardado muestra el año 2026 con la cámara fija. Referencia Heidelberg; se abre el 18 de abril de 2026 con luz de día. Diseño ilustrativo.",
    "description_ru": "Сад в апрельский день: крокусы и нарциссы на газоне, две клумбы тюльпанов у террасы, магнолия, черешня, слива и яблоня в цвету, форзиция вдоль забора. Откройте 3D-вид, чтобы увидеть цветение, затем меняйте дату: план выглядит по-разному в каждом месяце. Сохранённый облёт показывает 2026 год с неподвижной камеры. Ориентир: Гейдельберг; открывается 18 апреля 2026 года при дневном свете. Примерный проект.",
    "order": 7,
    "tags": ["spring", "bulbs", "timeline"],
    "showcase_date": "2026-04-18", "showcase_utc_time": "11:00",
}


def more_tours(framing):
    """From the south end towards the terrace while the year 2026 passes."""
    return [held_tour(framing.pose(8.0, 26.0), YEAR, date_range=(date(2026, 1, 10), date(2026, 12, 20)))]


def build():
    T, plan = ObjectType, Plan(SLUG, 1400, 1000, layer=text("Garden", "Garten", "Jardín"))
    plan.site("heidelberg")
    lawn = text("Lawn", "Rasen", "Césped")
    plan.rect(0, 0, 1400, 1000, T.LAWN, lawn)
    plan.line([(10, 990), (1390, 990)], T.WALL, text("Garden wall", "Gartenmauer", "Muro del jardín"),
              style=PathFenceStyle.STONE_WALL, tall=180)
    fence = text("Fence", "Zaun", "Valla")
    plan.line([(10, 990), (10, 10), (1390, 10), (1390, 990)], T.FENCE, fence,
              style=PathFenceStyle.WOODEN_FENCE, tall=120)
    plan.rect(350, 760, 700, 215, T.TERRACE_PATIO, text("Terrace", "Terrasse", "Terraza"),
              fill=FillPattern.FLAGSTONE)
    plan.line([(690, 60), (640, 230), (760, 440), (700, 640), (700, 760)], T.PATH,
              text("Gravel path", "Kiesweg", "Camino de grava"), style=PathFenceStyle.GRAVEL_PATH, wide=90)
    plan.rect(420, 900, 150, 50, T.BENCH, text("Bench", "Sitzbank", "Banco"))
    plan.circle(815, 905, 55, T.TABLE_ROUND, text("Table", "Tisch", "Mesa"))
    plan.rect(890, 882, 45, 45, T.CHAIR, text("Chair", "Stuhl", "Silla"), turn=-90)
    plan.rect(695, 882, 45, 45, T.CHAIR, "Chair", turn=90)
    plan.circle(520, 330, 26, T.BIRD_BATH, text("Bird bath", "Vogeltränke", "Bebedero de pájaros"))

    # ── the trees and shrubs: established for years, in blossom in April
    plan.plant("magnolia x soulangeana", 280, 540, planted=WOODY, size=(300, 270))
    plan.plant("prunus avium", 1110, 500, planted=WOODY, size=(480, 370))
    plan.plant("prunus domestica", 240, 230, planted=WOODY, size=(330, 270))
    plan.plant("malus domestica", 1150, 190, planted=WOODY, size=(340, 290))
    for y in (410, 550, 690, 830):
        plan.plant("forsythia x intermedia", 95, y, planted=WOODY, size=(150, 125))
    plan.plant("syringa vulgaris", 1300, 860, planted=WOODY, size=(220, 160))
    plan.plant("rhododendron ponticum", 1300, 700, planted=WOODY, size=(110, 110))

    # ── the bulbs: drifts in the lawn, tulips in two beds by the terrace
    plan.drift("crocus vernus", (410, 90, 190, 170), 34, gap=16, planted=BULBS)
    plan.drift("crocus vernus", (800, 250, 210, 150), 30, gap=16, seed="east", planted=BULBS)
    plan.drift("narcissus pseudonarcissus", (430, 390, 200, 230), 26, gap=30, planted=BULBS)
    plan.drift("narcissus pseudonarcissus", (800, 60, 180, 150), 18, gap=30, seed="gate", planted=BULBS)
    plan.drift("narcissus pseudonarcissus", (780, 470, 130, 180), 14, gap=30, seed="cherry", planted=BULBS)
    beds = []
    for x, name in ((360, text("West tulip bed", "Westliches Tulpenbeet", "Parterre de tulipanes oeste")),
                    (750, text("East tulip bed", "Östliches Tulpenbeet", "Parterre de tulipanes este"))):
        bed = plan.rect(x, 680, 290, 66, T.GARDEN_BED, name, fill=FillPattern.SOIL)
        plan.grid("tulipa gesneriana", x + 20, 698, 11, 2, 25, 30, parent=bed, planted=BULBS)
        beds.append(bed)
    plan.soil(beds[0], ph=6.8, day="2026-03-14")
    border = plan.rect(1090, 760, 150, 60, T.GARDEN_BED,
                       text("Pansy border", "Stiefmütterchenbeet", "Arriate de pensamientos"),
                       fill=FillPattern.SOIL)
    plan.grid("viola x wittrockiana", 1108, 776, 5, 2, 29, 28, parent=border, planted="2026-03-20")
    herbs = plan.rect(140, 800, 170, 60, T.GARDEN_BED, text("Herb patch", "Kräuterecke", "Rincón de hierbas"),
                      fill=FillPattern.SOIL)
    plan.row("allium schoenoprasum", (165, 830), (225, 830), 3, parent=herbs, planted="2023-04-22")
    plan.row("thymus vulgaris", (262, 830), (290, 830), 1, parent=herbs, planted="2023-04-22")
    rhubarb = plan.rect(1090, 840, 130, 130, T.GARDEN_BED,
                        text("Rhubarb corner", "Rhabarberecke", "Rincón del ruibarbo"), fill=FillPattern.SOIL)
    plan.plant("rheum rhabarbarum", 1155, 905, parent=rhubarb, planted="2022-04-09", size=(60, 90))

    plan.hint(362, 846, text(
        "18 Apr 2026 · 1  Open the 3D view: bulbs, magnolia and fruit trees flower today.\n"
        "2  Plan & Sun: scrub the date. By June the bulbs are leaves, by November the trees are bare.\n"
        "3  3D view → Camera Tour: play “A year in the garden”. Heidelberg; records are fictional.",
        "18.04.2026 · 1  3D-Ansicht öffnen: Zwiebelblumen, Magnolie und Obstbäume blühen heute.\n"
        "2  Plan & Sonne: Datum verschieben. Im Juni bleibt nur Laub, im November sind die Bäume kahl.\n"
        "3  3D-Ansicht → Kamerafahrt: „Ein Jahr im Garten“ abspielen. Heidelberg; Einträge sind fiktiv.",
        "18 abr 2026 · 1  Abra la vista 3D: bulbos, magnolio y frutales florecen hoy.\n"
        "2  Plan y sol: mueva la fecha. En junio quedan hojas, en noviembre los árboles están desnudos.\n"
        "3  Vista 3D → Recorrido de cámara: «Un año en el jardín». Heidelberg; registros ficticios."),
        size=0.4)

    for key, entries in (
        ("allium schoenoprasum", [("2025-05-03", 2, "bunch"), ("2025-08-16", 1, "bunch"),
                                  ("2026-04-11", 1, "bunch", a.FIRST_PICK)]),
        ("rheum rhabarbarum", [("2024-05-11", 1.2, "kg"), ("2025-05-09", 1.8, "kg", a.TENDER)]),
        ("thymus vulgaris", [("2025-06-14", 1, "bunch", a.AROMATIC), ("2025-08-30", 1, "bunch")]),
    ):
        plan.harvest(key, entries)
    return plan.done()
