"""Daily release-download statistics: snapshots, deltas, estimates and the workflow wiring."""

import json
import re
from datetime import date
from pathlib import Path

import pytest
from scripts import download_stats as ds

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/download-stats.yml").read_text(encoding="utf-8")

D1, D2, D3, D6 = (date(2026, 10, d) for d in (1, 2, 3, 6))


def _release(tag: str, installer: int, manifest: int, prerelease: bool = False) -> dict:
    return {
        "tag_name": tag,
        "published_at": "2026-09-30T12:00:00Z",
        "prerelease": prerelease,
        "assets": [
            {"name": f"OpenGardenPlanner-{tag}-Setup.exe", "download_count": installer},
            {"name": "SHA256SUMS.txt", "download_count": manifest},
        ],
    }


def _history(*days: tuple[date, list[dict]]) -> list[ds.Row]:
    rows: list[ds.Row] = []
    for day, releases in days:
        rows = ds.merge(rows, ds.snapshot_rows(releases, day))
    return rows


def _delta(deltas: list[ds.Delta], day: date, asset_suffix: str, tag: str = "v1.0.0") -> ds.Delta:
    (found,) = [
        d for d in deltas
        if d.date_utc == day.isoformat() and d.tag == tag and d.asset.endswith(asset_suffix)
    ]
    return found


def test_first_snapshot_is_a_baseline_not_a_daily_value() -> None:
    deltas = ds.daily_deltas(_history((D1, [_release("v1.0.0", 500, 40)])))
    assert {d.kind for d in deltas} == {ds.KIND_BASELINE}
    assert all(d.delta is None for d in deltas)


def test_next_day_is_the_difference_of_the_counters() -> None:
    rows = _history(
        (D1, [_release("v1.0.0", 500, 40)]),
        (D2, [_release("v1.0.0", 517, 44)]),
    )
    deltas = ds.daily_deltas(rows)
    installer = _delta(deltas, D2, "-Setup.exe")
    assert (installer.delta, installer.days_covered, installer.kind) == (17, 1, ds.KIND_NORMAL)
    assert _delta(deltas, D2, "SHA256SUMS.txt").delta == 4


def test_a_skipped_day_is_one_delta_over_the_whole_span() -> None:
    rows = _history(
        (D3, [_release("v1.0.0", 100, 10)]),
        (D6, [_release("v1.0.0", 130, 16)]),
    )
    installer = _delta(ds.daily_deltas(rows), D6, "-Setup.exe")
    assert (installer.delta, installer.days_covered) == (30, 3), (
        "no even split over the missing days: the span is reported as it is"
    )


def test_falling_counter_is_a_reset_and_takes_the_new_count() -> None:
    rows = _history(
        (D1, [_release("v1.0.0", 500, 40)]),
        (D2, [_release("v1.0.0", 3, 1)]),
    )
    installer = _delta(ds.daily_deltas(rows), D2, "-Setup.exe")
    assert (installer.delta, installer.kind) == (3, ds.KIND_RESET)


def test_release_first_seen_after_the_baseline_counts_from_zero() -> None:
    rows = _history(
        (D1, [_release("v1.0.0", 500, 40)]),
        (D2, [_release("v1.0.0", 505, 41), _release("v1.1.0", 60, 9)]),
    )
    deltas = ds.daily_deltas(rows)
    new = _delta(deltas, D2, "-Setup.exe", tag="v1.1.0")
    assert (new.delta, new.kind) == (60, ds.KIND_NEW), (
        "downloads between publishing and the first run belong to that day"
    )
    assert _delta(deltas, D2, "-Setup.exe").delta == 5


def test_merge_replaces_the_same_date_and_keeps_a_stable_order() -> None:
    first = ds.snapshot_rows([_release("v1.0.0", 10, 1)], D1)
    again = ds.snapshot_rows([_release("v1.0.0", 12, 2)], D1)
    other = ds.snapshot_rows([_release("v1.0.0", 20, 3)], D2)
    merged = ds.merge(ds.merge(other, first), again)
    assert [(r.date_utc, r.asset, r.download_count) for r in merged] == [
        ("2026-10-01", "OpenGardenPlanner-v1.0.0-Setup.exe", 12),
        ("2026-10-01", "SHA256SUMS.txt", 2),
        ("2026-10-02", "OpenGardenPlanner-v1.0.0-Setup.exe", 20),
        ("2026-10-02", "SHA256SUMS.txt", 3),
    ]


def test_summary_splits_in_app_from_web_by_the_checksum_file() -> None:
    rows = _history(
        (D1, [_release("v1.0.0", 500, 40)]),
        (D2, [_release("v1.0.0", 517, 44)]),
    )
    summary = ds.render_summary(rows, ds.daily_deltas(rows))
    assert "| 2026-10-02 | 17 | 4 | 13 |  |" in summary
    assert "| v1.0.0 | 517 | 44 |" in summary


def test_summary_never_reports_more_in_app_than_installer_downloads() -> None:
    rows = _history(
        (D1, [_release("v1.0.0", 500, 40)]),
        (D2, [_release("v1.0.0", 501, 49)]),
    )
    summary = ds.render_summary(rows, ds.daily_deltas(rows))
    assert "| 2026-10-02 | 1 | 1 | 0 |  |" in summary


def test_summary_with_only_a_baseline_says_so() -> None:
    rows = _history((D1, [_release("v1.0.0", 500, 40)]))
    summary = ds.render_summary(rows, ds.daily_deltas(rows))
    assert "baseline recorded on 2026-10-01" in summary
    assert "| 2026-10-01 |" not in summary


def test_summary_marks_spans_and_resets() -> None:
    rows = _history(
        (D3, [_release("v1.0.0", 100, 10)]),
        (D6, [_release("v1.0.0", 4, 2)]),
    )
    summary = ds.render_summary(rows, ds.daily_deltas(rows))
    assert "covers 3 days; counter reset" in summary


def test_prerelease_flag_survives_the_csv_round_trip(tmp_path: Path) -> None:
    ds.run(tmp_path, "o/r", D1, None, lambda _r, _t: [_release("v2.0.0-rc1", 1, 1, True)])
    stored = ds.read_snapshots(tmp_path / ds.SNAPSHOT_FILE)
    assert stored and all(row.prerelease for row in stored)


def test_a_rerun_with_the_same_answer_changes_no_byte(tmp_path: Path) -> None:
    def fetch(_repo: str, _token: str | None) -> list[dict]:
        return [_release("v1.0.0", 500, 40)]

    ds.run(tmp_path, "o/r", D1, None, fetch)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    ds.run(tmp_path, "o/r", D1, None, fetch)
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    assert set(before) == {ds.SNAPSHOT_FILE, ds.DAILY_FILE, ds.SUMMARY_FILE}


def test_daily_csv_has_an_empty_delta_for_the_baseline(tmp_path: Path) -> None:
    ds.run(tmp_path, "o/r", D1, None, lambda _r, _t: [_release("v1.0.0", 500, 40)])
    lines = (tmp_path / ds.DAILY_FILE).read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(ds.DAILY_FIELDS)
    assert lines[1] == "2026-10-01,v1.0.0,OpenGardenPlanner-v1.0.0-Setup.exe,,0,baseline"


@pytest.mark.parametrize(
    "answer",
    [
        [{"assets": []}],
        [{"tag_name": "v1", "assets": "nope"}],
        [{"tag_name": "v1", "assets": [{"name": "a", "download_count": -1}]}],
        [{"tag_name": "v1", "assets": [{"name": "a"}]}],
        ["not a release"],
    ],
)
def test_unusable_api_answers_are_refused_and_write_nothing(
    tmp_path: Path, answer: list
) -> None:
    with pytest.raises(ds.StatsError):
        ds.run(tmp_path, "o/r", D1, None, lambda _r, _t: answer)
    assert list(tmp_path.iterdir()) == [], "a failed fetch must never leave a zero behind"


def test_unreadable_snapshot_file_is_an_error_not_an_empty_history(tmp_path: Path) -> None:
    (tmp_path / ds.SNAPSHOT_FILE).write_text("wrong,columns\n1,2\n", encoding="utf-8")
    with pytest.raises(ds.StatsError):
        ds.run(tmp_path, "o/r", D1, None, lambda _r, _t: [_release("v1.0.0", 1, 1)])
    assert (tmp_path / ds.SNAPSHOT_FILE).read_text(encoding="utf-8") == "wrong,columns\n1,2\n"


def test_fetch_rejects_a_repo_that_is_not_owner_slash_name() -> None:
    with pytest.raises(ds.StatsError):
        ds.fetch_releases("owner/name/../../x", None)


def test_cli_dry_run_from_a_file_and_failure_exit_code(tmp_path: Path) -> None:
    listing = tmp_path / "releases.json"
    listing.write_text(json.dumps([_release("v1.0.0", 5, 1)]), encoding="utf-8")
    out = tmp_path / "out"
    assert ds.main(["--data-dir", str(out), "--releases-json", str(listing),
                    "--today", "2026-10-01"]) == 0
    assert (out / ds.SUMMARY_FILE).exists()

    listing.write_text("{}", encoding="utf-8")
    assert ds.main(["--data-dir", str(out), "--releases-json", str(listing)]) == 2
    assert ds.main(["--data-dir", str(out), "--today", "01.10.2026"]) == 2


# ---- the workflow that runs it -------------------------------------------------------


def test_workflow_runs_daily_off_the_hour_and_on_demand() -> None:
    cron = re.search(r'cron:\s*"(\d+) (\d+) \* \* \*"', WORKFLOW)
    assert cron, "the schedule must be a once-a-day cron"
    assert cron.group(1) != "0", "not on the hour: scheduled runs there are delayed"
    assert "workflow_dispatch:" in WORKFLOW


def test_workflow_has_least_privilege_and_cannot_overlap() -> None:
    top = WORKFLOW.split("jobs:", 1)[0]
    assert re.search(r"^permissions:\n  contents: read$", top, re.MULTILINE)
    assert len(re.findall(r"contents: write", WORKFLOW)) == 1, "only the job may write"
    assert "group: download-stats" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW


def test_workflow_never_touches_master_or_releases() -> None:
    assert "git push origin HEAD:download-stats" in WORKFLOW
    assert not re.search(r"git push[^\n]*master", WORKFLOW)
    assert "gh release" not in WORKFLOW


def test_workflow_runs_the_script_that_this_module_tests() -> None:
    assert "python3 scripts/download_stats.py --data-dir data" in WORKFLOW
