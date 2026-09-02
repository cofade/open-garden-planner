"""Live end-to-end harness for the satellite picker's JS view capture.

Drives the REAL MapPickerDialog + REAL Google Maps page with a real API
key and prints the whole pan-grid choreography (profile -> frames ->
stitch) with timestamps. This is the instrument that caught the #347
live-only bug: the page's guards compared a NUMERIC capture token against
its STRING form and silently ate every capture report, so the dialog
timed out while every test was green (tests drive the bridge directly
and never run the page's JavaScript).

Usage (from the repo root, needs a key in .env / OGP_GOOGLE_MAPS_KEY):

    PYTHONUTF8=1 venv/Scripts/python.exe -u scripts/live_capture_harness.py

The map takes a few seconds to load; the capture starts automatically
after 8 s for a hard-coded Berlin box. Anything the page reports through
the bridge is printed; a capture that reaches the stitch prints the
result's tile grid. The dialog closes itself after 90 s. Windows-only
harness (QtWebEngine window), not part of CI.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime

from dotenv import load_dotenv

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(_SCRIPT_DIR, "..", ".env"))

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import open_garden_planner.ui.dialogs.map_picker_dialog as mdlg  # noqa: E402
from open_garden_planner.services.google_maps_service import BoundingBox  # noqa: E402

_BBOX = BoundingBox(52.521, 13.404, 52.519, 13.406)
_TIMESTAMP = time.monotonic()


def log(msg: str) -> None:
    t = datetime.now(UTC)
    print(f"[HARNESS] {t.isoformat(timespec='milliseconds')} "
          f"(+{time.monotonic() - _TIMESTAMP:.3f}s) {msg}", flush=True)


def main() -> None:
    app = QApplication(sys.argv)
    dialog = mdlg.MapPickerDialog()
    dialog.show()

    def on_ready(token: str, frame_index: int, zoom: float, dpr: float,
                 css_w: float, css_h: float) -> None:
        log(f"captureReady token={token!r} frame={frame_index} zoom={zoom} "
            f"dpr={dpr} css=({css_w:.0f},{css_h:.0f})")

    def on_failed(token: str, message: str) -> None:
        log(f"captureError token={token!r} msg={message!r}")

    def on_result(result: str) -> None:
        if not result or result.startswith("google_js_view_capture"):
            grid = dialog.fetch_result.tile_grid if dialog.fetch_result else None
            log(f"capture finished: source={result!r} tile_grid={grid} "
                f"image={dialog.fetch_result.image.size if dialog.fetch_result else None}")
        else:
            log(f"capture finished with failure token: {result!r}")

    dialog._bridge.captureViewReady.connect(on_ready)
    dialog._bridge.captureViewFailed.connect(on_failed)
    dialog.finished.connect(lambda _code: on_result(
        dialog.fetch_result.source if dialog.fetch_result else "rejected/error"
    ))

    def draw_and_capture() -> None:
        log(f"emitting bounds {_BBOX}")
        dialog._bridge.boundsUpdated.emit(
            _BBOX.nw_lat, _BBOX.nw_lng, _BBOX.se_lat, _BBOX.se_lng
        )
        QTimer.singleShot(500, lambda: log(f"start capture ok={dialog._start_capture()}"))

    QTimer.singleShot(8_000, draw_and_capture)
    QTimer.singleShot(90_000, app.quit)
    app.exec()
    log("harness done")


if __name__ == "__main__":
    main()
