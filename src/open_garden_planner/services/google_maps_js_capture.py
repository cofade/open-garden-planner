"""JavaScript-API view capture support for the satellite import (issue #346).

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
"""

from __future__ import annotations

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


def pick_capture_zoom(
    bbox: BoundingBox,
    viewport_css_wh: tuple[float, float],
    *,
    margin: float = _VIEWPORT_MARGIN,
) -> int:
    """Highest integer zoom (≤ 20) whose ground coverage fits ``bbox`` in
    the viewport with a safety margin. Returns ``_MIN_ZOOM`` when nothing
    fits — the crop path degrades gracefully for absurdly large boxes."""
    width_m, height_m = bbox_size_m(bbox)
    center_lat, _ = bbox.center
    view_w, view_h = (max(v, 1.0) for v in viewport_css_wh)
    for zoom in range(_MAX_ZOOM, _MIN_ZOOM - 1, -1):
        mpp = meters_per_pixel(center_lat, zoom)
        if width_m <= view_w * mpp * margin and height_m <= view_h * mpp * margin:
            return zoom
    return _MIN_ZOOM


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
