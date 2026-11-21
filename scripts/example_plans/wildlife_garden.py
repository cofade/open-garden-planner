"""The wildlife garden: a flower meadow around a pond.

Nothing here is mown; trodden paths lead round. A boardwalk leads to a deck at the water, a willow
leans over the pond, an oak carries a hammock, and drifts of flowers stand in the meadow
for the insects. The plan is the lush one: it is made to be looked at in 3D.
"""

from __future__ import annotations

from . import authoring as a
from .i18n import text
from .plan import FillPattern, ObjectType, PathFenceStyle, Plan

SLUG = "wildlife-garden"
#: The stored orbit looks down more steeply than the dialog's 18 degrees: from there
#: the hedge hid the garden behind it (3D review of #940).
ORBIT_PITCH_DEG = 28.0
#: Trees and shrubs were moved here last autumn at the size they have; the meadow's
#: perennials are in their third year, its annuals were sown this spring.
WOODY, PERENNIAL, ANNUAL = "2025-10-25", "2024-04-20", "2026-04-12"

META = {
    "name_en": "Wildlife garden with pond - 18 x 14 m", "name_de": "Naturgarten mit Teich - 18 x 14 m",
    "name_es": "Jardín natural con estanque - 18 x 14 m",
    "name_ru": "Природный сад с прудом - 18 x 14 м",
    "name_fr": "Jardin sauvage avec bassin - 18 x 14 m",
    "description_en": "A flower meadow around a pond: a boardwalk to a deck at the water, a willow on the bank, an oak with a hammock, birch, elder and wild shrubs, and drifts of chamomile, flax, borage, coneflower and pot marigold for the insects. Nothing is mown; trodden paths lead round. Made for the 3D view. Lüneburg reference; opens on a morning of 14 June 2026. Illustrative layout.",
    "description_de": "Eine Blumenwiese um einen Teich: ein Holzsteg führt zum Deck am Wasser, am Ufer steht eine Weide, an der Eiche hängt eine Hängematte, dazu Birke, Holunder und Wildsträucher sowie Inseln aus Kamille, Lein, Borretsch, Sonnenhut und Ringelblume für die Insekten. Gemäht wird nichts; Trampelpfade führen herum. Gemacht für die 3D-Ansicht. Referenz Lüneburg; öffnet am Morgen des 14. Juni 2026. Beispielentwurf.",
    "description_es": "Una pradera de flores alrededor de un estanque: una pasarela lleva a una tarima junto al agua, un sauce en la orilla, un roble con una hamaca, abedul, saúco y arbustos silvestres, y manchas de manzanilla, lino, borraja, equinácea y caléndula para los insectos. No se siega nada; unos senderos pisados dan la vuelta. Pensado para la vista 3D. Referencia Lüneburg; se abre una mañana del 14 de junio de 2026. Diseño ilustrativo.",
    "description_ru": "Цветущий луг вокруг пруда: деревянный настил ведёт к площадке у воды, на берегу растёт ива, на дубе висит гамак, рядом берёза, бузина и дикие кустарники, а для насекомых — куртины ромашки, льна, огуречной травы, эхинацеи и календулы. Ничего не косят; вокруг ведут протоптанные тропинки. Создан для 3D-вида. Ориентир: Люнебург; открывается утром 14 июня 2026 года. Примерный проект.",
    "description_fr": "Une prairie fleurie autour d’un bassin : un ponton vers une terrasse au bord de l’eau, un saule sur la rive, un chêne avec un hamac, bouleau, sureau et arbustes sauvages, et des taches de camomille, lin, bourrache, échinacée et souci pour les insectes. Rien n’est tondu ; des sentiers piétinés font le tour. Conçu pour la vue 3D. Référence : Lunebourg ; s’ouvre un matin du 14 juin 2026. Disposition illustrative.",
    "order": 3,
    "tags": ["wildlife", "pond", "meadow"],
    "showcase_date": "2026-06-14", "showcase_utc_time": "06:35",
}


def build():
    T, plan = ObjectType, Plan(SLUG, 1800, 1400, layer=text("Wildlife garden", "Naturgarten", "Jardín natural"))
    plan.site("lueneburg")
    # one polygon, and everything that clears the grass is drawn after it, so above it
    plan.rect(0, 0, 1800, 1400, T.LAWN, text("Flower meadow", "Blumenwiese", "Pradera de flores"),
              fill=FillPattern.WILDFLOWER, color=a.MEADOW_GREEN)
    hedge = text("Wild hedge", "Wildhecke", "Seto silvestre")
    for run in a.runs([(12, 12), (12, 1388), (1788, 1388), (1788, 12)]):
        plan.line(run, T.FENCE, hedge, style=PathFenceStyle.HEDGE_FENCE, tall=170)
    fence = text("Front fence", "Vorderzaun", "Valla delantera")
    plan.line([(12, 12), (850, 12)], T.FENCE, fence, style=PathFenceStyle.WOODEN_FENCE, tall=110)
    plan.line([(950, 12), (1788, 12)], T.FENCE, fence, style=PathFenceStyle.WOODEN_FENCE, tall=110)

    # ── the mown paths: in from the gate, and once round the pond
    mown = text("Trodden path", "Trampelpfad", "Sendero pisado")
    plan.line([(900, 45), (900, 210), (620, 340), (320, 430)], T.PATH, mown,
              style=PathFenceStyle.DIRT_PATH, wide=80)
    plan.line([(900, 210), (1300, 330), (1600, 560), (1650, 900), (1640, 1150), (1300, 1210),
               (820, 1160), (540, 1000), (560, 580)], T.PATH, mown,
              style=PathFenceStyle.DIRT_PATH, wide=80)

    # ── the water
    plan.polygon([(880, 640), (1010, 560), (1200, 560), (1380, 640), (1440, 790), (1390, 930),
                  (1240, 1000), (1060, 990), (930, 900), (860, 770)], T.POND_POOL,
                 text("Pond", "Teich", "Estanque"))
    plan.line([(320, 430), (560, 580), (800, 770)], T.PATH,
              text("Boardwalk", "Holzsteg", "Pasarela"), style=PathFenceStyle.WOODEN_BOARDWALK, wide=100)
    plan.rect(780, 700, 170, 170, T.TERRACE_PATIO, text("Pond deck", "Teichdeck", "Tarima del estanque"),
              fill=FillPattern.DECKING)
    plan.rect(800, 800, 130, 48, T.BENCH, text("Bench", "Sitzbank", "Banco"), turn=180)
    for x, y in ((845, 610), (825, 690), (900, 935), (1000, 1005), (1300, 1005), (1420, 650)):
        plan.plant("iris germanica", x, y, planted=PERENNIAL, apart=36)

    # ── trees and wild shrubs
    plan.plant("salix alba", 1470, 1020, planted=WOODY, size=(560, 400))
    plan.plant("quercus robur", 300, 1090, planted=WOODY, size=(560, 400))
    plan.plant("betula pendula", 1560, 250, planted=WOODY, size=(720, 300))
    plan.plant("sambucus nigra", 900, 1290, planted=WOODY, size=(280, 210))
    plan.plant("sambucus nigra", 1180, 1290, planted=WOODY, size=(260, 200))
    plan.plant("viburnum opulus", 1705, 700, planted=WOODY, size=(220, 170))
    plan.plant("berberis vulgaris", 1710, 500, planted=WOODY, size=(150, 140))
    plan.plant("ilex aquifolium", 110, 620, planted=WOODY, size=(260, 170))
    plan.rect(400, 700, 210, 90, T.HAMMOCK, text("Hammock", "Hängematte", "Hamaca"))
    plan.circle(1250, 420, 26, T.BIRD_BATH, text("Bird bath", "Vogeltränke", "Bebedero de pájaros"))
    plan.rect(1670, 60, 90, 90, T.COMPOST_BIN, text("Compost", "Kompost", "Compostador"), tall=90)

    # ── flowers in the meadow, in drifts
    plan.drift("calendula officinalis", (110, 140, 430, 230), 16, gap=42, planted=ANNUAL,
               size=(10, 10))
    plan.drift("cosmos bipinnatus", (130, 150, 400, 210), 9, gap=48, seed="south-west", planted=ANNUAL,
               size=(10, 10))  # sown: cosmos is not 1.8 m tall in mid June
    plan.drift("linum usitatissimum", (1010, 70, 480, 200), 30, gap=24, planted=ANNUAL)
    plan.drift("chamaemelum nobile", (1000, 90, 520, 190), 10, gap=62, seed="south", planted=PERENNIAL)
    plan.drift("borago officinalis", (620, 400, 220, 170), 9, gap=58, planted=ANNUAL)
    plan.drift("echinacea purpurea", (900, 1030, 340, 110), 10, gap=52, planted=PERENNIAL)
    plan.drift("valeriana officinalis", (620, 1010, 180, 120), 5, gap=58, planted=PERENNIAL)
    plan.drift("cichorium intybus", (1470, 400, 110, 300), 9, gap=42, planted=PERENNIAL)
    plan.drift("hyssopus officinalis", (1130, 360, 240, 130), 6, gap=58, planted=PERENNIAL)

    plan.hint(40, 118, text(
        "14 Jun 2026 · 1  Open the 3D view: the meadow stands in flower and the willow leans over the pond.\n"
        "2  3D view → Camera Tour: play “Garden orbit”, or walk along the boardwalk in walk mode.\n"
        "3  Select a flower: Plant Details names what it does for insects. Lüneburg; records are fictional.",
        "14.06.2026 · 1  3D-Ansicht öffnen: die Wiese blüht, die Weide neigt sich über den Teich.\n"
        "2  3D-Ansicht → Kamerafahrt: „Rundflug“ abspielen oder im Gehmodus über den Holzsteg laufen.\n"
        "3  Blume wählen: Pflanzendetails nennen ihren Nutzen für Insekten. Lüneburg; Einträge sind fiktiv.",
        "14 jun 2026 · 1  Abra la vista 3D: la pradera está en flor y el sauce se inclina sobre el estanque.\n"
        "2  Vista 3D → Recorrido de cámara: «Vuelo alrededor del jardín», o camine por la pasarela.\n"
        "3  Seleccione una flor: Detalles de planta indica su función para los insectos. Lüneburg; registros ficticios."),
        size=0.44, ink=a.NOTE_ON_LAWN, bold=True)

    for key, entries in (
        ("chamaemelum nobile", [("2025-06-20", 60, "g", a.AROMATIC), ("2026-06-08", 45, "g")]),
        ("borago officinalis", [("2026-06-06", 20, "pcs", a.PETALS)]),
        ("calendula officinalis", [("2026-06-10", 15, "pcs", a.PETALS)]),
    ):
        plan.harvest(key, entries)
    return plan.done()
