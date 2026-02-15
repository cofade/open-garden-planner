"""Preferences dialog for application settings."""

import logging

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


class _PasswordLineEdit(QWidget):
    """A line edit with a show/hide toggle button for password-style input."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._line_edit = QLineEdit()
        self._line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._line_edit)

        self._toggle_btn = QPushButton(self.tr("Show"))
        self._toggle_btn.setFixedWidth(60)
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.toggled.connect(self._on_toggle)
        layout.addWidget(self._toggle_btn)

    def _on_toggle(self, checked: bool) -> None:
        if checked:
            self._line_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_btn.setText(self.tr("Hide"))
        else:
            self._line_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_btn.setText(self.tr("Show"))

    def text(self) -> str:
        return self._line_edit.text()

    def setText(self, text: str) -> None:
        self._line_edit.setText(text)

    def setPlaceholderText(self, text: str) -> None:
        self._line_edit.setPlaceholderText(text)


class PreferencesDialog(QDialog):
    """Preferences dialog with API Keys configuration.

    Allows users to enter and persist their plant API credentials
    via QSettings so they don't need environment variables.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Preferences"))
        self.setMinimumSize(550, 400)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Info label
        info_label = QLabel(
            self.tr(
                "Configure your plant database API keys below. "
                "Keys are stored locally and never shared. "
                "Environment variables (.env) are used as fallback."
            )
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # --- Trefle ---
        trefle_group = QGroupBox(self.tr("Trefle (trefle.io)"))
        trefle_layout = QFormLayout(trefle_group)

        self._trefle_token = _PasswordLineEdit()
        self._trefle_token.setPlaceholderText(self.tr("Enter Trefle API token..."))
        trefle_layout.addRow(self.tr("API Token:"), self._trefle_token)

        trefle_links = QHBoxLayout()
        trefle_signup = QPushButton(self.tr("Get API Key"))
        trefle_signup.setToolTip("https://trefle.io/users/sign_up")
        trefle_signup.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://trefle.io/users/sign_up"))
        )
        trefle_test = QPushButton(self.tr("Test"))
        trefle_test.clicked.connect(lambda: self._test_api("trefle"))
        trefle_links.addWidget(trefle_signup)
        trefle_links.addWidget(trefle_test)
        trefle_links.addStretch()
        trefle_layout.addRow("", trefle_links)

        layout.addWidget(trefle_group)

        # --- Perenual ---
        perenual_group = QGroupBox(self.tr("Perenual (perenual.com)"))
        perenual_layout = QFormLayout(perenual_group)

        self._perenual_key = _PasswordLineEdit()
        self._perenual_key.setPlaceholderText(self.tr("Enter Perenual API key..."))
        perenual_layout.addRow(self.tr("API Key:"), self._perenual_key)

        perenual_links = QHBoxLayout()
        perenual_signup = QPushButton(self.tr("Get API Key"))
        perenual_signup.setToolTip("https://perenual.com/docs/api")
        perenual_signup.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://perenual.com/docs/api"))
        )
        perenual_test = QPushButton(self.tr("Test"))
        perenual_test.clicked.connect(lambda: self._test_api("perenual"))
        perenual_links.addWidget(perenual_signup)
        perenual_links.addWidget(perenual_test)
        perenual_links.addStretch()
        perenual_layout.addRow("", perenual_links)

        layout.addWidget(perenual_group)

        # --- Permapeople ---
        permapeople_group = QGroupBox(self.tr("Permapeople (permapeople.org)"))
        permapeople_layout = QFormLayout(permapeople_group)

        self._permapeople_key_id = _PasswordLineEdit()
        self._permapeople_key_id.setPlaceholderText(self.tr("Enter Key ID..."))
        permapeople_layout.addRow(self.tr("Key ID:"), self._permapeople_key_id)

        self._permapeople_key_secret = _PasswordLineEdit()
        self._permapeople_key_secret.setPlaceholderText(self.tr("Enter Key Secret..."))
        permapeople_layout.addRow(self.tr("Key Secret:"), self._permapeople_key_secret)

        permapeople_links = QHBoxLayout()
        permapeople_signup = QPushButton(self.tr("Get API Key"))
        permapeople_signup.setToolTip("https://permapeople.org/knowledgebase/api-docs.html")
        permapeople_signup.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://permapeople.org/knowledgebase/api-docs.html")
            )
        )
        permapeople_test = QPushButton(self.tr("Test"))
        permapeople_test.clicked.connect(lambda: self._test_api("permapeople"))
        permapeople_links.addWidget(permapeople_signup)
        permapeople_links.addWidget(permapeople_test)
        permapeople_links.addStretch()
        permapeople_layout.addRow("", permapeople_links)

        layout.addWidget(permapeople_group)

        layout.addStretch()

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton(self.tr("Save"))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_and_accept)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _load_settings(self) -> None:
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        self._trefle_token.setText(settings.trefle_api_token)
        self._perenual_key.setText(settings.perenual_api_key)
        self._permapeople_key_id.setText(settings.permapeople_key_id)
        self._permapeople_key_secret.setText(settings.permapeople_key_secret)

    def _save_and_accept(self) -> None:
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        settings.trefle_api_token = self._trefle_token.text().strip()
        settings.perenual_api_key = self._perenual_key.text().strip()
        settings.permapeople_key_id = self._permapeople_key_id.text().strip()
        settings.permapeople_key_secret = self._permapeople_key_secret.text().strip()
        settings.sync()
        self.accept()

    def _test_api(self, api_name: str) -> None:
        """Test connectivity for the given API using current field values."""
        from open_garden_planner.services.plant_api.perenual_client import PerenualClient
        from open_garden_planner.services.plant_api.permapeople_client import PermapeopleClient
        from open_garden_planner.services.plant_api.trefle_client import TrefleClient

        try:
            if api_name == "trefle":
                token = self._trefle_token.text().strip()
                if not token:
                    QMessageBox.warning(
                        self, self.tr("Test"), self.tr("Please enter a Trefle API token first.")
                    )
                    return
                client = TrefleClient(api_token=token)
            elif api_name == "perenual":
                key = self._perenual_key.text().strip()
                if not key:
                    QMessageBox.warning(
                        self, self.tr("Test"), self.tr("Please enter a Perenual API key first.")
                    )
                    return
                client = PerenualClient(api_key=key)
            elif api_name == "permapeople":
                key_id = self._permapeople_key_id.text().strip()
                key_secret = self._permapeople_key_secret.text().strip()
                if not key_id or not key_secret:
                    QMessageBox.warning(
                        self,
                        self.tr("Test"),
                        self.tr("Please enter both Permapeople Key ID and Key Secret."),
                    )
                    return
                client = PermapeopleClient(key_id=key_id, key_secret=key_secret)
            else:
                return

            self.setCursor(Qt.CursorShape.WaitCursor)
            available = client.is_available()
            self.unsetCursor()

            if available:
                QMessageBox.information(
                    self,
                    self.tr("Test Successful"),
                    self.tr("Connection to {api} is working.").format(api=client.name),
                )
            else:
                QMessageBox.warning(
                    self,
                    self.tr("Test Failed"),
                    self.tr(
                        "Could not connect to {api}. "
                        "Please check your credentials."
                    ).format(api=client.name),
                )
        except Exception as e:
            self.unsetCursor()
            logger.warning(f"API test failed for {api_name}: {e}")
            QMessageBox.critical(
                self,
                self.tr("Test Error"),
                self.tr("Error testing {api}: {error}").format(
                    api=api_name.capitalize(), error=str(e)
                ),
            )
