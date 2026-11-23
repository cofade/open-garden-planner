"""The Mediterranean courtyard: a walled patio in Valencia at golden hour.

A house with a hip roof closes the north side, white walls the others. Under a pergola
with a grape vine stands the dining table; an olive and a fig grow in the ground, lemon
and orange in tubs, a windmill palm by the plunge pool. The plan shows another sun:
at 39 degrees north the summer sun stands high at noon and sets late and far to the
north-west.
"""

from __future__ import annotations

from . import authoring as a
from .i18n import text
from .plan import FillPattern, ObjectType, PathFenceStyle, Plan

SLUG = "mediterranean-courtyard"
#: The stored orbit looks down more steeply than the dialog's 18 degrees: from there
#: the wall hid the garden behind it (3D review of #940).
ORBIT_PITCH_DEG = 34.0
#: The house closes the north side: half a turn stays over the courtyard (#966).
#: Counter-clockwise from the WSW start sweeps south across the courtyard instead of north behind the house.
ORBIT_TURNS = 0.5
ORBIT_CLOCKWISE = False

META = {
    "name_en": "Mediterranean courtyard - 12 x 10 m", "name_de": "Mediterraner Innenhof - 12 x 10 m",
    "name_es": "Patio mediterráneo - 12 x 10 m",
    "name_ru": "Средиземноморский дворик - 12 x 10 м",
    "name_fr": "Cour méditerranéenne - 12 x 10 m",
    "description_en": "A walled patio at golden hour: an olive and a fig in the ground, lemon and orange in tubs, a windmill palm by the plunge pool, a grape vine on the pergola over the dining table, lavender and rosemary along the walls. Flagstone and terracotta, two loungers and a string of lights. Valencia reference, 39 degrees north: compare its sun with a northern plan. Opens on the evening of 21 June 2026. Illustrative layout.",
    "description_de": "Ein ummauerter Patio zur goldenen Stunde: Olive und Feige im Boden, Zitrone und Orange im Kübel, eine Hanfpalme am Tauchbecken, Wein an der Pergola über dem Esstisch, Lavendel und Rosmarin an den Mauern. Natursteinplatten und Terrakotta, zwei Liegen und eine Lichterkette. Referenz Valencia, 39 Grad Nord: den Sonnenstand mit einem nördlichen Plan vergleichen. Öffnet am Abend des 21. Juni 2026. Beispielentwurf.",
    "description_es": "Un patio entre muros a la hora dorada: un olivo y una higuera en tierra, limonero y naranjo en macetones, una palmera junto a la alberca, una vid en la pérgola sobre la mesa, lavanda y romero junto a los muros. Losas de piedra y terracota, dos tumbonas y una guirnalda de luces. Referencia Valencia, 39 grados norte: compare su sol con el de un plan del norte. Se abre la tarde del 21 de junio de 2026. Diseño ilustrativo.",
    "description_ru": "Дворик за стенами в золотой час: олива и инжир в грунте, лимон и апельсин в кадках, пальма у бассейна, виноград на перголе над обеденным столом, лаванда и розмарин вдоль стен. Каменные плиты и терракота, два шезлонга и гирлянда. Ориентир: Валенсия, 39 градусов северной широты: сравните солнце с северным планом. Открывается вечером 21 июня 2026 года. Примерный проект.",
    "description_fr": "Un patio clos à l’heure dorée : un olivier et un figuier en pleine terre, citronnier et oranger en bacs, un palmier de Chine près du bassin, une vigne sur la pergola au-dessus de la table. Lavande et romarin le long des murs. Dalles de pierre et terre cuite, deux chaises longues et une guirlande lumineuse. Référence : Valence, 39 degrés nord : comparez son soleil à celui d’un plan plus au nord. S’ouvre le soir du 21 juin 2026. Disposition illustrative.",
    "order": 2,
    "tags": ["mediterranean", "patio", "golden-hour"],
    "showcase_date": "2026-06-21", "showcase_utc_time": "18:25",
}


def build():
    T, plan = ObjectType, Plan(SLUG, 1200, 1000, layer=text("Courtyard", "Innenhof", "Patio"))
    plan.site("valencia")
    plan.rect(0, 0, 1200, 1000, T.TERRACE_PATIO, text("Flagstone patio", "Natursteinpatio", "Patio de losas"),
              fill=FillPattern.FLAGSTONE)
    plan.house([(0, 800), (1200, 800), (1200, 1000), (0, 1000)], text("House", "Haus", "Casa"),
               tall=620, roof="hip", pitch=22)
    plan.line([(8, 800), (8, 8), (1192, 8), (1192, 800)], T.WALL,
              text("Courtyard wall", "Hofmauer", "Muro del patio"), style=PathFenceStyle.STONE_WALL, tall=240)

    # ── the dining place under the vine
    plan.rect(110, 470, 420, 300, T.PERGOLA, text("Pergola", "Holzpergola", "Pérgola"), tall=260)
    plan.circle(320, 620, 62, T.TABLE_ROUND, text("Table", "Tisch", "Mesa"))
    chair = text("Chair", "Stuhl", "Silla")
    plan.rect(298, 705, 44, 44, T.CHAIR, chair)
    plan.rect(298, 491, 44, 44, T.CHAIR, chair, turn=180)
    plan.rect(205, 598, 44, 44, T.CHAIR, chair, turn=90)
    plan.rect(391, 598, 44, 44, T.CHAIR, chair, turn=-90)
    plan.plant("vitis vinifera", 130, 490, size=(260, 160))
    plan.plant("vitis vinifera", 510, 750, size=(260, 160))
    plan.line([(110, 770), (530, 470)], T.STRING_LIGHTS,
              text("String of lights", "Lichterkette", "Guirnalda de luces"), tall=250)

    # ── the water
    plan.rect(650, 120, 480, 320, T.TERRACE_PATIO, text("Terracotta surround", "Terrakotta-Umrandung", "Borde de terracota"),
              fill=FillPattern.TERRACOTTA)
    plan.polygon([(700, 165), (1080, 165), (1080, 395), (700, 395)], T.POND_POOL,
                 text("Plunge pool", "Tauchbecken", "Alberca"))
    lounger = text("Lounger", "Liege", "Tumbona")
    plan.rect(700, 470, 65, 190, T.LOUNGER, lounger)
    plan.rect(800, 470, 65, 190, T.LOUNGER, lounger)
    plan.circle(905, 610, 110, T.PARASOL, text("Parasol", "Sonnenschirm", "Sombrilla"), tall=240)
    lantern = text("Lantern", "Laterne", "Farol")
    for x, y in ((670, 140), (1110, 140), (670, 420), (1110, 420)):
        plan.circle(x, y, 12, T.GARDEN_LIGHT, lantern)

    # ── trees: two in the ground, two in tubs, a palm at the pool
    bed = text("Gravel bed", "Kiesbeet", "Parterre de grava")
    olive_bed = plan.circle(190, 300, 115, T.GARDEN_BED, bed, fill=FillPattern.GRAVEL)
    plan.plant("olea europaea", 190, 300, parent=olive_bed, size=(420, 320))
    fig_bed = plan.circle(150, 115, 95, T.GARDEN_BED, bed, fill=FillPattern.GRAVEL)
    plan.plant("ficus carica", 150, 115, parent=fig_bed, size=(280, 250))
    palm_bed = plan.circle(1130, 540, 55, T.GARDEN_BED, bed, fill=FillPattern.GRAVEL)
    plan.plant("trachycarpus fortunei", 1130, 540, parent=palm_bed, size=(380, 220))
    tub = text("Terracotta tub", "Terrakottakübel", "Macetón de terracota")
    lemon_tub = plan.circle(610, 730, 62, T.CONTAINER_ROUND, tub, tall=60, meta={"container_material": "terracotta"})
    plan.plant("citrus limon", 610, 730, parent=lemon_tub, size=(190, 120))
    orange_tub = plan.circle(1085, 725, 62, T.CONTAINER_ROUND, tub, tall=60, meta={"container_material": "terracotta"})
    plan.plant("citrus sinensis", 1085, 725, parent=orange_tub, size=(210, 120))
    pot = text("Planter pot", "Pflanztopf", "Maceta")
    for x, y in ((90, 790), (560, 460), (790, 800), (960, 800)):
        clay = plan.circle(x, y - 30, 26, T.CONTAINER_ROUND, pot, tall=35,
                           meta={"container_material": "terracotta"})
        plan.plant("pelargonium x hortorum", x, y - 30, parent=clay, size=(35, 40))

    # ── herbs along the walls
    west = plan.rect(28, 470, 62, 290, T.GARDEN_BED, text("Lavender border", "Lavendelsaum", "Arriate de lavanda"),
                     fill=FillPattern.GRAVEL)
    plan.row("lavandula angustifolia", (59, 510), (59, 720), 5, parent=west, size=(45, 50))
    east = plan.rect(1120, 610, 62, 180, T.GARDEN_BED, text("Rosemary border", "Rosmarinsaum", "Arriate de romero"),
                     fill=FillPattern.GRAVEL)
    plan.row("rosmarinus officinalis", (1151, 645), (1151, 755), 3, parent=east, size=(60, 55))
    south = plan.rect(330, 300, 250, 70, T.GARDEN_BED, text("Herb bed", "Kräuterbeet", "Bancal de hierbas"),
                      fill=FillPattern.GRAVEL)
    plan.row("salvia officinalis", (365, 335), (455, 335), 2, parent=south, size=(45, 50))
    plan.row("thymus vulgaris", (510, 335), (550, 335), 2, parent=south, planted="2024-04-20")
    plan.rect(330, 215, 150, 50, T.BENCH, text("Bench", "Sitzbank", "Banco"))

    plan.hint(300, 105, text(
        "21 Jun 2026, golden hour · 1  Open the 3D view: the low sun comes in over the west wall.\n"
        "2  Plan & Sun: go to 14:00. At 39° north the midday sun stands 74° high and shadows are short.\n"
        "3  Move the clock past sunset: the lanterns and the string of lights come on. Valencia; records are fictional.",
        "21.06.2026, goldene Stunde · 1  3D-Ansicht öffnen: die tiefe Sonne fällt über die Westmauer.\n"
        "2  Plan & Sonne: auf 14 Uhr gehen. Auf 39° Nord steht die Mittagssonne 74° hoch, die Schatten sind kurz.\n"
        "3  Uhr über den Sonnenuntergang stellen: Laternen und Lichterkette gehen an. Valencia; Einträge sind fiktiv.",
        "21 jun 2026, hora dorada · 1  Abra la vista 3D: el sol bajo entra por encima del muro oeste.\n"
        "2  Plano y sol: vaya a las 14:00. A 39° norte el sol del mediodía está a 74° y las sombras son cortas.\n"
        "3  Pase el reloj de la puesta de sol: se encienden los faroles y la guirnalda. Valencia; registros ficticios."),
        size=0.44)

    for key, entries in (
        ("rosmarinus officinalis", [("2026-05-09", 1, "bunch", a.AROMATIC), ("2026-06-13", 2, "bunch")]),
        ("salvia officinalis", [("2026-05-23", 1, "bunch", a.AROMATIC)]),
        ("thymus vulgaris", [("2025-06-07", 1, "bunch"), ("2026-05-30", 2, "bunch", a.AROMATIC)]),
    ):
        plan.harvest(key, entries)
    return plan.done()
