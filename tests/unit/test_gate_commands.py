"""The gate commands in our own documentation must survive the shell that runs them.

Born from a real, self-inflicted defect (PR #334, 2026-08-19). The frozen-exe
``--selftest`` gate was added to several documents at once, written with the
**outer** string double-quoted::

    powershell -Command "$p = Start-Process '...' -Wait -PassThru; exit $p.ExitCode"

Bash expands ``$`` inside double quotes, so PowerShell received
``= Start-Process '...' ; exit .ExitCode``, threw two
``CommandNotFoundException``s, exited 1 and **never launched the exe**. Measured
by printing the child's ``argv``::

    outer double quotes -> [ = Start-Process 'x' -Wait -PassThru; exit .ExitCode]
    outer single quotes -> [$p = Start-Process "x" -Wait -PassThru; exit $p.ExitCode]

The commit before it had the opposite defect: a naked
``…OpenGardenPlanner.exe --selftest``, which PowerShell does not wait on for a
GUI-subsystem process — it returned in ~6 ms with an empty ``$LASTEXITCODE``, so
the gate passed unconditionally. Both failure directions of one line, one commit
apart, in a change whose whole subject was not letting gate lists drift.

**Discovery, not a curated list.** An earlier version of this file pinned the
documents by name — a curated list defending against curated lists, and it was
wrong on its first run: eight documents were listed while sixteen prescribe the
exe gate, so six skills kept prescribing the 8-second smoke alone while citing
``CLAUDE.md``'s Quick Reference as their authority. Now every tracked document
that prescribes the smoke is *required* to prescribe ``--selftest`` too, so a
new copy is covered the moment it appears.

Two guards, aimed at different failure classes:

* :func:`shell_exposed_variables` — what bash would expand or execute before the
  child process sees it. Its first implementation used ``shlex.split`` and
  **passed on the known-broken line** (shlex models tokenisation, not
  expansion); its second caught ``$NAME`` only, and a reviewer bypassed it with
  PowerShell's ``$?`` idiom. It now also models ``$(…)``, backticks and bash's
  special parameters.
* the presence/shape checks — ``-Wait``/``-PassThru``/``exit`` and the built-exe
  path, so a *syntactically valid* command that silently does nothing is still
  rejected.

Issue #336 proposes a citation resolver for the skill library; it would not have
caught any of this, because the references resolved fine — the *commands* were
broken. This file is the complement.

Static by design: it does not run the gates (that needs a built exe and minutes
of wall clock).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: A document that prescribes this must also prescribe ``--selftest``.
_SMOKE_MARKER = "timeout 8 dist/OpenGardenPlanner"
_EXE_PATH = "dist/OpenGardenPlanner/OpenGardenPlanner.exe"

_SELFTEST_LINE = re.compile(r"^\s*powershell -Command .*--selftest.*$", re.MULTILINE)

#: ``$NAME`` / ``${NAME}``, and bash's special parameters — ``$?`` is the one a
#: reviewer used to walk straight past the previous version of this guard.
_VARIABLE = re.compile(r"\$\{\w+\}|\$\w+|\$[?$#!*@\-0-9]")


def _tracked_markdown() -> list[Path]:
    """Every tracked ``.md`` file, from git — so worktrees and build output are
    excluded without maintaining an ignore list."""
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "ls-files", "*.md"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [_REPO_ROOT / line for line in out.stdout.split("\n") if line.strip()]


def shell_exposed_variables(line: str) -> list[str]:
    """What bash would expand or execute before the child process sees ``line``.

    Models the subset of bash that can silently rewrite a documented command:
    ``$VAR`` / ``${VAR}``, the special parameters (``$?`` ``$$`` ``$#`` …),
    ``$(…)`` command substitution and backtick command substitution — each
    neutralised inside **single** quotes, live inside double quotes or unquoted.
    Backslash escapes are honoured outside single quotes.

    A non-empty result means the documented command does not deliver what it
    appears to. An unterminated quote is reported as ``"<unterminated quote>"``,
    since bash rejects the line outright.

    Not a complete shell parser, and deliberately so — but the docstring is kept
    honest about what it covers, because a guard that *looks* like a shell model
    invites trust it has not earned.
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
        elif not in_single:
            if char == "`":
                exposed.append("`…` command substitution")
            elif char == "$":
                if line.startswith("$(", index):
                    exposed.append("$(…) command substitution")
                else:
                    match = _VARIABLE.match(line, index)
                    if match:
                        exposed.append(match.group(0))
        index += 1
    if in_single or in_double:
        exposed.append("<unterminated quote>")
    return exposed


def _docs_prescribing_the_smoke() -> list[Path]:
    return [
        path
        for path in _tracked_markdown()
        if _SMOKE_MARKER in path.read_text(encoding="utf-8")
    ]


def _selftest_lines() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _docs_prescribing_the_smoke():
        name = path.relative_to(_REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        found.extend((name, line.strip()) for line in _SELFTEST_LINE.findall(text))
    return found


_LINES = _selftest_lines()
_IDS = [name for name, _ in _LINES]


def test_every_smoke_doc_also_prescribes_selftest() -> None:
    """Discovery, not a curated list.

    The 8-second smoke proves only that the process stays up; it cannot see a
    subsystem that died silently, which is how #291 survived six releases and
    how #277 shipped a crash. Any document telling a reader to run the smoke
    must tell them to run ``--selftest`` too, or it is the weaker of two
    competing gate definitions.
    """
    missing = [
        path.relative_to(_REPO_ROOT).as_posix()
        for path in _docs_prescribing_the_smoke()
        if not _SELFTEST_LINE.search(path.read_text(encoding="utf-8"))
    ]
    assert not missing, (
        "these documents prescribe the 8-second exe smoke but not --selftest, so "
        "they are a weaker copy of the gate in ogp-change-control section 2.8: "
        f"{missing}"
    )


def test_discovery_found_the_gate_documents() -> None:
    """Guard the guard: if the marker string ever changes, the two tests above
    would vacuously pass over an empty set."""
    assert len(_docs_prescribing_the_smoke()) >= 8
    assert _LINES, "no --selftest lines discovered at all"


@pytest.mark.parametrize("doc,line", _LINES, ids=_IDS)
def test_selftest_survives_the_shell(doc: str, line: str) -> None:
    """No ``$``/backtick construct may be eaten or executed by bash first."""
    exposed = shell_exposed_variables(line)
    assert not exposed, (
        f"{doc}: bash would expand or execute {exposed} before PowerShell sees "
        "the command — the outer string must be SINGLE-quoted, with the inner "
        f"PowerShell arguments double-quoted. Line: {line}"
    )


@pytest.mark.parametrize("doc,line", _LINES, ids=_IDS)
def test_selftest_waits_and_propagates_the_exit_code(doc: str, line: str) -> None:
    """``Start-Process -Wait -PassThru`` plus an explicit ``exit`` are required.

    Without ``-Wait``/``-PassThru`` PowerShell does not wait on a GUI-subsystem
    process and yields an empty exit code — a gate that passes whatever the
    selftest found. Without ``exit`` the caller never sees the child's code.
    """
    for required in ("Start-Process", "-Wait", "-PassThru", "exit"):
        assert required in line, f"{doc}: gate command is missing {required!r}"
    assert "$p.ExitCode" in line, (
        f"{doc}: the exit code must come from the child process object, not from "
        "PowerShell state such as $? — that reports whether the LAST statement "
        "succeeded, not what the selftest found"
    )


@pytest.mark.parametrize("doc,line", _LINES, ids=_IDS)
def test_selftest_targets_the_built_exe_path(doc: str, line: str) -> None:
    """The path must match what ``installer/ogp.spec`` actually produces."""
    assert _EXE_PATH in line, doc


class TestTheGuardItself:
    """Teeth, pinned against real defects rather than invented ones."""

    def test_rejects_the_defect_that_shipped(self) -> None:
        shipped = (
            'powershell -Command "$p = Start-Process '
            f"'{_EXE_PATH}' -ArgumentList '--selftest' -Wait -PassThru; "
            'exit $p.ExitCode"'
        )
        assert shell_exposed_variables(shipped) == ["$p", "$p"]

    def test_rejects_the_reviewers_bypass(self) -> None:
        """A reviewer walked past the previous version with PowerShell's ``$?``
        idiom: bash substitutes its own last exit status, PowerShell evaluates a
        constant, and the gate becomes unconditional."""
        bypass = (
            'powershell -Command "Start-Process '
            f"'{_EXE_PATH}' -ArgumentList '--selftest' -Wait -PassThru; "
            'if ($?) { exit 0 } else { exit 1 }"'
        )
        assert "$?" in shell_exposed_variables(bypass)

    def test_rejects_command_substitution(self) -> None:
        assert shell_exposed_variables('powershell -Command "$(echo PWNED)"') == [
            "$(…) command substitution"
        ]
        assert shell_exposed_variables('powershell -Command "`echo PWNED`"') == [
            "`…` command substitution",
            "`…` command substitution",
        ]

    def test_rejects_an_unterminated_quote(self) -> None:
        assert "<unterminated quote>" in shell_exposed_variables("powershell -c 'x")

    def test_accepts_the_corrected_form(self) -> None:
        corrected = (
            "powershell -Command '$p = Start-Process "
            f'"{_EXE_PATH}" -ArgumentList "--selftest" -Wait -PassThru; '
            "exit $p.ExitCode'"
        )
        assert shell_exposed_variables(corrected) == []

    def test_quoting_model_matches_bash(self) -> None:
        assert shell_exposed_variables("echo $HOME") == ["$HOME"]
        assert shell_exposed_variables("echo '$HOME'") == []
        assert shell_exposed_variables('echo "$HOME"') == ["$HOME"]
        assert shell_exposed_variables('echo "\\$HOME"') == []
        assert shell_exposed_variables("echo '\"$HOME\"'") == []
        assert shell_exposed_variables('echo "\'$HOME\'"') == ["$HOME"]
        assert shell_exposed_variables("echo ${HOME}") == ["${HOME}"]
        assert shell_exposed_variables('echo "$$"') == ["$$"]

    def test_indented_gate_lines_are_still_discovered(self) -> None:
        """A doc that indents the command inside a list item still counts — an
        earlier version anchored at column 0 and reported the gate as *missing*,
        which is a false and actively misleading diagnostic."""
        indented = "  powershell -Command 'x --selftest y'"
        assert _SELFTEST_LINE.search(indented) is not None
