"""Smoke test for scripts/audit_metrics.py — the re-runnable metrics baseline (2026-10 audit).

Runs the script offline (no git, mypy, ruff or radon) against this repository and checks
the JSON shape, so a later refactor of the script cannot silently drop a section that the
§11.3 debt register and the audit report rely on. The optional tool sections are covered
by the script's own graceful-degradation branches (``available: false`` with a reason).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_metrics.py"


def test_metrics_snapshot_offline(tmp_path: Path) -> None:
    out = tmp_path / "metrics.json"
    proc = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, str(SCRIPT), "--root", str(ROOT), "--out", str(out),
         "--no-git", "--no-mypy", "--no-ruff", "--no-radon"],
        capture_output=True, text=True, encoding="utf-8", timeout=600, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    snap = json.loads(out.read_text(encoding="utf-8"))

    assert snap["schema_version"] == 1
    for key in ("meta", "loc", "complexity", "types", "lint", "layering", "coverage",
                "tests", "git", "hygiene", "docs"):
        assert key in snap, key
    assert set(snap["meta"]["disabled"]) == {"git", "mypy", "ruff", "radon"}
    assert snap["complexity"] is None and snap["types"] is None and snap["lint"] is None
    assert snap["git"] is None and snap["coverage"] is None

    assert snap["loc"]["src_total"] > 50_000
    assert "core" in snap["loc"]["src_per_package"] and "ui" in snap["loc"]["src_per_package"]
    assert snap["tests"]["test_functions_total"] > 1_000
    assert snap["layering"]["module_level_violations_total"] >= 0
    assert "CONTRIBUTING.md" in snap["hygiene"]["standard_files"]
    assert snap["hygiene"]["claude_agents_identical"] is True
    assert snap["docs"]["markdown_files"] >= 10


def test_metrics_rejects_non_repo_root(tmp_path: Path) -> None:
    proc = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--out", str(tmp_path / "x.json")],
        capture_output=True, text=True, encoding="utf-8", timeout=120, check=False,
    )
    assert proc.returncode == 2
    assert "does not look like the repository root" in proc.stderr
