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
    # The Linux path secures the backend's file; the fake name would create
    # `fake-settings.ini` in the working directory on a Linux runner.
    monkeypatch.setattr(settings_module, "_secure_linux_settings", lambda _path: None)
    for name in (
        settings_module.PRODUCT_PROCESS_ENV,
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
    """``script_isolation.isolate()`` rebinds the names; the guard sees non-production ones."""
    monkeypatch.setattr(settings_module, "ORGANIZATION_NAME", "cofade_test")
    monkeypatch.setattr(settings_module, "APPLICATION_NAME", "Open Garden Planner Script 1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("CODEX_SANDBOX", "1")
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


def test_the_product_marker_is_set_inside_main_not_at_import() -> None:
    """``main()`` is the one legitimate production-names context (drift guard).

    Read rather than imported: this test runs after the QApplication exists, and
    ``main.py`` imports ``QtWebEngineWidgets``, which Qt requires before the first
    QCoreApplication. The AST check pins the placement the design depends on — a
    probe that imports ``main`` for a helper must not inherit the permission.
    """
    import ast
    from pathlib import Path

    main_path = Path(settings_module.__file__).parent.parent / "main.py"
    source = main_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    def sets_product_marker(node: ast.AST) -> bool:
        """An actual ``os.environ["OGP_PRODUCT_PROCESS"] = "1"`` statement."""
        if not isinstance(node, ast.Assign):
            return False
        if not (isinstance(node.value, ast.Constant) and node.value.value == "1"):
            return False
        for target in node.targets:
            if not isinstance(target, ast.Subscript):
                continue
            value = target.value
            if (
                isinstance(value, ast.Attribute)
                and value.attr == "environ"
                and isinstance(value.value, ast.Name)
                and value.value.id == "os"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == settings_module.PRODUCT_PROCESS_ENV
            ):
                return True
        return False

    main_fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    inside_main = {id(node) for node in ast.walk(main_fn)}
    assert any(sets_product_marker(node) for node in ast.walk(main_fn)), (
        "main() no longer sets the product marker"
    )
    assert not any(
        sets_product_marker(node)
        for node in ast.walk(tree)
        if id(node) not in inside_main
    ), "the product marker must not be set outside main()"
