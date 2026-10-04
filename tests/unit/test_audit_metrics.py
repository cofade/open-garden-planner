"""Tests for scripts/audit_metrics.py, the re-runnable metrics baseline (2026-10 audit).

The script's value is that a later run can be diffed against the committed snapshot, so
the dangerous failure is not a crash but a confident wrong number. These tests pin the
parsers that could produce one: a missing mypy must not read as 0 errors, a coverage.xml
from either pytest invocation must bucket identically (and an unknown layout must fail
closed), and the import classifier must tell module-level, function-local and
TYPE_CHECKING imports apart. One offline run checks the JSON shape.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from scripts.audit_metrics import classify_imports, coverage_section, parse_mypy

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_metrics.py"


def test_metrics_snapshot_offline(tmp_path: Path) -> None:
    out = tmp_path / "metrics.json"
    argv = [sys.executable, str(SCRIPT), "--root", str(ROOT), "--out", str(out)]
    argv += ["--no-git", "--no-mypy", "--no-ruff", "--no-radon"]
    proc = subprocess.run(  # noqa: S603 - fixed argv
        argv, capture_output=True, text=True, encoding="utf-8", timeout=600, check=False
    )
    assert proc.returncode == 0, proc.stderr
    snap = json.loads(out.read_text(encoding="utf-8"))

    assert snap["schema_version"] == 2
    for key in (
        "meta",
        "loc",
        "complexity",
        "types",
        "lint",
        "layering",
        "coverage",
        "tests",
        "git",
        "hygiene",
        "docs",
    ):
        assert key in snap, key
    assert set(snap["meta"]["disabled"]) == {"git", "mypy", "ruff", "radon"}
    for disabled in ("complexity", "types", "lint", "git", "coverage"):
        assert snap[disabled] is None, disabled

    assert "core" in snap["loc"]["src_per_package"] and "ui" in snap["loc"]["src_per_package"]
    assert all("\\" not in f["path"] for f in snap["loc"]["largest_src_files"])
    for violation in snap["layering"]["module_level_violations"]:
        assert violation["path"].split("/")[2] in ("core", "services", "models", "agent_api")
        assert all(i.split(".")[1] in ("ui", "app") for i in violation["imports"])
    assert snap["layering"]["unparsed_files"] == []
    assert snap["tests"]["unparsed_files"] == []


def test_missing_mypy_is_unavailable_not_zero() -> None:
    # `python -m mypy` without mypy installed exits 1, the same code as "errors found".
    result = parse_mypy(1, "", "/usr/bin/python3: No module named mypy")
    assert result["available"] is False
    assert "errors" not in result


def test_mypy_summary_lines_parse() -> None:
    out = (
        "src/open_garden_planner/core/a.py:3: error: Bad thing  [attr-defined]\n"
        'src/open_garden_planner/ui/b.py:9: error: Unused "type: ignore" comment  [unused-ignore]\n'
        "Found 2 errors in 2 files (checked 5 source files)\n"
    )
    result = parse_mypy(1, out, "")
    assert result["available"] is True
    assert (result["errors"], result["files_with_errors"]) == (2, 2)
    assert result["per_package"] == {"core": 1, "ui": 1}
    assert result["unused_type_ignores"] == 1

    clean = parse_mypy(0, "Success: no issues found in 5 source files\n", "")
    assert clean["available"] is True and clean["errors"] == 0


def _coverage_xml(path: Path, source: str, prefix: str) -> Path:
    def cls(name: str, hits: list[int]) -> str:
        lines = "".join(f'<line number="{i + 1}" hits="{h}"/>' for i, h in enumerate(hits))
        return f'<class name="x" filename="{prefix}{name}"><lines>{lines}</lines></class>'

    body = cls("core/a.py", [1, 1, 0, 1]) + cls("ui/b.py", [1, 0]) + cls("main.py", [1])
    path.write_text(
        f'<?xml version="1.0" ?><coverage><sources><source>{source}</source></sources>'
        f"<packages><package><classes>{body}</classes></package></packages></coverage>",
        encoding="utf-8",
    )
    return path


def test_coverage_layouts_bucket_identically(tmp_path: Path) -> None:
    # `pytest --cov` with [tool.coverage.run] source: filenames relative to the package.
    relative = coverage_section(
        _coverage_xml(tmp_path / "a.xml", "/w/repo/src/open_garden_planner", "")
    )
    # `pytest --cov=open_garden_planner`: filenames under src/.
    src_rooted = coverage_section(
        _coverage_xml(tmp_path / "b.xml", "/w/repo", "src/open_garden_planner/")
    )
    for result in (relative, src_rooted):
        assert result is not None and result["available"] is True
        assert set(result["per_package"]) == {"core", "ui", "(root)"}
        assert result["non_ui"]["statements"] == 5 and result["non_ui"]["line_pct"] == 80.0
        assert result["total"]["statements"] == 7
    assert relative["per_package"] == src_rooted["per_package"]


def test_coverage_checkout_named_like_the_package(tmp_path: Path) -> None:
    # A clone directory called open_garden_planner must not shift every file into "src".
    for i, (source, prefix) in enumerate(
        [
            ("/home/u/open_garden_planner/src/open_garden_planner", ""),
            ("/home/u/open_garden_planner", "src/open_garden_planner/"),
        ]
    ):
        result = coverage_section(_coverage_xml(tmp_path / f"d{i}.xml", source, prefix))
        assert result is not None and result["available"] is True
        assert set(result["per_package"]) == {"core", "ui", "(root)"}


def test_coverage_unknown_layout_fails_closed(tmp_path: Path) -> None:
    result = coverage_section(_coverage_xml(tmp_path / "c.xml", "/elsewhere", "other_pkg/"))
    assert result is not None and result["available"] is False


def test_import_classifier_scopes() -> None:
    source = (
        "from typing import TYPE_CHECKING\n"
        "import open_garden_planner.app.settings\n"
        "try:\n"
        "    from open_garden_planner.ui import theme\n"
        "except ImportError:\n"
        "    theme = None\n"
        "if TYPE_CHECKING:\n"
        "    from open_garden_planner.ui.canvas import CanvasView\n"
        "class C:\n"
        "    from open_garden_planner.app import paths\n"
        "    def m(self):\n"
        "        from open_garden_planner.ui.canvas.items import TextItem\n"
        "f = lambda: __import__('x')\n"
    )
    scopes = {
        (n.module if isinstance(n, ast.ImportFrom) else n.names[0].name): s
        for n, s in classify_imports(ast.parse(source))
    }
    assert scopes == {
        "typing": "module",
        "open_garden_planner.app.settings": "module",
        "open_garden_planner.ui": "module",
        "open_garden_planner.ui.canvas": "type_checking",
        "open_garden_planner.app": "module",
        "open_garden_planner.ui.canvas.items": "function_local",
    }
