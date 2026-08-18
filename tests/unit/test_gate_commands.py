"""The gate commands in our own documentation must survive the shell that runs them.

Born from a real, self-inflicted defect (PR #334, 2026-08-19). The frozen-exe
``--selftest`` gate was added to four documents at once — ``CLAUDE.md``,
``AGENTS.md``, ``ogp-change-control`` §2.8 and ``ogp-build-and-run`` — written
with the **outer** string double-quoted::

    powershell -Command "$p = Start-Process '...' -Wait -PassThru; exit $p.ExitCode"

Bash expands ``$`` inside double quotes, so PowerShell received
``= Start-Process '...' ; exit .ExitCode``, threw two
``CommandNotFoundException``s, exited 1 and **never launched the exe**. Measured
directly by printing the child's ``argv``::

    outer double quotes -> [ = Start-Process 'x' -Wait -PassThru; exit .ExitCode]
    outer single quotes -> [$p = Start-Process "x" -Wait -PassThru; exit $p.ExitCode]

The commit before it had the opposite defect: a naked
``…OpenGardenPlanner.exe --selftest`` call, which PowerShell does not wait on
for a GUI-subsystem process — it returned in ~6 ms with an empty
``$LASTEXITCODE``, so the gate passed unconditionally. Both failure directions of
one line, one commit apart, in a change whose whole subject was not letting gate
lists drift.

Issue #336 proposes a citation resolver for the skill library; it would not have
caught this, because the *reference* resolved fine — the *command* was broken.
This file is the complement: not "do the documents point at real things?" but
"do the shell commands they prescribe still mean what they look like they mean?"

Deliberately static. It does **not** run the gates (that needs a built exe and
minutes of wall clock); it applies bash's own quoting rules to the documented
line and asserts the variables that must reach the child process actually do.

A first cut of this file used ``shlex.split(posix=True)`` and **passed on the
known-broken input** — ``shlex`` models tokenisation but not ``$`` expansion, so
``$p`` survived it either way. That near-miss is why every assertion here is
checked against the real defect before being trusted (see
``test_the_guard_rejects_the_defect_that_shipped``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: Every document that carries the frozen-exe gate. If a ninth copy appears, add
#: it here — or better, delete it and point at ``ogp-change-control`` §2.8.
_GATE_DOCS = (
    "CLAUDE.md",
    "AGENTS.md",
    ".claude/skills/ogp-change-control/SKILL.md",
    ".agents/skills/ogp-change-control/SKILL.md",
    ".claude/skills/ogp-build-and-run/SKILL.md",
    ".agents/skills/ogp-build-and-run/SKILL.md",
    ".claude/skills/deliver-package/SKILL.md",
    ".agents/skills/deliver-package/SKILL.md",
)

_SELFTEST_LINE = re.compile(r"^powershell -Command .*--selftest.*$", re.MULTILINE)
_VARIABLE = re.compile(r"\$\{?\w+")


def shell_exposed_variables(line: str) -> list[str]:
    """The ``$variables`` bash would expand before the child process sees them.

    Applies bash's quoting rules: inside **single** quotes ``$`` is literal;
    inside double quotes (or unquoted) it is expanded. A non-empty result means
    the documented command does not deliver what it appears to.
    """
    exposed: list[str] = []
    in_single = in_double = False
    index = 0
    while index < len(line):
        char = line[index]
        if char == "\\" and not in_single:
            index += 2
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "$" and not in_single:
            match = _VARIABLE.match(line, index)
            if match:
                exposed.append(match.group(0))
        index += 1
    return exposed


def _selftest_lines() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for name in _GATE_DOCS:
        path = _REPO_ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        found.extend((name, line) for line in _SELFTEST_LINE.findall(text))
    return found


_LINES = _selftest_lines()


def test_every_gate_doc_carries_the_selftest_line() -> None:
    """All eight copies must exist — a doc that quietly lost the gate is the
    original failure mode (#291 hid for six releases behind a weaker check)."""
    documented = {name for name, _ in _LINES}
    missing = set(_GATE_DOCS) - documented
    assert not missing, f"frozen-exe --selftest gate missing from: {sorted(missing)}"


@pytest.mark.parametrize("doc,line", _LINES, ids=[d for d, _ in _LINES])
def test_selftest_variables_reach_powershell(doc: str, line: str) -> None:
    """``$p`` must reach PowerShell rather than being eaten by bash."""
    exposed = shell_exposed_variables(line)
    assert not exposed, (
        f"{doc}: bash would expand {exposed} before PowerShell sees them — the "
        "outer string must be SINGLE-quoted, with the inner PowerShell "
        f"arguments double-quoted. Line: {line}"
    )


@pytest.mark.parametrize("doc,line", _LINES, ids=[d for d, _ in _LINES])
def test_selftest_waits_and_propagates_the_exit_code(doc: str, line: str) -> None:
    """``Start-Process -Wait -PassThru`` plus an explicit ``exit`` are required.

    Without ``-Wait``/``-PassThru`` PowerShell does not wait on a GUI-subsystem
    process and yields an empty exit code — a gate that passes whatever the
    selftest found. Without ``exit`` the caller never sees the child's code.
    """
    for required in ("Start-Process", "-Wait", "-PassThru", "exit"):
        assert required in line, f"{doc}: gate command is missing {required!r}"


@pytest.mark.parametrize("doc,line", _LINES, ids=[d for d, _ in _LINES])
def test_selftest_targets_the_built_exe_path(doc: str, line: str) -> None:
    """The path must match what ``installer/ogp.spec`` actually produces."""
    assert "dist/OpenGardenPlanner/OpenGardenPlanner.exe" in line, doc


def test_the_guard_rejects_the_defect_that_shipped() -> None:
    """Teeth, pinned against the literal broken line from commit 32c337f.

    Without this, a future simplification of ``shell_exposed_variables`` could
    silently reduce it to the ``shlex`` version that passed on this very input.
    """
    shipped_defect = (
        'powershell -Command "$p = Start-Process '
        "'dist/OpenGardenPlanner/OpenGardenPlanner.exe' -ArgumentList "
        "'--selftest' -Wait -PassThru; exit $p.ExitCode\""
    )
    assert shell_exposed_variables(shipped_defect) == ["$p", "$p"]

    corrected = (
        "powershell -Command '$p = Start-Process "
        '"dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList '
        "\"--selftest\" -Wait -PassThru; exit $p.ExitCode'"
    )
    assert shell_exposed_variables(corrected) == []


def test_guard_handles_escaping_and_mixed_quotes() -> None:
    """Sanity checks on the quoting model itself."""
    assert shell_exposed_variables("echo $HOME") == ["$HOME"]
    assert shell_exposed_variables("echo '$HOME'") == []
    assert shell_exposed_variables('echo "$HOME"') == ["$HOME"]
    assert shell_exposed_variables('echo "\\$HOME"') == []
    assert shell_exposed_variables("echo '\"$HOME\"'") == []
    assert shell_exposed_variables('echo "\'$HOME\'"') == ["$HOME"]
