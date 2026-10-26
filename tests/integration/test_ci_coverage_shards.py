"""Exercise real pytest/xdist selection and coverage merging, including refusals (#601)."""

from __future__ import annotations

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from coverage import Coverage
from scripts.ci_coverage_shard import shard_spec

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("value", ["bad", "0", "0/0", "2/2", "-1/2", "0/2/3"])
def test_invalid_shards_are_refused(value: str) -> None:
    with pytest.raises(pytest.UsageError):
        shard_spec(value)


def test_real_shards_cover_the_whole_suite_and_merge_branch_data(tmp_path: Path) -> None:
    """No overlap, no missing case, perf collected once, and both branch arms covered."""
    (tmp_path / "sample.py").write_text(
        "def answer(value):\n    if value:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )
    (tmp_path / "test_sample.py").write_text(
        "import pytest\nfrom sample import answer\n"
        "@pytest.mark.parametrize('value', [False, True])\n"
        "def test_answer(value):\n    assert answer(value) == int(value)\n"
        "@pytest.mark.perf\ndef test_perf():\n    assert answer(True) == 1\n",
        encoding="utf-8",
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers = perf\n", encoding="utf-8")
    files: list[Path] = []
    seen: list[set[str]] = []
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONUTF8="1")
    for name, args in (
        ("part0", ["-n", "2", "-m", "not perf", "-p", "scripts.ci_coverage_shard", "--coverage-shard=0/2"]),
        ("part1", ["-n", "2", "-m", "not perf", "-p", "scripts.ci_coverage_shard", "--coverage-shard=1/2"]),
        ("perf", ["-n", "0", "-m", "perf"]),
    ):
        data = tmp_path / f"{name}.coverage"
        files.append(data)
        report = tmp_path / f"{name}.xml"
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "test_sample.py", "-q", *args,
             "--cov=sample", "--cov-branch", "--cov-report=", f"--junitxml={report}"],
            cwd=tmp_path, env=dict(env, COVERAGE_FILE=str(data)),
            text=True, capture_output=True, timeout=60,
        )
        assert run.returncode == 0, run.stdout + run.stderr
        seen.append({case.attrib["name"] for case in ET.parse(report).iter("testcase")})
    assert seen[0].isdisjoint(seen[1])
    assert seen[0] | seen[1] == {"test_answer[False]", "test_answer[True]"}
    assert seen[2] == {"test_perf"}
    combined = Coverage(data_file=str(tmp_path / "combined"), branch=True)
    combined.combine([str(path) for path in files], strict=True)
    combined.save()
    combined.xml_report(outfile=str(tmp_path / "combined.xml"))
    summary = ET.parse(tmp_path / "combined.xml").getroot()
    assert summary.attrib["line-rate"] == "1"
    assert summary.attrib["branch-rate"] == "1"
    assert int(summary.attrib["branches-valid"]) == 2


def test_an_empty_real_shard_fails_instead_of_passing(tmp_path: Path) -> None:
    (tmp_path / "test_one.py").write_text("def test_one():\n    pass\n", encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "test_one.py", "-p", "scripts.ci_coverage_shard",
         "--coverage-shard=1/2", "-n", "0"],
        cwd=tmp_path, env=dict(os.environ, PYTHONPATH=str(ROOT)),
        text=True, capture_output=True, timeout=60,
    )
    assert run.returncode != 0
    assert "selected no tests" in run.stderr
