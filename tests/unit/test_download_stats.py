"""Release-download statistics: snapshots, deltas, summary, fetching and the workflow wiring."""

import io
import json
import re
import urllib.error
import urllib.request
import zlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts import download_stats as ds

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/download-stats.yml").read_text(encoding="utf-8")

T1 = "2026-10-01T03:17:00Z"
T2 = "2026-10-02T03:17:00Z"
T3 = "2026-10-03T03:17:00Z"
T6 = "2026-10-06T03:17:00Z"


def _id(tag: str, what: str) -> int:
    return zlib.crc32(f"{tag}/{what}".encode())


def _release(
    tag: str, installer: int, manifest: int, *, prerelease: bool = False, draft: bool = False,
    installer_id: int | None = None,
) -> dict:
    return {
        "tag_name": tag,
        "published_at": "2026-09-30T12:00:00Z",
        "prerelease": prerelease,
        "draft": draft,
        "assets": [
            {"id": installer_id or _id(tag, "setup"), "name": f"OpenGardenPlanner-{tag}-Setup.exe",
             "download_count": installer},
            {"id": _id(tag, "sums"), "name": "SHA256SUMS.txt", "download_count": manifest},
            {"id": _id(tag, "sbom"), "name": f"sbom-{tag}.json", "download_count": 99},
        ],
    }


def _history(*days: tuple[str, list[dict]]) -> list[ds.Row]:
    rows: list[ds.Row] = []
    for taken_at, releases in days:
        rows = ds.merge(rows, ds.snapshot_rows(releases, taken_at))
    return rows


def _delta(deltas: list[ds.Delta], taken_at: str, suffix: str, tag: str = "v1.0.0") -> ds.Delta:
    (found,) = [
        d for d in deltas if d.taken_at == taken_at and d.tag == tag and d.asset.endswith(suffix)
    ]
    return found


# ---- snapshots -----------------------------------------------------------------------


def test_only_installer_and_checksum_of_published_releases_are_recorded() -> None:
    rows = ds.snapshot_rows(
        [_release("v1.0.0", 5, 1), _release("v1.1.0", 9, 9, draft=True)], T1
    )
    assert [r.asset for r in rows] == ["OpenGardenPlanner-v1.0.0-Setup.exe", "SHA256SUMS.txt"]


@pytest.mark.parametrize(
    "answer",
    [
        [{"assets": []}],
        [{"tag_name": "v1", "assets": "nope"}],
        [{"tag_name": "v1", "assets": [{"id": 1, "name": "a-Setup.exe", "download_count": -1}]}],
        [{"tag_name": "v1", "assets": [{"id": 1, "name": "a-Setup.exe", "download_count": True}]}],
        [{"tag_name": "v1", "assets": [{"name": "a-Setup.exe", "download_count": 1}]}],
        [{"tag_name": "v1", "assets": [{"id": 1, "download_count": 1}]}],
        ["not a release"],
    ],
)
def test_unusable_api_answers_are_refused_and_write_nothing(tmp_path: Path, answer: list) -> None:
    with pytest.raises(ds.StatsError):
        ds.run(tmp_path, "o/r", _at(T1), None, lambda _r, _t: answer)
    assert list(tmp_path.iterdir()) == [], "a failed fetch must never leave a zero behind"


def _at(taken_at: str) -> datetime:
    return datetime.strptime(taken_at, ds.TIMESTAMP_FORMAT).replace(tzinfo=UTC)


@pytest.mark.parametrize("answer", [[], [_release("v1", 1, 1, draft=True)]])
def test_a_listing_without_tracked_assets_is_an_error_not_a_green_run(
    tmp_path: Path, answer: list
) -> None:
    with pytest.raises(ds.StatsError, match="no installer or checksum"):
        ds.run(tmp_path, "o/r", _at(T1), None, lambda _r, _t: answer)


def test_a_listing_that_lost_most_assets_is_refused(tmp_path: Path) -> None:
    many = [_release(f"v1.0.{n}", 1, 1) for n in range(10)]
    ds.run(tmp_path, "o/r", _at(T1), None, lambda _r, _t: many)
    with pytest.raises(ds.StatsError, match="lost most of them"):
        ds.run(tmp_path, "o/r", _at(T2), None, lambda _r, _t: many[:2])
    ds.run(tmp_path, "o/r", _at(T2), None, lambda _r, _t: many[:6])


# ---- deltas --------------------------------------------------------------------------


def test_first_snapshot_is_a_baseline_not_a_value() -> None:
    deltas = ds.daily_deltas(_history((T1, [_release("v1.0.0", 500, 40)])))
    assert {d.kind for d in deltas} == {ds.KIND_BASELINE}
    assert all(d.delta is None and d.hours is None for d in deltas)


def test_next_snapshot_is_the_difference_and_carries_its_window_in_hours() -> None:
    rows = _history((T1, [_release("v1.0.0", 500, 40)]), (T2, [_release("v1.0.0", 517, 44)]))
    deltas = ds.daily_deltas(rows)
    installer = _delta(deltas, T2, "-Setup.exe")
    assert (installer.delta, installer.hours, installer.kind) == (17, 24.0, ds.KIND_NORMAL)
    assert _delta(deltas, T2, "SHA256SUMS.txt").delta == 4


def test_a_skipped_day_is_one_value_over_the_whole_window() -> None:
    rows = _history((T3, [_release("v1.0.0", 100, 10)]), (T6, [_release("v1.0.0", 130, 16)]))
    installer = _delta(ds.daily_deltas(rows), T6, "-Setup.exe")
    assert (installer.delta, installer.hours) == (30, 72.0)


def test_a_manual_rerun_the_same_day_reports_the_real_window_not_a_day() -> None:
    """The bootstrap run after a merge happens at an arbitrary time of day."""
    rows = _history(
        (T1, [_release("v1.0.0", 500, 40)]),
        ("2026-10-02T14:05:00Z", [_release("v1.0.0", 510, 41)]),
        ("2026-10-02T15:00:00Z", [_release("v1.0.0", 512, 41)]),
    )
    installer = _delta(ds.daily_deltas(rows), "2026-10-02T15:00:00Z", "-Setup.exe")
    assert (installer.delta, installer.hours) == (12, 35.7), (
        "the later run replaced the earlier one; its window is measured, not assumed to be 24 h"
    )


def test_falling_counter_is_a_reset_and_takes_the_new_count() -> None:
    rows = _history((T1, [_release("v1.0.0", 500, 40)]), (T2, [_release("v1.0.0", 3, 1)]))
    installer = _delta(ds.daily_deltas(rows), T2, "-Setup.exe")
    assert (installer.delta, installer.kind) == (3, ds.KIND_RESET)


def test_a_reuploaded_asset_is_new_even_if_its_count_is_higher() -> None:
    """Keyed by asset id: a new upload under the same name must not undercount."""
    rows = _history(
        (T1, [_release("v1.0.0", 5, 1)]),
        (T2, [_release("v1.0.0", 8, 1, installer_id=424242)]),
    )
    installer = _delta(ds.daily_deltas(rows), T2, "-Setup.exe")
    assert (installer.delta, installer.kind) == (8, ds.KIND_NEW)


def test_release_first_seen_after_the_baseline_counts_from_zero_over_the_window() -> None:
    rows = _history(
        (T1, [_release("v1.0.0", 500, 40)]),
        (T3, [_release("v1.0.0", 505, 41), _release("v1.1.0", 60, 9)]),
    )
    deltas = ds.daily_deltas(rows)
    new = _delta(deltas, T3, "-Setup.exe", tag="v1.1.0")
    assert (new.delta, new.kind, new.hours) == (60, ds.KIND_NEW, 48.0)
    assert _delta(deltas, T3, "-Setup.exe").delta == 5


def test_merge_replaces_the_same_date_and_keeps_a_stable_order() -> None:
    first = ds.snapshot_rows([_release("v1.0.0", 10, 1)], T1)
    again = ds.snapshot_rows([_release("v1.0.0", 12, 2)], "2026-10-01T09:00:00Z")
    other = ds.snapshot_rows([_release("v1.0.0", 20, 3)], T2)
    merged = ds.merge(ds.merge(other, first), again)
    assert [(r.taken_at, r.asset, r.download_count) for r in merged] == [
        ("2026-10-01T09:00:00Z", "OpenGardenPlanner-v1.0.0-Setup.exe", 12),
        ("2026-10-01T09:00:00Z", "SHA256SUMS.txt", 2),
        (T2, "OpenGardenPlanner-v1.0.0-Setup.exe", 20),
        (T2, "SHA256SUMS.txt", 3),
    ]


# ---- summary -------------------------------------------------------------------------


def _summary(*days: tuple[str, list[dict]]) -> str:
    rows = _history(*days)
    return ds.render_summary(rows, ds.daily_deltas(rows))


def test_summary_reports_the_raw_counters_and_claims_no_in_app_web_split() -> None:
    summary = _summary((T1, [_release("v1.0.0", 500, 40)]), (T2, [_release("v1.0.0", 517, 44)]))
    assert "| 2026-10-02 03:17 | 24 | 17 | 4 |  |" in summary
    assert "| v1.0.0 | 517 | 44 |" in summary
    assert "| **All** | 517 | 44 |" in summary
    assert "not split into in-app and web" in summary
    assert "(est.)" not in summary
    assert "v1.30.3" in summary, "the version floor of the checksum fetch is disclosed"


def test_summary_flags_windows_that_are_not_a_day_and_resets() -> None:
    summary = _summary((T3, [_release("v1.0.0", 100, 10)]), (T6, [_release("v1.0.0", 4, 2)]))
    assert "window is not about a day; counter reset" in summary


def test_summary_with_only_a_baseline_says_so() -> None:
    summary = _summary((T1, [_release("v1.0.0", 500, 40)]))
    assert "the baseline was taken on 2026-10-01T03:17:00Z" in summary
    assert "| 2026-10-01 03:17 |" not in summary


def test_summary_leaves_prereleases_out_of_the_table_and_sorts_totals_by_version() -> None:
    summary = _summary(
        (T1, [_release("v1.9.3", 1, 1), _release("v1.34.2", 1, 1), _release("v2.0.0-rc1", 1, 1, prerelease=True)]),
        (T2, [_release("v1.9.3", 1, 1), _release("v1.34.2", 3, 1), _release("v2.0.0-rc1", 50, 50, prerelease=True)]),
    )
    assert "| 2026-10-02 03:17 | 24 | 2 | 0 |  |" in summary
    tags = re.findall(r"^\| (v[\w.-]+) \|", summary, re.MULTILINE)
    assert tags == ["v2.0.0-rc1", "v1.34.2", "v1.9.3"]


# ---- files ---------------------------------------------------------------------------


def _run(tmp_path: Path, taken_at: str, *releases: dict) -> None:
    ds.run(tmp_path, "o/r", _at(taken_at), None, lambda _r, _t: list(releases))


def test_files_are_split_per_month(tmp_path: Path) -> None:
    _run(tmp_path, "2026-10-31T03:17:00Z", _release("v1.0.0", 5, 1))
    _run(tmp_path, "2026-11-01T03:17:00Z", _release("v1.0.0", 7, 1))
    assert sorted(p.name for p in (tmp_path / ds.SNAPSHOT_DIR).iterdir()) == [
        "2026-10.csv", "2026-11.csv",
    ]
    daily = (tmp_path / ds.DAILY_DIR / "2026-11.csv").read_text(encoding="utf-8").splitlines()
    assert daily[0] == ",".join(ds.DAILY_FIELDS)
    assert len(daily) == 3 and daily[1].endswith(",2,24,normal"), (
        "a value belongs to the month of the snapshot that ends its window"
    )
    assert len(ds.read_snapshots(tmp_path)) == 4


def test_a_rerun_with_the_same_answer_changes_no_byte(tmp_path: Path) -> None:
    _run(tmp_path, T1, _release("v1.0.0", 500, 40))
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    _run(tmp_path, T1, _release("v1.0.0", 500, 40))
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_daily_csv_has_an_empty_value_for_the_baseline(tmp_path: Path) -> None:
    _run(tmp_path, T1, _release("v1.0.0", 500, 40))
    lines = (tmp_path / ds.DAILY_DIR / "2026-10.csv").read_text(encoding="utf-8").splitlines()
    assert lines[1].startswith(f"{T1},v1.0.0,OpenGardenPlanner-v1.0.0-Setup.exe,")
    assert lines[1].endswith(",,,baseline")


@pytest.mark.parametrize(
    "content",
    [
        "wrong,columns\n1,2\n",
        ",".join(ds.SNAPSHOT_FIELDS) + f"\n{T1},v1,a-Setup.exe,1\n",  # short row
        ",".join(ds.SNAPSHOT_FIELDS) + f"\n{T1},v1,a-Setup.exe,1,-4,x,0\n",  # negative count
        ",".join(ds.SNAPSHOT_FIELDS) + "\n2026-11-01T00:00:00Z,v1,a-Setup.exe,1,4,x,0\n",  # month
        ",".join(ds.SNAPSHOT_FIELDS)
        + f"\n{T1},v1,a-Setup.exe,1,4,x,0\n{T1},v1,a-Setup.exe,1,4,x,0\n",  # duplicate
    ],
)
def test_a_damaged_snapshot_file_is_an_error_not_an_empty_history(
    tmp_path: Path, content: str
) -> None:
    path = tmp_path / ds.SNAPSHOT_DIR / "2026-10.csv"
    path.parent.mkdir()
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ds.StatsError):
        _run(tmp_path, T2, _release("v1.0.0", 1, 1))
    assert path.read_text(encoding="utf-8") == content


def test_cli_dry_run_from_a_file_and_the_exit_code_contract(tmp_path: Path) -> None:
    listing = tmp_path / "releases.json"
    listing.write_text(json.dumps([_release("v1.0.0", 5, 1)]), encoding="utf-8")
    out = tmp_path / "out"
    args = ["--data-dir", str(out), "--releases-json", str(listing)]
    assert ds.main([*args, "--now", T1]) == 0
    assert (out / ds.SUMMARY_FILE).exists()

    assert ds.main([*args, "--now", "01.10.2026"]) == 2
    listing.write_text("{}", encoding="utf-8")
    assert ds.main([*args, "--now", T2]) == 2
    short = out / ds.SNAPSHOT_DIR / "2026-10.csv"
    short.write_text(",".join(ds.SNAPSHOT_FIELDS) + "\nx\n", encoding="utf-8")
    listing.write_text(json.dumps([_release("v1.0.0", 5, 1)]), encoding="utf-8")
    assert ds.main([*args, "--now", T2]) == 2, "a damaged file is exit 2, never a traceback"


# ---- fetching ------------------------------------------------------------------------


class _Response(io.BytesIO):
    def __init__(self, payload: object, link: str = "") -> None:
        super().__init__(json.dumps(payload).encode())
        self.headers = {"Link": link} if link else {}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _pages(*pages: object) -> tuple[list[urllib.request.Request], ds.OpenUrl]:
    """A fake API serving ``pages`` in order; the last one has no ``next`` link."""
    seen: list[urllib.request.Request] = []

    def open_url(request: urllib.request.Request) -> _Response:
        index = len(seen)
        seen.append(request)
        last = index == len(pages) - 1
        link = "" if last else f'<{ds._API_PREFIX}repos/o/r/releases?page={index + 2}>; rel="next"'
        return _Response(pages[index], link)

    return seen, open_url


def test_fetch_pages_by_number_while_the_api_announces_a_next_page() -> None:
    seen, open_url = _pages([{"n": i} for i in range(100)], [{"n": i} for i in range(99)])
    releases = ds.fetch_releases("o/r", None, open_url)
    assert len(releases) == 199
    assert [r.full_url for r in seen] == [
        f"{ds._API_PREFIX}repos/o/r/releases?per_page=100&page=1",
        f"{ds._API_PREFIX}repos/o/r/releases?per_page=100&page=2",
    ]


def test_fetch_stops_on_a_full_last_page_without_asking_for_a_phantom_page() -> None:
    seen, open_url = _pages([{"n": i} for i in range(100)])
    assert len(ds.fetch_releases("o/r", None, open_url)) == 100
    assert len(seen) == 1, "the API's own Link header ends the loop, not the page length"


def test_fetch_sends_the_token_only_when_there_is_one() -> None:
    without, open_without = _pages([])
    with_token, open_with = _pages([])
    ds.fetch_releases("o/r", None, open_without)
    ds.fetch_releases("o/r", "secret", open_with)
    assert without[0].get_header("Authorization") is None
    assert with_token[0].get_header("Authorization") == "Bearer secret"


def test_fetch_turns_http_errors_and_wrong_shapes_into_stats_errors() -> None:
    def forbidden(request: urllib.request.Request) -> _Response:
        raise urllib.error.HTTPError(request.full_url, 403, "rate limit", {}, None)  # type: ignore[arg-type]

    with pytest.raises(ds.StatsError, match="page 1"):
        ds.fetch_releases("o/r", None, forbidden)
    _, not_a_list = _pages({"message": "oops"})
    with pytest.raises(ds.StatsError, match="not a list"):
        ds.fetch_releases("o/r", None, not_a_list)


def test_fetch_never_requests_a_url_taken_from_the_response() -> None:
    seen, open_url = _pages([], [])
    # a hostile Link header cannot steer the next request anywhere else
    def hostile(request: urllib.request.Request) -> _Response:
        seen.append(request)
        link = '<https://evil.example/x>; rel="next"' if len(seen) == 1 else ""
        return _Response([], link)

    ds.fetch_releases("o/r", "secret", hostile)
    assert all(r.full_url.startswith(f"{ds._API_PREFIX}repos/o/r/releases?") for r in seen)


def test_fetch_never_follows_a_redirect() -> None:
    handler = ds._NoRedirect()
    request = urllib.request.Request(f"{ds._API_PREFIX}repos/o/r/releases")
    assert handler.redirect_request(request, None, 301, "moved", {}, "https://evil.example/") is None


def test_fetch_rejects_a_repo_that_is_not_owner_slash_name() -> None:
    with pytest.raises(ds.StatsError):
        ds.fetch_releases("owner/name/../../x", None)


# ---- the workflow --------------------------------------------------------------------


def test_workflow_runs_daily_off_the_hour_and_on_demand() -> None:
    cron = re.search(r'cron:\s*"(\d+) (\d+) \* \* \*"', WORKFLOW)
    assert cron and cron.group(1) != "0", "once a day, not on the hour (delayed runs)"
    assert "workflow_dispatch:" in WORKFLOW


def test_workflow_gives_the_write_token_to_the_git_steps_only() -> None:
    top = WORKFLOW.split("jobs:", 1)[0]
    assert re.search(r"^permissions:\n  contents: read$", top, re.MULTILINE)
    assert WORKFLOW.count("contents: write") == 1, "only the job may write"
    assert "persist-credentials: false" in WORKFLOW
    steps = WORKFLOW.split("steps:", 1)[1].split("      - ")
    holders = [s.splitlines()[0] for s in steps if "github.token" in s]
    assert holders == ["name: Check out the data branch (create it on the first run)",
                       "name: Commit and push the data branch"], (
        "the step that parses the API answer must not hold the token"
    )
    assert "github.ref == 'refs/heads/master'" in WORKFLOW
    assert "group: download-stats" in WORKFLOW and "cancel-in-progress: false" in WORKFLOW


def test_workflow_never_touches_master_tags_or_releases() -> None:
    assert not re.search(r"git push[^\n]*master", WORKFLOW)
    assert "gh release" not in WORKFLOW and "git tag" not in WORKFLOW
