"""Conformance gate for the generated object sprites (#308, Package 3a).

Enforces the resources/objects/README.md style contract mechanically:
file coverage vs the generator table and the renderer maps, QtSvg-subset
allowlist, element/byte budgets, per-object viewBox, QtSvg acceptance, and
deterministic regeneration (no drift, no hand edits).
"""

import importlib.util
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PyQt6.QtSvg import QSvgRenderer

REPO = Path(__file__).parent.parent.parent
SCRIPT = REPO / "scripts" / "generate_object_sprites.py"
OBJECTS = REPO / "src" / "open_garden_planner" / "resources" / "objects"
FURNITURE_DIR = OBJECTS / "furniture"
INFRASTRUCTURE_DIR = OBJECTS / "infrastructure"

ALL_SVGS = sorted(FURNITURE_DIR.glob("*.svg")) + sorted(INFRASTRUCTURE_DIR.glob("*.svg"))

# QtSvg-subset ALLOWLIST (§8.23): everything the generator emits, nothing more.
# A new element/attribute must be added here consciously — after verifying
# QSvgRenderer actually supports it.
ALLOWED_ELEMENTS = frozenset({
    "svg", "defs", "g", "path", "line", "ellipse", "circle", "rect",
    "linearGradient", "radialGradient", "stop",
})
ALLOWED_ATTRIBUTES = frozenset({
    "d", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
    "width", "height", "fill", "fill-opacity", "opacity", "stroke",
    "stroke-width", "stroke-linecap", "stroke-linejoin", "transform",
    "stop-color", "stop-opacity", "id", "offset", "viewBox",
})
COLOR_VALUE = re.compile(r"^(none|#[0-9a-f]{6}|url\(#[A-Za-z0-9_]+\))$")
# Budgets: densest shipped sprite is hot_tub at 380 elements / 35,910 bytes (LF)
# (measured 2026-08-17); caps sit ~1.2x above it — a new recipe that trips
# them should be slimmed or the cap raised deliberately (with this note updated).
MAX_ELEMENTS = 460
MAX_BYTES = 44 * 1024


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_object_sprites", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


_GEN = _load_generator()


class TestFileCoverage:
    def test_table_matches_files(self) -> None:
        assert {p.stem for p in ALL_SVGS} == set(_GEN.OBJECTS)

    def test_files_live_in_their_declared_dir(self) -> None:
        for name, cfg in _GEN.OBJECTS.items():
            d = FURNITURE_DIR if cfg["dir"] == "furniture" else INFRASTRUCTURE_DIR
            assert (d / f"{name}.svg").exists(), f"{name} missing from {d.name}/"

    def test_renderer_maps_covered(self, qtbot: object) -> None:
        from open_garden_planner.core.furniture_renderer import (
            _FURNITURE_FILES,
            _INFRASTRUCTURE_FILES,
            _OBJECT_SVG_FILES,
            _SVG_DIR_OVERRIDES,
        )

        furniture = {n for n, c in _GEN.OBJECTS.items() if c["dir"] == "furniture"}
        infra = {n for n, c in _GEN.OBJECTS.items() if c["dir"] == "infrastructure"}
        assert set(_FURNITURE_FILES.values()) == furniture
        assert set(_INFRASTRUCTURE_FILES.values()) == infra
        # every infrastructure type must be reachable by the renderer (the two maps
        # get_furniture_svg_path actually reads) — a missing entry renders nothing
        for obj_type, filename in _INFRASTRUCTURE_FILES.items():
            assert _OBJECT_SVG_FILES.get(obj_type) == filename, f"{obj_type} not in _OBJECT_SVG_FILES"
            assert obj_type in _SVG_DIR_OVERRIDES, f"{obj_type} not in _SVG_DIR_OVERRIDES"


@pytest.mark.parametrize("svg_path", ALL_SVGS, ids=lambda p: p.stem)
class TestQtSvgSubset:
    def test_element_attribute_and_color_allowlist(self, svg_path: Path) -> None:
        root = ET.parse(svg_path).getroot()
        count = 0
        for el in root.iter():
            count += 1
            tag = el.tag.split("}")[-1]
            assert tag in ALLOWED_ELEMENTS, f"{svg_path.name}: <{tag}> not allowlisted"
            for name, value in el.attrib.items():
                name = name.split("}")[-1]
                assert name in ALLOWED_ATTRIBUTES, (
                    f"{svg_path.name}: attribute {name!r} on <{tag}> not allowlisted"
                )
                if name in ("fill", "stroke", "stop-color"):
                    assert COLOR_VALUE.match(value), (
                        f"{svg_path.name}: bad color value {value!r} on <{tag}>"
                    )
        assert count <= MAX_ELEMENTS, f"{svg_path.name}: {count} elements exceeds budget"

    def test_size_budget(self, svg_path: Path) -> None:
        assert svg_path.stat().st_size <= MAX_BYTES

    def test_viewbox_matches_recipe(self, svg_path: Path) -> None:
        w, h = _GEN.OBJECTS[svg_path.stem]["view"]
        assert f'viewBox="0 0 {w} {h}"' in svg_path.read_text(encoding="utf-8")

    def test_no_baked_directional_shadow(self, svg_path: Path) -> None:
        """Contract rule 1: the legacy '#00000020' offset drop shadow is gone."""
        assert "#00000020" not in svg_path.read_text(encoding="utf-8")

    def test_qtsvg_accepts(self, svg_path: Path, qtbot: object) -> None:
        assert QSvgRenderer(str(svg_path)).isValid(), f"QtSvg rejects {svg_path.name}"


class TestRecipes:
    def test_recipe_keys_are_known(self) -> None:
        for name, cfg in _GEN.OBJECTS.items():
            assert set(cfg) <= _GEN._KNOWN_KEYS, name

    def test_shape_matches_change_type_menu_and_art_aspect(self, qtbot: object) -> None:
        """`shape` is load-bearing: a circle-tool object must be offered for circles
        (the "Change Type" menu) and ship SQUARE art (a circle item renders into a
        square footprint — the BBQ was stretched on every canvas until #308)."""
        from open_garden_planner.core.furniture_renderer import (
            _FURNITURE_FILES,
            _INFRASTRUCTURE_FILES,
        )
        from open_garden_planner.core.object_types import get_valid_types_for_shape

        by_file = {v: k for k, v in {**_FURNITURE_FILES, **_INFRASTRUCTURE_FILES}.items()}
        circle_types = set(get_valid_types_for_shape("circle"))
        rect_types = set(get_valid_types_for_shape("rectangle"))
        for name, cfg in _GEN.OBJECTS.items():
            obj_type = by_file[name]
            w, h = cfg["view"]
            if cfg["shape"] == "circle":
                assert obj_type in circle_types, f"{name}: circle-tool object not offered for circles"
                assert w == h, f"{name}: circle-tool object must ship square art"
            else:
                assert cfg["shape"] == "rect", name
                assert obj_type in rect_types, f"{name}: rect-tool object not offered for rectangles"

    def test_default_dimensions_match_viewboxes(self, qtbot: object) -> None:
        """The renderer's default cm footprint IS the art's viewBox (contract rule 4)."""
        from open_garden_planner.core.furniture_renderer import (
            _FURNITURE_FILES,
            _INFRASTRUCTURE_FILES,
            FURNITURE_DEFAULT_DIMENSIONS,
        )

        by_file = {v: k for k, v in {**_FURNITURE_FILES, **_INFRASTRUCTURE_FILES}.items()}
        for name, cfg in _GEN.OBJECTS.items():
            obj_type = by_file[name]
            assert FURNITURE_DEFAULT_DIMENSIONS[obj_type] == tuple(float(v) for v in cfg["view"]), name


class TestDeterminism:
    def test_regeneration_matches_committed_files(self) -> None:
        """The committed SVGs are exactly what the generator produces (no drift)."""
        drift = [
            path.name
            for path, text in _GEN.generate_all().items()
            if not path.exists() or path.read_text(encoding="utf-8") != text
        ]
        assert not drift, f"object sprites drifted from generator output: {sorted(drift)}"

    def test_regenerated_bytes_equal_committed_svg_bytes(self) -> None:
        """L3.0 byte gate: every generated object SVG matches the committed file byte for byte."""
        generated = _GEN.generate_all()
        assert len(generated) == len(ALL_SVGS)
        for path, text in generated.items():
            committed = path.read_bytes().replace(b"\r\n", b"\n")
            assert committed == text.encode("utf-8"), f"{path.name}: byte mismatch"


class TestObjectArtPackage:
    """L3.0 (#387): ``core/object_art/materials.py`` is stdlib-only and is the single
    home of ``MATERIALS``, ``EMBER``, ``FLAME`` and ``mat``."""

    def test_package_is_stdlib_only(self) -> None:
        import sys

        from open_garden_planner.core import object_art
        from tests.unit.test_scene3d_contract import _imports

        package_dir = Path(object_art.__file__).parent
        modules = sorted(package_dir.rglob("*.py"))
        assert {p.name for p in modules} >= {"__init__.py", "materials.py"}
        stdlib = set(sys.stdlib_module_names) | {"__future__"}
        own = "open_garden_planner.core.object_art"
        for mod_path in modules:
            for name in _imports(mod_path):
                assert name.split(".")[0] in stdlib or name == own or name.startswith(own + "."), (
                    f"{mod_path.name} imports {name}"
                )

    def test_generator_shares_materials_module(self) -> None:
        from open_garden_planner.core.object_art import materials

        fresh_gen = _load_generator()
        assert fresh_gen.MATERIALS == materials.MATERIALS
        assert fresh_gen.EMBER == materials.EMBER
        assert fresh_gen.FLAME == materials.FLAME
        assert fresh_gen.TONE_KEYS == materials.TONE_KEYS
        for mat_name, tones in materials.MATERIALS.items():
            assert tuple(tones) == materials.TONE_KEYS, mat_name

    def test_generator_runs_without_qt_or_numpy(self) -> None:
        import subprocess
        import sys

        code = (
            "import runpy, sys; "
            "sys.modules['PyQt6'] = None; "
            "sys.modules['numpy'] = None; "
            f"sys.argv = [{str(SCRIPT)!r}, '--check']; "
            f"runpy.run_path({str(SCRIPT)!r}, run_name='__main__')"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr or proc.stdout
