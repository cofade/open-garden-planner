"""One-off migration (#1035): split the single-file ADR record into one file per ADR.

Reads the old ``docs/09-architecture-decisions/README.md`` from git, at the revision
given with ``--rev``, writes ``ADR-nnn-<slug>.md`` per decision, regenerates the
index with ``scripts/generate_doc_indexes.py``, rewrites in-repo links that point to an
anchor of the old file, and proves the split lossless.

    venv/Scripts/python.exe scripts/split_adr_record.py --rev master
    venv/Scripts/python.exe scripts/split_adr_record.py --rev master --verify-only

The split is deterministic. It was re-run once on its own branch, after a rebase brought
new ADR text from master. Its job ends with that branch: afterwards the ADR files are the
record, and a re-run would overwrite every later edit to them with the old file's text.
The script therefore refuses to run when the revision's README is already the generated
index, and refuses to overwrite an ADR file that differs from the old text unless
``--replace`` is passed. A branch that still edits the old file moves its hunk by hand
into the ADR's own file, with its headings one level up (ADR-083).

Every ADR keeps its body verbatim; only these things change:

- heading markers move up one level (``## ADR-nnn`` becomes the file's H1);
- a trailing issue/PR ref list in the title, e.g. ``(issues #664, #771)``, moves out of the
  H1 into the front-matter field ``refs`` (the word "issue(s)" is dropped from each part);
- front matter is added (``id``, ``title``, ``status``, ``refs``, ``superseded_by``,
  ``legacy_anchor``);
- trailing blank lines at the end of a section are dropped.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_doc_indexes as gdi

ROOT = gdi.REPO_ROOT
OLD_PATH = gdi.ADR_INDEX.as_posix()

ADR_H2_RE = re.compile(r"^ADR-(\d{3}): (.+)$")
TITLE_REFS_RE = re.compile(r"^(.*?) \(([^()]*#\d+[^()]*)\)$")
#: A link to an anchor of the old file. A permalink to a fixed commit
#: (``blob/<40-hex sha>/docs/…``) still resolves at that commit and is left alone.
ANCHOR_LINK_RE = re.compile(
    r"(?<!/[0-9a-f]{40}/docs/)"
    r"(?P<prefix>09-architecture-decisions/)README\.md#(?P<anchor>[^\s)\]`'\"<>]+)"
)


@dataclass
class Section:
    number: int
    raw_title: str
    clean_title: str
    refs: list[str]
    lines: list[str]  # the old section, trailing blank lines removed
    start: int  # 0-based line index of the ``## ADR`` line in the old file
    legacy_anchor: str
    old_anchors: list[str]  # anchors of every heading in the section, in order

    @property
    def id(self) -> str:
        return f"ADR-{self.number:03d}"

    @property
    def file_name(self) -> str:
        return f"{self.id}-{gdi.file_slug(self.clean_title)}.md"


def read_old(rev: str) -> str:
    out = subprocess.run(
        ["git", "show", f"{rev}:{OLD_PATH}"], cwd=ROOT, check=True, capture_output=True
    )
    return out.stdout.decode("utf-8")


def clean_title(raw: str) -> tuple[str, list[str]]:
    match = TITLE_REFS_RE.match(raw)
    if not match:
        return raw, []
    parts = [re.sub(r"^(?:[Ii]ssues?|PRs?) ", "", p.strip()) for p in match.group(2).split(",")]
    return match.group(1), [p for p in parts if p]


def split(text: str) -> tuple[list[str], list[Section]]:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    anchors = {index: anchor for index, _lvl, _txt, anchor in gdi.document_anchors(text)}
    starts = [
        index
        for index, level, raw in gdi.iter_headings(lines)
        if level == 2 and ADR_H2_RE.match(raw)
    ]
    other_h2 = [i for i, lvl, raw in gdi.iter_headings(lines) if lvl <= 2 and i not in starts]
    if any(i > starts[0] for i in other_h2):
        raise SystemExit(f"non-ADR H1/H2 inside the record at lines {[i + 1 for i in other_h2]}")
    preamble = lines[: starts[0]]
    sections: list[Section] = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        body = lines[start:end]
        while body and body[-1].strip() == "":
            body.pop()
        match = ADR_H2_RE.match(lines[start][3:])
        assert match
        title, refs = clean_title(match.group(2))
        sections.append(Section(
            number=int(match.group(1)), raw_title=match.group(2), clean_title=title, refs=refs,
            lines=body, start=start, legacy_anchor=anchors[start],
            old_anchors=[anchors[start + i] for i, _l, _t in gdi.iter_headings(body)],
        ))
    return preamble, sections


def promote(lines: list[str]) -> list[str]:
    out = list(lines)
    for index, level, _raw in gdi.iter_headings(lines):
        assert level >= 2, f"an H1 inside an ADR section: {lines[index]!r}"
        out[index] = lines[index][1:]
    return out


def demote(lines: list[str]) -> list[str]:
    out = list(lines)
    for index, _level, _raw in gdi.iter_headings(lines):
        out[index] = "#" + lines[index]
    return out


def render_file(section: Section) -> str:
    status = gdi.status_from_body(section.lines)
    front = gdi.render_front_matter({
        "id": section.id,
        "title": section.clean_title,
        "status": status,
        "refs": section.refs,
        "superseded_by": gdi.superseded_from_status(status),
        "legacy_anchor": section.legacy_anchor,
    })
    body = promote(section.lines)
    body[0] = f"# {section.id}: {section.clean_title}"
    return front + "\n" + "\n".join(body) + "\n"


def anchor_map(sections: list[Section]) -> dict[str, tuple[str, str]]:
    """old anchor -> (new file name, the same heading's anchor in the new file).

    A link to an ADR's own heading keeps an anchor too (the new H1's): the pitfall
    catalogue requires a pointer to name a heading (test_pitfall_catalogue.py).
    """
    mapping: dict[str, tuple[str, str]] = {}
    for section in sections:
        new = gdi.document_anchors(render_file(section).split("\n---\n", 1)[1])
        assert len(new) == len(section.old_anchors), section.id
        for old, (_i, _l, _t, anchor) in zip(section.old_anchors, new, strict=True):
            mapping[old] = (section.file_name, anchor)
    return mapping


def rewrite_links(mapping: dict[str, tuple[str, str]], *, dry: bool) -> list[str]:
    report: list[str] = []
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.decode("utf-8").split("\0")
    for rel in tracked:
        if not rel or rel.startswith(gdi.ADR_DIR.as_posix() + "/ADR-") or rel == OLD_PATH:
            continue
        path = ROOT / rel
        if path.suffix.lower() not in {".md", ".py", ".toml", ".txt", ".json", ".yml", ".yaml"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "architecture-decisions/README.md#" not in text:
            continue

        def sub(match: re.Match[str], rel: str = rel) -> str:
            anchor = match.group("anchor")
            if anchor not in mapping:
                report.append(f"UNRESOLVED {rel}: #{anchor}")
                return match.group(0)
            name, new = mapping[anchor]
            report.append(f"rewrote {rel}: #{anchor} -> {name}#{new}")
            return f"{match.group('prefix')}{name}#{new}"

        new_text = ANCHOR_LINK_RE.sub(sub, text)
        if new_text != text and not dry:
            path.write_text(new_text, encoding="utf-8", newline="\n")
    return report


def verify(text: str, preamble: list[str], sections: list[Section]) -> list[str]:
    """Re-read the written files and prove the old record is fully accounted for."""
    errors: list[str] = []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    covered = len(preamble)
    for section in sorted(sections, key=lambda s: s.start):
        path = ROOT / gdi.ADR_DIR / section.file_name
        values, body = gdi.parse_front_matter(path.read_text(encoding="utf-8"))
        body_lines = body.split("\n")
        if body_lines and body_lines[0] == "":
            body_lines.pop(0)
        if body_lines and body_lines[-1] == "":
            body_lines.pop()
        restored = demote(body_lines)
        title = str(values["title"])
        refs = list(cast("list[str]", values.get("refs", [])))
        if refs:
            # the H1 lost exactly its trailing "(... #n ...)" list, and refs carries it
            if not section.raw_title.startswith(title + " ("):
                errors.append(f"{section.id}: the cleaned title is not a prefix of the old one")
            tail = section.raw_title[len(title):]
            if [r for r in refs if r.startswith("#")] != re.findall(r"#\d+", tail):
                errors.append(f"{section.id}: refs {refs} do not match the old title's refs")
            if any(r not in tail for r in refs):
                errors.append(f"{section.id}: a ref is not text of the old title")
        elif title != section.raw_title:
            errors.append(f"{section.id}: title changed although it had no ref list")
        if restored[0] != f"## {section.id}: {title}":
            errors.append(f"{section.id}: the H1 is not '# {section.id}: <title>'")
        if restored[1:] != section.lines[1:]:
            errors.append(f"{section.id}: the body differs from the old section")
        if values.get("legacy_anchor") != section.legacy_anchor:
            errors.append(f"{section.id}: legacy_anchor does not match the old heading")
        # account for every old line: this section's lines, then blank separator lines
        if section.start != covered:
            gap = lines[covered : section.start]
            if any(g.strip() for g in gap):
                errors.append(f"old lines {covered + 1}-{section.start} are not accounted for")
        covered = section.start + len(section.lines)
    if any(line.strip() for line in lines[covered:]):
        errors.append(f"old lines after {covered} are not accounted for")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="split the ADR record (#1035)")
    parser.add_argument("--rev", required=True, help="read the old README from this git revision")
    parser.add_argument("--replace", action="store_true",
                        help="overwrite ADR files that differ from the old text (the split's own branch only)")
    parser.add_argument("--verify-only", action="store_true", help="write nothing, only prove")
    args = parser.parse_args(argv)

    text = read_old(args.rev)
    if not any(level == 2 and ADR_H2_RE.match(raw)
               for _i, level, raw in gdi.iter_headings(text.splitlines())):
        print(f"{OLD_PATH} at {args.rev} is already the generated index: the record is split. "
              "Edit the ADR files; do not re-run this migration.", file=sys.stderr)
        return 2
    preamble, sections = split(text)
    numbers = sorted(s.number for s in sections)
    print(f"{len(sections)} ADRs (ADR-{numbers[0]:03d} … ADR-{numbers[-1]:03d}), "
          f"{sum(1 for s in sections if s.refs)} titles cleaned, preamble {len(preamble)} lines")
    mapping = anchor_map(sections)

    folder = ROOT / gdi.ADR_DIR
    # Every file a write would replace: any ADR-nnn-*.md of an old-record number (a file
    # renamed after a title edit too), not only the one with today's derived name.
    changed = [
        s.id for s in sections
        for path in folder.glob(f"ADR-{s.number:03d}-*.md")
        if path.name != s.file_name or path.read_text(encoding="utf-8") != render_file(s)
    ]
    if changed and not args.verify_only and not args.replace:
        print(f"refusing to overwrite ADR files that differ from {args.rev}'s old text: "
              f"{', '.join(changed)}. Move such edits by hand (ADR-083), or pass --replace "
              "on the split's own branch.", file=sys.stderr)
        return 2

    if not args.verify_only:
        # Replace only the files of ADRs the old record holds; a newer ADR (ADR-083 on,
        # written as its own file) is left alone on a re-run.
        for section in sections:
            target = folder / section.file_name
            for old in folder.glob(f"ADR-{section.number:03d}-*.md"):
                if old != target:
                    old.unlink()
            content = render_file(section)
            # skip unchanged files: a rewrite would only churn line endings on a CRLF checkout
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                target.write_text(content, encoding="utf-8", newline="\n")
        errors = gdi.write(ROOT)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
    for line in rewrite_links(mapping, dry=args.verify_only):
        print(line)
    errors = verify(text, preamble, sections) + gdi.check(ROOT)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print("lossless proof:", "FAILED" if errors else "every ADR restores to its old section; "
          "every old line is in an ADR file, the index preamble, or a blank separator")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
