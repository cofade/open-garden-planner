"""Calendar accounting, immutable migration and real JavaScript aggregation."""

import ast
import json
import re
import shutil
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree

import pytest
from scripts import download_stats as ds
from scripts import download_stats_report as report


def sample(
    tag: str, count: int, published: str, taken: str = "2026-08-07T00:00:00Z",
    *, asset_id: int = 1, prerelease: bool = False,
) -> ds.Row:
    return ds.Row(taken, tag, f"{tag}-Setup.exe", asset_id, count, published, prerelease)


def series(tmp_path: Path, seed_rows: list[ds.Row], *later: ds.Row) -> dict:
    return report.calendar_series([*seed_rows, *later], report.baseline(tmp_path, seed_rows), "o/r")


def total(payload: dict) -> float:
    return sum(day[key] for day in payload["days"] for key in report.COMPONENTS)


def test_owner_example_and_fractional_downloads(tmp_path: Path) -> None:
    rows = [sample("v1.21.0", 4, "2026-08-01T00:00:00Z"),
            sample("v1.21.1", 12, "2026-08-03T00:00:00Z", asset_id=2),
            sample("v1.22.0", 0, "2026-08-07T00:00:00Z", asset_id=3)]
    data = series(tmp_path, rows)
    assert [d["historical"] for d in data["days"][:6]] == [2, 2, 3, 3, 3, 3]
    assert total(data) == 16
    rows[0] = replace(rows[0], download_count=5)
    assert [d["historical"] for d in series(tmp_path, rows)["days"][:2]] == [2.5, 2.5]


def test_same_day_releases_use_their_hours_and_sum(tmp_path: Path) -> None:
    rows = [sample("v1", 6, "2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z"),
            sample("v2", 18, "2026-08-01T06:00:00Z", "2026-08-02T00:00:00Z", asset_id=2)]
    assert series(tmp_path, rows)["days"] == [
        {"date": "2026-08-01", "historical": 24., "observed": 0., "gap": 0.,
         "windows": [], "partial": False}]


def test_identical_publication_times_and_zero_duration_keep_counts(tmp_path: Path) -> None:
    rows = [sample("v1", 2, "2026-08-07T00:00:00Z"),
            sample("v2", 3, "2026-08-07T00:00:00Z", asset_id=2)]
    assert total(series(tmp_path, rows)) == 5


def test_live_increments_all_releases_and_checksums_are_separate(tmp_path: Path) -> None:
    seed = [sample("v1", 4, "2026-08-01T00:00:00Z", "2026-08-03T17:00:00Z"),
            sample("v2", 2, "2026-08-02T00:00:00Z", "2026-08-03T17:00:00Z", asset_id=2)]
    later = [replace(r, taken_at="2026-08-04T00:17:00Z", download_count=r.download_count + 3)
             for r in seed]
    later.append(replace(later[0], asset="SHA256SUMS.txt", asset_id=99, download_count=1000))
    data = series(tmp_path, seed, *later)
    assert total(data) == pytest.approx(12)
    assert data["days"][-1]["date"] == "2026-08-03"
    assert data["days"][-1]["observed"] == 6
    assert data["days"][-1]["historical"] > 0
    assert data["days"][-1]["windows"] == [{
        "from": "2026-08-03T17:00:00Z", "to": "2026-08-04T00:17:00Z", "kind": "normal"}]


def test_gaps_are_estimates_and_zero_days_remain_zero(tmp_path: Path) -> None:
    first = sample("v1", 0, "2026-08-01T00:00:00Z", "2026-08-02T00:17:00Z")
    second = replace(first, taken_at="2026-08-05T00:17:00Z", download_count=6)
    third = replace(second, taken_at="2026-08-06T00:17:00Z")
    data = series(tmp_path, [first], second, third)
    by_date = {d["date"]: d for d in data["days"]}
    assert [by_date[f"2026-08-0{d}"]["gap"] for d in (2, 3, 4)] == [2, 2, 2]
    assert by_date["2026-08-05"]["observed"] == 0
    assert by_date["2026-08-05"]["windows"]
    assert min(by_date) == "2026-08-01" and max(by_date) == "2026-08-05"
    assert total(data) == 6


def test_asset_missing_for_one_snapshot_retains_its_own_window(tmp_path: Path) -> None:
    first = sample("v1", 4, "2026-08-01T00:00:00Z", "2026-08-02T00:17:00Z")
    other = replace(first, tag="v2", asset_id=2)
    middle = replace(other, taken_at="2026-08-03T00:17:00Z")
    last = replace(first, taken_at="2026-08-04T00:17:00Z", download_count=8)
    data = series(tmp_path, [first, other], middle, last)
    assert [d["gap"] for d in data["days"][-2:]] == [2, 2]


def test_prerelease_promotion_and_reset_are_admitted_once(tmp_path: Path) -> None:
    first = sample("v1", 5, "2026-08-01T00:00:00Z", "2026-08-02T00:17:00Z", prerelease=True)
    promoted = replace(first, prerelease=False, download_count=8, taken_at="2026-08-03T00:17:00Z")
    reset = replace(promoted, download_count=2, taken_at="2026-08-04T00:17:00Z")
    data = series(tmp_path, [first], promoted, reset)
    assert total(data) == 10
    assert [d["windows"][0]["kind"] for d in data["days"]] == ["new", "reset"]


def test_new_asset_after_midnight_is_not_plotted_before_publication(tmp_path: Path) -> None:
    first = sample("v1", 0, "2026-08-01T00:00:00Z", "2026-08-02T00:17:00Z")
    new = sample("v2", 3, "2026-08-03T00:05:00Z", "2026-08-03T00:17:00Z", asset_id=2)
    data = series(tmp_path, [first], new)
    assert data["days"][-1]["date"] == "2026-08-03"
    assert data["days"][-1]["observed"] == 3
    assert data["days"][-1]["partial"]
    assert data["days"][-1]["windows"][0]["from"] == new.published_at


def test_temporary_prerelease_does_not_readmit_a_final_counter(tmp_path: Path) -> None:
    first = sample("v1", 5, "2026-08-01T00:00:00Z", "2026-08-02T00:17:00Z")
    hidden = replace(first, prerelease=True, download_count=6, taken_at="2026-08-03T00:17:00Z")
    visible = replace(first, download_count=7, taken_at="2026-08-04T00:17:00Z")
    data = series(tmp_path, [first], hidden, visible)
    assert total(data) == pytest.approx(7)
    assert sum(day["gap"] for day in data["days"]) == 2
    assert data["days"][-1]["windows"][0] == {
        "from": first.taken_at, "to": visible.taken_at, "kind": "normal"}


def test_repeated_promotions_of_an_initially_prerelease_asset_count_once(tmp_path: Path) -> None:
    first = sample("v1", 5, "2026-08-01T00:00:00Z", "2026-08-02T00:17:00Z", prerelease=True)
    promoted = replace(first, download_count=7, prerelease=False, taken_at="2026-08-03T00:17:00Z")
    hidden = replace(first, download_count=9, taken_at="2026-08-04T00:17:00Z")
    restored = replace(promoted, download_count=10, taken_at="2026-08-05T00:17:00Z")
    data = series(tmp_path, [first], promoted, hidden, restored)
    assert total(data) == 10
    assert {w["kind"] for day in data["days"] for w in day["windows"]} == {"new", "normal"}


def test_reset_during_excluded_interval_retains_the_last_admitted_counter(tmp_path: Path) -> None:
    first = sample("v1", 10, "2026-08-01T00:00:00Z", "2026-08-02T00:17:00Z")
    hidden = replace(first, download_count=3, prerelease=True, taken_at="2026-08-03T00:17:00Z")
    restored = replace(first, download_count=4, taken_at="2026-08-04T00:17:00Z")
    data = series(tmp_path, [first], hidden, restored)
    assert total(data) == pytest.approx(14)
    assert data["days"][-1]["windows"][0]["kind"] == "reset"


@pytest.mark.parametrize("hidden_counts,expected", [([3], 22), ([3, 2], 25)])
def test_observed_resets_survive_recovery_above_old_counter(
    tmp_path: Path, hidden_counts: list[int], expected: int,
) -> None:
    first = sample("v1", 10, "2026-08-01T00:00:00Z", "2026-08-02T00:17:00Z")
    hidden = [replace(first, download_count=value, prerelease=True,
                      taken_at=f"2026-08-0{index+3}T00:17:00Z")
              for index, value in enumerate(hidden_counts)]
    restored = replace(first, download_count=12, taken_at="2026-08-06T00:17:00Z")
    data = series(tmp_path, [first], *hidden, restored)
    assert total(data) == pytest.approx(expected)
    assert data["days"][-1]["windows"][0]["kind"] == "reset"


def test_a_same_date_rerun_freezes_seed_before_replacing_snapshot(tmp_path: Path) -> None:
    def fetch(count):
        return lambda _r, _t: [{"tag_name": "v1", "published_at": "2026-08-01T00:00:00Z",
                                "assets": [{"id": 1, "name": "v1-Setup.exe", "download_count": count}]}]
    ds.run(tmp_path, "o/r", report.instant("2026-08-03T10:00:00Z"), None, fetch(5))
    frozen = (tmp_path / report.BASELINE_FILE).read_bytes()
    ds.run(tmp_path, "o/r", report.instant("2026-08-03T18:00:00Z"), None, fetch(8))
    assert (tmp_path / report.BASELINE_FILE).read_bytes() == frozen
    payload = json.loads((tmp_path / "site/timeline.json").read_text())
    assert total(payload) == pytest.approx(8)
    assert sum(d["historical"] for d in payload["days"]) == pytest.approx(5)
    assert ds.read_snapshots(tmp_path)[0].download_count == 8
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert ds.main(["--data-dir", str(tmp_path), "--repo", "o/r", "--report-only"]) == 0
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_migration_uses_earliest_stored_snapshot_not_new_api_counters(tmp_path: Path) -> None:
    old = sample("v1", 5, "2026-08-01T00:00:00Z", "2026-08-03T17:00:00Z")
    ds.write_outputs(tmp_path, [old], ds.daily_deltas([old]))  # pre-chart installation
    releases = [{"tag_name": "v1", "published_at": old.published_at,
                 "assets": [{"name": old.asset, "id": 1, "download_count": 9}]}]
    ds.run(tmp_path, "o/r", report.instant("2026-08-04T00:17:00Z"), None, lambda _r, _t: releases)
    seed = json.loads((tmp_path / report.BASELINE_FILE).read_text())
    assert seed["assets"][0]["download_count"] == 5
    assert seed["taken_at"] == old.taken_at
    assert total(json.loads((tmp_path / "site/timeline.json").read_text())) == pytest.approx(9)


def test_invalid_baseline_fails_without_changing_any_file(tmp_path: Path) -> None:
    (tmp_path / report.BASELINE_FILE).write_text('{"version":99}', encoding="utf-8")
    with pytest.raises(ValueError, match="baseline"):
        report.prepare_report(tmp_path, [sample("v1", 2, "2026-08-01T00:00:00Z")], [], "o/r")
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("payload", [None, {"version": 1}, {"version": 1, "taken_at": []},
                                    {"version": 1, "taken_at": "2026-08-01T00:00:00Z",
                                     "assets": [{}]}])
def test_malformed_seed_is_an_exit_code_not_a_traceback(tmp_path: Path, payload: object) -> None:
    row = sample("v1", 5, "2026-08-01T00:00:00Z")
    ds.write_outputs(tmp_path, [row], ds.daily_deltas([row]))
    (tmp_path / report.BASELINE_FILE).write_text(json.dumps(payload))
    assert ds.main(["--data-dir", str(tmp_path), "--report-only"]) == 2


def test_preview_is_valid_svg_and_translations_have_identical_keys(tmp_path: Path) -> None:
    catalogs = json.loads((report.WEB / "messages.json").read_text(encoding="utf-8"))
    registry = ast.parse((report.WEB.parents[1] / "src/open_garden_planner/core/i18n.py").read_text())
    supported = next(ast.literal_eval(node.value) for node in registry.body
                     if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
                     and node.target.id == "SUPPORTED_LANGUAGES")
    assert set(catalogs) == set(supported)
    assert all(set(catalog) == set(catalogs["en"]) for catalog in catalogs.values())
    assert all(value.strip() for catalog in catalogs.values() for value in catalog.values())
    html = (report.WEB / "index.html").read_text(encoding="utf-8")
    assert set(re.findall(r'data-i18n="([^"]+)"', html)) <= set(catalogs["en"])
    data = series(tmp_path, [sample("v1", 5, "2026-08-01T00:00:00Z")])
    root = ElementTree.fromstring(report.preview_svg(data, catalogs["de"]))
    titles = [e.text for e in root.iter("{http://www.w3.org/2000/svg}title")]
    assert titles[0] == "Installer-Downloads"
    assert any("2026-08-01" in text for text in titles[1:])


@pytest.mark.skipif(shutil.which("node") is None, reason="browser aggregation requires Node")
@pytest.mark.parametrize("grain", ["day", "week", "month", "year"])
def test_actual_browser_aggregation_preserves_counts_and_iso_boundaries(grain: str) -> None:
    start = date(2023, 12, 29)
    days = [{"date": (start + timedelta(days=i)).isoformat(), "historical": .25,
             "observed": i % 4, "gap": .5, "partial": False, "windows": []}
            for i in range(430)]
    script = """
require(process.argv[1]);
const {aggregate,selectRange,bounds} = globalThis.DownloadChart;
const data = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const selected = selectRange(data, '365');
console.log(JSON.stringify({groups:aggregate(selected,process.argv[2]),
  week:bounds('2024-01-01','week'),leap:bounds('2024-02-29','month')}));
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(report.WEB / "chart.js"), grain],
        input=json.dumps(days), capture_output=True, text=True, check=True,
    )
    actual = json.loads(result.stdout)
    assert sum(g["total"] for g in actual["groups"]) == sum(
        d[k] for d in days[-365:] for k in report.COMPONENTS)
    assert actual["week"] == ["2024-01-01", "2024-01-07"]
    assert actual["leap"] == ["2024-02-01", "2024-02-29"]
    if grain != "day":
        assert actual["groups"][0]["partial"] or actual["groups"][-1]["partial"]


def test_workflow_persists_before_upload_and_deploys_with_separate_permissions() -> None:
    text = (Path(__file__).resolve().parents[2] / ".github/workflows/download-stats.yml").read_text()
    assert 'cron: "17 0 * * *"' in text
    assert text.index("name: Commit and push") < text.index("name: Upload the static website")
    snapshot, deploy = text.split("  deploy:\n")
    assert "pages: write" not in snapshot and "id-token: write" not in snapshot
    assert "needs: snapshot" in deploy and "pages: write" in deploy and "id-token: write" in deploy
    assert "environment:" in deploy and "name: github-pages" in deploy
