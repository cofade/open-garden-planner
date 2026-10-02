"""Unit tests for the reserved tool-preview z band (issue #377).

The band must sit strictly above every derived document-item z (which lives in
``(0, 100)``) and strictly below ``minimap_widget._OVERLAY_Z_MIN`` — a preview at
or above that cutoff disappears from the minimap thumbnail mid-gesture.
"""

import re
from pathlib import Path

import pytest

from open_garden_planner.core.tools import preview_z
from open_garden_planner.ui.widgets.minimap_widget import _OVERLAY_Z_MIN

_TOOLS_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "open_garden_planner"
    / "core"
    / "tools"
)

# Every module issue #377 identified as building a bare preview primitive.
# Deliberately re-derived from the source (grep for QGraphics*Item( constructions)
# rather than copied from the issue, whose own list was incomplete: it omitted
# construction_tool.py and wrongly included text/fillet/chamfer (which build no
# preview item at all).
_PREVIEW_TOOL_MODULES = (
    "circle_tool.py",
    "rectangle_tool.py",
    "ellipse_tool.py",
    "polygon_tool.py",
    "polyline_tool.py",
    "arc_tool.py",
    "bezier_tool.py",
    "mirror_tool.py",
    "callout_tool.py",
    "select_tool.py",
    "construction_tool.py",
)

_CONSTRUCTOR = re.compile(
    r"QGraphics(?:EllipseItem|LineItem|PathItem|RectItem|PolygonItem)\("
    r"|scene\(\)\.add(?:Ellipse|Line|Path|Rect|Polygon|Text)\("
    r"|\.add(?:Ellipse|Line|Path|Rect|Polygon|Text)\("
)

# Modules whose preview z is governed by their OWN established constant and are
# therefore deliberately outside the #377 band: `offset_tool` uses the
# transient-preview value 9999, and `measure_tool`/`constraint_tool` use the
# tool-overlay band 1000-1003. They build previews via `scene.add*()` rather than
# direct constructors, which is why the issue's own census missed them entirely.
_ESTABLISHED_OTHER_BAND = frozenset(
    {"offset_tool.py", "measure_tool.py", "constraint_tool.py", "trim_tool.py"}
)


class TestPreviewZBand:
    def test_band_is_positive(self) -> None:
        for name in (
            "PREVIEW_Z_FILL",
            "PREVIEW_Z_LINE",
            "PREVIEW_Z_LABEL",
            "PREVIEW_Z_HANDLE",
        ):
            assert getattr(preview_z, name) >= 1, name

    def test_band_stays_below_minimap_overlay_cutoff(self) -> None:
        """A preview must stay visible in the minimap thumbnail (#377 / §8.9.5)."""
        for name in (
            "PREVIEW_Z_FILL",
            "PREVIEW_Z_LINE",
            "PREVIEW_Z_LABEL",
            "PREVIEW_Z_HANDLE",
            "MAX_PREVIEW_Z",
        ):
            assert getattr(preview_z, name) < _OVERLAY_Z_MIN, name

    def test_band_outranks_every_document_item(self) -> None:
        """Derived document-item z is strictly inside (0, 100)."""
        assert preview_z.PREVIEW_Z_FILL > 100

    def test_relative_order_is_fill_line_label_handle(self) -> None:
        assert (
            preview_z.PREVIEW_Z_FILL
            <= preview_z.PREVIEW_Z_LINE
            <= preview_z.PREVIEW_Z_LABEL
            <= preview_z.PREVIEW_Z_HANDLE
        )


@pytest.mark.parametrize("module_name", _PREVIEW_TOOL_MODULES)
def test_module_imports_a_preview_z_constant(module_name: str) -> None:
    """Each preview-building module must import the shared band, not hardcode a value."""
    source = (_TOOLS_DIR / module_name).read_text(encoding="utf-8")
    assert "preview_z import" in source, (
        f"{module_name} builds a preview primitive but does not import the shared "
        "preview-z constants (see core/tools/preview_z.py)."
    )


@pytest.mark.parametrize("module_name", _PREVIEW_TOOL_MODULES)
def test_every_preview_constructor_gets_a_z_value(module_name: str) -> None:
    """Heuristic drift guard: a new bare preview must not ship without a z-value.

    This is what would have caught the issue's own incomplete module list. It is a
    heuristic — it looks for ``setZValue`` within the eight lines after each
    preview construction (direct constructor OR ``scene.add*()``) — but it fails
    loudly on the exact mistake that caused #377.
    """
    lines = (_TOOLS_DIR / module_name).read_text(encoding="utf-8").splitlines()
    missing = []
    for index, line in enumerate(lines):
        if _CONSTRUCTOR.search(line):
            window = "\n".join(lines[index : index + 9])
            if "setZValue" not in window:
                missing.append(index + 1)
    assert not missing, (
        f"{module_name}: preview constructor(s) at line(s) {missing} have no nearby "
        "setZValue — the preview would draw behind beds and objects (#377)."
    )


@pytest.mark.parametrize("module_name", sorted(_ESTABLISHED_OTHER_BAND))
def test_established_modules_still_set_a_z_value(module_name: str) -> None:
    """The modules with their own band must still govern their previews.

    They are excluded from the #377 band because they already have one, not
    because z-ordering is unhandled there — so a regression that dropped their
    ``setZValue`` calls must still fail.
    """
    lines = (_TOOLS_DIR / module_name).read_text(encoding="utf-8").splitlines()
    preview_lines = [i for i, line in enumerate(lines) if _CONSTRUCTOR.search(line)]
    if not preview_lines:
        return
    assert any("setZValue" in line for line in lines), (
        f"{module_name} builds previews but never calls setZValue; it is expected "
        "to govern them with its own established band."
    )
