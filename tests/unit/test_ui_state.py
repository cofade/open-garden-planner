"""Unit tests for UiStateStore (QSettings-backed UI persistence).

Tests use an isolated INI file in a temp dir so they don't read or write
the user's real Open Garden Planner registry/preferences.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings

from open_garden_planner.app.ui_state import UiStateStore


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """Force QSettings to use an INI file in tmp_path."""
    ini_path = tmp_path / "ogp-test.ini"
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(tmp_path),
    )
    yield ini_path


class TestUiStateStorePanelState:
    def test_default_returned_when_unset(self, isolated_settings) -> None:
        store = UiStateStore()
        assert store.restore_panel_state("never_seen", default=True) is True
        assert store.restore_panel_state("never_seen", default=False) is False

    def test_save_then_restore_roundtrip(self, isolated_settings) -> None:
        store = UiStateStore()
        store.save_panel_state("properties", expanded=True)
        store.save_panel_state("layers", expanded=False)

        # Build a fresh store to ensure we read from the backing file, not
        # in-memory caches.
        store2 = UiStateStore()
        assert store2.restore_panel_state("properties", default=False) is True
        assert store2.restore_panel_state("layers", default=True) is False

    def test_string_true_decoded_to_bool(self, isolated_settings) -> None:
        """QSettings on some backends stores bools as strings."""
        s = QSettings("cofade", "Open Garden Planner")
        s.setValue("UiState/panel_xyz", "true")
        s.sync()

        store = UiStateStore()
        assert store.restore_panel_state("xyz", default=False) is True
