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

Exit code 0 means every site is still watched. It is deliberately NOT part of
the default test run: it rewrites source files, so it belongs to a review or a
pre-merge sweep, not to CI on a pull request.
"""

from __future__ import annotations

import argparse
import ast
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
    path.write_text(original.replace(anchor, body + anchor, 1), encoding="utf-8")
    try:
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

    print(f"Re-applying {len(SITES)} deleted #409 call sites against {PIN}\n")
    results: list[tuple[str, str]] = []
    for label, fname, anchor, draw, indent in SITES:
        verdict = check_site(fname, anchor, draw, indent)
        results.append((label, verdict))
        marker = "OK  " if verdict.startswith("caught (") else "FAIL"
        print(f"  [{marker}] {label:<24} {verdict}")
        if args.verbose and not verdict.startswith("caught ("):
            print("      (run pytest on the file by hand to see the failure)")

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
