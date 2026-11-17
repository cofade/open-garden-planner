"""Native Windows font/repaint oracle, launched by test_canvas_native_pixels."""

from __future__ import annotations

import faulthandler
import json
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "windows"
faulthandler.enable()



from scripts.quiet_windows import keep_windows_behind  # noqa: E402

import tests.conftest  # noqa: E402, F401 -- isolate all stores before app imports

keep_windows_behind()

import numpy as np  # noqa: E402
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt  # noqa: E402
from PyQt6.QtGui import QFont, QFontInfo, QImage, QPainter  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QGraphicsScene  # noqa: E402

from open_garden_planner.ui.canvas.items import TextItem  # noqa: E402


def repaint_differences() -> list[int]:
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView
    from open_garden_planner.ui.canvas.items import RectangleItem

    scene = CanvasScene(3000, 2000)
    view = CanvasView(scene)
    view.resize(800, 600)
    scene.set_shadows_enabled(False)
    view.set_grid_visible(False)
    view.show()
    view.set_zoom(0.77)
    item = RectangleItem(900, 800, 300, 200)
    scene.addItem(item)
    item.setSelected(True)
    view.centerOn(item.rect().center())
    QTest.qWait(80)
    differences = []
    handle_counts = []

    def grab():
        image = view.screen().grabWindow(view.viewport().winId()).toImage()
        assert not image.isNull()
        return image.convertToFormat(QImage.Format.Format_ARGB32)

    for step in range(15):
        item.setPos(QPointF(step * 2.3, step * 1.7))
        item._apply_rotation(step * 3.7)
        QTest.qWait(35)
        handle = item._resize_handles[0]
        pixel = view.mapFromScene(handle.scenePos())
        view.viewport().repaint(QRect(pixel.x() - 2, pixel.y() - 2, 4, 4))
        partial = grab()
        rgb = _pixels(partial)[:, :, :3]
        handle_counts.append(int(((rgb[:, :, 0] > 170) & (rgb[:, :, 1] > 65) & (rgb[:, :, 1] < 180) & (rgb[:, :, 2] < 50)).sum()))
        view.viewport().repaint()
        full = grab()
        difference = int(np.any(_pixels(partial) != _pixels(full), axis=2).sum())
        differences.append(difference)

    assert min(handle_counts) > 100, "the capture must contain real selected handles"
    if folder := os.environ.get("OGP_PIXEL_ARTIFACT_DIR"):
        Path(folder).mkdir(parents=True, exist_ok=True)
        partial.save(str(Path(folder) / "canvas-native.png"))
    view.close()
    view.setScene(None)
    view.deleteLater()
    scene.clear()
    return differences


def _pixels(image: QImage) -> np.ndarray:
    data = image.bits()
    data.setsize(image.sizeInBytes())
    return np.frombuffer(data, np.uint8).reshape(image.height(), image.bytesPerLine())[:, :image.width()*4].reshape(image.height(), image.width(), 4).copy()


def _letter_centres(note: TextItem, zoom: float, font_multiplier: int = 1) -> np.ndarray:
    scene = QGraphicsScene()
    scene.addItem(note)
    font = note.font()
    font.setPixelSize(QFontInfo(font).pixelSize() * font_multiplier)
    note.setFont(font)
    rect = note.sceneBoundingRect()
    width = round(rect.width() * zoom / font_multiplier) + 4
    height = round(rect.height() * zoom / font_multiplier) + 4
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.translate(0, height)
    painter.scale(1, -1)
    scene.render(painter, QRectF(0, 0, width - 4, height - 4), rect,
                 Qt.AspectRatioMode.IgnoreAspectRatio)
    painter.end()
    columns = np.any(_pixels(image)[:, :, :3].min(axis=2) < 100, axis=0)
    starts = np.flatnonzero(np.diff(np.r_[False, columns].astype(int)) == 1)
    ends = np.flatnonzero(np.diff(np.r_[columns, False].astype(int)) == -1)
    return (starts + ends) / 2


def letter_gaps(hinted: bool = False) -> list[float]:
    errors = []
    for zoom in (2.2, 3.3):
        note = TextItem(0, 0, "iiiiiiiiiiii", font_size=0.42)
        if hinted:
            font = note.font()
            font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
            note.setFont(font)
        normal = _letter_centres(note, zoom)
        reference = _letter_centres(TextItem(0, 0, "iiiiiiiiiiii", font_size=0.42), zoom, 12)
        assert len(normal) == len(reference) == 12, (normal, reference)
        errors.append(float(np.max(np.abs(np.diff(normal) - np.diff(reference)))))
    return errors


def balcony_note_boxes():
    from open_garden_planner.core.furniture_renderer import is_furniture_type
    from open_garden_planner.core.item_geometry import object_outline
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.services.example_library import bundled_examples
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    result = {}
    for language in ("en", "de", "es"):
        scene = CanvasScene()
        entry = next(e for e in bundled_examples(language) if e.path.stem == "balcony")
        ProjectManager().load(scene, entry.path, as_template=True)
        note = next(i for i in scene.items() if isinstance(i, TextItem))
        box = note.sceneBoundingRect()
        overlaps = [i.name for i in scene.items() if (is_furniture_type(getattr(i,"object_type",None)) or getattr(i,"object_type",None) is ObjectType.PARASOL) and i.sceneTransform().map(object_outline(i)).intersects(box)]
        result[language] = {"note": [box.x(),box.y(),box.width(),box.height()], "overlaps":overlaps}
        scene.clear()
    return result


def relocated_content_changes():
    from PyQt6.QtGui import QColor

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.canvas_view import CanvasView
    from open_garden_planner.ui.canvas.items import RectangleItem
    from open_garden_planner.ui.canvas.items.halo_text import PlanLabelItem
    from open_garden_planner.ui.canvas.plan_labels import plan_labels_shown, succession_badges_shown

    results = {}
    for case in ("rotated_tag", "edge_label", "edge_colour"):
        scene = CanvasScene(3000, 2000)
        view = CanvasView(scene)
        view.resize(900, 640)
        view.set_grid_visible(False)
        view.show()
        QTest.qWaitForWindowExposed(view)
        if case == "rotated_tag":
            bed = RectangleItem(800, 600, 500, 350, object_type=ObjectType.RAISED_BED)
            scene.addItem(bed)
            bed.set_succession_indicator([("AAAA", True)])
            label = bed._succession_badge_item
            label.setFont(QFont("Consolas", 12))
            bed._apply_rotation(37)
            view.set_zoom(1)
            view.centerOn(bed.mapToScene(bed.rect().center()))
            entries = succession_badges_shown
        else:
            label = PlanLabelItem("AAAAAAAA")
            label.free_extent_px = 100
            label.setFont(QFont("Consolas", 12))
            label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations)
            label.setPos(0, scene.height_cm)
            scene.addItem(label)
            view.fit_in_view()
            entries = plan_labels_shown
        QTest.qWait(100)

        def grab(target=view):
            image = target.screen().grabWindow(target.viewport().winId()).toImage()
            assert not image.isNull()
            return _pixels(image.convertToFormat(QImage.Format.Format_ARGB32))

        initial = grab()
        before = entries(scene, view.viewportTransform())[0][2]
        if case == "rotated_tag":
            label.set_lines([("BBBB", True)])
        elif case == "edge_colour":
            label.setBrush(QColor("purple"))
        else:
            label.setText("BBBBBBBB")
        QTest.qWait(100)
        partial = grab()
        after = entries(scene, view.viewportTransform())[0][2]
        view.viewport().repaint()
        full = grab()
        view.viewport().repaint()
        repeated = grab()
        results[case] = {
            "equal_bounds": before == after,
            "changed": int(np.count_nonzero(initial != full)),
            "stale": int(np.count_nonzero(partial != full)),
            "repeat_noise": int(np.count_nonzero(full != repeated)),
        }
        view.setScene(None)
        view.close()
        view.deleteLater()
        scene.clear()
    return results


if __name__ == "__main__":
    app = QApplication([])
    assert app.platformName() == "windows"
    print(json.dumps({"gaps": letter_gaps(), "hinted": letter_gaps(True),
                      "repaints": repaint_differences(), "balcony": balcony_note_boxes(),
                      "foreground": relocated_content_changes()}))
