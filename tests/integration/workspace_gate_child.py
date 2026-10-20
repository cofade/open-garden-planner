"""The app's own ``main()`` under the workspace gate hook — from source (L1.3).

Not a test module. ``python workspace_gate_child.py [plan.ogp]`` with
``OGP_WORKSPACE_GATE`` naming the scenario file: see ``workspace_gate_hook.py``, which
is imported FIRST — before anything of the app — so that the settings store this
process builds is a throw-away one. The frozen exe gets the same hook as a
PyInstaller runtime hook (``workspace_gate.spec``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import workspace_gate_hook  # noqa: E402, F401, I001 - must precede every app import

from open_garden_planner.main import main  # noqa: E402 - after the hook, on purpose

if __name__ == "__main__":
    sys.exit(main())
