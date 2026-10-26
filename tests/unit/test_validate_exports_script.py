"""Unit test for the diagnostic export validation script (AUD-037, #455)."""
from __future__ import annotations

from pathlib import Path

import scripts.validate_exports as val_exp


def test_validate_exports_importable_without_side_effects() -> None:
    """The script must be importable without executing exports or exiting the process."""
    assert hasattr(val_exp, "validate_exports")
    assert hasattr(val_exp, "create_sample_plan")
    assert hasattr(val_exp, "main")


def test_validate_exports_runs_on_sample_plan(qtbot, tmp_path: Path) -> None:
    """validate_exports executes against a sample plan and produces PNG, SVG, PDF."""
    ogp_path = tmp_path / "test_sample.ogp"
    val_exp.create_sample_plan(ogp_path)
    assert ogp_path.is_file()

    out_dir = tmp_path / "exports"
    results = val_exp.validate_exports(ogp_path, out_dir, verbose=False)

    outputs = results["outputs"]
    assert outputs["png"]["path"].is_file()
    assert outputs["png"]["bytes"] > 0
    assert outputs["svg"]["path"].is_file()
    assert outputs["svg"]["bytes"] > 0
    assert outputs["pdf"]["path"].is_file()
    assert outputs["pdf"]["bytes"] > 0


def test_validate_exports_main_cli(qtbot, tmp_path: Path) -> None:
    """main() CLI entrypoint succeeds with --quiet and custom output directory."""
    out_dir = tmp_path / "cli_out"
    code = val_exp.main(["--out-dir", str(out_dir), "--quiet"])
    assert code == 0
    assert (out_dir / "overview.png").is_file()
    assert (out_dir / "overview.svg").is_file()
    assert (out_dir / "report.pdf").is_file()
