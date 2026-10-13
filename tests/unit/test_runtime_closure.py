"""The single runtime-closure resolver shared by the spec and the inventory (AUD-051/055)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load():
    path = ROOT / "installer" / "runtime_closure.py"
    spec = importlib.util.spec_from_file_location("ogp_runtime_closure_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime_closure = _load()


def test_canonicalize_folds_pep503_separators() -> None:
    assert runtime_closure.canonicalize("typing_extensions") == "typing-extensions"
    assert runtime_closure.canonicalize("Example.Lib") == "example-lib"


def test_closure_is_the_project_runtime_tree_not_the_dev_tree() -> None:
    names = runtime_closure.runtime_distribution_names()
    assert "pillow" in names and "pyqt6" in names and "ezdxf" in names
    assert "pytest" not in names and "pyinstaller" not in names


def test_extras_of_transitive_dependencies_are_followed() -> None:
    """``pyjwt[crypto]`` must pull in ``cryptography`` — the bug in a plain walk."""
    names = runtime_closure.runtime_distribution_names()
    assert "pyjwt" in names
    assert "cryptography" in names


def test_the_project_itself_is_not_a_third_party_distribution() -> None:
    assert "open-garden-planner" not in runtime_closure.runtime_distribution_names()


def test_manifest_anchor_beats_a_stale_editable_metadata_dir(tmp_path: Path) -> None:
    """A stale ``*.egg-info`` on sys.path must not shrink the closure.

    Verified live on 2026-10-13: a dev checkout's ``src/open_garden_planner.egg-info``
    (version 0.1.0, two dependencies) shadowed the real dist-info and silently cut
    the closure to five names.
    """
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        '[project]\nname = "open-garden-planner"\ndependencies = ["pillow>=10.0.0"]\n',
        encoding="utf-8",
    )
    names = runtime_closure.runtime_distribution_names(manifest)
    assert "pillow" in names
    assert "pyqt6" not in names  # the injected manifest is the whole root set


def test_installed_version_resolves_canonical_names() -> None:
    assert runtime_closure.installed_version("pillow")
    assert runtime_closure.installed_version("not-a-real-distribution") is None
