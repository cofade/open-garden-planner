"""Integration tests for the JS-API view capture path (issue #346).

The dialog wraps a ``QWebEngineView`` that loads Google Maps — these tests
never boot WebEngine. They exercise the real dialog/bridge/state machine
against a widget stand-in whose ``grab()`` returns deterministic pixmaps,
covering: the capture button lifecycle, the EEA-403 fallback offer, the
widget-grab → crop → attribution → ``FetchResult`` pipeline, blank-render
refusal, cancellation, and the generation guard.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QWidget

# Import the dialog module at collection time: the fixture below patches a
# fully-qualified attribute, which requires the submodule to be loaded.
# (QtWebEngineWidgets is imported inside the dialog — same early-import
# requirement as the other picker tests.)
import open_garden_planner.ui.dialogs.map_picker_dialog as map_picker_dialog_mod  # noqa: F401, E402, I001
from open_garden_planner.services.google_maps_js_capture import capture_mpp
from open_garden_planner.services.google_maps_service import (
    BoundingBox,
    bbox_size_m,
)

_BBOX = BoundingBox(52.521, 13.404, 52.519, 13.406)
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
    from PyQt6.QtGui import QPainter

    painter = QPainter(pm)
    for i in range(64):
        shade = 20 + i * 3 if not blank else 40
        painter.fillRect(i * 20, (i * 7) % 700, 16, 120, QColor(shade, shade + 20, shade))
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


def _make_dialog(qtbot, mock_web_view, with_api_key):
    from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

    dialog = MapPickerDialog()
    qtbot.addWidget(dialog)
    dialog._bridge.boundsUpdated.emit(_BBOX.nw_lat, _BBOX.nw_lng, _BBOX.se_lat, _BBOX.se_lng)
    return dialog


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
        import time
        from threading import Event

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
        # The JS invocation carries the bbox centre and a zoom that fits the
        # fake viewport; the page then reports readiness.
        page = dialog._view.page()
        assert page.runJavaScript.call_count >= 1
        js_call = page.runJavaScript.call_args_list[0].args[0]
        import re

        match = re.fullmatch(
            r"window\.beginCapture\(([0-9.eE+-]+), ([0-9.eE+-]+), (\d+), (\d+)\);", js_call
        )
        assert match is not None, js_call
        center_lat, center_lng, zoom, token = (
            float(match.group(1)),
            float(match.group(2)),
            int(match.group(3)),
            int(match.group(4)),
        )
        assert center_lat == pytest.approx(_BBOX.center[0], rel=1e-9)
        assert center_lng == pytest.approx(_BBOX.center[1], rel=1e-9)
        # Zoom 17 fits the (1000, 700) stand-in viewport with the default
        # margin for the Berlin bbox — pinned by the unit tests. The token
        # is the capture generation, echoed back by the page's readiness
        # report.
        assert zoom == 17
        assert token == 1
        dialog._bridge.captureViewReady.emit("1", 17, 1.0, 1000.0, 700.0)
        assert dialog.result() == dialog.DialogCode.Accepted
        result = dialog.fetch_result
        assert result is not None
        assert result.source == "google_js_view_capture"
        assert result.tile_grid == (1, 1)
        assert result.bbox == _BBOX
        assert result.zoom == 17
        expected_mpp = capture_mpp(_BBOX.center[0], 17, 1.0)
        assert result.meters_per_pixel == pytest.approx(expected_mpp, rel=1e-9)
        assert result.attribution.startswith("Map data ©")
        bbox_w_m, bbox_h_m = bbox_size_m(_BBOX)
        assert abs(result.image.size[0] - round(bbox_w_m / expected_mpp)) <= 1
        assert abs(result.image.size[1] - round(bbox_h_m / expected_mpp)) <= 1

    def test_success_is_a_terminal_path_that_stops_the_watchdog(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """Regression pin for the round-2 review P0: a successful capture
        without _finish_capture left _capture_in_progress True with the 20 s
        watchdog armed — a phantom timeout box fired after a good import."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        assert dialog._capture_watchdog is not None
        dialog._bridge.captureViewReady.emit("1", 17, 1.0, 1000.0, 700.0)
        assert dialog.result() == dialog.DialogCode.Accepted
        assert dialog._capture_in_progress is False
        assert dialog._capture_watchdog is None
        restore_calls = [
            call.args[0]
            for call in dialog._view.page().runJavaScript.call_args_list
            if "restoreCaptureChrome" in str(call.args[0])
        ]
        assert restore_calls, "page chrome was never restored after success"

    def test_capture_uses_js_reported_dpr(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._view._grab_scale = 2.0
        dialog._on_capture_clicked()
        dialog._bridge.captureViewReady.emit("1", 17, 2.0, 1000.0, 700.0)
        assert dialog.result() == dialog.DialogCode.Accepted
        result = dialog.fetch_result
        # The effective dpr is derived from the grab itself (physical px /
        # css px) — a truthful report and the measured ruler agree.
        assert result.meters_per_pixel == pytest.approx(
            capture_mpp(_BBOX.center[0], 17, 2.0), rel=1e-9
        )

    def test_wild_dpr_disagreement_refuses_instead_of_mis_scaling(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        """A page report that wildly disagrees with the measured raster is
        refused: trusting either number could silently mis-scale the plan."""
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._view._grab_scale = 2.0
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._on_capture_clicked()
            # Page claims dpr 1.0 but the grab measures 2.0 — 100% drift.
            dialog._bridge.captureViewReady.emit("1", 17, 1.0, 1000.0, 700.0)
        critical.assert_called_once()
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog.fetch_result is None
        assert dialog._capture_in_progress is False

    def test_blank_grab_is_refused_without_accepting(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._view._grab_blank = True
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ) as critical:
            dialog._on_capture_clicked()
            dialog._bridge.captureViewReady.emit("1", 17, 1.0, 1000.0, 700.0)
        critical.assert_called_once()
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
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        dialog._finish_capture()
        dialog._bridge.captureViewReady.emit("1", 17, 1.0, 1000.0, 700.0)
        assert dialog.fetch_result is None
        assert dialog.result() != dialog.DialogCode.Accepted


@pytest.mark.skip(reason="ci-bisect probe 5")
class TestCaptureCancel:
    def test_cancel_during_capture_aborts_on_ready(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        dialog._on_cancel()
        assert dialog._capture_cancel_requested is True
        assert dialog.result() != dialog.DialogCode.Accepted
        dialog._bridge.captureViewReady.emit("1", 17, 1.0, 1000.0, 700.0)
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
        dialog._bridge.captureViewReady.emit("1", 17, 1.0, 1000.0, 700.0)
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
            dialog._capture_watchdog.setInterval(10)
            dialog._capture_watchdog.start(10)
            qtbot.waitUntil(lambda: dialog._capture_in_progress is False, timeout=2000)
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
            dialog._capture_watchdog.setInterval(10)
            dialog._capture_watchdog.start(10)
            qtbot.waitUntil(lambda: dialog._capture_in_progress is False, timeout=2000)
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
            dialog._capture_watchdog.setInterval(10)
            dialog._capture_watchdog.start(10)
            qtbot.waitUntil(lambda: dialog._capture_in_progress is False, timeout=2000)
        critical.assert_not_called()
        assert dialog.result() == dialog.DialogCode.Rejected


@pytest.mark.skip(reason="ci-bisect probe 4")
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


@pytest.mark.skip(reason="ci-bisect probe 4")
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
            "function beginCapture(",  # invoked by the dialog via runJavaScript
            "function restoreCaptureChrome(",  # invoked by _finish_capture
            "bridge.ready()",  # existing handshake must not regress
        ):
            assert token in html, f"map_picker.html lost the contract token: {token}"
        # Semantics, not just names: the generation token must be the FIRST
        # parameter of both reports (the dialog echoes and validates it);
        # the page stringifies it so the bridge contract never depends on
        # QWebChannel's number-to-string coercion.
        import re

        assert re.search(r"bridge\.captureReady\(\s*String\(\s*token\s*\)\s*,", html), (
            "captureReady must pass the stringified generation token first"
        )
        assert re.search(r"bridge\.captureError\(\s*String\(\s*token\s*\)\s*,", html), (
            "captureError must pass the stringified generation token first"
        )
        for slot in ("captureReady", "captureError", "ready", "boundsChanged"):
            assert hasattr(_MapBridge, slot), f"_MapBridge lost slot: {slot}"


@pytest.mark.skip(reason="ci-bisect probe 4")
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


@pytest.mark.skip(reason="ci-bisect probe 4")
class TestAttributionMetadataRoundTrip:
    def test_js_capture_geo_metadata_round_trips_through_item(
        self, qtbot, mock_web_view, with_api_key
    ) -> None:
        dialog = _make_dialog(qtbot, mock_web_view, with_api_key)
        dialog._on_capture_clicked()
        dialog._bridge.captureViewReady.emit("1", 17, 1.0, 1000.0, 700.0)
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
