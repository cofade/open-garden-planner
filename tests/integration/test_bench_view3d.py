"""``scripts/bench_view3d.py`` must not touch the user's settings (senior review).

Loading a plan records Recent Files; the script once wrote both bench plans into
the user's real list on every run. The run gets a private config home, so the
user's real store is out of reach either way, and the test reads which stores
it created.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="XDG config home is Linux")
def test_the_cpu_bench_writes_no_user_settings(tmp_path: Path) -> None:
    env = dict(os.environ, XDG_CONFIG_HOME=str(tmp_path), QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own script
        [sys.executable, str(REPO / "scripts" / "bench_view3d.py"), "--plans", "bench_small",
         "--repeat", "1"],
        env=env, capture_output=True, text=True, timeout=300, cwd=REPO,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    stores = sorted(p.name for p in tmp_path.iterdir())
    assert "cofade" not in stores, stores  # the app's real organization
    assert stores == ["cofade-ogp-tooling"], stores
