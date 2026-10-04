"""The spike's Qt message recorder (ADR-047 evidence, senior review round 2).

A broken custom shader used to be invisible to the evidence: the run exited 0
with ``status: ok`` while the pond rendered another colour. The classifier
decides which Qt messages fail a run, so it is pinned on real message texts.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from open_garden_planner.spike_q3d.qt_messages import QtMessages, classify

# Measured: renaming one function in water.frag (senior review, 6f0c4f4).
SHADER_PARSE = ("QSpirvCompiler: Failed to parse shader: ERROR: 0:120: "
                "'qt_sampleGlossyRenamed' : no matching overloaded function found")


@pytest.mark.parametrize("kind, text", [
    ("warning", SHADER_PARSE),
    ("warning", "Failed to build graphics pipeline state"),
    ("warning", "file:///x/GardenSpike.qml:231:13: Unable to assign [undefined] to QObject*"),
    ("warning", "qrc:/x.qml:12: ReferenceError: groundTexture is not defined"),
    ("warning", "QQmlComponent: Component is not ready"),
    ("critical", "anything a Qt module reports as critical"),
    ("fatal", "anything fatal"),
])
def test_shader_and_qml_failures_are_errors(kind: str, text: str) -> None:
    assert classify(kind, text) == "error"


@pytest.mark.parametrize("kind, text, expected", [
    ("warning", "QStandardPaths: XDG_RUNTIME_DIR not set, defaulting to '/tmp/runtime-root'",
     "warning"),
    ("info", "Using RHI backend OpenGL", "info"),
    ("debug", "frame swapped", "info"),
])
def test_other_messages_do_not_fail_a_run(kind: str, text: str, expected: str) -> None:
    assert classify(kind, text) == expected


def test_recorder_counts_keeps_and_logs_only_what_matters() -> None:
    logged: list[dict] = []
    qt = QtMessages(lambda phase, **fields: logged.append({"phase": phase, **fields}))
    qt.add("info", "Using RHI backend OpenGL")
    qt.add("warning", "QStandardPaths: XDG_RUNTIME_DIR not set")
    qt.add("warning", SHADER_PARSE, "qt.shadertools")
    report = qt.report()
    assert report["counts"] == {"error": 1, "warning": 1, "info": 1}
    assert qt.errors == [f"warning: qt.shadertools: {SHADER_PARSE}"]
    assert [entry["level"] for entry in logged] == ["warning", "error"]  # info stays out


def test_recorder_is_bounded_for_a_long_soak() -> None:
    qt = QtMessages()
    for k in range(1000):
        qt.add("warning", f"noise {k}")
    assert qt.report()["counts"]["warning"] == 1000
    assert len(qt.report()["warnings"]) == 30


_LATE_MESSAGE = textwrap.dedent("""
    import sys
    from pathlib import Path
    from PyQt6.QtCore import QCoreApplication, qWarning
    from open_garden_planner.spike_q3d.qt_messages import QtMessages, install, uninstall
    from open_garden_planner.spike_q3d.runner import SpikeLog

    app = QCoreApplication([])
    log = SpikeLog(Path(sys.argv[1]) / "spike.log")
    install(QtMessages(log))
    if sys.argv[2] == "uninstall":
        uninstall()
    log.close()
    qWarning("a late Qt message, after the log closed")
    print("survived", flush=True)
""")


@pytest.mark.parametrize("mode", ["uninstall", "closed-log"])
def test_a_late_qt_message_cannot_abort_the_process(tmp_path: Path, mode: str) -> None:
    """Senior review reproduced exit 134: the handler wrote to the closed log, raised,
    and PyQt turned the exception into qFatal. The runner detaches the handler before
    the log closes ("uninstall"), and the recorder never raises ("closed-log")."""
    src = Path(__file__).resolve().parents[2] / "src"
    env = dict(os.environ, PYTHONPATH=str(src), QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _LATE_MESSAGE, str(tmp_path), mode],
        env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "survived" in proc.stdout
