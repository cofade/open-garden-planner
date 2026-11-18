"""The allotment: a plot of a German allotment colony in July.

A summer house, a greenhouse and cold frames at the back, rows of vegetables on both
sides of the main path, a Three Sisters mound, berries along the hedge and a plum tree.
It teaches the planning side: a succession plan, a soil sample, a guild and harvests.
"""

from __future__ import annotations

from . import authoring as a
from .i18n import text
from .plan import FillPattern, ObjectType, PathFenceStyle, Plan

SLUG = "allotment"
#: The stored orbit looks down more steeply than the dialog's 18 degrees: from there
#: the hedge hid the garden behind it (3D review of #940).
ORBIT_PITCH_DEG = 24.0
#: ... and it starts over the chain-link front, which can be seen through.
ORBIT_SUN_OFFSET_DEG = 290.0
#: The gallery picture: the beds on both sides of the main path, not the whole tall plot.
THUMBNAIL = (0, 560, 1500, 844)

META = {
    "name_en": "Allotment - 15 x 20 m", "name_de": "Schrebergarten - 15 x 20 m",
    "name_es": "Huerto urbano - 15 x 20 m",
    "name_ru": "Садовый участок - 15 x 20 м",
    "description_en": "A plot in an allotment colony: summer house with a mono-pitch roof, greenhouse, cold frames, water tap and compost. Rows of potatoes, onions, carrots, cabbage and beans, a Three Sisters mound, berries and a plum tree. Succession plan, soil sample and harvest log are fictional. Leipzig reference; opens on a morning of 18 July 2026. Illustrative layout.",
    "description_de": "Eine Parzelle in der Kleingartenanlage: Laube mit Pultdach, Gewächshaus, Frühbeete, Wasserhahn und Kompost. Reihen mit Kartoffeln, Zwiebeln, Möhren, Kohl und Bohnen, ein Drei-Schwestern-Beet, Beeren und ein Pflaumenbaum. Nachfolgeplan, Bodenprobe und Erntebuch sind fiktiv. Referenz Leipzig; öffnet am Morgen des 18. Juli 2026. Beispielentwurf.",
    "description_es": "Una parcela de un huerto urbano: caseta con tejado a un agua, invernadero, cajoneras, grifo y compostador. Hileras de patatas, cebollas, zanahorias, coles y judías, un montículo de las tres hermanas, bayas y un ciruelo. El plan de sucesión, la muestra de suelo y las cosechas son ficticios. Referencia Leipzig; se abre una mañana del 18 de julio de 2026. Diseño ilustrativo.",
    "description_ru": "Участок в садовом товариществе: домик с односкатной крышей, теплица, парники, водопроводный кран и компост. Ряды картофеля, лука, моркови, капусты и фасоли, грядка «три сестры», ягодные кусты и слива. План смены культур, образец почвы и журнал урожая условные. Ориентир: Лейпциг; открывается утром 18 июля 2026 года. Примерный проект.",
    "order": 9,
    "tags": ["allotment", "vegetables", "succession"],
    "showcase_date": "2026-07-18", "showcase_utc_time": "07:00",
}


def build():
    T, plan = ObjectType, Plan(SLUG, 1500, 2000, layer=text("Allotment", "Parzelle", "Parcela"))
    plan.site("leipzig")
    plan.rect(0, 0, 1500, 2000, T.LAWN, text("Plot lawn", "Parzellenrasen", "Césped de la parcela"))

    # ── the boundary: a chain-link front with a gate gap, a hedge on the other three sides
    front = text("Front fence", "Vorderzaun", "Valla delantera")
    plan.line([(30, 150), (660, 150)], T.FENCE, front, style=PathFenceStyle.CHAIN_LINK, tall=120)
    plan.line([(840, 150), (1470, 150)], T.FENCE, front, style=PathFenceStyle.CHAIN_LINK, tall=120)
    hedge = text("Boundary hedge", "Grenzhecke", "Seto de linde")
    for run in a.runs([(30, 150), (30, 1970), (1470, 1970), (1470, 150)]):
        plan.line(run, T.FENCE, hedge, style=PathFenceStyle.HEDGE_FENCE, tall=140)
    plan.line([(750, 150), (750, 1410)], T.PATH, text("Main path", "Hauptweg", "Camino principal"),
              style=PathFenceStyle.PAVED_PATH, wide=100)

    # ── the summer house and its terrace
    plan.shed(960, 1650, 420, 290, T.TOOL_SHED, text("Summer house", "Laube", "Caseta"),
              tall=270, roof="shed", pitch=12, fill=FillPattern.ROOF_TILES)
    plan.rect(960, 1420, 420, 230, T.TERRACE_PATIO, text("Terrace", "Terrasse", "Terraza"),
              fill=FillPattern.DECKING)
    plan.circle(1105, 1535, 45, T.TABLE_ROUND, text("Table", "Tisch", "Mesa"))
    plan.rect(995, 1512, 45, 45, T.CHAIR, text("Chair", "Stuhl", "Silla"), turn=90)
    plan.rect(1170, 1512, 45, 45, T.CHAIR, "Chair", turn=-90)
    plan.circle(1290, 1535, 105, T.PARASOL, text("Parasol", "Sonnenschirm", "Sombrilla"), tall=230)
    plan.circle(925, 1700, 30, T.RAIN_BARREL, text("Rain barrel", "Regentonne", "Barril de lluvia"))
    plan.circle(1415, 1700, 30, T.RAIN_BARREL, "Rain barrel")

    # ── the working corner: greenhouse, cold frames, compost
    plan.greenhouse(110, 1570, 260, 350, text("Greenhouse", "Gewächshaus", "Invernadero"))
    frame = text("Cold frame", "Frühbeet", "Cajonera")
    plan.rect(420, 1810, 120, 80, T.COLD_FRAME, frame)
    plan.rect(420, 1700, 120, 80, T.COLD_FRAME, frame)
    compost = text("Compost", "Kompost", "Compostador")
    plan.rect(580, 1850, 90, 90, T.COMPOST_BIN, compost, tall=90)
    plan.rect(580, 1740, 90, 90, T.COMPOST_BIN, compost, tall=90)
    plan.rect(420, 1590, 140, 70, T.WHEELBARROW, text("Wheelbarrow", "Schubkarre", "Carretilla"))
    plan.circle(826, 781, 11, T.WATER_TAP, text("Water tap", "Wasserhahn", "Grifo"))

    # ── west of the path: the row crops
    def bed(x, y, width, height, name):
        return plan.rect(x, y, width, height, T.GARDEN_BED, name, fill=FillPattern.SOIL)

    potatoes = bed(110, 230, 550, 130, text("Potato bed", "Kartoffelbeet", "Bancal de patatas"))
    plan.grid("solanum tuberosum", 150, 265, 9, 2, 60, 60, parent=potatoes, planted="2026-04-10")
    roots = bed(110, 420, 550, 130, text("Onions and carrots", "Zwiebeln und Möhren", "Cebollas y zanahorias"))
    plan.row("allium cepa", (140, 445), (630, 445), 12, parent=roots, planted="2026-03-25")
    plan.row("daucus carota", (135, 475), (635, 475), 20, parent=roots, planted="2026-04-15")
    plan.row("allium cepa", (140, 505), (630, 505), 12, parent=roots, planted="2026-03-25")
    plan.row("allium sativum", (140, 533), (630, 533), 12, parent=roots, planted="2025-10-20")
    brassicas = bed(110, 610, 550, 130, text("Cabbage bed", "Kohlbeet", "Bancal de coles"))
    plan.row("brassica oleracea var. capitata", (165, 675), (365, 675), 3, parent=brassicas,
             planted="2026-05-10")
    plan.row("brassica oleracea var. acephala", (455, 675), (615, 675), 3, parent=brassicas,
             planted="2026-05-10")
    legumes = bed(110, 800, 550, 130, text("Beans and beets", "Bohnen und Rote Bete", "Judías y remolachas"))
    plan.grid("phaseolus vulgaris", 140, 838, 6, 2, 44, 56, parent=legumes, planted="2026-05-20")
    plan.grid("beta vulgaris", 420, 840, 11, 2, 22, 52, parent=legumes, planted="2026-04-20")
    berries = bed(110, 990, 550, 130, text("Strawberry bed", "Erdbeerbeet", "Bancal de fresas"))
    plan.grid("fragaria ananassa", 150, 1025, 9, 2, 60, 60, parent=berries, planted="2024-08-20")
    rhubarb = bed(110, 1180, 330, 130, text("Rhubarb corner", "Rhabarberecke", "Rincón del ruibarbo"))
    plan.row("rheum rhabarbarum", (185, 1245), (365, 1245), 2, parent=rhubarb, planted="2022-04-10",
             size=(70, 120))
    tomatoes = bed(110, 1370, 550, 130, text("Tomato bed", "Tomatenbeet", "Bancal de tomates"))
    plan.row("solanum lycopersicum", (165, 1435), (605, 1435), 5, parent=tomatoes, planted="2026-05-18")
    flowers = bed(110, 172, 550, 46, text("Marigold strip", "Tagetesstreifen", "Franja de tagetes"))
    plan.row("tagetes erecta", (140, 195), (630, 195), 10, parent=flowers, planted="2026-05-18")

    # ── east of the path
    salad = bed(840, 900, 520, 130, text("Salad bed", "Salatbeet", "Bancal de ensaladas"))
    plan.row("lactuca sativa", (880, 935), (1320, 935), 8, parent=salad, planted="2026-06-05")
    plan.row("eruca vesicaria", (875, 975), (1325, 975), 10, parent=salad, planted="2026-06-20")
    plan.row("raphanus sativus", (870, 1008), (1330, 1008), 16, parent=salad, planted="2026-06-28")
    plan.succession(salad, 2027, [("spinacia oleracea", "2027-03-10", "2027-05-10"),
                                  ("phaseolus vulgaris", "2027-05-20", "2027-08-20"),
                                  ("lactuca sativa", "2027-08-25", "2027-10-25")])
    plan.soil(potatoes, ph=6.0, day="2026-03-20")

    support = plan.rect(860, 1090, 480, 40, T.TRELLIS, text("Pea support", "Erbsenreisig", "Soporte de guisantes"),
                        tall=180)
    plan.row("pisum sativum", (890, 1110), (1310, 1110), 8, parent=support, planted="2026-03-28")
    herbs = bed(840, 1270, 420, 90, text("Herb bed", "Kräuterbeet", "Bancal de hierbas"))
    for x, key, planted, size in (
            (880, "petroselinum crispum", "2026-04-20", None),
            (945, "allium schoenoprasum", "2024-04-20", None),
            (1010, "anethum graveolens", "2026-04-20", None),
            (1080, "salvia officinalis", "2024-04-20", (50, 60)),
            (1150, "thymus vulgaris", "2024-04-20", None),
            (1215, "origanum vulgare", "2024-04-20", (40, 50))):
        plan.plant(key, x, 1315, parent=herbs, planted=planted, size=size)

    # the Three Sisters mound: corn in the middle, beans at its foot, squash on the rim
    mound = plan.polygon([(1100 + dx, 690 + dy) for dx, dy in (
        (180, 0), (127, 127), (0, 180), (-127, 127), (-180, 0), (-127, -127), (0, -180), (127, -127))],
        T.GARDEN_BED, text("Three Sisters mound", "Drei-Schwestern-Hügel", "Montículo de las tres hermanas"),
        fill=FillPattern.COMPOST)
    corn = [plan.plant("zea mays", 1100 + dx, 690 + dy, parent=mound, planted="2026-05-15")
            for dx, dy in ((0, 0), (-46, 0), (46, 0), (0, -46), (0, 46))]
    beans = [plan.plant("phaseolus coccineus", 1100 + dx, 690 + dy, parent=mound, planted="2026-05-25")
             for dx, dy in ((-36, 36), (36, -36))]
    squash = plan.plant("cucurbita maxima", 1010, 775, parent=mound, planted="2026-05-25", size=(50, 200))
    plan.guild("three-sisters-mound", text("Three Sisters", "Drei Schwestern", "Tres hermanas"),
               corn[0], {"nitrogen_fixer": beans, "ground_cover": [squash]})

    for y in (300, 420, 540):
        plan.plant("rubus idaeus", 1395, y, planted="2022-10-22", size=(60, 40))
    for y in (680, 800):
        plan.plant("ribes rubrum", 1395, y, planted="2022-10-22", size=(50, 40))
    for y in (920, 1040):
        plan.plant("ribes uva-crispa", 1395, y, planted="2022-10-22", size=(40, 40))
    plan.plant("prunus domestica", 1000, 335, planted="2021-11-06", size=(170, 100))
    plan.rect(1215, 330, 150, 50, T.BENCH, text("Bench", "Sitzbank", "Banco"))
    sun = bed(1180, 170, 270, 95, text("Sunflower corner", "Sonnenblumenecke", "Rincón de girasoles"))
    plan.row("helianthus annuus", (1225, 217), (1405, 217), 3, parent=sun, planted="2026-04-28",
             size=(10, 10))  # sown: a sunflower is not three metres tall in July

    plan.hint(40, 128, text(
        "18 Jul 2026 · 1  Right-click the salad bed: Succession Plan (2027). The potato bed has a soil test.\n"
        "2  Select the sweet corn → Guilds: the Three Sisters mound with beans and squash.\n"
        "3  Plan & Sun: scrub March to October and watch the beds fill. Leipzig; all records are fictional.",
        "18.07.2026 · 1  Rechtsklick aufs Salatbeet: Nachfolgeplanung (2027). Das Kartoffelbeet hat einen Bodentest.\n"
        "2  Zuckermais wählen → Gilden: das Drei-Schwestern-Beet mit Bohnen und Kürbis.\n"
        "3  Plan & Sonne: März bis Oktober durchgehen, die Beete füllen sich. Leipzig; alle Einträge sind fiktiv.",
        "18 jul 2026 · 1  Clic derecho en el bancal de ensaladas: sucesión (2027). El de patatas tiene un análisis de suelo.\n"
        "2  Seleccione el maíz → Gremios: el montículo de las tres hermanas con judías y calabaza.\n"
        "3  Plan y sol: recorra de marzo a octubre y vea llenarse los bancales. Leipzig; registros ficticios."),
        size=0.44, ink=a.NOTE_ON_LAWN, bold=True)

    for key, entries in (
        ("fragaria ananassa", [("2025-06-14", 2.2, "kg"), ("2026-06-10", 2.6, "kg", a.SWEET),
                               ("2026-06-21", 1.9, "kg")]),
        ("pisum sativum", [("2026-06-18", 0.9, "kg", a.TENDER), ("2026-07-02", 1.3, "kg"),
                           ("2026-07-12", 0.8, "kg")]),
        ("solanum tuberosum", [("2026-07-11", 3.5, "kg", a.FIRST_PICK)]),
        ("lactuca sativa", [("2026-07-08", 300, "g", a.CRISP), ("2026-07-15", 350, "g")]),
        ("rheum rhabarbarum", [("2025-05-10", 2.0, "kg"), ("2026-05-08", 2.4, "kg"),
                               ("2026-06-01", 1.5, "kg")]),
        ("rubus idaeus", [("2025-07-12", 1.8, "kg"), ("2026-07-05", 2.1, "kg", a.SWEET),
                          ("2026-07-14", 1.4, "kg")]),
        ("ribes rubrum", [("2025-07-08", 2.5, "kg"), ("2026-07-06", 2.9, "kg")]),
        ("prunus domestica", [("2025-08-30", 14, "kg")]),
    ):
        plan.harvest(key, entries)
    return plan.done()
