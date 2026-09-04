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

It is also syntactic, not semantic: a ``file.py:line`` citation is only
checked when it appears in the single backtick-quoted form ``path.py:N``
(optionally followed by a backtick-quoted symbol/snippet), searched under
``src/``, ``tests/``, ``scripts/``, and ``installer/``. A citation spelled
out in prose ("application.py line ~2893") is invisible to it — normalize a
citation into the gated form to bring it under the gate, the same way a
string has to go through ``tr()`` to be seen by the i18n gate (§8.3's own
"a plain string never reaches it" blind spot).
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

# (source file relative to repo root, citation key) -> reason. The key is the
# exact matched text (match.group(0)) for every check except file:line, which
# keys on "path:line(s)" with no backticks/symbol (see check_file_line_refs).
# Mirrors the exemption-list convention in tests/unit/test_settings_chokepoint.py
# (STORE_CLASS_EXEMPT_TESTS + its test_no_exemption_is_dead): every entry
# states why it is exempt, and test_skill_citations.py's own
# test_no_exemption_is_dead fails if an entry stops being needed.
KNOWN_EXCEPTIONS: dict[tuple[str, str], str] = {
    (
        ".claude/skills/debug-verbose/SKILL.md",
        "pytestqt/plugin.py:220",
    ): "third-party library (pytest-qt runtime dependency), not part of this repo",
    (
        ".agents/skills/debug-verbose/SKILL.md",
        "pytestqt/plugin.py:220",
    ): "third-party library (pytest-qt runtime dependency), not part of this repo",
}

_HEADING_RE = re.compile(r"^#{1,6}\s+(\d+(?:\.\d+){0,2})\b", re.MULTILINE)
_SECTION_REF_RE = re.compile(
    r"(?:§|[Ss]ection )(\d+(?:\.\d+){0,2}(?:/\d+(?:\.\d+){0,2})*)"
)
_ADR_REF_RE = re.compile(r"ADR-(\d{3}(?:/\d{3})*)\b")
_ADR_HEADING_RE = re.compile(r"^##\s+ADR-(\d{3})\b", re.MULTILINE)
_FR_REF_RE = re.compile(r"\bFR-(?:([A-Z]+)-)?(\d+(?:/\d+)*)\b")
_FR_HEADING_RE = re.compile(r"^#{2,6}\s+FR-([A-Z0-9-]+?)[:\s]", re.MULTILINE)
_FR_BULLET_RE = re.compile(r"^-\s+\*\*FR-([A-Z0-9-]+?)\*\*", re.MULTILINE)
_FILE_LINE_RE = re.compile(
    r"`((?:[\w.-]+/)*[\w.-]+\.py):(\d+(?:/\d+)*)`(?:\s*`([^`]+)`)?"
)
# A bare `#1234` needs no keyword; when one *is* present, it must agree with
# the registry (a citation this narrow and literal is not "clever about
# prose" — it never guesses at what a citation's surrounding claim means).
_ISSUE_REF_RE = re.compile(r"(?:\b(PR|[Ii]ssue) )?#(\d{2,5})\b")
# The trailing identifier/call name in a cited snippet, e.g.
# "self._x.set_panel_visible(...)" -> "set_panel_visible", not "self".
_CALL_NAME_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_BARE_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_STRING_LITERAL_RE = re.compile(r'"([^"]+)"|\'([^\']+)\'')

# How far a cited line may have drifted from a still-correct symbol before the
# citation counts as rot rather than ordinary refactor churn. Wide enough to
# tolerate a function moving within its file; narrow enough to have caught
# the #336 case (a citation off by ~1300 lines after unrelated features grew
# the file).
_SYMBOL_WINDOW_LINES = 300

# A string literal named in the cited snippet only has to sit next to the
# SAME occurrence of the symbol, not merely somewhere in the whole 300-line
# window — otherwise a recurring generic call (e.g. one setter invoked once
# per sidebar panel, each a few dozen lines apart) would "confirm" against
# whichever sibling call happens to share the window, not the cited one.
_LITERAL_PROXIMITY_LINES = 2


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


def _extract_symbol(text: str) -> str | None:
    """The identifier a cited snippet is actually about: the name of its
    last call (``self._x.set_panel_visible(...)`` -> ``set_panel_visible``,
    not ``self``), or its last bare identifier if it names no call at all
    (a class name like ``ResizeItemCommand``).
    """

    calls = _CALL_NAME_RE.findall(text)
    if calls:
        return calls[-1]
    names = _BARE_IDENTIFIER_RE.findall(text)
    return names[-1] if names else None


def _symbol_occurs(
    lines: list[str], lo: int, hi: int, symbol: str, literals: list[str]
) -> bool:
    """Whether `symbol` occurs in lines[lo:hi] AND, at that same specific
    occurrence, every literal from the cited snippet is nearby — not just
    somewhere else in the (much larger) window.
    """

    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    for i in range(lo, hi):
        if not pattern.search(lines[i]):
            continue
        local_lo = max(lo, i - _LITERAL_PROXIMITY_LINES)
        local_hi = min(hi, i + 1 + _LITERAL_PROXIMITY_LINES)
        local_text = "\n".join(lines[local_lo:local_hi])
        if all(lit in local_text for lit in literals):
            return True
    return False


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
            for number in match.group(1).split("/"):
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


# First-party Python lives under these; build/ and dist/ are gitignored
# PyInstaller output and venv/ is the virtualenv — none are things a skill
# file should be citing, and walking them would be slow and pointless.
_PY_SEARCH_DIRS = ("src", "tests", "scripts", "installer")


def _py_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for d in _PY_SEARCH_DIRS:
        files.extend((root / d).rglob("*.py"))
    return sorted(files)


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
                    f"does not exist under {'/, '.join(_PY_SEARCH_DIRS)}/"
                )
                continue

            symbol = _extract_symbol(symbol_text) if symbol_text else None
            literals = _STRING_LITERAL_RE.findall(symbol_text) if symbol_text else []
            literals = [a or b for a, b in literals]

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
                        windows_ok.append(
                            _symbol_occurs(lines, lo, hi, symbol, literals)
                        )
                    if not any(windows_ok):
                        reasons.append(
                            f"symbol '{symbol}'"
                            + (f" with literal(s) {literals}" if literals else "")
                            + f" not found within {_SYMBOL_WINDOW_LINES} lines "
                            f"of the cited line(s) in "
                            f"{candidate.relative_to(root).as_posix()}"
                        )
                        continue
                resolved = True
                break

            if not resolved:
                errors.append(f"{rel_file}:{line}: '{raw}' — {'; '.join(reasons)}")
    return errors


# --- #NNN issue/PR references ------------------------------------------------


def load_issue_registry(root: Path) -> dict[str, dict]:
    """Each entry also carries ``title``/``state`` for a human reading a
    gate failure or the snapshot itself; only ``is_pr`` is read by the
    checks below (a bare ``#NNN`` deliberately makes no claim about state —
    most citations in this corpus are to long-closed historical bugs).
    """
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
                    f"issue or PR ({ISSUE_REGISTRY_PATH} is stale — run "
                    "scripts/refresh_issue_registry.py if this is genuinely new)"
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
