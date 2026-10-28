"""Release-download statistics from GitHub's own asset counters (no telemetry).

GitHub keeps one cumulative ``download_count`` per release asset and no history. Each
run of this script appends one snapshot of those counters (stamped with the time it was
taken) to ``snapshots/YYYY-MM.csv`` and re-derives ``daily/YYYY-MM.csv`` (the difference
between consecutive snapshots, with the hours the difference covers) and ``SUMMARY.md``.
The snapshots are the source of truth; the derived files can always be rebuilt. Only the
installer (``*-Setup.exe``) and ``SHA256SUMS.txt`` of published (non-draft) releases are
recorded, one file per month, so no single file approaches GitHub's file-size limits.

What the numbers mean, and do not mean:

* They are downloads, not users: bots, virus scanners, retries and CI runs are counted.
* A value is the window between two snapshots, in hours; it is not a calendar day.
* The checksum file is fetched by an in-app update **from v1.30.3 on** (older apps
  download only the installer) **and** by web users who follow the install instructions
  (README and wiki tell them to). It therefore does not separate in-app updates from web
  downloads, and the summary reports the two raw counters instead of a derived split.

Run by ``.github/workflows/download-stats.yml``, which keeps the output on the orphan
``download-stats`` branch. Exit codes: 0 = written, 2 = the API answer or an input file
was unusable. A failed fetch never writes a zero.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SNAPSHOT_DIR = "snapshots"
DAILY_DIR = "daily"
SUMMARY_FILE = "SUMMARY.md"

SNAPSHOT_FIELDS = (
    "taken_at",
    "tag",
    "asset",
    "asset_id",
    "download_count",
    "published_at",
    "prerelease",
)
DAILY_FIELDS = ("taken_at", "tag", "asset", "asset_id", "delta", "hours", "kind")

TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
INSTALLER_SUFFIX = "-Setup.exe"
MANIFEST_NAME = "SHA256SUMS.txt"
SUMMARY_SNAPSHOTS = 30
#: A window outside this many hours is flagged in the summary (a skipped run, or a
#: manual run that moved the boundary).
NOMINAL_HOURS = (20.0, 28.0)
#: A listing that holds less than this share of the previous snapshot's assets is a
#: broken answer, not a real change.
MIN_ASSET_SHARE = 0.5

#: ``baseline`` = the first snapshot ever taken, so the counter's history is unknown and no
#: value is claimed; ``new`` = the asset first appears after the first snapshot, so the
#: whole count belongs to the window since the previous snapshot; ``normal`` = the
#: difference to the asset's previous snapshot; ``reset`` = the counter fell (the asset
#: was deleted and uploaded again), so the new count is taken as the window's downloads.
KIND_BASELINE = "baseline"
KIND_NEW = "new"
KIND_NORMAL = "normal"
KIND_RESET = "reset"

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_NEXT_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel="next"')
_API_PREFIX = "https://api.github.com/"
_PER_PAGE = 100
_MAX_PAGES = 50
_REQUEST_TIMEOUT = 30


class StatsError(Exception):
    """The API answer or an input file cannot be trusted; nothing is written."""


@dataclass(frozen=True)
class Row:
    """One asset's cumulative counter at one snapshot."""

    taken_at: str
    tag: str
    asset: str
    asset_id: int
    download_count: int
    published_at: str
    prerelease: bool

    @property
    def date_utc(self) -> str:
        return self.taken_at[:10]

    @property
    def month(self) -> str:
        return self.taken_at[:7]


@dataclass(frozen=True)
class Delta:
    """Downloads of one asset between two consecutive snapshots."""

    taken_at: str
    tag: str
    asset: str
    asset_id: int
    delta: int | None
    hours: float | None
    kind: str


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: the Authorization header must not travel to another URL."""

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


OpenUrl = Callable[[urllib.request.Request], AbstractContextManager[Any]]
Fetcher = Callable[[str, str | None], list[dict[str, Any]]]


def _default_open(request: urllib.request.Request) -> AbstractContextManager[Any]:
    opener = urllib.request.build_opener(_NoRedirect)
    return opener.open(request, timeout=_REQUEST_TIMEOUT)  # nosec: B310 - https literal


def fetch_releases(
    repo: str, token: str | None, open_url: OpenUrl = _default_open
) -> list[dict[str, Any]]:
    """All releases of ``repo`` from the GitHub API (the only function that uses the network).

    Pages are requested by number under ``/repos/``; the ``Link: rel="next"`` header, the
    API's own end-of-list signal, decides whether another page exists. (The ``next`` URL
    itself is not followed: it names the ``/repositories/<id>/`` form, and a page URL built
    here can never leave the API.)
    """
    if not _REPO_RE.match(repo):
        raise StatsError(f"not an owner/name repository: {repo!r}")
    releases: list[dict[str, Any]] = []
    for page in range(1, _MAX_PAGES + 1):
        url = f"{_API_PREFIX}repos/{repo}/releases?per_page={_PER_PAGE}&page={page}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "open-garden-planner-download-stats",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        try:
            with open_url(request) as response:
                payload = json.load(response)
                link = response.headers.get("Link") or ""
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise StatsError(f"release listing failed on page {page}: {exc}") from exc
        if not isinstance(payload, list):
            raise StatsError(f"release listing page {page} is not a list: {type(payload)}")
        releases.extend(payload)
        if not _NEXT_LINK_RE.search(link):
            return releases
    raise StatsError(f"release listing exceeds {_MAX_PAGES} pages")


def is_tracked_asset(name: str) -> bool:
    return name == MANIFEST_NAME or name.endswith(INSTALLER_SUFFIX)


def _count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def snapshot_rows(releases: Iterable[dict[str, Any]], taken_at: str) -> list[Row]:
    """The counters of the tracked assets of every published release, stamped ``taken_at``."""
    rows: list[Row] = []
    for release in releases:
        tag = release.get("tag_name") if isinstance(release, dict) else None
        assets = release.get("assets") if isinstance(release, dict) else None
        if not isinstance(tag, str) or not tag or not isinstance(assets, list):
            raise StatsError(f"release entry without tag_name/assets: {release!r:.200}")
        if release.get("draft"):
            continue  # a release still being assembled: partial assets, not public
        for asset in assets:
            name = asset.get("name") if isinstance(asset, dict) else None
            if not isinstance(name, str) or not name:
                raise StatsError(f"asset of {tag} without a name: {asset!r:.200}")
            if not is_tracked_asset(name):
                continue
            if not _count(asset.get("download_count")) or not _count(asset.get("id")):
                raise StatsError(f"asset {name} of {tag} without id/download_count: {asset!r:.200}")
            rows.append(
                Row(
                    taken_at=taken_at,
                    tag=tag,
                    asset=name,
                    asset_id=asset["id"],
                    download_count=asset["download_count"],
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
    return sorted(kept + new_rows, key=lambda r: (r.taken_at, r.tag, r.asset))


def _parse_time(taken_at: str) -> datetime:
    return datetime.strptime(taken_at, TIMESTAMP_FORMAT).replace(tzinfo=UTC)


def _hours(later: str, earlier: str) -> float:
    return round((_parse_time(later) - _parse_time(earlier)).total_seconds() / 3600, 1)


def daily_deltas(rows: Iterable[Row]) -> list[Delta]:
    """Per-asset differences between consecutive snapshots (see the ``KIND_*`` notes)."""
    ordered = sorted(rows, key=lambda r: (r.taken_at, r.tag, r.asset))
    snapshot_times = sorted({row.taken_at for row in ordered})
    previous_snapshot = {t: (snapshot_times[i - 1] if i else None) for i, t in enumerate(snapshot_times)}
    last: dict[int, Row] = {}
    deltas: list[Delta] = []
    for row in ordered:
        before = last.get(row.asset_id)
        window_start = before.taken_at if before else previous_snapshot[row.taken_at]
        if window_start is None:
            delta = Delta(row.taken_at, row.tag, row.asset, row.asset_id, None, None, KIND_BASELINE)
        else:
            span = _hours(row.taken_at, window_start)
            if before is None:
                value, kind = row.download_count, KIND_NEW
            elif row.download_count < before.download_count:
                value, kind = row.download_count, KIND_RESET
            else:
                value, kind = row.download_count - before.download_count, KIND_NORMAL
            delta = Delta(row.taken_at, row.tag, row.asset, row.asset_id, value, span, kind)
        deltas.append(delta)
        last[row.asset_id] = row
    return deltas


def _tag_key(tag: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", tag))


def render_summary(rows: list[Row], deltas: list[Delta]) -> str:
    """``SUMMARY.md``: the last 30 snapshots, newest first, plus the totals per release."""
    lines = [
        "# Release downloads",
        "",
        "Generated from GitHub's per-asset download counters; no data comes from the app.",
        "These are downloads, not users: bots, virus scanners and retries are included.",
        "Each line is the window between two snapshots (not a calendar day).",
        "",
        "`SHA256SUMS.txt` is fetched by in-app updates from v1.30.3 on *and* by web users who",
        "follow the install instructions; older apps download the installer only. The two",
        "columns are therefore reported as they are and are not split into in-app and web.",
        "Prereleases are left out of the table.",
        "",
    ]
    if not rows:
        return "\n".join([*lines, "No snapshot yet.", ""])

    prerelease_ids = {row.asset_id for row in rows if row.prerelease}
    by_snapshot: dict[str, list[Delta]] = {}
    for delta in deltas:
        if delta.kind != KIND_BASELINE and delta.asset_id not in prerelease_ids:
            by_snapshot.setdefault(delta.taken_at, []).append(delta)

    lines += [f"## Last {SUMMARY_SNAPSHOTS} snapshots", ""]
    if not by_snapshot:
        first = min(row.taken_at for row in rows)
        lines += [f"No values yet: the baseline was taken on {first}.", ""]
    else:
        lines += [
            "| Snapshot (UTC) | Window (h) | Installer | SHA256SUMS.txt | Note |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
        for taken_at in sorted(by_snapshot, reverse=True)[:SUMMARY_SNAPSHOTS]:
            lines.append(_summary_row(taken_at, by_snapshot[taken_at]))
        lines.append("")

    latest = max(row.taken_at for row in rows)
    lines += [
        f"## Totals per release (counters at {latest})",
        "",
        "| Release | Installer | SHA256SUMS.txt |",
        "| --- | ---: | ---: |",
    ]
    totals: dict[str, list[int]] = {}
    for row in rows:
        if row.taken_at != latest:
            continue
        slot = totals.setdefault(row.tag, [0, 0])
        slot[0 if row.asset.endswith(INSTALLER_SUFFIX) else 1] += row.download_count
    for tag in sorted(totals, key=_tag_key, reverse=True):
        lines.append(f"| {tag} | {totals[tag][0]} | {totals[tag][1]} |")
    lines.append(f"| **All** | {sum(t[0] for t in totals.values())} | {sum(t[1] for t in totals.values())} |")
    lines.append("")
    return "\n".join(lines)


def _summary_row(taken_at: str, deltas: list[Delta]) -> str:
    installer = sum(d.delta or 0 for d in deltas if d.asset.endswith(INSTALLER_SUFFIX))
    manifest = sum(d.delta or 0 for d in deltas if d.asset == MANIFEST_NAME)
    window = max(d.hours or 0.0 for d in deltas)
    notes: list[str] = []
    if not NOMINAL_HOURS[0] <= window <= NOMINAL_HOURS[1]:
        notes.append("window is not about a day")
    if any(d.kind == KIND_NEW for d in deltas):
        notes.append("new release or asset")
    if any(d.kind == KIND_RESET for d in deltas):
        notes.append("counter reset")
    stamp = taken_at.replace("T", " ")[:16]
    return f"| {stamp} | {window:g} | {installer} | {manifest} | {'; '.join(notes)} |"


def read_snapshots(data_dir: Path) -> list[Row]:
    """The stored snapshots of every month, or an empty list when there are none yet."""
    rows: list[Row] = []
    for path in sorted((data_dir / SNAPSHOT_DIR).glob("*.csv")):
        try:
            with path.open(encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                if tuple(reader.fieldnames or ()) != SNAPSHOT_FIELDS:
                    raise StatsError(f"{path}: unexpected columns {reader.fieldnames}")
                for item in reader:
                    if None in item or None in item.values():
                        raise StatsError(f"{path}: row {reader.line_num} has the wrong length")
                    row = Row(
                        taken_at=item["taken_at"],
                        tag=item["tag"],
                        asset=item["asset"],
                        asset_id=int(item["asset_id"]),
                        download_count=int(item["download_count"]),
                        published_at=item["published_at"],
                        prerelease=item["prerelease"] == "1",
                    )
                    _parse_time(row.taken_at)
                    if row.download_count < 0 or row.asset_id < 0:
                        raise StatsError(f"{path}: row {reader.line_num} has a negative number")
                    if row.month != path.stem:
                        raise StatsError(f"{path}: row {reader.line_num} belongs to {row.month}")
                    rows.append(row)
        except (OSError, ValueError, KeyError) as exc:
            raise StatsError(f"{path}: cannot read ({exc})") from exc
    seen: set[tuple[str, int]] = set()
    for row in rows:
        if (row.date_utc, row.asset_id) in seen:
            raise StatsError(f"duplicate snapshot of asset {row.asset_id} on {row.date_utc}")
        seen.add((row.date_utc, row.asset_id))
    return rows


def _write_csv(path: Path, fields: tuple[str, ...], records: Iterable[Iterable[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(fields)
        writer.writerows(records)


def write_outputs(data_dir: Path, rows: list[Row], deltas: list[Delta]) -> None:
    """Write the files; the same input always yields byte-identical files."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for month in sorted({row.month for row in rows}):
        _write_csv(
            data_dir / SNAPSHOT_DIR / f"{month}.csv",
            SNAPSHOT_FIELDS,
            (
                (r.taken_at, r.tag, r.asset, r.asset_id, r.download_count, r.published_at,
                 int(r.prerelease))
                for r in rows
                if r.month == month
            ),
        )
        _write_csv(
            data_dir / DAILY_DIR / f"{month}.csv",
            DAILY_FIELDS,
            (
                (d.taken_at, d.tag, d.asset, d.asset_id, "" if d.delta is None else d.delta,
                 "" if d.hours is None else f"{d.hours:g}", d.kind)
                for d in deltas
                if d.taken_at[:7] == month
            ),
        )
    (data_dir / SUMMARY_FILE).write_text(render_summary(rows, deltas), encoding="utf-8", newline="\n")


def run(
    data_dir: Path,
    repo: str,
    now: datetime,
    token: str | None,
    fetcher: Fetcher = fetch_releases,
) -> int:
    """Take a snapshot at ``now`` and rebuild the derived files; returns the row count."""
    taken_at = now.astimezone(UTC).strftime(TIMESTAMP_FORMAT)
    new_rows = snapshot_rows(fetcher(repo, token), taken_at)
    existing = read_snapshots(data_dir)
    if not new_rows:
        raise StatsError("the listing holds no installer or checksum asset: refusing to record it")
    if existing:
        latest = max(row.taken_at for row in existing)
        previous = sum(1 for row in existing if row.taken_at == latest)
        if len(new_rows) < previous * MIN_ASSET_SHARE:
            raise StatsError(
                f"the listing holds {len(new_rows)} tracked assets, the last snapshot {previous}: "
                "refusing to record an answer that lost most of them"
            )
    rows = merge(existing, new_rows)
    write_outputs(data_dir, rows, daily_deltas(rows))
    return len(new_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True, help="where the files live")
    parser.add_argument("--repo", default="cofade/open-garden-planner", help="owner/name")
    parser.add_argument("--now", help="UTC time to stamp (YYYY-MM-DDTHH:MM:SSZ); default: now")
    parser.add_argument(
        "--releases-json",
        type=Path,
        help="read the release listing from this file instead of the API (dry runs)",
    )
    args = parser.parse_args(argv)

    try:
        now = _parse_time(args.now) if args.now else datetime.now(UTC)
    except ValueError:
        print(f"--now is not a YYYY-MM-DDTHH:MM:SSZ time: {args.now!r}", file=sys.stderr)
        return 2

    def from_file(_repo: str, _token: str | None) -> list[dict[str, Any]]:
        loaded = json.loads(args.releases_json.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise StatsError(f"{args.releases_json}: not a list of releases")
        return loaded

    fetcher: Fetcher = from_file if args.releases_json else fetch_releases
    try:
        count = run(args.data_dir, args.repo, now, None, fetcher)
    except (StatsError, OSError, json.JSONDecodeError) as exc:
        print(f"download stats failed: {exc}", file=sys.stderr)
        return 2
    print(f"Recorded {count} asset counters at {now.strftime(TIMESTAMP_FORMAT)} in {args.data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
