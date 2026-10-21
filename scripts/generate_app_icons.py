"""Generate multi-resolution Windows .ico icons from OGP_logo.png.

Generates:
- installer/ogp_app.ico
- installer/ogp_file.ico
- src/open_garden_planner/resources/icons/ogp_app.ico

Standard Windows sizes: 16x16, 24x24, 32x32, 48x48, 64x64, 128x128, 256x256.

Usage:
    python scripts/generate_app_icons.py
    python scripts/generate_app_icons.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE_PNG = ROOT / "src" / "open_garden_planner" / "resources" / "icons" / "OGP_logo.png"

TARGET_ICOS = [
    ROOT / "installer" / "ogp_app.ico",
    ROOT / "installer" / "ogp_file.ico",
    ROOT / "src" / "open_garden_planner" / "resources" / "icons" / "ogp_app.ico",
]

STANDARD_SIZES: list[tuple[int, int]] = [
    (16, 16),
    (24, 24),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]
EXPECTED_SIZES_SET = set(STANDARD_SIZES)


def generate_icons() -> None:
    """Generate all target .ico files from the master PNG."""
    if not SOURCE_PNG.is_file():
        raise FileNotFoundError(f"Source logo not found: {SOURCE_PNG}")

    im = Image.open(SOURCE_PNG).convert("RGBA")
    for target in TARGET_ICOS:
        target.parent.mkdir(parents=True, exist_ok=True)
        im.save(target, format="ICO", sizes=STANDARD_SIZES)
        print(f"Generated {target.relative_to(ROOT)} ({target.stat().st_size} bytes)")


def check_icons() -> bool:
    """Check that all target .ico files exist and contain all required sizes."""
    ok = True
    for target in TARGET_ICOS:
        if not target.is_file():
            print(f"FAIL: {target.relative_to(ROOT)} is missing", file=sys.stderr)
            ok = False
            continue
        try:
            im = Image.open(target)
            sizes = im.info.get("sizes")
            im.close()
            if sizes != EXPECTED_SIZES_SET:
                print(
                    f"FAIL: {target.relative_to(ROOT)} has sizes {sizes}, expected {EXPECTED_SIZES_SET}",
                    file=sys.stderr,
                )
                ok = False
            else:
                print(f"OK: {target.relative_to(ROOT)} ({len(sizes)} resolutions)")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL: cannot inspect {target.relative_to(ROOT)}: {exc}", file=sys.stderr)
            ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check without writing")
    args = parser.parse_args()

    if args.check:
        return 0 if check_icons() else 1

    generate_icons()
    return 0 if check_icons() else 1


if __name__ == "__main__":
    sys.exit(main())
