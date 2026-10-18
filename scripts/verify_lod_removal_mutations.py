#!/usr/bin/env python
"""Re-apply every deleted #409 call site and assert the texture pin goes red.

The product change in PR #507 deletes a low-zoom flat fill that never ran. What
replaced it is a *negative* pin — a test that passes while the feature is absent
— and a negative pin has a failure mode a normal suite cannot have: it can stop
noticing. Three senior-review rounds found exactly that, in three different ways:

* the pin sampled the item's **bounding box**, whose corners are page background
  for a circle, an ellipse and a polygon, so a solid circle measured as
  high-contrast;
* it covered four **classes** while three of the seven deleted call sites sat
  behind ``is_plant`` / ``is_furniture_type``, which a ``GENERIC_*`` fixture
  never enters — a flat fill in a plant branch took a ``TREE`` circle from
  interior std 43.09 to 0.00 while 212 tests stayed green;
* its **export mask** sat in the wrong coordinate frame, which made one export
  case pass at spread 45.97 with a flat fill live.

Each was found by mutation, each cost a review round, and none of them is
caught by running the suite. This script makes that the routine: for each of the
seven call sites it re-inserts the branch, asserts the pin fails, and restores
the file. Run it after touching any canvas item's ``paint()``.

Usage::

    venv/Scripts/python.exe scripts/verify_lod_removal_mutations.py
    venv/Scripts/python.exe scripts/verify_lod_removal_mutations.py -v

Run it alone. It rewrites live source files, so two concurrent runs would
interleave writes into the same four files and restore the wrong content; the
lock below makes a second invocation exit rather than corrupt the tree. That
trade - rewriting source instead of copying a tree - is why this is not in CI.

Exit code 0 means every site is still watched.
"""

from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ITEMS = REPO / "src" / "open_garden_planner" / "ui" / "canvas" / "items"
PIN = "tests/integration/test_canvas_item_cache.py"

# (label, file, anchor to insert BEFORE, draw call, indent)
SITES: list[tuple[str, str, str, str, int]] = [
    (
        "rectangle / generic",
        "rectangle_item.py",
        "        # Fall back to standard rectangle painting",
        "painter.drawRect(self.rect())",
        8,
    ),
    (
        "rectangle / furniture",
        "rectangle_item.py",
        "            rect = self.rect()\n            pixmap = render_furniture_pixmap(",
        "painter.drawRect(rect)",
        12,
    ),
    (
        "circle / plant",
        "circle_item.py",
        "            # Render at a larger size so organic shapes fill the circle",
        "painter.drawEllipse(rect)",
        12,
    ),
    (
        "circle / furniture",
        "circle_item.py",
        "            rect = self.rect()\n            diameter = rect.width()",
        "painter.drawEllipse(rect)",
        12,
    ),
    (
        "circle / generic",
        "circle_item.py",
        "        # Fall back to standard ellipse painting for non-plant/furniture circles",
        "painter.drawEllipse(self.rect())",
        8,
    ),
    (
        "ellipse / generic",
        "ellipse_item.py",
        "        # F9: soil-mismatch border for bed-typed ellipses (US-12.10d).",
        "painter.drawEllipse(self.rect())",
        8,
    ),
    (
        "polygon / generic",
        "polygon_item.py",
        "        # For HOUSE polygons with a ridge: use mirrored tile rendering",
        "painter.drawPolygon(poly)",
        8,
    ),
]

BRANCH = """{i}from PyQt6.QtGui import QBrush as _MB, QColor as _MC

{i}if (
{i}    not self.isSelected()
{i}    and option is not None
{i}    and option.levelOfDetailFromTransform(painter.worldTransform()) < 0.4
{i}):
{i}    painter.save()
{i}    painter.setPen(self.pen())
{i}    painter.setBrush(_MB(_MC(31, 79, 216)))
{i}    {draw}
{i}    painter.restore()
{i}    return

"""

# The assertion text that means "the pin saw a flat fill", as opposed to some
# incidental error such as a NameError in the mutant.
ON_TEXTURE = ("flat fill at zoom", "lost the")

# Guards against a concurrent run: see the module docstring.
LOCK = Path(__file__).resolve().parent / ".verify_lod_removal_mutations.lock"


class AlreadyRunning(RuntimeError):
    """Another instance holds the lock; the tree would be interleaved."""


def _parses(path: Path) -> bool:
    try:
        ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    return True


def check_site(fname: str, anchor: str, draw: str, indent: int) -> str:
    path = ITEMS / fname
    original = path.read_text(encoding="utf-8")
    if anchor not in original:
        return "ANCHOR-MISSING (the anchor text moved — update SITES)"
    body = BRANCH.format(draw=draw, i=" " * indent)
    try:
        # The write is INSIDE the try: Path.write_text truncates before it
        # writes, so a kill during that call would leave a TRUNCATED source file
        # with no mutant left to undo - strictly worse than a mutated one, and
        # `git checkout -- src/` the only way back.
        path.write_text(original.replace(anchor, body + anchor, 1), encoding="utf-8")
        if not _parses(path):
            return "MUTANT-INVALID (this script's own mutant is broken)"
        proc = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pytest",
                PIN,
                "-q",
                "--no-header",
                # One pinned file, replayed once per mutant against a wall-clock
                # timeout. `addopts`' `-n auto` would spend that budget starting
                # workers for a single file (#509).
                "-n",
                "0",
            ],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    finally:
        path.write_text(original, encoding="utf-8")

    if proc.returncode == 0:
        return "SURVIVED — the pin no longer watches this call site"
    if any(needle in proc.stdout for needle in ON_TEXTURE):
        return "caught (on a texture assertion)"
    return "caught, but NOT on a texture assertion — check why it failed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print pytest's tail for each site",
    )
    args = parser.parse_args()

    try:
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        owner = (
            LOCK.read_text(encoding="utf-8", errors="replace").strip().lstrip("\ufeff")
            or "?"
        )
        alive = ""
        if owner.isdigit():
            # A stale lock must be decidable, not a guess. tasklist exits 0 even
            # when nothing matches, so the OUTPUT is the signal, not the return
            # code - reading the code would report every stale lock as alive,
            # which is the reassuring direction to be wrong in.
            if sys.platform == "win32":
                # errors="replace" is load-bearing: tasklist emits bytes the
                # console codec (cp1252 here) cannot decode, and a text-mode
                # subprocess then hands back stdout=None - which turned the
                # advisory into a crash on the exact path it exists to help
                # with.
                out = (
                    subprocess.run(
                        ["tasklist", "/FI", f"PID eq {owner}"],
                        capture_output=True,
                        text=True,
                        errors="replace",
                        check=False,
                    ).stdout
                    or ""
                )
                alive = owner in out and "No tasks" not in out
            else:
                alive = (
                    subprocess.run(
                        ["kill", "-0", owner], capture_output=True, check=False
                    ).returncode
                    == 0
                )
            alive_text = (
                "  (that process looks alive - do not delete the lock)"
                if alive
                else "  (no such process: the lock is stale and can be deleted)"
            )
        else:
            alive_text = "  (the lock records no pid)"
        print(
            f"refusing to run: {LOCK.name} exists, held by pid {owner}. Two runs "
            "would interleave writes into the same four source files."
            f"{alive_text}"
        )
        return 1
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return _run(args)
    finally:
        LOCK.unlink(missing_ok=True)


def _run(args: argparse.Namespace) -> int:
    print(f"Re-applying {len(SITES)} deleted #409 call sites against {PIN}\n")
    results: list[tuple[str, str]] = []
    for label, fname, anchor, draw, indent in SITES:
        verdict = check_site(fname, anchor, draw, indent)
        results.append((label, verdict))
        marker = "OK  " if verdict.startswith("caught (") else "FAIL"
        print(f"  [{marker}] {label:<24} {verdict}")
        if args.verbose and verdict.startswith("SURVIVED"):
            print("      the pin passed with a flat fill re-inserted at this site")

    bad = [(lab, v) for lab, v in results if not v.startswith("caught (")]
    print()
    if bad:
        print(f"{len(bad)} of {len(SITES)} call sites are not correctly watched:")
        for lab, v in bad:
            print(f"  - {lab}: {v}")
        return 1
    print(f"All {len(SITES)} call sites are watched; the removal is verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
