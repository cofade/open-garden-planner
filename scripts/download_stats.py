"""Daily release-download statistics from GitHub's own asset counters (no telemetry).

GitHub keeps one cumulative ``download_count`` per release asset and no history. This
script turns that into daily values: each run appends today's counters to
``downloads.csv`` (one row per date, release tag and asset) and re-derives
``daily.csv`` (the difference between consecutive snapshots) and ``SUMMARY.md`` from it.
The raw snapshots are the source of truth; the derived files can always be rebuilt.

Which way a download took is estimated from the two files an in-app update fetches
(``services/verified_update.py``): ``SHA256SUMS.txt`` first, then the ``*-Setup.exe``.
A web visitor takes the installer only. So the daily ``SHA256SUMS.txt`` increase
approximates in-app updates and ``Setup.exe`` minus that approximates web downloads.
The counters also include bots, virus scanners, retries and people who fetch the
checksum file by hand: the numbers are downloads, not users.

Run by ``.github/workflows/download-stats.yml``, which keeps the output on the orphan
``download-stats`` branch. Exit codes: 0 = written, 2 = the API answer was unusable or
an input file was unreadable. A failed fetch never writes a zero.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SNAPSHOT_FILE = "downloads.csv"
DAILY_FILE = "daily.csv"
SUMMARY_FILE = "SUMMARY.md"

SNAPSHOT_FIELDS = ("date_utc", "tag", "asset", "download_count", "published_at", "prerelease")
DAILY_FIELDS = ("date_utc", "tag", "asset", "delta", "days_covered", "kind")

INSTALLER_SUFFIX = "-Setup.exe"
MANIFEST_NAME = "SHA256SUMS.txt"
SUMMARY_DAYS = 30

#: ``baseline`` = first snapshot ever taken, so the counter's history is unknown and no
#: daily value is claimed; ``new`` = the asset first appears after the first snapshot, so
#: its counter started at zero and the whole count belongs to the span; ``normal`` = the
#: difference to the previous snapshot; ``reset`` = the counter fell (asset deleted and
#: uploaded again), so the new count is taken as the span's downloads.
KIND_BASELINE = "baseline"
KIND_NEW = "new"
KIND_NORMAL = "normal"
KIND_RESET = "reset"

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PER_PAGE = 100
_REQUEST_TIMEOUT = 30


class StatsError(Exception):
    """The API answer or an input file cannot be trusted; nothing is written."""


@dataclass(frozen=True)
class Row:
    """One asset's cumulative counter on one UTC date."""

    date_utc: str
    tag: str
    asset: str
    download_count: int
    published_at: str
    prerelease: bool

    @property
    def key(self) -> tuple[str, str]:
        return (self.tag, self.asset)


@dataclass(frozen=True)
class Delta:
    """Downloads of one asset between two consecutive snapshots."""

    date_utc: str
    tag: str
    asset: str
    delta: int | None
    days_covered: int
    kind: str


Fetcher = Callable[[str, str | None], list[dict[str, Any]]]


def fetch_releases(repo: str, token: str | None) -> list[dict[str, Any]]:
    """All releases of ``repo`` from the GitHub API (the only function that uses the network)."""
    if not _REPO_RE.match(repo):
        raise StatsError(f"not an owner/name repository: {repo!r}")
    releases: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{repo}/releases?per_page={_PER_PAGE}&page={page}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "open-garden-planner-download-stats",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT) as response:  # nosec: B310
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise StatsError(f"release listing failed on page {page}: {exc}") from exc
        if not isinstance(payload, list):
            raise StatsError(f"release listing page {page} is not a list: {type(payload)}")
        releases.extend(payload)
        if len(payload) < _PER_PAGE:
            return releases
        page += 1


def snapshot_rows(releases: Iterable[dict[str, Any]], today: date) -> list[Row]:
    """The counters of every asset of every release, stamped with ``today`` (UTC)."""
    rows: list[Row] = []
    for release in releases:
        tag = release.get("tag_name") if isinstance(release, dict) else None
        assets = release.get("assets") if isinstance(release, dict) else None
        if not isinstance(tag, str) or not tag or not isinstance(assets, list):
            raise StatsError(f"release entry without tag_name/assets: {release!r:.200}")
        for asset in assets:
            name = asset.get("name") if isinstance(asset, dict) else None
            count = asset.get("download_count") if isinstance(asset, dict) else None
            if not isinstance(name, str) or not name or not isinstance(count, int) or count < 0:
                raise StatsError(f"asset of {tag} without name/download_count: {asset!r:.200}")
            rows.append(
                Row(
                    date_utc=today.isoformat(),
                    tag=tag,
                    asset=name,
                    download_count=count,
                    published_at=str(release.get("published_at") or ""),
                    prerelease=bool(release.get("prerelease")),
                )
            )
    return rows


def merge(existing: Iterable[Row], new: Iterable[Row]) -> list[Row]:
    """``existing`` with the dates present in ``new`` replaced, in a stable order."""
    new_rows = list(new)
    replaced = {row.date_utc for row in new_rows}
    kept = [row for row in existing if row.date_utc not in replaced]
    return sorted(kept + new_rows, key=lambda r: (r.date_utc, r.tag, r.asset))


def daily_deltas(rows: Iterable[Row]) -> list[Delta]:
    """Per-asset differences between consecutive snapshots (see the ``KIND_*`` notes)."""
    ordered = sorted(rows, key=lambda r: (r.date_utc, r.tag, r.asset))
    if not ordered:
        return []
    first_snapshot = ordered[0].date_utc
    previous: dict[tuple[str, str], Row] = {}
    deltas: list[Delta] = []
    for row in ordered:
        before = previous.get(row.key)
        if before is None:
            if row.date_utc == first_snapshot:
                deltas.append(Delta(row.date_utc, row.tag, row.asset, None, 0, KIND_BASELINE))
            else:
                deltas.append(
                    Delta(row.date_utc, row.tag, row.asset, row.download_count, 1, KIND_NEW)
                )
        else:
            span = (date.fromisoformat(row.date_utc) - date.fromisoformat(before.date_utc)).days
            if row.download_count < before.download_count:
                deltas.append(
                    Delta(row.date_utc, row.tag, row.asset, row.download_count, span, KIND_RESET)
                )
            else:
                deltas.append(
                    Delta(
                        row.date_utc,
                        row.tag,
                        row.asset,
                        row.download_count - before.download_count,
                        span,
                        KIND_NORMAL,
                    )
                )
        previous[row.key] = row
    return deltas


def render_summary(rows: list[Row], deltas: list[Delta]) -> str:
    """``SUMMARY.md``: the last 30 snapshot days, newest first, plus the totals per release."""
    lines = [
        "# Release downloads",
        "",
        "Generated from GitHub's per-asset download counters; no data comes from the app.",
        "These are downloads, not users: bots, virus scanners, retries and people who fetch",
        "`SHA256SUMS.txt` by hand are included. *In-app* is estimated from the daily increase",
        "of `SHA256SUMS.txt` (an in-app update fetches it before the installer); *web* is the",
        "installer's increase minus that.",
        "",
    ]
    if not rows:
        return "\n".join([*lines, "No snapshot yet.", ""])

    by_date: dict[str, list[Delta]] = {}
    for delta in deltas:
        if delta.kind != KIND_BASELINE:
            by_date.setdefault(delta.date_utc, []).append(delta)

    lines += ["## Last 30 days", ""]
    if not by_date:
        lines += [f"No daily values yet: baseline recorded on {rows[0].date_utc}.", ""]
    else:
        lines += [
            "| Date (UTC) | Installer | In-app (est.) | Web (est.) | Note |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
        for day in sorted(by_date, reverse=True)[:SUMMARY_DAYS]:
            lines.append(_summary_row(day, by_date[day]))
        lines.append("")

    latest = max(row.date_utc for row in rows)
    lines += [
        f"## Totals per release (counters on {latest})",
        "",
        "| Release | Installer | SHA256SUMS.txt |",
        "| --- | ---: | ---: |",
    ]
    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        if row.date_utc != latest:
            continue
        slot = totals.setdefault(row.tag, {"installer": 0, "manifest": 0})
        if row.asset.endswith(INSTALLER_SUFFIX):
            slot["installer"] += row.download_count
        elif row.asset == MANIFEST_NAME:
            slot["manifest"] += row.download_count
    for tag in sorted(totals, reverse=True):
        lines.append(f"| {tag} | {totals[tag]['installer']} | {totals[tag]['manifest']} |")
    lines.append("")
    return "\n".join(lines)


def _summary_row(day: str, deltas: list[Delta]) -> str:
    installer = sum(d.delta or 0 for d in deltas if d.asset.endswith(INSTALLER_SUFFIX))
    manifest = sum(d.delta or 0 for d in deltas if d.asset == MANIFEST_NAME)
    in_app = min(installer, manifest)
    web = installer - in_app
    notes: list[str] = []
    span = max(d.days_covered for d in deltas)
    if span > 1:
        notes.append(f"covers {span} days")
    if any(d.kind == KIND_NEW for d in deltas):
        notes.append("new release or asset")
    if any(d.kind == KIND_RESET for d in deltas):
        notes.append("counter reset")
    return f"| {day} | {installer} | {in_app} | {web} | {'; '.join(notes)} |"


def read_snapshots(path: Path) -> list[Row]:
    """The stored snapshots, or an empty list when the file does not exist yet."""
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != SNAPSHOT_FIELDS:
                raise StatsError(f"{path}: unexpected columns {reader.fieldnames}")
            return [
                Row(
                    date_utc=_valid_date(item["date_utc"]),
                    tag=item["tag"],
                    asset=item["asset"],
                    download_count=int(item["download_count"]),
                    published_at=item["published_at"],
                    prerelease=item["prerelease"] == "1",
                )
                for item in reader
            ]
    except (OSError, ValueError, KeyError) as exc:
        raise StatsError(f"{path}: cannot read ({exc})") from exc


def _valid_date(text: str) -> str:
    return date.fromisoformat(text).isoformat()


def _write_csv(path: Path, fields: tuple[str, ...], records: Iterable[Iterable[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(records)


def write_outputs(data_dir: Path, rows: list[Row], deltas: list[Delta]) -> None:
    """Write the three files; the same input always yields byte-identical files."""
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        data_dir / SNAPSHOT_FILE,
        SNAPSHOT_FIELDS,
        (
            (r.date_utc, r.tag, r.asset, r.download_count, r.published_at, int(r.prerelease))
            for r in rows
        ),
    )
    _write_csv(
        data_dir / DAILY_FILE,
        DAILY_FIELDS,
        (
            (d.date_utc, d.tag, d.asset, "" if d.delta is None else d.delta, d.days_covered, d.kind)
            for d in deltas
        ),
    )
    (data_dir / SUMMARY_FILE).write_text(render_summary(rows, deltas), encoding="utf-8", newline="\n")


def run(
    data_dir: Path,
    repo: str,
    today: date,
    token: str | None,
    fetcher: Fetcher = fetch_releases,
) -> int:
    """Take today's snapshot and rebuild the derived files; returns the snapshot row count."""
    new_rows = snapshot_rows(fetcher(repo, token), today)
    rows = merge(read_snapshots(data_dir / SNAPSHOT_FILE), new_rows)
    write_outputs(data_dir, rows, daily_deltas(rows))
    return len(new_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="where the CSVs live")
    parser.add_argument("--repo", default="cofade/open-garden-planner", help="owner/name")
    parser.add_argument("--today", help="UTC date to stamp (YYYY-MM-DD); default: today")
    parser.add_argument(
        "--releases-json",
        type=Path,
        help="read the release listing from this file instead of the API (dry runs)",
    )
    args = parser.parse_args(argv)

    try:
        today = date.fromisoformat(args.today) if args.today else datetime.now(UTC).date()
    except ValueError:
        print(f"--today is not a YYYY-MM-DD date: {args.today!r}", file=sys.stderr)
        return 2

    def from_file(_repo: str, _token: str | None) -> list[dict[str, Any]]:
        loaded = json.loads(args.releases_json.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise StatsError(f"{args.releases_json}: not a list of releases")
        return loaded

    fetcher: Fetcher = from_file if args.releases_json else fetch_releases
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        count = run(args.data_dir, args.repo, today, token, fetcher)
    except (StatsError, OSError, json.JSONDecodeError) as exc:
        print(f"download stats failed: {exc}", file=sys.stderr)
        return 2
    print(f"Recorded {count} asset counters for {today.isoformat()} in {args.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
