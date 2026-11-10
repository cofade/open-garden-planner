"""#793 - every label on the canvas reads on every background; the grid lies under the objects.

The numbers are measured, not judged by eye. A label's *contrast* is the WCAG ratio
between its ink and what immediately surrounds the ink, taken from two pictures of
the real ``CanvasView``: one with the label and one without. The pixels the label
changed and that carry its colour are the ink; the pixels next to the ink that do
not are the surround. Without a halo the surround is the background (the survey
measured the scale bar at 1.25:1 on soil); with one it is the halo.

``core.legibility.MIN_TEXT_CONTRAST`` (4.5:1, WCAG AA) is the stated minimum.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QGraphicsItem

from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.legibility import MIN_TEXT_CONTRAST, contrast_ratio
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CalloutItem,
    CircleItem,
    PolygonItem,
    RectangleItem,
    TextItem,
)
from open_garden_planner.ui.theme import ThemeColors

#: What a label may lie on: the bare plan, a lawn, soil, a tiled roof, the grey
#: around the plan, the sun study's shadow, a pond, fresh snow.
BACKGROUNDS = {
    "plan": (245, 245, 220),
    "lawn": (96, 160, 62),
    "soil": (86, 60, 40),
    "roof": (196, 82, 48),
    "outside": (112, 112, 112),
    "shadow": (44, 46, 44),
    "pond": (52, 120, 190),
    "white": (255, 255, 255),
}


@pytest.fixture()
def canvas(qtbot):
    scene = CanvasScene(3000, 2000)
    scene.set_shadows_enabled(False)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    qtbot.waitExposed(view)
    view.set_snap_enabled(False)
    return view, scene


def _solid(scene: CanvasScene, rgb: tuple[int, int, int], rect: QRectF | None = None,
           name: str = "") -> RectangleItem:
    """A flat-coloured object: the background a label is measured on."""
    rect = rect or QRectF(-6000, -6000, 15000, 14000)
    item = RectangleItem(rect.x(), rect.y(), rect.width(), rect.height(),
                         object_type=ObjectType.GENERIC_RECTANGLE, name=name)
    item.fill_pattern = FillPattern.SOLID
    item.fill_color = QColor(*rgb)
    item.setBrush(create_pattern_brush(FillPattern.SOLID, item.fill_color))
    scene.addItem(item)
    return item


def _grab(view: CanvasView) -> QImage:
    QApplication.processEvents()
    return view.viewport().grab().toImage().convertToFormat(QImage.Format.Format_RGB32)


def _distance(a: QColor, b: QColor) -> int:
    return abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())


def _label_contrast(with_label: QImage, without: QImage, ink: QColor, region: QRect) -> float:
    """WCAG contrast between a label's ink and its immediate surround (module docstring)."""
    region = region.intersected(with_label.rect())
    ink_pixels: set[tuple[int, int]] = set()
    for y in range(region.top(), region.bottom() + 1):
        for x in range(region.left(), region.right() + 1):
            now = QColor(with_label.pixel(x, y))
            if _distance(now, QColor(without.pixel(x, y))) > 12 and _distance(now, ink) <= 45:
                ink_pixels.add((x, y))
    if len(ink_pixels) < 12:
        return 1.0       # no label to be seen: as unreadable as it gets
    # What meets the eye beside a stroke: the neighbours of the ink that are not
    # themselves a blend toward it (the anti-aliased edge belongs to the glyph).
    surround: set[tuple[int, int]] = set()
    for x, y in ink_pixels:
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                point = (x + dx, y + dy)
                if point in ink_pixels or not with_label.rect().contains(*point):
                    continue
                if _distance(QColor(with_label.pixel(*point)), ink) > 150:
                    surround.add(point)
    if not surround:
        return 1.0       # the ink stands on its own colour

    def mean(points: set[tuple[int, int]]) -> tuple[int, int, int]:
        colours = [QColor(with_label.pixel(x, y)) for x, y in points]
        return (
            round(sum(c.red() for c in colours) / len(colours)),
            round(sum(c.green() for c in colours) / len(colours)),
            round(sum(c.blue() for c in colours) / len(colours)),
        )

    ratio = contrast_ratio(mean(ink_pixels), mean(surround))
    print(f"[CONTRAST] {ratio:.2f}:1 ink={mean(ink_pixels)} surround={mean(surround)}")
    return ratio


# --------------------------------------------------------------------------
# (a) The scale bar
# --------------------------------------------------------------------------


@pytest.mark.parametrize("background", list(BACKGROUNDS))
@pytest.mark.parametrize("theme", ["LIGHT", "DARK"])
def test_the_scale_bar_label_reads_on_every_background(canvas, background: str, theme: str) -> None:
    view, scene = canvas
    view.apply_theme_colors(getattr(ThemeColors, theme))
    _solid(scene, BACKGROUNDS[background])
    with_bar = _grab(view)
    view.set_scale_bar_visible(False)
    without = _grab(view)

    corner = QRect(with_bar.width() - 260, with_bar.height() - 44, 260, 26)   # the label, not the bar
    ratio = _label_contrast(with_bar, without, QColor(view._scale_bar_fg), corner)
    assert ratio >= MIN_TEXT_CONTRAST, f"scale bar label on {background}: {ratio:.2f}:1"


def test_a_light_scale_bar_colour_gets_a_dark_halo(canvas) -> None:
    """The halo follows the ink: a theme that paints the bar light is still readable on snow."""
    view, scene = canvas
    view.apply_theme_colors(ThemeColors.LIGHT | {"scale_bar_fg": "#f2f2ea"})
    _solid(scene, BACKGROUNDS["white"])
    with_bar = _grab(view)
    view.set_scale_bar_visible(False)
    corner = QRect(with_bar.width() - 260, with_bar.height() - 44, 260, 26)
    assert _label_contrast(with_bar, _grab(view), QColor("#f2f2ea"), corner) >= MIN_TEXT_CONTRAST


def test_the_scale_bar_stays_inside_the_band_reserved_for_it(canvas) -> None:
    """Overlay widgets clear ``SCALE_BAR_RESERVED_PX`` (section 8.9.4): the halo must fit in it."""
    view, scene = canvas
    _solid(scene, BACKGROUNDS["soil"])
    with_bar = _grab(view)
    view.set_scale_bar_visible(False)
    without = _grab(view)
    rows = [
        y for y in range(with_bar.height())
        if any(with_bar.pixel(x, y) != without.pixel(x, y) for x in range(with_bar.width() - 300, with_bar.width()))
    ]
    assert rows, "the scale bar is not painted"
    assert min(rows) >= with_bar.height() - CanvasView.SCALE_BAR_RESERVED_PX


def test_the_minimap_clears_the_scale_bar_when_a_scrollbar_appears(qtbot) -> None:
    """Zooming in shows scrollbars: the viewport shrinks, the view does not resize."""
    from open_garden_planner.ui.widgets.minimap_widget import MARGIN, MinimapWidget

    scene = CanvasScene(2000, 1500)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    view.resize(700, 500)
    view.show()
    qtbot.waitExposed(view)
    view.set_zoom(0.05)                                  # the whole scene fits: no scrollbars
    QApplication.processEvents()
    minimap = MinimapWidget(view, scene)
    QApplication.processEvents()
    before = view.viewport().height()

    view.set_zoom(4.0)                                   # scrollbars appear
    QApplication.processEvents()
    assert view.viewport().height() < before, "this test needs the viewport to shrink"

    viewport = view.viewport().geometry()
    clearance = viewport.bottom() - minimap.geometry().bottom()
    assert clearance >= MARGIN + CanvasView.SCALE_BAR_RESERVED_PX


# --------------------------------------------------------------------------
# (b) Object labels
# --------------------------------------------------------------------------


def _label_region(view: CanvasView, item: QGraphicsItem) -> QRect:
    centre = view.mapFromScene(item.mapToScene(item.rect().center()))
    return QRect(centre.x() - 140, centre.y() - 40, 280, 80)


@pytest.mark.parametrize("background", list(BACKGROUNDS))
def test_an_object_label_reads_on_every_background(canvas, background: str) -> None:
    view, scene = canvas
    bed = _solid(scene, BACKGROUNDS[background], QRectF(900, 700, 1200, 600), name="Raised bed")
    view.centerOn(bed)
    with_label = _grab(view)
    bed.label_visible = False
    without = _grab(view)
    ratio = _label_contrast(with_label, without, QColor(0, 0, 0), _label_region(view, bed))
    assert ratio >= MIN_TEXT_CONTRAST, f"object label on {background}: {ratio:.2f}:1"


@pytest.mark.parametrize("background", ["lawn", "soil", "roof", "shadow"])
def test_an_area_label_reads_on_every_background(canvas, background: str) -> None:
    view, scene = canvas
    bed = _solid(scene, BACKGROUNDS[background], QRectF(900, 700, 1200, 600))
    view.centerOn(bed)
    bed.area_label_visible = True
    with_label = _grab(view)
    ink = bed._area_label_item.brush().color()
    bed.area_label_visible = False
    without = _grab(view)
    ratio = _label_contrast(with_label, without, ink, _label_region(view, bed))
    assert ratio >= MIN_TEXT_CONTRAST, f"area label on {background}: {ratio:.2f}:1"


def test_a_label_is_not_hidden_by_an_object_drawn_later(canvas) -> None:
    """The lawn's label used to lie under every object placed on the lawn."""
    view, scene = canvas
    lawn = _solid(scene, BACKGROUNDS["lawn"], QRectF(600, 500, 1800, 1000), name="Lawn")
    _solid(scene, BACKGROUNDS["soil"], QRectF(1300, 900, 400, 200))      # a bed on its centre
    view.centerOn(lawn)
    with_label = _grab(view)
    lawn.label_visible = False
    without = _grab(view)
    ratio = _label_contrast(with_label, without, QColor(0, 0, 0), _label_region(view, lawn))
    assert ratio >= MIN_TEXT_CONTRAST, "the lawn's label is covered by the bed"


@pytest.mark.parametrize("zoom", [0.12, 0.42, 1.0, 3.5])
@pytest.mark.parametrize("rotation", [0.0, 30.0])
def test_a_label_is_centred_on_its_object_at_every_zoom(canvas, zoom: float, rotation: float) -> None:
    view, scene = canvas
    bed = _solid(scene, BACKGROUNDS["soil"], QRectF(900, 700, 1200, 600), name="Raised bed")
    bed._apply_rotation(rotation)
    bed.area_label_visible = True
    view.set_zoom(zoom)
    view.centerOn(bed)
    QApplication.processEvents()
    transform = view.viewportTransform()
    centre = transform.map(bed.mapToScene(bed.rect().center()))

    label = bed._label_item
    box = label.deviceTransform(transform).mapRect(label.boundingRect())
    assert box.center().x() == pytest.approx(centre.x(), abs=0.6)
    assert box.center().y() == pytest.approx(centre.y(), abs=0.6)
    # the area hangs under the name, centred too, and clear of it
    area = bed._area_label_item
    area_box = area.deviceTransform(transform).mapRect(area.boundingRect())
    assert area_box.center().x() == pytest.approx(centre.x(), abs=0.6)
    assert area_box.top() >= box.bottom() - 6.0          # the two halos may touch, the texts not
    assert area_box.top() < box.bottom() + 8.0


@pytest.mark.parametrize("zoom", [0.42, 1.0, 3.5])
def test_the_area_is_shown_together_with_the_name(canvas, zoom: float) -> None:
    """The area hangs under the name, closer than two strangers' labels may lie.

    The layout took the pair for two labels that touch and left the area out:
    an object with both labels on showed its name only.
    """
    view, scene = canvas
    bed = _solid(scene, BACKGROUNDS["soil"], QRectF(900, 700, 1200, 600), name="Raised bed")
    bed.area_label_visible = True
    view.set_zoom(zoom)
    view.centerOn(bed)
    QApplication.processEvents()
    shown = {item for item, _device, _box in scene.plan_labels_shown(view.viewportTransform())}
    assert shown == {bed._label_item, bed._area_label_item}

    with_area = _grab(view)
    ink = bed._area_label_item.brush().color()
    bed.area_label_visible = False
    without = _grab(view)
    centre = view.mapFromScene(bed.mapToScene(bed.rect().center()))
    region = QRect(centre.x() - 80, centre.y() + 6, 160, 30)        # under the name
    ratio = _label_contrast(with_area, without, ink, region)
    assert ratio >= MIN_TEXT_CONTRAST, f"area under the name at zoom {zoom}: {ratio:.2f}:1"


def _ink_span(width: int, height: int, draw) -> tuple[int, int]:
    """Leftmost and rightmost column that ``draw`` darkens on a white picture."""
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(10.0, 6.0)
    draw(painter)
    painter.end()
    columns = [
        x for x in range(width)
        if any(QColor(image.pixel(x, y)).lightness() < 150 for y in range(height))
    ]
    return columns[0], columns[-1]


@pytest.mark.parametrize("bold", [True, False])
@pytest.mark.parametrize("points", [5, 7, 10, 14, 22])
@pytest.mark.parametrize("text", ["Perennial border", "Stepping stones", "12.00 m\u00b2"])
def test_the_halo_ends_where_the_text_ends(qtbot, text: str, points: int, bold: bool) -> None:
    """The halo is the stroked glyph outline; the glyphs are drawn by the text layout.

    The outline was laid out a second time, by ``QPainterPath.addText``, and
    the two layouts do not agree: a hinted layout rounds every advance to whole
    pixels. On Windows a bold 10 pt "Perennial border" ended 3.9 px past its
    outline, where the halo reaches 2.5 px, and 6.4 px at an export's 7 pt: the
    last letters stood outside their halo. Measured here on pixels, whatever
    builds the outline: the ink of the painted text and the ink of the filled
    outline start and end in the same columns.
    """
    from PyQt6.QtWidgets import QGraphicsSimpleTextItem, QStyleOptionGraphicsItem

    from open_garden_planner.ui.canvas.items.halo_text import HaloTextItem

    item = HaloTextItem(text)
    font = QFont("Arial", points)
    font.setBold(bold)
    item.setFont(font)
    width = int(QGraphicsSimpleTextItem.boundingRect(item).width()) + 40
    height = int(QGraphicsSimpleTextItem.boundingRect(item).height()) + 20

    glyphs = _ink_span(width, height, lambda painter: QGraphicsSimpleTextItem.paint(
        item, painter, QStyleOptionGraphicsItem(), None))
    outline = _ink_span(width, height, lambda painter: painter.fillPath(
        item._text_outline(), QBrush(QColor("black"))))
    assert abs(outline[0] - glyphs[0]) <= 1, (glyphs, outline)
    assert abs(outline[1] - glyphs[1]) <= 1, (glyphs, outline)


def test_a_two_line_label_has_its_halo_under_both_lines(qtbot) -> None:
    from PyQt6.QtWidgets import QGraphicsSimpleTextItem

    from open_garden_planner.ui.canvas.items.halo_text import HaloTextItem

    item = HaloTextItem("Raised bed\n6.24 m\u00b2")
    one_line = HaloTextItem("Raised bed")
    text_rect = QGraphicsSimpleTextItem.boundingRect(item)
    outline = item._text_outline().boundingRect()
    assert outline.height() > one_line._text_outline().boundingRect().height() * 1.6
    assert outline.top() >= text_rect.top() - 1.0
    assert outline.bottom() <= text_rect.bottom() + 1.0


def test_a_renamed_object_shows_its_new_name_at_once(canvas) -> None:
    """The label is painted from a kept picture; a rename must replace it."""
    view, scene = canvas
    bed = _solid(scene, BACKGROUNDS["soil"], QRectF(900, 700, 1200, 600), name="Bed")
    view.centerOn(bed)
    short = _grab(view)
    bed.name = "A much longer name for this bed"
    bed._update_label()
    long = _grab(view)
    region = _label_region(view, bed)

    def ink_columns(image: QImage) -> int:
        return sum(
            1 for x in range(region.left(), region.right() + 1)
            if any(_distance(QColor(image.pixel(x, y)), QColor(0, 0, 0)) < 60
                   for y in range(region.top(), region.bottom() + 1))
        )

    assert ink_columns(long) > 2 * ink_columns(short) > 0


def test_a_label_given_another_font_size_is_measured_again(canvas) -> None:
    """An export resizes every label's font; its rect and its halo must follow."""
    _view, scene = canvas
    bed = _solid(scene, BACKGROUNDS["soil"], QRectF(900, 700, 1200, 600), name="Raised bed")
    label = bed._label_item
    before = label.boundingRect()
    font = QFont(label.font())
    font.setPointSize(30)
    label.setFont(font)
    after = label.boundingRect()
    assert after.width() > 2.0 * before.width() and after.height() > 2.0 * before.height()
    assert after.center().x() == pytest.approx(0.0, abs=0.01)     # still centred on its anchor
    assert after.center().y() == pytest.approx(0.0, abs=0.01)


def _many_named(scene: CanvasScene) -> list[RectangleItem]:
    items = [_solid(scene, BACKGROUNDS["lawn"], QRectF(100, 100, 2800, 1800), name="Lawn"),
             _solid(scene, BACKGROUNDS["roof"], QRectF(200, 1200, 900, 600), name="House")]
    for row in range(6):
        for column in range(10):
            items.append(_solid(scene, BACKGROUNDS["soil"],
                                QRectF(1300 + column * 60, 300 + row * 60, 45, 45),
                                name=f"Chair {row}-{column}"))
    return items


@pytest.mark.parametrize("zoom", [0.08, 0.2, 0.42, 1.0, 4.0])
def test_labels_do_not_pile_up_when_the_plan_is_zoomed_out(canvas, zoom: float) -> None:
    from open_garden_planner.core.label_layout import LABEL_MIN_OWNER_PX

    view, scene = canvas
    items = _many_named(scene)
    view.set_zoom(zoom)
    view.centerOn(1500, 1000)
    QApplication.processEvents()
    transform = view.viewportTransform()
    shown = scene.plan_labels_shown(transform)

    boxes = [box for _label, _device, box in shown]
    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            assert not first.intersects(second), (zoom, first, second)
    names = {label.text() for label, _device, _box in shown}
    assert "Lawn" in names                               # the large object always names itself
    chair_px = 45.0 * zoom
    chairs = {name for name in names if name.startswith("Chair")}
    if chair_px < LABEL_MIN_OWNER_PX:
        assert not chairs, "an object too small to see must not carry a label"
    if zoom >= 4.0:
        visible = {i.name for i in items if view.viewport().rect().intersects(
            view.mapFromScene(i.sceneBoundingRect()).boundingRect())}
        assert {n for n in visible if n.startswith("Chair")} <= names, "with room, every label shows"


def test_the_selected_object_names_itself_even_when_tiny(canvas) -> None:
    view, scene = canvas
    items = _many_named(scene)
    view.set_zoom(0.08)
    view.centerOn(1500, 1000)
    chair = items[20]
    assert chair.name not in {label.text() for label, *_ in scene.plan_labels_shown(view.viewportTransform())}
    chair.setSelected(True)
    assert chair.name in {label.text() for label, *_ in scene.plan_labels_shown(view.viewportTransform())}


def test_what_the_minimap_suppresses_stays_suppressed(canvas) -> None:
    """The minimap blanks screen-space items with ``ItemHasNoContents``, not ``setVisible``."""
    view, scene = canvas
    bed = _solid(scene, BACKGROUNDS["soil"], QRectF(900, 700, 1200, 600), name="Raised bed")
    transform = view.viewportTransform()
    assert [label.text() for label, *_ in scene.plan_labels_shown(transform)] == ["Raised bed"]
    bed._label_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemHasNoContents, True)
    assert scene.plan_labels_shown(transform) == []


def test_an_exported_picture_carries_the_label_above_the_objects_too(qtbot) -> None:
    from open_garden_planner.services.scene_rendering import render_scene_region

    scene = CanvasScene(3000, 2000)
    scene.set_shadows_enabled(False)
    lawn = _solid(scene, BACKGROUNDS["lawn"], QRectF(600, 500, 1800, 1000), name="Lawn")
    _solid(scene, BACKGROUNDS["soil"], QRectF(1300, 900, 400, 200))

    def export() -> QImage:
        image = QImage(900, 600, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        render_scene_region(scene, painter, QRectF(0, 0, 900, 600), scene.canvas_rect)
        painter.end()
        return image

    with_label = export()
    lawn.label_visible = False
    without = export()
    ratio = _label_contrast(with_label, without, QColor(0, 0, 0), QRect(300, 250, 300, 100))
    assert ratio >= MIN_TEXT_CONTRAST


# --------------------------------------------------------------------------
# (d) Dimension labels
# --------------------------------------------------------------------------


def _dimension_colours() -> dict[str, QColor]:
    from open_garden_planner.ui.canvas import dimension_lines

    return {
        name: value for name, value in vars(dimension_lines).items()
        if name.startswith("COLOR_") and isinstance(value, QColor)
    }


@pytest.mark.parametrize("name", sorted(_dimension_colours()))
def test_every_dimension_colour_is_painted_legibly(name: str) -> None:
    from open_garden_planner.ui.canvas.items.halo_text import HaloTextItem

    item = HaloTextItem("6.01 m")
    item.setBrush(QBrush(_dimension_colours()[name]))
    ink, halo = item.brush().color(), item.halo_color()
    ratio = contrast_ratio((ink.red(), ink.green(), ink.blue()), (halo.red(), halo.green(), halo.blue()))
    assert ratio >= MIN_TEXT_CONTRAST, f"{name}: {ratio:.2f}:1"


@pytest.mark.parametrize("background", ["roof", "lawn", "soil", "pond", "plan"])
def test_a_dimension_label_reads_on_every_background(canvas, background: str) -> None:
    """The survey: a blue 6.01 m on the roof at 1.02:1."""
    from PyQt6.QtWidgets import QGraphicsSimpleTextItem

    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType

    view, scene = canvas
    _solid(scene, BACKGROUNDS[background])
    first = CircleItem(1000.0, 1000.0, 40.0, object_type=ObjectType.GENERIC_CIRCLE)
    second = CircleItem(2000.0, 1000.0, 40.0, object_type=ObjectType.GENERIC_CIRCLE)
    scene.addItem(first)
    scene.addItem(second)
    scene.constraint_graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER), AnchorRef(second.item_id, AnchorType.CENTER), 1000.0
    )
    scene.update_dimension_lines()
    view.centerOn(1500, 1000)
    text = next(
        item for item in scene.items()
        if isinstance(item, QGraphicsSimpleTextItem) and item.text() == "10.00 m"
    )
    with_label = _grab(view)
    ink = text.brush().color()
    text.setVisible(False)
    without = _grab(view)
    centre = view.mapFromScene(QPointF(1500, 1000))
    region = QRect(centre.x() - 120, centre.y() - 50, 240, 100)
    ratio = _label_contrast(with_label, without, ink, region)
    assert ratio >= MIN_TEXT_CONTRAST, f"dimension label on {background}: {ratio:.2f}:1"


# --------------------------------------------------------------------------
# (c) Text notes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size_cm", [0.1, 0.42, 1.0, 2.5])
def test_a_text_note_is_laid_out_unhinted_whatever_is_set_on_it(qtbot, size_cm: float) -> None:
    """A note is laid out once and scaled by the view.

    A hinted font rounds every advance to the pixel grid of the one size the
    note is laid out at; the zoom magnifies the rounding into uneven gaps
    ("thy me"). On Windows the worst letter gap was 2.85 px off at 3.3x before
    and 1.15 px after (docs: PF-CAN-52). The offscreen platform the suite runs
    on does not hint, so the pixels cannot show it here; the cause is pinned
    instead, after every setter that builds the font anew.
    """
    unhinted = QFont.HintingPreference.PreferNoHinting
    note = TextItem(0, 0, content="thyme fictional illustrative", font_size=size_cm)
    assert note.font().hintingPreference() == unhinted

    note.bold = True
    assert note.font().hintingPreference() == unhinted
    note.italic = True
    assert note.font().hintingPreference() == unhinted
    note.font_family = "Times New Roman"
    assert note.font().hintingPreference() == unhinted
    note.font_size = size_cm * 2.0
    assert note.font().hintingPreference() == unhinted
    assert note.font().bold() and note.font().italic()


def test_a_callout_is_laid_out_unhinted(qtbot) -> None:
    """A callout's text is scaled by the view like a note's."""
    callout = CalloutItem(QPointF(0, 0), QPointF(120, 80), content="thyme fictional")
    font = callout._text_child.font()
    assert font.hintingPreference() == QFont.HintingPreference.PreferNoHinting


# --------------------------------------------------------------------------
# (e) The grid
# --------------------------------------------------------------------------


def _grid_pixels(view: CanvasView) -> tuple[set[tuple[int, int]], QImage]:
    view.set_grid_visible(True)
    with_grid = _grab(view)
    view.set_grid_visible(False)
    without = _grab(view)
    changed = {
        (x, y)
        for y in range(with_grid.height())
        for x in range(with_grid.width())
        if with_grid.pixel(x, y) != without.pixel(x, y)
    }
    return changed, with_grid


@pytest.fixture()
def garden(qtbot):
    scene = CanvasScene(1000, 800)
    scene.set_shadows_enabled(False)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    qtbot.waitExposed(view)
    lawn = PolygonItem(
        [QPointF(0, 0), QPointF(450, 0), QPointF(450, 800), QPointF(0, 800)],
        object_type=ObjectType.LAWN,
    )
    scene.addItem(lawn)
    tree = CircleItem(700.0, 400.0, 110.0, object_type=ObjectType.TREE)
    scene.addItem(tree)
    shed = RectangleItem(520, 80, 200, 140, object_type=ObjectType.GARAGE_SHED)
    scene.addItem(shed)
    table = RectangleItem(120, 300, 160, 90, object_type=ObjectType.TABLE_RECTANGULAR)
    scene.addItem(table)                               # an object standing ON the lawn
    return view, scene, lawn, tree, shed, table


@pytest.mark.parametrize("zoom", [0.35, 0.6, 1.4])
def test_the_grid_lies_inside_the_plan_and_under_the_objects(garden, zoom: float) -> None:
    view, scene, lawn, tree, shed, table = garden
    view.set_zoom(zoom)
    view.centerOn(500, 400)
    changed, _image = _grid_pixels(view)
    assert changed, "the grid is not drawn at all"

    plan = view.mapFromScene(scene.canvas_rect).boundingRect()
    outside = [p for p in changed if not plan.adjusted(-1, -1, 1, 1).contains(*p)]
    assert not outside, f"{len(outside)} grid pixels on the grey around the plan"

    centre = view.mapFromScene(QPointF(700.0, 400.0))
    radius = 110.0 * zoom - 2.0
    on_tree = [p for p in changed if (p[0] - centre.x()) ** 2 + (p[1] - centre.y()) ** 2 < radius ** 2]
    assert not on_tree, f"{len(on_tree)} grid pixels across the tree"

    for item in (shed, table):
        box = view.mapFromScene(item.sceneBoundingRect()).boundingRect().adjusted(3, 3, -3, -3)
        on_item = [p for p in changed if box.contains(*p)]
        assert not on_item, f"{len(on_item)} grid pixels across {item.object_type.name}"

    # the grid is still where it is needed: on the bare plan AND on the lawn
    lawn_box = view.mapFromScene(QRectF(300, 450, 140, 300)).boundingRect()
    bare_box = view.mapFromScene(QRectF(800, 450, 180, 300)).boundingRect()
    assert sum(1 for p in changed if lawn_box.contains(*p)) > 10, "no grid on the lawn"
    assert sum(1 for p in changed if bare_box.contains(*p)) > 10, "no grid on the bare plan"


def test_the_grid_returns_where_an_object_was_moved_away(garden) -> None:
    view, _scene, _lawn, tree, _shed, _table = garden
    view.set_zoom(0.6)
    view.centerOn(500, 400)
    tree.setPos(0.0, 250.0)                            # now centred on (700, 650)
    changed, _image = _grid_pixels(view)
    old = view.mapFromScene(QRectF(640, 340, 120, 60)).boundingRect()
    assert sum(1 for p in changed if old.contains(*p)) > 5
    centre = view.mapFromScene(QPointF(700.0, 650.0))
    assert not [p for p in changed if (p[0] - centre.x()) ** 2 + (p[1] - centre.y()) ** 2 < 60.0 ** 2]


def test_the_grid_is_in_no_export(garden) -> None:
    """The grid is a view decoration: ``scene.render`` never reaches it."""
    from open_garden_planner.services.scene_rendering import render_scene_region

    view, scene, *_ = garden

    def export() -> QImage:
        image = QImage(500, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        render_scene_region(scene, painter, QRectF(0, 0, 500, 400), scene.canvas_rect)
        painter.end()
        return image

    view.set_grid_visible(False)
    plain = export()
    view.set_grid_visible(True)
    assert export() == plain
