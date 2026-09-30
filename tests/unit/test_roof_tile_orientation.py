"""Unit tests for HOUSE roof-tile orientation (issue #372).

The roof-tile texture has an intrinsic, non-negotiable direction. Each tile's
rounded free edge points ``+Y`` of the texture and each tile laps the tile
below it -- measured from the texture itself: a dark lapse line near ``y=10``,
then the light rounded free edge filling the rows beneath. That direction is
down-slope, and it is the direction water runs. A tile that laps the wrong way
is not a cosmetic difference; water runs back up under the laps.

``PolygonItem._paint_with_ridge`` splits the polygon into two halves along the
ridge and fills one with the texture and one with a mirrored copy. The halves
were assigned to brushes by ``_split_path_by_line``'s *arbitrary* left/right
naming, which follows the ridge's **direction**, not which side is downhill, so
the half that needed the texture's true down-slope was the one being mirrored.

The arithmetic behind the fix: ``normal_tx`` is ``translate(mid).rotate(angle)``
and a ``QBrush`` transform samples the texture at ``T^-1.p``, so the texture's
``+Y`` lands in the world at ``R(angle).(0,1) = (-sin a, cos a)`` -- exactly the
left-perpendicular ``(-uy, ux)`` that ``_split_path_by_line`` offsets
``left_path`` along. ``left_path`` is therefore the half the down-slope points
*into*, and it is the half that must keep the NORMAL brush.

How this file is built, and why
-------------------------------
These tests drive the **production** ``_paint_with_ridge`` and read what it
painted, because an earlier version of this file re-derived the brush
construction inside the test and therefore passed unchanged with the fix fully
reverted -- it asserted facts about test-local code, not about the app.

The probe is a two-colour pixmap (RED on its top half, BLUE on its bottom)
installed as the **item's own brush**, so ``_paint_with_ridge`` consumes it
through ``self.brush()`` exactly as it consumes the real texture. BLUE then
*is* the texture's down-slope.

Three instruments were tried and rejected before this one:

* Correlating the real 256 px tile texture against the render had **no
  discriminating power** (peak ~0.03 either way; the diagonal case a
  0.020-vs-0.019 coin flip) -- a few hundred sampled pixels span barely one
  texture period.
* Counting RED vs BLUE over a *patch* was also blind: the probe tiles, so a
  patch always comes out near 50/50 regardless of direction.
* A harness that called ``scene.removeItem(ridge)`` and one that ran the ridge
  points through ``house.mapToScene`` were both silently measuring the wrong
  thing; see the notes on ``_render`` and ``_ridge_axis``.

What works is sampling a **single pixel at a series of distances** outward from
the ridge and reading the resulting colour *sequence*. The probe tiles, so one
pixel is ambiguous -- but the phase of the sequence is not. Measured, sweeping
every 15 degrees from 0 to 345 on both landscape and portrait houses:

    fixed     R B B R B B      pre-fix:  B R R B R R

on **both** halves, identically at **every** angle and **both** aspect ratios.
The pre-fix code put the phase the wrong way round on both halves, so the laps
pointed back toward the ridge.

The angle-independence is the point, not a convenience: the defect was never
angle-specific -- it tracked *which half got the mirror*, and the swap is exact
in the brush's own frame. An earlier draft of this file excluded 90 and 270
degrees on the claim that "the ridge then runs along the sample axis and every
sample lands in one phase". That claim was an artifact of the
``_ridge_axis`` double-rotation bug below; with it fixed, 90 and 270 are as
informative as any other angle.

One thing the sweep could *not* do, and a second bug this file also contained:
sweeping the house's **rotation** never varies the angle that
``normal_tx.rotate()`` receives. That angle is the ridge's direction in the
polygon's **local** frame, which ``compute_roof_ridge_endpoints`` pins to the
longest bounding-box axis -- 0 for a landscape house at every rotation, 90 for a
portrait one at every rotation (measured by spying on the value). Since
``rotate(-a)`` and ``rotate(+a)`` are the same transform when ``a`` is 0, a
rotation-only sweep cannot tell a negated sign from a correct one, and the
"swap, not a probe" argument rests on that sign. So the cases span both
geometries; see ``HOUSE_CASES``.
"""

# ruff: noqa: ARG002

import math

import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints
from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem

#: The test cases, as ``(house_w, house_h, rotation)``.
#:
#: These are **two independent dimensions**, and conflating them is what made an
#: earlier version of this file weaker than it looked. ``rotation`` is the
#: house item's own transform. The angle that ``_paint_with_ridge`` actually
#: feeds to ``normal_tx.rotate()`` is a *different* thing: the ridge's angle in
#: the polygon's **local** frame, which ``compute_roof_ridge_endpoints`` fixes
#: to the longest bounding-box axis. For a landscape house that is 0 at every
#: rotation; for a **portrait** house it is 90 at every rotation.
#:
#: This matters because ``rotate(-angle)`` and ``rotate(+angle)`` are identical
#: when the angle is 0. Measured with the ``rotate`` sign negated: a landscape
#: house still reads ``RBBRBB`` at every rotation -- the mutant is completely
#: invisible -- while a portrait house reads ``BRRBRR`` and is caught. So the
#: portrait cases are what pin the sign, and the "swap, not a probe" argument in
#: ADR-046 rests on that sign. Sweeping rotation alone would leave the single
#: term the argument depends on untested.
HOUSE_CASE_VALUES = (
    (400.0, 250.0, 0.0),  # landscape, local ridge angle 0
    (400.0, 250.0, 45.0),
    (400.0, 250.0, 90.0),
    (250.0, 400.0, 0.0),  # portrait, local ridge angle 90
    (250.0, 400.0, 45.0),
    (250.0, 400.0, 90.0),
    (250.0, 400.0, 180.0),
    (300.0, 300.0, 30.0),  # square: width >= height, so local angle 0
)

HOUSE_CASES = [
    pytest.param(w, h, r, id=f"{'landscape' if w > h else ('square' if w == h else 'portrait')}_rot{int(r)}")
    for w, h, r in HOUSE_CASE_VALUES
]

#: Probe colours. The texture's ``+Y`` -- its down-slope -- is BLUE.
DOWN_SLOPE = "#0000ff"
UP_SLOPE = "#ff0000"

#: Sample distances (cm) from the ridge midpoint, along the ridge's
#: left-perpendicular. The first distance clears the ridge's painted body
#: (three hardcoded pens up to 8.0 wide, i.e. a 4.0 half-width, plus ``r=4``
#: end caps and antialiasing) at every angle. The ridge is hidden outright by
#: ``_render``, and that suppression was verified *not* to be load-bearing --
#: deleting it leaves all cases passing -- so this margin is belt-and-braces,
#: and it also means no case depends on the decoration's stroke width.
#:
#: The deepest distance (120) must stay inside the half-width of the narrower
#: dimension: for a portrait house the samples run horizontally, so 120 has to
#: fit inside 250/2 = 125. That margin is thin, so ``_is_informative`` rejects
#: any sequence containing ``?`` rather than letting a run-off-the-roof sample
#: pass.
SAMPLE_DISTANCES = (20, 40, 60, 80, 100, 120)

RENDER_WIDTH = 400


def _probe_pixmap() -> QPixmap:
    """Two-colour probe: RED on the texture's top half, BLUE on its bottom."""
    pm = QPixmap(64, 64)
    p = QPainter(pm)
    p.fillRect(0, 0, 64, 32, QColor(255, 0, 0))
    p.fillRect(0, 32, 64, 32, QColor(0, 0, 255))
    p.end()
    return pm


def _house_with_probe(
    rotation: float, house_w: float, house_h: float
) -> tuple[QGraphicsScene, PolygonItem]:
    """A HOUSE carrying the probe as its own brush, with a linked ridge.

    ``_paint_with_ridge`` reads ``self.brush()``, so installing the probe here
    means the production code transforms it exactly as it transforms the real
    texture -- no test-local copy of the brush construction.

    ``house._apply_rotation`` is the production entry point, and it calls
    ``_update_ridge_on_boundary``, so the ridge is re-derived into the rotated
    frame by the app's own code rather than by the test.
    """
    scene = QGraphicsScene()
    house = PolygonItem(
        [
            QPointF(0.0, 0.0),
            QPointF(house_w, 0.0),
            QPointF(house_w, house_h),
            QPointF(0.0, house_h),
        ],
        object_type=ObjectType.HOUSE,
    )
    house.setPos(0.0, 0.0)
    house.setBrush(QBrush(_probe_pixmap()))

    p1, p2 = compute_roof_ridge_endpoints(house.polygon(), house.pos())
    ridge = PolylineItem([p1, p2], object_type=ObjectType.ROOF_RIDGE)
    house.set_metadata("ridge_item_id", str(ridge.item_id))
    ridge.set_metadata("owner_polygon_id", str(house.item_id))
    scene.addItem(house)
    scene.addItem(ridge)

    if rotation:
        house.setTransformOriginPoint(house.polygon().boundingRect().center())
        house._apply_rotation(rotation)
    return scene, house


def _render(scene: QGraphicsScene, house: PolygonItem) -> QImage:
    """Render through Qt's real pipeline, preserving the house's aspect ratio.

    Aspect matters: ``scene.render`` into a fixed square stretches the scene
    rect, which moved the sampled points off the roof entirely in an earlier
    draft of this file.

    The ridge is **hidden, never removed**, and it is hidden with
    ``setVisible(False)``. Both halves of that are load-bearing, and both were
    got wrong in earlier drafts of this file:

    * ``scene.removeItem(ridge)`` makes ``_find_ridge()`` return ``None``, and
      ``_paint_with_ridge`` is only reached when it returns a ridge -- so every
      render measured ``super().paint()``, the fallback fill that the fixed and
      the unfixed code share. The images hashed byte-identical and the fix
      looked like a no-op, when it is not.
    * ``ridge.setPen(QPen(Qt.PenStyle.NoPen))`` does **not** hide it.
      ``PolylineItem._paint_roof_ridge`` never reads ``self.pen()``; it strokes
      three hardcoded pens (widths 8.0 / 5.5 / 1.8) plus ``r=4`` end-cap
      ellipses, and the ridge is stacked above the house. So that version left
      the ridge painting over its own sample points while its docstring
      asserted a suppression that never happened.

    ``_find_ridge`` does not filter on visibility, and ``scene.render`` skips
    invisible items -- so ``setVisible(False)`` suppresses the decoration while
    leaving the production paint path intact.
    """
    ridge = house._find_ridge()
    assert ridge is not None, (
        "the linked ridge must stay in the scene: _paint_with_ridge only runs "
        "when _find_ridge() returns it"
    )
    ridge.setVisible(False)

    bounds = house.sceneBoundingRect()
    height = int(round(RENDER_WIDTH * bounds.height() / bounds.width()))
    img = QImage(RENDER_WIDTH, height, QImage.Format.Format_ARGB32)
    img.fill(QColor(255, 255, 255, 255))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scene.render(p, QRectF(0.0, 0.0, float(RENDER_WIDTH), float(height)), bounds)
    p.end()
    return img


def _ridge_axis(house: PolygonItem) -> tuple[float, float, float, float]:
    """Ridge midpoint and its left-perpendicular, in scene coordinates.

    Since #364 the ridge points are already **scene** space:
    ``_update_ridge_on_boundary`` recomputes them through
    ``compute_roof_ridge_endpoints`` in the polygon's local frame and maps the
    result out, and ``_apply_rotation`` calls it. So the only mapping applied
    here is the ridge's own -- an earlier draft also ran the points through
    ``house.mapToScene``, which rotated them a second time and made the
    harness sample 30 degrees off the real ridge normal at 30 degrees of
    rotation. That single bug produced a phantom "degenerate" band at 90 and
    270 degrees and wrong readings at every other rotation except 0.
    """
    ridge = house._find_ridge()
    assert ridge is not None, "the HOUSE has no linked ridge"
    a = ridge.mapToScene(ridge.points[0])
    b = ridge.mapToScene(ridge.points[-1])
    mid_x = (a.x() + b.x()) / 2.0
    mid_y = (a.y() + b.y()) / 2.0
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    assert length > 1e-9, "degenerate ridge"
    return mid_x, mid_y, -dy / length, dx / length


def _outward_sequence(
    img: QImage,
    house: PolygonItem,
    axis: tuple[float, float, float, float],
    along_positive_n: bool,
) -> str:
    """Colour sequence walking OUTWARD from the ridge along ``+-n``.

    ``n = (-uy, ux)`` is the ridge's left-perpendicular, the direction
    ``_split_path_by_line`` offsets ``left_path`` along. Returns a string of
    ``R``/``B``/``?`` (white or off-roof), one character per sample distance.
    """
    mid_x, mid_y, nx, ny = axis
    if not along_positive_n:
        nx, ny = -nx, -ny

    bounds = house.sceneBoundingRect()
    out: list[str] = []
    for d in SAMPLE_DISTANCES:
        sample = QPointF(mid_x + nx * d, mid_y + ny * d)
        ix = int((sample.x() - bounds.left()) / bounds.width() * img.width())
        iy = int((sample.y() - bounds.top()) / bounds.height() * img.height())
        if not (0 <= ix < img.width() and 0 <= iy < img.height()):
            out.append("?")
            continue
        colour = QColor(img.pixel(ix, iy)).name()
        out.append("B" if colour == DOWN_SLOPE else ("R" if colour == UP_SLOPE else "?"))
    return "".join(out)


def _is_informative(sequence: str) -> bool:
    """Did the samples actually land on the roof and straddle a probe phase?

    Without this, a degenerate sequence compares equal to itself and makes a
    mirror assertion pass for free. Two ways to be degenerate, both reachable:
    ``??????`` when the samples run off the roof (the deepest sample is 120 cm
    against a half-width of 125 for a portrait house -- a thin margin), and
    ``RRRRRR`` when they all land inside one phase. So require no ``?`` at all,
    and both colours present.
    """
    return "?" not in sequence and "R" in sequence and "B" in sequence


def _is_mirror_pair(plus: str, minus: str) -> bool:
    """Do the two halves read the same, informative, outward sequence?

    A correct roof's two halves are mirror images across the ridge, so walking
    outward from it on either side meets the same tile phase in the same order.
    This is a property of the *split*, and it holds before and after the fix --
    so it is asserted separately, and that is what makes it useful: it
    attributes a failure of the orientation test to the brush *assignment*
    rather than to the split.

    Requiring both halves to be informative is what stops the comparison
    passing vacuously; the informativeness is also asserted on its own, so a
    failure says *which* of the two things went wrong.
    """
    return _is_informative(plus) and _is_informative(minus) and plus == minus


def _phase_runs_outward(sequence: str) -> bool:
    """Does the down-slope phase arrive as we walk away from the ridge?

    The probe tiles, so a single character says nothing about direction -- the
    phase depends on where the samples happen to land. What is unambiguous is
    the **first transition**: walking outward from the ridge, the RED
    (up-slope) band must come before the BLUE (down-slope) band, because the
    texture's own ``+Y`` points outward.

    This is the assertion that separates the two builds, measured through the
    production paint path:

        fixed    +n RBBRBB   -n RBBRBB     (first transition R->B)
        pre-fix  +n BRRBRR   -n BRRBRR     (first transition B->R)

    Both are mirror-symmetric -- the split is unchanged by the fix -- so a
    half-vs-half comparison cannot tell them apart. Only the absolute phase
    can, which is why this looks at the first transition and not at the pair.
    """
    if not _is_informative(sequence):
        return False
    return sequence.index("B") > sequence.index("R")


def _both_sequences(rotation: float, house_w: float, house_h: float) -> tuple[str, str]:
    scene, house = _house_with_probe(rotation, house_w, house_h)
    axis = _ridge_axis(house)
    img = _render(scene, house)
    return (
        _outward_sequence(img, house, axis, True),
        _outward_sequence(img, house, axis, False),
    )


@pytest.mark.parametrize(("house_w", "house_h", "rotation"), HOUSE_CASES)
def test_tiles_lap_away_from_the_ridge(
    house_w: float, house_h: float, rotation: float, qtbot: object
) -> None:
    """Both halves must run down-slope *outward*, in every orientation.

    Driving the production ``_paint_with_ridge``: reverting the fix (giving
    ``left_path`` the mirrored brush) reverses the phase on both halves,
    ``RBBRBB`` becoming ``BRRBRR``. Negating the ``rotate`` sign is caught by
    the portrait cases only -- see ``HOUSE_CASES``.
    """
    plus, minus = _both_sequences(rotation, house_w, house_h)

    assert _is_informative(plus) and _is_informative(minus), (
        f"{house_w:.0f}x{house_h:.0f} at {rotation} deg: samples were not "
        f"informative ({plus!r} / {minus!r}); the house, render size or "
        "sample distances changed"
    )
    assert _phase_runs_outward(plus), (
        f"{house_w:.0f}x{house_h:.0f} at {rotation} deg: the +n half laps "
        f"TOWARD the ridge (sequence {plus!r}); water would run uphill under "
        "the laps"
    )
    assert _phase_runs_outward(minus), (
        f"{house_w:.0f}x{house_h:.0f} at {rotation} deg: the -n half laps "
        f"TOWARD the ridge (sequence {minus!r})"
    )


def test_both_halves_are_mirror_images(qtbot: object) -> None:
    """A correct roof's two halves read the same outward sequence.

    The two halves are mirror images across the ridge, so walking outward from
    it on either side encounters the same tile phase. This holds both before
    and after the fix -- it is a property of the *split*, not of the
    assignment -- and is asserted separately so that a failure of
    ``test_tiles_lap_away_from_the_ridge`` can be attributed to the assignment
    rather than to the split.

    ``_is_informative`` requires the sequences to be informative, so a sample
    point that strayed off the roof fails here rather than passing vacuously.
    """
    for house_w, house_h, rotation in HOUSE_CASE_VALUES:
        plus, minus = _both_sequences(rotation, house_w, house_h)
        assert _is_informative(plus) and _is_informative(minus), (
            f"{house_w:.0f}x{house_h:.0f} at {rotation} deg: samples were not "
            f"informative ({plus!r} / {minus!r})"
        )
        assert _is_mirror_pair(plus, minus), (
            f"{house_w:.0f}x{house_h:.0f} at {rotation} deg: halves disagree "
            f"({plus!r} vs {minus!r}), so the split itself is wrong rather than "
            "the brush assignment"
        )


def test_the_roof_is_actually_painted_at_the_sample_points(qtbot: object) -> None:
    """Guard against a blank or unprobed canvas making the above vacuous."""
    scene, house = _house_with_probe(0.0, 400.0, 250.0)
    axis = _ridge_axis(house)
    img = _render(scene, house)
    plus = _outward_sequence(img, house, axis, True)
    minus = _outward_sequence(img, house, axis, False)
    for name, seq in (("+n", plus), ("-n", minus)):
        assert "?" not in seq, (
            f"{name}: some samples landed off the roof or on bare canvas "
            f"(sequence {seq!r}); the test house or render size changed"
        )
        assert _is_informative(seq), (
            f"{name}: probe colours absent (sequence {seq!r}); the probe "
            "brush is not reaching _paint_with_ridge"
        )


def test_probe_orientation_is_what_the_test_assumes(qtbot: object) -> None:
    """The probe's BLUE half must be its ``+Y``, or every assertion inverts.

    A pixmap's row 0 is its top, i.e. its lowest ``-Y``. This asserts that
    directly so a future change to the probe cannot silently reverse the
    meaning of every other test in this file.
    """
    pm = _probe_pixmap()
    image = pm.toImage()
    top = QColor(image.pixel(32, 8)).name()
    bottom = QColor(image.pixel(32, 56)).name()
    assert top == UP_SLOPE, f"probe top should be up-slope, got {top}"
    assert bottom == DOWN_SLOPE, f"probe bottom should be down-slope, got {bottom}"
