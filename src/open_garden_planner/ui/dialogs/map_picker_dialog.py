"""Embedded Google Maps picker dialog.

Opens a Google Maps satellite view inside a ``QWebEngineView``, lets the
user search for an address (Places Autocomplete) and draw a rectangle by
clicking two corners. On confirm the Static Maps API is called via
``google_maps_service.fetch_bbox`` to produce a single PNG image, which
is then returned to the caller together with geo metadata so the canvas
background can be created with an exact pixel→meter scale.

For projects Google's EEA terms restrict (Static Maps rejects satellite /
hybrid with HTTP 403 — issue #346), the dialog additionally offers a
**JS-API view capture**: the page re-positions the already-rendered map
over the drawn rectangle and the Python side grabs the ``QWebEngineView``
widget's pixels (``QWidget.grab()`` — never DOM access, which would both
taint and expose the API key embedded in tile URLs). Larger rectangles are
covered by a **pan grid** (issue #347): a capture-profile phase pins the
real viewport + dpr, the page pans the map across a ``cols × rows`` grid of
viewport positions at one integer zoom, Python grabs every frame, stitches
them seam-free at analytic whole-pixel offsets, and the mosaic is cropped
to the bounding box with the same analytic Web-Mercator math, with exactly
one attribution strip baked in. The result flows through the exact same
``FetchResult`` path as the Static fetch (single-frame capture is the
degenerate 1×1 grid — one engine, not two).
"""

from __future__ import annotations

import io
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path

from PIL import Image
from PyQt6.QtCore import (
    QBuffer,
    QCoreApplication,
    QIODevice,
    QLocale,
    QObject,
    QThread,
    QTimer,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QImage
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.google_maps_js_capture import (
    EEA_SATELLITE_BLOCKED,
    FRAME_RETRIES,
    CaptureLayoutError,
    FrameLayout,
    bake_attribution,
    build_frame_layout,
    capture_dpr_close_enough,
    capture_dpr_is_sane,
    capture_mpp,
    classify_static_failure,
    effective_capture_dpr,
    frame_quality_ok,
    is_blank_capture,
    pick_capture_zoom_and_grid,
    stitch_frames,
)
from open_garden_planner.services.google_maps_service import (
    BoundingBox,
    FetchCancelled,
    FetchResult,
    GoogleMapsFetchError,
    GoogleMapsKeyMissingError,
    _scrub_key,
    crop_image_to_bbox,
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
_CAPTURE_DPR_MESSAGE = "The capture dimensions are inconsistent with the display scaling. Please retry; if it keeps failing, restart the map window."
_CAPTURE_TIMEOUT_MESSAGE = "The capture timed out. Check your network or the API key, then try again."
_CAPTURE_UNEXPECTED_MESSAGE = "Unexpected error while capturing the map view."
_CAPTURE_RETRY_MESSAGE = "A map frame did not render. Retrying..."
_CAPTURE_FRAME_FAILED_MESSAGE = (
    "One or more map frames could not be captured. Try again, or use 'Load image'."
)
_CAPTURE_VIEW_CHANGED_MESSAGE = (
    "The map view changed size during the capture. Please try again."
)
_CAPTURE_PROGRESS = "Capturing frame {current} of {total}..."
# Initial value for the capture-choreography zoom; _start_capture always
# overwrites it before any JS is driven (the profile's zoom report is
# informational only — the dialog decides the zoom itself).
_MAX_ZOOM_HINT = 20
_CAPTURE_TOKEN_MESSAGES = {
    "capture-timeout": _CAPTURE_TIMEOUT_MESSAGE,
    "map-not-ready": _CAPTURE_UNEXPECTED_MESSAGE,
    "capture-in-progress": _CAPTURE_UNEXPECTED_MESSAGE,
    "zoom-mismatch": _CAPTURE_UNEXPECTED_MESSAGE,
}

logger = logging.getLogger(__name__)


def _map_capture_token(token: str) -> str:
    """Map a raw JS capture token to the message constant to translate.

    Never surfaces a raw page string to the user: tokens are internal
    contract values, and JS exception text (``error: ...``) is logged
    scrubbed rather than displayed.
    """
    return _CAPTURE_TOKEN_MESSAGES.get(token, _CAPTURE_UNEXPECTED_MESSAGE)


def _attribution_text() -> str:
    """Google attribution line baked into captured images.

    Deliberately not translated: Google attribution strings stay in
    English (brand/legal text, same rule as the MCP API surface).
    """
    return QCoreApplication.translate(
        "MapPickerDialog", "Map data ©{year} Google"
    ).format(year=datetime.now().year)


def _qimage_to_pil(image) -> Image:
    """Convert a grabbed QImage to a PIL RGB image."""
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    data = bytes(buf.data())
    buf.close()
    return Image.open(io.BytesIO(data)).convert("RGB")


class _MapBridge(QObject):
    """JS↔Python bridge exposed on the page as ``window.bridge``.

    JS-callable slots (matching the names used in ``map_picker.html``):
    - ``ready()`` — hand over the API key plus locale + translated strings
    - ``boundsChanged(nw_lat, nw_lng, se_lat, se_lng)`` — rectangle updated
    - ``boundsCleared()`` — rectangle removed
    - ``captureReady(token, frameIndex, zoom, dpr, css_w, css_h)`` — the
      page has positioned the map over one frame's centre and is waiting
      for the widget grab; ``token`` echoes the capture generation,
      ``frameIndex`` identifies the frame (−1 = capture profile report
      carrying viewport size + dpr before the pan grid is derived)
    - ``captureError(token, reason)`` — JS-side capture failure (timeout,
      zoom mismatch, …); ``token`` echoes the capture generation
    - ``reportError(msg)`` — JS-level failure

    Python-side signals re-emit those events to the dialog with different
    names to avoid colliding with the slot names QWebChannel exposes.
    """

    setupReady = pyqtSignal(str, str, "QVariantMap")  # api_key, locale, strings
    boundsUpdated = pyqtSignal(float, float, float, float)
    cleared = pyqtSignal()
    captureViewReady = pyqtSignal(str, int, float, float, float, float)  # token, frameIndex, zoom, dpr, css w/h
    captureViewFailed = pyqtSignal(str, str)  # token, raw js-failure token
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

    @pyqtSlot(str, int, float, float, float, float)
    def captureReady(
        self,
        token: str,
        frame_index: int,
        zoom: float,
        dpr: float,
        css_w: float,
        css_h: float,
    ) -> None:
        # Metadata only — the pixels are taken by the Python side via
        # QWebEngineView.grab(); image/tile data never crosses the bridge.
        # The token echoes the capture generation so a stale readiness
        # report from a previous capture can never be mistaken for the new
        # one's; frame_index −1 is the capture profile report.
        self.captureViewReady.emit(token, frame_index, zoom, dpr, css_w, css_h)

    @pyqtSlot(str, str)
    def captureError(self, token: str, message: str) -> None:
        # Symmetric with captureReady: the token echoes the capture
        # generation so a failure report from a previous capture can never
        # be mistaken for the current one's.
        self.captureViewFailed.emit(token, _scrub_key(message, self._api_key))

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
        self._capture_in_progress = False
        self._capture_cancel_requested = False
        self._capture_generation = 0
        self._capture_watchdog: QTimer | None = None
        self._capture_bbox: BoundingBox | None = None
        self._close_after_capture = False
        # Pan-grid capture state (issue #347): the profile report pins the
        # layout (zoom + grid + centers derived after the viewport/dpr are
        # known); frames are gathered one settle at a time, then stitched.
        self._capture_zoom = _MAX_ZOOM_HINT
        self._capture_grid = (1, 1)
        self._capture_layout: FrameLayout | None = None
        self._capture_frame_index = 0
        self._capture_frames: list[Image.Image] = []
        self._capture_retries_left = FRAME_RETRIES

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
        # Secondary path (issue #346): capture the rendered JS-API map view
        # when the Static Maps API is rejected (EEA restriction) — or at any
        # time the user prefers it.
        self._capture_button = QPushButton(self.tr("Capture view"), self)
        self._capture_button.setEnabled(False)
        self._capture_button.clicked.connect(self._on_capture_clicked)
        self._buttons.addButton(
            self._capture_button, QDialogButtonBox.ButtonRole.ActionRole
        )
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
        self._bridge.captureViewReady.connect(self._on_capture_ready)
        self._bridge.captureViewFailed.connect(self._on_capture_error)
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
        self._ok_button.setEnabled(not self._capture_in_progress)
        self._capture_button.setEnabled(not self._fetch_in_progress)
        self._status.setText(self.tr("Rectangle selected. Click 'Load image' to fetch."))

    def _on_bounds_cleared(self) -> None:
        self._bbox = None
        self._ok_button.setEnabled(False)
        self._capture_button.setEnabled(False)
        self._status.setText(
            self.tr("Search for an address, then draw a rectangle on the map.")
        )

    def _on_bridge_error(self, message: str) -> None:
        QMessageBox.warning(self, self.tr("Map error"), message)

    # ------------------------------------------------------------------
    # JS-API view capture (issues #346, #347)
    # ------------------------------------------------------------------

    def _start_capture(self) -> bool:
        """Start a pan-grid capture: hide chrome, report the profile, then
        drive one frame settle at a time. Returns False when the capture
        cannot start (no bbox / busy / no page)."""
        bbox = self._bbox
        if bbox is None or self._fetch_in_progress or self._capture_in_progress:
            return False
        # Snapshot the capture request: every later stage consumes THIS
        # snapshot (never live dialog state) so a changed/finished dialog
        # can't silently re-georeference a grab.
        self._capture_in_progress = True
        self._capture_cancel_requested = False
        self._close_after_capture = False
        self._capture_generation += 1
        generation = self._capture_generation
        self._capture_bbox = bbox
        # The zoom/grid choice mirrors the Static path's pick_zoom_and_grid:
        # highest zoom whose pan grid fits the viewport, capped 3x3. The
        # viewport estimate is EXACT — during capture the page hides its
        # toolbar and the map div grows to the full view size — but the
        # profile report still pins the real dims + dpr before the layout.
        viewport_css = (float(self._view.width()), float(self._view.height()))
        zoom, cols, rows = pick_capture_zoom_and_grid(bbox, viewport_css)
        self._capture_zoom = zoom
        self._capture_grid = (cols, rows)
        self._capture_layout = None
        self._capture_frame_index = 0
        self._capture_frames = []
        self._capture_retries_left = FRAME_RETRIES
        self._ok_button.setEnabled(False)
        self._capture_button.setEnabled(False)
        self._status.setText(self.tr("Positioning the map view..."))
        js = f"window.beginCaptureChrome({int(generation):d});"
        self._view.page().runJavaScript(
            js, lambda result, generation=generation: self._on_capture_js_result(
                result, generation
            )
        )
        self._arm_capture_watchdog(generation)
        return True

    def _arm_capture_watchdog(self, generation: int) -> None:
        """(Re)arm the Python-side safety net.

        The JS side has its own 15 s per-frame timeout, but a page that
        loses its bridge must not leave the dialog stuck forever. Restarted
        at every choreography step so a slow multi-frame capture is never
        killed while it makes progress — and the previous timer is STOPPED
        first: an orphaned, still-armed timer from an earlier step would
        fire mid-capture and abort a perfectly healthy grid with a phantom
        timeout box (the same class of bug #346's phantom watchdog, in a
        new shape — §11.4).
        """
        previous = self._capture_watchdog
        if previous is not None:
            previous.stop()
        watchdog = QTimer(self)
        watchdog.setSingleShot(True)
        watchdog.timeout.connect(
            lambda generation=generation: self._handle_capture_failure(
                self.tr(_CAPTURE_TIMEOUT_MESSAGE), generation
            )
        )
        self._capture_watchdog = watchdog
        watchdog.start(20_000)

    def _on_capture_clicked(self) -> None:
        self._start_capture()

    @staticmethod
    def _normalise_js_token(token: object) -> str:
        """Reduce any page-produced failure value to a plain token."""
        text = str(token) if isinstance(token, str) else ""
        if text.startswith("error:"):
            return "error"
        return text.strip() or "unknown"

    def _on_capture_js_result(self, result: object, generation: int) -> None:
        if generation != self._capture_generation or self._capture_finished():
            return
        if result in ("ok", None):
            return
        # Raw page strings never reach the user: tokens map to translated
        # messages; an `error: …` detail is logged (scrubbed) for diagnosis.
        token = self._normalise_js_token(result)
        if token == "error" and isinstance(result, str):
            logger.error(
                "JS view-capture positioning failed: %s",
                _scrub_key(str(result), self._api_key),
            )
        self._handle_capture_failure(
            self.tr(_map_capture_token(token)), generation
        )

    def _on_capture_ready(
        self,
        token: str,
        frame_index: int,
        _zoom: float,
        dpr: float,
        css_w: float,
        css_h: float,
    ) -> None:
        generation = self._capture_generation
        if self._capture_finished():
            return
        if token != str(generation):
            # A readiness report from a previous capture — never process it
            # as the current one's.
            return
        # Snapshot the user intents BEFORE any terminal handler mutates the
        # state — and only finish *after* the ready/failure decision is made
        # (an early _finish_capture would make every later failure handler
        # see "finished" and silently no-op).
        cancelled = self._capture_cancel_requested
        close_wanted = self._close_after_capture
        if cancelled or close_wanted:
            self._finish_capture()
            self._cancel_button.setEnabled(True)
            # Capture and the Static fetch are mutually exclusive — each
            # start path guards the other — so a close intent can always
            # complete immediately; nothing here may swallow it.
            if close_wanted:
                self._close_after_capture = False
                super().reject()
            else:
                self._status.setText(self.tr("Capture cancelled."))
            return
        # Sanity-check the JS report before trusting it for scale math.
        if css_w <= 0 or css_h <= 0:
            self._handle_capture_failure(
                self.tr(_CAPTURE_UNEXPECTED_MESSAGE), generation
            )
            return
        if frame_index == -1:
            # Capture profile: the page reports the real viewport + dpr so
            # the pan grid can be derived analytically (issue #347).
            self._on_capture_profile(dpr, css_w, css_h, generation)
            return
        self._on_capture_frame(frame_index, dpr, css_w, css_h, generation)

    def _on_capture_profile(
        self,
        dpr: float,
        css_w: float,
        css_h: float,
        generation: int,
    ) -> None:
        """Build the pan-grid layout from the profile and start the frames."""
        if self._capture_layout is not None:
            # Duplicate/stale profile report — the capture already moved on.
            return
        bbox = self._capture_bbox
        if bbox is None:
            self._handle_capture_failure(
                self.tr(_CAPTURE_UNEXPECTED_MESSAGE), generation
            )
            return
        reported_dpr = float(dpr) if dpr and dpr > 0 else 1.0
        try:
            cols, rows = self._capture_grid
            layout = build_frame_layout(
                bbox, self._capture_zoom, cols, rows, (css_w, css_h), reported_dpr
            )
        except (ValueError, CaptureLayoutError):
            logger.error(
                "Capture layout derivation failed:\n%s",
                _scrub_key(traceback.format_exc(), self._api_key),
            )
            self._handle_capture_failure(
                self.tr(_CAPTURE_FRAME_FAILED_MESSAGE), generation
            )
            return
        self._capture_layout = layout
        self._capture_frame_index = 0
        self._capture_retries_left = FRAME_RETRIES
        centers_json = json.dumps([[lat, lng] for lat, lng in layout.centers])
        js = (
            f"window.beginCaptureFrames({centers_json}, {self._capture_zoom:d}, "
            f"{int(generation):d});"
        )
        self._view.page().runJavaScript(
            js, lambda result, generation=generation: self._on_capture_js_result(
                result, generation
            )
        )
        self._arm_capture_watchdog(generation)

    def _on_capture_frame(
        self,
        frame_index: int,
        dpr: float,
        css_w: float,
        css_h: float,
        generation: int,
    ) -> None:
        """Grab one settled frame, gate its quality, and either advance,
        retry, or stitch the finished sequence (issue #347)."""
        layout = self._capture_layout
        if layout is None or frame_index != self._capture_frame_index:
            # A redundant or stale frame report — the page only ever reports
            # the frame this dialog asked it to settle.
            return
        # A mid-capture window resize would silently mis-stitch the frames;
        # refuse cleanly instead of shipping a wrong image.
        if (
            abs(css_w - layout.viewport_css_w) > 1.0
            or abs(css_h - layout.viewport_css_h) > 1.0
        ):
            self._handle_capture_failure(
                self.tr(_CAPTURE_VIEW_CHANGED_MESSAGE), generation
            )
            return
        try:
            grab = self._view.grab()
            # Derive the effective pixel density from the grab ITSELF —
            # measured ruler, not a report: physical px / css px.
            dpr_effective = effective_capture_dpr(grab.width(), css_w)
            if frame_index == 0:
                reported_dpr = float(dpr) if dpr and dpr > 0 else None
                if not capture_dpr_is_sane(dpr_effective, reported_dpr):
                    # A deterministic refusal, not a transient "unexpected"
                    # failure — the message says so honestly.
                    self._handle_capture_failure(
                        self.tr(_CAPTURE_DPR_MESSAGE), generation
                    )
                    return
                # The pan grid's geometry is built from the REPORTED dpr
                # (the mosaic must be self-consistent), so the ruler must
                # agree with the report almost exactly — otherwise every
                # paste offset and the result mpp would be slightly wrong.
                if reported_dpr is not None and not capture_dpr_close_enough(
                    dpr_effective, reported_dpr
                ):
                    self._handle_capture_failure(
                        self.tr(_CAPTURE_DPR_MESSAGE), generation
                    )
                    return
            image = _qimage_to_pil(
                grab.toImage().convertToFormat(QImage.Format.Format_RGB888)
            )
        except Exception:
            # The capture path must never crash the dialog on a rendering
            # quirk; log scrubbed and surface the generic message.
            logger.error(
                "Unexpected view capture failure:\n%s",
                _scrub_key(traceback.format_exc(), self._api_key),
            )
            self._handle_capture_failure(
                self.tr(_CAPTURE_UNEXPECTED_MESSAGE), generation
            )
            return
        if not frame_quality_ok(image) or is_blank_capture(image):
            # A blank/partly rendered frame must never land in the mosaic —
            # retry it with a fresh settle, then fail cleanly.
            if self._capture_retries_left > 0:
                self._capture_retries_left -= 1
                self._status.setText(self.tr(_CAPTURE_RETRY_MESSAGE))
                self._arm_capture_watchdog(generation)
                self._view.page().runJavaScript("window.retryCaptureFrame();")
                return
            self._handle_capture_failure(
                self.tr(_CAPTURE_FRAME_FAILED_MESSAGE), generation
            )
            return
        self._capture_frames.append(image)
        if len(self._capture_frames) < layout.frame_count:
            self._capture_retries_left = FRAME_RETRIES
            self._status.setText(
                self.tr(_CAPTURE_PROGRESS).format(
                    current=len(self._capture_frames) + 1, total=layout.frame_count
                )
            )
            self._capture_frame_index += 1
            self._arm_capture_watchdog(generation)
            self._view.page().runJavaScript("window.advanceCaptureFrame();")
            return
        try:
            result = self._build_capture_result(layout)
        except Exception:
            logger.error(
                "Unexpected view capture stitching failure:\n%s",
                _scrub_key(traceback.format_exc(), self._api_key),
            )
            self._handle_capture_failure(
                self.tr(_CAPTURE_FRAME_FAILED_MESSAGE), generation
            )
            return
        # Success is a terminal path too: finish stops the watchdog and
        # restores the page chrome. (Skipping it once re-armed a 20 s
        # watchdog that fired a phantom timeout box after a good import —
        # pinned by TestCaptureSuccess.test_success_stops_the_watchdog.)
        self._finish_capture()
        self._fetch_result = result
        self.accept()

    def _build_capture_result(self, layout: FrameLayout) -> FetchResult:
        """Stitch the gathered frames and build the standard FetchResult.

        Attribution is baked exactly once, on the cropped result — never
        per frame (the pan grid would stamp N strips into the mosaic).
        """
        bbox = self._capture_bbox
        if bbox is None:
            raise RuntimeError("capture result requested without a bbox")
        mosaic = stitch_frames(self._capture_frames, layout, bbox)
        mpp = capture_mpp(bbox.center[0], layout.zoom, layout.dpr)
        cropped = crop_image_to_bbox(mosaic, mpp, bbox)
        if is_blank_capture(cropped):
            raise RuntimeError("stitched capture is blank")
        attribution = _attribution_text()
        cropped = bake_attribution(cropped, attribution)
        return FetchResult(
            image=cropped,
            meters_per_pixel=mpp,
            zoom=layout.zoom,
            bbox=bbox,
            tile_grid=(layout.cols, layout.rows),
            source="google_js_view_capture",
            attribution=attribution,
        )

    def _on_capture_error(self, token: str, message: str) -> None:
        if self._capture_finished():
            return
        if token != str(self._capture_generation):
            # A failure from a previous capture — ignore, as with readiness.
            return
        raw_token = self._normalise_js_token(message)
        if raw_token not in ("capture-timeout", "zoom-mismatch", "map-not-ready", "capture-in-progress"):
            logger.error(
                "JS view capture error token: %s",
                _scrub_key(str(message), self._api_key),
            )
        self._handle_capture_failure(
            self.tr(_map_capture_token(raw_token)), self._capture_generation
        )

    def _capture_finished(self) -> bool:
        return not self._capture_in_progress

    def _finish_capture(self) -> None:
        """Return the page + dialog to the normal state. Idempotent."""
        watchdog = self._capture_watchdog
        if watchdog is not None:
            watchdog.stop()
            self._capture_watchdog = None
        if not self._capture_in_progress:
            self._capture_cancel_requested = False
            return
        self._capture_in_progress = False
        self._capture_cancel_requested = False
        self._view.page().runJavaScript("window.restoreCaptureChrome();")
        if self._bbox is not None and not self._fetch_in_progress:
            self._ok_button.setEnabled(True)
            self._capture_button.setEnabled(True)

    def _handle_capture_failure(self, message: str, generation: int) -> None:
        if generation != self._capture_generation or self._capture_finished():
            return
        # Snapshot the user intents BEFORE _finish_capture wipes the flags.
        cancelled = self._capture_cancel_requested
        close_wanted = self._close_after_capture
        self._finish_capture()
        self._cancel_button.setEnabled(True)
        if close_wanted:
            # A cancel/close already happened — the user doesn't want an
            # error box, they want the dialog gone. Capture and the Static
            # fetch are mutually exclusive, so the rejection can always
            # complete immediately.
            self._close_after_capture = False
            super().reject()
            return
        if cancelled:
            self._status.setText(self.tr("Capture cancelled."))
            return
        self._status.setText(
            self.tr("Capture failed. Try again, or use 'Load image'.")
        )
        QMessageBox.critical(self, self.tr("Failed to capture view"), message)

    def _ask_capture_fallback(self) -> bool:
        """Offer the view-capture path when Static returns the EEA 403."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(self.tr("Satellite image blocked"))
        box.setText(
            self.tr(
                "Google rejected the Static Maps request for your account and "
                "region: satellite and hybrid map types are not available "
                "through the Static Maps API (EEA restriction).\n\n"
                "You can capture the satellite view directly from the map "
                "below instead."
            )
        )
        capture_btn = box.addButton(
            self.tr("Capture view"), QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(self.tr("Retry Static Maps"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(capture_btn)
        box.exec()
        return box.clickedButton() is capture_btn

    def _on_accept(self) -> None:
        if self._bbox is None or self._fetch_in_progress or self._capture_in_progress:
            return
        # Only the OK button gets disabled — Cancel must stay clickable
        # so the user can abort a long mosaic fetch.
        self._ok_button.setEnabled(False)
        self._capture_button.setEnabled(False)
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
        if self._capture_in_progress:
            # The capture completes on the GUI thread only when the page
            # reports readiness; mark it cancelled and let the ready/error
            # handlers (or the watchdog) finish the state.
            self._capture_cancel_requested = True
            self._status.setText(self.tr("Cancelling..."))
            self._cancel_button.setEnabled(False)
            return
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
            QMessageBox.critical(self, self.tr("Failed to fetch image"), message)
        elif message == _UNEXPECTED_FETCH_FAILURE:
            QMessageBox.critical(
                self,
                self.tr("Failed to fetch image"),
                self.tr(_UNEXPECTED_FETCH_MESSAGE),
            )
        elif classify_static_failure(None, message) == EEA_SATELLITE_BLOCKED:
            # Google's own 403 body identified the EEA restriction. Offer the
            # JS-API view capture path (issue #346) without re-diagnosing.
            if self._ask_capture_fallback():
                self._ok_button.setEnabled(True)
                self._cancel_button.setEnabled(True)
                self._start_capture()
                return
        else:
            QMessageBox.critical(self, self.tr("Failed to fetch image"), message)
        self._ok_button.setEnabled(self._bbox is not None)
        self._capture_button.setEnabled(self._bbox is not None)
        self._cancel_button.setEnabled(True)
        self._status.setText(self.tr("Try again, or pick a smaller area."))

    def _on_fetch_cancelled(self, generation: int | None = None) -> None:
        if generation is not None and generation != self._fetch_generation:
            return
        self._fetch_in_progress = False
        self._fetch_cancel_requested = False
        self._ok_button.setEnabled(self._bbox is not None)
        self._capture_button.setEnabled(self._bbox is not None)
        self._cancel_button.setEnabled(True)
        self._status.setText(self.tr("Fetch cancelled."))

    def reject(self) -> None:
        """Cancel an active fetch before allowing any dialog rejection path."""
        if self._capture_in_progress:
            self._capture_cancel_requested = True
            # Unlike a Cancel button click (which wants the dialog to stay
            # open), reject()/close intent is honoured once the capture
            # reaches a terminal handler.
            self._close_after_capture = True
            return
        if (self._fetch_in_progress or self._worker is not None) and self._request_worker_shutdown():
            return
        self._close_after_fetch = False
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        # ``requests.get(timeout=10)`` is uninterruptible from the GUI thread
        # — ``cancel_check`` is consulted between tiles and immediately after
        # each response, never during a single in-flight HTTP call. Keep the
        # dialog alive until the worker finishes instead of blocking the GUI
        # thread while joining it. The GUI-thread capture is cancelled the
        # same way: mark it and let the terminal handler re-run the close.
        if self._capture_in_progress:
            self._capture_cancel_requested = True
            self._close_after_capture = True
            event.ignore()
            return
        if (self._fetch_in_progress or self._worker is not None) and self._request_worker_shutdown():
            event.ignore()
            return
        super().closeEvent(event)
