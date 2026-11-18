"""The cottage garden: a formal four-square garden drawn to measure.

Cross paths, a roundel in the middle, four beds edged with box inside a picket fence:
vegetables, herbs and flowers mixed, as in a German Bauerngarten. It shows the drawing
side: two guide lines carry the axes and three distance constraints hold the measures.
"""

from __future__ import annotations

from . import authoring as a
from .i18n import text
from .plan import AnchorType, FillPattern, ObjectType, PathFenceStyle, Plan

SLUG = "cottage-garden"

META = {
    "name_en": "Cottage garden - 12 x 12 m", "name_de": "Bauerngarten - 12 x 12 m",
    "name_es": "Jardín campesino - 12 x 12 m",
    "name_ru": "Крестьянский сад - 12 x 12 м",
    "description_en": "A formal four-square garden inside a picket fence: gravel cross paths, a rose roundel, four beds edged with box. Vegetables, herbs and flowers are mixed. Guide lines mark the two axes and distance constraints hold the path and bed measures. Fictional harvest log. Bamberg reference; opens on 20 June 2026 in daylight. Illustrative layout.",
    "description_de": "Ein formaler Bauerngarten im Lattenzaun: Wegekreuz aus Kies, Rosenrondell, vier Beete mit Buchseinfassung. Gemüse, Kräuter und Blumen stehen gemischt. Hilfslinien markieren die beiden Achsen, Abstandsbedingungen halten Weg- und Beetmaße. Fiktives Erntebuch. Referenz Bamberg; öffnet am 20. Juni 2026 bei Tageslicht. Beispielentwurf.",
    "description_es": "Un jardín formal de cuatro cuadros dentro de una valla de listones: caminos de grava en cruz, un rondel de rosas, cuatro bancales con borde de boj. Hortalizas, hierbas y flores se mezclan. Las guías marcan los dos ejes y las restricciones de distancia fijan las medidas. Cosechas ficticias. Referencia Bamberg; se abre el 20 de junio de 2026 con luz de día. Diseño ilustrativo.",
    "description_ru": "Регулярный сад из четырёх квадратов за штакетником: гравийные дорожки крестом, розовая клумба в центре, четыре грядки с бордюром из самшита. Овощи, травы и цветы растут вперемешку. Направляющие отмечают две оси, а ограничения расстояний удерживают размеры дорожек и грядок. Условный журнал урожая. Ориентир: Бамберг; открывается 20 июня 2026 года при дневном свете. Примерный проект.",
    "order": 6,
    "tags": ["cottage-garden", "formal", "guides"],
    "showcase_date": "2026-06-20", "showcase_utc_time": "09:00",
}

#: The garden's centre, and the four beds as mirror images of the south-west one.
CX, CY = 600, 660


def build():
    T, plan = ObjectType, Plan(SLUG, 1200, 1200, layer=text("Cottage garden", "Bauerngarten", "Jardín campesino"))
    plan.site("bamberg")
    plan.rect(0, 0, 1200, 1200, T.LAWN, text("Meadow strip", "Wiesenstreifen", "Franja de pradera"))
    plan.rect(100, 160, 1000, 1000, T.TERRACE_PATIO, text("Gravel ground", "Kiesfläche", "Suelo de grava"),
              fill=FillPattern.GRAVEL)
    plan.line([(540, 160), (100, 160), (100, 1160), (1100, 1160), (1100, 160), (660, 160)], T.FENCE,
              text("Picket fence", "Lattenzaun", "Valla de listones"),
              style=PathFenceStyle.WOODEN_FENCE, tall=100)

    def mirrored(points, east, north):
        return [(CX + (x - CX) * (-1 if east else 1), CY + (y - CY) * (-1 if north else 1))
                for x, y in points]

    # one bed, drawn in the south-west and mirrored: the inner corner is cut for the roundel
    outline = [(140, 200), (530, 200), (530, 470), (410, 590), (140, 590)]
    names = {(False, False): text("Vegetable bed", "Gemüsebeet", "Bancal de hortalizas"),
             (True, False): text("Cabbage and leek bed", "Kohl- und Lauchbeet", "Bancal de coles y puerros"),
             (False, True): text("Flower bed", "Blumenbeet", "Parterre de flores"),
             (True, True): text("Herb and berry bed", "Kräuter- und Beerenbeet", "Bancal de hierbas y bayas")}
    beds, edges = {}, {}
    box = text("Box edging", "Buchseinfassung", "Borde de boj")
    for east in (False, True):
        for north in (False, True):
            beds[east, north] = plan.polygon(mirrored(outline, east, north), T.GARDEN_BED,
                                             names[east, north], fill=FillPattern.SOIL)
            # box along the two sides on the paths; the cut corner stays open
            (x0, y0), (x1, y1) = mirrored([(520, 200), (540, 470)], east, north)
            edges[east, north] = plan.rect(min(x0, x1), min(y0, y1), 20, 270, T.HEDGE_SECTION, box, tall=35)
            (x0, y0), (x1, y1) = mirrored([(140, 580), (410, 600)], east, north)
            plan.rect(min(x0, x1), min(y0, y1), 270, 20, T.HEDGE_SECTION, box, tall=35)

    # ── the roundel: a rose among lavender
    roundel = plan.polygon([(CX + dx, CY + dy) for dx, dy in (
        (110, 0), (95, 55), (55, 95), (0, 110), (-55, 95), (-95, 55), (-110, 0), (-95, -55),
        (-55, -95), (0, -110), (55, -95), (95, -55))], T.GARDEN_BED,
        text("Rose roundel", "Rosenrondell", "Rondel de rosas"), fill=FillPattern.SOIL)
    for dx, dy in ((80, 0), (40, 69), (-40, 69), (-80, 0), (-40, -69), (40, -69)):
        plan.plant("lavandula angustifolia", CX + dx, CY + dy, parent=roundel, size=(40, 44))
    plan.plant("rosa rugosa", CX, CY, parent=roundel, size=(130, 110))    # last: above the lavender
    bench = plan.rect(525, 1090, 150, 50, T.BENCH, text("Bench", "Sitzbank", "Banco"))

    # ── south-west: vegetables with marigolds
    bed = beds[False, False]
    plan.row("lactuca sativa", (180, 240), (480, 240), 7, parent=bed, planted="2026-05-05")
    plan.row("allium cepa", (170, 290), (490, 290), 12, parent=bed, planted="2026-03-28")
    plan.row("daucus carota", (165, 330), (495, 330), 18, parent=bed, planted="2026-04-12")
    plan.row("phaseolus vulgaris", (180, 385), (480, 385), 7, parent=bed, planted="2026-05-16")
    plan.row("tagetes erecta", (180, 450), (420, 450), 5, parent=bed, planted="2026-05-16")
    plan.row("beta vulgaris", (170, 520), (390, 520), 9, parent=bed, planted="2026-04-18")

    # ── south-east: cabbage, leek and nasturtium
    bed = beds[True, False]
    plan.row("brassica oleracea var. capitata", (735, 255), (1005, 255), 4, parent=bed, planted="2026-05-08")
    plan.row("brassica oleracea var. acephala", (720, 350), (1020, 350), 5, parent=bed, planted="2026-05-08")
    plan.row("allium porrum", (710, 420), (1030, 420), 12, parent=bed, planted="2026-04-25")
    plan.row("tropaeolum majus", (840, 520), (1000, 520), 2, parent=bed, planted="2026-05-12", size=(25, 70))

    # ── north-west: the flowers
    bed = beds[False, True]
    plan.row("helianthus annuus", (195, 1065), (475, 1065), 4, parent=bed, planted="2026-04-26")
    plan.row("dahlia pinnata", (190, 960), (480, 960), 4, parent=bed, planted="2026-05-14", size=(90, 70))
    plan.row("paeonia lactiflora", (200, 860), (460, 860), 3, parent=bed, planted="2023-10-07", size=(70, 80))
    plan.row("echinacea purpurea", (180, 780), (390, 780), 4, parent=bed, planted="2024-04-20")
    plan.row("zinnia elegans", (440, 770), (500, 830), 2, parent=bed, planted="2026-05-14")

    # ── north-east: herbs, strawberries and two currants
    bed = beds[True, True]
    plan.row("ribes rubrum", (760, 1050), (980, 1050), 2, parent=bed, planted="2022-10-15", size=(60, 50))
    plan.row("fragaria ananassa", (715, 940), (1015, 940), 6, parent=bed, planted="2024-08-24")
    for x, key, planted, size in ((715, "salvia officinalis", "2024-04-20", (50, 60)),
                                  (790, "thymus vulgaris", "2024-04-20", None),
                                  (850, "origanum vulgare", "2024-04-20", (40, 50)),
                                  (915, "allium schoenoprasum", "2024-04-20", None),
                                  (965, "petroselinum crispum", "2026-04-20", None),
                                  (1015, "anethum graveolens", "2026-04-20", None)):
        plan.plant(key, x, 850, parent=bed, planted=planted, size=size)
    plan.row("borago officinalis", (810, 775), (1010, 775), 4, parent=bed, planted="2026-04-22")

    # ── drawn to measure: the axes as guides, the measures as constraints
    plan.guide(x=CX)
    plan.guide(y=CY)
    plan.distance(edges[False, False], edges[True, False],
                  anchors=(AnchorType.EDGE_RIGHT, AnchorType.EDGE_LEFT))
    plan.distance(edges[False, True], edges[True, True],
                  anchors=(AnchorType.EDGE_RIGHT, AnchorType.EDGE_LEFT))
    plan.distance(edges[False, False], bench)

    plan.hint(30, 128, text(
        "20 Jun 2026 · 1  The two guide lines are the garden's axes: drag a bed corner and it snaps to them.\n"
        "2  Constraints panel: three distances hold the path width; move a box edging and the other follows.\n"
        "3  Select two plants: the companion check tells you which neighbours suit. Bamberg; records are fictional.",
        "20.06.2026 · 1  Die zwei Hilfslinien sind die Gartenachsen: Beetecke ziehen, sie rastet daran ein.\n"
        "2  Bereich Bedingungen: drei Abstände halten die Wegbreite; eine Buchseinfassung schieben, die andere folgt.\n"
        "3  Zwei Pflanzen wählen: die Mischkultur-Prüfung zeigt passende Nachbarn. Bamberg; Einträge sind fiktiv.",
        "20 jun 2026 · 1  Las dos guías son los ejes del jardín: arrastre una esquina y se ajusta a ellas.\n"
        "2  Panel de restricciones: tres distancias fijan el ancho del camino; mueva un borde de boj y el otro lo sigue.\n"
        "3  Seleccione dos plantas: la comprobación de asociación indica buenos vecinos. Bamberg; registros ficticios."),
        size=0.36, ink=a.NOTE_ON_LAWN, bold=True)

    for key, entries in (
        ("lactuca sativa", [("2026-06-06", 280, "g", a.OUTER_LEAVES), ("2026-06-15", 340, "g", a.CRISP)]),
        ("fragaria ananassa", [("2025-06-12", 1.4, "kg"), ("2026-06-08", 1.7, "kg", a.SWEET),
                               ("2026-06-17", 1.2, "kg")]),
        ("allium schoenoprasum", [("2025-05-20", 2, "bunch"), ("2026-05-12", 2, "bunch"),
                                  ("2026-06-10", 1, "bunch")]),
        ("ribes rubrum", [("2024-07-10", 1.1, "kg"), ("2025-07-06", 2.3, "kg")]),
        ("salvia officinalis", [("2025-06-22", 1, "bunch", a.AROMATIC), ("2026-06-14", 1, "bunch")]),
    ):
        plan.harvest(key, entries)
    return plan.done()
