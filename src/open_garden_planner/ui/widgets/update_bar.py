"""Dismissible update-notification bar for US-8.3.

Shown at the top of the main window when a newer GitHub release is available.
"""

import contextlib
import html
import logging
import subprocess
import tempfile
import threading
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

from open_garden_planner.services.update_checker import ReleaseInfo
from open_garden_planner.services.verified_update import (
    DownloadCancelled,
    VerificationError,
    VerifiedInstaller,
    download_verified_installer,
)
from open_garden_planner.ui.theme import theme_color

logger = logging.getLogger(__name__)

class _DownloadWorker(QThread):
    """Background thread that downloads a file in chunks with a per-read timeout.

    Emits verified_ready only after size, origin and digest checks succeed.
    Failure signals contain categories, never raw network errors or signed URLs.
    """

    progress = pyqtSignal(int, int)
    verified_ready = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, release: ReleaseInfo, dest: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._release = release
        self._dest = dest
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            result = download_verified_installer(
                self._release, self._dest, cancelled=self._cancelled.is_set,
                progress=self.progress.emit,
            )
            self.verified_ready.emit(result)
        except DownloadCancelled:
            pass
        except Exception as exc:  # noqa: BLE001
            if not self._cancelled.is_set():
                self.failed.emit(str(exc) if isinstance(exc, VerificationError) else "network")


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
        self._release: ReleaseInfo | None = None
        self._worker: _DownloadWorker | None = None
        self._setup_ui()
        self.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_update(self, release: ReleaseInfo) -> None:
        """Populate and display the bar for a specific update.

        Args:
            tag_name:     Version tag, e.g. ``"v1.6.0"``.
            _body:        Release notes snippet (reserved, not displayed in bar).
            download_url: Direct URL to the ``*-Setup.exe`` asset, or ``""``
                          if no installer asset was found.
            html_url:     GitHub release page URL for the "What's new" link.
        """
        self._release = release
        tag_name, html_url = release.tag_name, release.html_url
        self._tag_name = tag_name
        self._download_url = release.download_url or ""
        self._html_url = html_url

        msg_plain = self.tr("A new version ({version}) is available.").format(version=tag_name)
        if html_url:
            whats_new = self.tr("What's new")
            link = (
                f'<a href="{html.escape(html_url)}" '
                f'style="color:{theme_color("on_status")};">'
                f"{html.escape(whats_new)} ↗</a>"
            )
            self._label.setText(f"{html.escape(msg_plain)}  {link}")
        else:
            self._label.setText(msg_plain)
        self._download_btn.setEnabled(release.installable)
        self._download_btn.setToolTip(
            "" if release.installable else self.tr("This release has no verifiable installer. Use the release page.")
        )
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

        # Styling lives in theme.py's global stylesheet (#UpdateBar rules,
        # info_bg banner) so a theme switch restyles the bar automatically.

    def apply_theme_colors(self, _colors: dict[str, str]) -> None:
        """Rebuild the label on theme switch (the What's-new link color is
        baked into its HTML at show time)."""
        if self.isVisible() and self._release is not None:
            self.show_update(self._release)

    def _on_skip(self) -> None:
        self.skip_version_requested.emit(self._tag_name)
        self.hide()

    def _on_download(self) -> None:
        """Download the installer in a background thread, then launch it."""
        if self._release is None or not self._release.installable:
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

        filename = self._release.installer_name
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

        worker = _DownloadWorker(self._release, dest, self)
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

        def on_finished(result: VerifiedInstaller) -> None:
            worker.wait()  # the verified signal can arrive before run() returns
            if progress.wasCanceled() or worker._cancelled.is_set():
                result.path.unlink(missing_ok=True)
                tmp_dir.rmdir()
                return
            progress.close()
            self._launch_installer(result, parent, html_url)

        def on_failed(error: str) -> None:
            progress.close()
            QMessageBox.critical(
                parent,
                self.tr("Download Failed"),
                self.tr(
                    "Could not download the installer:\n{error}\n\n"
                    "Download the latest release directly:\n{url}"
                ).format(error=self._verification_message(error), url=html_url),
            )

        def cleanup_empty_directory() -> None:
            # Verified installers remain for the running OS installer. Failed
            # and cancelled transfers own no files and leave no empty directory.
            with contextlib.suppress(OSError):
                tmp_dir.rmdir()

        worker.progress.connect(on_progress)
        worker.verified_ready.connect(on_finished)
        worker.failed.connect(on_failed)
        worker.finished.connect(cleanup_empty_directory)
        progress.canceled.connect(worker.cancel)
        worker.start()

    def _verification_message(self, category: str) -> str:
        return {
            "origin": self.tr("The download origin is not permitted."),
            "manifest": self.tr("The release checksum is missing or invalid."),
            "length": self.tr("The installer size does not match the release."),
            "digest": self.tr("The installer checksum does not match the release."),
            "destination": self.tr("The installer destination already exists."),
        }.get(category, self.tr("The download could not be completed safely."))

    def _launch_installer(self, result: VerifiedInstaller, parent: QWidget, html_url: str) -> None:
        """Launch the downloaded installer and quit the application."""
        try:
            result.check()
            subprocess.Popen([str(result.path)], close_fds=True)  # noqa: S603
        except Exception as exc:
            QMessageBox.critical(
                parent,
                self.tr("Launch Failed"),
                self.tr(
                    "Could not launch the installer:\n{error}\n\n"
                    "Try running Open Garden Planner as Administrator, "
                    "or download the installer directly:\n{url}"
                ).format(error=self._verification_message(str(exc) if isinstance(exc, VerificationError) else "network"), url=html_url),
            )
            return
        QApplication.quit()
