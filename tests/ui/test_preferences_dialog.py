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
