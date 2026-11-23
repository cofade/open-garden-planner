"""Native Windows font/repaint oracle, launched by test_canvas_native_pixels."""

from __future__ import annotations

import faulthandler
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "windows"
faulthandler.enable()



from scripts.quiet_windows import keep_windows_behind  # noqa: E402

import tests.conftest  # noqa: E402, F401 -- isolate all stores before app imports

keep_windows_behind()

import numpy as np  # noqa: E402
from PyQt6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt  # noqa: E402
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


def embedded_shed_repaints() -> dict:
    """Capture the main window's existing backing store through the edit sequence."""
    from unittest.mock import patch

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.core.commands import ResizeItemCommand
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.geometry_apply import (
        apply_rect_like_geometry,
        build_rect_resize,
    )

    with (
        patch.object(GardenPlannerApp, "_startup_sequence"),
        patch.object(GardenPlannerApp, "_start_update_check"),
    ):
        window = GardenPlannerApp()
    window.showNormal()
    window.resize(1100, 720)
    window.show()
    assert QTest.qWaitForWindowExposed(window)
    # The thumbnail is not part of this oracle. Its 100 ms throttle re-arms on
    # every scene change, and under a loaded machine the child could not rely
    # on it settling; disable it and stop an already scheduled tick.
    window._minimap.set_visible(False)
    window._minimap._update_timer.stop()
    window._load_project_file(str(ROOT / "src/open_garden_planner/resources/examples/family-garden.ogp"))
    view = window.canvas_view
    scene = view.scene()
    scene.set_shadows_enabled(False)
    view.set_grid_visible(False)
    viewport = view.viewport()
    shed = next(item for item in scene.items()
                if getattr(item, "object_type", None) == ObjectType.GARAGE_SHED)
    view.set_zoom(0.77)
    view.centerOn(shed.sceneBoundingRect().center())
    scene.clearSelection()
    shed.setSelected(True)

    class PaintRegions(QObject):
        def __init__(self):
            super().__init__()
            self.regions = []

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint:
                self.regions.append(event.region().boundingRect().getRect())
            return False

    regions = PaintRegions()
    viewport.installEventFilter(regions)

    def grab() -> QImage:
        frame = window.screen().grabWindow(window.winId())
        assert not frame.isNull()
        ratio = frame.devicePixelRatio()
        origin = viewport.mapTo(window, QPoint())
        crop = QRect(round(origin.x() * ratio), round(origin.y() * ratio),
                     round(viewport.width() * ratio), round(viewport.height() * ratio))
        return frame.toImage().copy(crop).convertToFormat(QImage.Format.Format_ARGB32)

    def bounds(mask):
        rows, columns = np.nonzero(mask)
        return [int(columns.min()), int(rows.min()), int(columns.max()), int(rows.max())] if len(rows) else []

    def settle(*, expect_paint: bool = True) -> None:
        # Deliver queued scene changes and wait until the measured viewport
        # stops receiving paint events: a fixed sleep is a guess, the paint
        # filter is the thing the comparison actually depends on. The minimap
        # is disabled above, so it cannot confound this. An edit must produce
        # at least one paint before its quiet window starts, or a starved
        # event loop could let this return before the first frame.
        QTest.qWait(1)
        window._minimap._update_timer.stop()
        if not expect_paint:
            # The opening baseline follows a fit timer; settle it with a short
            # drain and do not require a quiet paint stream (the fit animation
            # is still finishing). The measured drain is for the edits.
            QTest.qWait(200)
            return
        first = time.monotonic() + 5
        while not regions.regions and time.monotonic() < first:
            QTest.qWait(10)
        assert regions.regions, "the edit produced no viewport paint"
        # The viewport keeps receiving frames while the window is live (the
        # selection and the update indicator animate), so a "quiet stream"
        # never arrives. Wait until the edit's first frame is in, then let the
        # backing store and the following frame settle. Measured: 150 ms was
        # enough for every edit but the undo/redo pair, which needs the
        # command's full rebuild; 500 ms also covers a cold font/backing-store
        # cache on the first run after a build.
        QTest.qWait(500)

    def resize() -> None:
        rect = shed.rect()
        old, new = build_rect_resize(shed, rect.width() + 35, rect.height() - 17)
        view.command_manager.execute(ResizeItemCommand(shed, old, new, apply_rect_like_geometry))

    QTest.qWait(120)  # Startup fit timer precedes the edit sweep.
    view.set_zoom(0.77)
    view.centerOn(shed.sceneBoundingRect().center())
    settle(expect_paint=False)
    results = {}
    last = grab()
    edits = (
        ("shed_to_glasshouse", lambda: shed._dispatch_change_type(ObjectType.GREENHOUSE)),
        ("move", lambda: shed.moveBy(17.3, -6.1)),
        ("rotate", lambda: shed._apply_rotation(31.7)),
        ("undo_type", view.command_manager.undo),
        ("redo_type", view.command_manager.redo),
        ("resize", resize),
        ("undo_resize", view.command_manager.undo),
    )
    for name, edit in edits:
        regions.regions.clear()
        edit()
        settle()
        partial = grab()
        ordinary = list(regions.regions)
        viewport.repaint()
        full = grab()
        viewport.repaint()
        repeated = grab()
        partial_pixels, full_pixels = _pixels(partial), _pixels(full)
        diff = np.any(partial_pixels != full_pixels, axis=2)
        if folder := os.environ.get("OGP_PIXEL_ARTIFACT_DIR"):
            Path(folder).mkdir(parents=True, exist_ok=True)
            partial.save(str(Path(folder) / f"{name}-partial.png"))
            full.save(str(Path(folder) / f"{name}-full.png"))
            mask = QImage(diff.shape[1], diff.shape[0], QImage.Format.Format_RGB32)
            mask_bits = mask.bits()
            mask_bits.setsize(mask.sizeInBytes())
            pixels = np.frombuffer(mask_bits, np.uint32).reshape(diff.shape)
            pixels[:] = np.where(diff, 0xFFFFFFFF, 0xFF000000)
            mask.save(str(Path(folder) / f"{name}-difference.png"))
        results[name] = {
            "changed": int(np.any(_pixels(last) != full_pixels, axis=2).sum()),
            "diff": int(diff.sum()),
            "diff_bounds": bounds(diff),
            "repeat_noise": int(np.any(full_pixels != _pixels(repeated), axis=2).sum()),
            "regions": ordinary,
        }
        last = full
    assert shed.isSelected()
    window._project_manager.mark_clean()
    # Release Qt-owned children while Python and QApplication are both alive.
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    assert window.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return results


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


def _reset_display_profile() -> None:
    """The oracle is a picture of the default plan; a shared xdist worker may
    have left a non-metric display profile in the isolated test store (#907)."""
    from open_garden_planner.app.settings import get_settings

    get_settings().unit_system = "metric"
    get_settings().sync()


if __name__ == "__main__":
    _reset_display_profile()
    app = QApplication([])
    assert app.platformName() == "windows"
    print(json.dumps({"gaps": letter_gaps(), "hinted": letter_gaps(True),
                      "repaints": repaint_differences(), "balcony": balcony_note_boxes(),
                      "foreground": relocated_content_changes(),
                      "embedded_shed": embedded_shed_repaints()}))
