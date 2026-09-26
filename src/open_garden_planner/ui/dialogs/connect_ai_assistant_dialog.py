"""Connect-your-AI-assistant dialog (US-D1.6, generalized by issue #366).

Thin Qt shell over ``services/ai_client_onboarding.py``. Every client row is
built from the service's ``TARGETS`` registry, so a new client appears here
with no change to this file — the dialog knows nothing about any specific
vendor.

Three things this dialog owns (the service owns the mechanics):

* **The read-only URL is the default hand-out.** The connect URL can carry the
  Agent API's D2 write token, and pasting that into an assistant chat publishes
  the credential to whatever stores the transcript. So "Copy read-only URL" is
  the primary button, and the write URL sits behind a separate, explicitly
  worded action that says the token is in it.
* **A generic fallback that is always present**, even when nothing is
  detected, so a client OGP has never heard of is still one paste away.
* **Honest per-client state** — detected / registered / stale — instead of a
  button that silently re-registers nothing.

All prose here is UI copy and goes through ``self.tr()``; the URL, server
name, and snippet payloads are agent data and are never translated (mirrors
ADR-033's "MCP tool/resource descriptions are English" precedent — the same
reason client ``display_name``s stay English).

Client rows sit inside a ``QScrollArea`` so revealing a manual snippet scrolls
it into view instead of pushing the Close button off a fixed-size dialog
(issue #253) — and now also so the larger registry still fits.
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
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services import ai_client_onboarding as onboarding


class ConnectAiAssistantDialog(QDialog):
    """Shows the Agent API connect URL and helps register it with AI clients."""

    def __init__(
        self,
        server_url: str | None,
        parent: QWidget | None = None,
        *,
        token: str | None = None,
        enabled_in_settings: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Connect Your AI Assistant"))
        self.setMinimumSize(560, 480)
        self._server_url = server_url
        # A missing URL has TWO causes and they need different advice (#291):
        # the feature is switched off, or it is switched ON but the server
        # failed to start. Telling someone to enable an already-ticked box —
        # which is exactly what the old single message did — is a dead end.
        self._enabled_in_settings = enabled_in_settings
        # Present only when AI editing is enabled AND the server is live — the
        # caller (application.agent_api_write_token) enforces both. When set,
        # the client is registered to send it so the D2 write tools are
        # reachable. It is NEVER part of the default copy action (issue #366).
        self._token = token
        self._status_label = QLabel("")
        # Set in _setup_ui's enabled branch; the client rows scroll so a
        # revealed snippet can be scrolled into view (issue #253).
        self._clients_scroll: QScrollArea | None = None
        self._setup_ui()

    # -- layout ------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        if self._server_url is None:
            self._setup_disabled_ui(layout)
            return

        layout.addWidget(self._build_url_group())
        layout.addWidget(QLabel(self.tr("Transport: Streamable HTTP")))
        layout.addWidget(self._build_editing_note())

        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Client rows live in a scroll area so revealing a manual snippet
        # grows the scrollable region (and scrolls it into view) instead of
        # pushing the Close button off the bottom of a fixed-size dialog.
        clients_container = QWidget()
        clients_layout = QVBoxLayout(clients_container)
        clients_layout.setContentsMargins(0, 0, 0, 0)
        for client in onboarding.detect_clients():
            clients_layout.addWidget(self._build_client_row(client))
        # The vendor-agnostic path is ALWAYS present — it is what makes the
        # registry an optimisation rather than a gate, and it is the only
        # route for a client added after this release.
        clients_layout.addWidget(self._build_generic_group())
        clients_layout.addStretch()

        self._clients_scroll = QScrollArea()
        self._clients_scroll.setWidgetResizable(True)
        self._clients_scroll.setWidget(clients_container)
        layout.addWidget(self._clients_scroll, 1)

        layout.addLayout(self._build_close_row())

    def _build_url_group(self) -> QGroupBox:
        """The connect URL, with the READ-ONLY copy as the default action."""
        assert self._server_url is not None
        group = QGroupBox(self.tr("Connect URL"))
        row = QHBoxLayout(group)

        # Read-only by default: a token-bearing URL pasted into a chat leaks
        # the write credential into the transcript (issue #366).
        label = QLabel(onboarding.read_only_url(self._server_url))
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(label, 1)

        copy_read = QPushButton(self.tr("Copy read-only URL"))
        copy_read.clicked.connect(self._on_copy_read_only_url)
        row.addWidget(copy_read)

        if self._token:
            copy_write = QPushButton(self.tr("Copy URL with edit token"))
            copy_write.setToolTip(
                self.tr(
                    "This URL contains the token that lets an AI assistant edit "
                    "your plan. Do not paste it into a shared chat."
                )
            )
            copy_write.clicked.connect(self._on_copy_write_url)
            row.addWidget(copy_write)

        return group

    def _build_editing_note(self) -> QLabel:
        note = QLabel(
            self.tr(
                "AI editing is ON — clients added here can modify your plan. "
                "Each edit is a single undo step. Turn it off in "
                "Preferences → Agent API."
            )
            if self._token
            else self.tr(
                "Clients added here can read your plan but not edit it. To allow "
                "editing, enable it in Preferences → Agent API."
            )
        )
        note.setWordWrap(True)
        return note

    def _setup_disabled_ui(self, layout: QVBoxLayout) -> None:
        if self._enabled_in_settings:
            # Enabled but no live server: it failed to start (a port conflict,
            # or the frozen-build startup failure of #291). Never tell the user
            # to enable something whose box is already ticked.
            message = self.tr(
                "The Agent API is enabled, but its server is not running — it "
                "failed to start. The port may be in use by another program or "
                "a second copy of this app. Try a different port in "
                "Preferences → Agent API, then restart the application."
            )
        else:
            message = self.tr(
                "The Agent API is currently disabled, so no AI assistant can "
                "connect yet. Enable it in Preferences → Agent API first."
            )
        warning = QLabel(message)
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

    # -- per-client rows ---------------------------------------------------

    def _build_client_row(self, client: onboarding.ClientInfo) -> QWidget:
        group = QGroupBox(client.display_name)
        v = QVBoxLayout(group)

        # Kept, not discarded: the row's state must be able to change after an
        # Add, or "registered" is only ever true for the first second the
        # dialog is open.
        state_label = QLabel(self._state_text(client))
        v.addWidget(state_label)

        if not client.supports_local_http:
            # Detection-only AND unreachable: this client can't connect to a
            # localhost server at all. Show the honest redirect note only — no
            # add button, and no snippet (there is no config the user could
            # paste that would make it work). See issue #253 / ADR-035.
            note_label = QLabel(self._manual_note_for(client.client_id))
            note_label.setWordWrap(True)
            v.addWidget(note_label)
            return group

        actions_row = QHBoxLayout()
        if client.install_method != "manual":
            add_btn = QPushButton(self.tr("Add to {client}").format(client=client.display_name))
            add_btn.setEnabled(client.detected)
            add_btn.clicked.connect(
                lambda _checked=False, c=client, b=add_btn, s=state_label: (
                    self._on_add_clicked(c, b, s)
                )
            )
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
            onboarding.snippet_for_client(
                client.client_id, url=self._server_url, token=self._token
            )
        )
        # The snippet needs several lines; a 90px cap clipped it behind the
        # Close row (issue #253). Give it room and let the enclosing scroll
        # area handle any overflow rather than the dialog itself.
        snippet_text.setMinimumHeight(110)
        snippet_text.setMaximumHeight(240)
        snippet_text.setVisible(False)
        v.addWidget(snippet_text)

        def _reveal(checked: bool) -> None:
            note_label.setVisible(checked)
            snippet_text.setVisible(checked)
            if checked:
                self.adjustSize()
                if self._clients_scroll is not None:
                    self._clients_scroll.ensureWidgetVisible(snippet_text)

        snippet_toggle.toggled.connect(_reveal)

        return group

    def _build_generic_group(self) -> QWidget:
        """The vendor-agnostic route, always present (issue #366).

        Without it, "OGP has never heard of your client" means "paste a token
        into a chat and hope" — which is exactly the failure this work exists
        to close.
        """
        assert self._server_url is not None
        group = QGroupBox(self.tr("Other AI clients"))
        v = QVBoxLayout(group)

        intro = QLabel(
            self.tr(
                "No button for your client? Use these with any MCP client that "
                "reads a JSON config."
            )
        )
        intro.setWordWrap(True)
        v.addWidget(intro)

        # Read-only by construction: the service takes no token, so a live
        # write credential cannot end up on text the user is invited to paste
        # somewhere public.
        snippets = onboarding.generic_snippets(url=self._server_url)

        json_note = QLabel(
            self.tr('Add this to your client\'s "mcpServers" config:')
        )
        json_note.setWordWrap(True)
        v.addWidget(json_note)
        v.addWidget(self._snippet_box(snippets["json"]))

        cli_note = QLabel(self.tr("Or run this command:"))
        cli_note.setWordWrap(True)
        v.addWidget(cli_note)
        v.addWidget(self._snippet_box(snippets["cli"]))

        url_note = QLabel(
            self.tr("Or paste this read-only URL into your client:")
        )
        url_note.setWordWrap(True)
        v.addWidget(url_note)
        v.addWidget(self._snippet_box(snippets["url"]))

        return group

    def _snippet_box(self, text: str) -> QPlainTextEdit:
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setPlainText(text)
        box.setMinimumHeight(80)
        box.setMaximumHeight(200)
        return box

    # -- state text -------------------------------------------------------

    def _state_text(self, client: onboarding.ClientInfo) -> str:
        """Detected / registered / stale, in plain language.

        "Stale" is the case that motivated issue #366: a hand-pasted or
        token-rotated entry looks perfectly fine in the config and silently
        cannot connect, which is a miserable thing to debug.
        """
        if not client.detected:
            return self.tr("Not detected")
        if client.registered_url is None:
            return self.tr("Detected — not registered yet")
        assert self._server_url is not None
        # `is_stale` owns the rule, and it treats a READ-ONLY registration as
        # current. Comparing the full write-capable URL alone would report a
        # deliberately read-only client as stale forever, with the write
        # credential as the only offered remedy — and a rule living in two
        # places is a rule that will disagree with itself.
        expected = onboarding.url_with_token(self._server_url, self._token)
        if not onboarding.is_stale(client.client_id, expected):
            return self.tr("Detected — registered and up to date")
        return self.tr(
            "Detected — registered with a different address; add again to update"
        )

    def _manual_note_for(self, client_id: str) -> str:
        """Where this client's config lives, in prose.

        Keyed by id and completeness-tested, because a client added to the
        registry without a note here would show an empty string — the failure
        mode a dict lookup with a silent default invites.
        """
        notes = {
            "cursor": self.tr("Add this to your global Cursor MCP config file:"),
            "claude_code": self.tr("Merge this into your ~/.claude.json file:"),
            "opencode": self.tr(
                "Merge this into your ~/.config/opencode/opencode.jsonc file:"
            ),
            "codex": self.tr("Append this to your ~/.codex/config.toml file:"),
            "gemini": self.tr(
                "Add this to your ~/.gemini/config/mcp_config.json file:"
            ),
            "claude_desktop": self.tr(
                "Claude Desktop can't connect to a local server like this one — "
                "its connectors are reached from Anthropic's cloud and reject "
                "localhost URLs. Use Claude Code or Cursor for this local Agent "
                "API instead."
            ),
        }
        return notes.get(client_id, "")

    # -- actions ----------------------------------------------------------

    def _on_copy_read_only_url(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None or self._server_url is None:
            return
        clipboard.setText(onboarding.read_only_url(self._server_url))
        self._status_label.setText(self.tr("Read-only URL copied to clipboard."))

    def _on_copy_write_url(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is None or self._server_url is None:
            return
        clipboard.setText(onboarding.url_with_token(self._server_url, self._token))
        self._status_label.setText(
            self.tr(
                "URL with the edit token copied. Anyone holding it can change "
                "your plan — do not share it in a chat or a public document."
            )
        )

    def _on_add_clicked(
        self,
        client: onboarding.ClientInfo,
        button: QPushButton,
        state_label: QLabel,
    ) -> None:
        if self._server_url is None:
            return
        # Claude Code's install can shell out to the `claude` CLI (up to three
        # blocking subprocess calls, ~15s timeout each) — give visible feedback
        # for the whole call, mirroring preferences_dialog._test_api's
        # setCursor/unsetCursor around its own blocking network call.
        button.setEnabled(False)
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            try:
                result = onboarding.install_to_client(
                    client.client_id, url=self._server_url, token=self._token
                )
            except Exception as exc:  # noqa: BLE001 — UI trust boundary: a failed
                # install must never crash the app, even if a future client
                # strategy raises something install_to_client doesn't yet guard.
                self._status_label.setText(
                    self.tr("Could not add to {client}: {detail}").format(
                        client=client.display_name, detail=str(exc)
                    )
                )
                return
        finally:
            self.unsetCursor()
            button.setEnabled(client.detected)

        if result.success:
            # Re-read the row's state from disk, so a successful Add is
            # reflected in the row itself and not only in the status line.
            refreshed = next(
                (
                    c
                    for c in onboarding.detect_clients()
                    if c.client_id == client.client_id
                ),
                client,
            )
            state_label.setText(self._state_text(refreshed))
            if client.requires_restart:
                # A user-scope MCP server is only read at session start, so
                # tell the user to reconnect rather than leaving them to wonder
                # why a running session doesn't see it (issue #253).
                self._status_label.setText(
                    self.tr(
                        "Added to {client}. Start a new {client} session (or "
                        "restart it) to pick up the change."
                    ).format(client=client.display_name)
                )
            else:
                self._status_label.setText(
                    self.tr("Added to {client}.").format(client=client.display_name)
                )
            # `result.detail` carries the path that was written and, for a merge,
            # where the previous contents were backed up. The success branch
            # above deliberately says nothing about paths — but the merge DOES
            # make a `.bak` next to a config file in the user's home directory,
            # and a backup that is made but never named is litter they cannot
            # find. (Senior-review round 5: the field was populated and
            # documented in three places while the dialog ignored it, so the
            # user's experience was unchanged from before the fix.) A CLI route
            # puts the command's own output here instead, which is also worth
            # showing.
            if result.detail:
                self._status_label.setText(
                    self.tr("{summary} {detail}").format(
                        summary=self._status_label.text(), detail=result.detail
                    )
                )
        else:
            self._status_label.setText(
                self.tr("Could not add to {client}: {detail}").format(
                    client=client.display_name, detail=result.detail
                )
            )
