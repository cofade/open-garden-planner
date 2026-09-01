"""Unit tests for :mod:`open_garden_planner.services.google_maps_js_capture`.

Qt-free module — no ``qtbot``/QApplication needed. Covers the EEA 403
classifier, the capture scale math, zoom selection, the attribution bake,
the blank-render detector and the shared crop seam.
"""

from __future__ import annotations

import pytest
from PIL import Image

from open_garden_planner.services import google_maps_js_capture as cap
from open_garden_planner.services import google_maps_service as gms

_EEA_BODY = (
    "Your request cannot be served because satellite and hybrid map types "
    "are not available for your account and region. Learn more here: "
    "https://developers.google.com/maps/comms/eea/maps-static."
)
_WORKER_EEA_MESSAGE = f"Static Maps returned HTTP 403: {_EEA_BODY}"


class TestClassifyStaticFailure:
    def test_eea_body_with_status(self) -> None:
        assert cap.classify_static_failure(403, _EEA_BODY) == cap.EEA_SATELLITE_BLOCKED

    def test_eea_body_message_only(self) -> None:
        # The picker worker scrubs the status code; classification must also
        # work on the worker's full message text.
        assert (
            cap.classify_static_failure(None, _WORKER_EEA_MESSAGE)
            == cap.EEA_SATELLITE_BLOCKED
        )

    def test_generic_403_is_not_eea(self) -> None:
        assert cap.classify_static_failure(403, "REQUEST_DENIED") == cap.HTTP_403

    def test_generic_403_message_only(self) -> None:
        assert (
            cap.classify_static_failure(None, "Static Maps returned HTTP 403: REQUEST_DENIED")
            == cap.HTTP_403
        )

    def test_other_failures(self) -> None:
        assert cap.classify_static_failure(500, "boom") == cap.OTHER_FAILURE
        assert cap.classify_static_failure(None, "Network error") == cap.OTHER_FAILURE
        assert cap.classify_static_failure(None, "") == cap.OTHER_FAILURE

    def test_marker_alone_without_403_is_not_eea(self) -> None:
        assert (
            cap.classify_static_failure(500, _EEA_BODY) == cap.OTHER_FAILURE
        )
        assert cap.classify_static_failure(None, _EEA_BODY) == cap.OTHER_FAILURE

    def test_case_insensitive(self) -> None:
        assert (
            cap.classify_static_failure(403, _EEA_BODY.upper())
            == cap.EEA_SATELLITE_BLOCKED
        )


class TestCaptureMpp:
    def test_equals_mpp_divided_by_dpr(self) -> None:
        lat, zoom = 52.52, 19
        assert cap.capture_mpp(lat, zoom, 1.0) == pytest.approx(
            gms.meters_per_pixel(lat, zoom), rel=1e-12
        )
        assert cap.capture_mpp(lat, zoom, 2.0) == pytest.approx(
            gms.meters_per_pixel(lat, zoom) / 2.0, rel=1e-12
        )

    def test_fractional_dpr(self) -> None:
        # Verified in the #346 spike: at 125% scaling the page dpr is 1.25
        # and the grab is exactly css × 1.25 physical pixels.
        lat, zoom = 52.52, 19
        assert cap.capture_mpp(lat, zoom, 1.25) == pytest.approx(
            gms.meters_per_pixel(lat, zoom) / 1.25, rel=1e-12
        )

    @pytest.mark.parametrize("dpr", [0.0, -1.0, -2.5])
    def test_rejects_non_positive_dpr(self, dpr: float) -> None:
        with pytest.raises(ValueError):
            cap.capture_mpp(52.52, 19, dpr)


class TestPickCaptureZoom:
    # Berlin-sized box: ~135 m EW × ~222 m NS at lat 52.52.
    BERLIN = gms.BoundingBox(52.521, 13.404, 52.519, 13.406)

    def test_small_box_fits_at_high_zoom(self) -> None:
        zoom = cap.pick_capture_zoom(self.BERLIN, (1000.0, 700.0))
        # z18 coverage: 1000×0.3634×0.85 = 309 m EW, 700×0.3634×0.85 = 216 m NS
        # → the 222 m box does NOT fit z18; z17 does. This pins the margin math.
        assert zoom == 17

    def test_margin_shrinks_coverage(self) -> None:
        tight = cap.pick_capture_zoom(self.BERLIN, (1000.0, 700.0), margin=1.0)
        relaxed = cap.pick_capture_zoom(self.BERLIN, (1000.0, 700.0), margin=0.5)
        assert tight >= relaxed

    def test_monotonic_with_viewport(self) -> None:
        small = cap.pick_capture_zoom(self.BERLIN, (300.0, 200.0))
        large = cap.pick_capture_zoom(self.BERLIN, (1000.0, 700.0))
        assert small <= large

    def test_huge_box_floors_at_min_zoom(self) -> None:
        # Construct a box deliberately wider than what zoom 1 covers in a
        # (1000, 700) viewport with the default margin — the loop must fall
        # through to the floor. Self-consistent against the live constants.
        import math

        center_lat = 50.0
        z1_coverage_w = 1000.0 * cap._VIEWPORT_MARGIN * gms.meters_per_pixel(center_lat, 1)
        width_m = 1.05 * z1_coverage_w
        height_m = 0.5 * width_m
        d_lat = height_m / 111320.0
        d_lng = width_m / (111320.0 * max(math.cos(math.radians(center_lat)), 1e-6))
        huge = gms.BoundingBox(
            nw_lat=center_lat + d_lat / 2,
            nw_lng=-d_lng / 2,
            se_lat=center_lat - d_lat / 2,
            se_lng=d_lng / 2,
        )
        assert cap.pick_capture_zoom(huge, (1000.0, 700.0)) == 1

    def test_never_exceeds_twenty(self) -> None:
        tiny = gms.BoundingBox(52.5201, 13.4051, 52.52005, 13.4052)
        assert cap.pick_capture_zoom(tiny, (1000.0, 700.0)) <= 20


class TestBakeAttribution:
    def test_keeps_dimensions(self) -> None:
        img = Image.new("RGB", (320, 200), (20, 90, 30))
        out = cap.bake_attribution(img, "Map data ©2026 Google")
        assert out.size == img.size

    def test_does_not_mutate_input(self) -> None:
        img = Image.new("RGB", (320, 200), (20, 90, 30))
        before = img.getpixel((0, 0))
        cap.bake_attribution(img, "Map data ©2026 Google")
        assert img.getpixel((0, 0)) == before
        assert img.mode == "RGB"

    def test_strip_darkens_bottom_rows(self) -> None:
        img = Image.new("RGB", (320, 200), (255, 255, 255))
        out = cap.bake_attribution(img, "Map data ©2026 Google")
        # Bottom pixel sits inside the translucent black bar; top does not.
        assert out.getpixel((10, 199))[0] < 200
        assert out.getpixel((10, 10)) == (255, 255, 255)

    def test_text_pixels_present(self) -> None:
        img = Image.new("RGB", (320, 200), (0, 0, 0))
        out = cap.bake_attribution(img, "Map data ©2026 Google")
        bottom_row = [out.getpixel((x, 191)) for x in range(320)]
        assert any(pixel[0] > 180 for pixel in bottom_row)

    def test_empty_text_is_a_clean_copy(self) -> None:
        img = Image.new("RGB", (320, 200), (120, 120, 120))
        out = cap.bake_attribution(img, "")
        assert out.size == img.size
        assert out.getpixel((10, 10)) == (120, 120, 120)
        assert out.getpixel((10, 199)) == (120, 120, 120)


class TestBlankCapture:
    def test_solid_color_is_blank(self) -> None:
        assert cap.is_blank_capture(Image.new("RGB", (100, 100), (232, 234, 237))) is True

    def test_gradient_is_not_blank(self) -> None:
        img = Image.new("RGB", (100, 100))
        for x in range(100):
            for y in range(100):
                img.putpixel((x, y), (x, y, (x + y) % 255))
        assert cap.is_blank_capture(img) is False

    def test_noise_is_not_blank(self) -> None:
        import random

        rng = random.Random(42)
        img = Image.new("RGB", (100, 100))
        img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(100 * 100)])
        assert cap.is_blank_capture(img) is False


class TestSharedCropSeam:
    def test_crop_matches_static_behavior(self) -> None:
        """The JS-capture path crops through the promoted Static helper —
        one seam, one behavior (drift guard)."""
        bbox = gms.BoundingBox(52.521, 13.404, 52.519, 13.406)
        mpp = 0.5
        img = Image.new("RGB", (2000, 2000), (30, 60, 90))
        out = gms.crop_image_to_bbox(img, mpp, bbox)
        bbox_w_m, bbox_h_m = gms.bbox_size_m(bbox)
        assert abs(out.size[0] - round(bbox_w_m / mpp)) <= 1
        assert abs(out.size[1] - round(bbox_h_m / mpp)) <= 1
        assert out.size[0] < img.size[0]
        assert out.size[1] < img.size[1]
