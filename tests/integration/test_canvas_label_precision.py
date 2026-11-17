"""Labels and succession tags share one collision and containment contract."""

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QFontMetricsF, QImage

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem, TextItem
from open_garden_planner.ui.canvas.items.halo_text import PlanLabelItem
from open_garden_planner.ui.canvas.plan_labels import plan_labels_shown, succession_badges_shown


@pytest.fixture()
def canvas(qtbot):
    scene = CanvasScene(3000, 2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    qtbot.waitExposed(view)
    return view, scene


def test_note_font_is_independent_of_paint_device_dpi(qtbot):
    note = TextItem(0, 0, "thyme fictional", font_size=0.42)
    heights = []
    for dpi in (96, 144, 192):
        device = QImage(300, 100, QImage.Format.Format_ARGB32)
        device.setDotsPerMeterX(round(dpi / 0.0254))
        device.setDotsPerMeterY(round(dpi / 0.0254))
        heights.append(QFontMetricsF(note.font(), device).height())
    assert len(set(heights)) == 1


@pytest.mark.parametrize("angle", [0, 37, 90, 215])
def test_succession_tag_stays_inside_rotated_bed(canvas, angle):
    view, scene = canvas
    bed = RectangleItem(800, 600, 500, 350, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    badge = bed._ensure_succession_badge_item()
    badge.set_lines([("Lettuce", True), ("Carrots", False)])
    bed._position_succession_badge()
    bed._apply_rotation(angle)
    view.set_zoom(1)
    shown = succession_badges_shown(scene, view.viewportTransform())
    assert len(shown) == 1
    box = shown[0][2]
    polygon = bed.deviceTransform(view.viewportTransform()).mapToPolygon(bed.rect().toRect())
    # The tag is upright: all four of its device corners must lie on the bed.
    from PyQt6.QtCore import Qt
    for corner in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
        assert polygon.containsPoint(corner.toPoint(), Qt.FillRule.OddEvenFill)


def test_succession_tag_keeps_names_out_of_its_room(canvas):
    view, scene = canvas
    bed = RectangleItem(800, 600, 500, 350, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    badge = bed._ensure_succession_badge_item()
    badge.set_lines([("Lettuce", True)])
    bed._position_succession_badge()
    label = PlanLabelItem("A name over the crop tag")
    label.free_extent_px = 100
    label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations)
    scene.addItem(label)
    view.set_zoom(1)
    tag_box = succession_badges_shown(scene, view.viewportTransform())[0][2]
    label.setPos(view.viewportTransform().inverted()[0].map(tag_box.center()))
    assert label not in [entry[0] for entry in plan_labels_shown(scene, view.viewportTransform())]


def test_tiny_bed_still_has_succession_indicator(canvas):
    view, scene = canvas
    bed = RectangleItem(800, 600, 250, 180, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    badge = bed._ensure_succession_badge_item()
    badge.set_lines([("Lettuce", True), ("Carrots", False)])
    bed._position_succession_badge()
    view.set_zoom(0.1)
    shown = succession_badges_shown(scene, view.viewportTransform())
    assert len(shown) == 1
    assert shown[0][2].width() <= 12


@pytest.mark.parametrize("point", [QPointF(0, 0), QPointF(3000, 2000)])
def test_edge_label_stays_on_the_plan(canvas, point):
    view, scene = canvas
    label = PlanLabelItem("An edge label")
    label.free_extent_px = 100
    label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations)
    label.setPos(point)
    scene.addItem(label)
    view.fit_in_view()
    shown = plan_labels_shown(scene, view.viewportTransform())
    entry = next(entry for entry in shown if entry[0] is label)
    assert view.viewportTransform().mapRect(scene.canvas_rect).contains(entry[2])


def test_dimension_text_takes_room_before_object_names(canvas):
    from open_garden_planner.core.constraints import AnchorRef, AnchorType

    view, scene = canvas
    first = RectangleItem(400, 500, 100, 100)
    second = RectangleItem(800, 500, 100, 100)
    scene.addItem(first)
    scene.addItem(second)
    # The existing manager's public constraint path builds the real dimension.
    scene.constraint_graph.add_constraint(AnchorRef(first.item_id, AnchorType.CENTER),
                                          AnchorRef(second.item_id, AnchorType.CENTER), 400)
    scene.dimension_line_manager.update_all()
    dimensions = [i for i in scene.items() if isinstance(i, PlanLabelItem)]
    assert dimensions
    label = PlanLabelItem("An object name")
    label.free_extent_px = 100
    label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations)
    label.setPos(dimensions[0].scenePos())
    scene.addItem(label)
    shown = plan_labels_shown(scene, view.viewportTransform())
    assert dimensions[0] in [entry[0] for entry in shown]
    assert label not in [entry[0] for entry in shown]


def test_sun_contour_does_not_cross_a_text_note(canvas, monkeypatch):
    import numpy as np
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

    from open_garden_planner.ui.canvas.sun_heatmap import SunContourItem

    _view, scene = canvas
    note = TextItem(100, 200, "An authored note", font_size=0.42,
                    text_color=QColor("white"))
    scene.addItem(note)
    box = note.sceneBoundingRect()
    path = QPainterPath()
    path.moveTo(0, box.center().y())
    path.lineTo(500, box.center().y())
    contour = SunContourItem(path)
    contour.setPen(QPen(QColor("red"), 2))
    contour.setZValue(-449)
    scene.addItem(contour)

    def red_inside_note():
        box = note.sceneBoundingRect()
        image = QImage(500, 300, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        scene.render(painter, QRectF(0, 0, 500, 300), QRectF(0, 0, 500, 300))
        painter.end()
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        pixels = np.frombuffer(ptr, np.uint8).reshape(300, 500, 4)
        red = (pixels[:, :, 2] > 200) & (pixels[:, :, 1] < 50)
        assert red.any(), "the control contour must actually have been drawn"
        rect = box.toAlignedRect().adjusted(2, 2, -2, -2)
        return int(red[rect.top():rect.bottom(), rect.left():rect.right()].sum())

    assert red_inside_note() == 0
    note.setPos(300, 200)
    assert red_inside_note() == 0, "moving the note must move its contour exclusion"
    # A negative control pins that these pixels see the original defect.
    with monkeypatch.context() as patch:
        patch.setattr(scene, "annotation_covers", QPainterPath)
        assert red_inside_note() > 0


def test_minimap_omits_warning_arcs_without_scheduling_an_idle_loop(canvas, qtbot, monkeypatch):
    from open_garden_planner.ui.canvas.items import CircleItem
    from open_garden_planner.ui.widgets.minimap_widget import MinimapWidget

    view, scene = canvas
    tree = CircleItem(800, 800, 50, object_type=ObjectType.TREE)
    tree.metadata["plant_species"] = {"max_spread_cm": 500}
    scene.addItem(tree)
    scene.set_spacing_circles_visible(True)
    tree.set_spacing_overlap("overlap")
    minimap = MinimapWidget(view, scene)
    rings = []
    monkeypatch.setattr(tree, "_paint_spacing_ring", lambda *_args: rings.append(1))
    minimap._do_update()
    assert not rings
    assert scene.diagnostic_overlays_visible
    paints = []
    original = minimap._do_update

    def count():
        paints.append(1)
        original()

    monkeypatch.setattr(minimap, "_do_update", count)
    qtbot.wait(350)
    assert len(paints) <= 1, "thumbnail painting must not feed scene.changed forever"


def test_inline_text_edit_invalidates_retained_annotation_room(canvas):
    from PyQt6.QtGui import QTextCursor

    _view, scene = canvas
    note = TextItem(100, 800, "A short note", font_size=0.42)
    scene.addItem(note)
    before = scene.annotation_covers().boundingRect()
    revision = scene.paint_revision
    note.start_editing()
    cursor = note.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" longer text" * 30)
    note.setTextCursor(cursor)
    assert scene.paint_revision > revision
    assert scene.annotation_covers().boundingRect().width() > before.width() * 3
    note.finish_editing()
    assert note.content.endswith(" longer text")


@pytest.mark.parametrize("lines", [[("x" * 80, True)], [("Lettuce", True), ("Carrot", False)]])
def test_compact_indicator_is_square_independently_of_crop_text(canvas, lines):
    view, scene = canvas
    bed = RectangleItem(800, 600, 250, 180, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    bed.set_succession_indicator(lines)
    view.set_zoom(0.1)
    shown = succession_badges_shown(scene, view.viewportTransform())
    assert len(shown) == 1
    box = shown[0][2]
    assert box.height() >= 3
    assert box.width() == pytest.approx(box.height(), abs=1e-6)


def test_selected_ring_paints_prepare_decoration_exclusions_once(canvas, monkeypatch):
    from PyQt6.QtGui import QPainter

    from open_garden_planner.ui.canvas.items import CircleItem, group_item

    view, scene = canvas
    trees = []
    for index in range(30):
        tree = CircleItem(200 + index % 10 * 220, 300 + index // 10 * 300,
                          50, object_type=ObjectType.TREE)
        tree.metadata["plant_species"] = {"max_spread_cm": 500}
        scene.addItem(tree)
        tree.setSelected(True)
        trees.append(tree)
    calls = []
    original = group_item.selection_tree

    def counted(items):
        calls.append(1)
        return original(items)

    monkeypatch.setattr(group_item, "selection_tree", counted)
    image = QImage(1000, 800, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    for _repeat in range(2):
        for tree in trees:
            painter.setWorldTransform(tree.sceneTransform() * view.viewportTransform())
            tree._paint_spacing_ring(painter, 250)
    painter.end()
    assert len(calls) == 1
