"""The terraced-house garden: a narrow plot that does not face north.

Six metres wide and eighteen long, between the neighbours' hedges, with the house and a
flat-roofed extension at the top of the plan. True north is turned 35 degrees, so the
plan teaches the sun side: which border gets the evening sun, and where the house and
the hedges throw their shadows over a day.
"""

from __future__ import annotations

from datetime import time

from . import authoring as a
from .i18n import text
from .plan import FillPattern, ObjectType, PathFenceStyle, Plan
from .tours import held_tour

SLUG = "terraced-house-garden"
#: The stored orbit looks down more steeply than the dialog's 18 degrees: from there
#: the hedge hid the garden behind it (3D review of #940).
ORBIT_PITCH_DEG = 45.0
#: ... and nearer: fitted to the house, the garden filled a third of the picture.
ORBIT_CLOSER = 0.85
#: The gallery picture: the deck, the extension and the top of the lawn, not an 18 m sliver.
THUMBNAIL = (0, 760, 600, 760)
NORTH_DEG = 35.0
SHADOWS = text("Shadows over the day", "Schatten über den Tag", "Sombras a lo largo del día")

META = {
    "name_en": "Terraced-house garden - 6 x 18 m", "name_de": "Reihenhausgarten - 6 x 18 m",
    "name_es": "Jardín de casa adosada - 6 x 18 m",
    "name_ru": "Сад таунхауса - 6 x 18 м",
    "name_fr": "Jardin de maison mitoyenne - 6 x 18 m",
    "description_en": "A narrow garden between two hedges: house with a flat-roofed extension, timber deck, lawn with sandbox and swing, an apple tree, two borders and a shed with a mono-pitch roof. North is turned 35 degrees, so the hours-of-sun map and the shadows tell the two borders apart. A stored tour plays the shadows over one day. Cologne reference; opens on the late afternoon of 21 June 2026. Illustrative layout.",
    "description_de": "Ein schmaler Garten zwischen zwei Hecken: Haus mit Flachdach-Anbau, Holzdeck, Rasen mit Sandkasten und Schaukel, ein Apfelbaum, zwei Rabatten und ein Schuppen mit Pultdach. Norden ist um 35 Grad gedreht, so unterscheiden Sonnenstunden-Karte und Schatten die beiden Rabatten. Eine gespeicherte Kamerafahrt zeigt den Schattenlauf eines Tages. Referenz Köln; öffnet am späten Nachmittag des 21. Juni 2026. Beispielentwurf.",
    "description_es": "Un jardín estrecho entre dos setos: casa con anexo de cubierta plana, tarima de madera, césped con arenero y columpio, un manzano, dos arriates y una caseta de tejado a un agua. El norte está girado 35 grados, de modo que el mapa de horas de sol y las sombras distinguen los dos arriates. Un recorrido guardado muestra las sombras de un día. Referencia Colonia; se abre al final de la tarde del 21 de junio de 2026. Diseño ilustrativo.",
    "description_ru": "Узкий сад между двумя живыми изгородями: дом с пристройкой под плоской крышей, деревянный настил, газон с песочницей и качелями, яблоня, два цветника и сарай с односкатной крышей. Север повёрнут на 35 градусов, поэтому карта солнечных часов и тени показывают разницу между цветниками. Сохранённый облёт показывает движение теней за день. Ориентир: Кёльн; открывается ближе к вечеру 21 июня 2026 года. Примерный проект.",
    "description_fr": "Un jardin étroit entre deux haies : maison avec extension à toit plat, platelage en bois, pelouse avec bac à sable et balançoire, un pommier, deux bordures et un cabanon à toit à un pan. Le nord est tourné de 35 degrés, si bien que la carte des heures de soleil et les ombres distinguent les deux bordures. Une visite enregistrée fait défiler les ombres d’une journée. Référence : Cologne ; s’ouvre en fin d’après-midi le 21 juin 2026. Disposition illustrative.",
    "order": 8,
    "tags": ["terraced-house", "sun", "north"],
    "showcase_date": "2026-06-21", "showcase_utc_time": "16:15",
}


def more_tours(framing):
    """From the long side and well above, so that the narrow plot fills the picture
    while the sun goes round."""
    return [held_tour(framing.pose(90.0, 55.0), SHADOWS, time_range=(time(6, 0), time(21, 0)))]


def build():
    T, plan = ObjectType, Plan(SLUG, 600, 1800, layer=text("Garden", "Garten", "Jardín"))
    plan.site("cologne")
    plan.north(NORTH_DEG)
    plan.rect(0, 0, 600, 1800, T.LAWN, text("Lawn", "Rasen", "Césped"))

    # ── the house end
    plan.house([(0, 1400), (600, 1400), (600, 1800), (0, 1800)], text("House", "Haus", "Casa"), tall=780)
    plan.house([(300, 1150), (600, 1150), (600, 1400), (300, 1400)],
               text("Extension", "Anbau", "Anexo"), tall=310, roof="flat", ridge=False,
               fill=FillPattern.GRAVEL, color="#b7b2a6")
    plan.polygon([(0, 1000), (600, 1000), (600, 1150), (300, 1150), (300, 1400), (0, 1400)],
                 T.TERRACE_PATIO, text("Timber deck", "Holzdeck", "Tarima de madera"),
                 fill=FillPattern.DECKING)
    plan.line([(6, 1000), (6, 1400)], T.WALL, text("Privacy wall", "Sichtschutzmauer", "Muro de intimidad"),
              style=PathFenceStyle.STONE_WALL, tall=200)
    plan.rect(70, 1195, 160, 90, T.TABLE_RECTANGULAR, text("Table", "Tisch", "Mesa"))
    for x, y in ((92, 1150), (166, 1150), (92, 1290), (166, 1290)):
        plan.rect(x, y, 42, 42, T.CHAIR, text("Chair", "Stuhl", "Silla"))
    plan.circle(150, 1240, 125, T.PARASOL, text("Parasol", "Sonnenschirm", "Sombrilla"), tall=240)
    plan.circle(545, 1075, 28, T.BBQ_GRILL, text("BBQ", "Grill", "Barbacoa"))
    plan.rect(60, 1020, 190, 65, T.LOUNGER, text("Lounger", "Liege", "Tumbona"))

    # ── the neighbours' hedges down both sides, the borders in front of them
    hedge = text("Neighbour's hedge", "Nachbarhecke", "Seto del vecino")
    plan.polygon([(0, 0), (40, 0), (40, 1000), (0, 1000)], T.HEDGE_POLYGON, hedge, tall=190)
    plan.polygon([(560, 0), (600, 0), (600, 1000), (560, 1000)], T.HEDGE_POLYGON, hedge, tall=190)
    west = plan.rect(40, 330, 75, 420, T.GARDEN_BED,
                     text("West border", "Westrabatte", "Arriate oeste"), fill=FillPattern.MULCH)
    plan.row("hydrangea macrophylla", (78, 390), (78, 600), 3, parent=west, size=(90, 70))
    plan.row("rhododendron ponticum", (78, 690), (78, 690), 1, parent=west, size=(100, 70))
    east = plan.rect(485, 330, 75, 620, T.GARDEN_BED,
                     text("East border", "Ostrabatte", "Arriate este"), fill=FillPattern.MULCH)
    plan.row("lavandula angustifolia", (522, 380), (522, 560), 4, parent=east, size=(40, 50))
    plan.row("rosa rugosa", (522, 660), (522, 780), 2, parent=east, size=(110, 70))
    plan.row("salvia officinalis", (522, 870), (522, 915), 2, parent=east, size=(45, 45))

    # ── the lawn: play and a tree
    plan.line([(300, 1000), (270, 820), (320, 620), (300, 300)], T.PATH,
              text("Stepping stones", "Trittsteine", "Pasaderas"),
              style=PathFenceStyle.STEPPING_STONES, wide=50)
    plan.rect(130, 790, 120, 120, T.SANDBOX, text("Sandbox", "Sandkasten", "Arenero"))
    plan.rect(345, 470, 120, 200, T.SWING, text("Swing", "Schaukel", "Columpio"), tall=220)
    plan.plant("malus domestica", 205, 560, planted="2023-11-04", size=(160, 90))

    # ── the bottom of the garden: vegetables, the shed, the compost
    bed = plan.rect(60, 160, 260, 100, T.RAISED_BED, text("Raised bed", "Hochbeet", "Bancal elevado"), tall=45)
    plan.row("lactuca sativa", (95, 185), (285, 185), 6, parent=bed, planted="2026-04-22")
    plan.row("fragaria ananassa", (100, 232), (280, 232), 4, parent=bed, planted="2024-08-22")
    plan.shed(390, 60, 150, 200, T.TOOL_SHED, text("Shed", "Schuppen", "Cobertizo"), tall=220,
              roof="shed", pitch=14)
    plan.rect(70, 45, 90, 90, T.COMPOST_BIN, text("Compost", "Kompost", "Compostador"), tall=90)
    plan.circle(360, 100, 28, T.RAIN_BARREL, text("Rain barrel", "Regentonne", "Barril de lluvia"))

    plan.hint(50, 985, text(
        "21 Jun 2026 · 1  North is turned 35°: Plan & Sun shows the compass.\n"
        "2  Hours of Sun: the east border gets the evening sun, the west one little.\n"
        "3  3D view → Camera Tour: play “Shadows over the day”.\n"
        "Cologne; frost dates and harvests are fictional.",
        "21.06.2026 · 1  Norden ist um 35° gedreht (Kompass in Plan & Sonne).\n"
        "2  Sonnenstunden: Abendsonne im Ostbeet, im Westbeet kaum.\n"
        "3  3D-Ansicht → Kamerafahrt: „Schatten über den Tag“ abspielen.\n"
        "Köln; Frostdaten und Ernten sind fiktiv.",
        "21 jun 2026 · 1  El norte está girado 35°: Plano y sol muestra la brújula.\n"
        "2  Horas de sol: el arriate este recibe el sol de la tarde, el oeste poco.\n"
        "3  Vista 3D → Recorrido de cámara: «Sombras a lo largo del día».\n"
        "Colonia; heladas y cosechas ficticias."),
        size=0.37, ink=a.NOTE_ON_LAWN, bold=True)

    for key, entries in (
        ("lactuca sativa", [("2026-06-03", 220, "g", a.OUTER_LEAVES), ("2026-06-16", 300, "g", a.CRISP)]),
        ("fragaria ananassa", [("2025-06-15", 0.6, "kg"), ("2026-06-09", 0.8, "kg", a.SWEET),
                               ("2026-06-18", 0.5, "kg")]),
        ("salvia officinalis", [("2026-05-30", 1, "bunch", a.AROMATIC)]),
    ):
        plan.harvest(key, entries)
    return plan.done()
