"""Geo-metadata extension of :class:`BackgroundImageItem`.

Verifies the satellite-import code path: auto-scale from
``meters_per_pixel`` and roundtrip of ``geo_metadata`` through
``to_dict``/``from_dict``. Backwards compatibility with pre-geo project
files is also covered.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from open_garden_planner.ui.canvas.items.background_image_item import (
    BackgroundImageItem,
)


def _make_png_bytes(size: tuple[int, int] = (200, 150)) -> bytes:
    img = Image.new("RGB", size, color=(60, 120, 60))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def png_bytes() -> bytes:
    return _make_png_bytes()


class TestGeoMetadataAutoScale:
    def test_scale_derived_from_meters_per_pixel(self, qtbot, png_bytes) -> None:
        # mpp = 0.5 m/px → 1 px = 0.5 m = 50 cm → 1 cm = 0.02 px.
        geo = {
            "meters_per_pixel": 0.5,
            "zoom": 19,
            "center": [52.0, 13.0],
            "bbox_nw": [52.001, 12.999],
            "bbox_se": [51.999, 13.001],
            "source": "google_static_maps",
        }
        item = BackgroundImageItem(
            "test.png", _pixmap_data=png_bytes, geo_metadata=geo
        )
        assert item.scale_factor == pytest.approx(0.02, rel=1e-9)
        # Apply the scale transform so canvas-units == cm.
        assert item.scale() == pytest.approx(1.0 / 0.02, rel=1e-9)

    def test_no_geo_falls_back_to_default(self, qtbot, png_bytes) -> None:
        item = BackgroundImageItem("test.png", _pixmap_data=png_bytes)
        assert item.scale_factor == 1.0
        assert item.geo_metadata is None

    def test_geo_property_exposes_dict(self, qtbot, png_bytes) -> None:
        geo = {"meters_per_pixel": 0.3, "zoom": 20, "source": "foo"}
        item = BackgroundImageItem(
            "x.png", _pixmap_data=png_bytes, geo_metadata=geo
        )
        assert item.geo_metadata is geo


class TestGeoRoundtrip:
    def test_to_dict_includes_geo(self, qtbot, png_bytes) -> None:
        geo = {
            "meters_per_pixel": 0.2,
            "zoom": 20,
            "center": [48.137, 11.575],
            "bbox_nw": [48.138, 11.574],
            "bbox_se": [48.136, 11.576],
            "source": "google_static_maps",
            "fetched_at": "2026-05-14T10:00:00+00:00",
        }
        item = BackgroundImageItem(
            "m.png", _pixmap_data=png_bytes, geo_metadata=geo
        )
        data = item.to_dict()
        assert data["geo_metadata"] == geo

    def test_to_dict_omits_geo_when_none(self, qtbot, png_bytes) -> None:
        item = BackgroundImageItem("m.png", _pixmap_data=png_bytes)
        data = item.to_dict()
        assert "geo_metadata" not in data

    def test_from_dict_with_geo_restores_scale(self, qtbot, png_bytes) -> None:
        geo = {"meters_per_pixel": 0.4, "zoom": 19, "source": "google_static_maps"}
        original = BackgroundImageItem(
            "o.png", _pixmap_data=png_bytes, geo_metadata=geo
        )
        data = original.to_dict()
        restored = BackgroundImageItem.from_dict(data)
        assert restored.geo_metadata == geo
        assert restored.scale_factor == pytest.approx(0.025, rel=1e-9)

    def test_from_dict_backward_compat_no_geo(self, qtbot, png_bytes) -> None:
        """Old project files without geo_metadata must keep loading."""
        legacy = {
            "type": "background_image",
            "image_path": "legacy.png",
            "image_data": __import__("base64").b64encode(png_bytes).decode("ascii"),
            "position": {"x": 0, "y": 0},
            "opacity": 0.8,
            "locked": True,
            "scale_factor": 5.0,
        }
        item = BackgroundImageItem.from_dict(legacy)
        assert item.geo_metadata is None
        assert item.scale_factor == 5.0
        assert item.opacity == 0.8
        assert item.locked is True

    def test_manual_calibration_overrides_geo_scale_on_load(
        self, qtbot, png_bytes
    ) -> None:
        # User imported a satellite image, then manually re-calibrated. On
        # reload, the manual scale_factor must win over the geo-derived one.
        geo = {"meters_per_pixel": 1.0, "zoom": 18, "source": "google_static_maps"}
        data = {
            "type": "background_image",
            "image_path": "x.png",
            "image_data": __import__("base64").b64encode(png_bytes).decode("ascii"),
            "position": {"x": 0, "y": 0},
            "opacity": 1.0,
            "locked": False,
            "scale_factor": 2.5,
            "geo_metadata": geo,
        }
        item = BackgroundImageItem.from_dict(data)
        assert item.scale_factor == 2.5
        assert item.geo_metadata == geo


class TestCenteringWithScale:
    """Regression guard for the canvas-centering math after a satellite import.

    With ``transformOriginPoint`` at the local centre of the pixmap, setting
    ``pos = canvas_center - (w/2, h/2)`` places ``sceneBoundingRect().center()``
    at ``canvas_center`` regardless of scale. Multiplying by ``scale`` (an
    earlier bug) drifted the centre off the canvas for any non-trivial mpp.
    """

    def test_scene_center_matches_canvas_center_after_scaled_setpos(
        self, qtbot, png_bytes
    ) -> None:
        from PyQt6.QtCore import QPointF

        # 200×150 image at mpp=0.5 → scale_factor=0.02 → applied scale = 50.
        geo = {"meters_per_pixel": 0.5, "zoom": 19, "source": "google_static_maps"}
        item = BackgroundImageItem(
            "center.png", _pixmap_data=png_bytes, geo_metadata=geo
        )
        assert item.scale() == pytest.approx(50.0, rel=1e-9)

        canvas_center = QPointF(2500.0, 1500.0)
        w = item.boundingRect().width()
        h = item.boundingRect().height()
        # Correct formula — NO ``* scale``.
        item.setPos(canvas_center.x() - w / 2, canvas_center.y() - h / 2)

        # 1 cm tolerance handles half-pixel boundingRect rounding; the bug
        # this guards against missed by ~1000 cm so 1 is a comfortable margin.
        scene_center = item.sceneBoundingRect().center()
        assert scene_center.x() == pytest.approx(canvas_center.x(), abs=1.0)
        assert scene_center.y() == pytest.approx(canvas_center.y(), abs=1.0)


class TestFromFetchResultFactory:
    def test_builds_full_geo_metadata(self, qtbot, png_bytes) -> None:
        item = BackgroundImageItem.from_fetch_result(
            "z19.png",
            png_bytes,
            meters_per_pixel=0.3,
            bbox_nw=(52.52, 13.40),
            bbox_se=(52.51, 13.41),
            zoom=19,
            fetched_at="2026-05-14T12:00:00+00:00",
        )
        geo = item.geo_metadata
        assert geo is not None
        assert geo["meters_per_pixel"] == 0.3
        assert geo["bbox_nw"] == [52.52, 13.40]
        assert geo["bbox_se"] == [52.51, 13.41]
        assert geo["center"] == [(52.52 + 52.51) / 2, (13.40 + 13.41) / 2]
        assert geo["zoom"] == 19
        assert geo["source"] == "google_static_maps"
        assert item.scale_factor == pytest.approx(0.01 / 0.3, rel=1e-9)
