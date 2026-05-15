"""Tests for :mod:`open_garden_planner.services.google_maps_service`.

Covers the pure pieces (tile math, URL building, mosaic decision) plus a
mocked end-to-end ``fetch_bbox`` path. No real HTTP is performed.
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from PIL import Image

from open_garden_planner.services import google_maps_service as gms


class TestMetersPerPixel:
    """Web-Mercator ground resolution at the equator and higher latitudes."""

    def test_equator_zoom_0(self) -> None:
        assert gms.meters_per_pixel(0.0, 0) == pytest.approx(156543.0, rel=1e-3)

    def test_equator_zoom_19(self) -> None:
        assert gms.meters_per_pixel(0.0, 19) == pytest.approx(0.2985, rel=1e-2)

    def test_higher_latitude_smaller_mpp(self) -> None:
        # Mercator stretches near the poles, so meters-per-pixel SHRINKS as
        # latitude goes up: cos(60°) = 0.5 → exactly half the equator value.
        eq = gms.meters_per_pixel(0.0, 18)
        n60 = gms.meters_per_pixel(60.0, 18)
        assert n60 == pytest.approx(eq * 0.5, rel=1e-3)

    def test_doubles_per_zoom_step(self) -> None:
        a = gms.meters_per_pixel(48.0, 17)
        b = gms.meters_per_pixel(48.0, 18)
        assert a == pytest.approx(b * 2, rel=1e-6)


class TestHaversine:
    def test_zero_distance(self) -> None:
        assert gms.haversine_distance_m(52.0, 13.0, 52.0, 13.0) == pytest.approx(0.0)

    def test_known_distance(self) -> None:
        d = gms.haversine_distance_m(0.0, 0.0, 1.0, 0.0)
        assert d == pytest.approx(111_195, rel=1e-3)


class TestBboxAndZoomPicking:
    def test_small_box_single_tile(self) -> None:
        bbox = gms.BoundingBox(
            nw_lat=52.5200, nw_lng=13.4050,
            se_lat=52.5197, se_lng=13.4056,
        )
        width, height = gms.bbox_size_m(bbox)
        assert 20 < width < 80
        assert 20 < height < 80
        zoom, cols, rows = gms.pick_zoom_and_grid(bbox)
        assert (cols, rows) == (1, 1)
        assert 18 <= zoom <= 20

    def test_medium_box_grid(self) -> None:
        bbox = gms.BoundingBox(
            nw_lat=52.5300, nw_lng=13.4000,
            se_lat=52.5246, se_lng=13.4090,
        )
        zoom, cols, rows = gms.pick_zoom_and_grid(bbox)
        assert cols >= 2 and rows >= 2

    def test_caps_at_max_grid(self) -> None:
        bbox = gms.BoundingBox(
            nw_lat=53.0, nw_lng=13.0,
            se_lat=52.0, se_lng=14.0,
        )
        _, cols, rows = gms.pick_zoom_and_grid(bbox)
        assert cols <= 3 and rows <= 3


class TestUrlBuilding:
    def test_contains_all_params(self) -> None:
        # urlencode percent-encodes the comma in `center=lat,lng` — both
        # forms are valid in Static Maps URLs.
        url = gms._build_static_url(52.0, 13.0, 18, 640, "TEST_KEY")
        assert url.startswith("https://maps.googleapis.com/maps/api/staticmap?")
        for needle in ("center=52.0%2C13.0", "zoom=18", "size=640x640",
                       "scale=2", "maptype=satellite", "format=png",
                       "key=TEST_KEY"):
            assert needle in url, f"missing {needle}"

    def test_unsafe_chars_in_key_are_encoded(self) -> None:
        # Defends against keys containing ampersand / equals breaking the URL.
        url = gms._build_static_url(0.0, 0.0, 1, 10, "weird&key=foo")
        assert "key=weird%26key%3Dfoo" in url


class TestApiKeyHandling:
    def test_get_api_key_strips_whitespace(self, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "  abc123 \n")
        assert gms.get_api_key() == "abc123"
        assert gms.has_api_key() is True

    def test_get_api_key_raises_when_missing(self, monkeypatch) -> None:
        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        assert gms.has_api_key() is False
        with pytest.raises(gms.GoogleMapsKeyMissingError):
            gms.get_api_key()

    def test_empty_key_is_missing(self, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "   ")
        assert gms.has_api_key() is False


def _make_png_bytes(
    color: tuple[int, int, int], size: tuple[int, int] = (1280, 1280)
) -> bytes:
    """Build a synthetic PNG for HTTP-mock returns. Defaults to 1280×1280
    to match what Static Maps returns at ``scale=2``."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestFetchBbox:
    def test_single_call_when_bbox_small(self, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        bbox = gms.BoundingBox(
            nw_lat=52.5200, nw_lng=13.4050,
            se_lat=52.5197, se_lng=13.4056,
        )
        png = _make_png_bytes((128, 200, 128))
        with patch.object(gms, "requests") as mock_requests:
            mock_requests.get.return_value.status_code = 200
            mock_requests.get.return_value.content = png
            mock_requests.RequestException = Exception
            result = gms.fetch_bbox(bbox)
        assert mock_requests.get.call_count == 1
        assert result.tile_grid == (1, 1)
        # Image is cropped to the bbox — its pixel size is the bbox extent
        # divided by mpp. Just check it's a positive non-zero rectangle.
        assert result.image.size[0] > 0
        assert result.image.size[1] > 0
        assert result.meters_per_pixel > 0

    def test_mosaic_path_makes_multiple_calls(self, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        bbox = gms.BoundingBox(
            nw_lat=52.5300, nw_lng=13.4000,
            se_lat=52.5246, se_lng=13.4090,
        )
        png = _make_png_bytes((50, 50, 50))
        with patch.object(gms, "requests") as mock_requests:
            mock_requests.get.return_value.status_code = 200
            mock_requests.get.return_value.content = png
            mock_requests.RequestException = Exception
            result = gms.fetch_bbox(bbox)
        cols, rows = result.tile_grid
        assert cols * rows == mock_requests.get.call_count
        assert cols >= 2 and rows >= 2

    def test_network_error_does_not_leak_api_key(self, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "SECRET_KEY_AIza_xxxx")
        bbox = gms.BoundingBox(
            nw_lat=52.5200, nw_lng=13.4050,
            se_lat=52.5197, se_lng=13.4056,
        )

        class _BoomingException(Exception):
            def __str__(self) -> str:
                return (
                    "HTTPSConnectionPool host='maps.googleapis.com' "
                    "url=/maps/api/staticmap?center=52.5,13.4&key=SECRET_KEY_AIza_xxxx"
                )

        with patch.object(gms, "requests") as mock_requests:
            mock_requests.RequestException = _BoomingException
            mock_requests.get.side_effect = _BoomingException()
            with pytest.raises(gms.GoogleMapsFetchError) as ei:
                gms.fetch_bbox(bbox)
        msg = str(ei.value)
        assert "SECRET_KEY_AIza_xxxx" not in msg
        assert "[REDACTED]" in msg

    def test_http_body_does_not_leak_api_key(self, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "SECRET_KEY_AIza_xxxx")
        bbox = gms.BoundingBox(
            nw_lat=52.5200, nw_lng=13.4050,
            se_lat=52.5197, se_lng=13.4056,
        )
        with patch.object(gms, "requests") as mock_requests:
            mock_requests.get.return_value.status_code = 403
            mock_requests.get.return_value.text = (
                "API key SECRET_KEY_AIza_xxxx is not authorized for this API"
            )
            mock_requests.RequestException = Exception
            with pytest.raises(gms.GoogleMapsFetchError) as ei:
                gms.fetch_bbox(bbox)
        assert "SECRET_KEY_AIza_xxxx" not in str(ei.value)

    def test_http_error_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        bbox = gms.BoundingBox(
            nw_lat=52.5200, nw_lng=13.4050,
            se_lat=52.5197, se_lng=13.4056,
        )
        with patch.object(gms, "requests") as mock_requests:
            mock_requests.get.return_value.status_code = 403
            mock_requests.get.return_value.text = "REQUEST_DENIED"
            mock_requests.RequestException = Exception
            with pytest.raises(gms.GoogleMapsFetchError):
                gms.fetch_bbox(bbox)

    def test_returned_mpp_is_scale_2_output(self, monkeypatch) -> None:
        """``scale=2`` doubles output pixels without changing ground coverage,
        so the *output* image's mpp is ``meters_per_pixel(...) / _TILE_SCALE``.
        Consumers (BackgroundImageItem) read this directly to set canvas scale.
        """
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        bbox = gms.BoundingBox(
            nw_lat=52.5200, nw_lng=13.4050,
            se_lat=52.5197, se_lng=13.4056,
        )
        png = _make_png_bytes((0, 0, 0))
        with patch.object(gms, "requests") as mock_requests:
            mock_requests.get.return_value.status_code = 200
            mock_requests.get.return_value.content = png
            mock_requests.RequestException = Exception
            result = gms.fetch_bbox(bbox)
        standard_mpp = gms.meters_per_pixel(bbox.center[0], result.zoom)
        expected_mpp = standard_mpp / gms._TILE_SCALE
        assert result.meters_per_pixel == pytest.approx(expected_mpp, rel=1e-9)

    def test_image_is_cropped_to_bbox_dimensions(self, monkeypatch) -> None:
        """The returned image should match bbox_w/bbox_h * output_mpp, not
        the raw tile."""
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        bbox = gms.BoundingBox(
            nw_lat=52.5200, nw_lng=13.4050,
            se_lat=52.5197, se_lng=13.4056,
        )
        png = _make_png_bytes((0, 0, 0))
        with patch.object(gms, "requests") as mock_requests:
            mock_requests.get.return_value.status_code = 200
            mock_requests.get.return_value.content = png
            mock_requests.RequestException = Exception
            result = gms.fetch_bbox(bbox)
        bbox_w_m, bbox_h_m = gms.bbox_size_m(bbox)
        expected_w = round(bbox_w_m / result.meters_per_pixel)
        expected_h = round(bbox_h_m / result.meters_per_pixel)
        assert abs(result.image.size[0] - expected_w) <= 1
        assert abs(result.image.size[1] - expected_h) <= 1
        # And critically: SMALLER than the raw 1280×1280 mock, proving the
        # crop happened.
        assert result.image.size[0] < 1280
        assert result.image.size[1] < 1280

    def test_cancel_check_aborts_mosaic(self, monkeypatch) -> None:
        """Setting cancel_check to a True-returning callable raises FetchCancelled."""
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        # Large bbox forces a mosaic path where cancel_check is consulted.
        bbox = gms.BoundingBox(
            nw_lat=52.5300, nw_lng=13.4000,
            se_lat=52.5246, se_lng=13.4090,
        )
        with patch.object(gms, "requests") as mock_requests:
            mock_requests.RequestException = Exception
            with pytest.raises(gms.FetchCancelled):
                gms.fetch_bbox(bbox, cancel_check=lambda: True)
        # No tile fetched because cancel is checked before the first call.
        assert mock_requests.get.call_count == 0
