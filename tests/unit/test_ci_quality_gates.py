"""Regression gates for #399/#401/#402/#404, measured before implementation."""

import json
import re
from pathlib import Path

import pytest
from scripts import prepare_version_sync
from scripts.audit_metrics import coverage_section, parse_mypy
from scripts.check_branch_protection import differences
from scripts.check_coverage_floors import main as coverage_floor_main
from scripts.check_coverage_floors import regressions as coverage_regressions
from scripts.check_coverage_floors import validate_floors
from scripts.check_mypy_baseline import regressions as type_regressions
from scripts.check_mypy_baseline import validate_baseline
from scripts.check_pr_checks import differences as check_differences
from scripts.prepare_version_sync import replace_manifest_version, third_party_packages


def test_mypy_rejects_an_incomplete_diagnostic_stream() -> None:
    result = parse_mypy(1, "Found 2 errors in 1 file (checked 1 source file)\n", "")
    assert result["available"] is False
    assert parse_mypy(0, "Success: no issues found\n", "error: truncated")["available"] is False
    assert parse_mypy(0, "error: failed\nSuccess: no issues found\n", "")["available"] is False


def test_mypy_exposes_normalized_per_file_counts() -> None:
    result = parse_mypy(
        1,
        "src\\open_garden_planner\\core\\a.py:3: error: bad  [attr-defined]\n"
        "Found 1 error in 1 file (checked 1 source file)\n",
        "",
    )
    assert result["per_file"] == {"src/open_garden_planner/core/a.py": 1}


def test_coverage_exposes_counts_for_unrounded_floor_checks(tmp_path: Path) -> None:
    xml = tmp_path / "coverage.xml"
    xml.write_text(
        '<coverage><sources><source>/w/src/open_garden_planner</source></sources>'
        '<packages><package><classes><class filename="core/a.py"><lines>'
        '<line number="1" hits="1" branch="true" condition-coverage="50% (1/2)"/>'
        '<line number="2" hits="0"/>'
        '</lines></class></classes></package></packages></coverage>',
        encoding="utf-8",
    )
    result = coverage_section(xml)
    assert result is not None and result["available"]
    assert result["per_package"]["core"]["covered_statements"] == 1
    assert result["per_package"]["core"]["branches"] == 2
    assert result["per_package"]["core"]["covered_branches"] == 1


def test_coverage_root_and_spike_are_separate_non_ui_packages(tmp_path: Path) -> None:
    xml = tmp_path / "coverage.xml"
    xml.write_text('<coverage><sources><source>/w/src/open_garden_planner</source></sources>'
                   '<class filename="main.py"><lines><line number="1" hits="1"/>'
                   '</lines></class><class filename="spike_q3d/runner.py"><lines>'
                   '<line number="1" hits="0"/></lines></class></coverage>', encoding="utf-8")
    result = coverage_section(xml)
    assert result is not None and result["available"]
    assert set(result["per_package"]) == {"(root)", "spike_q3d"}
    assert result["non_ui"]["covered_statements"] == 1


@pytest.mark.parametrize("rc,out", [
    (0, "Found 1 error in 1 file\n"),
    (1, "Success: no issues found\n"),
    (2, "Success: no issues found\n"),
    (1, "pyproject.toml:3: error: bad\nFound 1 error in 1 file\n"),
    (1, "src/open_garden_planner/core/a.py:3: error: bad\nFound 1 error in 2 files\n"),
])
def test_mypy_invalid_reports_fail_closed(rc: int, out: str) -> None:
    assert parse_mypy(rc, out, "")["available"] is False


def test_type_budgets_are_per_file_and_new_files_have_no_budget() -> None:
    assert type_regressions({"a": 2, "b": 0, "new": 1}, {"a": 1, "b": 4}) == [
        {"path": "a", "actual": 2, "allowed": 1},
        {"path": "new", "actual": 1, "allowed": 0},
    ]
    assert type_regressions({"a": 1}, {"a": 2}) == []


@pytest.mark.parametrize("count", [-1, True, 1.5, "2"])
def test_type_allowances_reject_invalid_counts(count: object) -> None:
    data = {"schema_version": 1, "target_python": "3.11", "mypy_version": "2.4.0",
            "environments": {"win32": {"per_file": {"src/open_garden_planner/a.py": count}}}}
    with pytest.raises(ValueError):
        validate_baseline(data, "2.4.0")


def test_baseline_keeps_platforms_independent_and_rejects_tool_drift() -> None:
    data = {"schema_version": 1, "target_python": "3.11", "mypy_version": "2.4.0",
            "environments": {
                "linux": {"per_file": {"src/open_garden_planner/a.py": 1}},
                "win32": {"per_file": {"src/open_garden_planner/a.py": 2}},
            }}
    assert validate_baseline(data, "2.4.0")["environments"]["linux"]["per_file"] != (
        data["environments"]["win32"]["per_file"]
    )
    with pytest.raises(ValueError, match="metadata"):
        validate_baseline(data, "9.0.0")


def test_coverage_compares_exact_counts_and_names_every_package() -> None:
    packages = {"core": {"statements": 10000, "covered_statements": 7999}}
    assert coverage_regressions(packages, {"core": 80})
    assert coverage_regressions(packages, {"core": 79}) == []
    assert coverage_regressions(packages, {"core": 79, "ui": 0})
    assert coverage_regressions(packages, {"ui": 0})
    assert coverage_regressions({"core": {"statements": 5, "covered_statements": 4}},
                                {"core": 80}) == []


@pytest.mark.parametrize("floor", [-1, 101, True, 80.1, "80"])
def test_coverage_floor_metadata_is_strict(floor: object) -> None:
    with pytest.raises(ValueError):
        validate_floors({"schema_version": 1, "non_ui_definition": "all packages except ui",
                         "line_floors": {"core": floor}})


@pytest.mark.parametrize("line", [
    '<line number="1"/>', '<line number="1" hits="bad"/>',
    '<line number="1" hits="-1"/>', '<line number="1" hits="1" branch="true"/>',
    '<line number="1" hits="1" branch="true" condition-coverage="100% (3/2)"/>',
])
def test_coverage_bad_counts_fail_closed(tmp_path: Path, line: str) -> None:
    xml = tmp_path / "coverage.xml"
    xml.write_text('<coverage><sources><source>/w/src/open_garden_planner</source></sources>'
                   '<class filename="core/a.py"><lines>' + line + '</lines></class></coverage>',
                   encoding="utf-8")
    result = coverage_section(xml)
    assert result is not None and result["available"] is False


def test_protection_requires_checks_for_admins_but_no_review() -> None:
    payload = json.loads((Path(__file__).resolve().parents[2]
                          / "quality/master-protection.json").read_text(encoding="utf-8"))
    assert differences(payload, payload) == []
    payload["enforce_admins"] = {"enabled": False}
    payload["required_pull_request_reviews"]["required_approving_review_count"] = 1
    assert len(differences(payload, payload)) == 2


def test_coverage_floor_main_fails_closed_without_a_usable_report(tmp_path: Path, capsys) -> None:
    """#514: the floor step runs `if: always()`, so it must never pass without a report.

    ``main`` returns 2 when the XML is missing, malformed, or does not resolve into
    ``src/open_garden_planner``: "unavailable" is a failure, not a pass. The Coverage job
    depends on that — its floor step is the only step that decides the job, and it runs
    even when an earlier coverage step died.
    """
    floors = Path(__file__).resolve().parents[2] / "quality" / "coverage-floors.json"
    missing = tmp_path / "nope.xml"
    assert coverage_floor_main(["--xml", str(missing), "--floors", str(floors)]) == 2

    malformed = tmp_path / "bad.xml"
    malformed.write_text("<not-closed", encoding="utf-8")
    assert coverage_floor_main(["--xml", str(malformed), "--floors", str(floors)]) == 2

    empty = tmp_path / "empty.xml"
    empty.write_text(
        "<coverage><sources><source>/w/src/open_garden_planner</source></sources></coverage>",
        encoding="utf-8",
    )
    assert coverage_floor_main(["--xml", str(empty), "--floors", str(floors)]) == 2

    # The failure is also recorded, so the uploaded diagnostic says why.
    report = tmp_path / "summary.json"
    assert (
        coverage_floor_main(
            ["--xml", str(missing), "--floors", str(floors), "--report", str(report)]
        )
        == 2
    )
    assert json.loads(report.read_text(encoding="utf-8"))["available"] is False
    capsys.readouterr()  # the verdict JSON belongs in the CI log, not the test output


def test_master_protection_requires_the_coverage_floor_too() -> None:
    """#514: a floor breach blocks a merge, so the payload must name `Coverage`."""
    payload = json.loads(
        (
            Path(__file__).resolve().parents[2] / "quality/master-protection.json"
        ).read_text(encoding="utf-8")
    )
    contexts = set(payload["required_status_checks"]["contexts"])
    assert "Coverage" in contexts, (
        "the coverage floor is a merge gate (#514); leaving it out of the protection "
        "payload means a floor breach is visible and unblocking, which is the state the "
        "decision removed"
    )


def test_version_edit_preserves_comments_and_other_versions() -> None:
    manifest = '# comment\n[project]\nversion = "1.0.0" # keep\n[other]\nversion="9"\n'
    assert replace_manifest_version(manifest, "1.0.1") == manifest.replace('"1.0.0"', '"1.0.1"')
    with pytest.raises(ValueError):
        replace_manifest_version('[project]\nname="x"\n', "1.0.1")


def test_version_sync_rolls_back_after_a_partial_write(tmp_path: Path, monkeypatch) -> None:
    originals = {}
    for name in prepare_version_sync.SYNC_FILES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"original\n")
        originals[name] = target.read_bytes()
    monkeypatch.setattr(prepare_version_sync, "prepare",
                        lambda *_args: dict.fromkeys(prepare_version_sync.SYNC_FILES, b"changed\n"))
    write = Path.write_bytes
    failed = False

    def fail_once(path: Path, content: bytes) -> int:
        nonlocal failed
        if path.name == "__init__.py" and not failed:
            failed = True
            # The previous file really was changed before the failure.
            assert (tmp_path / "pyproject.toml").read_bytes() == b"changed\n"
            raise OSError("injected second-file write failure")
        return write(path, content)

    monkeypatch.setattr(Path, "write_bytes", fail_once)
    assert prepare_version_sync.main(["--root", str(tmp_path), "--tag", "v1.2.3",
                                      "--source-pr", "1", "--apply"]) == 2
    assert failed
    assert {name: (tmp_path / name).read_bytes() for name in originals} == originals


def test_version_sync_fingerprint_excludes_only_the_project() -> None:
    lock = ('[[package]]\nname="open-garden-planner"\nversion="1.0.0"\n'
            'source={editable="."}\n[[package]]\nname="example"\nversion="2.0"\n')
    assert third_party_packages(lock.encode()) == third_party_packages(
        lock.replace('version="1.0.0"', 'version="1.0.1"').encode()
    )
    assert third_party_packages(lock.encode()) != third_party_packages(
        lock.replace('version="2.0"', 'version="2.1"').encode()
    )


def test_documented_ci_inventory_matches_workflow_keys() -> None:
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = set(re.findall(r"^  ([\w-]+):$", workflow.split("jobs:", 1)[1], re.MULTILINE))
    docs = (root / "docs/07-deployment-view/README.md").read_text(encoding="utf-8")
    inventory = docs.split("| Job key |", 1)[1].split("\n\n", 1)[0]
    documented = set(re.findall(r"^\| `([\w-]+)` \|", inventory, re.MULTILINE))
    assert documented == jobs and len(jobs) == 10  # #601: partitions, serial coverage, aggregation


def test_finalization_has_no_bypass_and_uses_version_sync_prs() -> None:
    root = Path(__file__).resolve().parents[2]
    for tree in (".agents", ".claude"):
        text = (root / tree / "skills/finalize-us/SKILL.md").read_text(encoding="utf-8")
        assert "--admin" not in text
        assert "--match-head-commit VERIFIED_HEAD" in text
        assert "draft chore PR" in text and "prepare_version_sync.py" in text


@pytest.mark.parametrize("change", ["missing", "pending", "failed-coverage", "head", "skipped"])
def test_current_head_verifier_refuses_absence_and_failed_checks(change: str) -> None:
    pr = {"headRefOid": "abc", "baseRefName": "master", "statusCheckRollup": [
        {"name": "Test", "status": "COMPLETED", "conclusion": "SUCCESS"}]}
    assert check_differences(pr, "abc", ["Test"]) == []
    if change == "missing":
        pr["statusCheckRollup"] = []
    elif change == "head":
        pr["headRefOid"] = "replacement"
    elif change == "failed-coverage":
        pr["statusCheckRollup"].append(
            {"name": "Coverage", "status": "COMPLETED", "conclusion": "FAILURE"})
    elif change == "pending":
        pr["statusCheckRollup"][0]["status"] = "IN_PROGRESS"
    else:
        pr["statusCheckRollup"][0]["conclusion"] = "SKIPPED"
    assert check_differences(pr, "abc", ["Test"])


def test_functional_requirement_ids_are_unique() -> None:
    """Every FR id is DEFINED once — the whole file, not just the agent ids (#449).

    One requirement pasted twice — the defect #449 closed for FR-AGENT-27, and the one
    a merge conflict produced for FR-STACK-10 — is invisible to every other check: both
    lines read correctly, and a reader has no way to know which is normative. Only
    ``- **FR-...**`` LINES are definitions; a cross-reference ("see FR-STACK-08") is not.
    """
    root = Path(__file__).resolve().parents[2]
    text = (root / "docs/functional-requirements.md").read_text(encoding="utf-8")
    definitions = re.findall(
        r"^- \*\*(FR-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\*\*", text, re.MULTILINE
    )
    assert len(definitions) >= 350
    duplicates = sorted({value for value in definitions if definitions.count(value) > 1})
    assert duplicates == [], f"defined more than once: {', '.join(duplicates)}"
    assert "FR-AGENT-12a" in definitions
    assert "FR-AGENT-27" in definitions
    assert "FR-AGENT-29" in definitions
    assert "FR-STACK-10" in definitions

