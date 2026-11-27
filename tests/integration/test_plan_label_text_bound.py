"""A label of the plan lays out and paints a bounded text (review round 1, the hang).

A plan file is untrusted input (§8.11). An object's name went into its label
as it was: a name of a million characters was laid out and its glyph outlines
stroked at the first paint of the canvas. Measured with a real font: one paint
47 s with a million characters, an access violation in Qt's stroker with a
million and a half. The offscreen platform's box font hides it (56 ms), which
is why the 3D workspace's hostile-name test passed alone and hung in a run
where another test had registered the suite's real font (``ui_font_family``).

The label shows what every row and card shows of a name:
``core.plain_text.clip_line`` — one line, ``NAME_MAX_CHARS`` characters, an
ellipsis. The name itself is untouched.

These tests bound SIZES before they paint anything, so they fail on unbounded
text without hanging; the time bounds after that are generous.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plain_text import ELLIPSIS, NAME_MAX_CHARS, clip_line
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.items.halo_text import PlanLabelItem

#: About a million characters of markup and a second line: the 3D workspace's
#: hostile name, a little shorter.
HUGE = "<table><tr><td>" * 70_000 + "\nsecond line"

#: No label of the plan is wider than this on screen (80 characters of a bold
#: 10 pt face are about 700 px; the offscreen box font makes them 1100).
MAX_LABEL_WIDTH_PX = 2000.0
#: The paint itself is not timed here (a wall-clock bound belongs to the perf tier):
#: a bounded text is what makes it cheap. Measured 2-6 ms a paint; 47 s before.


def _bed(scene: CanvasScene, name: str = "") -> RectangleItem:
    bed = RectangleItem(400, 300, 300, 200, object_type=ObjectType.RAISED_BED, name=name)
    scene.addItem(bed)
    bed.initialize_label()
    return bed


def _shown(scene: CanvasScene, qtbot) -> CanvasView:
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(1000, 700)
    view.show()
    qtbot.waitExposed(view)
    view.centerOn(550, 400)
    return view


def _bounded(label) -> None:
    assert isinstance(label, PlanLabelItem)
    assert len(label.text()) <= NAME_MAX_CHARS + len(ELLIPSIS)
    assert "\n" not in label.text()
    assert label.boundingRect().width() < MAX_LABEL_WIDTH_PX


def test_a_name_of_a_million_characters_is_a_bounded_label_and_one_paint(qtbot, ui_font_family) -> None:
    """With the suite's real font: the state the hang needed."""
    scene = CanvasScene(5000, 3000)
    bed = _bed(scene, HUGE)
    assert len(HUGE) > 1_000_000
    _bounded(bed._label_item)                       # before anything is painted
    assert bed._label_item.text() == clip_line(HUGE)
    assert bed.name == HUGE                         # the plan keeps its name

    view = _shown(scene, qtbot)
    QApplication.processEvents()
    view.viewport().repaint()
    shown = [label.text() for label, _d, _b in scene.plan_labels_shown(view.viewportTransform())]
    assert shown == [clip_line(HUGE)]               # ... and the label is painted, not left out


def test_a_rename_to_a_huge_name_is_bounded_too(qtbot, ui_font_family) -> None:
    scene = CanvasScene(5000, 3000)
    bed = _bed(scene, "Herbs")
    assert bed._label_item.text() == "Herbs"
    bed.name = HUGE
    _bounded(bed._label_item)
    view = _shown(scene, qtbot)
    QApplication.processEvents()
    view.viewport().repaint()


@pytest.mark.parametrize(
    "name",
    [
        "Herbs",
        "Raised bed by the south fence",
        "Tomatoes\nand basil",                       # pasted into the name editor
        "  two   blanks\tand a tab ",
        "x" * 81,
        "A name of ninety characters " + "." * 62,
        "bell\x07 and an override \N{RIGHT-TO-LEFT OVERRIDE}",
    ],
)
def test_the_label_is_the_name_as_rows_and_cards_show_it(qtbot, name: str) -> None:
    """One rule for a name wherever it is shown on one line: the 3D info card,
    the problems list, and the label on the plan."""
    scene = CanvasScene(5000, 3000)
    bed = _bed(scene, name)
    label = bed._label_item
    assert label.text() == clip_line(name)
    assert "\n" not in label.text() and len(label.text()) <= NAME_MAX_CHARS + 1
    bed.name = name + " (2)"
    assert label.text() == clip_line(name + " (2)")


def test_a_short_name_is_the_label_unchanged(qtbot) -> None:
    scene = CanvasScene(5000, 3000)
    for name in ("Herbs", "Lavender 'Hidcote'", "Beet 2 / Möhren", "x" * NAME_MAX_CHARS):
        assert _bed(scene, name)._label_item.text() == name


def test_a_huge_crop_name_is_a_bounded_succession_badge(qtbot, ui_font_family) -> None:
    """The badge is painted in the same pass and draws its rows by hand, at
    every paint: a crop's name comes from the plan's species data."""
    scene = CanvasScene(5000, 3000)
    bed = _bed(scene)
    bed.set_succession_indicator([(HUGE, True), ("Radish", False)])
    badge = bed._succession_badge_item
    assert badge is not None
    assert badge.boundingRect().width() < MAX_LABEL_WIDTH_PX
    rows = [text for text, _current, _more in badge._rendered_rows()]
    assert all(len(text) <= NAME_MAX_CHARS + 3 and "\n" not in text for text in rows), rows
    assert rows[1].endswith("Radish")

    view = _shown(scene, qtbot)
    view.set_zoom(4.0)                              # the badge has room on its bed
    view.centerOn(550, 400)
    QApplication.processEvents()
    view.viewport().repaint()


def test_the_long_label_is_laid_out_once_not_at_every_paint(qtbot, ui_font_family) -> None:
    scene = CanvasScene(5000, 3000)
    _bed(scene, HUGE)
    view = _shown(scene, qtbot)
    for _ in range(5):
        QApplication.processEvents()
    view.viewport().repaint()
    layouts = scene.label_layouts
    for _ in range(20):
        view.viewport().repaint()
    assert scene.label_layouts == layouts


def test_a_picture_of_the_plan_paints_the_bounded_label(qtbot, ui_font_family) -> None:
    """An export draws its labels as vectors, at every render: the same text."""
    scene = CanvasScene(1200, 800)
    _bed(scene, HUGE)
    image = QImage(900, 600, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    try:
        render_scene_region(scene, painter, QRectF(0, 0, 900, 600), scene.canvas_rect, y_flip=True)
    finally:
        painter.end()


def test_inline_label_editor_bounds_huge_name_and_preserves_untouched_name(qtbot, ui_font_family) -> None:
    """Double-clicking / starting inline label edit on an object with a huge name
    loads the bounded single-line display copy and preserves the full stored
    ``item.name`` if committed unchanged; editing it commits the new name (#873)."""
    scene = CanvasScene(5000, 3000)
    bed = _bed(scene, HUGE)
    view = _shown(scene, qtbot)
    QApplication.processEvents()

    bed.start_label_edit()
    editor = bed._edit_label_item
    assert editor is not None
    assert editor.toPlainText() == clip_line(HUGE)
    assert len(editor.toPlainText()) <= NAME_MAX_CHARS + len(ELLIPSIS)
    assert editor.boundingRect().width() < MAX_LABEL_WIDTH_PX

    # Committing without editing must NOT overwrite the full underlying name
    bed._finish_label_edit()
    assert bed.name == HUGE

    # Actually editing the text in the inline editor commits the new name
    bed.start_label_edit()
    editor = bed._edit_label_item
    assert editor is not None
    editor.setPlainText("Renamed Herb Bed")
    bed._finish_label_edit()
    assert bed.name == "Renamed Herb Bed"
    assert bed._label_item.text() == "Renamed Herb Bed"
    view.viewport().repaint()


def test_main_window_sidebars_bound_long_names_and_notes(qtbot, monkeypatch) -> None:
    from PyQt6.QtWidgets import QLineEdit

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.ui.canvas.items.text_item import TextItem, bound_display_text
    from open_garden_planner.ui.panels.properties_panel import FocusOutTextEdit

    monkeypatch.setattr(GardenPlannerApp, "_startup_sequence", lambda _: None)
    monkeypatch.setattr(GardenPlannerApp, "_start_update_check", lambda _: None)
    window = GardenPlannerApp()
    monkeypatch.setattr(window, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(window)
    window.show()
    scene = window.canvas_scene
    bed = _bed(scene, HUGE)
    bed.setSelected(True)
    status = window.crop_rotation_panel._status_label
    assert len(status.text()) < 200
    assert status.heightForWidth(300) < 200
    name_field, = [
        field for field in window.properties_panel.findChildren(QLineEdit)
        if getattr(field, "_ogp_name_start", None) == HUGE
    ]
    assert name_field.text() == bound_display_text(HUGE)
    assert name_field.isReadOnly()
    qtbot.keyClicks(name_field, "ordinary edit")
    name_field.editingFinished.emit()
    assert bed.name == HUGE
    name_field._ogp_replace_button.click()
    assert not name_field.isReadOnly() and not name_field.text()
    name_field.setText("Renamed")
    name_field.editingFinished.emit()
    assert bed.name == "Renamed"
    window.canvas_view.command_manager.undo()
    assert bed.name == HUGE

    scene.clearSelection()
    note = TextItem(200, 200, HUGE)
    scene.addItem(note)
    note.setSelected(True)
    content, = window.properties_panel.findChildren(FocusOutTextEdit)
    assert len(content.toPlainText()) < 3_000
    assert content.isReadOnly()
    qtbot.keyClicks(content, "ordinary edit")
    content.editing_finished.emit()
    assert note.content == HUGE
    content._ogp_replace_button.click()
    assert not content.isReadOnly() and not content.toPlainText()
    content.setPlainText("A short note")
    content.editing_finished.emit()
    assert note.content == "A short note"
    window.canvas_view.command_manager.undo()
    assert note.content == HUGE


def test_huge_text_item_bounds_display_and_selection_paint(qtbot, ui_font_family) -> None:
    """A 1M-char TextItem keeps full ``content`` for serialization while bounding
    its Qt document and using a cosmetic selection border (#873)."""
    from open_garden_planner.ui.canvas.items.text_item import MAX_DISPLAY_TEXT_CHARS, TextItem

    huge_note = "a" * 1_000_000
    scene = CanvasScene(5000, 3000)
    item = TextItem(200, 200, huge_note)
    scene.addItem(item)

    assert item.content == huge_note
    assert len(item.toPlainText()) == MAX_DISPLAY_TEXT_CHARS + len(ELLIPSIS)
    assert item.boundingRect().width() < 100_000.0

    view = _shown(scene, qtbot)
    view.centerOn(item)
    item.setSelected(True)
    QApplication.processEvents()
    view.viewport().repaint()
    view.viewport().repaint()

    # Verify the custom cosmetic dashed selection border is actually painted when
    # selected (without leaking State_Selected to QGraphicsTextItem.paint).
    from PyQt6.QtWidgets import QStyle, QStyleOptionGraphicsItem

    def _paint_border_blue_pixels(selected: bool) -> int:
        img = QImage(320, 80, QImage.Format.Format_ARGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        try:
            p.translate(10, 10)
            opt = QStyleOptionGraphicsItem()
            if selected:
                opt.state |= QStyle.StateFlag.State_Selected
            item.paint(p, opt)
            assert not (opt.state & QStyle.StateFlag.State_Selected)
        finally:
            p.end()
        return sum(
            1
            for y in range(img.height())
            for x in range(img.width())
            if (c := img.pixelColor(x, y)).blue() > 180 and c.red() < 80
        )

    assert _paint_border_blue_pixels(False) == 0
    assert _paint_border_blue_pixels(True) > 0

    # Untouched edit commit keeps full 1M-char content; real edit replaces it
    item.start_editing()
    item.finish_editing()
    assert item.content == huge_note

    item.start_editing()
    item.setPlainText("Short Note")
    item.finish_editing()
    assert item.content == "Short Note"
    assert item.toPlainText() == "Short Note"


def test_huge_callout_item_bounds_display_and_selection_paint(qtbot, ui_font_family) -> None:
    """A 1M-char CalloutItem keeps full ``content`` while bounding its child
    ``QTextDocument`` so selection repaints stay bounded (#873)."""
    from PyQt6.QtCore import QPointF

    from open_garden_planner.ui.canvas.items.callout_item import CalloutItem
    from open_garden_planner.ui.canvas.items.text_item import MAX_DISPLAY_TEXT_CHARS

    huge_callout = "b" * 1_000_000
    scene = CanvasScene(5000, 3000)
    item = CalloutItem(QPointF(300, 300), QPointF(80, -60), huge_callout)
    scene.addItem(item)

    assert item.content == huge_callout
    assert item.to_dict()["content"] == huge_callout
    assert len(item._text_child.toPlainText()) == MAX_DISPLAY_TEXT_CHARS + len(ELLIPSIS)
    assert item.boundingRect().width() < 100_000.0

    view = _shown(scene, qtbot)
    view.centerOn(item)
    item.setSelected(True)
    QApplication.processEvents()
    view.viewport().repaint()
    view.viewport().repaint()

    # Untouched edit commit keeps full 1M-char content; real edit replaces it
    item.start_editing()
    item.finish_editing()
    assert item.content == huge_callout

    item.start_editing()
    item._text_child.setPlainText("North corner")
    item.finish_editing()
    assert item.content == "North corner"
    assert item._text_child.toPlainText() == "North corner"
