"""JavaScript-API view capture support for the satellite import (#346, #347).

For projects affected by Google's EEA restrictions the Static Maps API
rejects ``satellite``/``hybrid`` requests with HTTP 403 ("not available for
your account and region"). The documented alternative is the Maps
JavaScript API — which has no export endpoint. The sanctioned capture path
(ADR-019 addendum #346) is therefore: the embedded picker *displays* the
map through the JS API exactly as rendered, the application captures those
pixels at the ``QWebEngineView`` level (``QWidget.grab()`` — no DOM access,
no tile scraping, no cross-origin canvas tricks), and the image is scaled
and cropped with the same analytic Web-Mercator math the Static path has
always used.

Issue #347 extends that single capture to a **pan grid**: the page pans the
map across a ``cols × rows`` grid of viewport positions at the same integer
zoom, Python grabs every frame, and stitches them — mirroring the Static
mosaic (which caps at 3x3). The Math in this module is the basis of both
the single-frame and the pan-grid choreography; the dialog runs one engine.

This module is Qt-free: it holds the pure math and image helpers so they
are unit-testable without a QApplication.

Measured facts behind the design (spike for #346):

- Google's satellite tile responses carry **no** ``Access-Control-Allow-
  Origin`` header and tile ``<img>`` elements **taint** a ``<canvas>`` —
  the html2canvas approach fails with a ``SecurityError`` on
  ``getImageData`` inside QtWebEngine 6.10. Widget-level grab is the only
  capture surface that works and it never sees the DOM (tile URLs embed
  the API key; keep them out of Python entirely).
- ``QWebEngineView.grab()`` returns real pixels at exactly
  ``css_size × devicePixelRatio``; verified at dpr 1.0 and 1.25.
- The analytic ``meters_per_pixel`` formula holds for integer zooms in the
  JS map (verified against ``map.getBounds()`` to ~0.03%).
- Subclassing ``QWebEnginePage`` to capture console messages hard-crashed
  QtWebEngine (0xC0000409) — never do that in production code.

Seam-free stitch theory (ADR-019 addendum #347): satellite tiles at an
integer zoom are *deterministic world-pixel content*. If two successive
frame centers differ by a whole number of css/world pixels, both frames are
exact adjacent windows of the same world image rendered at the same
sub-pixel phase (the center's fractional part is identical), so adjacent
grabs are identical along their shared edge. ``build_frame_layout``
therefore places centers on a whole-css-pixel grid, and stitches exactly at
``step × dpr`` offsets. To keep those offsets integral in *physical*
(grabbed) pixels, steps are aligned to the denominator of the dpr fraction
(``step × dpr`` whole). The residual sub-pixel behaviour of Google's own
rasterizer is the one assumption validated on a real key (manual checklist).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from statistics import fmean

from PIL import Image, ImageDraw, ImageFont, ImageStat

from open_garden_planner.services.google_maps_service import (
    BoundingBox,
    bbox_size_m,
    meters_per_pixel,
)

_MAX_ZOOM = 20
_MIN_ZOOM = 1
# Fraction of the viewport (css px) the chosen bbox may use. Keeps a safety
# margin so rounding/dpr drift can never clip the drawn rectangle.
_VIEWPORT_MARGIN = 0.85
# Max grid we'll capture: parity with the Static mosaic's 3x3 cap (issue
# #347). One JS frame is a whole viewport re-render, so 9 frames is already
# a patient import; anything beyond buys little and risks long captures.
_MAX_CAPTURE_GRID = 3
# Per-frame retries before the whole capture errors out cleanly (issue #347).
FRAME_RETRIES = 2
# Padding (css px) the grid coverage must exceed the bbox by on each side,
# so the analytic final crop never engages its silent ``min()`` clamp.
# Sized past the worst ±1-px rounding windage: the layout steps round in
# css space while the crop size rounds in physical space, and those two
# roundings can disagree by a full pixel at dpr >= 2.
_COVERAGE_PAD_PX = 5.0

EEA_SATELLITE_BLOCKED = "eea_satellite_blocked"
HTTP_403 = "http_403"
OTHER_FAILURE = "other"

# Markers lifted from Google's canonical EEA 403 body (probed 2026-09):
# "Your request cannot be served because satellite and hybrid map types
# are not available for your account and region. Learn more here:
# https://developers.google.com/maps/comms/eea/maps-static."
_EEA_MARKERS = (
    "satellite and hybrid map types are not available",
    "not available for your account and region",
    "comms/eea",
)


def classify_static_failure(status_code: int | None, body: str) -> str:
    """Classify a Static-Maps failure into a coarse, honest category.

    Returns one of ``EEA_SATELLITE_BLOCKED``, ``HTTP_403``, or
    ``OTHER_FAILURE``. Google's own 403 body does the diagnosing; we only
    relay it — classification never invents a cause for non-matching
    failures.
    """
    body_lower = (body or "").lower()
    if status_code == 403:
        if any(marker in body_lower for marker in _EEA_MARKERS):
            return EEA_SATELLITE_BLOCKED
        return HTTP_403
    if status_code is None:
        # Message-only classification (the picker worker scrubs status).
        if "http 403" in body_lower and any(marker in body_lower for marker in _EEA_MARKERS):
            return EEA_SATELLITE_BLOCKED
        if "http 403" in body_lower:
            return HTTP_403
    return OTHER_FAILURE


def capture_mpp(lat: float, zoom: int, dpr: float) -> float:
    """Meters per *captured image* pixel for a JS-API view capture.

    The JS map draws ``meters_per_pixel(lat, zoom)`` metres per CSS pixel;
    the widget grab returns ``devicePixelRatio`` physical pixels per CSS
    pixel, exactly mirroring the role ``scale=2`` plays in the Static path
    (``output_mpp = standard_mpp / _TILE_SCALE``).
    """
    if dpr <= 0:
        raise ValueError(f"devicePixelRatio must be positive, got {dpr}")
    return meters_per_pixel(lat, zoom) / dpr


_DPR_MIN = 0.5
_DPR_MAX = 8.0  # generous: covers Windows custom scaling well beyond 400%


def effective_capture_dpr(grab_physical_width: int, css_width: float) -> float:
    """Physical pixels per CSS pixel of a widget grab — measured, not
    reported. The grab is the ruler; the page's own dpr claim is only a
    cross-check (issue #346)."""
    if css_width <= 0 or grab_physical_width <= 0:
        raise ValueError(
            f"capture dims must be positive, got {grab_physical_width}x{css_width}"
        )
    return grab_physical_width / float(css_width)


def capture_dpr_is_sane(effective: float, reported: float | None) -> bool:
    """Whether a measured capture density should be trusted.

    Refuses implausible densities and wild disagreement between the
    measured ruler and the page's report (integer rounding at fractional
    OS scales keeps normal drift far below the 30%/+0.5 tolerance — e.g.
    the project's 125% scaling measured 1250/1000 = 1.25 exactly).
    """
    if not (_DPR_MIN <= effective <= _DPR_MAX):
        return False
    if reported is None or reported <= 0:
        return True
    return abs(effective - float(reported)) <= max(0.5, 0.3 * float(reported))


def pick_capture_zoom_and_grid(
    bbox: BoundingBox,
    viewport_css_wh: tuple[float, float],
    *,
    max_grid: int = _MAX_CAPTURE_GRID,
    margin: float = _VIEWPORT_MARGIN,
) -> tuple[int, int, int]:
    """Highest integer zoom (≤ 20) whose per-frame coverage fits ``bbox``
    in a ``cols × rows ≤ max_grid`` pan grid, mirroring the Static path's
    ``pick_zoom_and_grid`` (one frame = one viewport, not one 640 px call).

    Returns ``(zoom, cols, rows)``. One frame covers ``viewport * mpp *
    margin`` meters; the margin keeps a safety edge so the analytic crop
    never clips the drawn rectangle. The captured resolution is then
    ``standard_mpp / dpr`` thanks to the widget grab (same role ``scale=2``
    plays in Static). Falls back to ``(_MIN_ZOOM, max_grid, max_grid)`` for
    absurdly large boxes.
    """
    width_m, height_m = bbox_size_m(bbox)
    center_lat, _ = bbox.center
    view_w, view_h = (max(v, 1.0) for v in viewport_css_wh)
    for zoom in range(_MAX_ZOOM, _MIN_ZOOM - 1, -1):
        mpp = meters_per_pixel(center_lat, zoom)
        cols = max(1, math.ceil(width_m / (view_w * mpp * margin)))
        rows = max(1, math.ceil(height_m / (view_h * mpp * margin)))
        if cols <= max_grid and rows <= max_grid:
            return zoom, cols, rows
    return _MIN_ZOOM, max_grid, max_grid


def pick_capture_zoom(
    bbox: BoundingBox,
    viewport_css_wh: tuple[float, float],
    *,
    margin: float = _VIEWPORT_MARGIN,
) -> int:
    """Single-frame zoom choice — the pan-grid picker with ``max_grid=1``
    (one engine, not a second; the dialog's single-frame flow is a 1x1
    grid).
    """
    zoom, _, _ = pick_capture_zoom_and_grid(
        bbox, viewport_css_wh, max_grid=1, margin=margin
    )
    return zoom


def world_px(lat: float, lng: float, zoom: int) -> tuple[float, float]:
    """Web-Mercator world pixel coordinates of a lat/lng at ``zoom``.

    The whole world maps to ``256 * 2**zoom`` pixels across; x grows east
    from −180°, y grows *south* from the top of the map (Google/OSM
    convention). These are exactly the CSS pixels the JS map paints at the
    given zoom, so a whole-number offset here is a whole-CSS-pixel pan.
    """
    size = 256 * (2**zoom)
    x = (lng + 180.0) / 360.0 * size
    phi = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(phi)) / math.pi) / 2.0 * size
    return x, y


def world_px_inverse(x: float, y: float, zoom: int) -> tuple[float, float]:
    """Inverse of :func:`world_px` — world pixels back to ``(lat, lng)``."""
    size = 256 * (2**zoom)
    lng = x * 360.0 / size - 180.0
    phi = math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / size)))
    return math.degrees(phi), lng


class CaptureLayoutError(ValueError):
    """Raised when a pan-grid layout/stitch is geometrically inconsistent.

    The dialog maps this to a clean user-facing failure — never a silently
    blank or wrongly scaled image.
    """


@dataclass(frozen=True)
class FrameLayout:
    """The analytically derived pan-grid for one capture.

    ``centers`` holds ``cols * rows`` ``(lat, lng)`` frame centers in
    row-major (NW) order; every center differs from its neighbours by a
    whole number of world/css pixels at ``zoom``, so adjacent grabs are
    exact adjacent windows of the same world image and stitch at whole
    ``step * dpr`` offsets without seams or overlap.
    """

    zoom: int
    cols: int
    rows: int
    dpr: float
    viewport_css_w: float
    viewport_css_h: float
    step_x_css: int
    step_y_css: int
    centers: tuple[tuple[float, float], ...]

    @property
    def frame_count(self) -> int:
        return self.cols * self.rows


def _dpr_step_multiple(dpr: float) -> int:
    """Smallest positive integer ``q`` with ``q * dpr`` an integer.

    Steps aligned to a multiple of ``q`` make the physical (grabbed)
    paste offsets ``step * dpr`` whole, so :func:`stitch_frames` never
    needs sub-pixel resampling. dpr 1.25 → 4, 1.5 → 2, 2.0 → 1, 1.0 → 1,
    1.6 → 5.
    """
    if dpr <= 0:
        raise ValueError(f"devicePixelRatio must be positive, got {dpr}")
    reduced = Fraction(dpr).limit_denominator(64)
    return max(1, reduced.denominator)


def _align_down(value: int, multiple: int) -> int:
    return value - value % multiple


def _align_up(value: int, multiple: int) -> int:
    return ((value + multiple - 1) // multiple) * multiple


def _frame_step(
    viewport_css: float, bbox_css_px: float, count: int, dpr: float
) -> int:
    """Whole-css-pixel pan step for the given grid axis.

    The coverage requirement is computed in PHYSICAL (grabbed) pixels —
    the same space ``stitch_frames``' coverage check and the final crop
    use — so the two can never disagree on rounding: the step covers
    ``round(bbox_css * dpr) + 2 * ceil(PAD * dpr)`` grabbed pixels per
    axis with ``(count - 1) * step + viewport``. Steps are aligned to the
    dpr fraction so ``step * dpr`` is a whole number of pixels.
    """
    if count <= 1:
        return 0
    view_int = max(1, int(viewport_css))
    q = _dpr_step_multiple(dpr)
    pad_px = math.ceil(_COVERAGE_PAD_PX * dpr)
    required_phys = round(bbox_css_px * dpr) + 2 * pad_px
    raw_css = max(1, math.ceil((required_phys / dpr - viewport_css) / (count - 1)))
    step = _align_up(raw_css, q)
    # A step wider than the frame itself means the grid is over-sized;
    # clamp just below the viewport (the final coverage check will still
    # refuse a genuinely too-small mosaic).
    max_step = _align_down(max(1, view_int - 1), q) or 1
    return max(1, min(step, max_step))


def build_frame_layout(
    bbox: BoundingBox,
    zoom: int,
    cols: int,
    rows: int,
    viewport_css_wh: tuple[float, float],
    dpr: float,
) -> FrameLayout:
    """Analytically derive the pan grid for ``bbox``.

    Frame (r, c) sits at the bbox centre plus ``(c - (cols-1)/2) * step``
    east and ``((rows-1)/2 - r) * step`` north in world pixels (row 0 is
    the NW corner), converted back to lat/lng via the exact inverse
    projection. The grid is symmetric about the bbox centre, so the
    stitched mosaic is centred on it and the shared
    ``crop_image_to_bbox`` seam applies unchanged.
    """
    if dpr <= 0:
        raise ValueError(f"devicePixelRatio must be positive, got {dpr}")
    if cols < 1 or rows < 1:
        raise ValueError(f"grid must be at least 1x1, got {cols}x{rows}")
    view_w, view_h = (max(v, 1.0) for v in viewport_css_wh)
    center_lat, center_lng = bbox.center
    mpp = meters_per_pixel(center_lat, zoom)
    bbox_w_m, bbox_h_m = bbox_size_m(bbox)
    # The step math does the physical-space rounding itself, matching the
    # final crop exactly (see _frame_step).
    step_x = _frame_step(view_w, bbox_w_m / mpp, cols, dpr)
    step_y = _frame_step(view_h, bbox_h_m / mpp, rows, dpr)
    cx, cy = world_px(center_lat, center_lng, zoom)
    centers: list[tuple[float, float]] = []
    for r in range(rows):
        for c in range(cols):
            fx = cx + (c - (cols - 1) / 2.0) * step_x
            # Row 0 is the NW corner: NORTH means a SMALLER world y
            # (Web-Mercator y grows south).
            fy = cy + (r - (rows - 1) / 2.0) * step_y
            centers.append(world_px_inverse(fx, fy, zoom))
    return FrameLayout(
        zoom=zoom,
        cols=cols,
        rows=rows,
        dpr=dpr,
        viewport_css_w=view_w,
        viewport_css_h=view_h,
        step_x_css=step_x,
        step_y_css=step_y,
        centers=tuple(centers),
    )


def stitch_frames(
    frames: Sequence[Image.Image], layout: FrameLayout, bbox: BoundingBox
) -> Image.Image:
    """Compose the pan-grid grabs into one mosaic centred on the bbox.

    Frame (r, c) is pasted at integer ``(c * step_x_css * dpr,
    r * step_y_css * dpr)`` offsets — whole physical pixels by
    construction — with the bbox centre landing exactly at the mosaic
    centre, so ``crop_image_to_bbox`` can crop it like any other
    centred image. Raises :class:`CaptureLayoutError` (never a silently
    blank region) when the mosaic cannot cover the bbox or the frames are
    inconsistent.
    """
    if len(frames) != layout.frame_count:
        raise CaptureLayoutError(
            f"expected {layout.frame_count} frames, got {len(frames)}"
        )
    dpr = layout.dpr
    sx = round(layout.step_x_css * dpr)
    sy = round(layout.step_y_css * dpr)
    view_w, view_h = frames[0].size
    if any(f.size != frames[0].size for f in frames[1:]):
        raise CaptureLayoutError("captured frames differ in size")
    width = (layout.cols - 1) * sx + view_w
    height = (layout.rows - 1) * sy + view_h
    if width <= 0 or height <= 0:
        raise CaptureLayoutError(f"degenerate mosaic size {width}x{height}")
    center_lat, _ = bbox.center
    mpp = meters_per_pixel(center_lat, layout.zoom) / dpr
    bbox_w_m, bbox_h_m = bbox_size_m(bbox)
    # The crop below must never clip: crop_image_to_bbox silently clamps
    # when the image is smaller than the bbox, which would hand the canvas
    # a wrongly scaled image. Refuse instead (clean error, never wrong).
    # Compare against the ROUNDED crop size (what the crop actually
    # produces), cushioned by the pad on each side — ceil'd so the pad
    # survives its own rounding.
    pad_px = math.ceil(_COVERAGE_PAD_PX * dpr)
    crop_w = round(bbox_w_m / mpp)
    crop_h = round(bbox_h_m / mpp)
    if crop_w + 2 * pad_px > width or crop_h + 2 * pad_px > height:
        raise CaptureLayoutError(
            f"mosaic {width}x{height} cannot cover bbox of "
            f"{crop_w}x{crop_h} px at zoom {layout.zoom}"
        )
    mosaic = Image.new("RGB", (width, height))
    for idx, frame in enumerate(frames):
        r, c = divmod(idx, layout.cols)
        mosaic.paste(frame, (c * sx, r * sy))
    return mosaic


def frame_quality_ok(
    image: Image.Image,
    *,
    cells: tuple[int, int] = (4, 4),
    min_cell_std: float = 1.0,
) -> bool:
    """Whether a grabbed frame is fully rendered imagery.

    The global stddev check (``is_blank_capture``) cannot see a *partly*
    loaded frame — a beige/white strip of unloaded tiles in a corner still
    has plenty of global variance. Splitting the frame into cells and
    requiring every cell to show texture catches the strip. A few uniform
    cells (open sea, snowfield) are tolerated — a refusal is always safe
    (the user just retries), matching ``is_blank_capture``'s documented
    trade-off.
    """
    gray = image.convert("L")
    w, h = gray.size
    cols, cell_rows = cells
    total = cols * cell_rows
    uniform = 0
    for r in range(cell_rows):
        for c in range(cols):
            box = (
                c * w // cols,
                r * h // cell_rows,
                (c + 1) * w // cols,
                (r + 1) * h // cell_rows,
            )
            stat = ImageStat.Stat(gray.crop(box))
            if not stat.stddev or fmean(stat.stddev) < min_cell_std:
                uniform += 1
    # A full blank strip of tiles is a whole row of cells (~25%); allow at
    # most one untextured cell below that, but refuse any larger dead area.
    return uniform <= max(1, total // 5)


def bake_attribution(image: Image.Image, text: str) -> Image.Image:
    """Bake a Google attribution strip into the bottom-left of the image.

    The widget grab captures Google's native on-map attribution, but the
    bbox crop usually cuts it away. To keep the stored artifact compliant
    with the attribution requirement (EEA ToS §3.2.4 / standard ToS), a
    small semi-opaque strip with the attribution line is drawn onto the
    final image. Returns a copy; the input is not mutated.
    """
    out = image.convert("RGB").copy()
    if not text:
        return out
    width, height = out.size
    bar_h = max(18, round(height * 0.03))
    try:
        font = ImageFont.load_default(size=max(10, round(bar_h * 0.55)))
    except TypeError:  # Pillow < 10.1: load_default takes no size
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(out, "RGBA")
    # Translucent black bar for legibility over any imagery.
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle((0, height - bar_h, width, height), fill=(0, 0, 0, 120))
    out = Image.alpha_composite(out.convert("RGBA"), overlay)
    # Re-measure the text for a light background so it reads on any tile.
    bbox = draw.textbbox((4, height - bar_h), text, font=font)
    text_h = bbox[3] - bbox[1]
    draw = ImageDraw.Draw(out)
    draw.text((6, height - bar_h + (bar_h - text_h) // 2), text, fill=(255, 255, 255, 255), font=font)
    return out.convert("RGB")


def is_blank_capture(image: Image.Image, *, min_std: float = 3.0) -> bool:
    """Treat a near-uniform capture as a failed render.

    A dead map (beige/white/grey page without tiles) renders an almost
    flat image; real satellite imagery never does. The standard deviation
    of the luminance channel is the cheap discriminator.

    Known trade-off: a genuinely uniform real scene (open sea, desert,
    snowfield) can fall under the threshold and be refused with the
    "did not render" message. The refusal is always safe (never a wrong
    scale) — the user just retries or picks a more varied area.
    """
    gray = image.convert("L")
    stat = ImageStat.Stat(gray)
    # ImageStat.stddev is population stddev of all pixels.
    if not stat.stddev:
        return True
    return fmean(stat.stddev) < min_std
