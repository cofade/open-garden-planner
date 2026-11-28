"""Split the single-file functional requirements into prefix-keyed topic files (#1036).

One-off migration, kept for the record and for review: it reads
``docs/functional-requirements.md`` at a git revision and writes
``docs/functional-requirements/*.md`` (and ``3d/*.md``). Each requirement ID goes, with its
text, to the one topic file that owns its prefix (``LAYOUT``). Lines without an ID are
handled by ``RULES``: dropped (chapter history), kept as a section's acceptance paragraph,
or turned into a new numbered entry. The index ``README.md`` is then written by
``scripts/generate_doc_indexes.py``.

The run proves itself (``verify``): every old ID exists exactly once in the new files with
the same words; every new ID is one of the IDs this migration names; every non-blank old
line is an entry line, a heading, or a line of a block that exactly one rule handled; and
every rule handled exactly one block.

    venv/Scripts/python.exe scripts/split_fr_record.py --rev origin/master
    venv/Scripts/python.exe scripts/split_fr_record.py --rev origin/master --verify-only
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OLD_PATH = "docs/functional-requirements.md"
NEW_DIR = Path("docs/functional-requirements")

ID = r"FR-[A-Z0-9]*[A-Z][A-Z0-9]*(?:-[A-Z0-9]*[A-Z][A-Z0-9]*)*-\d+[a-z]?"
ENTRY_RE = re.compile(rf"^- \*\*({ID})(:?)\*\*")
HEAD_ENTRY_RE = re.compile(rf"^#{{3,4}} ({ID}): (.+)$")
HEADING_RE = re.compile(r"^#{1,6} ")
FENCE = "```"


def prefix_of(fid: str) -> str:
    return re.sub(r"-\d+[a-z]?$", "", fid)


def id_key(fid: str) -> tuple[int, str]:
    match = re.search(r"-(\d+)([a-z]?)$", fid)
    assert match, fid
    return int(match.group(1)), match.group(2)


# --- the target layout --------------------------------------------------------------------

@dataclass
class Section:
    title: str | None  # None: no H2 (a one-family 3D file)
    prefixes: list[str]
    after: list[list[str]] = field(default_factory=list)  # acceptance paragraphs


@dataclass
class TopicFile:
    path: str  # relative to NEW_DIR
    title: str
    sections: list[Section]
    intro: str = ""


def _3d(path: str, title: str, prefix: str, intro: str = "") -> TopicFile:
    return TopicFile(f"3d/{path}", title, [Section(None, [prefix])], intro)


LAYOUT: list[TopicFile] = [
    TopicFile("canvas.md", "Canvas", [
        Section("Metric canvas", ["FR-CANVAS"]),
        Section("Grid", ["FR-GRID"]),
        Section("Background images", ["FR-IMG"]),
    ]),
    TopicFile("editing.md", "Drawing and editing", [
        Section("Drawing tools and shape properties", ["FR-DRAW"]),
        Section("Editing operations", ["FR-EDIT"]),
        Section("Split, group drill-down and Esc", ["FR-SPLIT", "FR-DRILL", "FR-GROUP", "FR-TOOL-ESC"]),
    ]),
    TopicFile("precision.md", "Precision", [
        Section("Snapping and alignment", ["FR-SNAP"]),
        Section("Typed coordinate input", ["FR-INPUT"]),
        Section("Reference points", ["FR-REF"]),
        Section("Measurement and units", ["FR-MEAS"]),
    ]),
    TopicFile("objects-layers.md", "Objects and layers", [
        Section("Objects", ["FR-OBJ"]),
        Section("Layers", ["FR-LAYER"]),
        Section("Stacking order", ["FR-STACK"]),
        Section("Garden beds", ["FR-BED"]),
        Section("Vertical and container gardening", ["FR-CONTAINER"]),
    ]),
    TopicFile("plants.md", "Plants", [
        Section("Plant objects and species data", ["FR-PLANT"]),
        Section("Plant guilds", ["FR-GUILD"]),
        Section("Plant lists and favorites", ["FR-LIB"]),
        Section("Plan timeline and plant lifetimes", ["FR-TIMELINE"]),
    ]),
    TopicFile("garden-records.md", "Garden records", [
        Section("Soil health", ["FR-SOIL"]),
        Section("Harvest log", ["FR-HARVEST"]),
        Section("Pest and disease log", ["FR-PEST"]),
        Section("Garden journal", ["FR-JOURNAL"]),
        Section("Shopping list", ["FR-SHOP"]),
        Section("Tasks and reminders", ["FR-TASK"]),
    ]),
    TopicFile("sun-shade.md", "Sun and shade", [
        Section("Solar engine, shadows and sun maps", ["FR-SUN"]),
    ]),
    TopicFile("files-export.md", "Files, export and examples", [
        Section("Project files", ["FR-FILE"]),
        Section("Export", ["FR-EXP"]),
        Section("Import", ["FR-IMP"]),
        Section("Data and download safety", ["FR-SAFETY"]),
        Section("Examples and templates", ["FR-EXAMPLE"]),
    ]),
    TopicFile("ui-look.md", "User interface and look", [
        Section("User interface", ["FR-UI"]),
        Section("Theme, icons and Preferences", ["FR-UI-THEME", "FR-UI-ICON", "FR-UI-PREF"]),
        Section("Sidebar accordion", ["FR-UI-SIDEBAR"]),
        Section("Iconography and the View menu", ["FR-ICON-3C"]),
        Section("Visual rendering", ["FR-VIS"]),
        Section("Plant illustrations", ["FR-PLANT-ART"]),
        Section("Object sprites", ["FR-OBJ-ART"]),
        Section("Textures", ["FR-TEX"]),
        Section("Languages", ["FR-I18N"]),
    ]),
    TopicFile("agent-api.md", "Agent API", [
        Section("Embedded MCP server", ["FR-AGENT"]),
    ]),
    TopicFile("distribution.md", "Distribution", [
        Section("Public download reporting", ["FR-STATS"]),
    ]),
    _3d("analyze.md", "Analyze in 3D", "FR-3D-ANALYZE",
        'One "Analyze" menu in the 3D pane\'s strip (#386, ADR-063).'),
    _3d("built.md", "Built world in 3D", "FR-3D-BUILT",
        "Furniture, structures, buildings and surfaces in 3D (#388, ADR-065)."),
    _3d("forge.md", "Plant Forge", "FR-3D-FORGE",
        "Procedural species models, LODs and phenology (#387, ADR-064)."),
    _3d("ground.md", "3D ground", "FR-3D-GROUND"),
    _3d("live.md", "Living garden", "FR-3D-LIVE",
        "Day and year playback, weather and garden lights (#389, ADR-070)."),
    _3d("look.md", "3D look, sky and motion", "FR-3D-LOOK",
        'Part of the workspace (ADR-059 addendum "looks, sky and the animation policy").'),
    _3d("photo.md", "Photo mode", "FR-3D-PHOTO"),
    _3d("plants.md", "3D plants", "FR-3D-PLANT"),
    _3d("preparation.md", "3D scene preparation", "FR-3D-PREP"),
    _3d("selection.md", "3D selection", "FR-3D-SELECT"),
    _3d("tour.md", "Camera tours", "FR-3D-TOUR"),
    _3d("walk.md", "Walkthrough", "FR-3D-WALK"),
    _3d("workspace.md", "3D workspace", "FR-3D-WS",
        'The plan area of every main window (ADR-060) — no switch; View → "3D View" shows '
        "its 3D pane (FR-SUN-06)."),
]

#: The title of a heading-form entry, with the user-story label of its old heading removed.
HEAD_TITLES = {"FR-SUN-09": "Cached sun-requirement diagnostics (#314)"}

#: The only edits inside an entry's own text: a cross-reference to an old chapter number,
#: which no longer exists, becomes the family it meant. The lossless check compares the
#: words after these replacements, so nothing else may change.
TEXT_FIXES: dict[str, tuple[str, str]] = {
    "FR-SUN-06": ("Detail: FR-33.", "Detail: the FR-3D-* requirements in `3d/`."),
    "FR-UI-ICON-01": ("by FR-30 3c, #310)", "by FR-ICON-3C, #310)"),
}

# --- the rules for lines without an ID -------------------------------------------------------
#
# A rule matches a block (a run of non-blank lines outside an entry) by the start of its first
# line. Actions:
#   ("drop", reason)                     the block is history; the reason goes into the PR
#   ("after", prefix, first_line|None)   the block becomes an acceptance paragraph after the
#                                        section that owns ``prefix``; ``first_line`` replaces
#                                        its first line (a package label removed)
#   ("entries", [(id, [lines])])         the block becomes these new entries (authored text)
#   ("numbered", prefix, first_number)   each "- " bullet of the block becomes the next ID
#   ("table", id, first_line)            a new entry: ``first_line`` then the block, indented

FR13_DROP = "absorbed into FR-OBJ-05 … FR-OBJ-08 after the catalogue check"

RULES: list[tuple[str, tuple]] = [
    ("Detailed functional requirements for Open Garden Planner.",
     ("drop", "replaced by the generated index's preamble")),
    ("Pre-defined object types for common property elements:",
     ("drop", "becomes FR-OBJ-09's lead line")),
    ("| Object Type | Default Properties | Representation |",
     ("table", "FR-OBJ-09", "- **FR-OBJ-09**: Pre-defined object types for common property elements:")),
    ("| Field | Type | Description |",
     ("table", "FR-PLANT-26", "- **FR-PLANT-26**: Plant metadata per instance:")),
    ("```", ("drop", "the ASCII main-window sketch of FR-10.1 is stale; FR-UI-10 describes today's galleries")),
    ("- Category-based thumbnail gallery", ("numbered", "FR-UI", 23)),
    ("- Table (rectangular, round), chair", ("entries", [
        ("FR-OBJ-05", ["- **FR-OBJ-05**: Outdoor furniture: table (rectangular, round), chair, bench, "
                       "parasol/umbrella, lounger, BBQ/grill, fire pit, planter/pot, sandbox, "
                       "trampoline, hot tub, swing, picnic table and hammock."]),
    ])),
    ("- Raised bed, compost bin, greenhouse", ("entries", [
        ("FR-OBJ-06", ["- **FR-OBJ-06**: Garden infrastructure: raised bed, compost bin, greenhouse, "
                       "cold frame, rain barrel, water tap, tool shed, wheelbarrow, pergola, bird "
                       "bath, garden light and string lights."]),
    ])),
    ("- Paths: gravel, stepping stones", ("entries", [
        ("FR-OBJ-07", ["- **FR-OBJ-07**: Path styles: gravel, stepping stones, paved, wooden "
                       "boardwalk and dirt."]),
        ("FR-OBJ-08", ["- **FR-OBJ-08**: Fence styles: wooden, board, metal/wrought iron, chain "
                       "link, hedge (living fence) and stone wall."]),
    ])),
    ("US-B7 (Paper Space MVP) and the FR-LAYOUT-01", ("drop", "retired feature (Paper Space, PR #191)")),
    ("> Scope note: US-C2 builds", ("drop", "delivery scope note of US-C2")),
    ("**Retired (#1009).** Smart Symbols", ("drop", "FR-25 dropped (owner decision 2026-11-26)")),
    ("> **Scope:** US-D1.1", ("drop", "delivery scope note of Package D")),
    ("**US-D1.2 — read/query tools**", ("drop", "user-story group label")),
    ("**US-D1.3 — vision tool**", ("drop", "user-story group label")),
    ("**US-D1.4 — export/save tools**", ("drop", "user-story group label")),
    ("**US-D1.5 — resources + read-analysis prompts**", ("drop", "user-story group label")),
    ("**US-D1.6 — AI client onboarding**", ("drop", "user-story group label")),
    ("**US-E1 — solar position engine**", ("drop", "user-story group label")),
    ("**US-E2 — object height property**", ("drop", "user-story group label")),
    ("**US-E3 — 2D analytic shadow overlay", ("drop", "user-story group label")),
    ("**US-E4 — hours-of-sun heatmap**", ("drop", "user-story group label")),
    ("**US-E6 — the 3D view**", ("drop", "user-story group label")),
    ("**US-E7 — first-person walkthrough**", ("drop", "user-story group label")),
    ("**US-E8 — plant growth over time**", ("drop", "user-story group label")),
    ("**Phase 17 L1.6 — plants stand on their bed**", ("drop", "package group label")),
    ("Acceptance: `tests/integration/test_icon_system.py` + `tests/integration/test_theme_switch_chrome.py`",
     ("after", "FR-UI-THEME", None)),
    ("Acceptance: `tests/unit/test_plant_sprite_conformance.py`", ("after", "FR-PLANT-ART", None)),
    ("Acceptance: `tests/unit/test_object_sprite_conformance.py`", ("after", "FR-OBJ-ART", None)),
    ("Acceptance (FR-TEX-04", ("after", "FR-TEX", None)),
    ("Acceptance: `tests/integration/test_icon_system.py` (every menu action", ("after", "FR-ICON-3C", None)),
    ("Acceptance: `tests/unit/test_stacking.py`", ("after", "FR-STACK", None)),
    ("The 3D view on Qt Quick 3D. Package L1", ("drop", "package history of FR-33")),
    ("Acceptance (L1.7): ", ("after", "FR-3D-PLANT", "strip:Acceptance (L1.7): ")),
    ("The workspace (L1.3, ADR-060).", ("drop", "rewritten as the intro of 3d/workspace.md")),
    ("Acceptance (L1.3): ", ("after", "FR-3D-WS", "strip:Acceptance (L1.3): ")),
    ("Acceptance (L1.8): ", ("after", "FR-3D-SELECT", "strip:Acceptance (L1.8): ")),
    ("Looks, sky and motion (L1.4,", ("drop", "rewritten as the intro of 3d/look.md")),
    ("Acceptance (L1.4): ", ("after", "FR-3D-LOOK", "strip:Acceptance (L1.4): ")),
    ("Acceptance (L7, FR-3D-LOOK-08", ("after", "FR-3D-LOOK", "replace:Acceptance (L7, FR-3D-LOOK-08=Acceptance (FR-3D-LOOK-08")),
    ("Acceptance (L1.5): ", ("after", "FR-3D-GROUND", "strip:Acceptance (L1.5): ")),
    ("Acceptance (L1.9): ", ("after", "FR-3D-WS", "strip:Acceptance (L1.9): ")),
    ("Analyze in 3D (L2, #386, ADR-063).", ("drop", "rewritten as the intro of 3d/analyze.md")),
    ("Acceptance (L2): ", ("after", "FR-3D-ANALYZE", "strip:Acceptance (L2): ")),
    ("Plant Forge: procedural species models", ("drop", "rewritten as the intro of 3d/forge.md")),
    ("Acceptance: `tests/integration/test_plant_forge.py`,", ("after", "FR-3D-FORGE", None)),
    ("The built world complete (L4, #388, ADR-065).", ("drop", "rewritten as the intro of 3d/built.md")),
    ("Acceptance (L4): ", ("after", "FR-3D-BUILT", "strip:Acceptance (L4): ")),
    ("Acceptance (L6): ", ("after", "FR-3D-PHOTO", "strip:Acceptance (L6): ")),
    ("Acceptance (L5): ", ("after", "FR-3D-LIVE", "strip:Acceptance (L5): ")),
    ("ADR-066, `tests/example_specs.py`", ("after", "FR-EXAMPLE", None)),
    ("Owner accepted the chart on 28 October 2026", ("after", "FR-STATS", "replace:Owner accepted the chart on 28 October 2026 (\"perfect\"); section 7.4 owns=Section 7.4 owns")),
    ("Pins: `tests/unit/test_shape_split.py`", ("after", "FR-SPLIT", None)),
]

#: Acceptance paragraphs that cover two families: the second family's file repeats them.
ALSO_AFTER = {
    "Acceptance (L1.8): ": "FR-3D-WALK",
    "Acceptance (L6): ": "FR-3D-TOUR",
}

#: Every ID this migration creates; nothing else may be new.
NEW_IDS = frozenset({
    "FR-OBJ-05", "FR-OBJ-06", "FR-OBJ-07", "FR-OBJ-08", "FR-OBJ-09", "FR-PLANT-26",
    "FR-UI-23", "FR-UI-24", "FR-UI-25", "FR-UI-26", "FR-UI-27", "FR-UI-28",
})


# --- parsing the old file -------------------------------------------------------------------

@dataclass
class Entry:
    id: str
    lines: list[str]  # the entry as written in the new file
    source: list[int]  # the old line indexes it consumed
    words: list[str]  # the old words, for the lossless check


@dataclass
class Block:
    start: int
    lines: list[str]
    indexes: list[int]


def _words(text: str) -> list[str]:
    return text.split()


def parse(lines: list[str]) -> tuple[list[Entry], list[Block], list[int]]:
    """Split the old file into entries, ID-less blocks and heading lines."""
    entries: list[Entry] = []
    blocks: list[Block] = []
    headings: list[int] = []
    n = len(lines)
    i = 0
    while i < n:
        line = lines[i]
        head = HEAD_ENTRY_RE.match(line)
        if head:
            fid = head.group(1)
            title = HEAD_TITLES.get(fid, head.group(2))
            j = i + 1
            while j < n and not HEADING_RE.match(lines[j]) and not ENTRY_RE.match(lines[j]):
                j += 1
            body = lines[i + 1:j]
            while body and not body[-1].strip():
                body.pop()
            while body and not body[0].strip():
                body.pop(0)
            out = [f"- **{fid}**: {title}"]
            if body:
                out.append("")
                out += [("  " + b) if b.strip() else "" for b in body]
            old_words = _words(head.group(2) if fid not in HEAD_TITLES else title)
            old_words += _words("\n".join(body))
            entries.append(Entry(fid, out, list(range(i, j)), ["-", f"**{fid}**:"] + old_words))
            i = j
            continue
        if HEADING_RE.match(line):
            headings.append(i)
            i += 1
            continue
        entry = ENTRY_RE.match(line)
        if entry:
            fid = entry.group(1)
            first = line.replace(f"**{fid}:**", f"**{fid}**:", 1) if entry.group(2) else line
            out = [first]
            source = [i]
            j = i + 1
            while j < n:
                cur = lines[j]
                if not cur.strip():
                    k = j
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and cur is not None and lines[k][:1] in (" ", "\t"):
                        out += [""] * (k - j)
                        source += list(range(j, k))
                        j = k
                        continue
                    break
                if cur[:1] in (" ", "\t"):
                    out.append(cur)
                elif (lines[j - 1].strip() and not ENTRY_RE.match(cur) and not HEADING_RE.match(cur)
                      and not cur.startswith(("- ", "|", ">", FENCE, "**US-", "Acceptance"))):
                    out.append(cur)  # a lazy continuation line
                else:
                    break
                source.append(j)
                j += 1
            old_text = "\n".join(lines[s] for s in source)
            old_text = old_text.replace(f"**{fid}:**", f"**{fid}**:", 1)
            if fid in TEXT_FIXES:
                old, new = TEXT_FIXES[fid]
                hits = [k for k, text in enumerate(out) if old in text]
                if len(hits) != 1 or old_text.count(old) != 1:
                    raise SystemExit(f"{fid}: TEXT_FIXES text {old!r} is not unique in the entry")
                out[hits[0]] = out[hits[0]].replace(old, new)
                old_text = old_text.replace(old, new)
            entries.append(Entry(fid, out, source, _words(old_text)))
            i = j
            continue
        if not line.strip():
            i += 1
            continue
        start = i
        block: list[str] = []
        indexes: list[int] = []
        in_fence = False
        while i < n and (lines[i].strip() or in_fence):
            if lines[i].startswith(FENCE):
                in_fence = not in_fence
            if not in_fence and i > start and (ENTRY_RE.match(lines[i]) or HEADING_RE.match(lines[i])):
                break
            block.append(lines[i])
            indexes.append(i)
            i += 1
        blocks.append(Block(start, block, indexes))
    return entries, blocks, headings


# --- building the new files -----------------------------------------------------------------

def _owner(prefix: str) -> tuple[TopicFile, Section]:
    for topic in LAYOUT:
        for section in topic.sections:
            if prefix in section.prefixes:
                return topic, section
    raise KeyError(f"no topic file owns prefix {prefix}")


def _rewrite_first(block: list[str], how: str | None) -> list[str]:
    if not how:
        return list(block)
    kind, _, arg = how.partition(":")
    first = block[0]
    if kind == "strip":
        assert first.startswith(arg), (first, arg)
        first = "Acceptance: " + first[len(arg):]
    elif kind == "replace":
        old, _, new = arg.partition("=")
        assert old in first, (first, old)
        first = first.replace(old, new, 1)
    return [first] + block[1:]


def build(old_text: str) -> tuple[dict[str, str], dict]:
    """Return ``{relative path: text}`` for every topic file, and the accounting."""
    lines = old_text.splitlines()
    entries, blocks, headings = parse(lines)
    by_id: dict[str, Entry] = {}
    for entry in entries:
        if entry.id in by_id:
            raise SystemExit(f"{entry.id} is defined twice in the old file")
        by_id[entry.id] = entry
    new_entries: dict[str, list[str]] = {}
    used: dict[str, int] = {rule: 0 for rule, _ in RULES}
    handled: set[int] = set()
    dropped: list[tuple[int, str, str]] = []
    for block in blocks:
        matches = [(rule, action) for rule, action in RULES if block.lines[0].startswith(rule)]
        if len(matches) != 1:
            raise SystemExit(
                f"old line {block.start + 1}: {len(matches)} rules match {block.lines[0][:80]!r}"
            )
        rule, action = matches[0]
        used[rule] += 1
        handled.update(block.indexes)
        kind = action[0]
        if kind == "drop":
            dropped.append((block.start + 1, block.lines[0][:70], action[1]))
        elif kind == "after":
            _, prefix, how = action
            paragraph = _rewrite_first(block.lines, how)
            _owner(prefix)[1].after.append(paragraph)
            also = next((p for key, p in ALSO_AFTER.items() if rule.startswith(key)), None)
            if also:
                _owner(also)[1].after.append(paragraph)
        elif kind == "entries":
            for fid, text in action[1]:
                new_entries[fid] = text
        elif kind == "numbered":
            _, prefix, number = action
            current: list[str] = []
            for line in block.lines:
                if line.startswith("- "):
                    current = [f"- **{prefix}-{number:02d}**: {line[2:]}"]
                    new_entries[f"{prefix}-{number:02d}"] = current
                    number += 1
                else:
                    current.append(line)
        elif kind == "table":
            _, fid, first = action
            new_entries[fid] = [first, ""] + ["  " + line for line in block.lines]
        else:
            raise SystemExit(f"unknown rule action {kind!r}")
    unused = [rule for rule, count in used.items() if count != 1]
    if unused:
        raise SystemExit(f"rules not used exactly once: {unused}")
    if set(new_entries) != NEW_IDS:
        raise SystemExit(f"new IDs {sorted(new_entries)} differ from NEW_IDS")

    all_entries: dict[str, list[str]] = {e.id: e.lines for e in entries}
    for fid, text in new_entries.items():
        if fid in all_entries:
            raise SystemExit(f"new ID {fid} already exists")
        all_entries[fid] = text

    files: dict[str, str] = {}
    placed: set[str] = set()
    for topic in LAYOUT:
        prefixes = [p for s in topic.sections for p in s.prefixes]
        out = ["---", f"title: {_json(topic.title)}",
               "prefixes: [" + ", ".join(_json(p) for p in prefixes) + "]", "---", "",
               f"# {topic.title}", ""]
        if topic.intro:
            out += [topic.intro, ""]
        for section in topic.sections:
            if section.title:
                out += [f"## {section.title}", ""]
            ids = sorted((fid for fid in all_entries if prefix_of(fid) in section.prefixes),
                         key=lambda f: (section.prefixes.index(prefix_of(f)), id_key(f)))
            if not ids:
                raise SystemExit(f"{topic.path}: section {section.title!r} has no entries")
            previous_loose = False
            for k, fid in enumerate(ids):
                text = all_entries[fid]
                loose = "" in text
                if k and (loose or previous_loose):
                    out.append("")
                out += text
                previous_loose = loose
                placed.add(fid)
            out.append("")
            for paragraph in section.after:
                out += paragraph + [""]
        while out and not out[-1]:
            out.pop()
        files[topic.path] = "\n".join(out) + "\n"
    missing = set(all_entries) - placed
    if missing:
        raise SystemExit(f"IDs with no topic file: {sorted(missing)}")

    accounted = set(headings) | handled
    for entry in entries:
        accounted.update(entry.source)
    stray = [i + 1 for i, line in enumerate(lines) if line.strip() and i not in accounted]
    if stray:
        raise SystemExit(f"old lines not accounted for: {stray[:20]}")
    report = {
        "entries": entries, "new": sorted(new_entries), "dropped": dropped,
        "headings": len(headings), "blocks": len(blocks),
    }
    return files, report


def _json(value: str) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


# --- verification against the files on disk -------------------------------------------------

DEF_RE = re.compile(rf"^- \*\*({ID})\*\*")


def entries_on_disk(root: Path) -> dict[str, list[str]]:
    """``{id: [lines]}`` for every definition in the topic files, read back from disk."""
    found: dict[str, list[str]] = {}
    for path in sorted((root / NEW_DIR).rglob("*.md")):
        if path.name == "README.md":
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        i = 0
        while i < len(lines):
            match = DEF_RE.match(lines[i])
            if not match:
                i += 1
                continue
            fid = match.group(1)
            if fid in found:
                raise SystemExit(f"{fid} is defined twice in the new files")
            block = [lines[i]]
            j = i + 1
            while j < len(lines):
                cur = lines[j]
                if DEF_RE.match(cur) or cur.startswith("#"):
                    break
                if not cur.strip():
                    k = j
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    if k < len(lines) and lines[k][:1] == " ":
                        j = k
                        continue
                    break
                if cur[:1] != " " and not lines[j - 1].strip():
                    break
                block.append(cur)
                j += 1
            found[fid] = block
            i = j
    return found


def verify(old_text: str, root: Path) -> list[str]:
    errors: list[str] = []
    entries, _, _ = parse(old_text.splitlines())
    disk = entries_on_disk(root)
    for entry in entries:
        if entry.id not in disk:
            errors.append(f"{entry.id} is missing from the topic files")
            continue
        if _words("\n".join(disk[entry.id])) != entry.words:
            errors.append(f"{entry.id}: its words changed in the move")
    extra = set(disk) - {e.id for e in entries} - NEW_IDS
    if extra:
        errors.append(f"IDs that neither existed nor are named new: {sorted(extra)}")
    missing_new = NEW_IDS - set(disk)
    if missing_new:
        errors.append(f"new IDs missing: {sorted(missing_new)}")
    return errors


# --- command line ---------------------------------------------------------------------------

def old_record(rev: str, root: Path) -> str:
    result = subprocess.run(  # fixed git argv; the revision is an operator argument
        ["git", "show", f"{rev}:{OLD_PATH}"], cwd=root, capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"{OLD_PATH} does not exist at {rev}: {result.stderr.decode().strip()}")
    return result.stdout.decode("utf-8").replace("\r\n", "\n")


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rev", required=True, help="git revision that still has the old file")
    parser.add_argument("--verify-only", action="store_true", help="check the files on disk")
    args = parser.parse_args(argv)
    old_text = old_record(args.rev, root)
    files, report = build(old_text)
    if not args.verify_only:
        for rel, text in files.items():
            path = root / NEW_DIR / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {len(files)} topic files")
    errors = verify(old_text, root)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"{len(report['entries'])} IDs moved, {len(report['new'])} new: {', '.join(report['new'])}")
    for fid, (old, new) in TEXT_FIXES.items():
        print(f"text fix in {fid}: {old!r} -> {new!r}")
    print(f"{report['headings']} chapter headings replaced; {report['blocks']} ID-less blocks handled")
    print("dropped:")
    for line, text, reason in report["dropped"]:
        print(f"  old line {line}: {text!r} — {reason}")
    print("lossless proof: every old ID is in exactly one topic file with the same words; "
          "every old line is an entry, a heading, or a block one rule handled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
