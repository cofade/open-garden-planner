"""Unit tests for UiStateStore (QSettings-backed UI persistence).

Since US-226 the store only persists window geometry + the main splitter (the
per-panel collapse/expand helpers were removed — the sidebar accordion always
starts collapsed). These tests cover the surviving geometry/splitter round-trips.

Tests use an isolated INI file in a temp dir so they don't read or write the
user's real Open Garden Planner registry/preferences.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMainWindow, QSplitter

from open_garden_planner.app.ui_state import UiStateStore


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    """Redirect UiStateStore's QSettings to an INI file in tmp_path.

    Uses ``monkeypatch`` to swap the ``QSettings`` symbol that ``UiStateStore``
    resolves, so no *process-global* QSettings state (``setDefaultFormat`` /
    ``setPath``) is mutated. Those statics are never reverted by Qt, and leaking
    them poisons every QSettings created later in the session.
    """
    ini_path = tmp_path / "ogp-test.ini"

    def _file_settings(*_args: object, **_kwargs: object) -> QSettings:
        return QSettings(str(ini_path), QSettings.Format.IniFormat)

    monkeypatch.setattr("open_garden_planner.app.ui_state.QSettings", _file_settings)
    yield ini_path


class TestUiStateStoreGeometry:
    def test_restore_returns_false_when_unset(self, isolated_settings, qtbot) -> None:
        win = QMainWindow()
        qtbot.addWidget(win)
        store = UiStateStore()
        assert store.restore_geometry(win) is False

    def test_geometry_roundtrip(self, isolated_settings, qtbot) -> None:
        src = QMainWindow()
        qtbot.addWidget(src)
        src.resize(800, 600)
        UiStateStore().save_geometry(src)

        dst = QMainWindow()
        qtbot.addWidget(dst)
        # A fresh store reads from the backing INI, not an in-memory cache.
        assert UiStateStore().restore_geometry(dst) is True


class TestUiStateStoreSplitter:
    def test_restore_returns_false_when_unset(self, isolated_settings, qtbot) -> None:
        sp = QSplitter()
        qtbot.addWidget(sp)
        assert UiStateStore().restore_splitter("main", sp) is False

    def test_splitter_roundtrip_preserves_sizes(self, isolated_settings, qtbot) -> None:
        from PyQt6.QtWidgets import QWidget

        src = QSplitter()
        qtbot.addWidget(src)
        src.addWidget(QWidget())
        src.addWidget(QWidget())
        src.setSizes([120, 380])
        UiStateStore().save_splitter("main", src)

        dst = QSplitter()
        qtbot.addWidget(dst)
        dst.addWidget(QWidget())
        dst.addWidget(QWidget())
        assert UiStateStore().restore_splitter("main", dst) is True
        # restoreState restores the *proportion* (scaled to the target's total
        # size), not the absolute pixels, so compare the ratio with tolerance.
        sizes = dst.sizes()
        total = sum(sizes)
        assert total > 0
        assert abs(sizes[0] / total - 120 / 500) < 0.05
