"""Integration tests: fill-pattern angle/scale/offset (issue #665).

Covers the whole user path: the Properties panel's four spins and Reset, the
undo stack, save/reload, Copy appearance, a material change, and the roof-tile
composition — the places the issue names one by one.
"""

from __future__ import annotations

import json

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QGraphicsScene,
    QPushButton,
)

from open_garden_planner.core import ProjectManager
from open_garden_planner.core.commands import CommandManager
from open_garden_planner.core.fill_patterns import (
    FillPattern,
    FillTransform,
    create_pattern_brush,
)
from open_garden_planner.core.item_look import copy_visual_style, style_gaps
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel


@pytest.fixture
def manager(qtbot) -> ProjectManager:
    return ProjectManager()


@pytest.fixture
def scene(qtbot) -> QGraphicsScene:
    return QGraphicsScene()


def _rect(scene) -> RectangleItem:
    item = RectangleItem(
        40,
        30,
        300,
        180,
        object_type=ObjectType.GARDEN_BED,
        fill_pattern=FillPattern.WOOD,
    )
    scene.addItem(item)
    return item


def _panel(manager: CommandManager) -> PropertiesPanel:
    return PropertiesPanel(command_manager=manager)


def _spins(panel: PropertiesPanel) -> dict[str, QDoubleSpinBox]:
    angle = next(s for s in panel.findChildren(QDoubleSpinBox) if s.suffix() == "°")
    scale = next(
        s
        for s in panel.findChildren(QDoubleSpinBox)
        if s is not angle and s.minimum() == 0.1 and s.maximum() == 20.0
    )
    offsets = [
        s
        for s in panel.findChildren(QDoubleSpinBox)
        if s is not angle and s is not scale and s.minimum() == -10000.0
    ]
    assert len(offsets) == 2
    return {"angle": angle, "scale": scale, "x": offsets[0], "y": offsets[1]}


def test_panel_edits_the_three_values_and_one_undo_step_each(qtbot) -> None:
    scene = QGraphicsScene()
    item = _rect(scene)
    manager = CommandManager()
    panel = _panel(manager)
    panel.set_selected_items([item])
    spins = _spins(panel)

    spins["angle"].setValue(45.0)
    assert item.fill_transform.angle_deg == 45.0
    assert item.brush().transform() == item.fill_transform.brush_transform()
    assert len(manager._undo_stack) == 1

    spins["scale"].setValue(2.5)
    assert item.fill_transform.scale == 2.5
    assert len(manager._undo_stack) == 2

    spins["x"].setValue(12.0)
    spins["y"].setValue(-8.0)
    assert item.fill_transform.offset_x_cm == 12.0
    assert item.fill_transform.offset_y_cm == -8.0
    assert style_gaps(item) == []

    manager.undo()  # y
    assert item.fill_transform.offset_y_cm == 0.0
    manager.undo()  # x
    manager.undo()  # scale
    assert item.fill_transform.scale == 1.0
    manager.undo()  # angle
    assert item.fill_transform.is_identity
    assert item.brush().transform().isIdentity()


def test_a_sprite_gets_no_pattern_transform_rows(qtbot) -> None:
    """A sprite paints its own art and ignores the brush, so the four rows are
    inert there — do not offer them (round-8 review P2)."""
    scene = QGraphicsScene()
    tree = CircleItem(0, 0, 30, object_type=ObjectType.TREE)
    scene.addItem(tree)
    assert tree.paints_sprite
    panel = _panel(CommandManager())
    panel.set_selected_items([tree])

    assert not [
        spin for spin in panel.findChildren(QDoubleSpinBox) if spin.suffix() == "°"
    ], "a sprite must not offer an inert Pattern Angle"


def test_a_textured_path_shows_and_edits_the_transform(qtbot) -> None:
    """Gravel/dirt paths paint a pattern stroke, so they need the controls too.

    They have no fill-colour/pattern row (``PolylineItem``), which used to hide
    the whole pattern block — the model and painter supported it, the user
    could not reach it (round-6 review P2).
    """
    from open_garden_planner.core.object_types import PathFenceStyle

    scene = QGraphicsScene()
    path = PolylineItem(
        [QPointF(0, 0), QPointF(400, 0)], object_type=ObjectType.PATH
    )
    path.path_fence_style = PathFenceStyle.GRAVEL_PATH
    scene.addItem(path)
    manager = CommandManager()
    panel = _panel(manager)
    panel.set_selected_items([path])

    spins = _spins(panel)
    spins["angle"].setValue(90.0)

    assert path.fill_transform.angle_deg == 90.0
    assert len(manager._undo_stack) == 1
    manager.undo()
    assert path.fill_transform.is_identity


def test_unchanged_value_creates_no_command(qtbot) -> None:
    scene = QGraphicsScene()
    item = _rect(scene)
    manager = CommandManager()
    panel = _panel(manager)
    panel.set_selected_items([item])
    spins = _spins(panel)

    spins["angle"].setValue(0.0)  # already the default
    assert manager._undo_stack == []


def test_reset_restores_all_three_in_one_step(qtbot) -> None:
    scene = QGraphicsScene()
    item = _rect(scene)
    manager = CommandManager()
    panel = _panel(manager)
    panel.set_selected_items([item])
    spins = _spins(panel)

    spins["angle"].setValue(30.0)
    spins["scale"].setValue(1.5)
    spins["x"].setValue(20.0)
    spins["y"].setValue(-10.0)
    depth_before = len(manager._undo_stack)

    reset = next(b for b in panel.findChildren(QPushButton) if b.text() == "Reset Pattern")
    reset.click()

    assert item.fill_transform.is_identity
    assert len(manager._undo_stack) == depth_before + 1
    manager.undo()
    assert item.fill_transform == FillTransform(30.0, 1.5, 20.0, -10.0)


def test_geometry_area_and_selection_are_untouched(qtbot) -> None:
    scene = QGraphicsScene()
    item = _rect(scene)
    before_rect = QRectF(item.rect())
    before_centre = item.mapToScene(item.rect().center())
    before_bounds = item.sceneBoundingRect()
    before_area = before_rect.width() * before_rect.height()

    item.fill_transform = FillTransform(angle_deg=37, scale=3.0, offset_x_cm=12)
    item.setBrush(
        create_pattern_brush(item.fill_pattern, QColor("#88aa66"), item.fill_transform)
    )

    assert item.rect() == before_rect
    assert item.rect().width() * item.rect().height() == before_area
    assert item.mapToScene(item.rect().center()) == before_centre
    assert item.sceneBoundingRect() == before_bounds
    assert item.isSelected() is False  # a display property never selects anything


@pytest.mark.parametrize(
    "factory",
    [
        pytest.param(lambda: RectangleItem(0, 0, 300, 120), id="RectangleItem"),
        pytest.param(
            lambda: PolygonItem(
                [QPointF(0, 0), QPointF(300, 0), QPointF(300, 120), QPointF(0, 120)]
            ),
            id="PolygonItem",
        ),
        pytest.param(lambda: CircleItem(0, 0, 80), id="CircleItem"),
        pytest.param(lambda: EllipseItem(0, 0, 300, 120), id="EllipseItem"),
    ],
)
def test_every_filled_shape_type_renders_the_transform(factory, qtbot) -> None:
    """Rectangle, polygon, circle and ellipse all consume the brush transform."""

    def render(transform: FillTransform) -> QImage:
        scene = QGraphicsScene()
        item = factory()
        item.object_type = ObjectType.GARDEN_BED
        item.fill_pattern = FillPattern.WOOD
        item.fill_transform = transform
        item.setBrush(
            create_pattern_brush(FillPattern.WOOD, QColor("#88aa66"), transform)
        )
        scene.addItem(item)
        bounds = item.sceneBoundingRect()
        image = QImage(
            int(bounds.width()), int(bounds.height()), QImage.Format.Format_ARGB32
        )
        image.fill(QColor("white"))
        painter = QPainter(image)
        scene.render(painter, QRectF(0, 0, image.width(), image.height()), bounds)
        painter.end()
        return image

    identity = render(FillTransform())
    turned = render(FillTransform(angle_deg=45, scale=1.7, offset_x_cm=9))
    assert identity != turned, "the pattern transform did not reach the fill"


def test_a_textured_path_renders_the_transform(qtbot) -> None:
    """The path painter must consume the item's transform, not just the panel.

    Deleting the ``fill_transform=`` kwarg from ``PolylineItem.paint`` left the
    whole suite green before this probe (round-7 review P2).
    """
    from open_garden_planner.core.object_types import PathFenceStyle

    def render(transform: FillTransform) -> QImage:
        scene = QGraphicsScene()
        item = PolylineItem(
            [QPointF(0, 0), QPointF(600, 0)], object_type=ObjectType.PATH
        )
        item.path_fence_style = PathFenceStyle.GRAVEL_PATH
        item.setPen(QPen(QColor("#8a7a55"), 40))
        item.fill_transform = transform
        scene.addItem(item)
        bounds = item.sceneBoundingRect().adjusted(-4, -4, 4, 4)
        image = QImage(
            int(bounds.width()), int(bounds.height()), QImage.Format.Format_ARGB32
        )
        image.fill(QColor("white"))
        painter = QPainter(image)
        scene.render(painter, QRectF(0, 0, image.width(), image.height()), bounds)
        painter.end()
        return image

    identity = render(FillTransform())
    turned = render(FillTransform(angle_deg=45, scale=1.7, offset_x_cm=9))
    assert identity != turned, "the pattern transform did not reach the path stroke"


def test_material_change_keeps_the_transform(qtbot) -> None:
    scene = QGraphicsScene()
    item = _rect(scene)
    manager = CommandManager()
    panel = _panel(manager)
    panel.set_selected_items([item])
    item.fill_transform = FillTransform(angle_deg=15, scale=1.75, offset_x_cm=6)

    panel._on_property_changed(item, "fill_pattern", FillPattern.STONE)

    assert item.fill_pattern is FillPattern.STONE
    assert item.fill_transform == FillTransform(15, 1.75, 6, 0)
    assert style_gaps(item) == []


def test_copy_appearance_carries_the_transform(qtbot) -> None:
    scene = QGraphicsScene()
    source = _rect(scene)
    target = _rect(scene)
    source.fill_transform = FillTransform(angle_deg=-22, scale=0.5, offset_y_cm=9)
    source.setBrush(
        create_pattern_brush(source.fill_pattern, QColor("#88aa66"), source.fill_transform)
    )

    copy_visual_style(source, target)

    assert target.fill_transform == source.fill_transform
    assert target.brush().transform() == source.brush().transform()


def test_save_and_reload_preserve_the_values(manager, scene, tmp_path) -> None:
    item = _rect(scene)
    item.fill_transform = FillTransform(angle_deg=30.5, scale=1.5, offset_x_cm=-12.5,
                                        offset_y_cm=7.0)
    item.setBrush(
        create_pattern_brush(item.fill_pattern, QColor("#88aa66"), item.fill_transform)
    )
    path = tmp_path / "transform.ogp"
    manager.save(scene, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == "1.4"
    stored = json.dumps(raw)
    assert '"fill_transform"' in stored

    expected = item.fill_transform
    expected_matrix = item.brush().transform()
    scene.clear()
    manager.load(scene, path)
    loaded = next(i for i in scene.items() if isinstance(i, RectangleItem))
    assert loaded.fill_transform == expected
    assert loaded.brush().transform() == expected_matrix

    # A second save/reload is stable: same block, same values.
    path2 = tmp_path / "transform-again.ogp"
    manager.save(scene, path2)
    raw2 = json.loads(path2.read_text(encoding="utf-8"))
    scene.clear()
    manager.load(scene, path2)
    again = next(i for i in scene.items() if isinstance(i, RectangleItem))
    assert again.fill_transform == expected
    stored_transform = next(
        obj["fill_transform"] for obj in raw["objects"] if "fill_transform" in obj
    )
    again_transform = next(
        obj["fill_transform"] for obj in raw2["objects"] if "fill_transform" in obj
    )
    assert again_transform == stored_transform


def test_the_legacy_hedge_migration_keeps_the_saved_look(manager, scene, tmp_path) -> None:
    """A HEDGE_SECTION rectangle becomes a polygon; its appearance must survive."""
    hedge = RectangleItem(
        0,
        0,
        200,
        40,
        object_type=ObjectType.HEDGE_SECTION,
        fill_pattern=FillPattern.HEDGE,
    )
    hedge.fill_transform = FillTransform(angle_deg=12, scale=1.25, offset_y_cm=3)
    hedge.stroke_color = QColor("#ffabcdef")
    hedge.stroke_width = 4.0
    hedge.setPen(QPen(QColor("#ffabcdef"), 4.0))
    scene.addItem(hedge)
    path = tmp_path / "hedge.ogp"
    manager.save(scene, path)

    scene.clear()
    manager.load(scene, path)
    loaded = next(i for i in scene.items() if isinstance(i, PolygonItem))
    assert loaded.object_type is ObjectType.HEDGE_POLYGON
    assert loaded.fill_transform == FillTransform(12, 1.25, 0, 3)
    assert loaded.pen().color() == QColor("#ffabcdef")
    assert loaded.pen().widthF() == 4.0
    assert style_gaps(loaded) == []


def test_untouched_plan_writes_no_transform_key(manager, scene, tmp_path) -> None:
    _rect(scene)
    path = tmp_path / "plain.ogp"
    manager.save(scene, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "fill_transform" not in json.dumps(raw)

    scene.clear()
    manager.load(scene, path)
    loaded = next(i for i in scene.items() if isinstance(i, RectangleItem))
    assert loaded.fill_transform.is_identity


def test_a_polyline_transform_round_trips(manager, scene, tmp_path) -> None:
    """A textured path/fence can carry the transform through a save too (#665)."""
    item = PolylineItem(
        [QPointF(0, 0), QPointF(300, 0)],
        object_type=ObjectType.PATH,
    )
    item.fill_pattern = FillPattern.GRAVEL
    item.fill_transform = FillTransform(angle_deg=18, scale=0.75, offset_x_cm=4)
    scene.addItem(item)
    path = tmp_path / "path.ogp"
    manager.save(scene, path)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert any("fill_transform" in obj for obj in raw["objects"])

    scene.clear()
    manager.load(scene, path)
    loaded = next(i for i in scene.items() if isinstance(i, PolylineItem))
    assert loaded.fill_transform == FillTransform(18, 0.75, 4, 0)


def test_old_file_without_the_key_loads_identity(manager, scene, tmp_path) -> None:
    item = _rect(scene)
    item.fill_transform = FillTransform(angle_deg=10)
    path = tmp_path / "with.ogp"
    manager.save(scene, path)
    raw = json.loads(path.read_text(encoding="utf-8"))

    # Strip the additive block, as an older app would have written the file.
    for obj in raw["objects"]:
        obj.pop("fill_transform", None)
    legacy = tmp_path / "legacy.ogp"
    legacy.write_text(json.dumps(raw), encoding="utf-8")

    scene.clear()
    manager.load(scene, legacy)
    loaded = next(i for i in scene.items() if isinstance(i, RectangleItem))
    assert loaded.fill_transform.is_identity


# ---------------------------------------------------------------------------
# Roof-tile composition (the ridge frame stays canonical at angle 0)
# ---------------------------------------------------------------------------


def _probe_pixmap() -> QPixmap:
    """RED top half / BLUE bottom half: texture +Y is BLUE."""
    pm = QPixmap(64, 64)
    p = QPainter(pm)
    p.fillRect(0, 0, 64, 32, QColor(255, 0, 0))
    p.fillRect(0, 32, 64, 32, QColor(0, 0, 255))
    p.end()
    return pm


def _house_with_probe(transform: FillTransform) -> tuple[QGraphicsScene, PolygonItem]:
    scene = QGraphicsScene()
    house = PolygonItem(
        [QPointF(0, 0), QPointF(400, 0), QPointF(400, 250), QPointF(0, 250)],
        object_type=ObjectType.HOUSE,
        fill_pattern=FillPattern.ROOF_TILES,
    )
    house.fill_transform = transform
    house.setBrush(QBrush(_probe_pixmap()))
    p1, p2 = compute_roof_ridge_endpoints(house.polygon(), house.pos())
    ridge = PolylineItem([p1, p2], object_type=ObjectType.ROOF_RIDGE)
    house.set_metadata("ridge_item_id", str(ridge.item_id))
    ridge.set_metadata("owner_polygon_id", str(house.item_id))
    scene.addItem(house)
    scene.addItem(ridge)
    return scene, house


def _render(scene, house: PolygonItem) -> QImage:
    ridge = house._find_ridge()
    assert ridge is not None
    ridge.setVisible(False)  # keep the production paint path, hide the decoration
    bounds = house.sceneBoundingRect()
    image = QImage(400, int(round(400 * bounds.height() / bounds.width())),
                   QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    scene.render(painter, QRectF(0, 0, image.width(), image.height()), bounds)
    painter.end()
    return image


def _colours_at(image: QImage, points) -> list[tuple[int, int, int]]:
    return [
        (image.pixelColor(int(x), int(y)).red(), image.pixelColor(int(x), int(y)).blue())
        for x, y in points
    ]


def test_a_rotated_pattern_reaches_the_roof_tiles(qtbot) -> None:
    """Angle 0 tiles along the ridge; 90 crosses the ridge, so the two sample
    points on the same roof half differ instead of matching."""
    points = ((140, 165), (240, 165))  # parallel to a landscape ridge at y=125

    scene_0, house_0 = _house_with_probe(FillTransform())
    flat = _colours_at(_render(scene_0, house_0), points)
    assert flat[0] == flat[1], "angle 0 must keep the canonical along-ridge tiling"

    scene_90, house_90 = _house_with_probe(FillTransform(angle_deg=90))
    turned = _colours_at(_render(scene_90, house_90), points)
    assert turned[0] != turned[1], "a 90-degree pattern turn must cross the ridge"

    # Both roof planes take the user transform, mirrored across the ridge. At
    # 90 degrees the bands run horizontally, so each half is uniform along y —
    # which can only be true if that half's brush was turned too — and the two
    # halves show opposite halves of the probe texture.
    image = _render(scene_90, house_90)
    upper = _colours_at(image, ((200, 85), (200, 105)))
    lower = _colours_at(image, ((200, 145), (200, 165)))
    assert upper[0] == upper[1], "the near roof plane did not receive the user angle"
    assert lower[0] == lower[1], "the mirrored roof plane did not receive the user angle"
    assert upper[0] != lower[0], "the two roof planes are not mirrored copies"



