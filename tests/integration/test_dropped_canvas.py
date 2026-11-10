"""A canvas that is dropped, not closed, must not end the process (review round 2, P1-1).

``CanvasView.scrollContentsBy`` read ``self._sun_legend_rect``. When the cyclic
collector takes a view together with its scene, it clears both objects'
attributes and then destroys them in an order of its own. Qt, destroying the
scene first, takes it from the view; that moves the scroll bars and calls
``scrollContentsBy`` on a view that has no attributes left. The
``AttributeError`` was raised inside a virtual that Qt had called, and PyQt
ends the process for that: exit code 0xC0000409, no traceback.

The suite never saw it: ``tests/conftest.py`` closes and deletes every widget
after each test, which destroys them in Qt's order. So this runs in a child
process (``dropped_canvas_child.py``) that builds canvases with everything on —
labels, the grid, the sun overlay, the sun map's key, the minimap, a selection,
scroll bars — paints them and drops them.

What Qt calls during such a collection was recorded, not guessed: with every
method of the view, the scene, the minimap, the shadow controller and every
item wrapped, the only Python code Qt entered was ``scrollContentsBy`` (and
what it calls). PF-CAN-61.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHILD = Path(__file__).with_name("dropped_canvas_child.py")


def test_collecting_a_dropped_canvas_does_not_end_the_process() -> None:
    done = subprocess.run(
        [sys.executable, str(CHILD), str(REPO)],
        capture_output=True, text=True, timeout=600, cwd=str(REPO),
    )
    assert done.returncode == 0, (
        f"the child ended with {done.returncode & 0xFFFFFFFF:#x} after\n"
        f"{done.stdout[-1500:]}\n{done.stderr[-3000:]}"
    )
    assert done.stdout.rstrip().endswith("done"), done.stdout[-1500:]


def test_the_view_reads_its_key_rectangle_without_attributes() -> None:
    """The mechanism itself, in this process: the attribute the scroll hook
    reads is found on the class when the instance has none."""
    from PyQt6.QtCore import QRect

    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    assert isinstance(vars(CanvasView).get("_sun_legend_rect"), QRect)
    assert CanvasView._sun_legend_rect.isEmpty()
