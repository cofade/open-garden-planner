"""Portable exact-count file floors share the existing coverage parser/gate."""
import json

import pytest
from scripts.audit_metrics import coverage_section
from scripts.check_coverage_floors import file_regressions, main, validate_file_floors

TARGET = "core/tools/constraint_tool.py"


def report_xml(path, covered=60, filename=TARGET, source="/checkout/src/open_garden_planner"):
    lines = "".join(f'<line number="{i}" hits="{int(i <= covered)}"/>' for i in range(1, 101))
    lines = lines.replace('<line number="1" hits="1"/>',
                          '<line number="1" hits="1" branch="true" condition-coverage="50% (1/2)"/>')
    path.write_text(f'<coverage><sources><source>{source}</source></sources><packages>'
                    f'<package><classes><class filename="{filename}"><lines>{lines}</lines>'
                    '</class></classes></package></packages></coverage>', encoding="utf-8")
    return path


def floors_json(path, *, files=True, package_floor=40):
    data = {"schema_version": 1, "non_ui_definition": "all packages except ui",
            "line_floors": {"core": package_floor}}
    if files:
        data["file_line_floors"] = {TARGET: 60}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("covered,expected", [(59, 1), (60, 0), (61, 0)])
def test_cli_exact_boundary(tmp_path, capsys, covered, expected):
    xml = report_xml(tmp_path / "c.xml", covered)
    floors = floors_json(tmp_path / "floors.json")
    report = tmp_path / "report.json"
    assert main(["--xml", str(xml), "--floors", str(floors), "--report", str(report)]) == expected
    result = json.loads(report.read_text())
    assert result["regressions"] == []
    counts = result["per_file"][TARGET]
    assert counts == {"statements": 100, "covered_statements": covered,
                      "branches": 2, "covered_branches": 1, "line_pct": float(covered), "branch_pct": 50.0}
    assert bool(result["file_regressions"]) == bool(expected)


def test_rounded_sixty_is_not_exact_sixty():
    assert file_regressions({TARGET: {"statements": 2340, "covered_statements": 1403}}, {TARGET: 60})
    assert not file_regressions({TARGET: {"statements": 2340, "covered_statements": 1404}}, {TARGET: 60})


@pytest.mark.parametrize("filename,source", [
    (TARGET, "/checkout/src/open_garden_planner"),
    ("src/open_garden_planner/" + TARGET, "/checkout"),
    ("C:/checkout/src/open_garden_planner/" + TARGET, "C:/checkout"),
    ("C:\\checkout\\src\\open_garden_planner\\core\\tools\\constraint_tool.py", "C:\\checkout"),
])
def test_normalized_file_counts(tmp_path, filename, source):
    result = coverage_section(report_xml(tmp_path / "c.xml", filename=filename, source=source))
    assert list(result["per_file"]) == [TARGET]
    assert result["per_file"][TARGET]["covered_statements"] == 60


@pytest.mark.parametrize("files,package_floor,expected", [(False, 40, 0), (False, 61, 1), (True, 61, 1)])
def test_existing_package_floors_still_apply(tmp_path, files, package_floor, expected):
    xml = report_xml(tmp_path / "c.xml")
    floors = floors_json(tmp_path / "f.json", files=files, package_floor=package_floor)
    assert main(["--xml", str(xml), "--floors", str(floors)]) == expected


def test_missing_required_file_fails(tmp_path):
    xml = report_xml(tmp_path / "c.xml", filename="core/other.py")
    floors = floors_json(tmp_path / "f.json")
    assert main(["--xml", str(xml), "--floors", str(floors)]) == 1


@pytest.mark.parametrize("corruption", ["not-xml", "negative-hits", "missing-hits", "bad-branch", "duplicate-line", "invalid-number"])
def test_malformed_report_fails_closed(tmp_path, corruption):
    xml = report_xml(tmp_path / "c.xml")
    source = xml.read_text()
    if corruption == "not-xml":
        source = "invalid"
    elif corruption == "negative-hits":
        source = source.replace('hits="1"', 'hits="-1"', 1)
    elif corruption == "missing-hits":
        source = source.replace(' hits="1"', '', 1)
    elif corruption == "bad-branch":
        source = source.replace('50% (1/2)', 'broken')
    elif corruption == "duplicate-line":
        source = source.replace('number="2"', 'number="1"')
    else:
        source = source.replace('number="1"', 'number="oops"', 1)
    xml.write_text(source)
    floors = floors_json(tmp_path / "f.json")
    assert main(["--xml", str(xml), "--floors", str(floors)]) == 2


@pytest.mark.parametrize("value", [None, [], {TARGET: True}, {TARGET: 60.0}, {TARGET: -1},
                                   {TARGET: 101}, {"../x.py": 60}, {"/x.py": 60},
                                   {"core\\x.py": 60}, {"core//x.py": 60}, {"C:/x.py": 60}])
def test_invalid_file_floor_metadata(value):
    with pytest.raises(ValueError):
        validate_file_floors({"file_line_floors": value})


def test_linux_rebaseline_preserves_file_floor(tmp_path, monkeypatch):
    import scripts.check_coverage_floors as gate
    monkeypatch.setattr(gate.sys, "platform", "linux")
    monkeypatch.setattr(gate.sys, "version_info", (3, 11))
    xml = report_xml(tmp_path / "c.xml", 75)
    floors = floors_json(tmp_path / "f.json")
    assert main(["--xml", str(xml), "--floors", str(floors), "--write-floors"]) == 0
    data = json.loads(floors.read_text())
    assert data["file_line_floors"] == {TARGET: 60}
    assert data["line_floors"] == {"core": 75}
