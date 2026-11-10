"""A tool's preview is no change of the plan's picture (second review of the 2D branch).

The scene keeps what a paint needs of the whole plan — what stands on it (the
grid's cut-out) and which labels have room — until its paint revision moves
(§8.37). The revision used to move on Qt's ``QGraphicsScene.changed``, and that
signal cannot tell an edit from a preview: a rubber band, a shape being drawn
and the measure tool's snap mark are scene items, and each of their moves took
both kept answers again. On the review's plan of 853 objects: 15 rebuilds of
each in 30 rubber-band moves, 12 ms a move.

The first class counts (§8.10.10). The second looks at pixels: a preview is
painted while it is there and leaves nothing behind.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QImage, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem
from tests.large_plan import show_large_plan

NO_KEYS = Qt.KeyboardModifier.NoModifier
LEFT = Qt.MouseButton.LeftButton


def _events() -> None:
    for _ in range(3):
        QApplication.processEvents()


def _drag_to(view: CanvasView, point: QPoint) -> None:
    """A mouse move with the left button held (``QTest.mouseMove`` holds none)."""
    viewport = view.viewport()
    assert viewport is not None
    event = QMouseEvent(
        QEvent.Type.MouseMove, QPointF(point), QPointF(viewport.mapToGlobal(point)),
        Qt.MouseButton.NoButton, LEFT, NO_KEYS,
    )
    QApplication.sendEvent(viewport, event)
    _events()


def _kept(view: CanvasView, scene: CanvasScene) -> tuple[int, int, int, int]:
    return (
        scene.paint_revision, scene.standing_cover_builds, scene.label_layouts,
        view.grid_layer_builds,
    )


@pytest.fixture()
def large(qtbot):
    view, scene, _items = show_large_plan(qtbot)
    view.set_grid_visible(True)
    _events()
    view.viewport().repaint()
    _events()
    assert scene.standing_cover_builds > 0 and scene.label_layouts > 0
    return view, scene


class TestAPreviewRebuildsNothing:
    def test_thirty_rubber_band_moves(self, large) -> None:
        view, scene = large
        viewport = view.viewport()
        view.set_active_tool(ToolType.SELECT)
        # the outside of the plan: the band starts on no object
        start = QPoint(4, 4)
        QTest.mousePress(viewport, LEFT, NO_KEYS, start)
        _events()
        before = _kept(view, scene)
        for step in range(1, 31):
            _drag_to(view, QPoint(4 + 9 * step, 4 + 5 * step))
        assert _kept(view, scene) == before, (
            "a rubber band moved the paint revision or rebuilt what is kept: "
            f"{before} -> {_kept(view, scene)} (revision, covers, layouts, grid layers)"
        )
        view.active_tool.cancel()
        _events()

    def test_a_rectangle_being_drawn(self, large) -> None:
        view, scene = large
        viewport = view.viewport()
        view.set_active_tool(ToolType.RECTANGLE)
        _events()
        QTest.mousePress(viewport, LEFT, NO_KEYS, QPoint(300, 300))
        _events()
        before = _kept(view, scene)
        for step in range(1, 31):
            _drag_to(view, QPoint(300 + 9 * step, 300 + 5 * step))
        assert _kept(view, scene) == before
        view.active_tool.cancel()
        _events()
        assert _kept(view, scene) == before, "taking the preview away is no change either"

    def test_the_measure_tool_hovering(self, large) -> None:
        view, scene = large
        viewport = view.viewport()
        view.set_active_tool(ToolType.MEASURE)
        _events()
        QTest.mouseMove(viewport, QPoint(300, 300))
        _events()
        before = _kept(view, scene)
        for step in range(1, 31):
            QTest.mouseMove(viewport, QPoint(300 + 9 * step, 300 + 5 * step))
            _events()
        assert _kept(view, scene) == before

    def test_an_edit_still_rebuilds(self, large) -> None:
        """The other half: what is kept must not outlive the plan it was
        taken from. A finished rectangle is an edit."""
        view, scene = large
        viewport = view.viewport()
        view.set_active_tool(ToolType.RECTANGLE)
        _events()
        before = _kept(view, scene)
        QTest.mousePress(viewport, LEFT, NO_KEYS, QPoint(300, 300))
        _drag_to(view, QPoint(420, 380))
        QTest.mouseRelease(viewport, LEFT, NO_KEYS, QPoint(420, 380))
        _events()
        view.viewport().repaint()
        after = _kept(view, scene)
        assert after[0] > before[0]
        assert after[1] > before[1] and after[2] > before[2]


# --------------------------------------------------------------------------
# Pixels
# --------------------------------------------------------------------------


def _grab(view: CanvasView) -> np.ndarray:
    viewport = view.viewport()
    assert viewport is not None
    image = viewport.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
    raw = image.constBits()
    assert raw is not None
    data = np.frombuffer(raw.asstring(image.sizeInBytes()), dtype=np.uint8)
    return data.reshape(image.height(), image.bytesPerLine() // 4, 4)[:, : image.width(), :3].copy()


@pytest.fixture()
def garden(qtbot):
    scene = CanvasScene(1000, 800)
    scene.set_shadows_enabled(False)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    qtbot.waitExposed(view)
    view.set_snap_enabled(False)
    bed = RectangleItem(100, 100, 300, 200, object_type=ObjectType.RAISED_BED, name="Bed")
    tree = CircleItem(700, 400, 110, object_type=ObjectType.TREE, name="Tree")
    for item in (bed, tree):
        scene.addItem(item)
        item.initialize_label()
    view.fit_in_view()
    view.set_grid_visible(True)
    _events()
    view.viewport().repaint()
    return view, scene


class TestAPreviewIsPaintedAndLeavesNothing:
    def test_a_rubber_band(self, garden) -> None:
        view, _scene = garden
        viewport = view.viewport()
        view.set_active_tool(ToolType.SELECT)
        clear = _grab(view)
        # on the bare plan, between the bed and the tree
        start = view.mapFromScene(QPointF(450.0, 600.0))
        end = view.mapFromScene(QPointF(560.0, 700.0))
        QTest.mousePress(viewport, LEFT, NO_KEYS, start)
        _drag_to(view, (start + end) / 2)
        _drag_to(view, end)
        with_band = _grab(view)
        box = (slice(min(start.y(), end.y()) + 2, max(start.y(), end.y()) - 2),
               slice(min(start.x(), end.x()) + 2, max(start.x(), end.x()) - 2))
        changed = np.abs(with_band[box].astype(int) - clear[box].astype(int)).sum(axis=2) > 6
        assert changed.mean() > 0.8, "the rubber band is not painted"
        QTest.mouseRelease(viewport, LEFT, NO_KEYS, end)
        _events()
        assert np.array_equal(_grab(view), clear), "the rubber band left pixels behind"

    def test_a_rectangle_being_drawn_and_cancelled(self, garden) -> None:
        view, scene = garden
        viewport = view.viewport()
        count = len(scene.items())
        view.set_active_tool(ToolType.RECTANGLE)
        _events()
        clear = _grab(view)
        start = view.mapFromScene(QPointF(450.0, 600.0))
        end = view.mapFromScene(QPointF(560.0, 700.0))
        QTest.mousePress(viewport, LEFT, NO_KEYS, start)
        _drag_to(view, end)
        with_preview = _grab(view)
        box = (slice(min(start.y(), end.y()) + 2, max(start.y(), end.y()) - 2),
               slice(min(start.x(), end.x()) + 2, max(start.x(), end.x()) - 2))
        changed = np.abs(with_preview[box].astype(int) - clear[box].astype(int)).sum(axis=2) > 6
        assert changed.mean() > 0.8, "the shape being drawn is not painted"
        # Escape, as the user cancels: the view's own path also takes away the
        # readout it shows beside the cursor.
        QTest.keyClick(viewport, Qt.Key.Key_Escape)
        _events()
        assert len(scene.items()) == count
        assert np.array_equal(_grab(view), clear), "the cancelled shape left pixels behind"
