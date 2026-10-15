"""Exercise the real CLI and persisted language selection/startup path (#496)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES, load_translator
from tests.translation_helpers import catalog_path, catalogs, project


def test_real_cli_refuses_incomplete_third_locale_without_writes(tmp_path):
    root = project(tmp_path)
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[2] / "scripts/check_translations.py"),
        "--root",
        str(root),
    ]
    environment = {**os.environ, "PYTHONUTF8": "1"}
    passed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=environment, check=False
    )
    assert passed.returncode == 0, passed.stdout + passed.stderr
    path = catalog_path(root)
    path.write_text('<TS language="es"/>', encoding="utf-8")
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    failed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=environment, check=False
    )
    assert failed.returncode == 1
    assert "es: missing [Dialog]" in failed.stdout and "Hello {name}" in failed.stdout
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    catalogs(root)
    corrected = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", env=environment, check=False
    )
    assert corrected.returncode == 0, corrected.stdout + corrected.stderr


@pytest.mark.parametrize("locale", SUPPORTED_LANGUAGES)
def test_language_menu_persists_then_next_window_uses_translation(qtbot, monkeypatch, locale):
    monkeypatch.setattr(QMessageBox, "information", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *_args, **_kwargs: QMessageBox.StandardButton.Discard
    )
    monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda _self: None)
    app = QApplication.instance()
    load_translator(app, "en")
    settings = get_settings()
    first = GardenPlannerApp()
    qtbot.addWidget(first)
    try:
        first._language_actions[locale].trigger()
        assert settings.language == locale
        first.close()
        # main.py installs the saved locale before constructing the next window.
        assert load_translator(app, settings.language)
        second = GardenPlannerApp()
        qtbot.addWidget(second)
        try:
            texts = {action.text() for action in second.menuBar().actions()}
            expected = QApplication.translate("GardenPlannerApp", "&View")
            assert expected in texts
            if locale == "de":
                assert expected != "&View"
            app.processEvents()
            assert second._language_actions[locale].isChecked()
        finally:
            second.close()
    finally:
        load_translator(app, "en")
