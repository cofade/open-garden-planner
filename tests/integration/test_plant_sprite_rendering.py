"""Integration gate (§8.10) for the generated plant sprites (#281).

Every sprite must render to visible pixels through the app's real path —
`core.plant_renderer.render_plant_pixmap` — exactly as the canvas uses it
(including rotation via item_id, tinting, and small growth-model sizes).
"""

from pathlib import Path

import pytest
from PyQt6.QtGui import QColor, QPixmap

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plant_renderer import (
    _SPECIES_FILES,
    PlantCategory,
    clear_plant_cache,
    render_plant_pixmap,
)

SPECIES_DIR = (
    Path(__file__).parent.parent.parent
    / "src" / "open_garden_planner" / "resources" / "plants" / "species"
)

# one alias per unique SVG file — covers every species sprite end-to-end
_ALIAS_FOR_FILE: dict[str, str] = {}
for alias, filename in _SPECIES_FILES.items():
    _ALIAS_FOR_FILE.setdefault(filename, alias)


# Visual-weight bounds (the #281 gate): ink coverage = opaque samples / all
# samples (alpha > 10, 2-px sampling grid, ground shadow included). Shipped
# set measured 2026-07-27: species 0.379-0.627 (spread 1.65x), categories up
# to 0.925 (hedge_section is a deliberately solid tile), 16-px minimum 0.375.
SPECIES_COVERAGE = (0.30, 0.75)
CATEGORY_COVERAGE = (0.30, 0.95)
SPECIES_SPREAD_MAX = 2.5
SMALL_SIZE_MIN_COVERAGE = 0.25


def _coverage(pixmap: QPixmap) -> float:
    image = pixmap.toImage()
    total = opaque = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            total += 1
            if image.pixelColor(x, y).alpha() > 10:
                opaque += 1
    return opaque / max(total, 1)


@pytest.fixture(autouse=True)
def _fresh_cache(qtbot: object) -> None:  # noqa: ARG001
    clear_plant_cache()


class TestEverySpeciesRenders:
    @pytest.mark.parametrize("filename", sorted(_ALIAS_FOR_FILE), ids=str)
    def test_species_coverage_within_bounds(self, filename: str) -> None:
        """Visible AND visually balanced: coverage inside the contract band."""
        alias = _ALIAS_FOR_FILE[filename]
        pixmap = render_plant_pixmap(
            ObjectType.SHRUB, diameter=64.0, item_id=f"it-{filename}", species=alias,
        )
        assert pixmap is not None and not pixmap.isNull()
        cov = _coverage(pixmap)
        lo, hi = SPECIES_COVERAGE
        assert lo <= cov <= hi, f"{filename}: coverage {cov:.3f} outside [{lo}, {hi}]"

    @pytest.mark.parametrize("filename", sorted(_ALIAS_FOR_FILE), ids=str)
    def test_species_legible_at_growth_model_size(self, filename: str) -> None:
        """US-E8 renders young plants tiny — every sprite must survive 16 px."""
        pixmap = render_plant_pixmap(
            ObjectType.SHRUB, diameter=16.0, item_id=f"sm-{filename}",
            species=_ALIAS_FOR_FILE[filename],
        )
        assert pixmap is not None and not pixmap.isNull()
        assert _coverage(pixmap) >= SMALL_SIZE_MIN_COVERAGE, f"{filename} illegible at 16 px"

    def test_species_visual_weight_spread(self) -> None:
        """No sprite may dominate or vanish next to its neighbours (#281)."""
        coverages = {}
        for filename, alias in _ALIAS_FOR_FILE.items():
            pixmap = render_plant_pixmap(
                ObjectType.SHRUB, diameter=64.0, item_id=f"sp-{filename}", species=alias,
            )
            assert pixmap is not None
            coverages[filename] = _coverage(pixmap)
        lo_name = min(coverages, key=coverages.get)
        hi_name = max(coverages, key=coverages.get)
        spread = coverages[hi_name] / max(coverages[lo_name], 0.001)
        assert spread <= SPECIES_SPREAD_MAX, (
            f"visual-weight spread {spread:.2f}x exceeds {SPECIES_SPREAD_MAX}x "
            f"({hi_name} {coverages[hi_name]:.3f} vs {lo_name} {coverages[lo_name]:.3f})"
        )

    def test_every_species_file_reachable_via_alias(self) -> None:
        """Every shipped species SVG is addressable through the renderer map."""
        files_on_disk = {p.stem for p in SPECIES_DIR.glob("*.svg")}
        assert files_on_disk == set(_ALIAS_FOR_FILE), (
            "species files and renderer map out of sync"
        )


class TestEveryCategoryRenders:
    @pytest.mark.parametrize("category", list(PlantCategory), ids=lambda c: c.name)
    def test_category_coverage_within_bounds(self, category: PlantCategory) -> None:
        pixmap = render_plant_pixmap(
            ObjectType.TREE, diameter=64.0, item_id=f"cat-{category.name}", category=category,
        )
        assert pixmap is not None and not pixmap.isNull()
        cov = _coverage(pixmap)
        lo, hi = CATEGORY_COVERAGE
        assert lo <= cov <= hi, f"{category.name}: coverage {cov:.3f} outside [{lo}, {hi}]"


class TestCanvasRenderPaths:
    def test_tinted_render(self) -> None:
        pixmap = render_plant_pixmap(
            ObjectType.SHRUB, diameter=64.0, item_id="tinted", species="tomato",
            tint_color=QColor(200, 100, 50, 100),
        )
        assert pixmap is not None and _coverage(pixmap) >= SPECIES_COVERAGE[0]

    def test_rotation_variation_changes_output(self) -> None:
        """Two item_ids produce different stable rotations of the same sprite."""
        p1 = render_plant_pixmap(ObjectType.SHRUB, diameter=64.0, item_id="rot-a", species="rose")
        p2 = render_plant_pixmap(ObjectType.SHRUB, diameter=64.0, item_id="rot-b", species="rose")
        assert p1 is not None and p2 is not None
        assert p1.toImage() != p2.toImage()

    def test_hedge_rect_viewbox_renders(self) -> None:
        pixmap = render_plant_pixmap(
            ObjectType.SHRUB, diameter=64.0, item_id="hedge",
            category=PlantCategory.HEDGE_SECTION,
        )
        assert pixmap is not None and _coverage(pixmap) >= 0.5
