"""The five species of the #940 example plans, end to end (§8.10).

gallery entry → the real ``dropEvent`` (and the plant database's own constructor,
``ui/plant_creation.build_species_plant``) → species data → the sprite the canvas
draws → ``snapshot_records`` → the Plant Forge mesh 3D builds.

Japanese Maple, Bamboo and Grape Vine have recipes of their own; Miscanthus and
Windmill Palm draw a category's look through an exact alias. A species record
cannot reach the ornamental-grass or palm category by itself — the database's
constructor picks a category from the height alone — which is what the aliases
are for: both constructors must end on the same sprite.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt
from PyQt6.QtGui import QDropEvent

from open_garden_planner.core import plant_renderer
from open_garden_planner.core.object_height import effective_height_cm
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.phenology import evaluate_phenology
from open_garden_planner.core.plant_art import SpriteRef, traits_for
from open_garden_planner.core.plant_forge import (
    FRUIT_PART,
    PART_FOLIAGE,
    enrich_climber_records,
    forge_record,
)
from open_garden_planner.core.scene3d.builders.plants import plant_sprite
from open_garden_planner.services.bundled_species_db import lookup_species
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.plant_creation import build_species_plant
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from open_garden_planner.ui.widgets.gallery_data import all_items, build_toolbar_categories

JUNE, OCTOBER = date(2026, 6, 21), date(2026, 10, 15)
FROST = {"last_spring_frost": "05-15", "first_fall_frost": "10-15"}

#: gallery name → (scientific name, the sprite both views draw, the 3D archetype)
NEW_SPECIES = {
    "Japanese Maple": ("Acer palmatum", SpriteRef("species", "japanese_maple"), "canopy"),
    "Bamboo": ("Fargesia murielae", SpriteRef("species", "bamboo"), "grass"),
    "Miscanthus": ("Miscanthus sinensis", SpriteRef("categories", "ornamental_grass"), "grass"),
    "Windmill Palm": ("Trachycarpus fortunei", SpriteRef("categories", "palm"), "palm"),
    "Grape Vine": ("Vitis vinifera", SpriteRef("species", "grape_vine"), "climber"),
}


def _drop(view: CanvasView, data: str, at: QPointF) -> CircleItem:
    before = {id(item) for item in view.scene().items()}
    mime = QMimeData()
    mime.setText(f"gallery:{data}")
    view.dropEvent(QDropEvent(QPointF(view.mapFromScene(at)), Qt.DropAction.CopyAction, mime,
                              Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    new = [item for item in view.scene().items()
           if isinstance(item, CircleItem) and id(item) not in before]
    assert len(new) == 1
    return new[0]


def _drawn(item: CircleItem) -> SpriteRef:
    path = plant_renderer._resolve_svg_path(item.object_type, item.plant_species, item.plant_category)
    assert path is not None
    return SpriteRef(path.parent.name, path.stem)


def test_each_new_species_is_dropped_drawn_and_built_as_one_plant(canvas: CanvasView) -> None:
    entries = {entry.name: entry for entry in all_items(build_toolbar_categories())}
    for n, (name, (scientific, sprite, archetype)) in enumerate(NEW_SPECIES.items()):
        entry = entries[name]
        assert entry.thumbnail is not None, name                 # a picture in the gallery
        item = _drop(canvas, f"{entry.tool_type.name}:species={entry.species}",
                     QPointF(300.0 + 700.0 * n, 400.0))
        species = item.metadata["plant_species"]
        assert species["scientific_name"] == scientific
        assert species["data_source"] == "bundled"
        assert item.radius == pytest.approx(species["max_spread_cm"] / 2.0)
        assert _drawn(item) == sprite, name                      # 2D

        record = snapshot_records(canvas.scene(), JUNE)[str(item.item_id)]
        assert plant_sprite(record) == sprite, name              # 3D: the same sprite
        assert traits_for(sprite).archetype == archetype
        parts = forge_record(record)
        positions = np.concatenate([part.mesh.positions for part in parts])
        expected = effective_height_cm(item.object_type, item.metadata, JUNE)
        assert record.height_cm == pytest.approx(expected)
        assert float(positions[:, 2].max()) == pytest.approx(expected, rel=0.03)   # truth: height
        assert float(positions[:, 2].min()) == pytest.approx(0.0, abs=0.5)        # on the ground
        assert any(part.name == PART_FOLIAGE for part in parts)


@pytest.mark.parametrize("name", ["Miscanthus", "Windmill Palm"])
def test_the_database_constructor_reaches_the_category_look(canvas: CanvasView, name: str) -> None:
    """The plant database places a species by its height only (SHRUB / spreading shrub
    for Miscanthus, TREE / round deciduous for the palm); the exact alias still draws
    the grass and the palm, in 2D and in 3D."""
    record = lookup_species(name)
    assert record is not None
    item = build_species_plant(canvas.scene(), QPointF(500.0, 500.0), dict(record))
    canvas.scene().addItem(item)
    assert item.plant_category is not None and item.plant_category.name in (
        "SPREADING_SHRUB", "ROUND_DECIDUOUS")
    sprite = NEW_SPECIES[name][1]
    assert _drawn(item) == sprite
    assert plant_sprite(snapshot_records(canvas.scene(), JUNE)[str(item.item_id)]) == sprite


def test_a_grape_vine_on_a_pergola_bears_grapes_in_october_only(canvas: CanvasView) -> None:
    """The vine climbs the pergola it stands beside and hangs its grapes in its fruit
    months, September and October, not in June. Its record carries no harvest window in
    weeks after the last frost: that put ripe grapes in June where the last frost is in
    February (the Mediterranean courtyard example), so it ripens like every woody fruit."""
    scene = canvas.scene()
    pergola = RectangleItem(560.0, 640.0, 300.0, 240.0, object_type=ObjectType.PERGOLA)
    scene.addItem(pergola)
    vine = _drop(canvas, "SHRUB:species=grape vine", QPointF(540.0, 760.0))
    assert "harvest_start" not in vine.metadata["plant_species"]
    states = {}
    for day in (JUNE, OCTOBER):
        records = enrich_climber_records(snapshot_records(scene, day).values())
        record = next(r for r in records if r.item_id == str(vine.item_id))
        assert record.params["climber_support"][0] == "pergola"
        parts = forge_record(record)
        assert any(part.name == FRUIT_PART for part in parts)   # built once, shown by season
        states[day] = evaluate_phenology(record, day, latitude_deg=52.5, frost_dates=FROST)
    assert states[JUNE].ripeness == 0.0 and states[JUNE].accent_opacity == 0.0
    assert states[OCTOBER].ripeness > 0.5 and states[OCTOBER].accent_opacity > 0.5
    assert states[OCTOBER].autumn_color > 0.5            # and its leaves turn
