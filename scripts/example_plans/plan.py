"""A new example plan under construction.

``Plan`` holds the scene and the project manager and adds items through the production
constructors. Every item gets an id made from what it is and where it stands, so that
moving or adding one item changes no other id: a plant's sprite turn and its 3D shape are
seeded by its id, and a plan that is tuned by eye must not reshuffle on every edit.

Scene frame: x grows to the east, y to the north, in centimetres from the plan's
south-west corner (the canvas view flips Qt's y for display).
"""

from __future__ import annotations

import random
from uuid import NAMESPACE_URL, UUID, uuid5

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPolygonF

from open_garden_planner.core.commands import CreateItemsCommand
from open_garden_planner.core.constraints import AnchorRef
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.guild_commands import GuildMembershipCommand
from open_garden_planner.core.item_look import adopt_pen
from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
from open_garden_planner.core.object_height import METADATA_KEY as HEIGHT_KEY
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints
from open_garden_planner.core.roof_style import OVERHANG_KEY, PITCH_KEY, ROOF_STYLES, STYLE_KEY
from open_garden_planner.models.layer import Layer
from open_garden_planner.models.plant_data import species_key
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord
from open_garden_planner.models.succession import SuccessionEntry, SuccessionPlan
from open_garden_planner.services.bundled_species_db import get_species_db
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene, GuideLine
from open_garden_planner.ui.canvas.geometry_apply import apply_rotation
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
    TextItem,
)
from open_garden_planner.ui.plant_creation import build_species_plant

from . import authoring as a
from .i18n import TRANSLATIONS, text
from .sites import SITES

GARDEN = text("Garden", "Garten", "Jardín")
#: The bundled guild templates' own words in the plans' languages. The templates ship an
#: English and a German text; the Spanish is authored here, beside the German it matches.
GUILD_WORDS = {
    "three-sisters-mound": {
        "name": ("Drei-Schwestern-Beet", "Montículo de las tres hermanas"),
        "description": (
            "Mais, kletternde Feuerbohnen und Winterkürbis. Standfeste Maissorten wählen und "
            "zeitlich versetzt säen. Stickstofffixierung versorgt Nachbarpflanzen nicht sofort; "
            "Pflanzenreste setzen Stickstoff später frei.",
            "Maíz, judías escarlata trepadoras y calabaza de invierno. Elija variedades de maíz "
            "robustas y escalone la siembra. La fijación de nitrógeno no lo pone de inmediato a "
            "disposición de los cultivos vecinos; los restos lo liberan más tarde."),
        "attribution": (
            "Mitwirkende von Open Garden Planner; Anbaukontext von Cornell Cooperative Extension, "
            "in Anerkennung der indigenen Drei-Schwestern-Tradition.",
            "Colaboradores de Open Garden Planner; contexto de cultivo de Cornell Cooperative "
            "Extension, en reconocimiento de la tradición indígena de las tres hermanas."),
    },
    "walnut-tolerant-guild": {
        "name": ("Walnussverträgliche Gilde", "Gremio tolerante al nogal"),
        "description": (
            "Walnuss mit bestäuberfreundlichen Astern. Die Verträglichkeitsangaben beruhen "
            "überwiegend auf Beobachtungen; Art, Boden und Bedingungen bleiben entscheidend.",
            "Nogal con ásteres para polinizadores. Penn State describe las especies de Aster como "
            "tolerantes sobre todo a partir de observaciones; la especie, el suelo y las "
            "condiciones siguen siendo decisivos."),
        "attribution": (
            "Mitwirkende von Open Garden Planner; berichtete Verträglichkeit von Penn State "
            "Extension, Bestäuberfunktion von RHS.",
            "Colaboradores de Open Garden Planner; tolerancia descrita por Penn State Extension, "
            "función polinizadora según RHS."),
    },
}
#: The day a plan's trees, shrubs and perennials stood by: before a year's time-lapse
#: starts, so that they leaf out in it and do not pop in (``family_garden.ESTABLISHED``).
ESTABLISHED = "2026-03-01"


class Plan:
    """One example plan: its scene, its manager and the ids of its items."""

    def __init__(self, slug: str, width_cm: float, height_cm: float, *, layer: str = GARDEN,
                 planted: str = ESTABLISHED) -> None:
        self.slug = slug
        self.scene = CanvasScene(width_cm=width_cm, height_cm=height_cm)
        self.manager = ProjectManager()
        self.planted = planted
        self._ids: set[UUID] = set()
        self._hint_layer: Layer | None = None
        self.ground = self.scene.active_layer
        self.ground.name = layer
        self.ground.id = self._id("layer", layer)

    # ── ids ──────────────────────────────────────────────────────────────────

    def _id(self, *parts: object) -> UUID:
        made = uuid5(NAMESPACE_URL, f"ogp-example/{self.slug}/" + ":".join(str(p) for p in parts))
        assert made not in self._ids, f"{self.slug}: two items are the same {parts}"
        self._ids.add(made)
        return made

    def _add(self, item, kind, name, x, y, layer=None):
        item._item_id = self._id(kind.name, name, f"{x:g},{y:g}")
        item.layer_id = (layer or self.ground).id
        self.scene.addItem(item)
        return item

    @staticmethod
    def _dress(item, height, fill, color, meta):
        if height is not None:
            item.metadata[HEIGHT_KEY] = float(height)
        if meta:
            item.metadata.update(meta)
        if color is not None:
            item.fill_color = QColor(color)
        if fill is not None:
            item.fill_pattern = fill
        if fill is not None or color is not None:
            item.setBrush(create_pattern_brush(item.fill_pattern, item.fill_color))
        return item

    # ── shapes ───────────────────────────────────────────────────────────────

    def rect(self, x, y, width, height, kind, name="", *, tall=None, fill=None, color=None,
             turn=0.0, meta=None, layer=None):
        """A rectangle with its south-west corner at (x, y); ``turn`` degrees about its
        centre, ``tall`` its height above the ground in cm."""
        item = RectangleItem(x, y, width, height, object_type=kind, name=name)
        self._add(self._dress(item, tall, fill, color, meta), kind, name, x, y, layer)
        if turn:
            apply_rotation(item, turn)
        return item

    def polygon(self, points, kind, name="", *, tall=None, fill=None, color=None, meta=None,
                layer=None):
        item = PolygonItem([QPointF(x, y) for x, y in points], object_type=kind, name=name)
        return self._add(self._dress(item, tall, fill, color, meta), kind, name, *points[0], layer)

    def circle(self, x, y, radius, kind, name="", *, tall=None, fill=None, color=None, meta=None,
               layer=None):
        item = CircleItem(x, y, radius, object_type=kind, name=name)
        return self._add(self._dress(item, tall, fill, color, meta), kind, name, x, y, layer)

    def line(self, points, kind, name="", *, style=PathFenceStyle.NONE, tall=None, wide=None,
             layer=None):
        """A path, fence or wall along ``points``; ``wide`` is a path's width in cm."""
        item = PolylineItem([QPointF(x, y) for x, y in points], object_type=kind, name=name,
                            path_fence_style=style)
        if tall is not None:
            item.metadata[HEIGHT_KEY] = float(tall)
        if wide is not None:
            pen = item.pen()
            pen.setWidthF(float(wide))
            adopt_pen(item, pen)
        return self._add(item, kind, name, *points[0], layer)

    # ── buildings ────────────────────────────────────────────────────────────

    @staticmethod
    def _roof(item, roof, pitch, overhang):
        if roof is not None:
            assert roof in ROOF_STYLES, roof
            item.metadata[STYLE_KEY] = roof
        if pitch is not None:
            item.metadata[PITCH_KEY] = float(pitch)
        if overhang is not None:
            item.metadata[OVERHANG_KEY] = float(overhang)
        return item

    def _ridge(self, owner, polygon, finish=None):
        """The linked ROOF_RIDGE of a house or a greenhouse, as the drawing tool makes it."""
        p1, p2 = compute_roof_ridge_endpoints(polygon, owner.pos())
        ridge = PolylineItem([p1, p2], object_type=ObjectType.ROOF_RIDGE)
        ridge._item_id = self._id("ROOF_RIDGE", owner.item_id)
        ridge.layer_id = owner.layer_id
        self.scene.addItem(ridge)
        ridge.set_metadata("owner_polygon_id", str(owner.item_id))
        if finish:
            ridge.set_metadata("ridge_finish", finish)
            ridge.stroke_color = QColor(176, 181, 185)
            ridge._setup_styling()
        owner.set_metadata("ridge_item_id", str(ridge.item_id))
        return ridge

    def house(self, points, name, *, tall=None, roof=None, pitch=None, overhang=None, ridge=True,
              fill=None, color=None):
        """A HOUSE polygon. With ``ridge`` it gets its linked roof ridge (a gable or a hip
        along it); a flat-roofed house has none, and ``fill`` gives it a roof that does not
        read as tiles in the plan."""
        house = self.polygon(points, ObjectType.HOUSE, name, tall=tall, fill=fill, color=color)
        self._roof(house, roof, pitch, overhang)
        if ridge:
            self._ridge(house, house.polygon())
        return house

    def shed(self, x, y, width, height, kind, name, *, tall=None, roof=None, pitch=None,
             overhang=None, turn=0.0, fill=None):
        """A GARAGE_SHED or TOOL_SHED rectangle with its roof style."""
        assert kind in (ObjectType.GARAGE_SHED, ObjectType.TOOL_SHED), kind
        return self._roof(self.rect(x, y, width, height, kind, name, tall=tall, turn=turn,
                                    fill=fill), roof, pitch, overhang)

    def greenhouse(self, x, y, width, height, name):
        """A GREENHOUSE with its linked aluminium ridge (#768)."""
        item = self.rect(x, y, width, height, ObjectType.GREENHOUSE, name)
        rect = item.rect()
        self._ridge(item, QPolygonF([rect.topLeft(), rect.topRight(), rect.bottomRight(),
                                     rect.bottomLeft()]), finish="aluminium")
        return item

    # ── plants ───────────────────────────────────────────────────────────────

    def plant(self, key, x, y, *, parent=None, planted=None, size=None, layer=None):
        """One plant of the bundled species ``key`` (its scientific name in lower case).

        ``size`` is ``(height_cm, spread_cm)`` on the planting day: a tree that stood here
        before is given the size it has, a seedling none. The plant is created the way a
        drop from the gallery creates it, so its parent bed is found by geometry; naming
        ``parent`` asserts that it landed there.
        """
        item = build_species_plant(self.scene, QPointF(x, y), get_species_db()[key])
        common = item.metadata["plant_species"]["common_name"]
        assert common in TRANSLATIONS, f"{common!r} has no translation: add it to i18n.SPECIES_NAMES"
        item.name = common
        instance = {"planting_date": planted or self.planted}
        if size:
            instance.update(current_height_cm=float(size[0]), current_spread_cm=float(size[1]))
            item.set_radius_centered(float(size[1]) / 2.0)
        item.metadata["plant_instance"] = instance
        item._item_id = self._id("PLANT", key, f"{x:g},{y:g}")
        item.layer_id = (layer or self.ground).id
        CreateItemsCommand(self.scene, [item]).execute()
        if parent is not None:
            assert item.parent_bed_id == parent.item_id, (self.slug, key, x, y)
        return item

    def row(self, key, start, end, count, **how):
        """``count`` plants evenly from ``start`` to ``end``, both ends included."""
        (x0, y0), (x1, y1) = start, end
        steps = max(count - 1, 1)
        return [self.plant(key, round(x0 + (x1 - x0) * i / steps, 1),
                           round(y0 + (y1 - y0) * i / steps, 1), **how) for i in range(count)]

    def grid(self, key, x, y, columns, rows, dx, dy, **how):
        """A block of plants: the first at (x, y), ``dx`` apart to the east, ``dy`` north."""
        return [self.plant(key, x + dx * column, y + dy * row, **how)
                for row in range(rows) for column in range(columns)]

    def drift(self, key, area, count, *, gap, seed="", **how):
        """``count`` plants scattered in ``area`` (x, y, width, height), at least ``gap``
        cm apart. The scatter is the same on every run: it is seeded by the plan, the
        species and ``seed``."""
        x, y, width, height = area
        rng = random.Random(f"{self.slug}/{key}/{seed}")
        placed: list[tuple[float, float]] = []
        for _attempt in range(count * 400):
            if len(placed) == count:
                break
            px, py = round(rng.uniform(x, x + width), 1), round(rng.uniform(y, y + height), 1)
            if all((px - qx) ** 2 + (py - qy) ** 2 >= gap * gap for qx, qy in placed):
                placed.append((px, py))
        assert len(placed) == count, (self.slug, key, "the area is too small for the drift")
        return [self.plant(key, px, py, **how) for px, py in placed]

    # ── words and layers ─────────────────────────────────────────────────────

    def layer(self, name, **how):
        """A further layer above the ones there are."""
        layer = Layer(id=self._id("layer", name), name=name,
                      z_order=max(each.z_order for each in self.scene.layers) + 1, **how)
        self.scene.add_layer(layer)
        return layer

    def hint(self, x, y, content, *, size=0.42, ink=a.NOTE_ON_PALE, bold=False):
        """The plan's one text: what it shows and what to try, on the hint layer."""
        assert self._hint_layer is None, "a plan has one hint"
        self._hint_layer = a.hint_layer(self.scene, self.slug)
        item = TextItem(x, y, content=content, font_size=size, bold=bold, text_color=QColor(ink))
        return self._add(item, ObjectType.GENERIC_TEXT, "hint", x, y, self._hint_layer)

    # ── the plan's data ──────────────────────────────────────────────────────

    def site(self, place):
        self.manager.set_location(dict(SITES[place]))

    def north(self, angle_deg):
        """True north on the plan, clockwise from plan-up."""
        self.manager.set_north_angle(angle_deg)

    def soil(self, bed, *, ph=6.5, day="2026-05-20", texture="loamy", levels=(1, 2, 3)):
        target = str(bed.item_id)
        record = SoilTestRecord(date=day, ph=ph, n_level=levels[0], p_level=levels[1],
                                k_level=levels[2], soil_texture=texture, notes=a.SOIL_NOTE)
        self.manager.set_soil_test_history(target, SoilTestHistory(target, [record]))

    def harvest(self, key, entries):
        """A fictional harvest history on the south-westernmost plant of species ``key``."""
        a.harvest(self.manager, self.slug, a.first(self.scene, key), entries)

    def succession(self, bed, year, entries):
        """``entries``: ``(species key, start date, end date)`` rows for ``bed``."""
        target = str(bed.item_id)
        rows = [SuccessionEntry(species_key=key, scientific_name=key,
                                common_name=get_species_db()[key]["common_name"],
                                start_date=start, end_date=end) for key, start, end in entries]
        for row in rows:
            assert row.common_name in TRANSLATIONS, row.common_name
        self.manager.set_succession_plan(target, SuccessionPlan(target, year, rows).to_dict())

    def guild(self, template_id, name, centre, members):
        """Make ``centre`` and ``members`` (``{role: [plants]}``) one guild of the bundled
        template ``template_id``. The plants stand where the plan put them."""
        library = GuildLibrary(user_dir=BUNDLED_EXAMPLES / "_no_user_guilds")
        template = library.templates[template_id].to_dict()
        for field, (german, spanish) in GUILD_WORDS[template_id].items():
            text(template[field], german, spanish)
        guild_id = str(self._id("guild", template_id, name))
        changes = [(centre, {"guild_id": guild_id, "role": "centre", "name": name,
                             "template": template})]
        for role, plants in members.items():
            changes += [(plant, {"guild_id": guild_id, "role": role}) for plant in plants]
        GuildMembershipCommand(changes).execute()
        assert species_key(centre.metadata["plant_species"]) == template["centre"], template_id

    def guide(self, *, x=None, y=None):
        """A guide line: vertical at ``x`` or horizontal at ``y``."""
        assert (x is None) != (y is None)
        self.scene.guide_lines.append(GuideLine(is_horizontal=x is None,
                                                position=float(y if x is None else x)))

    def distance(self, first, second, *, anchors=(AnchorType.CENTER, AnchorType.CENTER),
                 indexes=(0, 0)):
        """A distance constraint between two items, drawn as a dimension line. Its length is
        the distance the two anchors have now: the plan is drawn to measure, and a
        constraint that disagreed with the drawing would move an item on the first edit."""
        points = []
        for item, kind, index in zip((first, second), anchors, indexes, strict=True):
            found = [anchor.point for anchor in get_anchor_points(item)
                     if anchor.anchor_type is kind and anchor.anchor_index == index]
            assert len(found) == 1, (self.slug, item.name, kind, index, len(found))
            points.append(found[0])
        cm = round(((points[0].x() - points[1].x()) ** 2
                    + (points[0].y() - points[1].y()) ** 2) ** 0.5, 1)
        assert cm > 0, (self.slug, first.name, second.name)
        return self.scene.constraint_graph.add_constraint(
            AnchorRef(first.item_id, anchors[0], indexes[0]),
            AnchorRef(second.item_id, anchors[1], indexes[1]), cm,
            constraint_id=self._id("constraint", first.item_id, second.item_id, *anchors))

    def done(self):
        assert self.manager.location, f"{self.slug} has no place"
        for item in self.scene.items():
            if isinstance(item, TextItem):
                assert self.scene.canvas_rect.contains(item.sceneBoundingRect()), (
                    self.slug, "the hint runs off the plan", item.sceneBoundingRect())
        return self.scene, self.manager


__all__ = ["ESTABLISHED", "AnchorType", "FillPattern", "ObjectType", "PathFenceStyle", "Plan"]
