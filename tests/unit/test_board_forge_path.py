"""The board's frame and FPS instruments must render the same forged plants."""

import ast
from pathlib import Path


def test_board_fps_and_frames_share_the_forged_scene_upgrade():
    root = Path(__file__).resolve().parents[2]
    paths_and_functions = [
        (root / "scripts/render_beauty_board.py", "frame_rate"),
        (root / "src/open_garden_planner/ui/view3d/quick3d/offscreen.py", "render_records"),
    ]
    for path, function in paths_and_functions:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        (body,) = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function]
        calls = [n for n in ast.walk(body) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "forge_scene_plants"]
        assert len(calls) == 1, f"{function} bypasses the shared production forge upgrade"
        assert "plant_date" in {kw.arg for kw in calls[0].keywords}
