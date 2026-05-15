"""Integration tests for :class:`MapPickerDialog`.

The dialog wraps a ``QWebEngineView`` that loads Google Maps — we don't
boot WebEngine here. Instead we exercise the bridge (the actual JS↔Python
contract) and the fetch worker indirection so the dialog logic is covered
without network IO. The WebEngine view is patched at construction time.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QDialogButtonBox, QWidget

from open_garden_planner.services.google_maps_service import (
    BoundingBox,
    FetchResult,
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
