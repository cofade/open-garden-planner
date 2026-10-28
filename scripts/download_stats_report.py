"""Reproducible UTC calendar report, independent of Qt and the GitHub API.

The immutable baseline is an explicitly modelled history, never an observed daily
count. Fractions are retained until the JSON/SVG presentation boundary.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from fractions import Fraction
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts.download_stats import Row

BASELINE_FILE = "baseline.json"
WEB = Path(__file__).with_name("download_stats_web")
COMPONENTS = ("historical", "observed", "gap")
DAY = timedelta(days=1)


def instant(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False) + "\n"


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def baseline(data_dir: Path, seed_rows: list[Row]) -> dict[str, Any]:
    """Load a validated seed, or construct it BEFORE merge replaces the first date."""
    path = data_dir / BASELINE_FILE
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        first = min(row.taken_at for row in seed_rows)
        payload = {"version": 1, "taken_at": first,
                   "assets": [asdict(row) for row in seed_rows if row.taken_at == first]}
    try:
        _validate_baseline(payload)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid baseline structure") from exc
    return payload


def _validate_baseline(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("invalid baseline version")
    cutoff = instant(payload["taken_at"])
    if not isinstance(payload.get("assets"), list) or not payload["assets"]:
        raise ValueError("baseline has no assets")
    seen: set[int] = set()
    for asset in payload["assets"]:
        for key in ("asset_id", "download_count"):
            if type(asset[key]) is not int or asset[key] < 0:
                raise ValueError(f"invalid baseline {key}")
        if asset["asset_id"] in seen or asset["taken_at"] != payload["taken_at"]:
            raise ValueError("duplicate or inconsistent baseline asset")
        seen.add(asset["asset_id"])
        if not all(isinstance(asset[k], str) and asset[k] for k in ("tag", "asset")):
            raise ValueError("invalid baseline asset name or tag")
        if type(asset["prerelease"]) is not bool:
            raise ValueError("invalid baseline prerelease flag")
        if instant(asset["published_at"]) > cutoff:
            raise ValueError("baseline release published after its snapshot")


@dataclass
class CalendarDay:
    historical: Fraction = Fraction(0)
    observed: Fraction = Fraction(0)
    gap: Fraction = Fraction(0)
    windows: set[tuple[str, str, str]] = field(default_factory=set)
    partial: bool = False

    def export(self, day: date) -> dict[str, Any]:
        return {"date": day.isoformat(),
                **{key: float(getattr(self, key)) for key in COMPONENTS},
                "partial": self.partial,
                "windows": [{"from": a, "to": b, "kind": kind}
                            for a, b, kind in sorted(self.windows)]}


def _history(days: dict[date, CalendarDay], seed: dict[str, Any]) -> None:
    releases: dict[datetime, int] = defaultdict(int)
    end = instant(seed["taken_at"])
    for asset in seed["assets"]:
        if not asset["prerelease"]:
            published = instant(asset["published_at"])
            # Checksums establish the successor boundary even without an installer.
            releases[published] += (asset["download_count"]
                                    if asset["asset"].endswith("-Setup.exe") else 0)
    starts = sorted(releases)
    for index, start in enumerate(starts):
        stop = starts[index + 1] if index + 1 < len(starts) else end
        seconds = int((stop - start).total_seconds())
        if seconds == 0:
            if releases[start]:
                days[start.date()].historical += releases[start]
                days[start.date()].partial = True
            continue
        cursor = start
        while cursor < stop:
            midnight = datetime.combine(cursor.date() + DAY, time(), UTC)
            boundary = min(stop, midnight)
            days[cursor.date()].historical += Fraction(
                releases[start] * int((boundary - cursor).total_seconds()), seconds
            )
            cursor = boundary
    if starts and starts[0].time() != time():
        days[starts[0].date()].partial = True


def calendar_series(rows: list[Row], seed: dict[str, Any], repo: str) -> dict[str, Any]:
    """Historical estimate plus post-seed increments; never re-count the seed.

    Ordinary windows are assigned to the UTC date preceding the ending snapshot.
    Missing dates are shared evenly. Same-date manual windows are explicitly partial.
    Asset-specific gaps retain their own previous observation, just like daily_deltas.
    """
    days: dict[date, CalendarDay] = defaultdict(CalendarDay)
    _history(days, seed)
    cutoff = seed["taken_at"]
    previous = {asset["asset_id"]: asset for asset in seed["assets"]}
    admitted = {key: asset for key, asset in previous.items() if not asset["prerelease"]}
    snapshot_times = sorted({r.taken_at for r in rows if r.taken_at > cutoff})
    preceding = {stamp: (snapshot_times[i - 1] if i else cutoff)
                 for i, stamp in enumerate(snapshot_times)}
    for row in sorted(rows, key=lambda r: (r.taken_at, r.asset_id)):
        if row.taken_at <= cutoff:
            continue
        seen = previous.get(row.asset_id)
        previous[row.asset_id] = asdict(row)
        if row.prerelease or not row.asset.endswith("-Setup.exe"):
            continue
        old = admitted.get(row.asset_id)
        start_stamp = (old["taken_at"] if old else
                       seen["taken_at"] if seen else preceding[row.taken_at])
        # Admission and observation differ: temporarily hiding a final release
        # must not make a re-promotion count its entire total for a second time.
        if old is None:
            count, kind = row.download_count, "new"
        elif row.download_count < old["download_count"]:
            count, kind = row.download_count, "reset"
        else:
            count, kind = row.download_count - old["download_count"], "normal"
        start, stop = instant(start_stamp), instant(row.taken_at)
        if old is None:
            # A newly published asset cannot contribute to a day before it existed.
            start = max(start, instant(row.published_at))
            start_stamp = start.strftime("%Y-%m-%dT%H:%M:%SZ")
            if start > stop:
                raise ValueError("release published after its snapshot")
        length = (stop.date() - start.date()).days
        component = "gap" if length > 1 else "observed"
        dates = [start.date() + DAY * n for n in range(length)] if length else [stop.date()]
        for day in dates:
            slot = days[day]
            setattr(slot, component, getattr(slot, component) + Fraction(count, len(dates)))
            slot.windows.add((start_stamp, row.taken_at, kind))
            if not length:
                slot.partial = True
        admitted[row.asset_id] = asdict(row)
    latest = max([cutoff, *(r.taken_at for r in rows)])
    # A baseline taken partway through a day is a partial last day until observed.
    last_day = max(days, default=None)
    if last_day is not None and last_day >= instant(latest).date():
        days[last_day].partial = True
    return {"version": 1, "timezone": "UTC", "repo": repo,
            "baseline_at": cutoff, "updated_at": latest,
            "days": [days[day].export(day) for day in sorted(days)]}


def preview_svg(series: dict[str, Any], messages: dict[str, str]) -> str:
    """Daily last-year preview of the SAME values used by the interactive chart."""
    all_days = series["days"]
    lower = date.fromisoformat(all_days[-1]["date"]) - DAY * 364 if all_days else date.min
    selected = [day for day in all_days if date.fromisoformat(day["date"]) >= lower]
    ceiling = max((sum(day[k] for k in COMPONENTS) for day in selected), default=0)
    maximum = max(1, math.ceil(ceiling))
    left, top, width, height = 62, 80, 990, 230
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1080 405" role="img"',
        f' aria-labelledby="title desc"><title id="title">{escape(messages["title"])}</title>',
        f'<desc id="desc">{escape(messages["method"])}</desc>',
        '<style>text{font-family:system-ui,sans-serif;fill:#344054;font-size:12px}',
        '.bg{fill:#fff}.grid{stroke:#d0d7de;stroke-dasharray:3 4}',
        '@media(prefers-color-scheme:dark){text{fill:#c9d1d9}.bg{fill:#0d1117}',
        '.grid{stroke:#30363d}}</style><rect class="bg" width="1080" height="405" rx="12"/>',
        f'<text x="24" y="32" style="font-size:20px;font-weight:650">'
        f'{escape(messages["title"])}</text>',
        f'<text x="24" y="55">{escape(messages["subtitle"])}</text>',
    ]
    for tick in range(5):
        y = top + height - tick * height / 4
        parts += [f'<path class="grid" d="M{left} {y}h{width}"/>',
                  f'<text x="50" y="{y + 4}" text-anchor="end">{maximum*tick/4:g}</text>']
    step = width / max(1, len(selected))
    colors = {"historical": "#8b949e", "observed": "#2da44e", "gap": "#bf8700"}
    for index, day in enumerate(selected):
        y = top + height
        for key in COMPONENTS:
            h = day[key] / maximum * height
            y -= h
            label = f'{day["date"]}: {day[key]:.4g} ({messages[key]})'
            parts.append(f'<rect x="{left+index*step:.3f}" y="{y:.3f}" '
                         f'width="{max(.1, step*.8):.3f}" height="{h:.3f}" '
                         f'fill="{colors[key]}"><title>{escape(label)}</title></rect>')
    if selected:
        parts += [f'<text x="{left}" y="335">{selected[0]["date"]}</text>',
                  f'<text x="{left+width}" y="335" text-anchor="end">'
                  f'{selected[-1]["date"]} (UTC)</text>']
    for index, key in enumerate(COMPONENTS):
        x = 24 + index * 345
        parts += [f'<rect x="{x}" y="360" width="11" height="11" fill="{colors[key]}"/>',
                  f'<text x="{x+18}" y="370">{escape(messages[key])}</text>']
    return "\n".join([*parts, "</svg>", ""])


def prepare_report(
    data_dir: Path, rows: list[Row], seed_rows: list[Row], repo: str
) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate and render everything before any stored snapshot is replaced."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("invalid report repository")
    seed = baseline(data_dir, seed_rows)
    series = calendar_series(rows, seed, repo)
    catalogs = json.loads((WEB / "messages.json").read_text(encoding="utf-8"))
    output = {"site/timeline.json": json_text(series),
              "site/data.js": "globalThis.DOWNLOAD_DATA = " + json_text(series) + ";\n",
              "site/messages.js": "globalThis.DOWNLOAD_MESSAGES = " + json_text(catalogs) + ";\n",
              "site/preview.svg": preview_svg(series, catalogs["en"])}
    for name in ("index.html", "chart.js", "style.css"):
        output[f"site/{name}"] = (WEB / name).read_text(encoding="utf-8")
    return seed, output


def publish_report(data_dir: Path, output: dict[str, str]) -> None:
    for name, content in output.items():
        atomic_text(data_dir / name, content)
