"""#874: the Windows font backend must show a hinting regression in pixels."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def native_pixels():
    if sys.platform != "win32":
        pytest.skip("Windows font hinting and native repaint oracle")
    driver = Path(__file__).with_name("canvas_native_pixels.py")
    done = subprocess.run([sys.executable, str(driver)], capture_output=True,
                          text=True, encoding="utf-8", timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout.splitlines()[-1])


def test_zoomed_letter_gaps_match_a_high_resolution_reference(native_pixels):
    # A single-pixel raster phase is unavoidable; two pixels are a visible gap.
    assert max(native_pixels["gaps"]) <= 1.0
    assert min(native_pixels["hinted"]) > 1.0, "the negative control must see the old defect"


def test_selected_repaints_match_full_repaints_on_windows(native_pixels):
    assert max(native_pixels["repaints"]) == 0


def test_balcony_note_clears_the_furniture_with_native_fonts(native_pixels):
    for result in native_pixels["balcony"].values():
        assert not result["overlaps"]
        assert result["note"][0] + result["note"][2] < 300
