"""Integration tests for the JS-API view capture path (issues #346, #347).

The dialog wraps a ``QWebEngineView`` that loads Google Maps — these tests
never boot WebEngine. They exercise the real dialog/bridge/state machine
against a widget stand-in whose ``grab()`` returns deterministic pixmaps,
covering: the capture button lifecycle, the EEA-403 fallback offer, the
single-frame (1x1) pipeline, the pan-grid (multi-frame) choreography with
its per-frame quality gate and retry budget, the analytic stitch result,
cancellation, and the generation guard.
"""

from __future__ import annotations

import json
import re
import time
from threading import Event
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QWidget

# Import the dialog module at collection time: the fixture below patches a
# fully-qualified attribute, which requires the submodule to be loaded.
# (QtWebEngineWidgets is imported inside the dialog — same early-import
# requirement as the other picker tests.)
import open_garden_planner.ui.dialogs.map_picker_dialog as map_picker_dialog_mod  # noqa: F401, E402, I001
from open_garden_planner.services.google_maps_js_capture import (
    build_frame_layout,
    pick_capture_zoom_and_grid,
)
from open_garden_planner.services.google_maps_service import (
    BoundingBox,
    bbox_size_m,
    meters_per_pixel,
)

_BBOX = BoundingBox(52.521, 13.404, 52.519, 13.406)
# ~34 m x 44 m box: fits a single viewport even at zoom 20 -> the strict
# 1x1 (single-frame) degenerate case of the pan grid.
_TINY_BBOX = BoundingBox(52.5202, 13.40475, 52.5198, 13.40525)
# ~500 m x 220 m box: fills exactly a 2x2 pan grid at zoom 18 in the
# (1000, 700) stand-in viewport (zoom 19 would need 4x3 -> out of cap).
_BIG_BBOX = BoundingBox(52.520988, 13.40131, 52.519012, 13.40869)
_EEA_WORKER_MESSAGE = (
    "Static Maps returned HTTP 403: Your request cannot be served because "
    "satellite and hybrid map types are not available for your account and "
    "region. Learn more here: https://developers.google.com/maps/comms/eea/"
    "maps-static."
)


def _make_grab(blank: bool = False, size=(1000, 700)) -> QPixmap:
    """A deterministic, non-blank 'satellite' stand-in for view.grab()."""
    pm = QPixmap(*size)
    pm.fill(QColor(40, 60, 40))
    if blank:
        return pm
    painter = QPainter(pm)
    # Full-height banding spanning the whole image: every cell of the
    # frame-quality grid sees texture (a sparse pattern trips the per-cell
    # gate and turns the happy path into an endless retry). Shade stays in
    # 8-bit range — QColor values above 255 silently break the fillRect
    # and leave trailing cells uniform (observed at dpr 2 grabs).
    for i in range(size[0] // 20):
        shade = 20 + (i % 60) * 3
        painter.fillRect(i * 20, 0, 16, size[1], QColor(shade, shade + 20, shade))
    painter.end()
    return pm


class _DummyWebView(QWidget):
    """Real QWidget stand-in for the QWebEngineView the dialog wraps."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.resize(1000, 700)
        self._page = MagicMock()
        self._settings = MagicMock()
        self._grab_blank = False
        self._grab_scale = 1.0

    def page(self):  # noqa: D401
        return self._page

    def settings(self):  # noqa: D401
        return self._settings

    def setUrl(self, *_args, **_kwargs) -> None:
        pass

    def grab(self) -> QPixmap:
        w = max(1, round(1000 * self._grab_scale))
        h = max(1, round(700 * self._grab_scale))
        return _make_grab(blank=self._grab_blank, size=(w, h))


@pytest.fixture()
def mock_web_view():
    """Replace QWebEngineView with the lightweight stand-in."""
    with patch(
        "open_garden_planner.ui.dialogs.map_picker_dialog.QWebEngineView",
        _DummyWebView,
    ):
        yield


@pytest.fixture()
def with_api_key(monkeypatch):
    monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")


def _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_BBOX):
    from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

    dialog = MapPickerDialog()
    qtbot.addWidget(dialog)
    dialog._bridge.boundsUpdated.emit(bbox.nw_lat, bbox.nw_lng, bbox.se_lat, bbox.se_lng)
    return dialog


# --- capture choreography drivers (the JS page is suspended: the tests
# --- drive the bridge signals the page would emit) ----------------------

def _profile(dialog, generation=1, zoom=17, dpr=1.0, css_w=1000.0, css_h=700.0):
    """Emit the capture profile report (frameIndex -1)."""
    dialog._bridge.captureViewReady.emit(str(generation), -1, zoom, dpr, css_w, css_h)


def _frame(dialog, index, generation=1, zoom=17, dpr=1.0, css_w=1000.0, css_h=700.0):
    """Emit one frame's readiness report."""
    dialog._bridge.captureViewReady.emit(str(generation), index, zoom, dpr, css_w, css_h)


def _js_calls(dialog):
    return [
        call.args[0]
        for call in dialog._view.page().runJavaScript.call_args_list
        if isinstance(call.args[0], str)
    ]


def _begin_frames_call(dialog):
    """The beginCaptureFrames invocation (centers JSON, zoom, token)."""
    calls = [c for c in _js_calls(dialog) if c.startswith("window.beginCaptureFrames(")]
    assert calls, f"beginCaptureFrames was never invoked: {_js_calls(dialog)!r}"
    match = re.fullmatch(r"window\.beginCaptureFrames\((\[.*\]), (\d+), (\d+)\);", calls[-1])
    assert match is not None, calls[-1]
    return json.loads(match.group(1)), int(match.group(2)), int(match.group(3))


def _drive_capture(dialog, bbox=_BBOX, dpr=1.0):
    """Drive the full choreography: chrome -> profile -> every frame.

    Returns the (zoom, cols, rows) the dialog chose — the same grid the
    standalone picker produces for the stand-in viewport (drift guard).
    """
    zoom, cols, rows = pick_capture_zoom_and_grid(bbox, (1000.0, 700.0))
    _profile(dialog, zoom=zoom, dpr=dpr)
    for i in range(cols * rows):
        _frame(dialog, i, zoom=zoom, dpr=dpr)
    return zoom, cols, rows


class TestCaptureButtonLifecycle:
    def test_disabled_until_rectangle(self, qtbot, mock_web_view, with_api_key) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        assert dialog._capture_button.isEnabled() is False
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        assert dialog._capture_button.isEnabled() is True
        dialog._bridge.cleared.emit()
        assert dialog._capture_button.isEnabled() is False

    def test_disabled_while_static_fetch_runs(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        from open_garden_planner.services.google_maps_js_capture import (
            classify_static_failure,  # noqa: F401
        )

        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        started = Event()

        def _blocking_fetch(*_args, cancel_check=None, **_kwargs):
            started.set()
            while cancel_check is not None and not cancel_check():
                time.sleep(0.001)
            from open_garden_planner.services.google_maps_service import FetchCancelled

            raise FetchCancelled("cancelled")

        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox",
            side_effect=_blocking_fetch,
        ):
            dialog._on_accept()
            qtbot.waitUntil(started.is_set, timeout=1000)
            assert dialog._capture_button.isEnabled() is False
            dialog._on_cancel()
            qtbot.waitUntil(lambda: dialog._worker is None, timeout=2000)
        assert dialog._capture_button.isEnabled() is True


class TestCaptureSuccess:
    def test_capture_produces_js_capture_fetch_result(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        assert dialog._capture_in_progress is True
        assert _js_calls(dialog)[0] == "window.beginCaptureChrome(1);"
        # The pan grid for the Berlin box is a single column of 3 frames at
        # zoom 19 (the picker prefers a higher zoom over a single coarse
        # frame — that IS the resolution raise of issue #347).
        zoom, cols, rows = _drive_capture(dialog)
        assert (zoom, cols, rows) == (19, 1, 3)
        centers, js_zoom, token = _begin_frames_call(dialog)
        assert js_zoom == zoom
        assert token == 1
        assert len(centers) == cols * rows
        # Single column: the longitude is the bbox centre's; the latitudes
        # walk the north→south span symmetrically (the middle frame sits
        # exactly on the bbox centre; the outer ones are near-symmetric,
        # within the latitude↔world-y nonlinearity).
        for _lat, lng in centers:
            assert lng == pytest.approx(_BBOX.center[1], rel=1e-9)
        assert centers[0][0] > centers[1][0] > centers[2][0]
        assert centers[1][0] == pytest.approx(_BBOX.center[0], rel=1e-9)
        assert abs((centers[0][0] - centers[2][0]) / 2 - (centers[1][0] - centers[2][0])) < 1e-7  # noqa: E501
        assert dialog.result() == dialog.DialogCode.Accepted
        result = dialog.fetch_result
        assert result is not None
        assert result.source == "google_js_view_capture"
        assert result.tile_grid == (cols, rows)
        assert result.bbox == _BBOX
        assert result.zoom == zoom
        expected_mpp = meters_per_pixel(_BBOX.center[0], zoom) / 1.0
        assert result.meters_per_pixel == pytest.approx(expected_mpp, rel=1e-9)
        assert result.attribution.startswith("Map data ©")
        bbox_w_m, bbox_h_m = bbox_size_m(_BBOX)
        assert abs(result.image.size[0] - round(bbox_w_m / expected_mpp)) <= 1
        assert abs(result.image.size[1] - round(bbox_h_m / expected_mpp)) <= 1

    def test_tiny_box_is_a_strict_single_frame(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """A box that fits one viewport at the max zoom stays a 1x1 grid —
        the degenerate case must produce today's exact single-frame result."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._on_capture_clicked()
        zoom, cols, rows = _drive_capture(dialog, bbox=_TINY_BBOX)
        assert (cols, rows) == (1, 1)
        assert zoom == 20
        centers, js_zoom, _ = _begin_frames_call(dialog)
        assert len(centers) == 1
        assert centers[0][0] == pytest.approx(_TINY_BBOX.center[0], rel=1e-9)
        assert centers[0][1] == pytest.approx(_TINY_BBOX.center[1], rel=1e-9)
        assert js_zoom == zoom
        assert dialog.result() == dialog.DialogCode.Accepted
        result = dialog.fetch_result
        assert result is not None
        assert result.tile_grid == (1, 1)
        assert result.zoom == 20

    def test_success_is_a_terminal_path_that_stops_the_watchdog(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """Regression pin for the round-2 review P0: a successful capture
        without _finish_capture left _capture_in_progress True with the 20 s
        watchdog armed — a phantom timeout box fired after a good import."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._on_capture_clicked()
        assert dialog._capture_watchdog is not None
        _drive_capture(dialog, bbox=_TINY_BBOX)
        assert dialog.result() == dialog.DialogCode.Accepted
        assert dialog._capture_in_progress is False
        assert dialog._capture_watchdog is None
        restore_calls = [c for c in _js_calls(dialog) if "restoreCaptureChrome" in c]
        assert restore_calls, "page chrome was never restored after success"

    def test_capture_uses_js_reported_dpr(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._view._grab_scale = 2.0
        dialog._on_capture_clicked()
        zoom, _, _ = _drive_capture(dialog, bbox=_TINY_BBOX, dpr=2.0)
        assert dialog.result() == dialog.DialogCode.Accepted
        result = dialog.fetch_result
        # The layout is derived from the reported dpr; the grab's measured
        # ruler agrees, so the result mpp is the reported-dpr mpp.
        assert result.meters_per_pixel == pytest.approx(
            meters_per_pixel(_TINY_BBOX.center[0], zoom) / 2.0, rel=1e-9
        )

    def test_wild_dpr_disagreement_refuses_instead_of_mis_scaling(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """A page report that wildly disagrees with the measured raster is
        refused: trusting either number could silently mis-scale the plan."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._view._grab_scale = 2.0
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._on_capture_clicked()
            _profile(dialog, zoom=20, dpr=2.0)
            # Page claims dpr 1.0 but the grab measures 2.0 — 100% drift.
            _frame(dialog, 0, zoom=20, dpr=1.0)
        critical.assert_called_once()
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog.fetch_result is None
        assert dialog._capture_in_progress is False

    def test_near_miss_dpr_disagreement_refused(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """The pan grid is built from the REPORTED dpr, so even a small
        report/ruler disagreement (within the old wild-gate tolerance)
        must refuse: the paste offsets and result mpp would be slightly
        off. The ruler gate is the honest cross-check."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._view._grab_scale = 1.008  # measures 1.008, page claims 1.0
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._on_capture_clicked()
            _profile(dialog, zoom=20, dpr=1.0)
            _frame(dialog, 0, zoom=20, dpr=1.0)
        critical.assert_called_once()
        assert critical.call_args.args[2] == dialog.tr(
            map_picker_dialog_mod._CAPTURE_DPR_MESSAGE
        )
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog.fetch_result is None
        assert dialog._capture_in_progress is False

    def test_blank_grab_retries_then_succeeds(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """A blank first render must be retried via the page, not accepted —
        the retry's fresh settle can succeed."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=20)
        dialog._view._grab_blank = True
        _frame(dialog, 0, zoom=20)
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog._capture_in_progress is True
        assert any("retryCaptureFrame" in c for c in _js_calls(dialog)), (
            _js_calls(dialog)
        )
        assert dialog._capture_retries_left == 1
        dialog._view._grab_blank = False
        _frame(dialog, 0, zoom=20)
        assert dialog.result() == dialog.DialogCode.Accepted
        assert dialog.fetch_result is not None

    def test_blank_grab_exhausts_retries_and_fails_cleanly(
        self, qtbot, mock_web_view, with_api_key, monkeypatch
    ) -> None:
        """When the retry budget is spent the capture must fail cleanly —
        never accept a blank region."""
        monkeypatch.setattr(map_picker_dialog_mod, "FRAME_RETRIES", 1)
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=20)
        dialog._view._grab_blank = True
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            _frame(dialog, 0, zoom=20)  # blank -> one retry
            _frame(dialog, 0, zoom=20)  # blank again -> budget spent
        critical.assert_called_once()
        assert critical.call_args.args[2] == dialog.tr(
            map_picker_dialog_mod._CAPTURE_FRAME_FAILED_MESSAGE
        )
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog.fetch_result is None
        assert dialog._capture_in_progress is False
        assert dialog._ok_button.isEnabled() is True
        assert dialog._capture_button.isEnabled() is True

    def test_second_capture_ignored_while_first_in_progress(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        assert dialog._start_capture() is True
        calls_after_first = dialog._view.page().runJavaScript.call_count
        assert dialog._start_capture() is False
        assert dialog._view.page().runJavaScript.call_count == calls_after_first
        dialog._finish_capture()

    def test_stale_ready_after_finish_is_ignored(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._on_capture_clicked()
        dialog._finish_capture()
        _profile(dialog, zoom=20)
        _frame(dialog, 0, zoom=20)
        assert dialog.fetch_result is None
        assert dialog.result() != dialog.DialogCode.Accepted


class TestPanGridCapture:
    """Multi-frame capture (issue #347): profile -> N frames -> one stitch."""

    EXP_ZOOM, EXP_COLS, EXP_ROWS = 18, 2, 2

    def test_pan_grid_happy_path_stitches_four_frames(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_BIG_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=self.EXP_ZOOM)
        centers, zoom, token = _begin_frames_call(dialog)
        assert zoom == self.EXP_ZOOM
        assert token == 1
        assert len(centers) == 4
        # The centers must match the analytic pan grid exactly (drift guard
        # for the world-pixel math the stitch depends on).
        layout = build_frame_layout(
            _BIG_BBOX, self.EXP_ZOOM, 2, 2, (1000.0, 700.0), 1.0
        )
        for idx, (lat, lng) in enumerate(centers):
            exp_lat, exp_lng = layout.centers[idx]
            assert lat == pytest.approx(exp_lat, rel=1e-9)
            assert lng == pytest.approx(exp_lng, rel=1e-9)
        # Row-major NW order: frame 0 is the most north-west corner.
        assert centers[0][1] < centers[1][1]
        assert centers[0][0] > centers[2][0]
        for i in range(4):
            _frame(dialog, i, zoom=self.EXP_ZOOM)
            assert dialog._capture_frame_index == min(i + 1, 3)
        assert dialog.result() == dialog.DialogCode.Accepted
        result = dialog.fetch_result
        assert result is not None
        assert result.tile_grid == (2, 2)
        assert result.zoom == self.EXP_ZOOM
        assert len(dialog._capture_frames) == 4

    def test_pan_grid_reports_scale_and_size(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_BIG_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=self.EXP_ZOOM)
        for i in range(4):
            _frame(dialog, i, zoom=self.EXP_ZOOM)
        result = dialog.fetch_result
        assert result is not None
        assert result.source == "google_js_view_capture"
        assert result.bbox == _BIG_BBOX
        mpp = meters_per_pixel(_BIG_BBOX.center[0], self.EXP_ZOOM) / 1.0
        assert result.meters_per_pixel == pytest.approx(mpp, rel=1e-9)
        bbox_w_m, bbox_h_m = bbox_size_m(_BIG_BBOX)
        assert abs(result.image.size[0] - round(bbox_w_m / mpp)) <= 1
        assert abs(result.image.size[1] - round(bbox_h_m / mpp)) <= 1
        assert result.attribution.startswith("Map data ©")

    def test_one_advance_per_captured_frame(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """Between two frame reports the page is asked exactly once to move
        on — a dupe report cannot double-advance (frame drift)."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_BIG_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=self.EXP_ZOOM)
        _frame(dialog, 0, zoom=self.EXP_ZOOM)
        advances = [c for c in _js_calls(dialog) if "advanceCaptureFrame" in c]
        assert len(advances) == 1
        _frame(dialog, 0, zoom=self.EXP_ZOOM)  # duplicate/frame 0 — must be inert
        advances = [c for c in _js_calls(dialog) if "advanceCaptureFrame" in c]
        assert len(advances) == 1
        assert dialog._capture_frame_index == 1
        assert dialog._capture_in_progress is True
        dialog._finish_capture()

    def test_viewport_change_mid_capture_is_refused(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """A window resize between frames would silently mis-stitch — the
        dialog must refuse instead of shipping a wrong image."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_BIG_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=self.EXP_ZOOM)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            _frame(dialog, 0, zoom=self.EXP_ZOOM, css_w=900.0, css_h=650.0)
        critical.assert_called_once()
        assert critical.call_args.args[2] == dialog.tr(
            map_picker_dialog_mod._CAPTURE_VIEW_CHANGED_MESSAGE
        )
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog.fetch_result is None
        assert dialog._capture_in_progress is False

    def test_mid_grid_frame_retries_then_succeeds(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """A bad frame in the middle of a grid is retried in place; the
        already-captured frames must not be re-grabbed."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_BIG_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=self.EXP_ZOOM)
        _frame(dialog, 0, zoom=self.EXP_ZOOM)
        _frame(dialog, 1, zoom=self.EXP_ZOOM)
        # Frame 2 renders blank the first time -> retry, then loads.
        dialog._view._grab_blank = True
        _frame(dialog, 2, zoom=self.EXP_ZOOM)
        assert any("retryCaptureFrame" in c for c in _js_calls(dialog))
        assert dialog._capture_frame_index == 2  # still waiting on frame 2
        dialog._view._grab_blank = False
        _frame(dialog, 2, zoom=self.EXP_ZOOM)
        _frame(dialog, 3, zoom=self.EXP_ZOOM)
        assert dialog.result() == dialog.DialogCode.Accepted
        result = dialog.fetch_result
        assert result is not None
        assert result.tile_grid == (2, 2)

    def test_mid_grid_retry_exhaustion_fails_cleanly(
        self, qtbot, mock_web_view, with_api_key, monkeypatch
    ) -> None:
        """Only the degenerate 1x1 retry-exhaustion was covered; a mid-grid
        failure must behave identically: retry in place, then fail the
        whole capture with the frame-failed message — never accept a
        partial mosaic with a blank region."""
        monkeypatch.setattr(map_picker_dialog_mod, "FRAME_RETRIES", 1)
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_BIG_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=self.EXP_ZOOM)
        _frame(dialog, 0, zoom=self.EXP_ZOOM)
        _frame(dialog, 1, zoom=self.EXP_ZOOM)
        dialog._view._grab_blank = True
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            _frame(dialog, 2, zoom=self.EXP_ZOOM)  # blank -> one retry
            _frame(dialog, 2, zoom=self.EXP_ZOOM)  # blank again -> budget spent
        critical.assert_called_once()
        assert critical.call_args.args[2] == dialog.tr(
            map_picker_dialog_mod._CAPTURE_FRAME_FAILED_MESSAGE
        )
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog.fetch_result is None
        assert dialog._capture_in_progress is False

    def test_stitch_failure_is_handled_cleanly(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """The dialog must map a stitcher geometry failure (CaptureLayoutError)
        to the frame-failed message — a clean error, never a crash or an
        accepted result."""
        from open_garden_planner.services.google_maps_js_capture import (
            CaptureLayoutError,
        )

        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=20)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.stitch_frames",
            side_effect=CaptureLayoutError("cannot cover"),
        ), patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            _frame(dialog, 0, zoom=20)
        critical.assert_called_once()
        assert critical.call_args.args[2] == dialog.tr(
            map_picker_dialog_mod._CAPTURE_FRAME_FAILED_MESSAGE
        )
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog.fetch_result is None
        assert dialog._capture_in_progress is False


class TestCaptureCancel:
    def test_cancel_during_capture_aborts_on_ready(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        dialog._on_cancel()
        assert dialog._capture_cancel_requested is True
        assert dialog.result() != dialog.DialogCode.Accepted
        _profile(dialog)
        _frame(dialog, 0)
        assert dialog._capture_in_progress is False
        assert dialog.fetch_result is None
        assert dialog._cancel_button.isEnabled() is True

    def test_close_during_capture_completes_after_ready(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """A window close during capture must not drop the intent — the
        dialog rejects itself once the page's readiness report arrives."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog.show()
        dialog._on_capture_clicked()
        dialog.close()
        assert dialog.isVisible() is True
        assert dialog._close_after_capture is True
        _profile(dialog)
        _frame(dialog, 0)
        assert dialog.result() == dialog.DialogCode.Rejected
        assert dialog._capture_in_progress is False

    def test_watchdog_times_out_stuck_capture(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._on_capture_clicked()
            # Drive the handler deterministically: emitting the timeout
            # signal runs exactly the same slot synchronously, without a
            # real 10 ms timer racing pytest-qt's wait loop (which
            # segfaulted the linux-offscreen suite — §11.4).
            dialog._capture_watchdog.timeout.emit()
        assert dialog.fetch_result is None
        assert dialog._cancel_button.isEnabled() is True
        critical.assert_called_once()

    def test_watchdog_after_cancel_stays_silent(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """Cancel then a dead page: the watchdog must neither pop an error
        box nor leave the dialog stuck."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._on_capture_clicked()
            dialog._on_cancel()
            assert dialog._cancel_button.isEnabled() is False
            # Drive the handler deterministically: emitting the timeout
            # signal runs exactly the same slot synchronously, without a
            # real 10 ms timer racing pytest-qt's wait loop (which
            # segfaulted the linux-offscreen suite — §11.4).
            dialog._capture_watchdog.timeout.emit()
        critical.assert_not_called()
        assert dialog._cancel_button.isEnabled() is True
        assert dialog.fetch_result is None
        assert dialog.result() != dialog.DialogCode.Accepted

    def test_close_then_watchdog_rejects_without_error_box(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog.show()
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._on_capture_clicked()
            dialog.close()
            # Drive the handler deterministically: emitting the timeout
            # signal runs exactly the same slot synchronously, without a
            # real 10 ms timer racing pytest-qt's wait loop (which
            # segfaulted the linux-offscreen suite — §11.4).
            dialog._capture_watchdog.timeout.emit()
        critical.assert_not_called()
        assert dialog.result() == dialog.DialogCode.Rejected


class TestCaptureWatchdogLifecycle:
    @staticmethod
    def _active_watchdogs(dialog):
        """Live armed timers — the leak measure. A stopped timer whose
        underlying Qt slot was recycled by the next arm can LOOK active
        (isActive on a reused slot), so count objects, not slots."""
        from PyQt6.QtCore import QTimer

        return [t for t in dialog.findChildren(QTimer) if t.isActive()]

    def test_rearm_stops_the_previous_timer(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """Each choreography step arms a fresh watchdog AND stops the
        previous one — an orphaned idle timer would otherwise fire mid-
        capture and abort a progressing grid with a phantom timeout box
        (the #346 phantom-watchdog lesson in a new shape). At any moment
        exactly ONE watchdog may be armed; after finish, none."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        first = dialog._capture_watchdog
        assert len(self._active_watchdogs(dialog)) == 1
        # Berlin -> a 1x3 grid; each frame emission re-arms the watchdog.
        # Assert DURING the capture (a full _drive_capture would finish it).
        _profile(dialog, zoom=19)
        second = dialog._capture_watchdog
        assert second is not first
        assert len(self._active_watchdogs(dialog)) == 1, (
            "previous watchdog leaked and is still armed"
        )
        _frame(dialog, 0, zoom=19)
        assert len(self._active_watchdogs(dialog)) == 1
        _frame(dialog, 1, zoom=19)
        assert len(self._active_watchdogs(dialog)) == 1
        _frame(dialog, 2, zoom=19)
        assert dialog.result() == dialog.DialogCode.Accepted
        assert dialog._capture_in_progress is False
        assert self._active_watchdogs(dialog) == []

    def test_rearm_after_retry_stops_previous_timer(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """Retry re-arms too (the watchdog restarts at every step); the
        timer armed before the retry must be stopped — still exactly one
        armed watchdog."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._on_capture_clicked()
        _profile(dialog, zoom=20)
        before_retry = dialog._capture_watchdog
        dialog._view._grab_blank = True
        _frame(dialog, 0, zoom=20)  # blank -> retry (re-arms the watchdog)
        after_retry = dialog._capture_watchdog
        assert after_retry is not before_retry
        assert len(self._active_watchdogs(dialog)) == 1, (
            "previous watchdog leaked and is still armed"
        )
        dialog._view._grab_blank = False
        _frame(dialog, 0, zoom=20)
        assert dialog.result() == dialog.DialogCode.Accepted
        assert self._active_watchdogs(dialog) == []


class TestCaptureErrorMapping:
    def test_timeout_token_shows_translated_message(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._bridge.captureViewFailed.emit("1", "capture-timeout")
        critical.assert_called_once()
        args = critical.call_args.args
        # args[2] is the message text — never the raw page token.
        assert args[2] == dialog.tr(map_picker_dialog_mod._CAPTURE_TIMEOUT_MESSAGE)
        assert dialog._capture_in_progress is False
        assert dialog._cancel_button.isEnabled() is True

    def test_stale_token_error_is_ignored(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._bridge.captureViewFailed.emit("0", "capture-timeout")
        critical.assert_not_called()
        assert dialog._capture_in_progress is True
        dialog._finish_capture()

    def test_stale_js_result_callback_is_ignored(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """A runJavaScript callback from a previous generation must neither
        succeed nor fail the current capture."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            callback = dialog._view.page().runJavaScript.call_args_list[0].args[1]
            # Stale generation: both results must be ignored.
            callback("ok", 0)
            callback("error: stale", 0)
        assert critical.call_count == 0
        assert dialog._capture_in_progress is True
        assert dialog.fetch_result is None
        dialog._finish_capture()

    def test_close_intent_honored_via_error_report(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """Close during capture + the page's failure report = silent close,
        no error box."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog.show()
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._on_capture_clicked()
            dialog.close()
            dialog._bridge.captureViewFailed.emit("1", "capture-timeout")
        critical.assert_not_called()
        assert dialog.result() == dialog.DialogCode.Rejected
        assert dialog._capture_in_progress is False

    def test_zoom_mismatch_token_is_mapped(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._bridge.captureViewFailed.emit("1", "zoom-mismatch")
        critical.assert_called_once()
        assert critical.call_args.args[2] == dialog.tr(
            map_picker_dialog_mod._CAPTURE_UNEXPECTED_MESSAGE
        )

    def test_runjavascript_failure_path_maps_error_token(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            # Simulate the runJavaScript callback delivering the page's
            # error return value (a JS exception message).
            callback = dialog._view.page().runJavaScript.call_args_list[0].args[1]
            callback("error: google.maps is not defined", 1)
        critical.assert_called_once()
        assert critical.call_args.args[2] == dialog.tr(
            map_picker_dialog_mod._CAPTURE_UNEXPECTED_MESSAGE
        )
        assert "google.maps is not defined" not in critical.call_args.args[2]


class TestBridgeContract:
    def test_html_contract_names_match_python_bridge(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """Drift guard: the JS-side surface names must match the bridge's
        slots and the page-side window functions the dialog invokes."""
        from pathlib import Path

        from open_garden_planner.ui.dialogs.map_picker_dialog import (
            MapPickerDialog,
            _MapBridge,
        )

        html = Path(MapPickerDialog.HTML_FILE).read_text(encoding="utf-8")
        for token in (
            "bridge.captureReady(",  # page reports readiness
            "bridge.captureError(",  # page reports failure
            "function beginCaptureChrome(",  # capture profile (viewport/dpr)
            "function beginCaptureFrames(",  # frame-sequence start
            "function advanceCaptureFrame(",  # Python ack: next frame
            "function retryCaptureFrame(",  # Python quality refusal: re-settle
            "function restoreCaptureChrome(",  # invoked by _finish_capture
            "bridge.ready()",  # existing handshake must not regress
        ):
            assert token in html, f"map_picker.html lost the contract token: {token}"
        # Semantics, not just names: the generation token must be the FIRST
        # parameter of both reports (the dialog echoes and validates it);
        # the page stringifies it so the bridge contract never depends on
        # QWebChannel's number-to-string coercion.
        assert re.search(
            r"bridge\.captureReady\(\s*String\(\s*(?:token|captureState\.token)\s*\)\s*,", html
        ), "captureReady must pass the stringified generation token first"
        assert re.search(
            r"bridge\.captureError\(\s*String\(\s*(?:token|captureState\.token)\s*\)\s*,", html
        ), "captureError must pass the stringified generation token first"
        # The pan-grid profile must be reported as frameIndex -1 — the
        # dialog dispatches on that sentinel.
        assert re.search(
            r"bridge\.captureReady\(\s*String\(\s*(?:token|captureState\.token)\s*\)\s*,\s*(-1)\s*,", html
        ), "captureReady frameIndex -1 (profile report) must be preserved"
        # Google's native attribution element is hidden for the capture only
        # and restored afterwards; the baked strip is the artifact's
        # attribution (ADR-019 addendum #347).
        assert ".gm-style-cc" in html, "attribution hide/restore target missing"
        for slot in ("captureReady", "captureError", "ready", "boundsChanged"):
            assert hasattr(_MapBridge, slot), f"_MapBridge lost slot: {slot}"


class TestEeaFallbackOffer:
    def test_eea_failure_offers_capture_and_starts_it(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._ask_capture_fallback = MagicMock(return_value=True)  # type: ignore[method-assign]
        dialog._on_fetch_failure(_EEA_WORKER_MESSAGE)
        assert dialog._capture_in_progress is True
        assert dialog._view.page().runJavaScript.call_count >= 1

    def test_eea_failure_offer_declined_leaves_dialog_open(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._ask_capture_fallback = MagicMock(return_value=False)  # type: ignore[method-assign]
        dialog._on_fetch_failure(_EEA_WORKER_MESSAGE)
        assert dialog._capture_in_progress is False
        assert dialog._ok_button.isEnabled() is True
        assert dialog._capture_button.isEnabled() is True

    def test_generic_403_does_not_offer_capture(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._ask_capture_fallback = MagicMock(return_value=True)  # type: ignore[method-assign]
            dialog._on_fetch_failure("Static Maps returned HTTP 403: REQUEST_DENIED")
        assert dialog._ask_capture_fallback.call_count == 0  # type: ignore[attr-defined]
        assert dialog._capture_in_progress is False
        critical.assert_called_once()


class TestAttributionMetadataRoundTrip:
    def test_js_capture_geo_metadata_round_trips_through_item(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key, bbox=_TINY_BBOX)
        dialog._on_capture_clicked()
        _drive_capture(dialog, bbox=_TINY_BBOX)
        result = dialog.fetch_result
        assert result is not None

        import io

        from open_garden_planner.ui.canvas.items import BackgroundImageItem

        buf = io.BytesIO()
        result.image.save(buf, format="PNG")
        item = BackgroundImageItem.from_fetch_result(
            image_path="google_satellite_z17.png",
            png_bytes=buf.getvalue(),
            meters_per_pixel=result.meters_per_pixel,
            bbox_nw=(result.bbox.nw_lat, result.bbox.nw_lng),
            bbox_se=(result.bbox.se_lat, result.bbox.se_lng),
            zoom=result.zoom,
            source=result.source,
            attribution=result.attribution,
            fetched_at="2026-09-01T00:00:00+00:00",
        )
        meta = item.geo_metadata
        assert meta is not None
        assert meta["source"] == "google_js_view_capture"
        assert meta["attribution"].startswith("Map data ©")
        data = item.to_dict()
        assert data["geo_metadata"]["attribution"] == meta["attribution"]
        reloaded = BackgroundImageItem.from_dict(data)
        assert reloaded.geo_metadata is not None
        assert reloaded.geo_metadata["source"] == "google_js_view_capture"
        assert reloaded.geo_metadata["attribution"] == meta["attribution"]
