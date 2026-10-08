"""Exercise developer-tool CLIs through subprocesses without remote writes."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def invoke(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args],
                          capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)


def write_xml(path: Path, hits: list[int]) -> None:
    lines = "".join(f'<line number="{i + 1}" hits="{h}"/>' for i, h in enumerate(hits))
    path.write_text('<coverage><sources><source>/x/src/open_garden_planner</source></sources>'
                    '<class filename="core/example.py"><lines>' + lines
                    + '</lines></class></coverage>', encoding="utf-8")


def test_coverage_cli_pass_fail_and_report_errors(tmp_path: Path) -> None:
    xml, floors, report = (tmp_path / n for n in ("coverage.xml", "floors.json", "report.json"))
    floors.write_text(json.dumps({"schema_version": 1,
                                 "non_ui_definition": "all packages except ui",
                                 "line_floors": {"core": 80}}), encoding="utf-8")
    write_xml(xml, [1, 1, 1, 1, 0])
    argv = ("--xml", str(xml), "--floors", str(floors), "--report", str(report))
    assert invoke("check_coverage_floors.py", *argv).returncode == 0
    assert json.loads(report.read_text(encoding="utf-8"))["regressions"] == []
    write_xml(xml, [1, 1, 1, 0, 0])
    assert invoke("check_coverage_floors.py", *argv).returncode == 1
    assert json.loads(report.read_text(encoding="utf-8"))["regressions"][0]["covered_statements"] == 3
    xml.write_text("broken", encoding="utf-8")
    assert invoke("check_coverage_floors.py", *argv).returncode == 2
    assert json.loads(report.read_text(encoding="utf-8"))["available"] is False


@pytest.mark.parametrize("defect", ["duplicate-line", "duplicate-file", "contradictory-total"])
def test_coverage_cli_rejects_inflated_or_contradictory_records(tmp_path: Path, defect: str) -> None:
    xml, floors = tmp_path / "coverage.xml", tmp_path / "floors.json"
    floors.write_text(json.dumps({"schema_version": 1,
                                 "non_ui_definition": "all packages except ui",
                                 "line_floors": {"core": 80}}), encoding="utf-8")
    lines = '<line number="1" hits="1"/><line number="2" hits="0"/>'
    if defect == "duplicate-line":
        lines = '<line number="1" hits="1"/>' * 8 + '<line number="2" hits="0"/>'
    cls = '<class filename="core/a.py"><lines>' + lines + '</lines></class>'
    if defect == "duplicate-file":
        cls += cls
    declared = 99 if defect == "contradictory-total" else 2
    xml.write_text(f'<coverage lines-valid="{declared}" lines-covered="1"><sources>'
                   '<source>/w/src/open_garden_planner</source></sources>' + cls + '</coverage>',
                   encoding="utf-8")
    proc = invoke("check_coverage_floors.py", "--xml", str(xml), "--floors", str(floors))
    assert proc.returncode == 2, proc.stdout
    assert json.loads(proc.stdout)["available"] is False


def test_type_cli_invalid_baseline_fails_visibly_without_rewriting(tmp_path: Path) -> None:
    baseline, report = tmp_path / "baseline.json", tmp_path / "report.json"
    baseline.write_text('{"schema_version": 999}', encoding="utf-8")
    original = baseline.read_bytes()
    proc = invoke("check_mypy_baseline.py", "--baseline", str(baseline), "--report", str(report))
    assert proc.returncode == 2
    assert json.loads(report.read_text(encoding="utf-8"))["available"] is False
    assert baseline.read_bytes() == original


def test_type_cli_missing_mypy_is_an_error_not_a_clean_result(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, "-S", str(ROOT / "scripts/check_mypy_baseline.py"),
         "--report", str(report)], capture_output=True, text=True,
        encoding="utf-8", timeout=60, check=False,
    )
    assert proc.returncode == 2
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["available"] is False and "mypy" in data["reason"]


def test_lock_cli_missing_lock_does_not_modify_root(tmp_path: Path) -> None:
    proc = invoke("check_dependency_lock.py", "--root", str(tmp_path))
    assert proc.returncode == 2
    assert "Missing uv.lock" in proc.stderr
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("tag,pr", [("1.2.3", "1"), ("v1.2.3", "0"), ("vbad", "1")])
def test_version_sync_cli_rejects_inputs_before_writing(tmp_path: Path, tag: str, pr: str) -> None:
    proc = invoke("prepare_version_sync.py", "--root", str(tmp_path), "--tag", tag,
                  "--source-pr", pr, "--apply")
    assert proc.returncode == 2
    assert list(tmp_path.iterdir()) == []


def test_protection_cli_reads_fixture_and_never_mutates(tmp_path: Path) -> None:
    payload = ROOT / "quality/master-protection.json"
    response = tmp_path / "response.json"
    response.write_bytes(payload.read_bytes())
    assert invoke("check_branch_protection.py", "--response", str(response)).returncode == 0
    data = json.loads(response.read_text(encoding="utf-8"))
    data["required_status_checks"]["contexts"] = []
    response.write_text(json.dumps(data), encoding="utf-8")
    before = response.read_bytes()
    assert invoke("check_branch_protection.py", "--response", str(response)).returncode == 1
    assert response.read_bytes() == before


def test_pr_check_cli_rejects_missing_results_and_changed_head(tmp_path: Path) -> None:
    policy = json.loads((ROOT / "quality/master-protection.json").read_text(encoding="utf-8"))
    checks = [{"name": name, "status": "COMPLETED", "conclusion": "SUCCESS"}
              for name in policy["required_status_checks"]["contexts"]]
    response = tmp_path / "pr.json"
    data = {"headRefOid": "abc", "baseRefName": "master", "statusCheckRollup": checks}
    response.write_text(json.dumps(data), encoding="utf-8")
    args = ("--pr", "1", "--head", "abc", "--response", str(response))
    assert invoke("check_pr_checks.py", *args).returncode == 0
    assert invoke("check_pr_checks.py", *args, "--head", "new").returncode == 1
    data["statusCheckRollup"] = []
    response.write_text(json.dumps(data), encoding="utf-8")
    before = response.read_bytes()
    assert invoke("check_pr_checks.py", *args).returncode == 1
    assert response.read_bytes() == before
    response.write_text("null", encoding="utf-8")
    assert invoke("check_pr_checks.py", *args).returncode == 2


@pytest.mark.skipif(sys.version_info[:2] != (3, 11), reason="Type gate targets Python 3.11")
def test_type_cli_generate_check_regress_and_reduce(tmp_path: Path) -> None:
    source = tmp_path / "src/open_garden_planner"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    module = source / "example.py"
    module.write_text('value: int = "bad"\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[tool.mypy]\nstrict=true\npython_version="3.11"\n',
                                            encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    argv = ("--root", str(tmp_path), "--baseline", str(baseline))
    assert invoke("check_mypy_baseline.py", *argv, "--write-baseline").returncode == 0
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert data["environments"][sys.platform]["per_file"] == {
        "src/open_garden_planner/example.py": 1,
    }
    before = baseline.read_bytes()
    assert invoke("check_mypy_baseline.py", *argv).returncode == 0
    module.write_text('value: int = "bad"\nother: int = "also bad"\n', encoding="utf-8")
    assert invoke("check_mypy_baseline.py", *argv).returncode == 1
    module.write_text("value: int = 1\n", encoding="utf-8")
    assert invoke("check_mypy_baseline.py", *argv).returncode == 0
    assert baseline.read_bytes() == before
    (source / "new.py").write_text('value: int = "bad"\n', encoding="utf-8")
    assert invoke("check_mypy_baseline.py", *argv).returncode == 1


def lock_fixture(path: Path) -> None:
    for name in ("pyproject.toml", "uv.lock", "pylock.toml",
                 "src/open_garden_planner/__init__.py", "README.md"):
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)


@pytest.mark.skipif(shutil.which("uv") is None, reason="Requires project-pinned uv")
def test_version_sync_cli_is_offline_transactional_and_idempotent(tmp_path: Path) -> None:
    import tomllib

    lock_fixture(tmp_path)
    files = ("pyproject.toml", "src/open_garden_planner/__init__.py", "uv.lock", "pylock.toml")
    before = {name: (tmp_path / name).read_bytes() for name in files}
    version = tomllib.loads(before["pyproject.toml"].decode())["project"]["version"]
    major, minor, patch = map(int, version.split("."))
    tag = f"v{major}.{minor}.{patch + 1}"
    argv = ("--root", str(tmp_path), "--tag", tag, "--source-pr", "42")
    dry = invoke("prepare_version_sync.py", *argv)
    assert dry.returncode == 0, dry.stderr
    assert not json.loads(dry.stdout)["already_synced"]
    assert before == {name: (tmp_path / name).read_bytes() for name in files}
    applied = invoke("prepare_version_sync.py", *argv, "--apply")
    assert applied.returncode == 0, applied.stderr
    assert tomllib.loads((tmp_path / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"] == tag[1:]
    assert f'__version__ = "{tag[1:]}"' in (tmp_path / files[1]).read_text(encoding="utf-8")
    repeated = invoke("prepare_version_sync.py", *argv)
    assert repeated.returncode == 0, repeated.stderr
    assert json.loads(repeated.stdout)["already_synced"] is True


@pytest.mark.skipif(shutil.which("uv") is None, reason="Requires project-pinned uv")
def test_lock_cli_rejects_altered_export_and_stale_manifest_without_repairs(tmp_path: Path) -> None:
    lock_fixture(tmp_path)
    argv = ("--root", str(tmp_path))
    assert invoke("check_dependency_lock.py", *argv).returncode == 0
    assert invoke("check_dependency_lock.py", *argv).returncode == 0
    export = tmp_path / "pylock.toml"
    original_export = export.read_bytes()
    export.write_bytes(original_export + b"\n# altered\n")
    assert invoke("check_dependency_lock.py", *argv).returncode == 2
    assert export.read_bytes() == original_export + b"\n# altered\n"
    export.write_bytes(original_export)
    manifest = tmp_path / "pyproject.toml"
    import tomllib

    current = tomllib.loads(manifest.read_text(encoding="utf-8"))["project"]["version"]
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(f'version = "{current}"',
                                                    'version = "99.0.0"'), encoding="utf-8")
    before = (tmp_path / "uv.lock").read_bytes()
    assert invoke("check_dependency_lock.py", *argv).returncode == 2
    assert (tmp_path / "uv.lock").read_bytes() == before
