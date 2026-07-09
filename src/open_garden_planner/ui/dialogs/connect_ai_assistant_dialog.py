"""Connect-your-AI-assistant dialog (US-D1.6).

Thin Qt shell over ``services/ai_client_onboarding.py`` — shows the Agent
API's connect URL and, per detected client, either a one-click "Add to …"
button (Cursor, Claude Code) or a guided copy-paste snippet (Claude Desktop,
and any client without automatic support). All prose here is UI copy and
goes through ``self.tr()``; the URL/server name/snippet payloads are agent
data and are never translated (mirrors ADR-033's "MCP tool/resource
descriptions are English" precedent).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services import ai_client_onboarding as onboarding


class ConnectAiAssistantDialog(QDialog):
    """Shows the Agent API connect URL and helps register it with AI clients."""

    def __init__(self, server_url: str | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Connect Your AI Assistant"))
        self.setMinimumSize(560, 480)
        self._server_url = server_url
        self._status_label = QLabel("")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        if self._server_url is None:
            self._setup_disabled_ui(layout)
            return

        url_group = QGroupBox(self.tr("Connect URL"))
        url_layout = QHBoxLayout(url_group)
        url_label = QLabel(self._server_url)
        url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        url_layout.addWidget(url_label, 1)
        copy_btn = QPushButton(self.tr("Copy URL"))
        copy_btn.clicked.connect(self._on_copy_url)
        url_layout.addWidget(copy_btn)
        layout.addWidget(url_group)

        layout.addWidget(QLabel(self.tr("Transport: Streamable HTTP")))

        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        for client in onboarding.detect_clients():
            layout.addWidget(self._build_client_row(client))

        layout.addStretch()
        layout.addLayout(self._build_close_row())

    def _setup_disabled_ui(self, layout: QVBoxLayout) -> None:
        warning = QLabel(
            self.tr(
                "The Agent API is currently disabled, so no AI assistant can "
                "connect yet. Enable it in Preferences → Agent API first."
            )
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)
        layout.addStretch()
        layout.addLayout(self._build_close_row())

    def _build_close_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton(self.tr("Close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        return row

    def _build_client_row(self, client: onboarding.ClientInfo) -> QWidget:
        group = QGroupBox(client.display_name)
        v = QVBoxLayout(group)

        status_text = self.tr("Detected") if client.detected else self.tr("Not detected")
        v.addWidget(QLabel(status_text))

        actions_row = QHBoxLayout()
        if client.install_method != "manual":
            add_btn = QPushButton(self.tr("Add to {client}").format(client=client.display_name))
            add_btn.setEnabled(client.detected)
            add_btn.clicked.connect(lambda _checked=False, c=client: self._on_add_clicked(c))
            actions_row.addWidget(add_btn)

        snippet_toggle = QPushButton(self.tr("Show manual snippet"))
        snippet_toggle.setCheckable(True)
        actions_row.addWidget(snippet_toggle)
        actions_row.addStretch()
        v.addLayout(actions_row)

        note_label = QLabel(self._manual_note_for(client.client_id))
        note_label.setWordWrap(True)
        note_label.setVisible(False)
        v.addWidget(note_label)

        snippet_text = QPlainTextEdit()
        snippet_text.setReadOnly(True)
        assert self._server_url is not None
        snippet_text.setPlainText(
            onboarding.snippet_for_client(client.client_id, url=self._server_url)
        )
        snippet_text.setMaximumHeight(90)
        snippet_text.setVisible(False)
        v.addWidget(snippet_text)

        snippet_toggle.toggled.connect(note_label.setVisible)
        snippet_toggle.toggled.connect(snippet_text.setVisible)

        return group

    def _manual_note_for(self, client_id: str) -> str:
        notes = {
            "cursor": self.tr("Add this to your global Cursor MCP config file:"),
            "claude_code": self.tr("Run this command in a terminal:"),
            "claude_desktop": self.tr(
                "In Claude Desktop, go to Settings → Connectors → "
                '"Add custom connector" and paste this URL:'
            ),
        }
        return notes.get(client_id, "")

    def _on_copy_url(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None or self._server_url is None:
            return
        clipboard.setText(self._server_url)
        self._status_label.setText(self.tr("URL copied to clipboard."))

    def _on_add_clicked(self, client: onboarding.ClientInfo) -> None:
        if self._server_url is None:
            return
        try:
            result = onboarding.install_to_client(client.client_id, url=self._server_url)
        except Exception as exc:  # noqa: BLE001 — UI trust boundary: a failed
            # install must never crash the app, even if a future client
            # strategy raises something install_to_client doesn't yet guard.
            self._status_label.setText(
                self.tr("Could not add to {client}: {detail}").format(
                    client=client.display_name, detail=str(exc)
                )
            )
            return
        if result.success:
            self._status_label.setText(
                self.tr("Added to {client}.").format(client=client.display_name)
            )
        else:
            self._status_label.setText(
                self.tr("Could not add to {client}: {detail}").format(
                    client=client.display_name, detail=result.detail
                )
            )
