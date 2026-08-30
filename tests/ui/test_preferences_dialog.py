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

    def test_has_google_maps_key_field(self, dialog) -> None:
        """Dialog exposes a Google Maps API key input."""
        assert hasattr(dialog, "_google_maps_key")

    def test_trefle_field_is_empty_by_default(self, dialog) -> None:
        """Trefle token field is empty when no key is configured."""
        # QSettings is isolated to 'cofade_test' in conftest — no real key
        assert dialog._trefle_token.text() == ""

    def test_trefle_token_accepts_text(self, dialog, qtbot) -> None:
        """Typing into the Trefle token field updates the value."""
        dialog._trefle_token._line_edit.setText("test-token-123")
        assert dialog._trefle_token.text() == "test-token-123"

    def test_google_maps_key_save_and_clear_round_trip(self, dialog, qtbot) -> None:
        """Google Maps key persistence follows the existing Preferences save path."""
        from open_garden_planner.app.settings import get_settings

        dialog._google_maps_key.setText("preference-key")
        dialog._save_and_accept()
        assert get_settings().google_maps_api_key == "preference-key"

        restored = PreferencesDialog()
        qtbot.addWidget(restored)
        assert restored._google_maps_key.text() == "preference-key"

        restored._google_maps_key.setText("")
        restored._save_and_accept()
        assert get_settings().google_maps_api_key == ""

    def test_google_maps_environment_fallback_is_not_copied_to_field(
        self, qtbot, monkeypatch
    ) -> None:
        """An environment key is shown as a hint but is never written to the field."""
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "environment-key")
        dlg = PreferencesDialog()
        qtbot.addWidget(dlg)

        assert dlg._google_maps_key.text() == ""
        assert "OGP_GOOGLE_MAPS_KEY" in dlg._google_maps_key._line_edit.placeholderText()


class _FakeParentWindow:
    """Stands in for GardenPlannerApp: agent_api_running_url()/agent_api_write_token()."""

    def __init__(
        self, running_url: str | None, write_token: str | None = None
    ) -> None:
        self._running_url = running_url
        self._write_token = write_token

    def agent_api_running_url(self) -> str | None:
        return self._running_url

    def agent_api_write_token(self) -> str | None:
        return self._write_token


class TestConnectAiAssistantEntryPoint:
    """US-D1.6: the Preferences 'Connect AI Assistant…' button must ask
    whether the server is actually *running* — never reconstruct a URL from
    settings/widget state, which can look fine while the server itself
    failed to start (e.g. a port conflict at launch)."""

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

    def _open_and_capture_url(self, dialog, monkeypatch) -> dict:
        captured = {}

        class _FakeDialog:
            def __init__(self, url, _parent, *, token=None, enabled_in_settings=False):
                captured["url"] = url
                captured["token"] = token
                captured["enabled_in_settings"] = enabled_in_settings

            def exec(self):
                return None

        monkeypatch.setattr(
            "open_garden_planner.ui.dialogs.connect_ai_assistant_dialog."
            "ConnectAiAssistantDialog",
            _FakeDialog,
        )
        dialog._on_connect_ai_assistant()
        return captured

    def test_no_parent_window_passes_none(self, dialog, monkeypatch) -> None:
        """The `dialog` fixture builds PreferencesDialog with no parent at all
        (as tests do) — must degrade to None, not raise."""
        assert dialog.parent() is None
        captured = self._open_and_capture_url(dialog, monkeypatch)
        assert captured["url"] is None

    def test_server_not_running_passes_none_even_if_settings_look_fine(
        self, dialog, monkeypatch
    ) -> None:
        """The exact bug this fixes: settings/widgets can look perfectly
        configured while the server itself never started (PortInUseError at
        launch) — the dialog must still get None, not a reconstructed URL."""
        monkeypatch.setattr(dialog, "parent", lambda: _FakeParentWindow(None))
        dialog._agent_api_check.setChecked(True)
        dialog._agent_api_port_spin.setValue(8765)

        captured = self._open_and_capture_url(dialog, monkeypatch)

        assert captured["url"] is None

    def test_server_running_passes_its_url(self, dialog, monkeypatch) -> None:
        monkeypatch.setattr(
            dialog, "parent", lambda: _FakeParentWindow("http://127.0.0.1:9191/mcp")
        )

        captured = self._open_and_capture_url(dialog, monkeypatch)

        assert captured["url"] == "http://127.0.0.1:9191/mcp"

    def test_enabled_but_dead_server_is_distinguishable_from_disabled(
        self, dialog, monkeypatch
    ) -> None:
        """Issue #291: a missing URL has two causes and they need different
        advice. Telling a user to tick an already-ticked box is a dead end, so
        the dialog is told whether the feature is enabled, not just that there
        is no URL."""
        monkeypatch.setattr(dialog, "parent", lambda: _FakeParentWindow(None))

        dialog._agent_api_check.setChecked(True)
        captured = self._open_and_capture_url(dialog, monkeypatch)
        assert captured["url"] is None
        assert captured["enabled_in_settings"] is True, (
            "enabled-but-not-running must be distinguishable from disabled"
        )

        dialog._agent_api_check.setChecked(False)
        captured = self._open_and_capture_url(dialog, monkeypatch)
        assert captured["enabled_in_settings"] is False


class TestAgentApiTokenField:
    """US-D2.0: the token field must never let Copy silently hand out a value
    the running server doesn't actually accept. Regenerate persists to
    settings immediately, but the running server keeps validating whatever it
    was started with until a restart (Save) — so a visible note covers the gap
    instead of Copy/the field diverging silently."""

    @pytest.fixture()
    def dialog(self, qtbot):
        dlg = PreferencesDialog()
        qtbot.addWidget(dlg)
        dlg._agent_api_check.setChecked(True)
        dlg._agent_api_writes_check.setChecked(True)
        return dlg

    def test_no_note_when_running_token_matches_settings(self, dialog, monkeypatch) -> None:
        from open_garden_planner.app.settings import get_settings

        current = get_settings().agent_api_token
        monkeypatch.setattr(
            dialog, "parent", lambda: _FakeParentWindow("http://127.0.0.1:8765/mcp", current)
        )

        dialog._refresh_agent_api_token_field()

        assert dialog._agent_api_token_edit.text() == current
        # isVisible() is compound with the (never-shown) top-level dialog and
        # would always read False here; isHidden() reflects setVisible()
        # directly regardless of ancestor state.
        assert dialog._agent_api_token_pending_note.isHidden() is True

    def test_note_shown_when_running_token_differs_after_regenerate(
        self, dialog, monkeypatch
    ) -> None:
        """The exact scenario the reviewer flagged: Regenerate persists a new
        settings token immediately, but a still-running server was started
        with the old one — Copy would hand out a token that doesn't work yet."""
        stale_running_token = "token-the-live-server-still-accepts"
        monkeypatch.setattr(
            dialog,
            "parent",
            lambda: _FakeParentWindow("http://127.0.0.1:8765/mcp", stale_running_token),
        )

        dialog._on_regenerate_agent_api_token()

        assert dialog._agent_api_token_edit.text() != stale_running_token
        # isVisible() is compound with the (never-shown) top-level dialog and
        # would always read False here; isHidden() reflects setVisible()
        # directly regardless of ancestor state.
        assert dialog._agent_api_token_pending_note.isHidden() is False

    def test_no_note_when_no_server_running(self, dialog, monkeypatch) -> None:
        monkeypatch.setattr(dialog, "parent", lambda: _FakeParentWindow(None, None))

        dialog._refresh_agent_api_token_field()

        # isVisible() is compound with the (never-shown) top-level dialog and
        # would always read False here; isHidden() reflects setVisible()
        # directly regardless of ancestor state.
        assert dialog._agent_api_token_pending_note.isHidden() is True

    def test_note_hidden_when_writes_disabled(self, dialog, monkeypatch) -> None:
        monkeypatch.setattr(
            dialog,
            "parent",
            lambda: _FakeParentWindow("http://127.0.0.1:8765/mcp", "some-other-token"),
        )
        dialog._agent_api_token_pending_note.setVisible(True)  # force a prior state

        dialog._agent_api_writes_check.setChecked(False)

        # isVisible() is compound with the (never-shown) top-level dialog and
        # would always read False here; isHidden() reflects setVisible()
        # directly regardless of ancestor state.
        assert dialog._agent_api_token_pending_note.isHidden() is True
