"""The family garden: the 3D view's showcase.

The very plan the bench fixture ``bench_small.ogp`` is, built by the same
``make_bench_plans.build_small`` so that it cannot drift from what every Beauty Board shows,
and with that fixture's item ids, because a plant's procedural shape is seeded by its id.
"""

from __future__ import annotations

from uuid import uuid5

from PyQt6.QtCore import QPointF

from open_garden_planner.core.commands import CreateItemsCommand, ResizeItemCommand
from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.growth_model import years_to_maturity
from open_garden_planner.core.item_look import adopt_pen, copy_visual_style, inherit_item_identity
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, PolylineItem
from open_garden_planner.ui.canvas.items.polygon_item import polygon_resize_apply

from . import authoring as a
from .i18n import text

SLUG = "family-garden"
IDS = "bench"

META = {
    "name_en": "Family garden - 24 x 16 m", "name_de": "Familiengarten - 24 x 16 m",
    "name_es": "Jardín familiar - 24 x 16 m",
    "name_ru": "Семейный сад - 24 x 16 м",
    "description_en": "A whole garden to explore in 3D: house, greenhouse, shed, terrace with pergola, lawn with pond and trampoline, three raised vegetable beds, fruit trees, hedge and fences. 61 plants. Berlin reference; opens on 21 June 2026 in daylight, ready for the 3D view. Illustrative layout.",
    "description_de": "Ein ganzer Garten zum Erkunden in 3D: Haus, Gewächshaus, Schuppen, Terrasse mit Pergola, Rasen mit Teich und Trampolin, drei Hochbeete, Obstbäume, Hecke und Zäune. 61 Pflanzen. Referenz Berlin; öffnet am 21. Juni 2026 bei Tageslicht, bereit für die 3D-Ansicht. Beispielentwurf.",
    "description_es": "Un jardín entero para explorar en 3D: casa, invernadero, cobertizo, terraza con pérgola, césped con estanque y cama elástica, tres bancales elevados, frutales, seto y vallas. 61 plantas. Referencia Berlín; se abre el 21 de junio de 2026 con luz de día, listo para la vista 3D. Diseño ilustrativo.",
    "description_ru": "Целый сад для изучения в 3D: дом, теплица, сарай, терраса с перголой, газон с прудом и батутом, три высокие грядки с овощами, плодовые деревья, живая изгородь и заборы. 61 растение. Ориентир: Берлин; открывается на 21 июня 2026 года при дневном свете, готов к просмотру в 3D. Примерный проект.",
    "order": 1,
    "tags": ["showcase", "3d", "family-garden"],
    "showcase_date": "2026-06-21", "showcase_utc_time": a.SHOWCASE_UTC_TIME,
}


# The showcase garden's own words (``family_garden``): every item name of the builder and
# every species name beyond the teaching plans'.
for _en, _de, _es in (
    ("Layer 1", "Ebene 1", "Capa 1"), ("Lawn", "Rasen", "Césped"), ("Terrace", "Terrasse", "Terraza"),
    ("Gravel yard", "Kieshof", "Patio de grava"), ("Pond", "Teich", "Estanque"),
    ("House", "Haus", "Casa"), ("Greenhouse", "Gewächshaus", "Invernadero"),
    ("Shed", "Schuppen", "Cobertizo"), ("Pergola", "Holzpergola", "Pérgola"),
    ("South fence", "Südzaun", "Valla sur"), ("East fence", "Ostzaun", "Valla este"),
    ("Beech hedge", "Buchenhecke", "Seto de haya"), ("Yard wall", "Hofmauer", "Muro del patio"),
    ("Gravel path", "Kiesweg", "Camino de grava"), ("Stepping stones", "Trittsteine", "Pasaderas"),
    ("Herb strip", "Kräuterstreifen", "Franja de hierbas"),
    ("Perennial border", "Staudenrabatte", "Arriate de vivaces"),
    ("Perennial border (east)", "Staudenrabatte (Ost)", "Arriate de vivaces (este)"),
    ("Flower bed", "Blumenbeet", "Parterre de flores"),
    ("Raised bed 1", "Hochbeet 1", "Bancal elevado 1"), ("Raised bed 2", "Hochbeet 2", "Bancal elevado 2"),
    ("Raised bed 3", "Hochbeet 3", "Bancal elevado 3"), ("Pot 1", "Topf 1", "Maceta 1"),
    ("Pot 2", "Topf 2", "Maceta 2"), ("Pot 3", "Topf 3", "Maceta 3"),
    ("Trellis", "Rankgitter", "Espaldera"), ("Table", "Tisch", "Mesa"), ("Chair", "Stuhl", "Silla"),
    ("BBQ", "Grill", "Barbacoa"), ("Fire pit", "Feuerstelle", "Hoguera"), ("Bench", "Sitzbank", "Banco"),
    ("Bird bath", "Vogeltränke", "Bebedero de pájaros"), ("Trampoline", "Trampolin", "Cama elástica"),
    ("Compost", "Kompost", "Compostador"), ("Wheelbarrow", "Schubkarre", "Carretilla"),
    ("Rain barrel", "Regentonne", "Barril de lluvia"),
    # species the teaching plans do not have; a name both languages share stays as it is
    ("Sage", "Salbei", "Salvia"), ("Oregano", "Oregano", "Orégano"), ("Lavender", "Lavendel", "Lavanda"),
    ("Peony", "Pfingstrose", "Peonía"), ("Iris", "Schwertlilie", "Lirio"),
    ("Echinacea", "Sonnenhut", "Equinácea"), ("Aster", "Aster", "Áster"),
    ("Chrysanthemum", "Chrysantheme", "Crisantemo"),
    ("Lily", "Lilie", "Azucena"), ("Pansy", "Stiefmütterchen", "Pensamiento"),
    ("Sunflower", "Sonnenblume", "Girasol"), ("Dahlia", "Dahlie", "Dalia"),
    ("Cosmos", "Schmuckkörbchen", "Cosmos"),
    ("Zinnia", "Zinnie", "Zinnia"), ("Tulip", "Tulpe", "Tulipán"), ("Tomato", "Tomate", "Tomate"),
    ("Sweet Pepper", "Paprika", "Pimiento"), ("Cabbage", "Kohl", "Col"), ("Kale", "Grünkohl", "Col rizada"),
    ("Onion", "Zwiebel", "Cebolla"), ("Beet", "Rote Bete", "Remolacha"), ("Zucchini", "Zucchini", "Calabacín"),
    ("Leek", "Lauch", "Puerro"), ("Spinach", "Spinat", "Espinaca"), ("Rosemary", "Rosmarin", "Romero"),
    ("Cucumber", "Gurke", "Pepino"), ("Hydrangea", "Hortensie", "Hortensia"), ("Rose", "Rose", "Rosal"),
    ("Lilac", "Flieder", "Lila"), ("Boxwood", "Buchsbaum", "Boj"), ("Forsythia", "Forsythie", "Forsitia"),
    ("Rhododendron", "Rhododendron", "Rododendro"), ("Blueberry", "Heidelbeere", "Arándano"),
    ("Raspberry", "Himbeere", "Frambuesa"), ("Gooseberry", "Stachelbeere", "Grosella espinosa"),
    ("Cherry Tree", "Kirschbaum", "Cerezo"), ("Birch", "Birke", "Abedul"), ("Pear Tree", "Birnbaum", "Peral"),
    ("Spruce", "Fichte", "Picea"), ("Magnolia", "Magnolie", "Magnolia"),
):
    text(_en, _de, _es)


#: Before the first day of a tour's default time-lapse (``tour_dialog.DEFAULT_SEASON``).
ESTABLISHED = "2026-03-01"


def establish(item):
    """A tree, a shrub, a perennial stood here before the season: a time-lapse from March shows
    it leafing out, not popping in on the fixture's one date. What ripens within a season keeps
    its planting day and comes up in the beds."""
    metadata = getattr(item, "metadata", None) or {}
    instance, species = metadata.get("plant_instance"), metadata.get("plant_species")
    if not instance or not species:
        return
    kind = item.object_type.name if getattr(item, "object_type", None) is not None else ""
    if years_to_maturity(species, kind) >= 1.0:
        instance["planting_date"] = ESTABLISHED


#: The showcase's two paths, as wide as a path one walks on. The bench fixture keeps the
#: 8 and 6 cm it was made with (``make_bench_plans.LEGACY_PATH_WIDTH_CM``: its pinned
#: numbers), and they were hairlines in the plan and in 3D (#795).
FAMILY_PATH_WIDTH_CM = {"Gravel path": 80.0, "Stepping stones": 50.0}


#: What stood in the 50 cm stepping-stone walk, and where it stands in the showcase: the
#: object's name or the plant's common name, and its centre. In the bench plan the walk is
#: a 6 cm line, so a bird bath 26 cm from it and two perennials beside it were clear; as a
#: walk it ran over them (review of #795). The path's own points stay: test data is pinned
#: to them, and so does the bench fixture's layout. The lily moves so that the
#: chrysanthemum, now east of the walk, keeps its distance from it.
FAMILY_MOVED_CM = {
    "Bird bath": (620.0, 450.0),         # was (560, 470): east of the walk, by the pond's end
    "Geranium": (612.0, 681.0),          # was x 630: the border's last plant west of the walk
    "Chrysanthemum": (746.0, 681.0),     # was x 712: the first plant east of it
    "Lily": (811.0, 681.0),              # was x 794
}

#: The cherry bears fruit in June (its fictional harvest below), so it is no tree of this
#: spring: planted in autumn 2022 as a nursery tree of this size (the growth model's low
#: end is the size AT planting). On the reference date its crown is the 3.7 m the plan was
#: drawn with; it is 6.4 m tall, where the spring-planted tree stood at 5.1 m.
FAMILY_CHERRY = {"planting_date": "2022-11-05", "current_spread_cm": 130.0,
                 "current_height_cm": 150.0}


def name_of(item):
    """An object's name, or a plant's common name (the bench builder names no plant)."""
    species = (getattr(item, "metadata", None) or {}).get("plant_species") or {}
    return getattr(item, "name", "") or species.get("common_name", "")


def _make_walks_clear(scene: CanvasScene) -> None:
    """Give the 50 cm stone walk and the 80 cm gravel walk room in the showcase (#866)."""
    gravel = next(item for item in scene.items()
                  if isinstance(item, PolylineItem) and item.name == "Gravel path")
    # Go around the birch on its east side, between the crown and the
    # vegetables before turning back toward the west side of the trellis.
    bends = [(1380, 840), (1515, 800), (1585, 705), (1638, 525),
             (1625, 486), (1566, 427), (1549, 400)]
    points = gravel.points
    rerouted = gravel.clone_with_points([points[0], *(QPointF(x, y) for x, y in bends), points[-1]])
    inherit_item_identity(gravel, rerouted)
    scene.removeItem(gravel)
    scene.addItem(rerouted)

    # The edges facing the stone walk follow its diagonal with a clearance
    # of just over 5 cm outside the stroke. The existing plants stay put.
    border = next(item for item in scene.items()
                  if isinstance(item, PolygonItem) and item.name == "Perennial border")
    position = {"pos_x": border.x(), "pos_y": border.y()}
    before = position | {"vertices": [{"x": p.x(), "y": p.y()} for p in border.polygon()]}
    west = [(180, 650), (630, 650), (662, 712), (180, 712)]
    after = position | {"vertices": [{"x": x, "y": y} for x, y in west]}
    ResizeItemCommand(border, before, after, polygon_resize_apply).execute()

    east = PolygonItem(
        [QPointF(700, 650), QPointF(1000, 650), QPointF(1000, 712), QPointF(730, 712)],
        ObjectType.GARDEN_BED, "Perennial border (east)", layer_id=border.layer_id,
    )
    # Derive one extra identity without consuming the bench builder's seed.
    east._item_id = uuid5(border.item_id, "family-garden-east-border")
    copy_visual_style(border, east)
    CreateItemsCommand(scene, [east]).execute()


def build():
    """The bench plan as an example: ``make_bench_plans.build_small``, one builder for both."""
    from make_bench_plans import BERLIN, build_small

    builder = build_small()
    widened, moved, cherries = set(), set(), 0
    for item in builder.scene.items():
        establish(item)
        name = name_of(item)
        if getattr(item, "object_type", None) is ObjectType.GARAGE_SHED:
            builder.filled(item, FillPattern.ROOF_TILES)
        if getattr(item, "object_type", None) is ObjectType.PATH and item.name in FAMILY_PATH_WIDTH_CM:
            pen = item.pen()
            pen.setWidthF(FAMILY_PATH_WIDTH_CM[item.name])
            adopt_pen(item, pen)
            widened.add(item.name)
        if name in FAMILY_MOVED_CM and isinstance(item, CircleItem):
            assert name not in moved, name          # each name stands for one object
            centre = item.mapToParent(item.rect().center())
            item.moveBy(FAMILY_MOVED_CM[name][0] - centre.x(), FAMILY_MOVED_CM[name][1] - centre.y())
            moved.add(name)
        if name == "Cherry Tree":
            item.metadata["plant_instance"] = dict(FAMILY_CHERRY)
            cherries += 1
    assert widened == set(FAMILY_PATH_WIDTH_CM), widened
    assert moved == set(FAMILY_MOVED_CM) and cherries == 1, (moved, cherries)
    _make_walks_clear(builder.scene)
    manager = ProjectManager()
    manager.set_location(dict(BERLIN) | {"timezone": "Europe/Berlin"})
    # What a Berlin garden planted on 15 April (its trees stood before) has given by 21 June.
    for key, entries in (
        ("lactuca sativa", [("2026-05-30", 180, "g", a.OUTER_LEAVES), ("2026-06-12", 220, "g", a.CRISP)]),
        ("spinacia oleracea", [("2026-05-22", 250, "g", a.TENDER), ("2026-06-05", 300, "g")]),
        ("allium schoenoprasum", [("2026-05-15", 1, "bunch"), ("2026-06-08", 2, "bunch")]),
        ("petroselinum crispum", [("2026-06-02", 1, "bunch")]),
        ("ocimum basilicum", [("2026-06-14", 1, "bunch", a.AROMATIC)]),
        ("prunus avium", [("2026-06-13", 2.5, "kg", a.FIRST_PICK), ("2026-06-19", 4, "kg", a.SWEET)]),
    ):
        a.harvest(manager, "family-garden", a.first(builder.scene, key), entries)
    return builder.scene, manager
