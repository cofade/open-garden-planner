"""Regression guard for issue #277 — the Qt3D wheels must be built for the
SAME Qt micro as the core Qt runtime, or Qt3DCore fails to import in a frozen
build and the 3D view silently kills the process when the user opens it.

Root cause: pyproject hard-pinned PyQt6-3D-Qt6 but left PyQt6-Qt6 free to
float, so a fresh CI resolve mixed Qt6Core.dll 6.11.1 with Qt3D DLLs built for
6.11.0. These assertions fail fast in the fast CI test job if the pins ever
drift again. They import NO Qt3D module (only metadata + qVersion), so they
need no display or GL context and are safe on the offscreen CI runner — the
real DLL-load exercise is the frozen-exe ``--selftest`` in release.yml.
"""

from importlib.metadata import version

from PyQt6.QtCore import qVersion


def test_qt3d_wheel_matches_core_qt_runtime(qtbot) -> None:  # noqa: ARG001
    """The loaded Qt6Core.dll (``qVersion``) must equal the Qt version the
    Qt3D wheels were built for (``PyQt6-3D-Qt6``'s version)."""
    runtime = qVersion()
    qt3d_qt = version("PyQt6-3D-Qt6")
    assert runtime == qt3d_qt, (
        f"Qt runtime {runtime} != Qt3D wheel {qt3d_qt} (issue #277): Qt3DCore "
        "will fail to import against a mismatched Qt6Core.dll. Pin PyQt6-Qt6 "
        "and PyQt6-3D-Qt6 to equal micros in pyproject.toml."
    )


def test_core_and_qt3d_runtime_wheels_pinned_equal(qtbot) -> None:  # noqa: ARG001
    """The two Qt runtime wheels (core + Qt3D) must resolve to equal micros —
    the pin-level invariant behind the DLL-level check above."""
    core = version("PyQt6-Qt6")
    qt3d = version("PyQt6-3D-Qt6")
    assert core == qt3d, (
        f"PyQt6-Qt6 {core} != PyQt6-3D-Qt6 {qt3d} (issue #277): pin both to "
        "the same version in pyproject.toml."
    )
