"""The Japanese garden: sand, stone, water and a few plants, on an October afternoon.

A raked sand court with moss islands, a pond with a plank bridge, a tea house with a
hip roof, stepping stones between them. The planting is chosen for the season it is
shown in: a red Japanese maple, a birch in yellow, and pine, bamboo, rhododendron and
box that stay green. It shows the surfaces: nearly every ground material of the app
lies here side by side.
"""

from __future__ import annotations

from .i18n import text
from .plan import FillPattern, ObjectType, PathFenceStyle, Plan

SLUG = "japanese-garden"
#: The stored orbit looks down more steeply than the dialog's 18 degrees: from there
#: the fence hid the garden behind it (3D review of #940).
ORBIT_PITCH_DEG = 34.0
#: ... and nearer: fitted to the 8.8 m birch, the garden filled a third of the picture.
ORBIT_CLOSER = 0.8
#: Everything was planted last autumn at the size it has, so it stands all year.
SET = "2025-10-25"

META = {
    "name_en": "Japanese garden - 12 x 10 m", "name_de": "Japangarten - 12 x 10 m",
    "name_es": "Jardín japonés - 12 x 10 m",
    "name_ru": "Японский сад - 12 x 10 м",
    "name_fr": "Jardin japonais - 12 x 10 m",
    "description_en": "Sand, stone and water on an October afternoon: a raked sand court with moss islands and rocks, a pond with a plank bridge, a tea house with a hip roof and a timber veranda, stepping stones and slate. Red Japanese maples, a birch in autumn yellow, pine, bamboo, rhododendron and box. Nearly every ground material lies side by side here. Düsseldorf reference; opens on 20 October 2026 in low afternoon light. Illustrative layout.",
    "description_de": "Sand, Stein und Wasser an einem Oktobernachmittag: ein geharkter Sandhof mit Moosinseln und Steinen, ein Teich mit Bohlenbrücke, ein Teehaus mit Walmdach und Holzveranda, Trittsteine und Schiefer. Rote Fächerahorne, eine Birke in Herbstgelb, Kiefer, Bambus, Rhododendron und Buchs. Fast jedes Bodenmaterial liegt hier nebeneinander. Referenz Düsseldorf; öffnet am 20. Oktober 2026 im tiefen Nachmittagslicht. Beispielentwurf.",
    "description_es": "Arena, piedra y agua en una tarde de octubre: un patio de arena rastrillada con islas de musgo y rocas, un estanque con puente de tablones, una casa de té con tejado a cuatro aguas y galería de madera, pasaderas y pizarra. Arces japoneses rojos, un abedul amarillo de otoño, pino, bambú, rododendro y boj. Casi todos los materiales de suelo están aquí juntos. Referencia Düsseldorf; se abre el 20 de octubre de 2026 con luz baja de tarde. Diseño ilustrativo.",
    "description_ru": "Песок, камень и вода октябрьским днём: двор из граблёного песка с островками мха и камнями, пруд с дощатым мостиком, чайный домик с вальмовой крышей и деревянной верандой, шаговые камни и сланец. Красные японские клёны, берёза в осенней желтизне, сосна, бамбук, рододендрон и самшит. Здесь рядом лежат почти все материалы покрытий. Ориентир: Дюссельдорф; открывается 20 октября 2026 года при низком послеполуденном свете. Примерный проект.",
    "description_fr": "Sable, pierre et eau un après-midi d’octobre : une cour de sable ratissée avec des îlots de mousse et des rochers, un bassin avec un pont de planches, une maison de thé au toit à quatre pans et une véranda en bois, des pas japonais et de l’ardoise. Érables du Japon rouges, un bouleau jaune d’automne, pin, bambou, rhododendron et buis. Presque tous les matériaux de sol se côtoient ici. Référence : Düsseldorf ; s’ouvre le 20 octobre 2026 dans la lumière basse de l’après-midi. Disposition illustrative.",
    "order": 4,
    "tags": ["japanese", "materials", "autumn"],
    "showcase_date": "2026-10-20", "showcase_utc_time": "13:50",
}


def build():
    T, plan = ObjectType, Plan(SLUG, 1200, 1000, layer=text("Garden", "Garten", "Jardín"))
    plan.site("duesseldorf")
    plan.rect(0, 0, 1200, 1000, T.LAWN, text("Moss lawn", "Moosrasen", "Césped de musgo"),
              fill=FillPattern.MOSS, color="#4b6337")
    plan.line([(8, 8), (8, 992), (1192, 992), (1192, 8), (660, 8)], T.FENCE,
              text("Timber fence", "Holzzaun", "Valla de madera"),
              style=PathFenceStyle.BOARD_FENCE, tall=190)
    plan.line([(540, 8), (8, 8)], T.FENCE, "Timber fence",
              style=PathFenceStyle.BOARD_FENCE, tall=190)

    # ── the sand court with its islands
    plan.rect(90, 90, 620, 420, T.TERRACE_PATIO, text("Raked sand", "Geharkter Sand", "Arena rastrillada"),
              fill=FillPattern.SAND)
    island = text("Moss island", "Moosinsel", "Isla de musgo")
    plan.polygon([(190, 300), (290, 270), (380, 320), (360, 410), (250, 430), (180, 380)],
                 T.LAWN, island, fill=FillPattern.MOSS, color="#4b6337")
    plan.polygon([(500, 250), (590, 240), (640, 300), (600, 360), (510, 340)],
                 T.LAWN, island, fill=FillPattern.MOSS, color="#4b6337")
    rock = text("Rock", "Stein", "Roca")
    for tall, points in (
            (60, [(255, 332), (272, 322), (296, 320), (314, 334), (318, 356), (304, 372), (282, 378),
                  (260, 372), (250, 352)]),
            (40, [(545, 282), (562, 275), (580, 277), (591, 290), (590, 306), (576, 316), (558, 317),
                  (546, 304)]),
            (25, [(420, 192), (440, 183), (462, 184), (475, 198), (474, 216), (458, 229), (438, 231),
                  (420, 222), (413, 206)])):
        plan.polygon(points, T.GENERIC_POLYGON, rock, tall=tall, fill=FillPattern.STONE, color="#a49e93")
    plan.plant("pinus sylvestris", 300, 400, planted=SET, size=(320, 240))

    # ── the tea house, its veranda and the way to it
    plan.shed(110, 720, 280, 210, T.TOOL_SHED, text("Tea house", "Teehaus", "Casa de té"),
              tall=290, roof="hip", pitch=30, overhang=60)
    plan.rect(110, 630, 280, 90, T.TERRACE_PATIO, text("Veranda", "Veranda", "Galería"),
              fill=FillPattern.DECKING)
    plan.rect(390, 560, 70, 380, T.TERRACE_PATIO, text("Slate walk", "Schieferweg", "Paseo de pizarra"),
              fill=FillPattern.SLATE, color="#7b8088")
    plan.line([(600, 50), (600, 90)], T.PATH, text("Gate path", "Torweg", "Camino de la puerta"),
              style=PathFenceStyle.PAVED_PATH, wide=90)
    plan.line([(700, 300), (790, 380), (780, 480), (700, 540), (560, 560), (460, 590)], T.PATH,
              text("Stepping stones", "Trittsteine", "Pasaderas"), style=PathFenceStyle.STEPPING_STONES, wide=55)
    plan.rect(150, 650, 130, 46, T.BENCH, text("Bench", "Sitzbank", "Banco"))

    # ── the water and the bridge
    plan.polygon([(700, 620), (800, 560), (960, 560), (1090, 620), (1120, 740), (1060, 860), (920, 900),
                  (780, 870), (690, 780)], T.POND_POOL, text("Pond", "Teich", "Estanque"))
    plan.line([(620, 740), (760, 730), (900, 735), (1060, 725), (1150, 730)], T.PATH,
              text("Plank bridge", "Bohlenbrücke", "Puente de tablones"),
              style=PathFenceStyle.WOODEN_BOARDWALK, wide=80)
    plan.rect(90, 25, 430, 55, T.TERRACE_PATIO, text("Pebble strip", "Kieselstreifen", "Franja de guijarros"),
              fill=FillPattern.PEBBLES)

    # ── the plants: red and yellow for October, the rest evergreen
    plan.plant("acer palmatum", 600, 690, planted=SET, size=(250, 230))
    plan.plant("acer palmatum", 800, 170, planted=SET, size=(190, 180))
    plan.plant("betula pendula", 1085, 190, planted=SET, size=(700, 280))
    plan.plant("pinus sylvestris", 930, 400, planted=SET, size=(300, 220))
    plan.row("fargesia murielae", (520, 950), (1130, 950), 8, planted=SET, size=(330, 85))
    for x, y in ((1125, 490), (1125, 835), (650, 835)):
        plan.plant("rhododendron ponticum", x, y, planted=SET, size=(120, 130))
    for x, y in ((120, 560), (60, 470), (540, 860), (930, 150)):
        plan.plant("buxus sempervirens", x, y, planted=SET, size=(70, 85))
    plan.row("miscanthus sinensis", (760, 470), (950, 470), 3, planted=SET, size=(150, 90))
    for x, y in ((690, 600), (820, 540), (980, 545), (1105, 610), (1155, 660), (900, 548)):
        plan.plant("iris germanica", x, y, planted="2024-04-20")
    plan.plant("juniperus communis", 60, 70, planted=SET, size=(160, 110))
    lantern = text("Stone lantern", "Steinlaterne", "Linterna de piedra")
    for x, y in ((450, 540), (740, 440), (1060, 500)):
        plan.circle(x, y, 14, T.GARDEN_LIGHT, lantern)

    plan.hint(110, 180, text(
        "20 Oct 2026 · 1  Open the 3D view: sand, slate, pebbles, moss and water lie side by side.\n"
        "2  Select a surface → Properties: change its fill and see it in 2D and 3D at once.\n"
        "3  Plan & Sun: scrub to June. The maples stay red, the birch turns green. Düsseldorf reference.",
        "20.10.2026 · 1  3D-Ansicht öffnen: Sand, Schiefer, Kiesel, Moos und Wasser liegen nebeneinander.\n"
        "2  Fläche wählen → Eigenschaften: Füllung ändern und in 2D und 3D zugleich sehen.\n"
        "3  Plan & Sonne: auf Juni gehen. Die Ahorne bleiben rot, die Birke wird grün. Referenz Düsseldorf.",
        "20 oct 2026 · 1  Abra la vista 3D: arena, pizarra, guijarros, musgo y agua, uno junto a otro.\n"
        "2  Seleccione una superficie → Propiedades: cambie el relleno y véalo en 2D y 3D a la vez.\n"
        "3  Plano y sol: vaya a junio. Los arces siguen rojos, el abedul se vuelve verde. Referencia Düsseldorf."),
        size=0.3)
    return plan.done()
