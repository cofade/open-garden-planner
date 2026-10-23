"""Mutation check for the plant art — tables, sprite rule and 3D plant builder (Phase 17 L1.7, #385).

A green suite says the tests pass. It does not say they would FAIL if the code
were wrong. The first version of the plant builder passed every gate it had set
itself while a squash was built 1.6 times too tall and squashed back, a lavender
floated 9 cm above the ground, and dropping the renderer's "is the file there"
survived 3,048 tests. This script asks the second question directly: it breaks
ONE rule at a time and runs the tests that are supposed to notice. Every mutant
must be KILLED — pytest exits with code 1 ("tests ran and some failed") AND
names a FAILED test. A SURVIVED mutant is a rule no test pins; a pattern that no
longer matches exactly once is STALE — a mutant that silently stopped mutating
proves nothing; and any other outcome is BROKEN: pytest exiting with 2
(interrupted, a collection error), 3 (internal error), 4 (usage: a test id that
does not exist any more) or 5 (nothing collected) is a run that did not test
the mutant, and "any non-zero exit" used to count it as a kill (review round 3;
the fix is the scene-contract script's, ``scripts/mutation_check_scene3d.py``).

How it works: the tree (``src/``, ``tests/``, ``scripts/``, ``pyproject.toml``)
is copied ONCE into a temporary directory; each mutant is one or more textual
replacements in one file OF THAT COPY, undone after its test run. The checkout
is never written to, so it is safe to run next to a test run or with uncommitted
work — what is tested is the working tree as it is on disk.

It is NOT part of the test suite (it takes about an hour on a busy machine). Run it by hand
after changing ``core/plant_art/``, ``core/scene3d/builders/plants.py``, the
plant lines of ``ui/view3d/snapshot.py``, ``core/plant_renderer.py``'s resolver,
or their tests::

    venv/Scripts/python.exe scripts/mutation_check_plant_art.py            # all mutants
    venv/Scripts/python.exe scripts/mutation_check_plant_art.py --list     # names only
    venv/Scripts/python.exe scripts/mutation_check_plant_art.py --stale    # patterns only, no tests
    venv/Scripts/python.exe scripts/mutation_check_plant_art.py -k leaf    # a subset
    venv/Scripts/python.exe scripts/mutation_check_plant_art.py --tests integration/   # by test file

Exit code 0: every mutant killed. 1: a mutant survived, is stale or its run was broken.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = "src/open_garden_planner/"

RESOLVE = SRC + "core/plant_art/resolve.py"
RECIPES = SRC + "core/plant_art/recipes.py"
RENDERER = SRC + "core/plant_renderer.py"
PLANTS = SRC + "core/scene3d/builders/plants.py"
MESH = SRC + "core/scene3d/mesh.py"
SNAPSHOT = SRC + "ui/view3d/snapshot.py"
GENERATOR = "scripts/generate_plant_sprites.py"
MEASURE = "scripts/measure_plant_art_3d.py"

ART = ("tests/unit/test_plant_art.py", "tests/unit/test_plant_sprite_conformance.py::TestDeterminism")
UNIT = ("tests/unit/test_scene3d_plants.py",)
PIPE = ("tests/integration/test_scene3d_plants.py",)
PERF = ("tests/perf/test_scene3d_plants_budget.py",)


@dataclass(frozen=True)
class Mutant:
    """One broken rule: in ``path``, replace each ``old`` by its ``new``; ``tests`` must fail."""

    label: str
    path: str
    edits: tuple[tuple[str, str], ...]
    tests: tuple[str, ...]


def one(label: str, path: str, old: str, new: str, tests: tuple[str, ...]) -> Mutant:
    return Mutant(label, path, ((old, new),), tests)


MUTANTS: tuple[Mutant, ...] = (
    # ── the sprite rule and the tables (core/plant_art) ──────────────────────
    one("the species sprite is never used", RESOLVE,
        "    for stem in species_candidates(species):", "    for stem in ():", ART),
    one("a name that CONTAINS a key is not matched", RESOLVE,
        "if key_words <= words)", "if False)", ART),
    one("a key that CONTAINS the name is not matched", RESOLVE,
        "if words <= key_words)", "if False)", ART),
    one("the most specific key does not win", RESOLVE,
        "key=lambda row: (-row[0], -row[1], row[2]),", "key=lambda row: (row[2],),", ART),
    one("the species string is not stripped", RESOLVE,
        're.sub(r"[\\s\\-_]+", " ", name.lower()).strip()', 're.sub(r"[\\s\\-_]+", " ", name.lower())',
        ART),
    one("the species string is not lower-cased", RESOLVE,
        're.sub(r"[\\s\\-_]+", " ", name.lower())', 're.sub(r"[\\s\\-_]+", " ", name)', ART),
    one("the separators are not read as blanks", RESOLVE,
        're.sub(r"[\\s\\-_]+", " ", name.lower())', 're.sub(r"\\s+", " ", name.lower())', ART),
    one("availability is ignored by the rule", RESOLVE,
        "return sprite if available is None or available(sprite) else None", "return sprite", ART),
    one("a tree's default sprite is the conifer", RESOLVE,
        '"TREE": "ROUND_DECIDUOUS",', '"TREE": "CONIFER",', ART),
    one("the species map is reordered (first partial match wins)", RESOLVE,
        '    "rose": "rose",\n    "rosa": "rose",\n    "lavender": "lavender",',
        '    "lavender": "lavender",\n    "rose": "rose",\n    "rosa": "rose",', ART),
    one("a non-plant kind among the plant kinds", RESOLVE,
        '    "PERENNIAL": "FLOWERING_PERENNIAL",\n}',
        '    "PERENNIAL": "FLOWERING_PERENNIAL",\n    "GENERIC_CIRCLE": "ROUND_DECIDUOUS",\n}', ART),
    one("a flower colour no sprite uses is edited", RECIPES,
        '"#a98fe0", "#d0c0f0", "#6b46ab"', '"#a98fe1", "#d0c0f0", "#6b46ab"', ART),
    one("a palette anchor is edited", RECIPES, 'pal("#54ab4b",', 'pal("#54ab4c",', ART),
    one("the hedge takes the default palette", RECIPES,
        '    if recipe.get("a") == "hedge":\n        return HEDGE_PALETTE',
        '    if recipe.get("a") == "hedge":\n        return DEFAULT_PALETTE', ART),
    one("plant_art imports numpy", RECIPES,
        "from collections.abc import Mapping", "import numpy\nfrom collections.abc import Mapping", ART),
    # ── the generator and the 2D renderer ───────────────────────────────────
    one("the generator keeps a table of its own", GENERATOR,
        "PALETTES = _RECIPES.PALETTES\n", "PALETTES = dict(_RECIPES.PALETTES)\n", ART),
    one("the generator needs Qt again", GENERATOR,
        "import importlib.util\n", "import importlib.util\n\nimport PyQt6.QtCore  # noqa: F401\n", ART),
    one("the renderer keeps a copy of the species map", RENDERER,
        "_SPECIES_FILES: dict[str, str] = SPECIES_SPRITES",
        "_SPECIES_FILES: dict[str, str] = dict(SPECIES_SPRITES)", ART),
    Mutant("the renderer resolves by a rule of its own", RENDERER, (
        ("    sprite = resolve_sprite(\n        object_type.name,",
         "    sprite = _own_rule(\n        object_type.name,"),
        ("def _sprite_path(sprite: SpriteRef) -> Path:",
         "_own_rule = resolve_sprite\n\n\ndef _sprite_path(sprite: SpriteRef) -> Path:")), ART),
    one("the renderer does not ask whether the sprite's file exists (review P1-1)", RENDERER,
        "        available=lambda candidate: _sprite_path(candidate).exists(),\n", "", ART),
    # ── the measuring script stays out of the developer's stores ─────────────
    # Both are SAFE to run: with the first the test's child process refuses to load a plan
    # (the settings names are not a test key) and never builds a settings object; with the
    # second the names ARE a test key and the profile is the temporary one the test hands
    # over. A mutant that left the names half rebound is deliberately not here — it would
    # open a key next to the developer's real one.
    one("the measuring script does not isolate itself (its loads write the real recent files)", MEASURE,
        "ISOLATED_PROFILE = isolate()\n", "ISOLATED_PROFILE = None\n", PIPE),
    one("the measuring script keeps the profile it was handed", MEASURE,
        "        os.environ[variable] = str(directory)\n", "", PIPE),
    # ── what 3D resolves from (review P1-2, ruling R14) ──────────────────────
    one("the builder resolves from the species data's name", PLANTS,
        "    species = record.params.get(PARAM_SPRITE_SPECIES)\n",
        '    species = record.params.get("species_name")\n', UNIT + PIPE),
    one("the builder resolves from the category only", PLANTS,
        "    species = record.params.get(PARAM_SPRITE_SPECIES)\n", "    species = None\n", PIPE),
    one("the snapshot strips the item's species string", SNAPSHOT,
        "        params[PARAM_SPRITE_SPECIES] = sprite_species  # raw: what the 2D sprite is resolved from\n",
        "        params[PARAM_SPRITE_SPECIES] = sprite_species.strip() or sprite_species\n", PIPE),
    one("the snapshot hands on the species data's name as the sprite string", SNAPSHOT,
        "        params[PARAM_SPRITE_SPECIES] = sprite_species  # raw: what the 2D sprite is resolved from\n",
        "        params[PARAM_SPRITE_SPECIES] = species_name or sprite_species\n", PIPE),
    # ── the fit: truth by scaling ────────────────────────────────────────────
    one("5 % too tall", PLANTS,
        "height / max(top - bottom, 1e-12)", "1.05 * height / max(top - bottom, 1e-12)", UNIT),
    one("15 % too narrow", PLANTS,
        "scale = np.array([radius / max(widest, 1e-12), radius / max(widest, 1e-12),",
        "scale = np.array([0.85 * radius / max(widest, 1e-12), 0.85 * radius / max(widest, 1e-12),", UNIT),
    one("the base is not put on the ground", PLANTS, "        part.pos[:, 2] -= bottom\n", "", UNIT),
    one("the trunk moves with a lopsided crown", PLANTS,
        "    foliage.pos[:, :2] -= shift\n",
        "    foliage.pos[:, :2] -= shift\n    if wood is not None:\n        wood.pos[:, :2] -= 40.0 * shift\n",
        UNIT),
    one("stray foliage is not pulled back onto the canopy circle", PLANTS,
        "    foliage.pos[stray, :2] *= (radius / distance[stray])[:, None]\n", "", UNIT),
    one("normals are not renormalised after the fit", PLANTS,
        "        part.nrm = np.where(length > 1e-12, nrm / np.maximum(length, 1e-12), _UP[None, :])",
        "        part.nrm = nrm + 0.0 * length", UNIT),
    one("a dipping vertex lifts the whole plant", PLANTS,
        "        pressed += int((part.pos[:, 2] < 0.0).sum())\n"
        "        part.pos[:, 2] = np.maximum(part.pos[:, 2], 0.0)\n",
        "        pressed += int((part.pos[:, 2] < 0.0).sum())\n", UNIT),
    # ── the fit's report: the instrument must tell the truth (review P1-3) ───
    one("the report says nothing was pulled back", PLANTS,
        "        clamped_share=float(stray.mean()), clamped_reach=clamped_reach,",
        "        clamped_share=0.0, clamped_reach=1.0,", UNIT),
    one("the report says the builder built to the height", PLANTS,
        "        built_top=built_top, z_scale=float(scale[2]), xy_scale=float(scale[0]),",
        "        built_top=1.0, z_scale=1.0, xy_scale=float(scale[0]),", UNIT),
    one("the report says nothing was pressed onto the ground", PLANTS,
        "        pressed_share=pressed / vertices, set_down=bottom / height,",
        "        pressed_share=0.0, set_down=0.0,", UNIT),
    # ── where a plant ENDS: the fit's last step (review round 2, P1-A) ────────
    one("the fit's last step is skipped: nothing bounds where a vertex ends", PLANTS,
        "    reined = _rein_in(foliage.pos, REACH_MAX * radius)\n",
        "    reined = 0\n", UNIT),
    one("the last step reins in the wood too (a flat face keeps a normal that is not its own)", PLANTS,
        "    reined = _rein_in(foliage.pos, REACH_MAX * radius)\n",
        "    reined = sum(_rein_in(part.pos, REACH_MAX * radius) for part in parts)\n", UNIT),
    one("the last step pulls a vertex straight toward the axis (the box shrinks)", PLANTS,
        "        flat[beyond, major] = np.copysign(kept, flat[beyond, major])\n"
        "        flat[beyond, minor] = np.copysign(np.sqrt(np.maximum(limit * limit - kept * kept, 0.0)),\n"
        "                                          flat[beyond, minor])\n",
        "        flat[beyond] *= (limit / np.hypot(flat[beyond, 0], flat[beyond, 1]))[:, None]\n"
        "        del minor, each, kept\n", UNIT),
    one("the last step shrinks the LARGER coordinate", PLANTS,
        "        major = far.argmax(axis=1)                                # a tie keeps x\n",
        "        major = far.argmin(axis=1)\n", UNIT),
    one("the bound on the reach is the gate and a bit", PLANTS,
        "REACH_MAX: Final = 1.09", "REACH_MAX: Final = 1.12", UNIT),
    one("the report says no plant was reined in", PLANTS,
        "        reach=reach, reined_share=reined / vertices)", "        reach=reach, reined_share=0.0)", UNIT),
    one("the report states the bound, not where the plant ends", PLANTS,
        "        reach=reach, reined_share=reined / vertices)",
        "        reach=REACH_MAX, reined_share=reined / vertices)", UNIT),
    # ── built TO the data (review P1-3) ──────────────────────────────────────
    one("lobes do not top out at the height", PLANTS, "    _top_out(centers, radii, p.height)\n", "", UNIT),
    one("a leaf with no headroom stays standing", PLANTS,
        "    new_slope = keep * slope\n", "    new_slope = slope + 0.0 * keep\n", UNIT),
    one("shell leaves face along the ray, not the surface", PLANTS,
        "    normal = np.where(hit[:, None], (on_surface - centers[lobe]) / radii[lobe] ** 2, reach)",
        "    normal = reach + 0.0 * on_surface + 0.0 * lobe[:, None]", UNIT),
    one("the sole of a lobe on the ground is built", PLANTS,
        "    keep = geo.pos[geo.tri][:, :, 2].max(axis=1) > skin\n",
        "    keep = geo.pos[geo.tri][:, :, 2].max(axis=1) > skin - 1e9\n", UNIT),
    one("a leaf may be longer than the plant is wide", PLANTS,
        "    length = np.minimum(length, _LEAF_LONGEST * radius)\n", "", UNIT),
    one("a leaf at the canopy's edge is not turned", PLANTS,
        "    turn = np.where(inside.any(axis=0), inside.argmax(axis=0), far.argmin(axis=0))\n",
        "    turn = np.zeros(count, np.int64) + 0 * inside.argmax(axis=0) + 0 * far.argmin(axis=0)\n", UNIT),
    one("a blade's arch shortens it", PLANTS,
        "    rise = (f - arch * f ** 3) / (1.0 - arch)\n", "    rise = f - arch * f ** 3\n", UNIT),
    one("the tallest blade is not the plant's height", PLANTS,
        "    height = p.height * tall / float(tall.max())\n", "    height = p.height * tall\n", UNIT),
    one("a folded leaf's bow ignores the plant's height", PLANTS,
        "    lift = np.maximum(np.minimum(bow * length, room), 0.0)[:, None]\n",
        "    lift = np.maximum(bow * length + 0.0 * room, 0.0)[:, None]\n", UNIT),
    one("a folded leaf's ripple ignores the plant's height", PLANTS,
        "    swing = np.minimum(ripple * grown[None, :] * half[:, :, 0], np.minimum(up_room, down_room))",
        "    swing = ripple * grown[None, :] * half[:, :, 0] + 0.0 * up_room * down_room", UNIT),
    one("the crown whorl's tallest leaf stops short of the height", PLANTS,
        "        tall = tall / float(tall.max())\n", "        tall = tall * 1.0\n", UNIT),
    one("outlines of any reach", PLANTS, "_RIM_REACH: Final = 0.97", "_RIM_REACH: Final = 0.40", UNIT),
    one("shell leaves on an envelope, not on the lobes", PLANTS,
        "    distance = np.where(hit, distance, miss) * dice.u(0.96, 1.05, len(reach))",
        "    distance = 0.0 * distance + miss * 0.0 + dice.u(0.70, 1.0, len(reach))", UNIT),
    # ── budget, seed, individuality ──────────────────────────────────────────
    one("a canopy may have 1,200 leaves", PLANTS,
        "p.shell_leaves(300, 18.0, 160, 480)", "p.shell_leaves(300, 18.0, 160, 1200)", UNIT),
    one("every plant has the same seed", PLANTS,
        'item_seed(str(seed) if seed is not None else "", "plant")', 'item_seed("", "plant")', UNIT),
    one("the seed is the item id, not the seed param", PLANTS,
        "    seed = record.params.get(PARAM_SEED)", "    seed = record.item_id", UNIT),
    one("unseeded randomness", PLANTS,
        "self._rng = np.random.Generator(np.random.PCG64(seed))",
        "self._rng = np.random.Generator(np.random.PCG64())", UNIT),
    one("another bit generator behind the dice", PLANTS,
        "self._rng = np.random.Generator(np.random.PCG64(seed))",
        "self._rng = np.random.Generator(np.random.Philox(seed))", UNIT),
    Mutant("every hedge is the same drum", PLANTS, (
        ("bulge, dip = _lumps(d, 0.10), _lumps(d, 0.14)", "bulge, dip = _lumps(d, 0.0), _lumps(d, 0.0)"),
        ("batter = d.uf(0.72, 0.98)", "batter = 1.0 + 0.0 * d.uf(0.72, 0.98)"),
        ("shoulder = d.uf(0.68, 0.90)", "shoulder = 0.86 + 0.0 * d.uf(0.68, 0.90)"),
        ("square = d.uf(0.74, 0.94)", "square = 0.82 + 0.0 * d.uf(0.74, 0.94)"),
        ("lean, low_side = d.uf(0.0, 0.12), d.uf(0.0, _TAU)", "lean, low_side = 0.0 * d.uf(0.0, 0.12), d.uf(0.0, _TAU)"),
    ), UNIT),
    one("the builder reads the transform", PLANTS,
        "                            height, radius)",
        "                            height, radius + record.transform.base_cm)", UNIT),
    # ── archetypes, colours, conventions ─────────────────────────────────────
    one("an unknown archetype becomes a mound", PLANTS,
        '    if archetype not in ARCHETYPE_BUILDERS:\n'
        '        raise ValueError(f"no 3D builder for archetype {archetype!r}")',
        '    if archetype not in ARCHETYPE_BUILDERS:\n        archetype = "mound"', UNIT),
    one("the palm has no builder", PLANTS, '    "palm": _palm,\n', "", UNIT),
    one("perennials are not registered", PLANTS,
        "registry.register_many(sorted(PLANT_KINDS), build_plant)",
        'registry.register_many(["SHRUB", "TREE"], build_plant)', UNIT),
    one("conifers in tip tones", PLANTS, '    "conifer": 0.11,', '    "conifer": 0.90,', UNIT),
    one("a tip weight a little off its derivation", PLANTS, '    "palm": 0.505,', '    "palm": 0.56,', UNIT),
    one("red and blue swapped", PLANTS,
        "rgba[:, :3] = np.clip(_srgb_to_linear(srgb) * geo.shade[:, None], 0.0, 1.0)",
        "rgba[:, :3] = np.clip(_srgb_to_linear(srgb) * geo.shade[:, None], 0.0, 1.0)[:, ::-1]", UNIT),
    one("sRGB decoded with a plain gamma", PLANTS,
        "return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)",
        "return np.asarray(srgb ** 2.2, np.float64)", UNIT),
    one("no wind weight", PLANTS,
        "sway = np.stack([np.clip(foliage.pos[:, 2] / height, 0.0, 1.0),",
        "sway = np.stack([np.zeros(len(foliage.pos)) + 0.0 * height,", UNIT),
    one("the spike's bark literal", PLANTS, 'BARK_SRGB: Final = "#5d432d"', 'BARK_SRGB: Final = "#5a4632"', UNIT),
    one("a head grows its curd (a feature key is read)", PLANTS,
        "    width = 0.70 * p.radius\n",
        '    width = 0.70 * p.radius * (1.3 if p.recipe.get("head") else 1.0)\n', UNIT),
    # ── the placeholder ──────────────────────────────────────────────────────
    one("the placeholder casts a shadow", PLANTS,
        'return (MeshPart(mesh, "vc", casts_shadow=False, name=PART_PLACEHOLDER),)',
        'return (MeshPart(mesh, "vc", casts_shadow=True, name=PART_PLACEHOLDER),)', UNIT),
    Mutant("no height: a guessed 3 m plant", PLANTS, (
        ("        height = _estimated_fallback_cm(record)\n        if height is None:\n            return placeholder_parts(radius)",
         "        height = _estimated_fallback_cm(record) or 300.0\n        if height is None:\n            return placeholder_parts(radius)"),
        ("                            height, radius)",
         "                            height or 300.0, radius)")), UNIT),
    one("the placeholder is 40 % of the diameter high", PLANTS,
        "PLACEHOLDER_HEIGHT_FRACTION: Final = 0.12\nPLACEHOLDER_MAX_HEIGHT_CM: Final = 25.0",
        "PLACEHOLDER_HEIGHT_FRACTION: Final = 0.40\nPLACEHOLDER_MAX_HEIGHT_CM: Final = 2500.0", PIPE),
    one("the placeholder in a leaf green", PLANTS,
        'tone = srgb_to_linear(FLOWERS["white"][0]) * np.float32(PLACEHOLDER_SHADE)',
        'tone = srgb_to_linear(PALETTES["fresh"]["t0"]) * np.float32(PLACEHOLDER_SHADE)', UNIT),
    one("the placeholder has 8 sides", PLANTS,
        "_PLACEHOLDER_SIDES: Final = 48", "_PLACEHOLDER_SIDES: Final = 8", UNIT),
    one("plant_archetype answers for a plant without a canopy circle (review P2-6)", PLANTS,
        "    plant = _plant_of(record)\n    if plant is None:\n        return None\n    if record.height_cm is None:\n        try:",
        "    sprite = plant_sprite(record)\n    if sprite is None:\n        return None\n    plant = (sprite, 1.0)\n    if record.height_cm is None:\n        try:", UNIT),
    # ── the sizes a plant is built at (review round 3) ───────────────────────
    one("a size beyond what a record can hold is built (a mesh of NaNs)", PLANTS,
        "    if not (MIN_SIZE_CM <= height_cm <= MAX_LENGTH_CM and MIN_SIZE_CM <= radius_cm <= MAX_LENGTH_CM):",
        "    if not (MIN_SIZE_CM <= height_cm and MIN_SIZE_CM <= radius_cm):", UNIT),
    one("a size under a micrometre is built (the logarithm overflows)", PLANTS,
        "    if not (MIN_SIZE_CM <= height_cm <= MAX_LENGTH_CM and MIN_SIZE_CM <= radius_cm <= MAX_LENGTH_CM):",
        "    if not (0.0 < height_cm <= MAX_LENGTH_CM and 0.0 < radius_cm <= MAX_LENGTH_CM):", UNIT),
    one("the floor of the sizes is a centimetre (a seedling is refused)", PLANTS,
        "MIN_SIZE_CM: Final = 1e-4", "MIN_SIZE_CM: Final = 1.0", UNIT),
    # ── the shape cache (review P2-1) ────────────────────────────────────────
    one("the cache ignores the proportion", PLANTS,
        "    return round(math.log(height_cm / radius_cm) / math.log(PROPORTION_STEP))",
        "    return 0 * round(math.log(height_cm / radius_cm) / math.log(PROPORTION_STEP))", UNIT),
    one("the cache ignores the seed", PLANTS,
        "    form, own, step = _form(recipe), int(seed), _proportion_step(height_cm, radius_cm)",
        "    form, own, step = _form(recipe), 0 * int(seed), _proportion_step(height_cm, radius_cm)",
        UNIT),
    one("the cache's key ignores a recipe number the builders read", PLANTS,
        '    return _Form(archetype, palette_key(recipe), _number_or_none(recipe.get("leaf_scale")),',
        '    return _Form(archetype, palette_key(recipe), _number_or_none(recipe.get("no_such_key")),', UNIT),
    one("a stretched shape's normals are not renormalised", PLANTS,
        "            normals = _sealed((bent / np.linalg.norm(bent, axis=1, keepdims=True)).astype(np.float32))",
        "            normals = _sealed(bent.astype(np.float32))", UNIT),
    one("a scaled plant's own arrays can be written to", PLANTS,
        "    return np.frombuffer(array.tobytes(), dtype=np.float32).reshape(array.shape)",
        "    return array", UNIT),
    one("a mesh's arrays can be made writeable again (review round 2, P2-6)", MESH,
        "    return np.frombuffer(data, dtype=np.float32).reshape(-1, width)",
        "    array = np.array(values, dtype=np.float32).reshape(-1, width)\n"
        "    array.setflags(write=False)\n    return array", UNIT),
    one("the cache holds nothing (every tick rebuilds)", PLANTS,
        "SHAPE_CACHE_BYTES: Final = 256 * 1024 * 1024", "SHAPE_CACHE_BYTES: Final = 1", UNIT + PERF),
    # ── the cache at its cap (review round 2, P2-2) ──────────────────────────
    one("at its cap the cache is plain least-recently-used (the cliff)", PLANTS,
        "            if before is not None and self._asked.get(oldest, 0) > before:\n"
        "                return                      # everything held is in use: this one is not held\n",
        "", UNIT),
    one("the cache has no cap", PLANTS,
        "        while self._bytes + size > self._max_bytes:\n            oldest = next(iter(self._held))",
        "        while False and self._bytes + size > self._max_bytes:\n            oldest = next(iter(self._held))",
        UNIT),
    one("a shape that was found is not marked as asked for", PLANTS,
        "                self._held.move_to_end(key)\n", "", UNIT),
    one("the cache forgets when a shape was asked for", PLANTS,
        "            before = self._asked.pop(key, None)\n",
        "            before = self._asked.pop(key, None) and None\n", UNIT),
    one("a shape larger than the cap empties the cache", PLANTS,
        "        if key in self._held or size > self._max_bytes:\n", "        if key in self._held:\n", UNIT),
    one("clearing the cache keeps the request log", PLANTS,
        "            self._held.clear()\n            self._asked.clear()\n",
        "            self._held.clear()\n", UNIT),
    one("a smaller cap drops nothing", PLANTS,
        "            while self._held and self._bytes > self._max_bytes:\n",
        "            while False and self._bytes > self._max_bytes:\n", UNIT),
    # ── a growing plant stays the plant it was (review round 2, P2-7) ────────
    Mutant("a conifer rolls its dice per whorl it has (another tree at each new whorl)", PLANTS, (
        ("    sits, reaches, cuts = d.u(-0.18, 0.18, most), d.u(0.84, 1.0, most), d.u(0.52, 0.70, most)\n",
         "    sits, reaches, cuts = d.u(-0.18, 0.18, tiers), d.u(0.84, 1.0, tiers), d.u(0.52, 0.70, tiers)\n"),
        ("    hangs, turns = d.u(0.05, 0.18, most), d.u(0.0, _TAU, most)\n",
         "    hangs, turns = d.u(0.05, 0.18, tiers), d.u(0.0, _TAU, tiers)\n")), UNIT),
)


def copy_tree(target: Path) -> None:
    skip = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
    for name in ("src", "tests", "scripts"):
        shutil.copytree(REPO / name, target / name, ignore=skip)
    shutil.copy2(REPO / "pyproject.toml", target / "pyproject.toml")


def stale(mutant: Mutant, root: Path) -> str:
    """Why the mutant's patterns no longer fit, or '' when each matches exactly once."""
    text = (root / mutant.path).read_text(encoding="utf-8").replace("\r\n", "\n")
    for old, _new in mutant.edits:
        if text.count(old) != 1:
            return f"pattern found {text.count(old)}x in {mutant.path}: {old[:60]!r}"
    return ""


#: pytest's exit code for "tests were collected and run, and some failed".
PYTEST_TESTS_FAILED = 1


def failed_test_of(output: str) -> str:
    """The first ``FAILED tests/…`` line of a pytest run's output, or ''."""
    return next((line for line in output.splitlines() if line.startswith("FAILED tests")), "")


def verdict_of(returncode: int, failed_test: str) -> str:
    """What a pytest run says about a mutant. KILLED needs BOTH: exit code 1 and a
    test pytest names as FAILED. Exit code 0 is SURVIVED; everything else — another
    exit code, or code 1 without a failed test (errors only) — is BROKEN."""
    if returncode == 0:
        return "SURVIVED"
    return "KILLED" if returncode == PYTEST_TESTS_FAILED and failed_test else "BROKEN"


def run(mutant: Mutant, root: Path) -> tuple[str, str]:
    """``(verdict, detail)`` — KILLED, SURVIVED, STALE or BROKEN."""
    reason = stale(mutant, root)
    if reason:
        return "STALE", reason
    path = root / mutant.path
    original = path.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")
    for old, new in mutant.edits:
        text = text.replace(old, new)
    try:
        path.write_text(text, encoding="utf-8", newline="")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *mutant.tests, "-q", "-x", "-n", "0", "-p", "no:cacheprovider"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1800, check=False,
        )
    finally:
        path.write_bytes(original)
    lines = proc.stdout.strip().splitlines()
    tail = lines[-1] if lines else proc.stderr.strip()[-200:]
    failed = failed_test_of(proc.stdout)
    verdict = verdict_of(proc.returncode, failed)
    if verdict == "SURVIVED":
        return verdict, tail
    if verdict == "BROKEN":
        return verdict, f"pytest exit code {proc.returncode}, no FAILED test: {tail[:130]}"
    return verdict, failed[:170]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--list", action="store_true", help="print the mutants and exit")
    parser.add_argument("--stale", action="store_true", help="check the patterns only (no tests)")
    parser.add_argument("-k", metavar="TEXT", default="", help="only mutants whose label contains TEXT")
    parser.add_argument("--tests", metavar="TEXT", default="",
                        help="only mutants one of whose test targets contains TEXT (after changing a "
                             "test file: the mutants it is there to kill)")
    args = parser.parse_args(argv)
    chosen = [m for m in MUTANTS if args.k.lower() in m.label.lower()
              and any(args.tests in target for target in m.tests)]
    if args.list:
        for mutant in chosen:
            print(f"{mutant.label}  [{mutant.path}]")
        print(f"{len(chosen)} mutants")
        return 0
    if args.stale:
        reasons = [(m.label, stale(m, REPO)) for m in chosen]
        for label, reason in reasons:
            if reason:
                print(f"STALE    {label}  [{reason}]")
        print(f"{sum(1 for _l, r in reasons if not r)}/{len(chosen)} patterns fit")
        return 1 if any(reason for _label, reason in reasons) else 0
    not_killed = 0
    with tempfile.TemporaryDirectory(prefix="ogp-plant-mutants-") as scratch:
        root = Path(scratch)
        copy_tree(root)
        baseline = subprocess.run(
            [sys.executable, "-m", "pytest", *ART, *UNIT, *PIPE, "-q", "-x", "-n", "0", "-p", "no:cacheprovider"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=3600, check=False)
        last = (baseline.stdout.strip().splitlines() or ["?"])[-1]
        print(f"unmutated copy: {last}", flush=True)
        if baseline.returncode != 0:
            print("refusing to run: the unmutated copy is not green")
            return 2
        for mutant in chosen:
            started = time.perf_counter()
            verdict, detail = run(mutant, root)
            not_killed += verdict != "KILLED"
            print(f"{verdict:<8} {mutant.label}  [{time.perf_counter() - started:.0f} s; {detail}]",
                  flush=True)
    print(f"{len(chosen) - not_killed}/{len(chosen)} mutants killed")
    return 1 if not_killed else 0


if __name__ == "__main__":
    raise SystemExit(main())
