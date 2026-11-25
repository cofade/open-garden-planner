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


def test_selected_shed_replacement_repaints_in_the_main_window(native_pixels):
    for edit, result in native_pixels["embedded_shed"].items():
        assert result["changed"] > 0 and result["regions"], edit
        assert result["repeat_noise"] == 0, (edit, result)
        # #1004's own next step, now a guard: the edit's paint regions must cover
        # the item's old AND new bounds. A strip left out is a missing invalidate,
        # a defect no pixel comparison can name.
        assert result["uncovered"] == [], (edit, result)
        assert result["diff"] == 0, (edit, result)


def test_balcony_note_clears_the_furniture_with_native_fonts(native_pixels):
    for result in native_pixels["balcony"].values():
        assert not result["overlaps"]
        assert result["note"][0] + result["note"][2] < 300


def test_same_size_content_changes_repaint_relocated_foreground(native_pixels):
    for case, result in native_pixels["foreground"].items():
        assert result["equal_bounds"], case
        assert result["changed"] > 0, f"{case}: missing content must not pass"
        assert result["repeat_noise"] == 0, f"{case}: reject raster noise in the oracle"
        assert result["stale"] == 0, f"{case}: the partial repaint left stale pixels"
