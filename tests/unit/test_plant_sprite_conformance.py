"""Conformance gate for the generated plant sprites (#281).

Enforces the resources/plants/README.md style contract mechanically:
file coverage, QtSvg-subset rules, renderer-map consistency, and
deterministic regeneration (no drift, no hand edits).
"""

import importlib.util
import re
import xml.etree.ElementTree as ET  # noqa: S405 - parsing our own generated files
from pathlib import Path

import pytest
from PyQt6.QtSvg import QSvgRenderer

REPO = Path(__file__).parent.parent.parent
SCRIPT = REPO / "scripts" / "generate_plant_sprites.py"
PLANTS = REPO / "src" / "open_garden_planner" / "resources" / "plants"
SPECIES_DIR = PLANTS / "species"
CATEGORIES_DIR = PLANTS / "categories"

ALL_SVGS = sorted(SPECIES_DIR.glob("*.svg")) + sorted(CATEGORIES_DIR.glob("*.svg"))

FORBIDDEN = re.compile(
    r"<filter|<mask|<clipPath|<text|<image|<style|\bclass=|href=", re.IGNORECASE
)


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_plant_sprites", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


_GEN = _load_generator()


class TestFileCoverage:
    def test_species_count(self) -> None:
        assert len(list(SPECIES_DIR.glob("*.svg"))) == 108

    def test_category_count(self) -> None:
        assert len(list(CATEGORIES_DIR.glob("*.svg"))) == 15

    def test_species_table_matches_files(self) -> None:
        assert {p.stem for p in SPECIES_DIR.glob("*.svg")} == set(_GEN.SPECIES)

    def test_category_table_matches_files(self) -> None:
        assert {p.stem for p in CATEGORIES_DIR.glob("*.svg")} == set(_GEN.CATEGORIES)

    def test_renderer_species_map_covered(self, qtbot: object) -> None:  # noqa: ARG002
        from open_garden_planner.core.plant_renderer import _SPECIES_FILES

        missing = {f for f in set(_SPECIES_FILES.values()) if not (SPECIES_DIR / f"{f}.svg").exists()}
        assert not missing, f"renderer maps species with no SVG: {sorted(missing)}"

    def test_renderer_category_map_covered(self, qtbot: object) -> None:  # noqa: ARG002
        from open_garden_planner.core.plant_renderer import _CATEGORY_FILES

        missing = {f for f in _CATEGORY_FILES.values() if not (CATEGORIES_DIR / f"{f}.svg").exists()}
        assert not missing, f"renderer maps categories with no SVG: {sorted(missing)}"


@pytest.mark.parametrize("svg_path", ALL_SVGS, ids=lambda p: p.stem)
class TestPerFileContract:
    def test_well_formed_and_subset(self, svg_path: Path) -> None:
        text = svg_path.read_text(encoding="utf-8")
        ET.fromstring(text)  # noqa: S314 - our own generated content
        match = FORBIDDEN.search(text)
        assert match is None, f"{svg_path.name} uses forbidden SVG feature: {match.group(0)!r}"

    def test_viewbox(self, svg_path: Path) -> None:
        text = svg_path.read_text(encoding="utf-8")
        expected = '10 25 80 50' if svg_path.stem == "hedge_section" else '0 0 100 100'
        assert f'viewBox="{expected}"' in text

    def test_qtsvg_accepts(self, svg_path: Path, qtbot: object) -> None:  # noqa: ARG002
        assert QSvgRenderer(str(svg_path)).isValid(), f"QtSvg rejects {svg_path.name}"


class TestDeterminism:
    def test_regeneration_matches_committed_files(self) -> None:
        """The committed SVGs are exactly what the generator produces (no drift)."""
        drift = [
            path.name
            for path, text in _GEN.generate_all().items()
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]
        assert not drift, f"sprites drifted from generator output: {sorted(drift)}"
