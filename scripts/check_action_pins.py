"""Read-only gate: every external GitHub Action must be pinned to an immutable commit (AUD-053).

Scans ``.github/workflows/*.yml`` and ``.github/actions/*/action.yml`` for ``uses:``
references. Rules:

* local actions (``./...``) are allowed as-is;
* ``docker://`` references are allowed as-is (immutability is the image digest's job);
* every other reference must be ``owner/repo@<40 lowercase hex>`` followed by a
  readable ``# vX.Y.Z`` comment.

The check is line-based on purpose: ``yaml.safe_load`` would discard exactly the
version comment this gate exists to require.

Exit codes: 0 = all pinned, 2 = violation or unreadable input. Never repairs files.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

USES_RE = re.compile(r"^(?P<indent>\s*)-\s+uses:\s*(?P<ref>[^#\s]+)\s*(?:#\s*(?P<comment>.+?))?\s*$")
STEP_USES_RE = re.compile(r"^(?P<indent>\s+)uses:\s*(?P<ref>[^#\s]+)\s*(?:#\s*(?P<comment>.+?))?\s*$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^v\d+(?:\.\d+)*\b")

ALLOWED_PREFIXES = ("./", "docker://")


def _target_files(root: Path) -> list[Path]:
    files = sorted((root / ".github" / "workflows").glob("*.yml"))
    files += sorted((root / ".github" / "actions").glob("*/action.yml"))
    return [f for f in files if f.is_file()]


def _violations_in(text: str) -> list[tuple[int, str, str]]:
    """Return (line_number, reference, reason) for each unpinned ``uses:``."""
    found: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = USES_RE.match(line) or STEP_USES_RE.match(line)
        if match is None:
            continue
        ref = match.group("ref")
        comment = match.group("comment") or ""
        if ref.startswith(ALLOWED_PREFIXES):
            continue
        if "@" not in ref:
            found.append((lineno, ref, "reference has no '@<commit>' part"))
            continue
        repo, _, pinned = ref.rpartition("@")
        if not repo:
            found.append((lineno, ref, "reference has an empty 'owner/repo' part"))
            continue
        if not SHA_RE.match(pinned):
            found.append((lineno, ref, "not pinned to a 40-hex commit SHA"))
            continue
        if not VERSION_RE.match(comment.strip()):
            found.append((lineno, ref, "SHA lacks a readable '# vX.Y.Z' version comment"))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()

    files = _target_files(root)
    if not files:
        print(f"No workflow/action files found under {root}", file=sys.stderr)
        return 2

    bad = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{path}: cannot read ({exc})", file=sys.stderr)
            bad += 1
            continue
        for lineno, ref, reason in _violations_in(text):
            rel = path.relative_to(root)
            print(f"{rel}:{lineno}: {ref}: {reason}", file=sys.stderr)
            bad += 1

    if bad:
        print(f"Action pin check failed: {bad} violation(s)", file=sys.stderr)
        return 2
    print(f"All {len(files)} workflow/action files pin every external action to a commit SHA")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
