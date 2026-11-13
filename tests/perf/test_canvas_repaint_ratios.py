"""What the grid's cut-out and the label pass cost in a repaint of a large plan (review of #784, #793).

Scenario: the review's plan of 853 named objects (``tests/large_plan.py``) at
fit in a 1469 x 901 viewport. Before the review's fixes the grid's cut-out
was built on every paint (a full repaint with the grid on cost 3.5 times one
with the lines and no cut-out) and the label pass laid out every label on every
paint (a 40-pixel repaint cost 2.8 times one without the pass). Both are kept
by the scene now (§8.9.15, §8.9.17, §8.37): measured 1.1 and 1.0-1.1, in five
runs on a machine that five other processes were loading (one run of the grid
read 1.47).

Each bound is a RATIO of two medians taken alternately in the same process,
never milliseconds: this machine's absolute timings drift by half with no code
change (#509), a ratio of interleaved measurements does not. The counts that
hold on any machine are in ``tests/integration/test_grid_cover_cache.py`` and
``tests/integration/test_label_layout_cache.py``.
"""

from __future__ import annotations

import gc
import statistics
import time
from collections.abc import Callable

import pytest
from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QApplication

from open_garden_planner.ui.canvas import plan_labels
from tests.large_plan import show_large_plan

#: A full repaint with the grid on may cost this many times one that draws
#: the grid's lines with nothing cut out of them. Measured 1.09-1.11 with the
#: kept cut-out (1.47 in one run under load), 3.5 before; 2 leaves room for a
#: busy machine and none for a cut-out that is built on every paint. Since the
#: second review the view keeps the finished layer as well, and a repaint lays
#: it down: 0.70-0.86, cheaper than drawing the lines.
GRID_CUT_OUT_RATIO = 2.0

#: A 40 x 40 pixel repaint may cost this many times the same repaint with the
#: label pass switched off. Measured 1.02-1.09 with the kept layout, 2.8 before.
LABEL_PASS_RATIO = 2.0


def _median_ms(paint: Callable[[], None], count: int = 11, warmup: int = 3) -> float:
    gc.collect()
    for _ in range(warmup):
        paint()
        QApplication.processEvents()
    times: list[float] = []
    for _ in range(count):
        started = time.perf_counter()
        paint()
        times.append((time.perf_counter() - started) * 1000.0)
    return statistics.median(times)


@pytest.mark.perf
def test_grid_cut_out_repaint_ratio(qtbot, monkeypatch) -> None:
    view, scene, _items = show_large_plan(qtbot)
    view.set_grid_visible(True)
    QApplication.processEvents()
    viewport = view.viewport()
    with_cut_out = view._draw_grid

    def lines_only(painter: QPainter, rect: QRectF) -> None:
        plan = scene.canvas_rect.intersected(rect)
        painter.save()
        painter.setClipRect(plan, Qt.ClipOperation.IntersectClip)
        view._draw_grid_lines(painter, plan)
        painter.restore()

    ratios: list[float] = []
    readings: list[tuple[float, float]] = []
    for _ in range(7):  # alternately: drift hits both arms alike
        monkeypatch.setattr(view, "_draw_grid", with_cut_out)
        cut = _median_ms(viewport.repaint)
        monkeypatch.setattr(view, "_draw_grid", lines_only)
        plain = _median_ms(viewport.repaint)
        readings.append((cut, plain))
        ratios.append(cut / max(plain, 1e-6))
    ratio = statistics.median(ratios)
    print("[GRID-PERF] cut-out/lines ms per round: "
          + " ".join(f"{a:.1f}/{b:.1f}" for a, b in readings)
          + f" | ratio median {ratio:.2f} min {min(ratios):.2f} max {max(ratios):.2f}")
    assert ratio <= GRID_CUT_OUT_RATIO, (
        f"a repaint with the grid's cut-out costs {ratio:.2f} times one with the lines alone "
        f"(bound {GRID_CUT_OUT_RATIO}); rounds ms: {readings}"
    )


@pytest.mark.perf
def test_label_pass_partial_repaint_ratio(qtbot, monkeypatch) -> None:
    view, _scene, _items = show_large_plan(qtbot)
    view.set_grid_visible(False)
    QApplication.processEvents()
    viewport = view.viewport()
    viewport.repaint()
    patch = QRect(viewport.width() // 2, viewport.height() // 2, 40, 40)
    real = plan_labels.LabelPass.paint

    def partial() -> None:
        viewport.repaint(patch)

    ratios: list[float] = []
    readings: list[tuple[float, float]] = []
    for _ in range(7):
        monkeypatch.setattr(plan_labels.LabelPass, "paint", real)
        with_pass = _median_ms(partial, count=21)
        monkeypatch.setattr(plan_labels.LabelPass, "paint", lambda *_args: None)
        without = _median_ms(partial, count=21)
        readings.append((with_pass, without))
        ratios.append(with_pass / max(without, 1e-6))
    ratio = statistics.median(ratios)
    print("[LABEL-PERF] pass on/off ms per round: "
          + " ".join(f"{a:.2f}/{b:.2f}" for a, b in readings)
          + f" | ratio median {ratio:.2f} min {min(ratios):.2f} max {max(ratios):.2f}")
    assert ratio <= LABEL_PASS_RATIO, (
        f"a 40-pixel repaint with the label pass costs {ratio:.2f} times one without "
        f"(bound {LABEL_PASS_RATIO}); rounds ms: {readings}"
    )
