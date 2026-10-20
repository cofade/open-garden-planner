"""Gate for the chapter-11 pitfall catalogue (ADR-061).

The index in docs/11-risks-and-technical-debt/README.md §11.4 is the one place a
lesson's ID resolves. These tests hold the index to the numbered files under
``pitfalls/`` and the verbatim files under ``archive/``: IDs are unique and
permanent, every index row resolves to its entry's anchor, every archive link
resolves, every pin names a real test, every legacy ``11.4.N`` ID resolves through
the redirect table, and the files stay within their size budgets.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "11-risks-and-technical-debt"
README = DOC / "README.md"
PITFALLS = DOC / "pitfalls"
ARCHIVE = DOC / "archive"

#: The README index plus its redirect table must stay small enough to scan.
README_MAX_BYTES = 64_000
#: Area files. Tightened once the dedupe has landed (ADR-061).
PITFALL_MAX_BYTES = 64_000

ENTRY_ID = re.compile(r"^PF-[A-Z0-9]+-\d{2}$")
ENTRY_HEADING = re.compile(r"^### (PF-[A-Z0-9]+-\d{2})$")
FIELD = re.compile(r"^- \*\*(Rule|Pinned by|Source|Status|Legacy):\*\* (.*)$")
ANY_HEADING = re.compile(r"^(#{1,6}) (.+?)\s*$")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
PIN = re.compile(r"`((?:tests|scripts|src)/[\w./-]+\.py)(?:::(\w+))?`")
LEGACY_HEADING = re.compile(r"^#{2,6} 11\.4\.\d+\b", re.MULTILINE)


def github_slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def anchors_of(path: Path) -> set[str]:
    """Every anchor GitHub generates for ``path``, with its -1, -2 suffixes."""
    seen: dict[str, int] = {}
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").split("\n"):
        match = ANY_HEADING.match(line)
        if not match:
            continue
        base = github_slug(match.group(2))
        count = seen.get(base, 0)
        found.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return found


def section_11_4() -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index("## 11.4 Known Development Pitfalls")
    end = text.index("## 11.5 ", start)
    return text[start:end]


def index_rows() -> list[dict[str, str]]:
    """Each ``| PF-… |`` row of the index, its cells split on unescaped pipes."""
    rows = []
    for line in section_11_4().split("\n"):
        if not line.startswith("| PF-"):
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:-1]]
        rows.append({"id": cells[0], "rule": cells[1], "status": cells[2],
                     "where": cells[3], "legacy": cells[4]})
    return rows


def redirect_rows() -> list[tuple[str, str]]:
    section = section_11_4()
    tail = section[section.index("### Redirect of legacy numbered IDs"):]
    rows = []
    for line in tail.split("\n"):
        match = re.match(r"^\| (11\.4\.\d+) \| (PF-[A-Z0-9]+-\d{2}) \|", line)
        if match:
            rows.append((match.group(1), match.group(2)))
    return rows


def entries() -> list[dict[str, object]]:
    """Every ``### PF-…`` entry in the area files, with its bold fields."""
    found: list[dict[str, object]] = []
    for file in sorted(PITFALLS.glob("*.md")):
        lines = file.read_text(encoding="utf-8").split("\n")
        for index, line in enumerate(lines):
            match = ENTRY_HEADING.match(line)
            if not match:
                continue
            fields: dict[str, str] = {}
            for follow in lines[index + 1:index + 12]:
                field = FIELD.match(follow)
                if field:
                    fields[field.group(1)] = field.group(2)
            found.append({"id": match.group(1), "file": file, "fields": fields})
    return found


def test_index_ids_are_unique_and_match_the_entries() -> None:
    rows = index_rows()
    ids = [row["id"] for row in rows]
    found = [str(entry["id"]) for entry in entries()]
    assert len(ids) == len(set(ids)), "an ID appears twice in the §11.4 index"
    assert len(found) == len(set(found)), "an ID is used by two entries"
    assert set(ids) == set(found), (
        f"index-only: {sorted(set(ids) - set(found))}; "
        f"entry-only: {sorted(set(found) - set(ids))}"
    )
    for entry_id in ids:
        assert ENTRY_ID.match(entry_id), f"malformed ID {entry_id}"


def test_every_index_row_links_to_its_entry_anchor() -> None:
    for row in index_rows():
        links = LINK.findall(row["where"])
        assert len(links) == 1, f"{row['id']}: where-cell must hold one link"
        target = links[0]
        file_part, _, anchor = target.partition("#")
        file = (README.parent / file_part).resolve()
        assert file.is_file(), f"{row['id']}: {file_part} does not exist"
        assert anchor == row["id"].lower(), f"{row['id']}: anchor {anchor!r}"
        assert anchor in anchors_of(file), f"{row['id']}: no heading #{anchor} in {file_part}"


def test_every_entry_has_the_template_fields() -> None:
    for entry in entries():
        fields = entry["fields"]
        assert isinstance(fields, dict)
        for name in ("Rule", "Pinned by", "Source", "Status"):
            assert fields.get(name), f"{entry['id']} has no **{name}:** field"


def test_pins_name_real_tests_or_say_why_there_are_none() -> None:
    for entry in entries():
        pinned = entry["fields"]["Pinned by"]  # type: ignore[index]
        if pinned.startswith("none"):
            assert " — " in pinned and pinned.split(" — ", 1)[1].strip(), (
                f"{entry['id']}: 'none' must give a reason"
            )
            continue
        pins = PIN.findall(pinned)
        assert pins, f"{entry['id']}: Pinned by names no test file"
        for path, name in pins:
            file = ROOT / path
            assert file.is_file(), f"{entry['id']} pins missing file {path}"
            if name:
                body = file.read_text(encoding="utf-8", errors="replace")
                assert re.search(rf"(?:def|class)\s+{re.escape(name)}\b", body), (
                    f"{entry['id']} pins missing test {path}::{name}"
                )


def test_archive_links_resolve_to_an_existing_anchor() -> None:
    for entry in entries():
        status = str(entry["fields"]["Status"])  # type: ignore[index]
        for target in LINK.findall(status):
            file_part, _, anchor = target.partition("#")
            file = (entry["file"].parent / file_part).resolve()  # type: ignore[union-attr]
            assert file.is_file(), f"{entry['id']}: {file_part} does not exist"
            if anchor:
                assert anchor in anchors_of(file), (
                    f"{entry['id']}: no heading #{anchor} in {file_part}"
                )


def test_redirect_table_resolves_every_legacy_numbered_id() -> None:
    rows = redirect_rows()
    legacy = [number for number, _ in rows]
    assert set(legacy) == {f"11.4.{n}" for n in range(1, 21)}, sorted(set(legacy))
    assert legacy.count("11.4.6") == 2, "11.4.6 named two entries and must map to both"
    index_ids = {row["id"] for row in index_rows()}
    for number, target in rows:
        assert target in index_ids, f"{number} redirects to unknown {target}"


def test_size_budgets_hold() -> None:
    assert README.stat().st_size <= README_MAX_BYTES, "README §11.4 index is too large"
    for file in sorted(PITFALLS.glob("*.md")):
        assert file.stat().st_size <= PITFALL_MAX_BYTES, f"{file.name} is over budget"


def test_no_legacy_numbered_headings_remain_outside_the_archive() -> None:
    assert not LEGACY_HEADING.search(README.read_text(encoding="utf-8")), (
        "a §11.4.N heading survived in the README; the entry belongs in pitfalls/ or archive/"
    )
    for file in sorted(PITFALLS.glob("*.md")):
        assert not LEGACY_HEADING.search(file.read_text(encoding="utf-8")), (
            f"{file.name} holds a legacy §11.4.N heading"
        )


def test_every_archive_file_named_by_an_entry_exists() -> None:
    named = set()
    for entry in entries():
        for target in LINK.findall(str(entry["fields"]["Status"])):  # type: ignore[index]
            named.add((ARCHIVE / target.partition("#")[0].split("/")[-1]).name)
    for name in named:
        assert (ARCHIVE / name).is_file(), f"archive file {name} is missing"


#: Trees whose text may cite a pitfall. The gate itself and the verbatim archive are
#: exempt; so are the legacy columns of the chapter index and the Legacy field.
SCAN_ROOTS = ("docs", ".claude", ".agents", "src", "tests", "scripts", "installer", ".github")
SCAN_FILES = ("CLAUDE.md", "AGENTS.md")
PF_TOKEN = re.compile(r"\bPF-[A-Z0-9]+-\d{2}\b")
LEGACY_TOKEN = re.compile(r"\b11\.4\.\d+\b")
SKIP_SUFFIXES = {".pyc", ".ogp", ".png", ".ico", ".icns", ".qm"}


def scanned_text() -> list[tuple[Path, int, str]]:
    """Every line of every text file a citation could live in, minus the exemptions."""
    lines: list[tuple[Path, int, str]] = []
    candidates = [ROOT / name for name in SCAN_FILES]
    for root in SCAN_ROOTS:
        candidates += [path for path in (ROOT / root).rglob("*") if path.is_file()]
    for path in sorted(set(candidates)):
        if "__pycache__" in path.parts or path.suffix in SKIP_SUFFIXES or path == Path(__file__).resolve():
            continue
        if "archive" in path.relative_to(ROOT).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.split("\n"), start=1):
            if path == README and (line.startswith("| 11.4.") or line.startswith("| PF-")):
                continue  # redirect table and the index's legacy column
            if "**Legacy:**" in line:
                continue
            lines.append((path, number, line))
    return lines


def test_every_pitfall_citation_resolves_to_the_index() -> None:
    known = {row["id"] for row in index_rows()}
    unknown = []
    for path, number, line in scanned_text():
        for token in PF_TOKEN.findall(line):
            if token not in known:
                unknown.append(f"{path.relative_to(ROOT)}:{number} {token}")
    assert not unknown, "pitfall IDs with no index row:\n" + "\n".join(unknown[:20])


def test_no_legacy_numbered_citation_survives_outside_the_archive() -> None:
    stale = [f"{path.relative_to(ROOT)}:{number}"
             for path, number, line in scanned_text() if LEGACY_TOKEN.search(line)]
    assert not stale, "legacy §11.4.N citations remain (migrate to PF IDs):\n" + "\n".join(stale[:20])
