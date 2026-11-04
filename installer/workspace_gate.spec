# -*- mode: python ; coding: utf-8 -*-
"""The GATE build of Open Garden Planner — test tooling, never shipped (Phase 17 L1.3).

The product build (``ogp.spec``) with ONE difference:
``tests/integration/workspace_gate_hook.py`` runs as a PyInstaller RUNTIME HOOK,
before the app's entry script. The hook moves the app's settings store to a
throw-away key and refuses any other (it fails closed, exit code 97) — which is
what makes it safe to script the frozen exe through "open a plan, enter 3D,
close": a plan load writes Recent Files and a clean close writes the window
geometry, and the registry key they go to is moved by no environment variable
(docs/08 §8.10.9).

    pyinstaller installer/workspace_gate.spec --noconfirm --distpath <dir> --workpath <dir>
    # then: OGP_WORKSPACE_GATE_EXE=<dir>/OpenGardenPlannerGate/OpenGardenPlannerGate.exe
    #       OGP_RENDER3D=1 pytest tests/integration/test_view3d_workspace_render.py -k frozen

The recipe is NOT copied: this file executes the text of ``ogp.spec`` with the
hook list and the two output names changed, and refuses to build when that text
no longer has exactly those anchors — a gate build that silently differs from
the product build would prove nothing about the product.
"""

from pathlib import Path

_product = Path(SPECPATH) / "ogp.spec"  # noqa: F821 - SPECPATH is PyInstaller's
_hook = Path(SPECPATH).parent / "tests" / "integration" / "workspace_gate_hook.py"  # noqa: F821
_text = _product.read_text(encoding="utf-8")
for _old, _new, _times in (
    ("    runtime_hooks=[],\n", f"    runtime_hooks=[{str(_hook)!r}],\n", 1),
    ('    name="OpenGardenPlanner",\n', '    name="OpenGardenPlannerGate",\n', 2),
):
    if _text.count(_old) != _times:
        raise SystemExit(f"workspace_gate.spec: ogp.spec has {_old.strip()!r} "
                         f"{_text.count(_old)} time(s), not {_times} - adapt the gate spec")
    _text = _text.replace(_old, _new)
if not _hook.is_file():
    raise SystemExit(f"workspace_gate.spec: the runtime hook is missing: {_hook}")
exec(compile(_text, str(_product), "exec"))  # noqa: S102 - this repository's own spec
