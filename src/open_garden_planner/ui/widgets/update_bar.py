"""Dismissible update-notification bar for US-8.3.

Shown at the top of the main window when a newer GitHub release is available.
"""

import html
import logging
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QWidget,
)

logger = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = 15  # seconds — socket read timeout per chunk


class _DownloadWorker(QThread):
    """Background thread that downloads a file in chunks with a per-read timeout.

    Signals:
        progress(bytes_downloaded, total_bytes): Emitted after each chunk.
            total_bytes is 0 when Content-Length is not available.
        finished(dest): Emitted with the destination path on successful completion.
        failed(error): Emitted with the error message string on failure.
    """

    progress = pyqtSignal(int, int)
    finished = pyqtSignal(Path)
    failed = pyqtSignal(str)

    _CHUNK_SIZE = 65536

    def __init__(self, url: str, dest: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._url = url
        self._dest = dest
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                self._url,
                headers={"User-Agent": "OpenGardenPlanner-Updater"},
            )
            with urllib.request.urlopen(req, timeout=_DOWNLOAD_TIMEOUT) as resp:  # noqa: S310
                total = int(resp.getheader("Content-Length") or 0)
                downloaded = 0
                with self._dest.open("wb") as fh:
                    while not self._cancelled:
                        chunk = resp.read(self._CHUNK_SIZE)
                        if not chunk:
                            break
                        fh.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total)
            if self._cancelled:
                self._dest.unlink(missing_ok=True)
            else:
                self.finished.emit(self._dest)
        except Exception as exc:  # noqa: BLE001
            if not self._cancelled:
                self.failed.emit(str(exc))


class UpdateBar(QFrame):
    """Horizontal notification bar displayed when an update is available.

    Signals:
        skip_version_requested(str): Emitted with the version tag when the user
            clicks "Skip this version".
    """

    skip_version_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tag_name = ""
        self._download_url = ""
        self._html_url = ""
        self._worker: _DownloadWorker | None = None
        self._setup_ui()
        self.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_update(self, tag_name: str, _body: str, download_url: str, html_url: str = "") -> None:
        """Populate and display the bar for a specific update.

        Args:
            tag_name:     Version tag, e.g. ``"v1.6.0"``.
            _body:        Release notes snippet (reserved, not displayed in bar).
            download_url: Direct URL to the ``*-Setup.exe`` asset, or ``""``
                          if no installer asset was found.
            html_url:     GitHub release page URL for the "What's new" link.
        """
        self._tag_name = tag_name
        self._download_url = download_url
        self._html_url = html_url

        msg_plain = self.tr("A new version ({version}) is available.").format(version=tag_name)
        if html_url:
            whats_new = self.tr("What's new")
            link = (
                f'<a href="{html.escape(html_url)}" style="color:white;">'
                f"{html.escape(whats_new)} ↗</a>"
            )
            self._label.setText(f"{html.escape(msg_plain)}  {link}")
        else:
            self._label.setText(msg_plain)
        self._download_btn.setVisible(bool(download_url))
        self.show()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        self.setObjectName("UpdateBar")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMaximumHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self._label = QLabel()
        self._label.setWordWrap(False)
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self._label.setOpenExternalLinks(True)
        layout.addWidget(self._label, stretch=1)

        self._download_btn = QPushButton(self.tr("Download && Install"))
        self._download_btn.setFixedHeight(28)
        self._download_btn.clicked.connect(self._on_download)
        layout.addWidget(self._download_btn)

        skip_btn = QPushButton(self.tr("Skip this version"))
        skip_btn.setFixedHeight(28)
        skip_btn.clicked.connect(self._on_skip)
        layout.addWidget(skip_btn)

        remind_btn = QPushButton(self.tr("Remind me later"))
        remind_btn.setFixedHeight(28)
        remind_btn.clicked.connect(self.hide)
        layout.addWidget(remind_btn)

        self._apply_style()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            "#UpdateBar {"
            "  background-color: #1a73e8;"
            "  color: white;"
            "  border: none;"
            "}"
            "#UpdateBar QLabel {"
            "  color: white;"
            "  font-weight: bold;"
            "}"
            "#UpdateBar QPushButton {"
            "  background-color: rgba(255,255,255,51);"   # 0.20 * 255
            "  color: white;"
            "  border: 1px solid rgba(255,255,255,128);"  # 0.50 * 255
            "  border-radius: 4px;"
            "  padding: 2px 10px;"
            "}"
            "#UpdateBar QPushButton:hover {"
            "  background-color: rgba(255,255,255,89);"   # 0.35 * 255
            "}"
        )

    def _on_skip(self) -> None:
        self.skip_version_requested.emit(self._tag_name)
        self.hide()

    def _on_download(self) -> None:
        """Download the installer in a background thread, then launch it."""
        if not self._download_url:
            return
        if self._worker and self._worker.isRunning():
            return

        parent = self.window()

        reply = QMessageBox.question(
            parent,
            self.tr("Install Update"),
            self.tr(
                "The installer will be downloaded and launched.\n"
                "Open Garden Planner will close when the installer starts.\n\n"
                "Continue?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        filename = self._download_url.split("/")[-1]
        tmp_dir = Path(tempfile.mkdtemp())
        dest = tmp_dir / filename

        progress = QProgressDialog(
            self.tr("Downloading {filename}…").format(filename=filename),
            self.tr("Cancel"),
            0,
            100,
            parent,
        )
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()

        html_url = self._html_url

        worker = _DownloadWorker(self._download_url, dest, self)
        self._worker = worker

        def on_progress(downloaded: int, total: int) -> None:
            if progress.wasCanceled():
                worker.cancel()
                return
            if total > 0:
                progress.setMaximum(100)
                progress.setValue(int(downloaded / total * 100))
            else:
                progress.setMaximum(0)

        def on_finished(path: Path) -> None:
            progress.close()
            self._launch_installer(path, parent, html_url)

        def on_failed(error: str) -> None:
            progress.close()
            QMessageBox.critical(
                parent,
                self.tr("Download Failed"),
                self.tr(
                    "Could not download the installer:\n{error}\n\n"
                    "Download the latest release directly:\n{url}"
                ).format(error=error, url=html_url),
            )

        worker.progress.connect(on_progress)
        worker.finished.connect(on_finished)
        worker.failed.connect(on_failed)
        progress.canceled.connect(worker.cancel)
        worker.start()

    def _launch_installer(self, dest: Path, parent: QWidget, html_url: str) -> None:
        """Launch the downloaded installer and quit the application."""
        try:
            subprocess.Popen([str(dest)], close_fds=True)  # noqa: S603
        except Exception as exc:
            QMessageBox.critical(
                parent,
                self.tr("Launch Failed"),
                self.tr(
                    "Could not launch the installer:\n{error}\n\n"
                    "Try running Open Garden Planner as Administrator, "
                    "or download the installer directly:\n{url}"
                ).format(error=str(exc), url=html_url),
            )
            return
        QApplication.quit()
