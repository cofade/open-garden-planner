#!/usr/bin/env python
"""Measure the widget graphs a GardenPlannerApp leaves behind (#515).

``tests/conftest.py::_reclaim_widgets`` removes the leak's *cost* without identifying its
cause. The measurement during #509 lived in a scratch directory and could not be re-run:
a clean process holds 0 widgets, and after ``tests/ui/test_main_window.py`` the process
holds 38 271 widgets (1 580 top-level), 0 % of them visible, so one ``apply_theme()``
round-trip costs ~22 s instead of 1.3 ms. This is that probe, committed.

Modes
-----
``apps --count N``
    Construct N full ``GardenPlannerApp`` windows and close each without deleting it (the
    ``qtbot.addWidget`` shape). Report counts right after the loop, after ``gc.collect()``
    and after the survivors are ``deleteLater``-ed. ``--delete-each`` closes AND deletes
    each app instead — the two-case comparison the issue asks for.

``per-test FILE...``
    Run one or more test files with the reclaim fixture disabled and a counting plugin,
    printing the widget count after each test's teardown. Answers "which of the 30 leaks,
    and how much each".

``parents --count N``
    Construct/close N apps, then sample surviving widgets and print their parent chains:
    the probe for "are the survivors' C++ parents the closed windows?".

Run it with the project venv::

    venv/Scripts/python.exe scripts/probe_widget_leaks.py apps --count 5
    venv/Scripts/python.exe scripts/probe_widget_leaks.py per-test tests/ui/test_main_window.py
    venv/Scripts/python.exe scripts/probe_widget_leaks.py parents --count 5

It writes nothing to the owner's QSettings profile: importing ``tests.conftest`` rebinds
the organization to ``cofade_test`` before the first app is built.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: Set by `per-test`; the plugin role appends one JSON object per test.
PROBE_OUT = "OGP_WIDGET_PROBE_OUT"


def _prepare_isolation() -> None:
    """Rebind QSettings to the test key and keep the app quiet.

    Importing the root conftest runs its module-level rebinding (organization
    ``cofade_test``), so the probe never writes to the owner's profile. The welcome dialog
    is patched out rather than relying on its setting, exactly as the suite does.
    """
    import tests.conftest  # noqa: F401  (module-level rebinding is the point)

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import AppSettings, create_qsettings

    store = create_qsettings()
    store.setValue(AppSettings.KEY_AGENT_API_ENABLED, False)
    store.setValue(AppSettings.KEY_SHOW_WELCOME, False)
    GardenPlannerApp._show_welcome_dialog = lambda _self: None  # type: ignore[method-assign]


def _counts(app) -> dict[str, int]:
    widgets = app.allWidgets()
    return {
        "widgets": len(widgets),
        "top_level": len(app.topLevelWidgets()),
        "visible": sum(1 for widget in widgets if widget.isVisible()),
    }


def _flush(app) -> None:
    from PyQt6.QtCore import QCoreApplication, QEvent

    app.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _construct(count: int, delete_each: bool) -> int:
    _prepare_isolation()
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.app.application import GardenPlannerApp

    app = QApplication.instance() or QApplication([])
    print(f"start: {_counts(app)}")
    for index in range(count):
        window = GardenPlannerApp()
        window.show()
        window.close()
        if delete_each:
            window.deleteLater()
            _flush(app)
        if (index + 1) % 5 == 0 or index == count - 1:
            print(f"after {index + 1:>2} app(s): {_counts(app)}")
    # The loop variable is the probe's own strong reference to the LAST app; holding it
    # would make the post-gc count describe this script instead of the leak.
    window = None
    del window
    after_loop = _counts(app)
    gc.collect()
    after_gc = _counts(app)
    _flush(app)
    print(f"after gc.collect(): {after_gc}")
    print(f"loop total: {after_loop}")
    return app


def mode_apps(count: int, delete_each: bool) -> int:
    app = _construct(count, delete_each)
    if not delete_each:
        for widget in app.topLevelWidgets():
            widget.deleteLater()
        _flush(app)
    print(f"after deleteLater on the survivors: {_counts(app)}")
    return 0


def mode_parents(count: int) -> int:
    app = _construct(count, delete_each=False)
    from PyQt6 import sip
    from PyQt6.QtWidgets import QWidget

    top_levels = app.topLevelWidgets()
    print(f"\n{len(top_levels)} surviving top-level widget(s)")
    for index, widget in enumerate(top_levels[:10]):
        print(
            f"  [{index}] {type(widget).__name__} "
            f"visible={widget.isVisible()} deleted={sip.isdeleted(widget)} "
            f"parent={type(widget.parentWidget()).__name__ if widget.parentWidget() else None}"
        )
    samples = [w for w in app.allWidgets() if not w.isVisible()][:5]
    print(f"\nsampled {len(samples)} invisible widget(s), parent chain outward:")
    for widget in samples:
        chain = []
        node: QWidget | None = widget
        for _ in range(6):
            if node is None:
                break
            chain.append(f"{type(node).__name__}{'' if node.isVisible() else '(hidden)'}")
            node = node.parentWidget()
        print("  " + " <- ".join(chain))
    return 0


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item):  # pragma: no cover - only runs under -p
    """Plugin role: record the live widget count AFTER each test's teardown."""

    def record() -> None:
        out = os.environ.get(PROBE_OUT)
        if not out:
            return
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance()
        counts = {"widgets": 0, "top_level": 0, "visible": 0}
        if app is not None:
            counts = _counts(app)
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"nodeid": item.nodeid, **counts}) + "\n")

    yield
    record()


def pytest_sessionfinish():  # pragma: no cover - only runs under -p
    """Plugin role: the decisive experiment for #515's holder question.

    When ``OGP_WIDGET_PROBE_GC=1``, count the survivors, run one full collection, and
    count again. If the population collapses, the widgets are **uncollected cyclic
    garbage** (no strong holder), and the "strong references" reading in #509 came from
    measuring before a collection. If it does not, a strong reference remains and the
    next step is a creation-time referrer probe.
    """
    if os.environ.get("OGP_WIDGET_PROBE_GC") != "1":
        return
    import gc

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        print("\n[probe] no QApplication at session finish")
        return
    before = _counts(app)
    print(f"\n[probe] widgets before gc.collect(): {before}")
    for pass_number in range(1, 4):
        collected = gc.collect()
        counts = _counts(app)
        print(
            f"[probe] pass {pass_number}: widgets {counts['widgets']} "
            f"(objects collected: {collected})"
        )
        if counts["widgets"] == 0:
            break


def mode_per_test(files: list[str]) -> int:
    if not files:
        print("per-test needs at least one test file")
        return 2
    with tempfile.TemporaryDirectory(prefix="ogp-widget-probe-") as directory:
        out = Path(directory) / "counts.jsonl"
        env = dict(os.environ)
        env["OGP_TEST_MEASURE_WIDGET_LEAK"] = "1"
        env[PROBE_OUT] = str(out)
        command = [
            sys.executable,
            "-m",
            "pytest",
            *files,
            "-q",
            "--no-header",
            "-n",
            "0",
            "-p",
            "scripts.probe_widget_leaks",
        ]
        print(f"running: {' '.join(command)}")
        subprocess.run(command, cwd=REPO, env=env, check=False)  # noqa: S603
        if not out.exists():
            print("the probe plugin wrote no counts (was it imported?)")
            return 1
        rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
        print("\nwidgets after each test (delta = what that test leaked):")
        previous = 0
        for row in rows:
            delta = row["widgets"] - previous
            previous = row["widgets"]
            name = row["nodeid"].split("::")[-1]
            print(
                f"  {name:<58} total={row['widgets']:>6}  "
                f"top={row['top_level']:>5}  delta={delta:>6}"
            )
        print(f"\nfinal total={previous}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    apps = sub.add_parser("apps", help="construct N apps and measure the leak")
    apps.add_argument("--count", type=int, default=5)
    apps.add_argument(
        "--delete-each",
        action="store_true",
        help="close AND deleteLater each app (the opposite case)",
    )
    per_test = sub.add_parser("per-test", help="per-test widget counts with the reclaim off")
    per_test.add_argument("files", nargs="+")
    parents = sub.add_parser("parents", help="parent-chain survey of the survivors")
    parents.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    if args.mode == "apps":
        return mode_apps(args.count, args.delete_each)
    if args.mode == "per-test":
        return mode_per_test(args.files)
    return mode_parents(args.count)


if __name__ == "__main__":
    raise SystemExit(main())
