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


class TestCaptureDprSanity:
    def test_exact_ratio(self) -> None:
        assert cap.effective_capture_dpr(1250, 1000.0) == pytest.approx(1.25)

    def test_integer_rounding_stays_sane(self) -> None:
        # A 1.33-scale screen producing a 1-px-rounded grab must pass the
        # cross-check against the page's own report.
        eff = cap.effective_capture_dpr(1331, 1000.0)
        assert cap.capture_dpr_is_sane(eff, 1.33) is True

    def test_rejects_non_positive_dims(self) -> None:
        with pytest.raises(ValueError):
            cap.effective_capture_dpr(0, 1000.0)
        with pytest.raises(ValueError):
            cap.effective_capture_dpr(1000, 0.0)

    @pytest.mark.parametrize("eff", [0.2, 0.49, 8.5, 20.0])
    def test_implausible_densities_refused(self, eff: float) -> None:
        assert cap.capture_dpr_is_sane(eff, None) is False
        assert cap.capture_dpr_is_sane(eff, eff) is False

    def test_wild_report_disagreement_refused(self) -> None:
        # Measured 2.0 vs reported 1.0 — 100% drift must refuse, never
        # silently trust either number.
        assert cap.capture_dpr_is_sane(2.0, 1.0) is False
        assert cap.capture_dpr_is_sane(1.0, 2.0) is False

    def test_modest_disagreement_accepted(self) -> None:
        assert cap.capture_dpr_is_sane(1.24, 1.25) is True
        assert cap.capture_dpr_is_sane(1.25, None) is True
        assert cap.capture_dpr_is_sane(2.0, 1.7) is True

    def test_high_density_displays_accepted(self) -> None:
        # A 500%-scaled display is unusual but valid — must not be refused
        # as implausible.
        assert cap.capture_dpr_is_sane(5.0, 5.0) is True


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


class TestWorldPx:
    def test_round_trip_precision(self) -> None:
        """lat/lng -> world px -> lat/lng must be exact to float noise."""
        import math
        import random

        rng = random.Random(347)
        for zoom in (1, 8, 14, 18, 20):
            size = 256 * (2**zoom)
            for _ in range(25):
                x = rng.uniform(0, size)
                y = rng.uniform(0, size)
                lat, lng = cap.world_px_inverse(x, y, zoom)
                x2, y2 = cap.world_px(lat, lng, zoom)
                assert abs(lat) <= 85.05113  # mercator clipping latitude
                assert (lat - cap.world_px_inverse(x2, y2, zoom)[0]) < 1e-9
                assert abs(x2 - x) < 1e-6
                assert abs(y2 - y) < 1e-6
                # A whole-number world-pixel offset is a whole-number css
                # pan: the inverse of integer world px is the frame center.
                assert math.isfinite(lat) and math.isfinite(lng)

    def test_sign_convention(self) -> None:
        """x grows east from -180°, y grows SOUTH from the top."""
        x0, y0 = cap.world_px(0.0, 0.0, 10)
        x_east, _ = cap.world_px(0.0, 1.0, 10)
        x_west, _ = cap.world_px(0.0, -1.0, 10)
        _, y_north = cap.world_px(1.0, 0.0, 10)
        _, y_south = cap.world_px(-1.0, 0.0, 10)
        assert x_east > x0 > x_west
        assert y_north < y0 < y_south  # north = SMALLER y

    @pytest.mark.parametrize(
        "dpr,expected",
        [(1.0, 1), (1.25, 4), (1.5, 2), (2.0, 1), (1.6, 5), (5 / 3, 3)],
    )
    def test_step_multiple(self, dpr: float, expected: int) -> None:
        assert cap._dpr_step_multiple(dpr) == expected

    def test_whole_css_steps_keep_phase(self) -> None:
        """Frame centers differing by a whole css px keep the SAME
        fractional world-pixel phase — the seam-free rendering claim."""
        import random

        rng = random.Random(7)
        for _ in range(50):
            lat, lng = 50 + rng.random(), 10 + rng.random()
            zoom = 17
            cx, cy = cap.world_px(lat, lng, zoom)
            step = rng.randrange(50, 900)
            fx, _ = cap.world_px(*cap.world_px_inverse(cx + step, cy, zoom), zoom)
            assert abs((fx - cx) - step) < 1e-6
            assert abs((fx % 1) - (cx % 1)) < 1e-6  # same phase after pan


class TestPickCaptureZoomAndGrid:
    BERLIN = gms.BoundingBox(52.521, 13.404, 52.519, 13.406)

    def test_grid_1_reproduces_single_frame_pick(self) -> None:
        for viewport in ((1000.0, 700.0), (800.0, 600.0), (300.0, 200.0)):
            expected = cap.pick_capture_zoom(self.BERLIN, viewport)
            got = cap.pick_capture_zoom_and_grid(self.BERLIN, viewport, max_grid=1)
            assert got == (expected, 1, 1)

    def test_prefers_higher_zoom_over_fewer_frame_fine(
        self,
    ) -> None:
        """The grid cap (3x3) lets the picker zoom IN beyond what a single
        frame could cover — the resolution raise of issue #347."""
        zoom, cols, rows = cap.pick_capture_zoom_and_grid(self.BERLIN, (1000.0, 700.0))
        single = cap.pick_capture_zoom(self.BERLIN, (1000.0, 700.0))
        assert zoom > single
        assert cols * rows > 1
        assert cols <= 3 and rows <= 3

    def test_caps_at_max_grid(self) -> None:
        zoom, cols, rows = cap.pick_capture_zoom_and_grid(
            self.BERLIN, (1000.0, 700.0), max_grid=2
        )
        assert cols <= 2 and rows <= 2
        assert zoom < cap.pick_capture_zoom_and_grid(self.BERLIN, (1000.0, 700.0))[0]

    def test_global_box_never_exceeds_grid_cap(self) -> None:
        """The largest physically valid box (roughly half the planet) must
        still respect the 3x3 cap — the zoom-1 fallback exists only as a
        defensive safety net for degenerate inputs."""
        huge = gms.BoundingBox(
            nw_lat=80.0, nw_lng=-89.5, se_lat=20.0, se_lng=89.5
        )
        zoom, cols, rows = cap.pick_capture_zoom_and_grid(huge, (1000.0, 700.0))
        assert cap._MIN_ZOOM <= zoom <= cap._MAX_ZOOM
        assert cols <= 3 and rows <= 3

    def test_grid_size_monotonic_with_viewport(self) -> None:
        small = cap.pick_capture_zoom_and_grid(self.BERLIN, (300.0, 200.0))
        large = cap.pick_capture_zoom_and_grid(self.BERLIN, (1000.0, 700.0))
        assert small[0] <= large[0]


class TestFrameLayout:
    @pytest.mark.parametrize("dpr", [1.0, 1.25, 1.5, 2.0])
    def test_steps_are_whole_and_dpr_exact(self, dpr: float) -> None:
        """Steps are whole css px AND step*dpr is integral (the paste-offset
        exactness both the seam and the mosaic placement need)."""
        bbox = gms.BoundingBox(52.52135, 13.40205, 52.51865, 13.40795)
        layout = cap.build_frame_layout(bbox, 18, 2, 2, (1000.0, 700.0), dpr)
        assert layout.step_x_css > 0 and layout.step_y_css > 0
        assert (layout.step_x_css * dpr) % 1 < 1e-9
        assert (layout.step_y_css * dpr) % 1 < 1e-9

    def test_centers_symmetric_about_bbox_centre(self) -> None:
        bbox = gms.BoundingBox(52.52135, 13.40205, 52.51865, 13.40795)
        layout = cap.build_frame_layout(bbox, 18, 2, 2, (1000.0, 700.0), 1.0)
        cx, cy = cap.world_px(*bbox.center, layout.zoom)
        dx = [cap.world_px(*c, layout.zoom)[0] - cx for c in layout.centers]
        dy = [cap.world_px(*c, layout.zoom)[1] - cy for c in layout.centers]
        assert dx[0] == pytest.approx(-dx[1], abs=1e-6)
        assert dy[0] == pytest.approx(-dy[2], abs=1e-6)

    def test_coverage_never_clamps_crop(self) -> None:
        """Property: for random bboxes/grids the mosaic covers the bbox
        with the pad, so crop_image_to_bbox's silent min() never fires."""
        import random


        rng = random.Random(347)
        for _ in range(120):
            lat = rng.uniform(20.0, 65.0)
            lng = rng.uniform(-30.0, 30.0)
            w_m = rng.uniform(40.0, 1200.0)
            h_m = rng.uniform(40.0, 900.0)
            d_lng = w_m / (111320.0 * max(rng.uniform(0.5, 1.0), 0.3))
            d_lat = h_m / 111320.0
            bbox = gms.BoundingBox(
                nw_lat=lat + d_lat / 2,
                nw_lng=lng - d_lng / 2,
                se_lat=lat - d_lat / 2,
                se_lng=lng + d_lng / 2,
            )
            viewport = (rng.uniform(400, 1200), rng.uniform(300, 800))
            zoom, cols, rows = cap.pick_capture_zoom_and_grid(bbox, viewport)
            dpr = rng.choice([1.0, 1.25, 1.5, 2.0])
            layout = cap.build_frame_layout(bbox, zoom, cols, rows, viewport, dpr)
            frames = [
                Image.new("RGB", (int(viewport[0] * dpr), int(viewport[1] * dpr)), (0, 0, 0))
                for _ in range(layout.frame_count)
            ]
            mosaic = cap.stitch_frames(frames, layout, bbox)
            mpp = gms.meters_per_pixel(bbox.center[0], zoom) / dpr
            crop_w = round(gms.bbox_size_m(bbox)[0] / mpp)
            # The crop must never engage its silent clamp (the stitch
            # itself guarantees this by raising CaptureLayoutError).
            assert crop_w + 2 * cap._COVERAGE_PAD_PX * dpr <= mosaic.size[0]

    def test_layout_rejects_bad_inputs(self) -> None:
        bbox = gms.BoundingBox(52.521, 13.404, 52.519, 13.406)
        with pytest.raises(ValueError):
            cap.build_frame_layout(bbox, 18, 0, 1, (1000.0, 700.0), 1.0)
        with pytest.raises(ValueError):
            cap.build_frame_layout(bbox, 18, 1, 1, (1000.0, 700.0), 0.0)


class TestStitchFrames:
    def _make_world(self, size=600) -> Image.Image:
        """A deterministic 'world image' whose pixel value is a pure
        function of the world pixel index."""
        img = Image.new("RGB", (size, size))
        data = []
        for y in range(size):
            for x in range(size):
                data.append(((x * 13 + y * 7) % 256, (x * 7 + y * 13) % 256, (x + y) % 256))
        img.putdata(data)
        return img

    def test_stitch_reconstructs_the_world_image_exactly(self) -> None:
        """THE seam test: frames cut from a synthetic world image by the
        layout math must stitch back into the identical world pixels — a
        seam (wrong paste offset, half-pixel phase, inverted axis) would
        break pixel identity at the frame boundaries."""
        # Viewport SMALLER than the bbox on both axes -> real multi-frame
        # steps; even steps keep every frame window on whole world pixels.
        vw, vh, zoom = 180, 140, 18
        cx, cy = 300, 220  # integer world-px centre
        # bbox spanning 262 world px per axis -> steps 92 (x) / 132 (y) with the
        # physical-space pad (even steps keep whole-pixel frame windows).
        nw = cap.world_px_inverse(cx - 131, cy - 131, zoom)
        se = cap.world_px_inverse(cx + 131, cy + 131, zoom)
        bbox = gms.BoundingBox(
            nw_lat=nw[0], nw_lng=nw[1], se_lat=se[0], se_lng=se[1]
        )
        layout = cap.build_frame_layout(bbox, zoom, 2, 2, (vw, vh), 1.0)
        assert layout.step_x_css == 92
        assert layout.step_y_css == 132
        world = self._make_world(600)
        frames = []
        for _lat, _lng in layout.centers:
            fx, fy = cap.world_px(_lat, _lng, zoom)
            left = round(fx - vw / 2)
            top = round(fy - vh / 2)
            frames.append(world.crop((left, top, left + vw, top + vh)))
        mosaic = cap.stitch_frames(frames, layout, bbox)
        x0, y0 = cx - 136, cy - 136
        assert mosaic.size == (272, 272)
        expected = world.crop((x0, y0, x0 + 272, y0 + 272))
        assert mosaic.tobytes() == expected.tobytes()
        # The shared crop seam on the mosaic is centred on the bbox.
        mpp = gms.meters_per_pixel(bbox.center[0], zoom)
        cropped = gms.crop_image_to_bbox(mosaic, mpp, bbox)
        assert cropped.size[0] <= mosaic.size[0] and cropped.size[1] <= mosaic.size[1]

    def test_stitch_rejects_inconsistent_frames(self) -> None:
        bbox = gms.BoundingBox(52.52135, 13.40205, 52.51865, 13.40795)
        layout = cap.build_frame_layout(bbox, 18, 2, 2, (1000.0, 700.0), 1.0)
        with pytest.raises(cap.CaptureLayoutError):
            cap.stitch_frames([Image.new("RGB", (1000, 700))], layout, bbox)
        frames = [Image.new("RGB", (1000, 700)) for _ in range(4)]
        frames[1] = Image.new("RGB", (999, 700))
        with pytest.raises(cap.CaptureLayoutError):
            cap.stitch_frames(frames, layout, bbox)
        # A grid whose mosaic cannot cover the bbox must refuse, not clamp.
        tiny_boxes = [Image.new("RGB", (500, 300)) for _ in range(4)]
        with pytest.raises(cap.CaptureLayoutError):
            cap.stitch_frames(tiny_boxes, layout, bbox)


class TestFrameQuality:
    def test_full_imagery_passes(self) -> None:
        img = Image.new("RGB", (400, 300))
        for y in range(300):
            for x in range(400):
                img.putpixel((x, y), ((x * 3 + y) % 256, (x + y * 5) % 256, x % 256))
        assert cap.frame_quality_ok(img) is True

    def test_blank_strip_is_refused(self) -> None:
        """A beige strip (unloaded tiles) across a row of cells must be
        caught even though the global stddev is high."""
        img = Image.new("RGB", (400, 300))
        for y in range(300):
            for x in range(400):
                if y > 210:  # bottom ~30% = one blank row of cells
                    img.putpixel((x, y), (232, 234, 237))
                else:
                    img.putpixel((x, y), ((x * 3 + y) % 256, (x + y * 5) % 256, x % 256))
        assert cap.frame_quality_ok(img) is False

    def test_few_uniform_cells_tolerated(self) -> None:
        """A single calm-sea cell must not refuse the frame (the refusal
        trade-off mirrors is_blank_capture's documented caveat)."""
        img = Image.new("RGB", (400, 300))
        for y in range(300):
            for x in range(400):
                if x < 100 and y < 75:  # one uniform corner cell
                    img.putpixel((x, y), (10, 10, 10))
                else:
                    img.putpixel((x, y), ((x * 3 + y) % 256, (x + y * 5) % 256, x % 256))
        assert cap.frame_quality_ok(img) is True

    def test_fully_blank_is_refused(self) -> None:
        img = Image.new("RGB", (400, 300), (232, 234, 237))
        assert cap.frame_quality_ok(img) is False
