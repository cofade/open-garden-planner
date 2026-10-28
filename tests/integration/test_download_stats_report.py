"""Exercise the real file-input CLI, stored migration and self-contained site outputs."""

import json
import subprocess
import sys
from pathlib import Path

from scripts import download_stats as ds
from scripts import download_stats_report as report


def test_saved_snapshot_to_static_site_and_rebuild(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    data = tmp_path / "data"
    old = ds.Row("2026-08-03T17:00:00Z", "v1", "v1-Setup.exe", 1, 5,
                 "2026-08-01T00:00:00Z", False)
    ds.write_outputs(data, [old], ds.daily_deltas([old]))
    listing = tmp_path / "releases.json"
    listing.write_text(json.dumps([{
        "tag_name": "v1", "published_at": old.published_at,
        "assets": [{"name": old.asset, "id": 1, "download_count": 8}],
    }]), encoding="utf-8")
    args = [sys.executable, str(root / "scripts/download_stats.py"), "--data-dir", str(data),
            "--repo", "o/r"]
    subprocess.run([*args, "--releases-json", str(listing), "--now", "2026-08-04T00:17:00Z"],
                   cwd=root, check=True, capture_output=True, text=True)
    payload = json.loads((data / "site/timeline.json").read_text())
    assert sum(d[k] for d in payload["days"] for k in report.COMPONENTS) == 8
    assert payload["days"][-1]["observed"] == 3
    assert json.loads((data / report.BASELINE_FILE).read_text())["assets"][0]["download_count"] == 5
    summary = (data / "SUMMARY.md").read_text()
    assert summary.index("preview.svg") < summary.index("## Last")
    assert "https://o.github.io/r/" in summary
    for name in ("index.html", "style.css", "chart.js", "messages.js", "data.js", "preview.svg"):
        assert (data / "site" / name).stat().st_size > 0
    before = {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
    subprocess.run([*args, "--report-only"], cwd=root, check=True, capture_output=True, text=True)
    assert before == {p: p.read_bytes() for p in data.rglob("*") if p.is_file()}
