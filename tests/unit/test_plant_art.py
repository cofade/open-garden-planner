"""One recipe table for 2D and 3D — ``core/plant_art`` (Phase 17 L1.7, #385).

The plant sprites' recipe tables and the species → sprite resolution moved out
of the sprite generator and the 2D renderer into a stdlib-only package, so the
3D plant builder reads the SAME recipe through the SAME function. This file
pins the move:

- the package imports nothing but the standard library (gate G8);
- the generator and the renderer hold no table of their own any more: the
  renderer holds the package's objects, the generator executes the package's
  ``recipes.py`` by file path (so that it still needs no Qt);
- ``resolve_sprite`` answers exactly what the 2D resolver answered before the
  extraction (``tests/fixtures/plant_art/sprite_resolution_golden.json``, written
  from the unchanged code in the commit before the move; its generator, with
  that resolver kept statement for statement, is
  ``scripts/make_sprite_resolution_golden.py``) — with every sprite file present
  and with sprite files MISSING, at the pure function and at the renderer;
- the dormant spike's palette copy still equals the shared table (until L1.10).

The sprites themselves are pinned by ``test_plant_sprite_conformance.py``, which
regenerates all 123 SVGs in memory and compares them with the shipped files.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter

from open_garden_planner.core import plant_art
from open_garden_planner.core.plant_art import recipes, resolve
from open_garden_planner.core.plant_art.resolve import (
    CATEGORY_SPRITES,
    DEFAULT_CATEGORY,
    PLANT_KINDS,
    SPECIES_SPRITES,
    SpriteRef,
    recipe_for,
    resolve_recipe,
    resolve_sprite,
)
from tests.unit.test_scene3d_contract import _imports

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "generate_plant_sprites.py"
GOLDEN_SCRIPT = REPO / "scripts" / "make_sprite_resolution_golden.py"
PLANTS = REPO / "src" / "open_garden_planner" / "resources" / "plants"
PACKAGE = Path(plant_art.__file__).parent
GOLDEN = REPO / "tests" / "fixtures" / "plant_art" / "sprite_resolution_golden.json"
BUNDLED = REPO / "src" / "open_garden_planner" / "resources" / "data" / "plant_species.json"

TABLES = ("PALETTES", "FRUITS", "FLOWERS", "SPECIES", "CATEGORIES")
ARCHETYPES = {
    "allium", "canopy", "climber", "conifer", "feathery", "flower", "grass", "ground", "head",
    "hedge", "mound", "palm", "rosette",
}


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_plant_sprites_for_plant_art", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_golden_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("make_sprite_resolution_golden", GOLDEN_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _MissingFiles:
    """``Path.exists`` with some sprite files taken away, for a ``with`` block; the
    renderer's memos (which path a plant resolves to, which renderers are loaded)
    are emptied on the way in and on the way out."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *sprites: str) -> None:
        self._monkeypatch = monkeypatch
        self._gone = {PLANTS / f"{sprite}.svg" for sprite in sprites}

    def __enter__(self) -> None:
        from open_garden_planner.core import plant_renderer

        assert all(path.exists() for path in self._gone)      # they ARE shipped
        real = Path.exists
        gone = self._gone
        self._monkeypatch.setattr(
            Path, "exists", lambda path, *a, **k: False if path in gone else real(path, *a, **k))
        plant_renderer._resolve_svg_path.cache_clear()
        plant_renderer.clear_plant_cache()

    def __exit__(self, *_exc: object) -> None:
        from open_garden_planner.core import plant_renderer

        self._monkeypatch.undo()
        plant_renderer._resolve_svg_path.cache_clear()
        plant_renderer.clear_plant_cache()


def _file_exists(sprite: SpriteRef) -> bool:
    """What the 2D renderer asks: is there an SVG for this sprite?"""
    return (PLANTS / sprite.group / f"{sprite.name}.svg").exists()


GOLDEN_ROWS: list[tuple[str, str, str | None, str | None]] = [
    (row[0], row[1], row[2], row[3]) for row in json.loads(GOLDEN.read_text(encoding="utf-8"))
]


# ── gate G8: stdlib only ──────────────────────────────────────────────────────


MODULES = sorted(PACKAGE.rglob("*.py"))


def test_the_scan_covers_the_package() -> None:
    assert {p.name for p in MODULES} >= {"__init__.py", "recipes.py", "resolve.py"}


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.relative_to(PACKAGE).as_posix())
def test_package_is_stdlib_only(path: Path) -> None:
    """No Qt, no numpy, no other part of the app: the sprite generator (a plain
    script) and the Qt-free 3D builders both import this package."""
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    own = "open_garden_planner.core.plant_art"
    for name in _imports(path):
        assert name.split(".")[0] in stdlib or name == own or name.startswith(own + "."), (
            f"{path.name} imports {name}"
        )


# ── the tables moved, and nobody kept a copy ──────────────────────────────────


class TestTables:
    def test_counts(self) -> None:
        assert len(recipes.SPECIES) == 108
        assert len(recipes.CATEGORIES) == 15
        assert len(recipes.PALETTES) == 9
        assert len(recipes.FRUITS) == 18
        assert len(recipes.FLOWERS) == 13

    def test_the_generator_holds_the_package_s_tables(self) -> None:
        """The generator executes the package's own ``recipes.py`` — the same file, by
        its path — and holds what that file defines: the package's tables, key
        order included (sprites are seeded and drawn per table entry)."""
        generator = _load_generator()
        assert generator.RECIPES_FILE.resolve() == Path(recipes.__file__).resolve()
        for name in TABLES:
            loaded, packaged = getattr(generator, name), getattr(recipes, name)
            assert loaded == packaged and list(loaded) == list(packaged), name
        assert generator.DEFAULT_PALETTE == recipes.DEFAULT_PALETTE == "fresh"
        assert generator.HEDGE_PALETTE == recipes.HEDGE_PALETTE == "dark"
        assert len(generator.generate_all()) == 123

    def test_the_generator_defines_no_table_of_its_own(self) -> None:
        """A table literal left behind in the script would be a second source: every
        table name in it is bound to the loaded recipes module's attribute of the
        same name, and to nothing else."""
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        bound: dict[str, list[ast.expr | None]] = {}
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    if isinstance(target, ast.Name):
                        bound.setdefault(target.id, []).append(node.value)
        for name in (*TABLES, "DEFAULT_PALETTE", "HEDGE_PALETTE"):
            assert len(bound.get(name, [])) == 1, name
            value = bound[name][0]
            assert isinstance(value, ast.Attribute) and value.attr == name, name
            assert isinstance(value.value, ast.Name) and value.value.id == "_RECIPES", name

    def test_the_generator_needs_nothing_but_the_standard_library(self) -> None:
        """It was a standard-library script before the tables moved out of it, and it
        still is: with PyQt6 and numpy unimportable it loads, imports no app module,
        and regenerates all 123 sprites without drift. (An ``import
        open_garden_planner.core.plant_art.recipes`` in it looked just as innocent:
        the package's files are stdlib-only — and importing them runs
        ``core/__init__.py``, which loads PyQt6. Review round 1.)"""
        code = (
            "import importlib.util, sys\n"
            "for blocked in ('PyQt6', 'numpy'):\n"
            "    sys.modules[blocked] = None\n"
            "spec = importlib.util.spec_from_file_location('generator_alone', sys.argv[1])\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(module)\n"
            "app = [name for name in sys.modules if name.startswith('open_garden_planner')]\n"
            "files = module.generate_all()\n"
            "drift = [p for p, text in files.items() if p.read_text(encoding='utf-8') != text]\n"
            "print(len(files), len(drift), len(app))\n"
        )
        result = subprocess.run([sys.executable, "-c", code, str(SCRIPT)], capture_output=True,
                                text=True, timeout=120, check=False)
        assert result.returncode == 0, result.stderr
        assert result.stdout.split() == ["123", "0", "0"]

    def test_every_palette_has_the_six_anchors(self) -> None:
        for name, palette in recipes.PALETTES.items():
            assert tuple(palette) == recipes.PALETTE_ANCHORS == ("t0", "t1", "b0", "b1", "occ", "rib")
            for colour in palette.values():
                assert len(colour) == 7 and colour[0] == "#", (name, colour)
                int(colour[1:], 16)

    def test_archetypes_are_the_thirteen_of_the_tables(self) -> None:
        assert recipes.ARCHETYPES == ARCHETYPES
        assert {recipe["a"] for recipe in recipes.SPECIES.values()} | {
            recipe["a"] for recipe in recipes.CATEGORIES.values()
        } == ARCHETYPES

    def test_every_recipe_names_a_real_palette(self) -> None:
        for name, recipe in {**recipes.SPECIES, **recipes.CATEGORIES}.items():
            assert recipes.palette_key(recipe) in recipes.PALETTES, name

    def test_the_one_implicit_palette_is_the_hedge_s(self) -> None:
        """Every recipe names its palette except the hedge, whose palette used to
        be a literal inside the generator's ``build_hedge``."""
        implicit = [name for name, recipe in {**recipes.SPECIES, **recipes.CATEGORIES}.items()
                    if "pal" not in recipe]
        assert implicit == ["hedge_section"]
        assert recipes.palette_key(recipes.CATEGORIES["hedge_section"]) == recipes.HEDGE_PALETTE
        assert (recipes.HEDGE_PALETTE, recipes.DEFAULT_PALETTE) == ("dark", "fresh")
        assert recipes.palette_key({"a": "mound"}) == "fresh"

    def test_feature_keys_are_keys_the_generator_knows(self) -> None:
        generator = _load_generator()
        assert recipes.FEATURE_KEYS <= generator._KNOWN_KEYS
        used = {key for recipe in {**recipes.SPECIES, **recipes.CATEGORIES}.values()
                for key in recipe}
        assert used <= generator._KNOWN_KEYS


# ── the shared species → sprite resolution ───────────────────────────────────


class TestResolution:
    def test_the_golden_covers_the_whole_sprite_set(self) -> None:
        answers = {sprite for *_rest, sprite in GOLDEN_ROWS if sprite}
        assert len(GOLDEN_ROWS) == 1562 and len(answers) == 123
        assert any(sprite is None for *_rest, sprite in GOLDEN_ROWS)

    @pytest.mark.parametrize("available", [None, _file_exists, resolve.has_recipe],
                             ids=["everything", "file-exists", "has-recipe"])
    def test_resolve_sprite_answers_what_the_2d_resolver_answered(self, available) -> None:
        """Held to the answers of the unchanged resolver — whichever way
        availability is asked: the 2D renderer asks for a file, the 3D builder
        for a recipe, and the two sets are the same 123 names."""
        wrong = []
        for species, kind, category, expected in GOLDEN_ROWS:
            sprite = resolve_sprite(kind, species, category, available=available)
            got = None if sprite is None else f"{sprite.group}/{sprite.name}"
            if got != expected:
                wrong.append((species, kind, category, expected, got))
        assert wrong == []

    def test_the_golden_is_what_its_generator_writes(self) -> None:
        """The fixture's provenance is in the repo: the resolver as it stood before the
        extraction, kept statement for statement in the generator script, answers
        exactly the committed rows."""
        script = _load_golden_script()
        assert script.golden_text() == GOLDEN.read_text(encoding="utf-8")
        assert len(script.cases()) == len(GOLDEN_ROWS) == 1562

    def test_the_2d_renderer_resolves_through_it(self, qtbot, monkeypatch) -> None:
        from open_garden_planner.core import plant_renderer
        from open_garden_planner.core.object_types import ObjectType

        wrong = []
        for species, kind, category, expected in GOLDEN_ROWS:
            path = plant_renderer._resolve_svg_path(
                ObjectType[kind], species,
                plant_renderer.PlantCategory[category] if category else None)
            got = None if path is None else f"{path.parent.name}/{path.stem}"
            if got != expected:
                wrong.append((species, kind, category, expected, got))
        assert wrong == []
        # ... through the shared function, not by a copy of its rules: what the
        # renderer returns is whatever ``resolve_sprite`` says — observed, by handing
        # it a rule that answers something no copy would
        asked: list[tuple[object, ...]] = []

        def always_the_palm(kind, species="", category=None, *, available=None):
            asked.append((kind, species, category, available is not None))
            return SpriteRef("categories", "palm")

        monkeypatch.setattr(plant_renderer, "resolve_sprite", always_the_palm)
        answer = plant_renderer._resolve_svg_path.__wrapped__(
            ObjectType.PERENNIAL, "Tomato", plant_renderer.PlantCategory.VEGETABLE)
        assert answer == PLANTS / "categories" / "palm.svg"
        assert asked == [("PERENNIAL", "Tomato", "VEGETABLE", True)]   # with a file test

    def test_the_renderer_skips_a_sprite_whose_file_is_missing(self, qtbot, monkeypatch) -> None:
        """The renderer's own use of the rule: a mapped sprite whose SVG is not on disk
        is skipped, and the plant gets the next sprite in line — as it always did.
        Dropping the renderer's ``available=`` survived 3,048 tests (review round 1):
        with every file present, nothing ever asked."""
        from open_garden_planner.core import plant_renderer
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import PlantCategory

        resolve_path = plant_renderer._resolve_svg_path.__wrapped__   # past the memo

        def sprite(object_type, species="", category=None) -> str | None:
            path = resolve_path(object_type, species, category)
            return None if path is None else f"{path.parent.name}/{path.stem}"

        perennial, tree = ObjectType.PERENNIAL, ObjectType.TREE
        assert sprite(perennial, "tomato", PlantCategory.VEGETABLE) == "species/tomato"
        with _MissingFiles(monkeypatch, "species/tomato"):
            # exact match gone: the item's category, else its type's default category
            assert sprite(perennial, "tomato", PlantCategory.VEGETABLE) == "categories/vegetable"
            assert sprite(perennial, "tomato") == "categories/flowering_perennial"
            assert sprite(tree, "Tomato ") == "categories/round_deciduous"
            assert sprite(perennial, "lettuce") == "species/lettuce"          # others untouched
        with _MissingFiles(monkeypatch, "species/cherry_tree"):
            # the exact key's file is gone: the first PARTIAL match whose file exists
            assert sprite(tree, "cherry") != "species/cherry_tree"
            assert sprite(tree, "cherry") == _load_golden_script().reference_resolve(
                "TREE", "cherry", None, lambda group, stem: (group, stem) != ("species", "cherry_tree"))
        with _MissingFiles(monkeypatch, "species/tomato", "categories/vegetable"):
            assert sprite(perennial, "tomato", PlantCategory.VEGETABLE) == "categories/flowering_perennial"
        with _MissingFiles(monkeypatch, "species/tomato", "categories/flowering_perennial"):
            assert sprite(perennial, "tomato") is None                        # nothing left to draw
        assert sprite(perennial, "tomato", PlantCategory.VEGETABLE) == "species/tomato"   # restored

    def test_a_plant_whose_sprite_file_is_missing_is_painted_with_the_next_one(
        self, qtbot, monkeypatch
    ) -> None:
        """... and the plant is PAINTED with it. Without the fall-through the renderer
        is handed a dead path, loads nothing, and the plant is a bare circle."""
        from open_garden_planner.core import plant_renderer
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import PlantCategory
        from open_garden_planner.ui.canvas.items.circle_item import CircleItem

        def pixels(pixmap) -> bytes:
            image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            return bytes(bits)

        def painted(item: CircleItem) -> bytes:
            image = QImage(160, 160, QImage.Format.Format_ARGB32)
            image.fill(0)
            painter = QPainter(image)
            scene.render(painter, QRectF(0, 0, 160, 160), item.sceneBoundingRect())
            painter.end()
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            return bytes(bits)

        from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

        scene = QGraphicsScene()
        item = CircleItem(0.0, 0.0, 40.0, object_type=ObjectType.PERENNIAL)
        item.plant_species, item.plant_category = "tomato", PlantCategory.VEGETABLE
        # the canvas caches an unselected item's painting; here every painting must be real
        item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        scene.addItem(item)
        own = painted(item)
        own_pixmap = pixels(plant_renderer.render_plant_pixmap(
            ObjectType.PERENNIAL, 96.0, "", "tomato", PlantCategory.VEGETABLE))
        category_pixmap = pixels(plant_renderer.render_plant_pixmap(
            ObjectType.PERENNIAL, 96.0, "", "", PlantCategory.VEGETABLE))
        assert own_pixmap != category_pixmap
        with _MissingFiles(monkeypatch, "species/tomato"):
            fallen = plant_renderer.render_plant_pixmap(
                ObjectType.PERENNIAL, 96.0, "", "tomato", PlantCategory.VEGETABLE)
            assert fallen is not None                       # a sprite, not a bare circle
            assert pixels(fallen) == category_pixmap        # ... the category's
            without_file = painted(item)
        item.plant_species = ""
        plant_renderer.clear_plant_cache()
        as_category = painted(item)

        def apart(a: bytes, b: bytes) -> float:
            """Mean difference of two paintings, in 8-bit levels per channel."""
            return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)

        # the ITEM paints the category sprite (to a rounding level of the scaled
        # pixmap), which is not the sprite it paints when its own file is there
        assert apart(without_file, as_category) < 0.05
        assert apart(without_file, own) > 2.0

    def test_the_rule_is_the_old_one_with_files_missing(self, qtbot) -> None:
        """The differential the golden cannot make (the shipped set is complete): the
        old resolver against the extracted rule AND against the renderer, with every
        sprite file taken away in turn and with larger sets gone — over every fifth
        question (the script's ``--differential`` asks them all: 481,096 comparisons,
        0 mismatches, 2026-10-11)."""
        script = _load_golden_script()
        compared, wrong = script.differential(asked=script.cases()[::5])
        assert wrong == []
        assert compared == 2 * len(script.missing_sets()) * len(script.cases()[::5]) > 90_000

    def test_the_differential_bites(self, qtbot, monkeypatch) -> None:
        """A renderer that forgets to ask whether the file exists is caught."""
        from open_garden_planner.core import plant_renderer

        script = _load_golden_script()
        real = plant_renderer.resolve_sprite

        def forgetful(kind, species="", category=None, **_available):
            return real(kind, species, category)

        monkeypatch.setattr(plant_renderer, "resolve_sprite", forgetful)
        _compared, wrong = script.differential(
            sets=[frozenset([("species", "tomato")])], asked=[("tomato", "PERENNIAL", "VEGETABLE")])
        assert len(wrong) == 1 and wrong[0].startswith("plant_renderer(")

    def test_the_renderer_s_maps_are_the_package_s(self, qtbot) -> None:
        from open_garden_planner.core import plant_renderer
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import PlantCategory

        assert plant_renderer._SPECIES_FILES is SPECIES_SPRITES
        by_category = {PlantCategory[name]: stem for name, stem in CATEGORY_SPRITES.items()}
        assert by_category == plant_renderer._CATEGORY_FILES
        defaults = {ObjectType[kind]: PlantCategory[name]
                    for kind, name in DEFAULT_CATEGORY.items()}
        assert defaults == plant_renderer._OBJECT_TYPE_DEFAULT_CATEGORY
        assert set(CATEGORY_SPRITES) == {category.name for category in PlantCategory}

    def test_plant_kinds_are_the_repo_s_plant_types(self, qtbot) -> None:
        """Drift guard: one answer to "is this a plant?" (the 3D builder registers
        for ``PLANT_KINDS``). Two modules keep a list of their own — the Qt-free
        height model and the agent API — and both are held to it here."""
        from open_garden_planner.agent_api import creates
        from open_garden_planner.core.object_height import _PLANT_TYPE_NAMES
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type

        assert frozenset({"TREE", "SHRUB", "PERENNIAL"}) == PLANT_KINDS
        assert {t.name for t in ObjectType if is_plant_type(t)} == PLANT_KINDS
        assert _PLANT_TYPE_NAMES == PLANT_KINDS
        assert creates._PLANT_TYPE_NAMES == PLANT_KINDS
        assert {t.name for t in ObjectType if creates.is_plant_type_name(t.name)} == PLANT_KINDS

    def test_every_sprite_the_maps_name_has_a_recipe(self) -> None:
        assert set(SPECIES_SPRITES.values()) == set(recipes.SPECIES)
        assert set(CATEGORY_SPRITES.values()) == set(recipes.CATEGORIES)
        assert set(DEFAULT_CATEGORY.values()) <= set(CATEGORY_SPRITES)

    def test_every_sprite_is_reachable_by_its_own_name(self) -> None:
        """What the gallery sets as a plant's species: the file name, spaced."""
        for stem in recipes.SPECIES:
            assert resolve_sprite("PERENNIAL", stem.replace("_", " ")) == SpriteRef("species", stem)
        for name, stem in CATEGORY_SPRITES.items():
            assert resolve_sprite("TREE", "", name) == SpriteRef("categories", stem)

    def test_not_a_plant_resolves_to_nothing(self) -> None:
        assert resolve_sprite("HOUSE", "tomato", "PALM") is None
        assert resolve_recipe("HOUSE", "tomato", "PALM") is None

    def test_an_unknown_category_name_falls_back_to_the_kind_s_default(self) -> None:
        assert resolve_sprite("SHRUB", "", "NO_SUCH_CATEGORY") == SpriteRef(
            "categories", "spreading_shrub")

    def test_an_unavailable_sprite_falls_through_like_a_missing_file(self) -> None:
        """The old resolver went on to the next rule when a mapped file did not
        exist. The hook keeps that — for a file (2D) or for a recipe (3D)."""
        def without(*missing: str):
            return lambda sprite: sprite.name not in missing

        assert resolve_sprite("TREE", "tomato", "PALM") == SpriteRef("species", "tomato")
        # the exact key is gone: the partial match finds the next key that fits
        assert resolve_sprite("TREE", "apple tree", available=without("apple_tree")) == SpriteRef(
            "categories", "round_deciduous")
        assert resolve_sprite("TREE", "cherry", available=without("cherry_tree")) == SpriteRef(
            "categories", "round_deciduous")
        # no species sprite: the category; no category sprite: the kind's default; then nothing
        assert resolve_sprite("TREE", "tomato", "PALM", available=without("tomato")) == SpriteRef(
            "categories", "palm")
        assert resolve_sprite("TREE", "tomato", "PALM",
                              available=without("tomato", "palm")) == SpriteRef(
            "categories", "round_deciduous")
        assert resolve_sprite("TREE", "tomato", "PALM",
                              available=without("tomato", "palm", "round_deciduous")) is None

    def test_the_partial_match_keeps_its_2d_quirks(self) -> None:
        """Not a wish list: the 2D renderer draws these today, so 3D builds them."""
        assert resolve_sprite("PERENNIAL", "Lemon Balm") == SpriteRef("species", "lemon_tree")
        assert resolve_sprite("PERENNIAL", "Melon") == SpriteRef("species", "eggplant")
        assert resolve_sprite("PERENNIAL", " \t ") == SpriteRef("species", "rose")
        assert resolve_sprite("PERENNIAL", "Echinacea") == SpriteRef(
            "categories", "flowering_perennial")

    def test_recipe_for_and_resolve_recipe(self) -> None:
        assert recipe_for(SpriteRef("species", "tomato")) is recipes.SPECIES["tomato"]
        assert recipe_for(SpriteRef("categories", "palm")) is recipes.CATEGORIES["palm"]
        with pytest.raises(KeyError):
            recipe_for(SpriteRef("species", "no_such_sprite"))
        sprite, recipe = resolve_recipe("TREE", "Apple Tree", None) or (None, None)
        assert sprite == SpriteRef("species", "apple_tree") and recipe is recipes.SPECIES["apple_tree"]

    def test_every_bundled_species_resolves_to_a_recipe(self, qtbot) -> None:
        """Gate G4, the data half: each of the bundled species reaches a recipe,
        and it is the recipe of the sprite the 2D renderer draws for it."""
        from open_garden_planner.core import plant_renderer
        from open_garden_planner.core.object_types import ObjectType

        plants = json.loads(BUNDLED.read_text(encoding="utf-8"))["plants"]
        assert len(plants) == 118
        species_sprites = 0
        for record in plants:
            name = record["common_name"]
            for kind in sorted(PLANT_KINDS):
                resolved = resolve_recipe(kind, name, None)
                assert resolved is not None, name
                sprite, recipe = resolved
                assert recipe["a"] in ARCHETYPES
                path = plant_renderer._resolve_svg_path(ObjectType[kind], name, None)
                assert path is not None
                assert (path.parent.name, path.stem) == (sprite.group, sprite.name), name
            species_sprites += resolved[0].group == "species"
        assert species_sprites == 106  # the other 12 take their item type's category


# ── the spike keeps a copy until L1.10 ────────────────────────────────────────


class TestSpikeCopy:
    def test_palette_copy_equals_the_shared_table(self) -> None:
        """Drift guard (dies with the spike in L1.10): nobody tunes one of them."""
        from open_garden_planner.spike_q3d import meshes as spike

        assert set(spike.PALETTES) == set(recipes.PALETTES)
        for name, palette in recipes.PALETTES.items():
            assert spike.PALETTES[name] == (
                palette["t0"], palette["t1"], palette["b0"], palette["b1"]), name

    def test_accent_copy_is_made_of_shared_colours(self) -> None:
        from open_garden_planner.spike_q3d import meshes as spike

        shared = {triad[1] for triad in recipes.FRUITS.values()} | {
            spec[0] for spec in recipes.FLOWERS.values()
        }
        assert set(spike.ACCENTS.values()) <= shared
