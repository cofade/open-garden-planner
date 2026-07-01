"""Unit tests for the Agent API render pixel-size math (Qt-free, pure function).

``resolve_image_pixel_size`` clamps the requested width and derives the height
from the region's aspect ratio, independently clamping the height too so a
pathological aspect ratio can't turn a modest width request into a runaway
image.
"""

from __future__ import annotations

import pytest

from open_garden_planner.agent_api.render import (
    MAX_IMAGE_PX,
    MIN_IMAGE_PX,
    resolve_image_pixel_size,
)


class TestResolveImagePixelSize:
    def test_default_width_square_region(self) -> None:
        width_px, height_px = resolve_image_pixel_size(500.0, 500.0, 1024)
        assert (width_px, height_px) == (1024, 1024)

    def test_width_within_range_preserves_aspect_ratio(self) -> None:
        width_px, height_px = resolve_image_pixel_size(1000.0, 800.0, 500)
        assert width_px == 500
        assert height_px == pytest.approx(400, abs=1)

    def test_clamps_below_minimum(self) -> None:
        width_px, height_px = resolve_image_pixel_size(500.0, 500.0, 10)
        assert (width_px, height_px) == (MIN_IMAGE_PX, MIN_IMAGE_PX)

    def test_clamps_above_maximum(self) -> None:
        width_px, height_px = resolve_image_pixel_size(500.0, 500.0, 5000)
        assert (width_px, height_px) == (MAX_IMAGE_PX, MAX_IMAGE_PX)

    def test_negative_or_zero_width_request_clamps_to_minimum(self) -> None:
        width_px, height_px = resolve_image_pixel_size(500.0, 500.0, -50)
        assert (width_px, height_px) == (MIN_IMAGE_PX, MIN_IMAGE_PX)

    def test_pathologically_tall_region_double_clamps_height(self) -> None:
        """A 1cm x 10 000cm strip must not produce a runaway-tall image."""
        width_px, height_px = resolve_image_pixel_size(1.0, 10_000.0, 1024)
        assert width_px == MIN_IMAGE_PX
        assert height_px == MAX_IMAGE_PX

    def test_pathologically_wide_region_double_clamps_width(self) -> None:
        width_px, height_px = resolve_image_pixel_size(10_000.0, 1.0, 1024)
        assert width_px == MAX_IMAGE_PX
        assert height_px == MIN_IMAGE_PX

    def test_non_positive_region_dimensions_raise(self) -> None:
        with pytest.raises(ValueError):
            resolve_image_pixel_size(0.0, 500.0, 1024)
        with pytest.raises(ValueError):
            resolve_image_pixel_size(500.0, -1.0, 1024)

    def test_output_within_bounds_for_arbitrary_aspect_ratios(self) -> None:
        for region_width, region_height in [(100.0, 50.0), (50.0, 100.0), (1.0, 1.0), (3000.0, 3000.0)]:
            width_px, height_px = resolve_image_pixel_size(region_width, region_height, 1024)
            assert MIN_IMAGE_PX <= width_px <= MAX_IMAGE_PX
            assert MIN_IMAGE_PX <= height_px <= MAX_IMAGE_PX


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
