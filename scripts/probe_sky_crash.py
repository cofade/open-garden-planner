"""Soak the sky in the full app: the probe behind PF-E3D-17 (#391).

Qt 6.12.0's ``SkyMaterial`` light cube used a freed QRhi resource and killed the process
with no Python trace. This drives the real app, from source, through the manual checklist's
actions in a seeded loop: bench_small.ogp in 3D, the time, the weather, the walk, the reduced
motion, the sky model and the workspace mode. Every action is printed and logged BEFORE it
runs, so the last line before a crash names it. Settings are isolated.

    venv/Scripts/python.exe -X faulthandler scripts/probe_sky_crash.py --seconds 240

Exit 0 and a last line of "no crash" is a pass. A crash leaves no exit code worth reading:
read the log it names (a native stack in ``faulthandler``'s format, thread by thread), then
``%LOCALAPPDATA%\\CrashDumps``. The same seed gives the same actions, but not the same
timing: seed 7 crashed 3 of 5 runs on the old build, so run it several times.

``--extra`` adds what the old build's runs did not have (a resize, Partly cloudy). It changes
the seed's sequence, so leave it off to repeat the seed-7 runs of PF-E3D-17.
"""

from __future__ import annotations

import argparse
import faulthandler
import random
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import time as dtime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "src"))

import script_isolation  # noqa: E402

if __name__ == "__main__":
    script_isolation.isolate_profile()

# Match the product's required WebEngine-before-QApplication import order.
import open_garden_planner.main  # noqa: E402,F401

PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
WEATHERS = ["clear", "overcast", "rain", "snow"]
SIZES = [(1600, 1000), (1100, 700), (1900, 1040), (800, 600)]
#: Delays between actions, in ms: bursts as well as rests.
DELAYS_MS = [80, 150, 300, 600, 1200]
#: The action's share of the loop.
WEIGHTS = {"time": 10, "weather": 3, "walk": 1, "motion": 1, "sky": 1, "mode": 1}


def main() -> int:
    script_isolation.isolate()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=240.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--sky", default="atmosphere", choices=("painted", "atmosphere"))
    parser.add_argument("--quality", default="ultra")
    parser.add_argument("--only", default="", help="comma-separated actions, e.g. sky,weather")
    parser.add_argument("--extra", action="store_true", help="also resize, and Partly cloudy")
    parser.add_argument("--log", type=Path, help="default: a file in the temp folder")
    args = parser.parse_args()

    log_path = args.log or Path(tempfile.gettempdir()) / f"ogp_sky_probe_{args.seed}.txt"
    log = log_path.open("w", encoding="utf-8")
    faulthandler.enable(file=log, all_threads=True)
    start_time = time.monotonic()

    def say(message: str) -> None:
        line = f"[PROBE] {time.monotonic() - start_time:7.2f}s {message}"
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.app.application import GardenPlannerApp
    from open_garden_planner.app.settings import (
        APPLICATION_NAME,
        ORGANIZATION_NAME,
        get_settings,
    )
    from open_garden_planner.core.i18n import load_translator
    from open_garden_planner.ui.theme import apply_theme
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode

    rng = random.Random(args.seed)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APPLICATION_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)
    settings = get_settings()
    settings.view3d_sky_model = args.sky
    settings.view3d_quality = args.quality
    settings.show_welcome_on_startup = False
    settings.agent_api_enabled = False
    settings.language = "de"
    load_translator(app, "de")
    apply_theme(app, settings.theme_mode)
    GardenPlannerApp._show_welcome_dialog = lambda _self: None
    window = GardenPlannerApp()
    window.resize(*SIZES[0])
    window.show()
    window._open_project_file(str(PLAN))

    workspace = window._workspace
    clock = window._sim_clock
    weathers = [*WEATHERS, "partly_cloudy"] if args.extra else WEATHERS
    state = {"minute": 9 * 60, "walk": False, "reduced": False, "sky": args.sky, "count": 0}

    def a_time() -> None:
        state["minute"] = (state["minute"] + rng.choice([5, 10, 15, 30, 45])) % (24 * 60)
        minute = state["minute"]
        say(f"time {minute // 60:02d}:{minute % 60:02d}")
        clock.set_time_of_day(dtime(minute // 60, minute % 60))

    def a_weather() -> None:
        weather = rng.choice(weathers)
        say(f"weather {weather}")
        workspace.living.set_weather(weather)

    def a_walk() -> None:
        state["walk"] = not state["walk"]
        say(f"walk {state['walk']}")
        workspace.set_walking(state["walk"])

    def a_motion() -> None:
        look = workspace.look
        if look is None:
            say("motion: no look yet")
            return
        state["reduced"] = not state["reduced"]
        say(f"system reduced motion {state['reduced']}")
        look.set_system_reduced_motion(state["reduced"])

    def a_sky() -> None:
        state["sky"] = "painted" if state["sky"] == "atmosphere" else "atmosphere"
        say(f"sky {state['sky']}")
        settings.view3d_sky_model = state["sky"]
        workspace.apply_look_settings()

    def a_mode() -> None:
        mode = rng.choice([WorkspaceMode.VIEW3D, WorkspaceMode.SPLIT, WorkspaceMode.VIEW3D])
        say(f"mode {mode.name}")
        workspace.set_mode(mode)

    def a_resize() -> None:
        width, height = rng.choice(SIZES)
        say(f"resize {width}x{height}")
        window.resize(width, height)

    actions: dict[str, Callable[[], None]] = {
        "time": a_time, "weather": a_weather, "walk": a_walk, "motion": a_motion,
        "sky": a_sky, "mode": a_mode}
    weights = dict(WEIGHTS)
    if args.extra:
        actions["resize"] = a_resize
        weights["resize"] = 2
    if args.only:
        wanted = set(args.only.split(","))
        actions = {name: action for name, action in actions.items() if name in wanted}
    names = [name for name in actions for _ in range(weights[name])]

    def step() -> None:
        if time.monotonic() - start_time > args.seconds:
            say(f"done after {state['count']} actions, no crash")
            app.quit()
            return
        state["count"] += 1
        name = rng.choice(names)
        try:
            actions[name]()
        except Exception as error:
            say(f"action {name} raised {type(error).__name__}: {error}")
        QTimer.singleShot(rng.choice(DELAYS_MS), step)

    def begin() -> None:
        say("3D mode")
        workspace.set_mode(WorkspaceMode.VIEW3D)
        QTimer.singleShot(8000, step)

    QTimer.singleShot(1500, begin)
    say(f"seed {args.seed} seconds {args.seconds} sky {args.sky} quality {args.quality} "
        f"actions {sorted(actions)} log {log_path}")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
