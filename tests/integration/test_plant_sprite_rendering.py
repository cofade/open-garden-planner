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


def _opaque_pixels(pixmap: QPixmap) -> int:
    image = pixmap.toImage()
    count = 0
    for y in range(0, image.height(), 2):
        for x in range(0, image.width(), 2):
            if image.pixelColor(x, y).alpha() > 10:
                count += 1
    return count


@pytest.fixture(autouse=True)
def _fresh_cache(qtbot: object) -> None:  # noqa: ARG001
    clear_plant_cache()


class TestEverySpeciesRenders:
    @pytest.mark.parametrize("filename", sorted(_ALIAS_FOR_FILE), ids=str)
    def test_species_renders_visible_pixels(self, filename: str) -> None:
        alias = _ALIAS_FOR_FILE[filename]
        pixmap = render_plant_pixmap(
            ObjectType.SHRUB, diameter=64.0, item_id=f"it-{filename}", species=alias,
        )
        assert pixmap is not None and not pixmap.isNull()
        assert _opaque_pixels(pixmap) > 120, f"{filename} renders (near-)blank"

    def test_every_species_file_reachable_via_alias(self) -> None:
        """Every shipped species SVG is addressable through the renderer map."""
        files_on_disk = {p.stem for p in SPECIES_DIR.glob("*.svg")}
        assert files_on_disk == set(_ALIAS_FOR_FILE), (
            "species files and renderer map out of sync"
        )


class TestEveryCategoryRenders:
    @pytest.mark.parametrize("category", list(PlantCategory), ids=lambda c: c.name)
    def test_category_renders_visible_pixels(self, category: PlantCategory) -> None:
        pixmap = render_plant_pixmap(
            ObjectType.TREE, diameter=64.0, item_id=f"cat-{category.name}", category=category,
        )
        assert pixmap is not None and not pixmap.isNull()
        assert _opaque_pixels(pixmap) > 120, f"{category.name} renders (near-)blank"


class TestCanvasRenderPaths:
    def test_tinted_render(self) -> None:
        pixmap = render_plant_pixmap(
            ObjectType.SHRUB, diameter=64.0, item_id="tinted", species="tomato",
            tint_color=QColor(200, 100, 50, 100),
        )
        assert pixmap is not None and _opaque_pixels(pixmap) > 120

    def test_small_growth_size_still_visible(self) -> None:
        """US-E8 growth model renders young plants small — sprites must survive 16 px."""
        pixmap = render_plant_pixmap(
            ObjectType.PERENNIAL, diameter=16.0, item_id="young", species="lettuce",
        )
        assert pixmap is not None and not pixmap.isNull()
        assert _opaque_pixels(pixmap) > 15

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
        assert pixmap is not None and _opaque_pixels(pixmap) > 200
