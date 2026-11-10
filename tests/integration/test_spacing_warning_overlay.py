"""#786 - a spacing warning is a quiet mark, and no diagnostic overlay is in an export.

Before: a plant too close to a neighbour drew a FILLED translucent red disc at its
spacing radius, the bundled family garden opened under a red wash (24 discs up to
12 m wide), and the discs were in every exported picture. A food-forest guild
reported each ground-cover plant under its tree as an overlap.

Now, end to end on the real window, canvas and scene:

* the warning is a thin dashed line on the crowded spot only, never a fill;
* a plant whose spacing is fine draws nothing unless it is selected;
* a tree and what grows under its crown are no conflict (``core.plant_sizing``);
* a picture of the plan (PNG, SVG, PDF report, print, Agent API) carries no
  diagnostic decoration: one seam, ``ExportService._hide_overlay_items``.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.services.diagnostics import diagnostics_from_records
from open_garden_planner.services.export_service import ExportService
from open_garden_planner.services.scene_rendering import render_scene_region
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem
from tests.integration.test_bed_context_menu import BED_SHAPES

EXAMPLES = Path(__file__).parents[2] / "src/open_garden_planner/resources/examples"


def _make_app(qtbot, monkeypatch):
    from open_garden_planner.app.application import GardenPlannerApp

    monkeypatch.setattr(
        QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(1300, 900)
    win.show()
    qtbot.waitExposed(win)
    return win


def _open(win, slug: str) -> None:
    win._load_project_file(str(EXAMPLES / f"{slug}.ogp"))
    win._sim_clock.set_datetime(datetime(2026, 6, 21, 12, 0))
    QApplication.processEvents()
    win.canvas_view.fit_in_view()
    win._update_spacing_overlaps()
    QApplication.processEvents()


def _grab(view: CanvasView) -> QImage:
    QApplication.processEvents()
    return view.viewport().grab().toImage().convertToFormat(QImage.Format.Format_RGB32)


def _changed_share(first: QImage, second: QImage, threshold: int = 30) -> float:
    """Share of pixels whose colour differs between two pictures of the same size."""
    assert first.size() == second.size()
    changed = 0
    for y in range(first.height()):
        for x in range(first.width()):
            a, b = QColor(first.pixel(x, y)), QColor(second.pixel(x, y))
            if (
                abs(a.red() - b.red()) + abs(a.green() - b.green()) + abs(a.blue() - b.blue())
                > threshold
            ):
                changed += 1
    return changed / (first.width() * first.height())


def _spacing_counts(win) -> Counter:
    records = win._project_manager.diagnostics_snapshot(win.canvas_scene)
    return Counter(d.kind for d in diagnostics_from_records(records))


# --------------------------------------------------------------------------
# The flagship example on the real canvas
# --------------------------------------------------------------------------


def test_the_family_garden_opens_without_a_red_wash(qtbot, monkeypatch) -> None:
    win = _make_app(qtbot, monkeypatch)
    _open(win, "family-garden")
    view = win.canvas_view

    with_warnings = _grab(view)
    win._spacing_circles_action.trigger()      # View > Overlays > Show Spacing Circles: off
    without = _grab(view)
    win._spacing_circles_action.trigger()

    share = _changed_share(with_warnings, without)
    # Measured on master (53b48405): 22.0 % of the viewport was tinted by the
    # discs. The dashed arcs change 1.1 % of it.
    assert share < 0.04, f"spacing warnings repaint {share:.1%} of the canvas"
    # ...and they are still there to be noticed.
    assert share > 0.0005, "the spacing warnings are not visible at all"


def test_the_spacing_diagnostics_of_the_four_examples(qtbot, monkeypatch) -> None:
    """The counts the diagnostics list shows for the bundled plans.

    A food forest's guild plants stand under their tree on purpose: 22 false
    overlaps before #786, none now. The family garden keeps 22 TRUE ones (six
    trees drawn at today's size whose mature crowns will meet, a shrub border
    planted 70 cm apart, snug vegetable rows); they are reported, not hidden.
    Master reported 24 there: two berry shrubs under the spruce and the apple.
    """
    win = _make_app(qtbot, monkeypatch)
    counts = {}
    for slug in ("family-garden", "food-forest", "raised-bed", "balcony"):
        _open(win, slug)
        counts[slug] = _spacing_counts(win)["spacing_overlap"]
    assert counts == {"family-garden": 22, "food-forest": 0, "raised-bed": 0, "balcony": 0}


def test_no_tree_is_reported_against_what_grows_under_it(qtbot, monkeypatch) -> None:
    from open_garden_planner.core.plant_sizing import spacing_storey_for_item

    win = _make_app(qtbot, monkeypatch)
    for slug in ("family-garden", "food-forest"):
        _open(win, slug)
        plants = {
            (round(p.mapToScene(p.rect().center()).x(), 3),
             round(p.mapToScene(p.rect().center()).y(), 3)): p
            for p in win.canvas_scene.items() if win._is_canvas_plant(p)
        }
        for plant in plants.values():
            for x, y, _radius in plant.spacing_conflicts:
                neighbour = plants[(round(x, 3), round(y, 3))]
                assert spacing_storey_for_item(plant) == spacing_storey_for_item(neighbour)


def test_the_export_of_the_family_garden_carries_no_warning_overlay(
    qtbot, monkeypatch, tmp_path
) -> None:
    win = _make_app(qtbot, monkeypatch)
    _open(win, "family-garden")
    scene = win.canvas_scene
    assert _spacing_counts(win)["spacing_overlap"] == 22

    ExportService.export_to_png(scene, tmp_path / "with.png", dpi=72, output_width_cm=20.0)
    win._spacing_circles_action.trigger()      # every spacing state cleared
    assert _spacing_counts(win)["spacing_overlap"] == 0
    ExportService.export_to_png(scene, tmp_path / "without.png", dpi=72, output_width_cm=20.0)

    with_warnings, without = QImage(str(tmp_path / "with.png")), QImage(str(tmp_path / "without.png"))
    assert _changed_share(with_warnings, without, threshold=0) == 0.0


# --------------------------------------------------------------------------
# The mark itself: an outline, drawn on the crowded spot
# --------------------------------------------------------------------------


def _tree(scene: CanvasScene, x: float, y: float, footprint: float, spread: float) -> CircleItem:
    plant = CircleItem(x, y, footprint, object_type=ObjectType.TREE)
    plant.metadata["plant_species"] = {"common_name": "Tree", "max_spread_cm": spread}
    scene.addItem(plant)
    return plant


def _render(scene: CanvasScene, zoom: float, *, export: bool = False) -> QImage:
    rect = scene.canvas_rect
    image = QImage(int(rect.width() * zoom), int(rect.height() * zoom), QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    render_scene_region(
        scene, painter, QRectF(0, 0, image.width(), image.height()), rect,
        hide_overlays=export, hide_construction=True,
    )
    painter.end()
    return image


def _is_background(image: QImage, scene: CanvasScene, zoom: float, x: float, y: float) -> bool:
    """Whether the picture shows the bare plan colour at scene point (x, y)."""
    pixel = QColor(image.pixel(int(x * zoom), image.height() - 1 - int(y * zoom)))
    plan = scene.CANVAS_COLOR
    return (
        abs(pixel.red() - plan.red()) + abs(pixel.green() - plan.green())
        + abs(pixel.blue() - plan.blue())
    ) <= 6


def _mark_crowded(plant: CircleItem, neighbours: list[tuple[float, float, float]]) -> None:
    """Flag a plant as too close to ``neighbours`` the way the main window does.

    Before #786 the flag took no neighbours; the fallback lets these tests be run
    against that code, where they show the fill.
    """
    try:
        plant.set_spacing_overlap("overlap", neighbours)
    except TypeError:
        plant.set_spacing_overlap("overlap")


#: A point of the first tree's spacing ring (30 degrees) that lies inside the
#: second tree's ring and clear of both sprites.
_ON_RING_IN_LENS = (500.0 + 300.0 * 0.8660254, 650.0)


@pytest.fixture()
def crowded(qtbot):
    """Two trees 4 m apart whose 6 m mature crowns will meet, on an empty plan."""
    scene = CanvasScene(1600, 1000)
    scene.set_shadows_enabled(False)
    first = _tree(scene, 500.0, 500.0, 100.0, 600.0)
    second = _tree(scene, 900.0, 500.0, 100.0, 600.0)
    _mark_crowded(first, [(900.0, 500.0, 300.0)])
    _mark_crowded(second, [(500.0, 500.0, 300.0)])
    return scene, first, second


@pytest.mark.parametrize("zoom", [0.25, 0.6, 1.5])
@pytest.mark.parametrize("rotation", [0.0, 37.0])
def test_a_spacing_warning_fills_nothing(crowded, zoom: float, rotation: float) -> None:
    scene, first, second = crowded
    first._apply_rotation(rotation)
    image = _render(scene, zoom)
    # inside the first tree's spacing circle, clear of both footprints and of
    # every ring: bare plan. Master painted the translucent red disc here.
    for point in [(500.0, 700.0), (350.0, 500.0), (500.0, 320.0), (600.0, 650.0)]:
        assert _is_background(image, scene, zoom, *point), point
    # inside the lens where the two circles overlap: bare plan too
    assert _is_background(image, scene, zoom, 700.0, 560.0)


@pytest.mark.parametrize("zoom", [0.25, 0.6, 1.5])
@pytest.mark.parametrize("rotation", [0.0, 37.0, 215.0])
def test_the_warning_is_drawn_where_the_circles_overlap_only(
    crowded, zoom: float, rotation: float
) -> None:
    scene, first, _second = crowded
    first._apply_rotation(rotation)
    image = _render(scene, zoom)
    # the first tree's ring at 30 degrees: inside the neighbour's circle -> marked
    assert not _is_background(image, scene, zoom, *_ON_RING_IN_LENS)
    # ...and (200, 500): its far side, where nothing is crowded -> not marked
    assert _is_background(image, scene, zoom, 200.0, 500.0)
    assert _is_background(image, scene, zoom, 500.0, 800.0)


def test_a_plant_with_fine_spacing_draws_no_ring_until_it_is_selected(qtbot) -> None:
    scene = CanvasScene(1600, 1000)
    scene.set_shadows_enabled(False)
    tree = _tree(scene, 800.0, 500.0, 100.0, 600.0)
    tree.set_spacing_overlap("ideal")
    assert _is_background(_render(scene, 0.6), scene, 0.6, 1100.0, 500.0)
    assert tree.boundingRect().width() < 300.0      # no ring, no inflated repaint region

    tree.setSelected(True)
    image = _render(scene, 0.6)
    assert not _is_background(image, scene, 0.6, 1100.0, 500.0)   # the whole ring, as an aid
    assert not _is_background(image, scene, 0.6, 500.0, 500.0)
    assert _is_background(image, scene, 0.6, 950.0, 500.0)        # and still no fill


def test_the_selected_crowded_plant_shows_its_whole_ring(crowded) -> None:
    scene, first, _second = crowded
    first.setSelected(True)
    image = _render(scene, 0.6)
    assert not _is_background(image, scene, 0.6, 200.0, 500.0)
    assert not _is_background(image, scene, 0.6, *_ON_RING_IN_LENS)


def test_the_toggle_hides_the_warning(crowded) -> None:
    scene, _first, _second = crowded
    assert not _is_background(_render(scene, 0.6), scene, 0.6, *_ON_RING_IN_LENS)
    scene.set_spacing_circles_visible(False)
    assert _is_background(_render(scene, 0.6), scene, 0.6, *_ON_RING_IN_LENS)


def test_a_moved_plant_redraws_its_mark_although_its_neighbour_did_not_move(crowded) -> None:
    """The arcs face the neighbour; a cached item is not repainted by a move."""
    scene, first, _second = crowded
    first.setPos(0.0, 200.0)                       # now at (500, 700)
    revisions: list[int] = []
    first.update = lambda *_a, **_k: revisions.append(1)  # type: ignore[method-assign]
    first.set_spacing_overlap("overlap", [(900.0, 500.0, 300.0)])
    assert revisions, "the same neighbour from a new place must repaint the plant"
    revisions.clear()
    first.set_spacing_overlap("overlap", [(900.0, 500.0, 300.0)])
    assert not revisions, "an unchanged state must stay silent (idle scene, #305)"


# --------------------------------------------------------------------------
# Every diagnostic decoration stays out of a picture of the plan
# --------------------------------------------------------------------------


def _decorated_scene() -> tuple[CanvasScene, dict[str, object]]:
    from open_garden_planner.ui.canvas.items.garden_item import GuildBadgeItem, SunBadgeItem

    scene = CanvasScene(2000, 1200)
    scene.set_shadows_enabled(False)
    items: dict[str, object] = {}
    first = _tree(scene, 400.0, 600.0, 100.0, 600.0)
    second = _tree(scene, 800.0, 600.0, 100.0, 600.0)
    first.set_spacing_overlap("overlap", [(800.0, 600.0, 300.0)])
    second.set_spacing_overlap("overlap", [(400.0, 600.0, 300.0)])
    items["spacing"] = first
    first.set_antagonist_warning(True)
    second.set_companion_highlight("antagonistic")
    bed = RectangleItem(1200, 200, 300, 200, object_type=ObjectType.GARDEN_BED, name="")
    scene.addItem(bed)
    bed._soil_mismatch_level = "critical"
    bed.set_rotation_status("violation")
    items["bed"] = bed
    polygon_bed = PolygonItem(
        [QPointF(1200, 700), QPointF(1500, 700), QPointF(1500, 900), QPointF(1200, 900)],
        object_type=ObjectType.GARDEN_BED,
    )
    scene.addItem(polygon_bed)
    polygon_bed._soil_mismatch_level = "warning"
    polygon_bed.set_rotation_status("suboptimal")
    pot = CircleItem(1700.0, 600.0, 60.0, object_type=ObjectType.CONTAINER_ROUND)
    scene.addItem(pot)
    pot.set_capacity_overrun(True)
    planter = RectangleItem(1600, 900, 200, 100, object_type=ObjectType.CONTAINER)
    scene.addItem(planter)
    planter.set_capacity_overrun(True)
    sun = SunBadgeItem(second)
    from PyQt6.QtGui import QPixmap

    picture = QPixmap(24, 24)
    picture.fill(QColor("orange"))
    sun.setPixmap(picture)
    sun.setPos(second.rect().center())
    guild = GuildBadgeItem(-8, -8, 16, 16, first)
    guild.setBrush(QColor("#e3a234"))
    guild.setPos(first.rect().center())
    items["sun"], items["guild"] = sun, guild
    return scene, items


def _clear_decorations(scene: CanvasScene, items: dict[str, object]) -> None:
    for item in scene.items():
        if hasattr(item, "set_spacing_overlap"):
            item.set_spacing_overlap(None)
            item.set_antagonist_warning(False)
            item.set_companion_highlight(None)
            item.set_rotation_status(None)
            item.set_capacity_overrun(False)
            item._soil_mismatch_level = None
            item.update()
    items["sun"].setVisible(False)       # type: ignore[attr-defined]
    items["guild"].setVisible(False)     # type: ignore[attr-defined]


def test_the_canvas_shows_every_decoration_and_an_export_shows_none(qtbot) -> None:
    scene, items = _decorated_scene()
    on_canvas = _render(scene, 0.5)
    exported = _render(scene, 0.5, export=True)
    _clear_decorations(scene, items)
    bare = _render(scene, 0.5)

    assert _changed_share(on_canvas, bare, threshold=24) > 0.001   # they are painted...
    assert _changed_share(exported, bare, threshold=0) == 0.0      # ...and not exported


def _set_every_diagnostic_flag(item: object, on: bool) -> None:
    """Raise (or clear) every diagnostic flag a garden item can paint."""
    item.set_spacing_overlap("overlap" if on else None)       # type: ignore[attr-defined]
    item.set_antagonist_warning(on)                           # type: ignore[attr-defined]
    item.set_companion_highlight("antagonistic" if on else None)  # type: ignore[attr-defined]
    item.set_rotation_status("violation" if on else None)     # type: ignore[attr-defined]
    item.set_capacity_overrun(on)                             # type: ignore[attr-defined]
    item._soil_mismatch_level = "critical" if on else None    # type: ignore[attr-defined]
    item.update()                                             # type: ignore[attr-defined]


@pytest.mark.parametrize("factory,_supports_grid,supports_soil", BED_SHAPES)
def test_no_plant_parent_shape_carries_a_decoration_into_an_export(
    factory, _supports_grid: bool, supports_soil: bool, qtbot
) -> None:
    """The export seam holds for every shape of the bed gate (section 8.14, ADR-017).

    Bed features were twice shipped on some of the four bed shapes only. The
    decorations are painted from three places (the mixin, the rectangle, the
    polygon), so the same mistake is possible here: a shape that paints a
    border or a badge without asking ``_diagnostics_painted``. The shapes are
    the bed gate's own list, so a shape added there is checked here too.
    """
    scene = CanvasScene(600, 400)
    scene.set_shadows_enabled(False)
    item = factory()
    scene.addItem(item)
    item.setPos(250.0, 170.0)
    _set_every_diagnostic_flag(item, True)
    assert item.has_diagnostic_decoration()

    on_canvas = _render(scene, 1.0)
    exported = _render(scene, 1.0, export=True)
    _set_every_diagnostic_flag(item, False)
    bare = _render(scene, 1.0)

    assert _changed_share(exported, bare, threshold=0) == 0.0
    if supports_soil:      # every soil-capable shape paints the soil border at least
        assert _changed_share(on_canvas, bare, threshold=24) > 0.0


def test_the_seam_switches_the_painted_decorations_off_and_on_again(qtbot) -> None:
    scene, items = _decorated_scene()
    assert scene.diagnostic_overlays_visible

    hidden, selection = ExportService._hide_overlay_items(scene)
    assert not scene.diagnostic_overlays_visible
    assert not items["sun"].isVisible() and not items["guild"].isVisible()  # type: ignore[attr-defined]
    # the diagnostics themselves are untouched: only what is painted changes
    assert items["spacing"].spacing_overlap == "overlap"                    # type: ignore[attr-defined]
    assert items["bed"].soil_mismatch_level == "critical"                   # type: ignore[attr-defined]

    ExportService._restore_overlay_items(hidden, selection)
    assert scene.diagnostic_overlays_visible
    assert items["sun"].isVisible() and items["guild"].isVisible()          # type: ignore[attr-defined]


def test_a_nested_export_leaves_the_decorations_on_afterwards(qtbot) -> None:
    """Print holds the seam while its dialog is open; a preview export runs inside it."""
    scene, _items = _decorated_scene()
    outer = ExportService._hide_overlay_items(scene)
    inner = ExportService._hide_overlay_items(scene)
    ExportService._restore_overlay_items(*inner)
    assert not scene.diagnostic_overlays_visible, "the outer holder still wants them off"
    ExportService._restore_overlay_items(*outer)
    assert scene.diagnostic_overlays_visible


def test_switching_the_decorations_does_not_touch_the_plan(qtbot) -> None:
    scene, _items = _decorated_scene()
    revision = scene.plan_revision
    scene.set_diagnostic_overlays_visible(False)
    scene.set_diagnostic_overlays_visible(True)
    assert scene.plan_revision == revision


@pytest.mark.parametrize("fmt", ["svg", "pdf"])
def test_the_vector_and_report_paths_use_the_same_seam(qtbot, tmp_path, monkeypatch, fmt) -> None:
    scene, _items = _decorated_scene()
    seen: list[bool] = []
    original = scene.render

    def spy(*args, **kwargs):
        seen.append(scene.diagnostic_overlays_visible)
        return original(*args, **kwargs)

    monkeypatch.setattr(scene, "render", spy)
    if fmt == "svg":
        ExportService.export_to_svg(scene, tmp_path / "plan.svg")
    else:
        from open_garden_planner.services import pdf_report_service

        pdf_report_service._scene_to_image(scene, scene.canvas_rect, QRectF(0, 0, 400, 240))
    assert seen and not any(seen), "the scene was rendered with its decorations on"
    assert scene.diagnostic_overlays_visible
