"""Generate the architecture-decision index from the per-ADR files, or check it.

Each decision lives in its own file, ``docs/09-architecture-decisions/ADR-nnn-<slug>.md``
(#1035, ADR-083). The file starts with a small front-matter block, then one H1
``# ADR-nnn: <title>``, then the record. ``docs/09-architecture-decisions/README.md``
is written by this script from the front matter and must not be edited by hand.

Run from the repository root::

    venv/Scripts/python.exe scripts/generate_doc_indexes.py           # rewrite the index
    venv/Scripts/python.exe scripts/generate_doc_indexes.py --check   # gate: exit 1 on drift

``--check`` is also run by ``tests/unit/test_doc_indexes.py``, so the suite fails when an
ADR file is malformed or the index is stale. The script uses only the standard library.

Front matter is a strict subset of YAML: one ``key: value`` per line, where a value is a
JSON string or a JSON list of strings (both valid YAML), or a bare token for ``id`` and
``legacy_anchor``. The keys are fixed (``FIELDS``); an unknown key is an error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = Path("docs/09-architecture-decisions")
ADR_INDEX = ADR_DIR / "README.md"

#: Front-matter keys in their written order; True = required.
FIELDS: dict[str, bool] = {
    "id": True,
    "title": True,
    "status": False,
    "refs": False,
    "superseded_by": False,
    "legacy_anchor": False,
}
LIST_FIELDS = frozenset({"refs", "superseded_by"})
BARE_FIELDS = frozenset({"id", "legacy_anchor"})

#: ADR numbers deliberately left unused, each with its reason. A number missing between
#: ADR-001 and the highest number fails the gate unless it is listed here.
ALLOWED_GAPS: dict[int, str] = {}

ADR_FILE_RE = re.compile(r"^ADR-(\d{3})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
ADR_ID_RE = re.compile(r"^ADR-(\d{3})$")
H1_RE = re.compile(r"^# (ADR-\d{3}): (.+)$")
#: A fenced-code delimiter (CommonMark: at most three spaces of indentation; the record
#: has fences inside list items at three).
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
HEADING_RE = re.compile(r"^(#{1,6}) +(.*?) *#* *$")

INDEX_PREAMBLE = """\
# 9. Architecture Decisions

Architecture Decision Records (ADRs) for significant technical choices.

Each ADR is one file in this folder, `ADR-nnn-<slug>.md`, and its addenda stay inside
that file. **This index is generated** by `scripts/generate_doc_indexes.py` from each
file's front matter; do not edit it by hand. To add an ADR, create the next
`ADR-nnn-<slug>.md` with front matter (see ADR-083), then run the generator. To add an
addendum, append it to the ADR's own file. `--check` runs in the test suite.

The hidden anchors in the first column keep links to the old single-file record working:
a link to `README.md#adr-069-…` lands on ADR-069's row.
"""


# --- GitHub heading anchors ---------------------------------------------------------------


_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def heading_text(raw: str) -> str:
    """Return the text GitHub renders for a heading's Markdown source.

    Inside a code span (`` `…` ``) the text is literal: no link or HTML is stripped there.
    """
    parts = raw.split("`")
    for i in range(0, len(parts), 2):  # even parts lie outside code spans
        parts[i] = _HTML_TAG_RE.sub("", _LINK_RE.sub(r"\1", parts[i])).replace("*", "")
    return "".join(parts)


def github_slug(raw: str) -> str:
    """The anchor GitHub gives a heading (github-slugger), before de-duplication.

    Lower-case; keep letters, marks, numbers, ``_``, ``-`` and spaces; spaces become ``-``.
    """
    kept = []
    for ch in heading_text(raw).lower():
        if ch in " -" or unicodedata.category(ch)[0] in "LMN" or unicodedata.category(ch) == "Pc":
            kept.append(ch)
    return "".join(kept).replace(" ", "-")


class SlugCounter:
    """De-duplicate anchors the way GitHub does within one rendered document."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def anchor(self, raw: str) -> str:
        base = github_slug(raw)
        slug = base
        while slug in self._seen:
            self._seen[base] += 1
            slug = f"{base}-{self._seen[base]}"
        self._seen.setdefault(slug, 0)
        return slug


def iter_headings(lines: Iterable[str]) -> Iterable[tuple[int, int, str]]:
    """Yield ``(line_index, level, text)`` for every ATX heading outside code fences.

    A fence closes only on the same character, at least as long as its opening
    (CommonMark), so a ```` ``` ```` line inside a ``~~~`` block does not end it.
    """
    fence = ""
    for index, line in enumerate(lines):
        match = FENCE_RE.match(line)
        if fence:
            if match and match.group(1)[0] == fence[0] and len(match.group(1)) >= len(fence) \
                    and not line[match.end():].strip():
                fence = ""
            continue
        if match:
            fence = match.group(1)
            continue
        match = HEADING_RE.match(line)
        if match:
            yield index, len(match.group(1)), match.group(2)


def document_anchors(text: str) -> list[tuple[int, int, str, str]]:
    """``(line_index, level, text, anchor)`` for each heading, de-duplicated as on GitHub."""
    counter = SlugCounter()
    return [
        (index, level, raw, counter.anchor(raw))
        for index, level, raw in iter_headings(text.splitlines())
    ]


def file_slug(title: str, limit: int = 60) -> str:
    """The kebab-case, ASCII file-name slug of a cleaned ADR title."""
    ascii_text = unicodedata.normalize("NFKD", heading_text(title))
    ascii_text = ascii_text.encode("ascii", "ignore").decode("ascii").lower().replace("'", "")
    words = re.findall(r"[a-z0-9]+", ascii_text)
    slug = ""
    for word in words:
        candidate = f"{slug}-{word}" if slug else word
        if len(candidate) > limit and slug:
            break
        slug = candidate
    return slug


# --- front matter ---------------------------------------------------------------------------


class FrontMatterError(ValueError):
    pass


def render_front_matter(values: dict[str, object]) -> str:
    lines = ["---"]
    for key in FIELDS:
        value = values.get(key)
        if value in (None, "", []):
            continue
        if key in BARE_FIELDS:
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def parse_front_matter(text: str) -> tuple[dict[str, object], str]:
    """Split ``text`` into its front-matter values and the body after it."""
    if not text.startswith("---\n"):
        raise FrontMatterError("does not start with a '---' front-matter line")
    end = text.find("\n---\n", 3)
    if end < 0:
        raise FrontMatterError("front matter has no closing '---' line")
    values: dict[str, object] = {}
    for number, line in enumerate(text[4:end].split("\n"), start=2):
        key, sep, raw = line.partition(": ")
        if not sep or key not in FIELDS:
            raise FrontMatterError(f"line {number}: unknown or malformed field {line!r}")
        if key in values:
            raise FrontMatterError(f"line {number}: duplicate field {key!r}")
        if key in BARE_FIELDS:
            if not re.fullmatch(r"[\w-]+", raw):
                raise FrontMatterError(f"line {number}: {key} must be a bare token")
            values[key] = raw
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FrontMatterError(f"line {number}: {key} is not a JSON value ({exc})") from exc
        if key in LIST_FIELDS:
            if not (isinstance(value, list) and value and all(isinstance(v, str) for v in value)):
                raise FrontMatterError(f"line {number}: {key} must be a non-empty list of strings")
        elif not (isinstance(value, str) and value):
            raise FrontMatterError(f"line {number}: {key} must be a non-empty string")
        values[key] = value
    for key, required in FIELDS.items():
        if required and key not in values:
            raise FrontMatterError(f"missing required field {key!r}")
    return values, text[end + len("\n---\n"):]


# --- the ADR set --------------------------------------------------------------------------


@dataclass
class Adr:
    path: Path
    number: int
    title: str
    status: str = ""
    refs: list[str] = field(default_factory=list)
    superseded_by: list[str] = field(default_factory=list)
    legacy_anchor: str = ""
    values: dict[str, object] = field(default_factory=dict)
    body: str = ""

    @property
    def id(self) -> str:
        return f"ADR-{self.number:03d}"

    @property
    def body_status(self) -> str:
        return status_from_body(self.body.split("\n"))

    def synced_values(self) -> dict[str, object]:
        """The front matter with ``status`` and ``superseded_by`` taken from the body."""
        values = dict(self.values)
        values["status"] = self.body_status
        values["superseded_by"] = superseded_from_status(self.body_status)
        return {key: value for key, value in values.items() if value not in ("", [], None)}


# --- status, derived from the body ------------------------------------------------------------


STATUS_RE = re.compile(r"^\*\*Status(?:\*\*:|:\*\*|\.\*\*)\s*(.*)$")
#: The record's field labels that may follow a Status line without a blank line. A closed
#: list: a bold clause inside the paragraph (ADR-069's "**Superseded on 2026-11-24 …:**")
#: is status text, not the next field.
_FIELD_LINE_RE = re.compile(
    r"^\*\*(?:Context|Date|Decision|Rationale|Consequences|Alternatives(?: considered)?"
    r"|Problem|Scope)\b[^*]*(?::\*\*|\*\*:|\.\*\*)"
)
#: An early one-line record runs on: "**Status**: Accepted | **Context**: …".
_INLINE_FIELD = " | **"
_ADR_REF_RE = re.compile(r"\bADR-\d{3}\b")


def status_from_body(lines: list[str]) -> str:
    """The ADR's own status: its first ``**Status**:`` paragraph before any sub-heading.

    The paragraph ends at a blank line, a heading, or the next field label
    (``_FIELD_LINE_RE``); an early one-line record's ``| **Context**: …`` tail is not status.
    The lines are joined with single spaces; the text is otherwise verbatim. A version
    sync edits this line; the generator copies it into the front matter.
    """
    headings = [index for index, _level, _text in iter_headings(lines)]
    limit = headings[1] if len(headings) > 1 else len(lines)
    for i in range(limit):
        match = STATUS_RE.match(lines[i])
        if not match:
            continue
        parts = [match.group(1).strip()]
        for line in lines[i + 1 : limit]:
            # a real heading only: "#475 (raster lane …)" continues the paragraph (ADR-069)
            if not line.strip() or _FIELD_LINE_RE.match(line) or HEADING_RE.match(line):
                break
            parts.append(line.strip())
        return " ".join(part for part in parts if part).split(_INLINE_FIELD, 1)[0].strip()
    return ""


def superseded_from_status(status: str) -> list[str]:
    """``["ADR-040", "ADR-042"]`` for "Superseded by ADR-040 and ADR-042 (…); …"."""
    plain = status.replace("**", "")
    if not plain.startswith("Superseded"):
        return []
    clause = re.split(r"[;(]", plain, maxsplit=1)[0]
    return list(dict.fromkeys(_ADR_REF_RE.findall(clause)))


# --- the ADR set ----------------------------------------------------------------------------


def adr_paths(root: Path = REPO_ROOT) -> list[Path]:
    """Every per-ADR file, sorted by name (= by number)."""
    folder = root / ADR_DIR
    return sorted(
        (path for path in folder.glob("*.md") if path.name.lower().startswith("adr-")),
        key=lambda p: p.name,
    )


def load_adrs(root: Path = REPO_ROOT) -> tuple[list[Adr], list[str]]:
    """Read every ADR file; return the parsed ADRs and the errors found on the way.

    Files are found case-insensitively (``adr-084-x.md`` too), so a misnamed file fails
    the gate on every platform instead of being invisible on a case-sensitive one.
    """
    adrs: list[Adr] = []
    errors: list[str] = []
    for path in adr_paths(root):
        rel = path.relative_to(root).as_posix()
        name = ADR_FILE_RE.match(path.name)
        if not name:
            errors.append(f"{rel}: file name must be ADR-nnn-<kebab-case-slug>.md")
            continue
        try:
            values, body = parse_front_matter(path.read_text(encoding="utf-8"))
        except FrontMatterError as exc:
            errors.append(f"{rel}: {exc}")
            continue
        number = int(name.group(1))
        if values["id"] != f"ADR-{number:03d}":
            errors.append(f"{rel}: id {values['id']!r} does not match the file name")
        h1s = [(lvl, text) for _, lvl, text in iter_headings(body.splitlines()) if lvl == 1]
        first = body.lstrip("\n").split("\n", 1)[0]
        h1 = H1_RE.match(first)
        if len(h1s) != 1 or not h1:
            errors.append(f"{rel}: the body must open with the file's only H1, '# ADR-nnn: <title>'")
        elif h1.group(1) != values["id"] or h1.group(2) != values["title"]:
            errors.append(f"{rel}: H1 {first!r} does not match id and title in the front matter")
        adrs.append(Adr(
            path=path, number=number, title=str(values["title"]),
            status=str(values.get("status", "")),
            refs=list(cast("list[str]", values.get("refs", []))),
            superseded_by=list(cast("list[str]", values.get("superseded_by", []))),
            legacy_anchor=str(values.get("legacy_anchor", "")),
            values=values, body=body.lstrip("\n"),
        ))
    return adrs, errors


def check_adr_set(adrs: list[Adr]) -> list[str]:
    errors: list[str] = []
    numbers: dict[int, list[Adr]] = {}
    for adr in adrs:
        numbers.setdefault(adr.number, []).append(adr)
    for number, holders in sorted(numbers.items()):
        if len(holders) > 1:
            names = ", ".join(h.path.name for h in holders)
            errors.append(f"ADR-{number:03d} is used by more than one file: {names}")
    if numbers:
        for number in range(1, max(numbers) + 1):
            if number not in numbers and number not in ALLOWED_GAPS:
                errors.append(f"ADR-{number:03d} is missing (list a deliberate gap in ALLOWED_GAPS)")
    anchors: dict[str, str] = {}
    for adr in adrs:
        for target in adr.superseded_by:
            match = ADR_ID_RE.match(target)
            if not match or int(match.group(1)) not in numbers:
                errors.append(f"{adr.id}: superseded_by names {target!r}, which is no ADR")
        if adr.legacy_anchor:
            if adr.legacy_anchor in anchors:
                errors.append(f"{adr.id}: legacy_anchor duplicates {anchors[adr.legacy_anchor]}'s")
            anchors[adr.legacy_anchor] = adr.id
    return errors


def check_status_sync(adrs: list[Adr]) -> list[str]:
    """The front matter's ``status``/``superseded_by`` must be what the body says."""
    errors: list[str] = []
    for adr in adrs:
        if adr.status != adr.body_status:
            errors.append(
                f"{adr.id}: front-matter status differs from the body's **Status** line "
                "(run scripts/generate_doc_indexes.py, which copies the body's)"
            )
        if adr.superseded_by != superseded_from_status(adr.body_status):
            errors.append(
                f"{adr.id}: superseded_by does not match the body's **Status** line "
                "(run scripts/generate_doc_indexes.py)"
            )
    return errors


def sync_front_matter(adrs: list[Adr]) -> list[Path]:
    """Copy each body's status into its front matter; return the files rewritten."""
    written: list[Path] = []
    for adr in adrs:
        synced = adr.synced_values()
        if synced == {k: v for k, v in adr.values.items() if v not in ("", [], None)}:
            continue
        adr.path.write_text(
            render_front_matter(synced) + "\n" + adr.body, encoding="utf-8", newline="\n"
        )
        adr.values = synced
        adr.status = str(synced.get("status", ""))
        adr.superseded_by = list(cast("list[str]", synced.get("superseded_by", [])))
        written.append(adr.path)
    return written


# --- the index ----------------------------------------------------------------------------


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def short_status(status: str, limit: int = 90) -> str:
    """The index's status cell: the status's first sentence, capped at ``limit`` characters.

    The full status stays in the ADR file's front matter and body. An old one-line record
    (``Status | Context | …``) is cut at its first ``|`` field separator.
    """
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", status).replace("**", "")
    text = text.split(" | ", 1)[0]
    cut = re.search(r"\.(\s|$)", text)
    if cut:
        text = text[: cut.start()]
    text = text.strip().rstrip(";,:")
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0]
        # never end inside a bracket or a quotation: back off to before it opened
        while text.count("(") > text.count(")"):
            text = text[: text.rindex("(")].rstrip()
        if text.count('"') % 2:
            text = text[: text.rindex('"')].rstrip()
        text = text.rstrip(";,:—- ") + " …"
    return text or "—"


def render_index(adrs: list[Adr]) -> str:
    rows = ["| ADR | Title | Status |", "|---|---|---|"]
    for adr in sorted(adrs, key=lambda a: a.number):
        stub = f'<a id="{adr.legacy_anchor}"></a>' if adr.legacy_anchor else ""
        link = f"{stub}[{adr.id}]({adr.path.name})"
        rows.append(f"| {link} | {_cell(adr.title)} | {_cell(short_status(adr.status))} |")
    return INDEX_PREAMBLE + "\n" + "\n".join(rows) + "\n"


def check(root: Path = REPO_ROOT) -> list[str]:
    """Every gate failure; an empty list means the ADR files and the index agree."""
    adrs, errors = load_adrs(root)
    if not adrs and not errors:
        return [f"{ADR_DIR.as_posix()}: no ADR-*.md files found"]
    errors += check_adr_set(adrs) + check_status_sync(adrs)
    if not errors:
        index = root / ADR_INDEX
        current = index.read_text(encoding="utf-8") if index.exists() else ""
        if current != render_index(adrs):
            errors.append(
                f"{ADR_INDEX.as_posix()} is stale or was edited by hand: "
                "run scripts/generate_doc_indexes.py"
            )
    return errors


def write(root: Path = REPO_ROOT) -> list[str]:
    """Copy each body's status into its front matter, then rewrite the index."""
    adrs, errors = load_adrs(root)
    errors += check_adr_set(adrs)
    if errors:
        return errors
    for path in sync_front_matter(adrs):
        print(f"synced front matter of {path.relative_to(root).as_posix()}")
    errors = check_adr_set(adrs)
    if errors:
        return errors
    (root / ADR_INDEX).write_text(render_index(adrs), encoding="utf-8", newline="\n")
    return []


def main(argv: list[str] | None = None, root: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="fail on drift, write nothing")
    args = parser.parse_args(argv)
    root = root or REPO_ROOT
    errors = check(root) if args.check else write(root)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if not errors and not args.check:
        print(f"wrote {ADR_INDEX.as_posix()}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
