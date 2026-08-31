"""Integration tests for :class:`MapPickerDialog`.

The dialog wraps a ``QWebEngineView`` that loads Google Maps — we don't
boot WebEngine here. Instead we exercise the bridge (the actual JS↔Python
contract) and the fetch worker indirection so the dialog logic is covered
without network IO. The WebEngine view is patched at construction time.
"""

from __future__ import annotations

import logging
import time
from threading import Event
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QDialogButtonBox, QWidget

from open_garden_planner.services.google_maps_service import (
    BoundingBox,
    FetchCancelled,
    FetchResult,
    GoogleMapsFetchError,
)


class _DummyWebView(QWidget):
    """Real QWidget with the bits of QWebEngineView the dialog touches."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = MagicMock()
        self._settings = MagicMock()

    def page(self):  # noqa: D401
        return self._page

    def settings(self):  # noqa: D401
        return self._settings

    def setUrl(self, *_args, **_kwargs) -> None:
        # No real browser to navigate; URL load is verified at the call site.
        pass


@pytest.fixture()
def mock_web_view():
    """Replace QWebEngineView with a lightweight QWidget stand-in."""
    with patch(
        "open_garden_planner.ui.dialogs.map_picker_dialog.QWebEngineView",
        _DummyWebView,
    ):
        yield


@pytest.fixture()
def with_api_key(monkeypatch):
    monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")


class TestAvailability:
    def test_is_available_true_when_key_set(self, with_api_key) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        assert MapPickerDialog.is_available() is True

    def test_is_available_false_when_key_missing(self, monkeypatch) -> None:
        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        assert MapPickerDialog.is_available() is False

    def test_is_available_with_explicit_key_without_environment(self, monkeypatch) -> None:
        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        assert MapPickerDialog.is_available("preference-key") is True


class TestDialogConstruction:
    def test_constructs_with_key(self, qtbot, with_api_key, mock_web_view) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        ok_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None
        assert ok_button.isEnabled() is False  # No rectangle drawn yet.

    def test_rejects_when_key_missing(self, qtbot, monkeypatch, mock_web_view) -> None:
        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        # Suppress the modal QMessageBox so the test doesn't block.
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.warning"
        ):
            dialog = MapPickerDialog()
            qtbot.addWidget(dialog)
        # The dialog called reject() in __init__; it's not visible/accepted.
        assert dialog.fetch_result is None

    def test_explicit_key_reaches_map_bridge(
        self, qtbot, monkeypatch, mock_web_view
    ) -> None:
        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        dialog = MapPickerDialog(api_key="preference-key")
        qtbot.addWidget(dialog)

        assert dialog._api_key == "preference-key"
        assert dialog._bridge._api_key == "preference-key"


class TestBridgeSignals:
    def test_bounds_updated_enables_ok(self, qtbot, with_api_key, mock_web_view) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)

        ok_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button.isEnabled() is False

        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        assert ok_button.isEnabled() is True
        assert dialog._bbox == BoundingBox(
            nw_lat=52.521, nw_lng=13.404, se_lat=52.519, se_lng=13.406
        )

    def test_cleared_disables_ok(self, qtbot, with_api_key, mock_web_view) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)

        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        ok_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button.isEnabled() is True

        dialog._bridge.cleared.emit()
        assert ok_button.isEnabled() is False
        assert dialog._bbox is None

    def test_ready_emits_setup_payload(self, qtbot, with_api_key, mock_web_view) -> None:
        """``ready()`` hands JS the API key + locale + translated strings."""
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        captured: list[tuple] = []
        dialog._bridge.setupReady.connect(
            lambda key, locale, strings: captured.append((key, locale, strings))
        )
        dialog._bridge.ready()
        assert len(captured) == 1
        key, locale, strings = captured[0]
        assert key == "TEST_KEY"
        assert isinstance(locale, str) and locale  # something like "de" or "en-US"
        # All the UI string keys the HTML expects must be present.
        assert "searchPlaceholder" in strings
        assert "drawButton" in strings
        assert "clearButton" in strings
        assert "hintInitial" in strings
        assert "hintDrawing" in strings


class TestFetchFlow:
    def test_worker_passes_explicit_key_to_service(self) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import _FetchWorker

        bbox = BoundingBox(52.521, 13.404, 52.519, 13.406)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox"
        ) as fetch:
            worker = _FetchWorker(bbox, "preference-key")
            worker.run()

        assert fetch.call_args.kwargs["api_key"] == "preference-key"

    def test_worker_logs_scrubbed_traceback_for_unexpected_failure(self, caplog) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import _FetchWorker

        bbox = BoundingBox(52.521, 13.404, 52.519, 13.406)
        messages: list[str] = []
        worker = _FetchWorker(bbox, "SECRET_GOOGLE_MAPS_KEY")
        worker.failed.connect(messages.append)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox",
            side_effect=RuntimeError("request URL leaked SECRET_GOOGLE_MAPS_KEY"),
        ), caplog.at_level(
            logging.ERROR,
            logger="open_garden_planner.ui.dialogs.map_picker_dialog",
        ):
            worker.run()

        assert messages
        assert "SECRET_GOOGLE_MAPS_KEY" not in messages[0]
        assert "Unexpected satellite image fetch failure" in caplog.text
        assert "SECRET_GOOGLE_MAPS_KEY" not in caplog.text

    def test_worker_scrubs_typed_fetch_error_secret(self) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import _FetchWorker

        bbox = BoundingBox(52.521, 13.404, 52.519, 13.406)
        messages: list[str] = []
        worker = _FetchWorker(bbox, "SECRET_GOOGLE_MAPS_KEY")
        worker.failed.connect(messages.append)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox",
            side_effect=GoogleMapsFetchError(
                "Static Maps returned HTTP 403: key=SECRET_GOOGLE_MAPS_KEY"
            ),
        ):
            worker.run()

        assert messages
        assert "SECRET_GOOGLE_MAPS_KEY" not in messages[0]

    def test_cancel_during_in_flight_fetch_is_authoritative(
        self, qtbot, with_api_key, mock_web_view
    ) -> None:
        """An in-flight worker reports cancellation instead of accepting data."""
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        started = False

        def _blocking_fetch(*_args, cancel_check=None, **_kwargs):
            nonlocal started
            started = True
            deadline = time.monotonic() + 2
            while cancel_check is not None and not cancel_check():
                if time.monotonic() >= deadline:
                    raise AssertionError("worker cancellation was not observed")
                time.sleep(0.001)
            raise FetchCancelled("cancelled")

        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox",
            side_effect=_blocking_fetch,
        ):
            dialog._on_accept()
            qtbot.waitUntil(lambda: started, timeout=1000)
            dialog._on_cancel()
            qtbot.waitUntil(lambda: dialog._worker is None, timeout=2000)

        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog._ok_button.isEnabled() is True

    def test_cancel_ignores_success_already_in_flight(
        self, qtbot, with_api_key, mock_web_view
    ) -> None:
        """A success queued after Cancel cannot accept the dialog."""
        from PIL import Image

        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        started = Event()
        release = Event()
        fake_result = FetchResult(
            image=Image.new("RGB", (10, 10)),
            meters_per_pixel=0.3,
            zoom=19,
            bbox=dialog._bbox,
            tile_grid=(1, 1),
        )

        def _slow_success(*_args, **_kwargs):
            started.set()
            assert release.wait(2)
            return fake_result

        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox",
            side_effect=_slow_success,
        ):
            dialog._on_accept()
            qtbot.waitUntil(started.is_set, timeout=1000)
            dialog._on_cancel()
            release.set()
            qtbot.waitUntil(lambda: dialog._worker is None, timeout=2000)

        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog.fetch_result is None

    def test_close_does_not_block_on_in_flight_worker(
        self, qtbot, with_api_key, mock_web_view
    ) -> None:
        """Closing requests cancellation without joining on the GUI thread."""
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        started = Event()
        release = Event()

        def _blocking_fetch(*_args, **_kwargs):
            started.set()
            release.wait(2)
            return FetchResult(
                image=MagicMock(),
                meters_per_pixel=0.3,
                zoom=19,
                bbox=dialog._bbox,
                tile_grid=(1, 1),
            )

        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox",
            side_effect=_blocking_fetch,
        ):
            dialog.show()
            dialog._on_accept()
            qtbot.waitUntil(started.is_set, timeout=1000)
            started_at = time.monotonic()
            dialog.close()
            assert time.monotonic() - started_at < 0.5
            assert dialog.isVisible() is True
            release.set()
            qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=2000)

        assert dialog._worker is None
        assert dialog._fetch_in_progress is False

    def test_escape_cancels_in_flight_worker_before_rejecting(
        self, qtbot, with_api_key, mock_web_view
    ) -> None:
        """Escape uses the same cancellation guard as the window close path."""
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        started = Event()

        def _blocking_fetch(*_args, cancel_check=None, **_kwargs):
            started.set()
            while cancel_check is not None and not cancel_check():
                time.sleep(0.001)
            raise FetchCancelled("cancelled")

        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox",
            side_effect=_blocking_fetch,
        ):
            dialog.show()
            dialog._on_accept()
            qtbot.waitUntil(started.is_set, timeout=1000)
            QTest.keyClick(dialog, Qt.Key.Key_Escape)
            qtbot.waitUntil(lambda: dialog._worker is None, timeout=2000)

        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog._fetch_in_progress is False

    def test_failed_worker_reference_is_cleared_before_second_cancel(
        self, qtbot, with_api_key, mock_web_view
    ) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)

        with (
            patch(
                "open_garden_planner.ui.dialogs.map_picker_dialog.fetch_bbox",
                side_effect=GoogleMapsFetchError("network failure"),
            ),
            patch(
                "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
            ),
        ):
            dialog._on_accept()
            qtbot.waitUntil(lambda: dialog._worker is None, timeout=1000)

        # A second Cancel after a terminal worker must be a normal dialog
        # action, not a call through a deleted QThread wrapper.
        dialog._on_cancel()
        assert dialog.result() == dialog.DialogCode.Rejected

    def test_success_path_accepts_dialog(
        self, qtbot, with_api_key, mock_web_view
    ) -> None:
        from PIL import Image

        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        fake_result = FetchResult(
            image=Image.new("RGB", (10, 10)),
            meters_per_pixel=0.3,
            zoom=19,
            bbox=BoundingBox(52.521, 13.404, 52.519, 13.406),
            tile_grid=(1, 1),
        )
        dialog._on_fetch_success(fake_result)
        assert dialog.fetch_result is fake_result
        assert dialog.result() == dialog.DialogCode.Accepted

    def test_failure_path_keeps_dialog_open(
        self, qtbot, with_api_key, mock_web_view
    ) -> None:
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        with patch(
            "open_garden_planner.ui.dialogs.map_picker_dialog.QMessageBox.critical"
        ):
            dialog._on_fetch_failure("Network error")
        ok_button = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button.isEnabled() is True
        assert dialog.fetch_result is None

    def test_cancel_during_fetch_keeps_dialog_open(
        self, qtbot, with_api_key, mock_web_view
    ) -> None:
        """Cancel during fetch must NOT close the dialog and must re-enable OK."""
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog
        dialog = MapPickerDialog()
        qtbot.addWidget(dialog)
        dialog._bridge.boundsUpdated.emit(52.521, 13.404, 52.519, 13.406)
        dialog._on_fetch_cancelled()
        # Dialog stayed open; both buttons usable again.
        assert dialog.result() != dialog.DialogCode.Accepted
        assert dialog._ok_button.isEnabled() is True
        assert dialog._cancel_button.isEnabled() is True
