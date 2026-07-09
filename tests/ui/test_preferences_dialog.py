"""UI tests for PreferencesDialog."""

# ruff: noqa: ARG002

import pytest

from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog


class TestPreferencesDialog:
    """Tests for PreferencesDialog widget state."""

    @pytest.fixture()
    def dialog(self, qtbot):
        dlg = PreferencesDialog()
        qtbot.addWidget(dlg)
        return dlg

    def test_dialog_creates_without_error(self, qtbot) -> None:
        """PreferencesDialog can be instantiated without error."""
        dlg = PreferencesDialog()
        qtbot.addWidget(dlg)
        assert dlg is not None

    def test_has_trefle_token_field(self, dialog) -> None:
        """Dialog exposes a Trefle API token input."""
        assert hasattr(dialog, "_trefle_token")

    def test_has_perenual_key_field(self, dialog) -> None:
        """Dialog exposes a Perenual API key input."""
        assert hasattr(dialog, "_perenual_key")

    def test_trefle_field_is_empty_by_default(self, dialog) -> None:
        """Trefle token field is empty when no key is configured."""
        # QSettings is isolated to 'cofade_test' in conftest — no real key
        assert dialog._trefle_token.text() == ""

    def test_trefle_token_accepts_text(self, dialog, qtbot) -> None:
        """Typing into the Trefle token field updates the value."""
        dialog._trefle_token._line_edit.setText("test-token-123")
        assert dialog._trefle_token.text() == "test-token-123"


class TestConnectAiAssistantEntryPoint:
    """US-D1.6: the Preferences 'Connect AI Assistant…' button must never
    register an unsaved (possibly not-yet-running) port/enabled state."""

    @pytest.fixture()
    def dialog(self, qtbot):
        dlg = PreferencesDialog()
        qtbot.addWidget(dlg)
        return dlg

    def test_button_exists_and_toggles_with_checkbox(self, dialog) -> None:
        assert hasattr(dialog, "_agent_api_connect_btn")
        dialog._agent_api_check.setChecked(False)
        assert dialog._agent_api_connect_btn.isEnabled() is False
        dialog._agent_api_check.setChecked(True)
        assert dialog._agent_api_connect_btn.isEnabled() is True

    def test_unsaved_port_change_warns_instead_of_opening_dialog(
        self, dialog, monkeypatch
    ) -> None:
        opened = []
        monkeypatch.setattr(
            "open_garden_planner.ui.dialogs.connect_ai_assistant_dialog."
            "ConnectAiAssistantDialog",
            lambda *a: opened.append(a),
        )
        warned = []
        monkeypatch.setattr(
            "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.information",
            lambda *a: warned.append(a),
        )

        dialog._agent_api_check.setChecked(True)
        dialog._agent_api_port_spin.setValue(dialog._agent_api_port_spin.value() + 1)
        dialog._on_connect_ai_assistant()

        assert warned
        assert not opened

    def test_saved_state_opens_dialog_with_running_url(self, dialog, monkeypatch) -> None:
        from open_garden_planner.app.settings import get_settings

        # conftest's autouse fixture forces agent_api_enabled=False for tests
        # (so the suite never starts a real server) — persist a matching
        # "saved" enabled+port pair explicitly rather than relying on defaults.
        settings = get_settings()
        settings.agent_api_enabled = True
        settings.agent_api_port = 9191
        dialog._agent_api_check.setChecked(settings.agent_api_enabled)
        dialog._agent_api_port_spin.setValue(settings.agent_api_port)

        captured = {}

        class _FakeDialog:
            def __init__(self, url, _parent):
                captured["url"] = url

            def exec(self):
                return None

        monkeypatch.setattr(
            "open_garden_planner.ui.dialogs.connect_ai_assistant_dialog."
            "ConnectAiAssistantDialog",
            _FakeDialog,
        )

        dialog._on_connect_ai_assistant()

        assert captured["url"] == f"http://127.0.0.1:{settings.agent_api_port}/mcp"
