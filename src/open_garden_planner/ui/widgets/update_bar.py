"""Dismissible update-notification bar for US-8.3.

Shown at the top of the main window when a newer GitHub release is available.
"""

import logging
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
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
        self._setup_ui()
        self.hide()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_update(self, tag_name: str, body: str, download_url: str) -> None:
        """Populate and display the bar for a specific update.

        Args:
            tag_name:     Version tag, e.g. ``"v1.6.0"``.
            body:         Release notes snippet (≤ 300 chars).
            download_url: Direct URL to the ``*-Setup.exe`` asset, or ``""``
                          if no installer asset was found.
        """
        self._tag_name = tag_name
        self._download_url = download_url

        msg = self.tr("A new version ({version}) is available.").format(version=tag_name)
        if body:
            msg += "  " + body.split("\n")[0][:100]
        self._label.setText(msg)
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
        self._label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
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
            "  background-color: rgba(255,255,255,0.20);"
            "  color: white;"
            "  border: 1px solid rgba(255,255,255,0.50);"
            "  border-radius: 4px;"
            "  padding: 2px 10px;"
            "}"
            "#UpdateBar QPushButton:hover {"
            "  background-color: rgba(255,255,255,0.35);"
            "}"
        )

    def _on_skip(self) -> None:
        self.skip_version_requested.emit(self._tag_name)
        self.hide()

    def _on_download(self) -> None:
        """Download the installer to a temp dir, launch it, then quit the app."""
        if not self._download_url:
            return

        parent = self.window()

        # Ask for confirmation
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
            0,
            parent,
        )
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        try:
            urllib.request.urlretrieve(self._download_url, dest)  # noqa: S310
        except Exception as exc:
            progress.close()
            QMessageBox.critical(
                parent,
                self.tr("Download Failed"),
                self.tr("Could not download the installer:\n{error}").format(error=str(exc)),
            )
            return

        progress.close()

        try:
            subprocess.Popen([str(dest)], close_fds=True)  # noqa: S603
        except Exception as exc:
            QMessageBox.critical(
                parent,
                self.tr("Launch Failed"),
                self.tr("Could not launch the installer:\n{error}").format(error=str(exc)),
            )
            return

        QApplication.quit()
