"""The settings chokepoint refuses the owner's real store from probes (#587).

A review probe built ``GardenPlannerApp`` in a scratchpad, gave the QApplication
a throwaway name and set ``QSettings.setDefaultFormat(IniFormat)``. Neither
redirects ``create_qsettings()``, which passes the module's own names to
``QSettings(org, app)`` — and that constructor always uses the native format. The
write reached the owner's registry and switched off the startup Welcome dialog.
These tests pin the guard that now refuses that process.
"""

from __future__ import annotations

import pytest

from open_garden_planner.app import settings as settings_module

pytestmark = pytest.mark.usefixtures("qtbot")


class _FakeQSettings:
    """A backend that records construction instead of touching the real registry."""

    def __init__(self, organization: str, application: str) -> None:
        self.organization = organization
        self.application = application

    def fileName(self) -> str:
        return "fake-settings.ini"


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch):
    """Production names, a fake backend, and none of the allow markers."""
    monkeypatch.setattr(
        settings_module, "ORGANIZATION_NAME", settings_module.PRODUCTION_ORGANIZATION_NAME
    )
    monkeypatch.setattr(
        settings_module, "APPLICATION_NAME", settings_module.PRODUCTION_APPLICATION_NAME
    )
    monkeypatch.setattr(settings_module, "QSettings", _FakeQSettings)
    for name in (
        settings_module.PRODUCT_PROCESS_ENV,
        settings_module.ISOLATION_MARKER_ENV,
        settings_module.ALLOW_PRODUCTION_ENV,
    ):
        monkeypatch.delenv(name, raising=False)
    for name in settings_module.TOOLING_ENV_MARKERS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    yield


def test_a_headless_probe_is_refused(production, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    with pytest.raises(settings_module.SettingsIsolationError, match="offscreen"):
        settings_module.create_qsettings()


def test_a_minimal_platform_is_refused(production, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "minimal:enable_fonts")
    with pytest.raises(settings_module.SettingsIsolationError, match="minimal"):
        settings_module.create_qsettings()


def test_a_tooling_shell_probe_is_refused(production, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "windows")
    monkeypatch.setenv("CODEX_SANDBOX", "1")
    with pytest.raises(settings_module.SettingsIsolationError, match="CODEX_SANDBOX"):
        settings_module.create_qsettings()


def test_an_isolated_script_is_allowed(production, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv(settings_module.ISOLATION_MARKER_ENV, "1")
    assert isinstance(settings_module.create_qsettings(), _FakeQSettings)


def test_the_product_entry_point_is_allowed(production, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "windows")
    monkeypatch.setenv(settings_module.PRODUCT_PROCESS_ENV, "1")
    assert isinstance(settings_module.create_qsettings(), _FakeQSettings)


def test_the_deliberate_override_is_allowed(production, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv(settings_module.ALLOW_PRODUCTION_ENV, "1")
    assert isinstance(settings_module.create_qsettings(), _FakeQSettings)


def test_non_production_names_are_allowed(production, monkeypatch: pytest.MonkeyPatch) -> None:
    """The test suite and ``script_isolation`` rebind the names; they are already safe."""
    monkeypatch.setattr(settings_module, "ORGANIZATION_NAME", "cofade_test")
    monkeypatch.setattr(settings_module, "APPLICATION_NAME", "Open Garden Planner Test 1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("CODEX_SANDBOX", "1")
    assert isinstance(settings_module.create_qsettings(), _FakeQSettings)


def test_the_tooling_scan_matches_exact_session_markers_only() -> None:
    assert settings_module._tooling_environment_marker({"CODEX_SANDBOX": "1"}) == "CODEX_SANDBOX"
    assert settings_module._tooling_environment_marker(
        {"OPENCODE_SESSION_ID": "ses_x"}
    ) == "OPENCODE_SESSION_ID"
    # API keys are not session markers; a developer's shell may hold them.
    assert settings_module._tooling_environment_marker({"CODEX_API_KEY": "sk-x"}) is None
    assert settings_module._tooling_environment_marker({"GEMINI_API_KEY": "x"}) is None


def test_the_product_entry_point_uses_the_shared_marker_name() -> None:
    """``main.py`` is the one legitimate production-names context (drift guard).

    Read rather than imported: this test runs after the QApplication exists, and
    ``main.py`` imports ``QtWebEngineWidgets``, which Qt requires before the first
    QCoreApplication. The frozen exe gate proves the import path itself.
    """
    from pathlib import Path

    main_source = (
        Path(settings_module.__file__).parent.parent / "main.py"
    ).read_text(encoding="utf-8")
    assert f'os.environ["{settings_module.PRODUCT_PROCESS_ENV}"] = "1"' in main_source
