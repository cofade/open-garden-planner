"""Verify that identifiers cited across the skill libraries still resolve.

The skill files under ``.claude/skills/`` and ``.agents/skills/`` (plus
``CLAUDE.md`` / ``AGENTS.md``) are dense with cross-references: numbered doc
sections (``§8.10``), ADRs (``ADR-033``), functional requirements
(``FR-AGENT-03``), ``file.py:line`` citations, and GitHub issue/PR numbers
(``#336``). Nothing previously verified that those references still point at
something real. This module is that check (issue #336).

Scope, deliberately: this gate resolves *identifiers*, not *claims*. It does
not try to verify that a citation's surrounding prose is still an accurate
description of the cited thing — only that the thing named still exists.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CORPUS_GLOBS: tuple[str, ...] = (
    ".claude/skills/*/SKILL.md",
    ".agents/skills/*/SKILL.md",
    "CLAUDE.md",
    "AGENTS.md",
)

# Numbered arc42 chapters live at docs/0N-*/README.md (01 through 12); chapter
# 09 (architecture decisions) uses ADR-0NN headings instead of N.M sections.
_DOC_CHAPTER_NUMBERS = tuple(n for n in range(1, 13) if n != 9)

ADR_INDEX_PATH = "docs/09-architecture-decisions/README.md"
FR_INDEX_PATH = "docs/functional-requirements.md"
ISSUE_REGISTRY_PATH = "tests/data/issue_registry.json"

# (source file relative to repo root, exact raw citation text) -> reason.
# Mirrors the exemption-list convention in tests/unit/test_icon_conformance.py
# / check_icon_conformance.py's PROVENANCE guard: every entry states why it is
# exempt rather than silently skipping it.
KNOWN_EXCEPTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (
            ".claude/skills/debug-verbose/SKILL.md",
            "pytestqt/plugin.py:220",
        ): "third-party library (pytest-qt runtime dependency), not part of this repo",
        (
            ".agents/skills/debug-verbose/SKILL.md",
            "pytestqt/plugin.py:220",
        ): "third-party library (pytest-qt runtime dependency), not part of this repo",
    }
)

_HEADING_RE = re.compile(r"^#{1,4}\s+(\d+(?:\.\d+){0,2})\b", re.MULTILINE)
_SECTION_REF_RE = re.compile(
    r"(?:§|[Ss]ection )(\d+(?:\.\d+){0,2}(?:/\d+(?:\.\d+){0,2})*)"
)
_ADR_REF_RE = re.compile(r"ADR-(\d{3})(?:/(\d{3}))*")
_ADR_HEADING_RE = re.compile(r"^##\s+ADR-(\d{3})\b", re.MULTILINE)
_FR_REF_RE = re.compile(r"\bFR-(?:([A-Z]+)-)?(\d+(?:/\d+)*)\b")
_FR_HEADING_RE = re.compile(r"^#{2,3}\s+FR-([A-Z0-9-]+?)[:\s]", re.MULTILINE)
_FR_BULLET_RE = re.compile(r"^-\s+\*\*FR-([A-Z0-9-]+?)\*\*", re.MULTILINE)
_FILE_LINE_RE = re.compile(
    r"`((?:[\w.-]+/)*[\w.-]+\.py):(\d+(?:/\d+)*)`(?:\s*`([^`]+)`)?"
)
_ISSUE_REF_RE = re.compile(r"(?:\b(PR|[Ii]ssue) )?#(\d{2,5})\b")
_IDENTIFIER_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)")

# How far a cited line may have drifted from a still-correct symbol before the
# citation counts as rot rather than ordinary refactor churn. Wide enough to
# tolerate a function moving within its file; narrow enough to have caught
# the #336 case (a citation off by ~1300 lines after unrelated features grew
# the file).
_SYMBOL_WINDOW_LINES = 300


@dataclass(frozen=True)
class Citation:
    file: str
    line: int
    raw: str


def find_corpus_files(root: Path = REPO_ROOT) -> list[Path]:
    files: list[Path] = []
    for pattern in CORPUS_GLOBS:
        files.extend(sorted(root.glob(pattern)))
    return files


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_matches(text: str, pattern: re.Pattern[str]):
    for match in pattern.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        yield line, match


def _is_excepted(rel_file: str, raw: str) -> bool:
    return (rel_file, raw) in KNOWN_EXCEPTIONS


# --- §N.M / "section N.M" references ---------------------------------------


def _own_section_headings(text: str) -> set[str]:
    return {m.group(1) for m in _HEADING_RE.finditer(text)}


def build_section_pool(root: Path, corpus_files: list[Path]) -> set[str]:
    """All numbered headings anywhere a §N.M citation could legitimately
    point: every corpus file's own headings, plus the numbered arc42
    chapters. A citation only has to resolve *somewhere* in this pool —
    this gate checks that identifiers resolve, not that a citation points
    at the one "correct" file among several plausible ones.
    """

    pool: set[str] = set()
    for path in corpus_files:
        pool |= _own_section_headings(path.read_text(encoding="utf-8"))
    for n in _DOC_CHAPTER_NUMBERS:
        matches = sorted((root / "docs").glob(f"{n:02d}-*/README.md"))
        for doc in matches:
            pool |= _own_section_headings(doc.read_text(encoding="utf-8"))
    return pool


def check_section_refs(
    root: Path, corpus_files: list[Path], pool: set[str]
) -> list[str]:
    errors: list[str] = []
    for path in corpus_files:
        rel_file = _rel(root, path)
        text = path.read_text(encoding="utf-8")
        for line, match in _iter_matches(text, _SECTION_REF_RE):
            raw = match.group(0)
            if _is_excepted(rel_file, raw):
                continue
            for number in match.group(1).split("/"):
                if number not in pool:
                    errors.append(
                        f"{rel_file}:{line}: section reference '{raw}' — "
                        f"no heading '{number}' found in any skill file or "
                        "numbered arc42 chapter"
                    )
    return errors


# --- ADR-0NN references ------------------------------------------------------


def build_adr_pool(root: Path) -> set[str]:
    text = (root / ADR_INDEX_PATH).read_text(encoding="utf-8")
    return {m.group(1) for m in _ADR_HEADING_RE.finditer(text)}


def check_adr_refs(
    root: Path, corpus_files: list[Path], pool: set[str]
) -> list[str]:
    errors: list[str] = []
    for path in corpus_files:
        rel_file = _rel(root, path)
        text = path.read_text(encoding="utf-8")
        for line, match in _iter_matches(text, _ADR_REF_RE):
            raw = match.group(0)
            if _is_excepted(rel_file, raw):
                continue
            numbers = [match.group(1)] + [g for g in match.groups()[1:] if g]
            for number in numbers:
                if number not in pool:
                    errors.append(
                        f"{rel_file}:{line}: '{raw}' cites ADR-{number}, "
                        f"which has no heading in {ADR_INDEX_PATH}"
                    )
    return errors


# --- FR-* references ----------------------------------------------------------


def build_fr_pool(root: Path) -> set[str]:
    text = (root / FR_INDEX_PATH).read_text(encoding="utf-8")
    pool = {m.group(1) for m in _FR_HEADING_RE.finditer(text)}
    pool |= {m.group(1) for m in _FR_BULLET_RE.finditer(text)}
    return pool


def check_fr_refs(root: Path, corpus_files: list[Path], pool: set[str]) -> list[str]:
    errors: list[str] = []
    for path in corpus_files:
        rel_file = _rel(root, path)
        text = path.read_text(encoding="utf-8")
        for line, match in _iter_matches(text, _FR_REF_RE):
            raw = match.group(0)
            if _is_excepted(rel_file, raw):
                continue
            namespace = match.group(1)
            numbers = match.group(2).split("/")
            for number in numbers:
                fr_id = f"{namespace}-{number}" if namespace else number
                if fr_id not in pool:
                    errors.append(
                        f"{rel_file}:{line}: '{raw}' cites FR-{fr_id}, which "
                        f"has no entry in {FR_INDEX_PATH}"
                    )
    return errors


# --- file.py:line citations --------------------------------------------------


def _py_files(root: Path) -> list[Path]:
    return sorted((root / "src").rglob("*.py"))


def _resolve_path_citation(root: Path, cited_path: str, py_files: list[Path]) -> list[Path]:
    matches = []
    for f in py_files:
        rel = f.relative_to(root).as_posix()
        if rel == cited_path or rel.endswith("/" + cited_path):
            matches.append(f)
    return matches


def check_file_line_refs(root: Path, corpus_files: list[Path]) -> list[str]:
    errors: list[str] = []
    py_files = _py_files(root)
    for path in corpus_files:
        rel_file = _rel(root, path)
        text = path.read_text(encoding="utf-8")
        for line, match in _iter_matches(text, _FILE_LINE_RE):
            raw = match.group(0)
            cited_path, lines_str, symbol_text = match.groups()
            if _is_excepted(rel_file, f"{cited_path}:{lines_str}"):
                continue
            candidates = _resolve_path_citation(root, cited_path, py_files)
            if not candidates:
                errors.append(
                    f"{rel_file}:{line}: '{raw}' cites '{cited_path}', which "
                    "does not exist under src/"
                )
                continue

            symbol = None
            if symbol_text:
                sym_match = _IDENTIFIER_RE.match(symbol_text)
                symbol = sym_match.group(1) if sym_match else None

            resolved = False
            reasons: list[str] = []
            for candidate in candidates:
                lines = candidate.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                total_lines = len(lines)
                cited_lines = [int(x) for x in lines_str.split("/")]
                bad_lines = [n for n in cited_lines if n > total_lines]
                if bad_lines:
                    reasons.append(
                        f"{candidate.relative_to(root).as_posix()} has "
                        f"{total_lines} lines, cited line(s) {bad_lines} "
                        "out of range"
                    )
                    continue
                if symbol:
                    windows_ok = []
                    for cited_line in cited_lines:
                        lo = max(0, cited_line - 1 - _SYMBOL_WINDOW_LINES)
                        hi = min(total_lines, cited_line + _SYMBOL_WINDOW_LINES)
                        window = "\n".join(lines[lo:hi])
                        windows_ok.append(
                            re.search(rf"\b{re.escape(symbol)}\b", window)
                            is not None
                        )
                    if not any(windows_ok):
                        reasons.append(
                            f"symbol '{symbol}' not found within "
                            f"{_SYMBOL_WINDOW_LINES} lines of the cited "
                            f"line(s) in {candidate.relative_to(root).as_posix()}"
                        )
                        continue
                resolved = True
                break

            if not resolved:
                errors.append(f"{rel_file}:{line}: '{raw}' — {'; '.join(reasons)}")
    return errors


# --- #NNN issue/PR references ------------------------------------------------


def load_issue_registry(root: Path) -> dict[str, dict]:
    return json.loads((root / ISSUE_REGISTRY_PATH).read_text(encoding="utf-8"))


def check_issue_refs(
    root: Path, corpus_files: list[Path], registry: dict[str, dict]
) -> list[str]:
    errors: list[str] = []
    for path in corpus_files:
        rel_file = _rel(root, path)
        text = path.read_text(encoding="utf-8")
        for line, match in _iter_matches(text, _ISSUE_REF_RE):
            raw = match.group(0)
            if _is_excepted(rel_file, raw):
                continue
            keyword, number = match.groups()
            entry = registry.get(number)
            if entry is None:
                errors.append(
                    f"{rel_file}:{line}: '{raw}' does not match any known "
                    f"issue or PR (refresh {ISSUE_REGISTRY_PATH} if this is "
                    "genuinely new)"
                )
                continue
            if keyword == "PR" and not entry["is_pr"]:
                errors.append(
                    f"{rel_file}:{line}: '{raw}' is labeled a PR but #{number} "
                    f"is an issue ('{entry['title']}')"
                )
            elif keyword is not None and keyword.lower() == "issue" and entry["is_pr"]:
                errors.append(
                    f"{rel_file}:{line}: '{raw}' is labeled an issue but "
                    f"#{number} is a PR ('{entry['title']}')"
                )
    return errors


# --- orchestration ------------------------------------------------------------


def check_repo(root: Path = REPO_ROOT) -> list[str]:
    corpus_files = find_corpus_files(root)
    errors: list[str] = []
    errors += check_section_refs(root, corpus_files, build_section_pool(root, corpus_files))
    errors += check_adr_refs(root, corpus_files, build_adr_pool(root))
    errors += check_fr_refs(root, corpus_files, build_fr_pool(root))
    errors += check_file_line_refs(root, corpus_files)
    errors += check_issue_refs(root, corpus_files, load_issue_registry(root))
    return errors


def main() -> int:
    errors = check_repo()
    if errors:
        print(f"Found {len(errors)} unresolved citation(s):")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("All skill-library citations resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
