"""AUD-052: the stale second dependency manifests must stay deleted.

``requirements.txt`` carried ``PyQt6>=6.6.0`` — the exact spec that caused the
#277 Qt micro mismatch — while the real selection lives in ``uv.lock`` /
``pylock.toml``. Narrative and decision records (``docs/`` outside the wiki,
and the dated audit snapshot in ``docs/11``) describe the removal and are
excluded from the scan, which targets the surfaces that *instruct* a reader:
skills, the wiki, CI, scripts, configuration and code.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

MANIFESTS = ["requirements.txt", "requirements-dev.txt"]

#: A bare token, so ``locked-requirements.txt`` in a CI step does not match.
REFERENCE_RE = re.compile(r"(?<![\w-])requirements(?:-dev)?\.txt")

SCAN_DIRS = ["src", "tests", "scripts", ".github", "installer", "quality",
             ".agents/skills", ".claude/skills", "docs/wiki"]
SCAN_FILES = ["README.md", "AGENTS.md", "CLAUDE.md", "CONTRIBUTING.md", "pyproject.toml"]

SELF = Path("tests/unit/test_no_stale_requirement_manifests.py")


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for rel in SCAN_DIRS:
        base = ROOT / rel
        if base.is_dir():
            files.extend(p for p in base.rglob("*") if p.is_file())
    files.extend(ROOT / name for name in SCAN_FILES if (ROOT / name).is_file())
    return files


def test_the_stale_manifests_are_gone() -> None:
    for name in MANIFESTS:
        assert not (ROOT / name).exists(), (
            f"{name} is back — the locked recipe (uv.lock/pylock.toml) is the only "
            "dependency source of truth"
        )


def test_nothing_current_references_the_removed_manifests() -> None:
    offenders: list[str] = []
    for path in _scanned_files():
        rel = path.relative_to(ROOT)
        if rel == SELF:
            continue
        if rel.suffix.lower() not in {".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if REFERENCE_RE.search(text):
            offenders.append(str(rel))
    assert not offenders, "stale manifest references remain: " + ", ".join(sorted(offenders))
