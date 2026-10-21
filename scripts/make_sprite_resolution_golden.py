"""The provenance of ``tests/fixtures/plant_art/sprite_resolution_golden.json``.

Phase 17 L1.7 (#385) moved the rule that picks a plant's 2D sprite out of
``core/plant_renderer.py`` into ``core/plant_art/resolve.py`` so that the 3D plant
builder asks the SAME rule. The golden file is what the renderer's resolver
answered BEFORE the move, and this script is how it was — and is — made:

- ``reference_resolve`` is that resolver, as it stood in ``core/plant_renderer.py``
  at commit ``aaec048`` (the last one before the move), statement for statement.
  Only its three inputs are parameters here: the species map, the category maps
  and "does this sprite's file exist". The maps themselves moved without a
  change of content or order (pinned by the golden: it was first written from
  the real ``aaec048`` code, in the commit before the move).
- ``cases`` is the question list: every key of the species map (as it is, in
  title case, upper-cased with blanks), every bundled species' common and
  scientific name, every sprite stem as the gallery writes it and as a file
  name, a handful of odd strings, three item kinds that are plants and two that
  are not, and every category.
- ``golden_text`` is the file: one JSON row ``[species, kind, category, answer]``
  per case, every sprite file present.
- ``differential`` holds the extracted rule against the reference with files
  MISSING — the half the golden cannot show, because the shipped set is
  complete: every sprite removed in turn, then random sets of 2 … 40 sprites,
  then all species sprites, then all category sprites. Both the pure function
  (``resolve_sprite`` with an ``available`` predicate) and the renderer itself
  (``_resolve_svg_path`` with ``Path.exists`` patched) are compared.

**#446 changed the rule, so the reference changed with it.** The old rule
matched a species name by substring; it is kept here as ``legacy_resolve``,
statement for statement, and ``--legacy-diff`` prints what the change does to
every case — the before / after of a rule that decides what a plant looks like
in 2D *and* in 3D. The golden is written from the CURRENT rule
(``reference_resolve``); the legacy rule is what it replaced.

Usage:
    venv/Scripts/python.exe scripts/make_sprite_resolution_golden.py            # write the golden
    venv/Scripts/python.exe scripts/make_sprite_resolution_golden.py --check    # compare, exit 1 on drift
    venv/Scripts/python.exe scripts/make_sprite_resolution_golden.py --differential
    venv/Scripts/python.exe scripts/make_sprite_resolution_golden.py --legacy-diff
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
# This checkout's source tree, whatever else is installed.
sys.path.insert(0, str(REPO / "src"))

from open_garden_planner.core.plant_art.resolve import (  # noqa: E402
    CATEGORY_SPRITES,
    DEFAULT_CATEGORY,
    SPECIES_SPRITES,
    SpriteRef,
    resolve_sprite,
)

GOLDEN = REPO / "tests" / "fixtures" / "plant_art" / "sprite_resolution_golden.json"
PLANTS = REPO / "src" / "open_garden_planner" / "resources" / "plants"
BUNDLED = REPO / "src" / "open_garden_planner" / "resources" / "data" / "plant_species.json"

Exists = Callable[[str, str], bool]          # (group, stem) -> is there a sprite file
Case = tuple[str, str, "str | None"]         # (species, kind, category)

KINDS = ("TREE", "SHRUB", "PERENNIAL", "HOUSE", "GARDEN_BED")
ODD = [
    "", " ", " \t ", "a", "e", "ee", "tree", "xyz", "no such plant", "Bean (Bush)", "ROSE",
    " Rose ", "rosé", "apple-tree", "Solanum", "prunus persica 'Redhaven'", "Sweet Cherry",
    "blackcurrant bush", "ß", "İris", "Wild Rose Hip", "bay", "box", "mum", "pea",
    "peach", "pear", "plum", "elder", "Elderflower", "lemon balm", "melon", "sweet potato",
    "kiwi", "palm", "hedge", "grass", "fern", "strawberry", "Round Deciduous", "conifer",
]


def _reference_candidates(species: str, species_files: Mapping[str, str]) -> list[str]:
    """The sprite stems a species name can mean, best first — the current rule
    (#446), statement for statement with ``core.plant_art.resolve.species_candidates``.

    1. the whole name (normalised: lower case, blanks collapsed, ``-`` and
       ``_`` read as blanks);
    2. a key whose every word is a word of the name — the key with the most
       words wins, then the longest key, then the table's order;
    3. a key that holds every word of the name — the key with the fewest extra
       words wins, then the table's order.
    """
    if not species:
        return []
    wanted = re.sub(r"[\s\-_]+", " ", species.lower()).strip()
    if not wanted:
        return []
    found: list[str] = []
    normalised, keyed = _normalised_index(species_files)
    exact = normalised.get(wanted)
    if exact is not None:
        found.append(exact)
    words = frozenset(wanted.split())
    contained = sorted(
        ((len(key_words), length, index, stem)
         for index, (key_words, length, stem) in enumerate(keyed)
         if key_words <= words),
        key=lambda row: (-row[0], -row[1], row[2]),
    )
    found.extend(row[3] for row in contained)
    supersets = sorted(
        ((len(key_words) - len(words), index, stem)
         for index, (key_words, _length, stem) in enumerate(keyed)
         if words <= key_words),
        key=lambda row: (row[0], row[1]),
    )
    found.extend(row[2] for row in supersets)
    return list(dict.fromkeys(found))


_INDEX_CACHE: dict[int, tuple[dict[str, str], tuple[tuple[frozenset[str], int, str], ...]]] = {}


def _normalised_index(
    species_files: Mapping[str, str],
) -> tuple[dict[str, str], tuple[tuple[frozenset[str], int, str], ...]]:
    """(normalised key -> sprite, every key as (words, length, sprite)), cached
    per map: the differential asks this hundreds of thousands of times."""
    cached = _INDEX_CACHE.get(id(species_files))
    if cached is not None:
        return cached
    normalised: dict[str, str] = {}
    words: list[tuple[frozenset[str], int, str]] = []
    for key, stem in species_files.items():
        folded = re.sub(r"[\s\-_]+", " ", key.lower()).strip()
        normalised.setdefault(folded, stem)
        words.append((frozenset(folded.split()), len(folded), stem))
    built = (normalised, tuple(words))
    _INDEX_CACHE[id(species_files)] = built
    return built


def reference_resolve(
    kind: str,
    species: str,
    category: str | None,
    exists: Exists,
    species_files: Mapping[str, str] = SPECIES_SPRITES,
    category_files: Mapping[str, str] = CATEGORY_SPRITES,
    default_category: Mapping[str, str] = DEFAULT_CATEGORY,
) -> str | None:
    """The CURRENT rule (#446) as ``"<group>/<stem>"``, or None. Kept statement
    for statement (which is why it reads the way it does); enum members are
    their names here."""
    if kind not in default_category:
        return None

    # 1. Try species-specific SVG
    for stem in _reference_candidates(species, species_files):
        if exists("species", stem):
            return f"species/{stem}"

    # 2. Try category SVG
    if category is not None:
        filename = category_files.get(category)
        if filename and exists("categories", filename):
            return f"categories/{filename}"

    # 3. Fall back to default category based on ObjectType
    fallback = default_category.get(kind)
    if fallback:
        filename = category_files.get(fallback)
        if filename and exists("categories", filename):
            return f"categories/{filename}"

    return None


def legacy_resolve(
    kind: str,
    species: str,
    category: str | None,
    exists: Exists,
    species_files: Mapping[str, str] = SPECIES_SPRITES,
    category_files: Mapping[str, str] = CATEGORY_SPRITES,
    default_category: Mapping[str, str] = DEFAULT_CATEGORY,
) -> str | None:
    """The rule #446 replaced: the substring match, statement for statement.

    Kept so the change can be measured rather than asserted — ``--legacy-diff``
    prints what the new rule answers against what this one answered, for every
    case of the golden.
    """
    if kind not in default_category:
        return None

    # 1. Try species-specific SVG
    if species:
        species_lower = species.lower().strip()
        # Check direct match first
        if species_lower in species_files and exists("species", species_files[species_lower]):
            return f"species/{species_files[species_lower]}"
        # Check partial match (species name contains a known key)
        for key, filename in species_files.items():
            if (key in species_lower or species_lower in key) and exists("species", filename):
                return f"species/{filename}"

    # 2. Try category SVG
    if category is not None:
        filename = category_files.get(category)
        if filename and exists("categories", filename):
            return f"categories/{filename}"

    # 3. Fall back to default category based on ObjectType
    fallback = default_category.get(kind)
    if fallback:
        filename = category_files.get(fallback)
        if filename and exists("categories", filename):
            return f"categories/{filename}"

    return None


def legacy_diff() -> list[tuple[str, str, str | None, str | None, str | None]]:
    """``(species, kind, category, legacy answer, current answer)`` for every
    case the two rules answer differently."""
    rows = []
    for name, kind, category in cases():
        was = legacy_resolve(kind, name, category, file_exists)
        now = reference_resolve(kind, name, category, file_exists)
        if was != now:
            rows.append((name, kind, category, was, now))
    return rows


def species_strings() -> list[str]:
    bundled = json.loads(BUNDLED.read_text(encoding="utf-8"))["plants"]
    stems = sorted(path.stem for path in (PLANTS / "species").glob("*.svg"))
    keys = list(SPECIES_SPRITES)
    strings = [*keys, *(key.title() for key in keys), *(f"  {key.upper()} " for key in keys[::7]),
               *(str(record.get("common_name") or "") for record in bundled),
               *(str(record.get("scientific_name") or "") for record in bundled),
               *(stem.replace("_", " ") for stem in stems),       # what the gallery sets
               *stems, *ODD]
    return list(dict.fromkeys(strings))


def cases() -> list[Case]:
    """The questions, in the golden file's order."""
    asked: list[Case] = []
    for name in species_strings():
        asked.append((name, "TREE", None))
        asked.append((name, "PERENNIAL", "PALM"))
    for name in ("", "no such plant", " \t "):
        for kind in KINDS:
            for category in (None, *CATEGORY_SPRITES):
                if (name, kind, category) not in asked:
                    asked.append((name, kind, category))
    return asked


def file_exists(group: str, stem: str) -> bool:
    return (PLANTS / group / f"{stem}.svg").exists()


def golden_text() -> str:
    rows = [[name, kind, category, reference_resolve(kind, name, category, file_exists)]
            for name, kind, category in cases()]
    return "[\n" + ",\n".join(json.dumps(row, ensure_ascii=True) for row in rows) + "\n]\n"


def all_sprites() -> list[tuple[str, str]]:
    return ([("species", stem) for stem in dict.fromkeys(SPECIES_SPRITES.values())]
            + [("categories", stem) for stem in dict.fromkeys(CATEGORY_SPRITES.values())])


def missing_sets(seed: int = 385) -> list[frozenset[tuple[str, str]]]:
    """Which sprite files are taken away, one set per differential pass."""
    sprites = all_sprites()
    rng = random.Random(seed)  # noqa: S311 - a reproducible sample, nothing secret
    sets = [frozenset([sprite]) for sprite in sprites]
    sets += [frozenset(rng.sample(sprites, count)) for count in (2, 3, 5, 8, 13, 21, 40) for _ in range(4)]
    sets.append(frozenset(sprite for sprite in sprites if sprite[0] == "species"))
    sets.append(frozenset(sprite for sprite in sprites if sprite[0] == "categories"))
    sets.append(frozenset(sprites))
    return sets


def extracted_answer(kind: str, species: str, category: str | None,
                     missing: frozenset[tuple[str, str]]) -> str | None:
    """The extracted rule's answer with ``missing`` sprites unavailable."""
    sprite = resolve_sprite(kind, species, category,
                            available=lambda ref: (ref.group, ref.name) not in missing)
    return None if sprite is None else f"{sprite.group}/{sprite.name}"


def renderer_answer(kind: str, species: str, category: str | None,
                    missing: frozenset[tuple[str, str]]) -> str | None:
    """The 2D renderer's own answer with the ``missing`` sprites' files gone
    (``Path.exists`` patched; the renderer's memo is bypassed)."""
    from open_garden_planner.core import plant_renderer
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.core.plant_renderer import PlantCategory

    gone = {PLANTS / group / f"{stem}.svg" for group, stem in missing}
    real_exists = Path.exists

    def exists(path: Path, *args: object, **kwargs: object) -> bool:
        return False if path in gone else real_exists(path, *args, **kwargs)  # type: ignore[arg-type]

    with patch.object(Path, "exists", exists):
        found = plant_renderer._resolve_svg_path.__wrapped__(
            ObjectType[kind], species, PlantCategory[category] if category else None)
    return None if found is None else f"{found.parent.name}/{found.stem}"


def differential(sets: Iterable[frozenset[tuple[str, str]]] | None = None,
                 asked: list[Case] | None = None, renderer: bool = True) -> tuple[int, list[str]]:
    """(comparisons made, mismatches) of the extracted rule — and, with
    ``renderer``, of the 2D renderer — against ``reference_resolve``."""
    asked = cases() if asked is None else asked
    compared, wrong = 0, []
    for missing in (missing_sets() if sets is None else sets):
        for name, kind, category in asked:
            expected = reference_resolve(kind, name, category,
                                         lambda group, stem, gone=missing: (group, stem) not in gone)
            answers = {"resolve_sprite": extracted_answer(kind, name, category, missing)}
            if renderer:
                answers["plant_renderer"] = renderer_answer(kind, name, category, missing)
            for who, got in answers.items():
                compared += 1
                if got != expected:
                    wrong.append(f"{who}({kind}, {name!r}, {category}) without {sorted(missing)[:3]}"
                                 f"{'…' if len(missing) > 3 else ''}: {got} != {expected}")
    return compared, wrong


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="compare with the committed golden")
    parser.add_argument("--differential", action="store_true",
                        help="old rule vs extracted rule vs renderer, with sprite files missing")
    parser.add_argument("--legacy-diff", action="store_true",
                        help="the rule #446 replaced vs the current rule, for every case")
    args = parser.parse_args()
    if args.legacy_diff:
        rows = legacy_diff()
        for name, kind, category, was, now in rows:
            print(f"{name!r} [{kind}{'' if category is None else f'/{category}'}]: "
                  f"{was} -> {now}")
        print(f"{len(rows)} of {len(cases())} cases answer differently")
        return 0
    if args.differential:
        compared, wrong = differential()
        for line in wrong[:20]:
            print("MISMATCH", line)
        print(f"{compared} comparisons over {len(missing_sets())} sets of missing sprites, "
              f"{len(wrong)} mismatches")
        return 1 if wrong else 0
    text = golden_text()
    if args.check:
        same = GOLDEN.read_text(encoding="utf-8") == text
        print(f"OK: the golden is what the reference resolver answers ({len(cases())} rows)"
              if same else "DRIFT: the golden differs from the reference resolver's answers")
        return 0 if same else 1
    GOLDEN.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {len(cases())} rows to {GOLDEN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# kept importable for the tests: tests/unit/test_plant_art.py loads this file by path
__all__ = ["SpriteRef", "cases", "differential", "golden_text", "legacy_diff", "legacy_resolve",
           "missing_sets", "reference_resolve"]
