"""The modern garden: straight lines, few materials, and light for the evening.

A flat-roofed bungalow, a slate terrace with a hot tub and a fire pit, a reflecting pool
in the lawn, corten-steel beds with grasses, a red Japanese maple as the one accent. It
opens at golden hour; its second stored tour runs from that light into the night, and
the garden lights come on as the sun goes down.
"""

from __future__ import annotations

from datetime import time

from . import authoring as a
from .i18n import text
from .plan import FillPattern, ObjectType, PathFenceStyle, Plan
from .tours import orbit_tour

SLUG = "modern-garden"
#: The stored orbit looks down more steeply than the dialog's 18 degrees: from there
#: the wall hid the garden behind it (3D review of #940).
ORBIT_PITCH_DEG = 30.0
CORTEN = "#8b4a2a"
DUSK = text("Evening into night", "Vom Abend in die Nacht", "Del atardecer a la noche")

META = {
    "name_en": "Modern garden - 15 x 12 m", "name_de": "Designgarten - 15 x 12 m",
    "name_es": "Jardín moderno - 15 x 12 m",
    "name_ru": "Современный сад - 15 x 12 м",
    "description_en": "Straight lines and few materials: a flat-roofed bungalow, a slate terrace with hot tub, loungers and fire pit, a reflecting pool in the lawn, corten-steel beds with miscanthus and lavender, a bamboo screen and a red Japanese maple. Guide lines carry the grid. Lanterns and a string of lights: play the stored tour from evening into night and they come on. Munich reference; opens at golden hour on 15 August 2026. Illustrative layout.",
    "description_de": "Klare Linien und wenige Materialien: Flachdach-Bungalow, Schieferterrasse mit Whirlpool, Liegen und Feuerstelle, ein Wasserbecken im Rasen, Cortenstahl-Beete mit Chinaschilf und Lavendel, ein Bambus-Sichtschutz und ein roter Fächerahorn. Hilfslinien tragen das Raster. Laternen und Lichterkette: die gespeicherte Fahrt vom Abend in die Nacht abspielen, dann gehen sie an. Referenz München; öffnet zur goldenen Stunde am 15. August 2026. Beispielentwurf.",
    "description_es": "Líneas rectas y pocos materiales: un bungaló de cubierta plana, una terraza de pizarra con bañera de hidromasaje, tumbonas y hoguera, un estanque espejo en el césped, bancales de acero corten con eulalia y lavanda, una pantalla de bambú y un arce japonés rojo. Las guías marcan la retícula. Faroles y guirnalda: reproduzca el recorrido del atardecer a la noche y se encienden. Referencia Múnich; se abre a la hora dorada del 15 de agosto de 2026. Diseño ilustrativo.",
    "description_ru": "Прямые линии и немного материалов: бунгало с плоской крышей, сланцевая терраса с джакузи, шезлонгами и очагом, зеркальный бассейн на газоне, грядки из кортеновской стали с мискантусом и лавандой, ширма из бамбука и красный японский клён. Направляющие задают сетку. Фонари и гирлянда: запустите сохранённый облёт от вечера к ночи, и они зажгутся. Ориентир: Мюнхен; открывается в золотой час 15 августа 2026 года. Примерный проект.",
    "order": 5,
    "tags": ["modern", "lights", "dusk"],
    "showcase_date": "2026-08-15", "showcase_utc_time": "17:40",
}


def more_tours(framing):
    """The same orbit while the evening passes: 19:15 to 21:00 on a Central European
    summer clock. The sun sets at about 20:30 in Munich in mid August, and the lamps are
    fully on when it stands three degrees under the horizon. It ends in twilight, six
    degrees under: later, the faces turned away from the moon are black (#953)."""
    return [orbit_tour(framing.orbit(), DUSK, time_range=(time(19, 15), time(21, 0)))]


def build():
    T, plan = ObjectType, Plan(SLUG, 1500, 1200, layer=text("Garden", "Garten", "Jardín"))
    plan.site("munich")
    plan.rect(0, 0, 1500, 1200, T.LAWN, text("Lawn", "Rasen", "Césped"))
    plan.line([(8, 820), (8, 8), (1492, 8), (1492, 1192), (900, 1192)], T.WALL,
              text("Garden wall", "Gartenmauer", "Muro del jardín"), style=PathFenceStyle.STONE_WALL, tall=180)

    # ── the house and its terrace
    plan.house([(0, 820), (900, 820), (900, 1200), (0, 1200)], text("Bungalow", "Bungalow", "Bungaló"),
               tall=320, roof="flat", ridge=False, fill=FillPattern.CONCRETE, color="#c9c7c1")
    plan.rect(0, 520, 900, 300, T.TERRACE_PATIO, text("Slate terrace", "Schieferterrasse", "Terraza de pizarra"),
              fill=FillPattern.SLATE, color="#7b8088")
    plan.rect(680, 560, 190, 190, T.HOT_TUB, text("Hot tub", "Whirlpool", "Bañera de hidromasaje"), tall=85)
    lounger = text("Lounger", "Liege", "Tumbona")
    plan.rect(70, 560, 65, 190, T.LOUNGER, lounger)
    plan.rect(165, 560, 65, 190, T.LOUNGER, lounger)
    plan.circle(450, 650, 50, T.FIRE_PIT, text("Fire pit", "Feuerstelle", "Hoguera"))
    plan.rect(330, 705, 150, 50, T.BENCH, text("Bench", "Sitzbank", "Banco"))
    plan.line([(30, 800), (880, 540)], T.STRING_LIGHTS,
              text("String of lights", "Lichterkette", "Guirnalda de luces"), tall=260)

    # ── the lawn: a reflecting pool, box spheres, the maple
    plan.polygon([(150, 170), (750, 170), (750, 370), (150, 370)], T.POND_POOL,
                 text("Reflecting pool", "Wasserbecken", "Estanque espejo"))
    for x in (90, 290, 490, 690, 860):
        plan.plant("buxus sempervirens", x, 455, size=(60, 65))
    maple_bed = plan.circle(1010, 280, 115, T.GARDEN_BED, text("Pebble bed", "Kieselbeet", "Parterre de guijarros"),
                            fill=FillPattern.PEBBLES)
    plan.plant("acer palmatum", 1010, 280, parent=maple_bed, size=(300, 280))

    # ── the east side: pebbles, stepping stones, three corten beds, the bamboo screen
    plan.rect(900, 520, 600, 680, T.TERRACE_PATIO, text("Pebble court", "Kieselhof", "Patio de guijarros"),
              fill=FillPattern.PEBBLES)
    plan.line([(900, 670), (1010, 670), (1010, 1100), (940, 1160)], T.PATH,
              text("Stepping stones", "Trittsteine", "Pasaderas"), style=PathFenceStyle.STEPPING_STONES, wide=55)
    corten = text("Corten bed", "Cortenbeet", "Bancal de corten")
    # a metal container, not a raised bed: a raised bed's frame is always timber in 3D
    steel = {"container_material": "metal"}
    beds = [plan.rect(1090, y, 330, 95, T.CONTAINER, corten, tall=50, fill=FillPattern.CORTEN,
                      color=CORTEN, meta=steel) for y in (600, 790, 980)]
    plan.row("miscanthus sinensis", (1140, 647), (1370, 647), 3, parent=beds[0], size=(150, 90))
    plan.row("lavandula angustifolia", (1130, 837), (1380, 837), 5, parent=beds[1], size=(45, 50))
    plan.row("miscanthus sinensis", (1140, 1027), (1370, 1027), 3, parent=beds[2], size=(150, 90))
    screen = plan.rect(1405, 70, 70, 400, T.CONTAINER, text("Bamboo trough", "Bambustrog", "Jardinera de bambú"),
                       tall=50, fill=FillPattern.CORTEN, color=CORTEN, meta=steel)
    plan.row("fargesia murielae", (1440, 110), (1440, 430), 5, parent=screen, size=(320, 85))

    # ── light for the evening
    lantern = text("Lantern", "Laterne", "Farol")
    for x, y in ((130, 150), (450, 150), (770, 150), (130, 390), (450, 390), (770, 390),
                 (1060, 600), (1060, 790), (1060, 980), (1180, 280)):
        plan.circle(x, y, 12, T.GARDEN_LIGHT, lantern)

    # ── the grid the garden is drawn on
    plan.guide(x=900)
    plan.guide(y=520)
    plan.guide(y=170)
    plan.guide(y=370)

    plan.hint(40, 110, text(
        "15 Aug 2026, golden hour · 1  3D view → Camera Tour: play “Evening into night”. The lanterns come on at sunset.\n"
        "2  The four guide lines carry the grid: drag the pool's edge and it snaps to them.\n"
        "3  Plan & Sun: set the clock to 13:00 and compare the flat roof's short shadow. Munich reference.",
        "15.08.2026, goldene Stunde · 1  3D-Ansicht → Kamerafahrt: „Vom Abend in die Nacht“. Bei Sonnenuntergang gehen die Laternen an.\n"
        "2  Die vier Hilfslinien tragen das Raster: Beckenkante ziehen, sie rastet daran ein.\n"
        "3  Plan & Sonne: Uhr auf 13 Uhr stellen und den kurzen Schatten des Flachdachs vergleichen. Referenz München.",
        "15 ago 2026, hora dorada · 1  Vista 3D → Recorrido de cámara: «Del atardecer a la noche». Los faroles se encienden al ponerse el sol.\n"
        "2  Las cuatro guías marcan la retícula: arrastre el borde del estanque y se ajusta a ellas.\n"
        "3  Plan y sol: ponga el reloj a las 13:00 y compare la sombra corta de la cubierta plana. Referencia Múnich."),
        size=0.42, ink=a.NOTE_ON_LAWN, bold=True)
    return plan.done()
