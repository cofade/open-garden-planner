"""Embedded Google Maps picker dialog.

Opens a Google Maps satellite view inside a ``QWebEngineView``, lets the
user search for an address (Places Autocomplete) and draw a rectangle by
clicking two corners. On confirm the Static Maps API is called via
``google_maps_service.fetch_bbox`` to produce a single PNG image, which
is then returned to the caller together with geo metadata so the canvas
background can be created with an exact pixel→meter scale.
"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path

from PyQt6.QtCore import (
    QLocale,
    QObject,
    QThread,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.google_maps_service import (
    BoundingBox,
    FetchCancelled,
    FetchResult,
    GoogleMapsFetchError,
    GoogleMapsKeyMissingError,
    _scrub_key,
    fetch_bbox,
    get_api_key,
    has_api_key,
)

_KEY_MISSING_FAILURE = "google_maps_key_missing"
_UNEXPECTED_FETCH_FAILURE = "unexpected_satellite_fetch_failure"
_KEY_MISSING_MESSAGE = (
    "Set a Google Maps API key in Preferences or "
    "OGP_GOOGLE_MAPS_KEY in your .env file to enable satellite "
    "background loading."
)
_UNEXPECTED_FETCH_MESSAGE = "Unexpected error while fetching satellite image."

logger = logging.getLogger(__name__)


class _MapBridge(QObject):
    """JS↔Python bridge exposed on the page as ``window.bridge``.

    JS-callable slots (matching the names used in ``map_picker.html``):
    - ``ready()`` — hand over the API key plus locale + translated strings
    - ``boundsChanged(nw_lat, nw_lng, se_lat, se_lng)`` — rectangle updated
    - ``boundsCleared()`` — rectangle removed
    - ``reportError(msg)`` — JS-level failure

    Python-side signals re-emit those events to the dialog with different
    names to avoid colliding with the slot names QWebChannel exposes.
    """

    setupReady = pyqtSignal(str, str, "QVariantMap")  # api_key, locale, strings
    boundsUpdated = pyqtSignal(float, float, float, float)
    cleared = pyqtSignal()
    errorReported = pyqtSignal(str)

    def __init__(
        self,
        api_key: str,
        locale: str,
        strings: dict[str, str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._locale = locale
        self._strings = strings

    @pyqtSlot()
    def ready(self) -> None:
        self.setupReady.emit(self._api_key, self._locale, self._strings)

    @pyqtSlot(float, float, float, float)
    def boundsChanged(
        self, nw_lat: float, nw_lng: float, se_lat: float, se_lng: float
    ) -> None:
        self.boundsUpdated.emit(nw_lat, nw_lng, se_lat, se_lng)

    @pyqtSlot()
    def boundsCleared(self) -> None:
        self.cleared.emit()

    @pyqtSlot(str)
    def reportError(self, message: str) -> None:
        # Defensive: scrub the API key from any JS-side error message before
        # it reaches the dialog (and ultimately a QMessageBox). Today's only
        # caller is a hardcoded string, but browsers can pass the script URL
        # into ``script.onerror`` and any future JS error path could carry
        # the key.
        self.errorReported.emit(_scrub_key(message, self._api_key))


class _FetchWorker(QThread):
    """Runs ``fetch_bbox`` in a background thread.

    Cancellation: the dialog calls :meth:`requestInterruption`; the worker
    passes its ``isInterruptionRequested`` as the service's ``cancel_check``
    callback, which raises :class:`FetchCancelled` between tiles.
    """

    finished_ok = pyqtSignal(object)  # FetchResult
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self, bbox: BoundingBox, api_key: str, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._bbox = bbox
        self._api_key = api_key

    def run(self) -> None:  # noqa: D401 - QThread API
        try:
            result = fetch_bbox(
                self._bbox,
                api_key=self._api_key,
                cancel_check=self.isInterruptionRequested,
            )
        except FetchCancelled:
            self.cancelled.emit()
            return
        except GoogleMapsKeyMissingError:
            self.failed.emit(_KEY_MISSING_FAILURE)
            return
        except GoogleMapsFetchError as e:
            self.failed.emit(_scrub_key(str(e), self._api_key))
            return
        except Exception:  # safety net for unexpected errors
            # Do not forward arbitrary exception text: lower layers may carry
            # request URLs or other sensitive implementation details.
            # Format and scrub the traceback before logging it; logging the
            # exception object with ``exc_info=True`` could write a raw API
            # key echoed by a lower-level request error.
            logger.error(
                "Unexpected satellite image fetch failure:\n%s",
                _scrub_key(traceback.format_exc(), self._api_key),
            )
            self.failed.emit(_UNEXPECTED_FETCH_FAILURE)
            return
        self.finished_ok.emit(result)


class MapPickerDialog(QDialog):
    """Embedded Google Maps picker with rectangle selection."""

    HTML_FILE = (
        Path(__file__).parent.parent.parent
        / "resources"
        / "web"
        / "map_picker.html"
    )

    def __init__(
        self, parent: QWidget | None = None, *, api_key: str | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Load Satellite Background"))
        self.resize(1000, 700)

        self._bbox: BoundingBox | None = None
        self._fetch_result: FetchResult | None = None
        self._worker: _FetchWorker | None = None
        self._fetch_generation = 0
        self._fetch_in_progress = False
        self._fetch_cancel_requested = False
        self._close_after_fetch = False
        self._api_key = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._view = QWebEngineView(self)
        # The HTML is loaded via ``file://`` (a local resource) but pulls
        # Google Maps JS from ``https://maps.googleapis.com``. By default
        # QtWebEngine treats that as a cross-origin block and the script
        # tag's ``onerror`` fires — visible as "Failed to load Google Maps
        # JS API". Granting the local page remote-URL access fixes it.
        _settings = self._view.settings()
        _settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        _settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
        )
        layout.addWidget(self._view, 1)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(10, 6, 10, 6)
        self._status = QLabel(
            self.tr("Search for an address, then draw a rectangle on the map."),
            self,
        )
        status_row.addWidget(self._status, 1)
        layout.addLayout(status_row)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self._ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._cancel_button = self._buttons.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_button.setText(self.tr("Load image"))
        self._ok_button.setEnabled(False)
        self._buttons.accepted.connect(self._on_accept)
        # Cancel does two jobs: cancel an in-flight fetch (if any) and close
        # the dialog if nothing is running. ``_on_cancel`` handles both.
        self._buttons.rejected.connect(self._on_cancel)
        layout.addWidget(self._buttons)

        # The application normally passes a resolved key; a missing key still
        # surfaces as a friendly error rather than a 403 mid-flow.
        try:
            self._api_key = get_api_key(api_key)
        except GoogleMapsKeyMissingError:
            QMessageBox.warning(
                self,
                self.tr("API key missing"),
                self.tr(_KEY_MISSING_MESSAGE),
            )
            self.reject()
            return

        # Build the i18n payload for the HTML side. Strings live in this
        # dialog's translation context so they appear in the .ts file under
        # ``MapPickerDialog`` alongside the Qt-side strings.
        ui_strings = {
            "searchPlaceholder": self.tr("Search address..."),
            "drawButton": self.tr("Draw rectangle"),
            "clearButton": self.tr("Clear"),
            "hintInitial": self.tr(
                "Click 'Draw rectangle', then drag a rectangle on the map."
            ),
            "hintDrawing": self.tr("Drag on the map to draw the rectangle."),
        }
        # Carry language + region separately rather than parsing BCP47 in
        # JS — for locales like ``zh-Hant-TW`` the second BCP47 subtag is a
        # script (``Hant``), not a region. ``QLocale().name()`` gives us
        # ``de_DE`` etc., and ``territory()`` is the authoritative source.
        qlocale = QLocale()
        language_tag = qlocale.bcp47Name().split("-")[0] or "en"
        territory_code = QLocale.territoryToCode(qlocale.territory()) or language_tag.upper()
        locale_payload = f"{language_tag}|{territory_code}"
        self._bridge = _MapBridge(self._api_key, locale_payload, ui_strings, self)
        self._bridge.boundsUpdated.connect(self._on_bounds_updated)
        self._bridge.cleared.connect(self._on_bounds_cleared)
        self._bridge.errorReported.connect(self._on_bridge_error)

        channel = QWebChannel(self)
        channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(channel)
        self._view.setUrl(QUrl.fromLocalFile(str(self.HTML_FILE)))

    @staticmethod
    def is_available(api_key: str | None = None) -> bool:
        """Whether the dialog can be opened (API key present)."""
        return has_api_key(api_key)

    @property
    def fetch_result(self) -> FetchResult | None:
        return self._fetch_result

    def _on_bounds_updated(
        self, nw_lat: float, nw_lng: float, se_lat: float, se_lng: float
    ) -> None:
        # Reject degenerate (zero-area / sub-pixel) rectangles — a stray
        # click without a drag would otherwise enable OK on a 1×1-pixel
        # fetch. ~1e-6° is < 0.2 m at any latitude, well below the resolution
        # of the lowest sensible satellite request.
        if abs(nw_lat - se_lat) < 1e-6 or abs(nw_lng - se_lng) < 1e-6:
            self._on_bounds_cleared()
            return
        self._bbox = BoundingBox(
            nw_lat=nw_lat, nw_lng=nw_lng, se_lat=se_lat, se_lng=se_lng
        )
        self._ok_button.setEnabled(True)
        self._status.setText(self.tr("Rectangle selected. Click 'Load image' to fetch."))

    def _on_bounds_cleared(self) -> None:
        self._bbox = None
        self._ok_button.setEnabled(False)
        self._status.setText(
            self.tr("Search for an address, then draw a rectangle on the map.")
        )

    def _on_bridge_error(self, message: str) -> None:
        QMessageBox.warning(self, self.tr("Map error"), message)

    def _on_accept(self) -> None:
        if self._bbox is None or self._fetch_in_progress:
            return
        # Only the OK button gets disabled — Cancel must stay clickable
        # so the user can abort a long mosaic fetch.
        self._ok_button.setEnabled(False)
        self._status.setText(self.tr("Fetching satellite image..."))
        self._fetch_generation += 1
        generation = self._fetch_generation
        self._fetch_in_progress = True
        self._fetch_cancel_requested = False
        self._worker = _FetchWorker(self._bbox, self._api_key, self)
        worker = self._worker
        worker.finished_ok.connect(
            lambda result, generation=generation: self._on_fetch_success(
                result, generation
            )
        )
        worker.failed.connect(
            lambda message, generation=generation: self._on_fetch_failure(
                message, generation
            )
        )
        worker.cancelled.connect(
            lambda generation=generation: self._on_fetch_cancelled(generation)
        )
        # Clear the Python reference when the thread reaches its terminal
        # signal, then schedule C++ deletion. Keeping a deleted QThread wrapper
        # in ``_worker`` makes a later Cancel click call into invalid Qt state.
        worker.finished.connect(lambda worker=worker: self._on_worker_finished(worker))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_worker_finished(self, worker: _FetchWorker) -> None:
        """Drop a terminal worker reference without disturbing a replacement."""
        if self._worker is not worker:
            return
        self._worker = None
        if self._close_after_fetch:
            # QThread.finished is delivered only after run() has returned, so
            # the child is safe to release before rejecting the dialog. The
            # queued terminal signal, if any, is discarded with the dialog.
            self._close_after_fetch = False
            self._fetch_in_progress = False
            self._fetch_cancel_requested = False
            super().reject()

    def _request_worker_shutdown(self) -> bool:
        """Request cancellation and return whether a worker still owns close."""
        worker = self._worker
        if worker is None:
            # A terminal signal may already have cleared the wrapper. There is
            # no running child left for this dialog to own in that state.
            self._fetch_in_progress = False
            self._fetch_cancel_requested = False
            self._close_after_fetch = False
            return False
        self._close_after_fetch = True
        self._fetch_cancel_requested = True
        self._ok_button.setEnabled(False)
        self._cancel_button.setEnabled(False)
        self._status.setText(self.tr("Cancelling..."))
        try:
            if worker.isRunning():
                worker.requestInterruption()
        except RuntimeError:
            if self._worker is worker:
                self._worker = None
            self._fetch_in_progress = False
            self._fetch_cancel_requested = False
            self._close_after_fetch = False
            return False
        return True

    def _on_cancel(self) -> None:
        """Cancel a running fetch, or close the dialog if nothing is running."""
        if self._fetch_in_progress:
            self._fetch_cancel_requested = True
            self._status.setText(self.tr("Cancelling..."))
            self._cancel_button.setEnabled(False)
        worker = self._worker
        if worker is not None:
            try:
                running = worker.isRunning()
            except RuntimeError:
                self._worker = None
                running = False
            if running:
                worker.requestInterruption()
                return
            if self._fetch_in_progress:
                # The worker has stopped, but its terminal signal may still be
                # queued. Keep the dialog open until that signal is processed.
                return
        if self._fetch_in_progress:
            # The terminal worker cleanup may already have cleared the wrapper;
            # a queued success/failure/cancel signal still owns this fetch.
            return
        self.reject()

    def _on_fetch_success(
        self, result: FetchResult, generation: int | None = None
    ) -> None:
        if generation is not None and generation != self._fetch_generation:
            return
        if self._fetch_cancel_requested:
            self._on_fetch_cancelled(generation)
            return
        self._fetch_in_progress = False
        self._fetch_cancel_requested = False
        self._fetch_result = result
        self.accept()

    def _on_fetch_failure(self, message: str, generation: int | None = None) -> None:
        if generation is not None and generation != self._fetch_generation:
            return
        self._fetch_in_progress = False
        self._fetch_cancel_requested = False
        if self._close_after_fetch:
            return
        if message == _KEY_MISSING_FAILURE:
            message = self.tr(_KEY_MISSING_MESSAGE)
        elif message == _UNEXPECTED_FETCH_FAILURE:
            message = self.tr(_UNEXPECTED_FETCH_MESSAGE)
        QMessageBox.critical(self, self.tr("Failed to fetch image"), message)
        self._ok_button.setEnabled(True)
        self._cancel_button.setEnabled(True)
        self._status.setText(self.tr("Try again, or pick a smaller area."))

    def _on_fetch_cancelled(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._fetch_generation:
            return
        self._fetch_in_progress = False
        self._fetch_cancel_requested = False
        self._ok_button.setEnabled(self._bbox is not None)
        self._cancel_button.setEnabled(True)
        self._status.setText(self.tr("Fetch cancelled."))

    def reject(self) -> None:
        """Cancel an active fetch before allowing any dialog rejection path."""
        if (self._fetch_in_progress or self._worker is not None) and self._request_worker_shutdown():
            return
        self._close_after_fetch = False
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # ``requests.get(timeout=10)`` is uninterruptible from the GUI thread
        # — ``cancel_check`` is consulted between tiles and immediately after
        # each response, never during a single in-flight HTTP call. Keep the
        # dialog alive until the worker finishes instead of blocking the GUI
        # thread while joining it.
        if (self._fetch_in_progress or self._worker is not None) and self._request_worker_shutdown():
            event.ignore()
            return
        super().closeEvent(event)
