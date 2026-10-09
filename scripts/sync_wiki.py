"""Validate and render repository-owned wiki pages without network or Git writes."""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGES = ("Home.md", "Roadmap.md", "Installation.md", "Contributing.md",
         "Architecture.md", "_Sidebar.md")
INCLUDES = {
    "roadmap-overview": ("Overview", True),
    "roadmap-infrastructure": ("Dev Infrastructure", True),
    "roadmap-phase-17": ("Phase 17: Living Garden 3D", False),
}
MARKER = re.compile(r"^<!-- ogp:include ([a-z0-9-]+) -->$", re.MULTILINE)
LINK = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")


def read_utf8(path: Path) -> str:
    """Decode strictly and reject known corruption in public prose."""
    content = path.read_text(encoding="utf-8")
    if any(token in content for token in ("\ufeff", "\ufffd", "\u00c3\u00a2", "\u00e2\u20ac")):
        raise ValueError(f"Invalid UTF-8 text or mojibake in {path}")
    if re.search(r"\\u[0-9a-fA-F]{4}", content):
        raise ValueError(f"Literal Unicode escape in {path}")
    return content


def source_section(document: str, heading: str, *, table_only: bool) -> str:
    """Extract one unique H2 section, or its first contiguous Markdown table."""
    headings = list(re.finditer(r"^## (.+)$", document, re.MULTILINE))
    matches = [i for i, match in enumerate(headings)
               if match.group(1) == heading or match.group(1).startswith(heading + " (")]
    if len(matches) != 1:
        raise ValueError(f"Expected one roadmap section: {heading} (found {len(matches)})")
    index = matches[0]
    end = headings[index + 1].start() if index + 1 < len(headings) else len(document)
    section = document[headings[index].start():end].strip()
    # Separators belong to the surrounding page, not to the included section.
    section = re.sub(r"\n+---\s*$", "", section)
    if not table_only:
        return section
    table = re.search(r"^\|[^\n]+\n(?:\|[^\n]+\n?)+", section, re.MULTILINE)
    if table is None:
        raise ValueError(f"Missing roadmap table: {heading}")
    return table.group(0).rstrip()


def prose(content: str) -> str:
    """Exclude fenced examples from Markdown link validation."""
    return re.sub(r"^```[^\n]*\n.*?^```[^\n]*$", "", content,
                  flags=re.MULTILINE | re.DOTALL)


def anchor_names(content: str) -> set[str]:
    anchors: set[str] = set()
    for heading in re.findall(r"^#{1,6} (.+)$", prose(content), re.MULTILINE):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        anchors.add(slug)
    return anchors


def validate_links(root: Path, pages: dict[str, str]) -> None:
    """Resolve wiki pages and repository file links locally; do not fetch URLs."""
    prefix = "/cofade/open-garden-planner/"
    for name, content in pages.items():
        for raw_target in LINK.findall(prose(content)):
            target = urlsplit(raw_target.strip().strip("<>"))
            linked_content: str | None = None
            if target.scheme or target.netloc:
                if target.netloc != "github.com" or not target.path.startswith(prefix):
                    continue
                relative = target.path[len(prefix):]
                if not relative.startswith(("blob/master/", "tree/master/")):
                    continue
                path = (root / unquote(relative.split("/", 2)[2])).resolve()
                if not path.is_relative_to(root) or not path.exists():
                    raise ValueError(f"Broken repository link in {name}: {raw_target}")
                if path.is_file() and path.suffix == ".md":
                    linked_content = read_utf8(path)
            else:
                page = unquote(target.path)
                key = page if page.endswith(".md") else page + ".md"
                if not page:
                    key = name
                if key not in pages:
                    raise ValueError(f"Broken wiki link in {name}: {raw_target}")
                linked_content = pages[key]
            if (target.fragment and linked_content is not None
                    and unquote(target.fragment) not in anchor_names(linked_content)):
                raise ValueError(f"Broken heading link in {name}: {raw_target}")


def render_pages(root: Path) -> dict[str, str]:
    root = root.resolve()
    roadmap = read_utf8(root / "docs/roadmap.md")
    includes = {key: source_section(roadmap, heading, table_only=table_only)
                for key, (heading, table_only) in INCLUDES.items()}
    pages: dict[str, str] = {}
    for name in PAGES:
        content = read_utf8(root / "docs/wiki" / name)
        markers = MARKER.findall(content)
        expected = set(INCLUDES) if name == "Roadmap.md" else set()
        if set(markers) != expected or len(markers) != len(expected):
            raise ValueError(f"Missing, duplicate or unexpected inclusion marker in {name}")
        content = MARKER.sub(lambda match: includes[match.group(1)], content)
        if "ogp:include" in content:
            raise ValueError(f"Malformed inclusion marker in {name}")
        pages[name] = content.rstrip() + "\n"
    validate_links(root, pages)
    return pages


def write_pages(root: Path, output: Path, pages: dict[str, str]) -> None:
    output = output.resolve()
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError("Output must be outside the source repository")
    if output.exists() and not output.is_dir():
        raise ValueError("Output must be a directory")
    # Check every target before writing any page. Never follow a file symlink.
    for name in pages:
        path = output / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError(f"Output page is not a regular file: {path}")
    output.mkdir(parents=True, exist_ok=True)
    for name, content in pages.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")


def compare_pages(wiki: Path, pages: dict[str, str]) -> bool:
    if not wiki.is_dir():
        raise ValueError(f"Wiki checkout is unavailable: {wiki}")
    matches = True
    for name, expected in pages.items():
        path = wiki / name
        if not path.is_file():
            print(f"Missing published page: {name}")
            matches = False
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            matches = False
            print("".join(difflib.unified_diff(actual.splitlines(keepends=True),
                                             expected.splitlines(keepends=True),
                                             fromfile=f"published/{name}",
                                             tofile=f"rendered/{name}")), end="")
    return matches


def main(argv: list[str] | None = None) -> int:
    # Windows redirected stdout otherwise uses the system code page for Unicode diffs.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Source repository root")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate sources (default)")
    mode.add_argument("--output", type=Path, help="Render six pages outside the source repo")
    mode.add_argument("--check-published", action="store_true", help="Compare an existing checkout")
    parser.add_argument("--wiki-dir", type=Path, help="Checkout to compare; required for --check-published")
    args = parser.parse_args(argv)
    if bool(args.wiki_dir) != bool(args.check_published):
        parser.error("Use --wiki-dir only with --check-published; both are required")
    root = args.root.resolve()
    try:
        pages = render_pages(root)
        if args.output:
            write_pages(root, args.output, pages)
            print(f"Rendered {len(pages)} wiki pages to {args.output.resolve()}; no Git operations")
        elif args.check_published:
            if not compare_pages(args.wiki_dir, pages):
                return 1
            print("Published wiki pages match repository sources")
        else:
            print(f"Validated {len(pages)} wiki pages and {len(INCLUDES)} roadmap inclusions")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Wiki validation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
