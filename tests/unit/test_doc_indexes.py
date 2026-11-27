"""The ADR files and their generated index (#1035, ADR-083).

``scripts/generate_doc_indexes.py --check`` is the gate: this suite runs it against the
real tree, and pins each failure mode on a small tree in ``tmp_path``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name: str) -> ModuleType:
    scripts = str(REPO / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gdi = _load("generate_doc_indexes")


def _adr(root: Path, number: int, title: str = "A decision", *, name: str | None = None,
         front: str | None = None, body: str | None = None) -> Path:
    folder = root / "docs" / "09-architecture-decisions"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name or f"ADR-{number:03d}-{gdi.file_slug(title)}.md")
    if front is None:
        front = f'id: ADR-{number:03d}\ntitle: "{title}"\nstatus: "Accepted"'
    if body is None:
        body = f"# ADR-{number:03d}: {title}\n\n**Status**: Accepted\n"
    path.write_text(f"---\n{front}\n---\n\n{body}", encoding="utf-8")
    return path


def _tree(root: Path, count: int = 3) -> Path:
    for number in range(1, count + 1):
        _adr(root, number, f"Decision {number}")
    assert gdi.write(root) == []
    return root


# --- the real tree ------------------------------------------------------------------------


def test_the_real_adr_files_and_index_pass_the_gate() -> None:
    assert gdi.check(REPO) == []


def test_the_real_record_still_holds_every_migrated_adr() -> None:
    """Guard the guard: the gate must not pass on an empty or half-empty folder."""
    adrs, errors = gdi.load_adrs(REPO)
    assert errors == []
    numbers = [adr.number for adr in adrs]
    assert numbers[:82] == list(range(1, 83))
    legacy = [adr for adr in adrs if adr.legacy_anchor]
    assert len(legacy) == 82, "every ADR from the single-file record keeps its old anchor"


def test_every_legacy_anchor_is_a_stub_in_the_index() -> None:
    index = (REPO / gdi.ADR_INDEX).read_text(encoding="utf-8")
    adrs, _ = gdi.load_adrs(REPO)
    for adr in adrs:
        if adr.legacy_anchor:
            assert f'<a id="{adr.legacy_anchor}"></a>[{adr.id}]({adr.path.name})' in index


def test_known_old_links_resolve_to_their_stub() -> None:
    """Anchors that issue comments and the wiki used before the split (measured 2026-11-27)."""
    index = (REPO / gdi.ADR_INDEX).read_text(encoding="utf-8")
    for anchor in (
        "adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16",
        "adr-069-native-triangulation-and-off-the-gui-thread-3d-preparation-452-531-598",
        "adr-075-cad-editing-keeps-the-group-frame-and-the-command-stack-issues-664-771",
        "adr-017-bed-specific-features-built-centrally-on-gardenitemmixin",
    ):
        assert f'<a id="{anchor}">' in index, anchor


def test_no_tracked_file_links_an_anchor_of_the_old_single_file() -> None:
    """After the split, ``…/README.md#…`` may only name an index stub.

    A permalink to a fixed commit (``blob/<sha>/…#L33``) still resolves there and is exempt.
    """
    import re
    import subprocess

    link = re.compile(
        r"(?<!/[0-9a-f]{40}/docs/)09-architecture-decisions/README\.md#([^\s)\]`'\"<>]+)"
    )
    index = (REPO / gdi.ADR_INDEX).read_text(encoding="utf-8")
    stubs = set(re.findall(r'<a id="([^"]+)"></a>', index))
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, check=True, capture_output=True
    ).stdout.decode("utf-8").split("\0")
    bad = []
    for rel in filter(None, tracked):
        path = REPO / rel
        # the same file types the migration rewrote (scripts/split_adr_record.py)
        if path.suffix.lower() not in {".md", ".py", ".toml", ".txt", ".json", ".yml", ".yaml"}:
            continue
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for anchor in link.findall(text):
            if anchor not in stubs:
                bad.append(f"{rel}: #{anchor}")
    assert bad == []


# --- slugs ----------------------------------------------------------------------------


@pytest.mark.parametrize(("heading", "anchor"), [
    ("ADR-017: Bed-Specific Features Built Centrally on `GardenItemMixin`",
     "adr-017-bed-specific-features-built-centrally-on-gardenitemmixin"),
    ("ADR-035: AI Client Onboarding — Safe Cross-App Config Registration (US-D1.6)",
     "adr-035-ai-client-onboarding--safe-cross-app-config-registration-us-d16"),
    ("Addendum (#414 — one frost anchor per surface, and one date-window entry point)",
     "addendum-414--one-frost-anchor-per-surface-and-one-date-window-entry-point"),
    ("ADR-014: Bundled `plant_species.json` is single source of truth for species + calendar",
     "adr-014-bundled-plant_speciesjson-is-single-source-of-truth-for-species--calendar"),
])
def test_github_slug_matches_anchors_github_rendered(heading: str, anchor: str) -> None:
    assert gdi.github_slug(heading) == anchor


def test_repeated_headings_get_githubs_numeric_suffixes() -> None:
    text = "# T\n\n## Addendum\n\n## Addendum\n\n```\n## not a heading\n```\n\n## Addendum\n"
    assert [a for *_rest, a in gdi.document_anchors(text)] == [
        "t", "addendum", "addendum-1", "addendum-2",
    ]


def test_file_slug_is_ascii_kebab_case_and_capped() -> None:
    slug = gdi.file_slug("Director's cut — one capture path, photo mode, camera tours, "
                         "video and `render_3d_view`")
    assert slug == "directors-cut-one-capture-path-photo-mode-camera-tours-video"
    assert len(slug) <= 60


# --- the gate on a small tree ---------------------------------------------------------------


def test_a_generated_tree_passes(tmp_path: Path) -> None:
    assert gdi.check(_tree(tmp_path)) == []


def test_a_hand_edited_index_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    index = root / gdi.ADR_INDEX
    index.write_text(index.read_text(encoding="utf-8") + "\n## ADR-004: appended by hand\n",
                     encoding="utf-8")
    assert any("stale or was edited by hand" in e for e in gdi.check(root))


def test_a_new_adr_without_regeneration_fails(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    _adr(root, 4, "Decision 4")
    assert any("stale" in e for e in gdi.check(root))


def test_a_gap_in_the_numbers_fails(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One")
    _adr(tmp_path, 3, "Three")
    assert any("ADR-002 is missing" in e for e in gdi.check(tmp_path))


def test_a_duplicate_number_fails(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One")
    _adr(tmp_path, 1, "Uno")
    assert any("more than one file" in e for e in gdi.check(tmp_path))


def test_id_must_match_the_file_name(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One", front='id: ADR-002\ntitle: "One"')
    assert any("does not match the file name" in e for e in gdi.check(tmp_path))


def test_h1_must_match_id_and_title(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One", body="# ADR-001: Another title\n")
    assert any("does not match id and title" in e for e in gdi.check(tmp_path))


def test_the_body_must_open_with_its_only_h1(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One", body="# ADR-001: One\n\n# A second H1\n")
    assert any("only H1" in e for e in gdi.check(tmp_path))


def test_a_demoted_heading_is_not_an_h1(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One", body="## ADR-001: One\n")
    assert any("only H1" in e for e in gdi.check(tmp_path))


def test_a_bad_file_name_fails(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One", name="ADR-001_One.md")
    assert any("file name must be" in e for e in gdi.check(tmp_path))


@pytest.mark.parametrize(("front", "message"), [
    ('id: ADR-001\ntitle: "One"\nowner: "me"', "unknown or malformed field"),
    ('id: ADR-001\ntitle: One', "not a JSON value"),
    ('id: ADR-001\ntitle: "One"\nrefs: "#12"', "non-empty list of strings"),
    ('id: ADR-001\ntitle: "One"\nrefs: []', "non-empty list of strings"),
    ('id: ADR-001\ntitle: ""', "non-empty string"),
    ('id: ADR-001\ntitle: "One"\ntitle: "One"', "duplicate field"),
    ('title: "One"', "missing required field 'id'"),
    ('id: "ADR-001"\ntitle: "One"', "bare token"),
])
def test_malformed_front_matter_fails(tmp_path: Path, front: str, message: str) -> None:
    _adr(tmp_path, 1, "One", front=front)
    assert any(message in e for e in gdi.check(tmp_path)), gdi.check(tmp_path)


def test_superseded_by_must_name_an_existing_adr(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One", front='id: ADR-001\ntitle: "One"\nsuperseded_by: ["ADR-009"]')
    assert any("superseded_by names 'ADR-009'" in e for e in gdi.check(tmp_path))


def test_legacy_anchors_must_be_unique(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One", front='id: ADR-001\ntitle: "One"\nlegacy_anchor: same')
    _adr(tmp_path, 2, "Two", front='id: ADR-002\ntitle: "Two"\nlegacy_anchor: same')
    assert any("legacy_anchor duplicates" in e for e in gdi.check(tmp_path))


def test_front_matter_round_trips() -> None:
    values = {"id": "ADR-007", "title": 'A "quoted" title: with colon',
              "status": "Superseded by ADR-042 | x", "refs": ["#1", "US-F5"],
              "superseded_by": ["ADR-042"], "legacy_anchor": "adr-007-x"}
    parsed, body = gdi.parse_front_matter(gdi.render_front_matter(values) + "\n# body\n")
    assert parsed == values
    assert body == "\n# body\n"


def test_the_index_sorts_by_number_and_escapes_pipes(tmp_path: Path) -> None:
    _adr(tmp_path, 2, "Two", front='id: ADR-002\ntitle: "Two"\nstatus: "Accepted | Context: x"')
    _adr(tmp_path, 1, "One")
    assert gdi.write(tmp_path) == []
    rows = [line for line in (tmp_path / gdi.ADR_INDEX).read_text(encoding="utf-8").splitlines()
            if line.startswith("| [ADR-")]
    assert [row.split("]")[0] for row in rows] == ["| [ADR-001", "| [ADR-002"]
    assert rows[1].endswith("| Two | Accepted |")


@pytest.mark.parametrize(("status", "cell"), [
    ("Accepted (2026-11-20). Shipped in v1.40.11 (PR #981).", "Accepted (2026-11-20)"),
    ("Accepted, 2026-10-08; released v1.29.6, 2026-10-09. Master", "Accepted, 2026-10-08; released v1.29.6, 2026-10-09"),
    ("**Accepted (GO)** (owner) | **Context**: long", "Accepted (GO) (owner)"),
    ("Shipped in [v1.43.0](https://x/v1.43.0) (PR #1021)", "Shipped in v1.43.0 (PR #1021)"),
    ("", "—"),
])
def test_short_status(status: str, cell: str) -> None:
    assert gdi.short_status(status) == cell


def test_short_status_is_capped() -> None:
    cell = gdi.short_status("Accepted " + "word " * 40)
    assert len(cell) <= 90 and cell.endswith(" …")


def test_short_status_never_ends_inside_a_bracket() -> None:
    cell = gdi.short_status("Shipped in v1.42.0 after owner acceptance (2026-11-23; issue #1002; "
                            "PR #1000 and the long tail of follow-up reviews)")
    assert cell == "Shipped in v1.42.0 after owner acceptance …"


# --- the status is the body's ---------------------------------------------------------------


def test_a_status_edited_only_in_the_body_fails_the_gate(tmp_path: Path) -> None:
    """A version sync edits the body's Status line; the front matter must follow (finalize-us)."""
    root = _tree(tmp_path, 1)
    (path,) = (root / "docs" / "09-architecture-decisions").glob("ADR-001-*.md")
    path.write_text(path.read_text(encoding="utf-8").replace(
        "**Status**: Accepted", "**Status**: Shipped in v1.2.3 (PR #9)"), encoding="utf-8")
    assert any("front-matter status differs" in e for e in gdi.check(root))


def test_the_generator_copies_the_body_status_into_front_matter_and_index(tmp_path: Path) -> None:
    root = _tree(tmp_path, 2)
    (path,) = (root / "docs" / "09-architecture-decisions").glob("ADR-001-*.md")
    path.write_text(path.read_text(encoding="utf-8").replace(
        "**Status**: Accepted", "**Status**: **Superseded** by ADR-002 (2026-11-27); see there."),
        encoding="utf-8")
    assert gdi.write(root) == []
    values, body = gdi.parse_front_matter(path.read_text(encoding="utf-8"))
    assert values["status"] == "**Superseded** by ADR-002 (2026-11-27); see there."
    assert values["superseded_by"] == ["ADR-002"]
    assert "**Status**: **Superseded** by ADR-002" in body
    assert "| Superseded by ADR-002 (2026-11-27); see there |" in (
        root / gdi.ADR_INDEX).read_text(encoding="utf-8")
    assert gdi.check(root) == []


def test_a_superseded_status_without_superseded_by_fails(tmp_path: Path) -> None:
    _adr(tmp_path, 1, "One", front='id: ADR-001\ntitle: "One"\nstatus: "Superseded by ADR-002"',
         body="# ADR-001: One\n\n**Status**: Superseded by ADR-002\n")
    _adr(tmp_path, 2, "Two")
    assert any("superseded_by does not match" in e for e in gdi.check(tmp_path))


@pytest.mark.parametrize(("lines", "status"), [
    (["# ADR-001: T", "", "**Status**: Accepted (2026-11-27)", "", "**Context**: x"],
     "Accepted (2026-11-27)"),
    (["# ADR-001: T", "**Status:** Shipped in", "[v1.0](u) (PR #1).", "**Context**: x"],
     "Shipped in [v1.0](u) (PR #1)."),
    (["# ADR-001: T", "", "## Addendum", "", "**Status**: an addendum's own"], ""),
])
def test_status_from_body(lines: list[str], status: str) -> None:
    assert gdi.status_from_body(lines) == status


# --- fences and file names ------------------------------------------------------------------


def test_a_fence_closes_only_on_its_own_marker(tmp_path: Path) -> None:
    """A ``` line inside a ~~~ block does not end it, so a later real H1 is still seen."""
    _adr(tmp_path, 1, "One", body="# ADR-001: One\n\n~~~\n```\n~~~\n\n# A second H1\n")
    assert any("only H1" in e for e in gdi.check(tmp_path))
    text = "# T\n\n   ```json\n# not a heading\n   ```\n"
    assert [raw for _i, _l, raw in gdi.iter_headings(text.splitlines())] == ["T"]


def test_a_lower_case_adr_file_is_not_invisible(tmp_path: Path) -> None:
    _tree(tmp_path, 1)
    folder = tmp_path / "docs" / "09-architecture-decisions"
    (folder / "adr-002-lower.md").write_text("---\nid: ADR-002\n---\n", encoding="utf-8")
    assert any("adr-002-lower.md: file name must be" in e for e in gdi.check(tmp_path))


def test_a_code_span_keeps_its_html_in_the_slug() -> None:
    assert gdi.github_slug("Use `<a id>` stubs") == "use-a-id-stubs"
    assert gdi.github_slug("Use <b>bold</b> text") == "use-bold-text"


# --- the one-off migration ------------------------------------------------------------------


def test_the_split_refuses_to_run_on_an_already_split_record() -> None:
    """After #1035 the ADR files are the record; re-running would overwrite their edits."""
    split = _load("split_adr_record")
    assert split.main(["--rev", "HEAD", "--verify-only"]) == 2


def test_main_check_exit_codes(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    assert gdi.main(["--check"], root=root) == 0
    (root / gdi.ADR_INDEX).write_text("edited\n", encoding="utf-8")
    assert gdi.main(["--check"], root=root) == 1
    assert gdi.main([], root=root) == 0
    assert gdi.main(["--check"], root=root) == 0
