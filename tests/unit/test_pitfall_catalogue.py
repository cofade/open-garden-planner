"""Gate for the chapter-11 pitfall catalogue (ADR-061).

The index in docs/11-risks-and-technical-debt/README.md §11.4 is the one place a lesson's
ID resolves. These tests hold the index to the numbered files under ``pitfalls/`` and the
verbatim files under ``archive/``: IDs are unique and permanent; every index row carries
exactly its entry's rule, status and legacy number and links to the entry's anchor; every
entry has the template fields and no placeholder; every pin names a real test; every
pointer names a home that holds its issue numbers and its pins; every archive link resolves;
every legacy ``11.4.N`` ID resolves through the redirect table; every PF citation resolves to
the index; and the files stay within their size budgets.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "11-risks-and-technical-debt"
README = DOC / "README.md"
PITFALLS = DOC / "pitfalls"
ARCHIVE = DOC / "archive"

#: The chapter README (the index carries one full rule per entry) must stay small enough to scan.
#: A maintenance trigger, not a target: the index grows one row per lesson, so the
#: budget is raised when the next package's rows no longer fit rather than met by
#: shortening rules (ADR-061 addendum "the index budget is raised", #588).
README_MAX_BYTES = 96_000
#: Area files. The UI area holds the most entries (22, with their full rules); a file over this is split by sub-area.
PITFALL_MAX_BYTES = 64_000

ENTRY_ID = re.compile(r"^PF-[A-Z0-9]+-\d{2}$")
ENTRY_HEADING = re.compile(r"^### (PF-[A-Z0-9]+-\d{2})$")
FIELD = re.compile(r"^- \*\*(Rule|Pinned by|Source|Status|Legacy):\*\* (.*)$")
ANY_HEADING = re.compile(r"^(#{1,6}) (.+?)\s*$")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
POINTER = re.compile(r"^pointer → \[[^\]]*\]\(([^)#\s]+)#([^)\s]+)\)")
#: A pin is a test file under ``tests/``, optionally with ``::name``. Nothing else pins.
PIN = re.compile(r"`(tests/[\w./-]+\.py)(?:::(\w+))?`")
PINS_ONLY = re.compile(r"`tests/[\w./-]+\.py(?:::\w+)?`(?:; `tests/[\w./-]+\.py(?:::\w+)?`)*")
ISSUE = re.compile(r"#(\d{2,4})\b")
LEGACY_NUMBER = re.compile(r"11\.4\.\d+\b")
LEGACY_HEADING = re.compile(r"^#{2,6} 11\.4\.\d+\b", re.MULTILINE)
PLACEHOLDER = re.compile(r"pending review|\bTBD\b", re.IGNORECASE)
#: Each legacy number names one entry, except the two that name several rules: §11.4.6
#: (a dead-code entry and a sun self-shadow entry) and §11.4.17 (the ground-bake diary,
#: whose three standing rules sit in three entries).
LEGACY_ROWS = {**{f"11.4.{n}": 1 for n in range(1, 21)}, "11.4.6": 2, "11.4.17": 3}


def github_slug(heading: str) -> str:
    """GitHub's heading anchor: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _headings(lines: list[str]):
    """Each heading outside a fenced code block, with its line index and match."""
    fenced = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = ANY_HEADING.match(line)
        if match:
            yield index, match


def anchors_of(path: Path) -> set[str]:
    """Every anchor GitHub generates for ``path``, with its -1, -2 suffixes."""
    seen: dict[str, int] = {}
    found: set[str] = set()
    for _, match in _headings(path.read_text(encoding="utf-8").split("\n")):
        base = github_slug(match.group(2))
        count = seen.get(base, 0)
        found.add(base if count == 0 else f"{base}-{count}")
        seen[base] = count + 1
    return found


def section_of(path: Path, anchor: str) -> str | None:
    """The text from the heading GitHub gives ``anchor`` to the next heading of its level or higher."""
    lines = path.read_text(encoding="utf-8").split("\n")
    seen: dict[str, int] = {}
    for index, match in _headings(lines):
        base = github_slug(match.group(2))
        count = seen.get(base, 0)
        seen[base] = count + 1
        if (base if count == 0 else f"{base}-{count}") != anchor:
            continue
        level = len(match.group(1))
        end = next((k for k, later in _headings(lines) if k > index and len(later.group(1)) <= level),
                   len(lines))
        return "\n".join(lines[index:end])
    return None


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


def test_entry_rows_belong_to_the_five_column_index_table() -> None:
    """A PF row in the three-column redirect table loses its navigation cells."""
    header: list[str] = []
    for line in section_11_4().splitlines():
        if not line.startswith("|"):
            header = []
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line)[1:-1]]
        if not header:
            header = cells
        if cells[0].startswith("PF-"):
            assert header == ["ID", "Rule", "Status", "Where", "Legacy"]
            assert len(cells) == len(header)


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
        headings = list(_headings(lines))
        for position, (index, _) in enumerate(headings):
            match = ENTRY_HEADING.match(lines[index])
            if not match:
                continue
            # an entry ends at the next heading: a short entry must not read the fields of the next
            end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
            fields: dict[str, str] = {}
            for follow in lines[index + 1:end]:
                field = FIELD.match(follow)
                if field:
                    fields[field.group(1)] = field.group(2)
            found.append({"id": match.group(1), "file": file, "fields": fields, "lines": lines[index:end]})
    return found


def status_word(status: str) -> str:
    return re.split(r"[;\s]", status, maxsplit=1)[0]


def legacy_numbers(legacy: str) -> list[str]:
    return LEGACY_NUMBER.findall(legacy)


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


def test_every_h3_heading_in_the_area_files_is_an_entry_heading() -> None:
    for file in sorted(PITFALLS.glob("*.md")):
        lines = file.read_text(encoding="utf-8").split("\n")
        for index, match in _headings(lines):
            if match.group(1) == "#" and index == 0:
                continue
            assert match.group(1) == "###" and ENTRY_HEADING.match(lines[index]), (
                f"{file.name}:{index + 1} is not an entry heading: {lines[index][:80]!r}"
            )


def test_index_rows_agree_with_their_entries() -> None:
    by_id = {str(entry["id"]): entry for entry in entries()}
    for row in index_rows():
        fields = by_id[row["id"]]["fields"]
        assert isinstance(fields, dict)
        assert row["rule"] == fields["Rule"], f"{row['id']}: index rule differs from the entry's"
        assert row["status"] == status_word(fields["Status"]), f"{row['id']}: index status differs"
        assert row["legacy"] == ", ".join(legacy_numbers(fields.get("Legacy", ""))), (
            f"{row['id']}: index legacy differs from the entry's"
        )
        assert "|" not in fields["Rule"], f"{row['id']}: a rule may not hold a pipe"


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


def test_every_entry_has_the_template_fields_and_no_placeholder() -> None:
    for entry in entries():
        fields = entry["fields"]
        assert isinstance(fields, dict)
        for name in ("Rule", "Pinned by", "Source", "Status", "Legacy"):
            assert fields.get(name), f"{entry['id']} has no **{name}:** field"
        for line in entry["lines"]:  # type: ignore[union-attr]
            assert not PLACEHOLDER.search(str(line)), f"{entry['id']} still holds placeholder text"


#: The four forms a Status field may take (ADR-061, decision 3).
STATUS_FORMS = re.compile(r"^(?:standing|standing; narrative in \[[^\]]+\]\([^)]+\)|pointer → \[[^\]]+\]\([^)]+\)|retired; narrative in \[[^\]]+\]\([^)]+\))$")


def test_every_status_uses_one_of_the_four_forms() -> None:
    for entry in entries():
        status = str(entry["fields"]["Status"])  # type: ignore[index]
        assert STATUS_FORMS.match(status), f"{entry['id']}: Status is not one of the four forms: {status[:60]!r}"


def test_pins_name_real_tests_or_say_why_there_are_none() -> None:
    for entry in entries():
        pinned = str(entry["fields"]["Pinned by"])  # type: ignore[index]
        if pinned.startswith("none"):
            assert " — " in pinned and pinned.split(" — ", 1)[1].strip(), (
                f"{entry['id']}: 'none' must give a reason"
            )
            continue
        assert PINS_ONLY.fullmatch(pinned), (
            f"{entry['id']}: Pinned by holds only `tests/…py::name` pins, separated by '; '"
        )
        for path, name in PIN.findall(pinned):
            file = ROOT / path
            assert file.is_file(), f"{entry['id']} pins missing file {path}"
            if name:
                body = file.read_text(encoding="utf-8", errors="replace")
                assert re.search(rf"(?:def|class)\s+{re.escape(name)}\b", body), (
                    f"{entry['id']} pins missing test {path}::{name}"
                )


def test_pointer_entries_name_a_home_that_holds_their_issues_and_pins() -> None:
    for entry in entries():
        status = str(entry["fields"]["Status"])  # type: ignore[index]
        if not status.startswith("pointer"):
            continue
        match = POINTER.match(status)
        assert match, f"{entry['id']}: a pointer must link its home with a heading anchor"
        target = (entry["file"].parent / match.group(1)).resolve()  # type: ignore[union-attr]
        section = section_of(target, match.group(2))
        assert section is not None, f"{entry['id']}: no heading #{match.group(2)} in {match.group(1)}"
        source = str(entry["fields"]["Source"])  # type: ignore[index]
        for issue in ISSUE.findall(source):
            assert re.search(rf"#{issue}\b", section), (
                f"{entry['id']}: its home #{match.group(2)} does not mention issue #{issue}"
            )
        for path, _ in PIN.findall(str(entry["fields"]["Pinned by"])):  # type: ignore[index]
            # a home may name its test by file name alone
            assert path.rsplit("/", 1)[1] in section, f"{entry['id']}: its home does not name its pin {path}"
        # A home must preserve the substance of the rule, not merely cite its issue numbers
        rule = str(entry["fields"]["Rule"])
        keywords = {
            word.lower()
            for word in re.findall(r"\b[A-Za-z]{5,}\b", rule)
            if word.lower() not in {
                "every", "other", "their", "which", "where", "after", "never", "under",
                "because", "first", "lines", "shows", "about", "could", "would", "should",
            }
        }
        matched = {kw for kw in keywords if kw in section.lower()}
        assert len(matched) >= min(3, len(keywords)), (
            f"{entry['id']}: its home #{match.group(2)} matches only {matched} out of substantive rule keywords {keywords}"
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
    counts: dict[str, int] = {}
    for number, _ in rows:
        counts[number] = counts.get(number, 0) + 1
    assert counts == LEGACY_ROWS, sorted(counts.items())
    index_ids = {row["id"] for row in index_rows()}
    for number, target in rows:
        assert target in index_ids, f"{number} redirects to unknown {target}"


def test_redirect_rows_match_the_legacy_field_of_their_entry() -> None:
    by_id = {str(entry["id"]): entry for entry in entries()}
    rows = set(redirect_rows())
    for number, target in rows:
        legacy = str(by_id[target]["fields"]["Legacy"])  # type: ignore[index]
        assert number in legacy_numbers(legacy), f"{target} does not name {number} in its Legacy field"
    for entry_id, entry in by_id.items():
        for number in legacy_numbers(str(entry["fields"]["Legacy"])):  # type: ignore[index]
            assert (number, entry_id) in rows, f"{entry_id} names {number}, which the redirect table lacks"


def _stored_size(path: Path) -> int:
    # newline-normalised: an autocrlf checkout holds a CR per line that the repository
    # (and CI's checkout) does not, and a budget must not differ between them
    return len(path.read_bytes().replace(b"\r\n", b"\n"))


def test_size_budgets_hold() -> None:
    assert _stored_size(README) <= README_MAX_BYTES, "README §11.4 index is too large"
    for file in sorted(PITFALLS.glob("*.md")):
        assert _stored_size(file) <= PITFALL_MAX_BYTES, f"{file.name} is over budget"


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
            if "archive/" in target:
                named.add(target.partition("#")[0].split("/")[-1])
    assert named, "no entry links into the archive"
    for name in sorted(named):
        assert (ARCHIVE / name).is_file(), f"archive file {name} is missing"


#: Trees whose text may cite a pitfall. The verbatim archive is exempt, and so is this gate
#: (it names the patterns). The legacy columns of the chapter index and the Legacy field are
#: exempt too; the redirect table is the one place a legacy number may stand.
SCAN_ROOTS = ("docs", ".claude", ".agents", ".codex", "src", "tests", "scripts", "installer", ".github")
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
        if (
            "__pycache__" in path.parts
            or "worktrees" in path.parts
            or path.suffix in SKIP_SUFFIXES
            or path == Path(__file__).resolve()
        ):
            continue
        if path.is_relative_to(ARCHIVE):
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
