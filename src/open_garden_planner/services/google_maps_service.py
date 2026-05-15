"""Google Maps Static API client with Web-Mercator tile math.

Fetches a satellite background image for a given lat/lng bounding box and
returns it together with the pixel→meters scale derived analytically from
the Web-Mercator projection. For boxes too large to fit in a single
640x640 Static-Maps call (scale=2 → 1280x1280 effective pixels), the
service automatically stitches a 2x2 / 3x3 grid of sub-calls with Pillow.

The API key is read from the ``OGP_GOOGLE_MAPS_KEY`` environment variable
(loaded from ``.env`` at app startup in ``main.py``). It is intentionally
never bundled into the installer — any binary distributing the key could
be reverse-engineered and the key abused. See ADR-019.
"""

from __future__ import annotations

import io
import math
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from PIL import Image

_STATIC_MAPS_URL = "https://maps.googleapis.com/maps/api/staticmap"
_EARTH_CIRCUMFERENCE_M = 2 * math.pi * 6378137.0
# Static Maps free tier: 640x640 per call, scale=2 → 1280x1280 effective.
# Note on units: ``scale`` ONLY doubles the output pixels; the geographic
# area covered by one call stays ``_TILE_BASE_PX * standard_mpp`` (where
# standard_mpp is ``meters_per_pixel(lat, zoom)``). The effective mpp of
# the returned image is therefore ``standard_mpp / _TILE_SCALE``.
_TILE_BASE_PX = 640
_TILE_SCALE = 2
_TILE_EFFECTIVE_PX = _TILE_BASE_PX * _TILE_SCALE  # 1280, output dimensions
# Max grid we'll auto-stitch; beyond this resolution is overkill and call
# budgets get uncomfortable.
_MAX_GRID = 3
_ENV_VAR = "OGP_GOOGLE_MAPS_KEY"


class GoogleMapsKeyMissingError(RuntimeError):
    """Raised when the API key env var is not set."""


class GoogleMapsFetchError(RuntimeError):
    """Raised when Static Maps returns a non-200 or invalid image."""


class FetchCancelled(GoogleMapsFetchError):
    """Raised when a mosaic fetch is cancelled mid-flight by the caller."""


@dataclass(frozen=True)
class BoundingBox:
    """A geographic bounding box in WGS84 (lat/lng degrees)."""

    nw_lat: float
    nw_lng: float
    se_lat: float
    se_lng: float

    @property
    def center(self) -> tuple[float, float]:
        return (
            (self.nw_lat + self.se_lat) / 2.0,
            (self.nw_lng + self.se_lng) / 2.0,
        )


@dataclass(frozen=True)
class FetchResult:
    """Output of a successful satellite fetch."""

    image: Image.Image
    meters_per_pixel: float
    zoom: int
    bbox: BoundingBox
    tile_grid: tuple[int, int]  # (cols, rows) — (1,1) means single call


def has_api_key() -> bool:
    """True iff the API key env var is set and non-empty."""
    return bool(os.environ.get(_ENV_VAR, "").strip())


def get_api_key() -> str:
    """Return the API key or raise if missing. Strip whitespace."""
    key = os.environ.get(_ENV_VAR, "").strip()
    if not key:
        raise GoogleMapsKeyMissingError(
            f"Environment variable {_ENV_VAR} is not set. "
            "Put it in your project .env file."
        )
    return key


def meters_per_pixel(lat: float, zoom: int) -> float:
    """Web-Mercator ground resolution at the given latitude and zoom.

    See https://wiki.openstreetmap.org/wiki/Slippy_map_tilenames#Resolution_and_Scale
    """
    return (math.cos(math.radians(lat)) * _EARTH_CIRCUMFERENCE_M) / (
        256.0 * (2**zoom)
    )


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in meters between two lat/lng points."""
    radius = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def bbox_size_m(bbox: BoundingBox) -> tuple[float, float]:
    """Approximate width/height of a bounding box in meters."""
    center_lat, _ = bbox.center
    width = haversine_distance_m(center_lat, bbox.nw_lng, center_lat, bbox.se_lng)
    height = haversine_distance_m(bbox.nw_lat, bbox.nw_lng, bbox.se_lat, bbox.nw_lng)
    return width, height


def pick_zoom_and_grid(bbox: BoundingBox) -> tuple[int, int, int]:
    """Choose max zoom + minimal mosaic grid that covers ``bbox``.

    Strategy: prefer the highest possible zoom (best resolution) and pay for
    extra tiles when the bbox is too large for a single Static Maps call.
    Caps at zoom 20 (Static Maps satellite limit) and a 3x3 grid (9 calls,
    enough for very large gardens at meaningful resolution).

    Returns ``(zoom, cols, rows)``. One call covers ``_TILE_BASE_PX *
    standard_mpp`` meters wide; ``scale=2`` only doubles the OUTPUT pixels.
    """
    width_m, height_m = bbox_size_m(bbox)
    center_lat, _ = bbox.center

    for zoom in range(20, 0, -1):
        mpp = meters_per_pixel(center_lat, zoom)
        # Coverage of one Static Maps call (scale=2 doesn't change coverage).
        call_span_m = _TILE_BASE_PX * mpp
        cols = max(1, math.ceil(width_m / call_span_m))
        rows = max(1, math.ceil(height_m / call_span_m))
        if cols <= _MAX_GRID and rows <= _MAX_GRID:
            return zoom, cols, rows

    # Fallback: lowest zoom + max grid (only hits for absurdly large bboxes).
    return 1, _MAX_GRID, _MAX_GRID


def _build_static_url(
    center_lat: float,
    center_lng: float,
    zoom: int,
    size_px: int,
    api_key: str,
) -> str:
    """Build a Static Maps URL. Side-effect-free, safe to test."""
    params = {
        "center": f"{center_lat},{center_lng}",
        "zoom": str(zoom),
        "size": f"{size_px}x{size_px}",
        "scale": str(_TILE_SCALE),
        "maptype": "satellite",
        "format": "png",
        "key": api_key,
    }
    return f"{_STATIC_MAPS_URL}?{urlencode(params)}"


def _scrub_key(text: str, api_key: str) -> str:
    """Remove the API key (and any ``key=…`` query param) from a string.

    Used on anything we hand back via exceptions — `requests` exceptions
    stringify with the full request URL, and Google can echo the URL in
    its error bodies. Either path would leak the key into logs / dialogs.
    """
    scrubbed = text.replace(api_key, "[REDACTED]") if api_key else text
    return re.sub(r"key=[^&\s\"']+", "key=[REDACTED]", scrubbed)


def _fetch_tile(
    center_lat: float,
    center_lng: float,
    zoom: int,
    api_key: str,
    *,
    timeout: float = 10.0,
) -> Image.Image:
    """HTTP-fetch a single Static Maps tile and return as PIL Image.

    Raises ``GoogleMapsFetchError`` on non-200 or invalid response. The
    API key is scrubbed from every error message before raising.
    """
    url = _build_static_url(center_lat, center_lng, zoom, _TILE_BASE_PX, api_key)
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as e:
        raise GoogleMapsFetchError(
            f"Network error: {_scrub_key(str(e), api_key)}"
        ) from None
    if response.status_code != 200:
        body = _scrub_key(response.text[:200], api_key)
        raise GoogleMapsFetchError(
            f"Static Maps returned HTTP {response.status_code}: {body}"
        )
    try:
        return Image.open(io.BytesIO(response.content)).convert("RGB")
    except Exception as e:
        raise GoogleMapsFetchError(
            f"Invalid image response: {_scrub_key(str(e), api_key)}"
        ) from None


def _crop_to_bbox(
    image: Image.Image, mpp: float, bbox: BoundingBox
) -> Image.Image:
    """Crop the centred satellite image down to exactly the bbox area.

    Static Maps returns ``size × size`` pixels centred on ``(lat, lng)`` at a
    given zoom — there's no native bbox parameter. So the fetched image
    (single tile or stitched mosaic) covers more ground than the user's
    rectangle, with padding on all sides. Cropping to the bbox makes the
    canvas-placed image match the rectangle the user drew.

    ``mpp`` is unchanged by cropping (pixels-per-metre is intrinsic to the
    zoom level + latitude, not the image size).
    """
    bbox_w_m, bbox_h_m = bbox_size_m(bbox)
    img_w, img_h = image.size
    crop_w = max(1, min(img_w, round(bbox_w_m / mpp)))
    crop_h = max(1, min(img_h, round(bbox_h_m / mpp)))
    left = (img_w - crop_w) // 2
    top = (img_h - crop_h) // 2
    return image.crop((left, top, left + crop_w, top + crop_h))


def fetch_bbox(
    bbox: BoundingBox,
    *,
    api_key: str | None = None,
    timeout: float = 10.0,
    cancel_check: Callable[[], bool] | None = None,
) -> FetchResult:
    """Fetch a satellite image covering ``bbox``.

    Picks the zoom level + tile grid that maximises resolution while fitting
    the entire bbox. Single Static-Maps call for small boxes; stitched
    mosaic for larger ones. The returned image is cropped to exactly the
    bbox dimensions so the canvas-placed image matches what the user drew.

    ``cancel_check`` — if given, is polled between tiles. When it returns
    True, the fetch raises ``FetchCancelled`` rather than continuing.
    """
    if api_key is None:
        api_key = get_api_key()

    zoom, cols, rows = pick_zoom_and_grid(bbox)
    center_lat, center_lng = bbox.center
    standard_mpp = meters_per_pixel(center_lat, zoom)
    # One Static Maps call covers _TILE_BASE_PX * standard_mpp meters and
    # returns _TILE_EFFECTIVE_PX pixels because of scale=2 → the output's
    # actual mpp is standard_mpp / _TILE_SCALE. Crop math and consumers
    # (BackgroundImageItem auto-scale) must use this output_mpp.
    output_mpp = standard_mpp / _TILE_SCALE
    call_span_m = _TILE_BASE_PX * standard_mpp  # ground covered per call

    if cols == 1 and rows == 1:
        raw = _fetch_tile(center_lat, center_lng, zoom, api_key, timeout=timeout)
        return FetchResult(
            image=_crop_to_bbox(raw, output_mpp, bbox),
            meters_per_pixel=output_mpp,
            zoom=zoom,
            bbox=bbox,
            tile_grid=(1, 1),
        )

    mosaic = Image.new("RGB", (cols * _TILE_EFFECTIVE_PX, rows * _TILE_EFFECTIVE_PX))
    deg_per_m_lat = 1.0 / 111320.0
    deg_per_m_lng = 1.0 / (111320.0 * max(math.cos(math.radians(center_lat)), 1e-6))
    tile_dlat = call_span_m * deg_per_m_lat
    tile_dlng = call_span_m * deg_per_m_lng

    for row in range(rows):
        for col in range(cols):
            if cancel_check is not None and cancel_check():
                raise FetchCancelled("Fetch cancelled by caller")
            offset_x = col - (cols - 1) / 2.0
            offset_y = (rows - 1) / 2.0 - row  # row 0 is at the top → +lat
            tile_lat = center_lat + offset_y * tile_dlat
            tile_lng = center_lng + offset_x * tile_dlng
            tile_img = _fetch_tile(
                tile_lat, tile_lng, zoom, api_key, timeout=timeout
            )
            mosaic.paste(
                tile_img,
                (col * _TILE_EFFECTIVE_PX, row * _TILE_EFFECTIVE_PX),
            )

    return FetchResult(
        image=_crop_to_bbox(mosaic, output_mpp, bbox),
        meters_per_pixel=output_mpp,
        zoom=zoom,
        bbox=bbox,
        tile_grid=(cols, rows),
    )
