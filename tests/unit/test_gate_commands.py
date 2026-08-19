"""One home for the frozen-exe gate command, and it must survive its shell.

Two rules, both born from real self-inflicted defects in PR #334.

**Rule 1 — the command literal lives in one place.** An early draft of this file
reacted to "eight documents prescribe a weaker gate" by copying the corrected
command into ten more, then guarding the copies with a hand-maintained list of
filenames. A reviewer named it: the response to *"a second copy of a gate list is
how a gate goes missing"* was to make eighteen copies. So the literals now live
only in :data:`SANCTIONED_HOMES` — the canonical definition
(``ogp-change-control`` §2.8), its mechanics (``ogp-build-and-run``) and the
copy-paste Quick Reference in the root instructions — and every other document
**cites** §2.8 by name. The CI workflow that actually runs the gate is checked
separately, on its own terms (see :data:`_RELEASE_WORKFLOW`).

**Rule 2 — wherever it does appear, it must work.** The command was wrong twice
in two commits:

* ``…OpenGardenPlanner.exe --selftest`` — PowerShell does not wait on a
  GUI-subsystem process; it returned in ~6 ms with an empty ``$LASTEXITCODE``.
  The gate passed unconditionally.
* ``powershell -Command "$p = Start-Process …; exit $p.ExitCode"`` — bash expands
  ``$`` inside double quotes, so PowerShell received
  ``= Start-Process …; exit .ExitCode``, threw two ``CommandNotFoundException``s
  and exited 1 without launching the exe. The gate failed unconditionally.

Measured by printing the child's ``argv``::

    outer double quotes -> [ = Start-Process 'x' -Wait -PassThru; exit .ExitCode]
    outer single quotes -> [$p = Start-Process "x" -Wait -PassThru; exit $p.ExitCode]

Every version of this guard was itself defeated, and each defeat is now a teeth
case: ``shlex.split`` modelled tokenisation but not expansion and passed on the
first defect; a ``$NAME``-only scanner was bypassed with PowerShell's ``$?``; and
substring checks for ``Start-Process``/``-Wait``/``-PassThru``/``exit`` were
bypassed by dropping the ``$p =`` assignment while keeping ``exit $p.ExitCode``,
which exits 0 whatever the child returned.

Static by design: it does not run the gates (that needs a built exe and minutes
of wall clock). Issue #336 proposes a citation resolver for the skill library;
that checks references *resolve*, this checks commands *run*.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The only files allowed to carry the command literal. Everything else cites
#: ``ogp-change-control`` §2.8 by name. Short and meaningful by construction —
#: unlike the eighteen-name list this replaced, adding an entry here is a
#: decision to accept another copy, not routine maintenance.
SANCTIONED_HOMES = frozenset(
    {
        "CLAUDE.md",
        "AGENTS.md",
        ".claude/skills/ogp-change-control/SKILL.md",
        ".agents/skills/ogp-change-control/SKILL.md",
        ".claude/skills/ogp-build-and-run/SKILL.md",
        ".agents/skills/ogp-build-and-run/SKILL.md",
    }
)

#: The CI step that actually runs the gate. Deliberately NOT in
#: :data:`SANCTIONED_HOMES`: it declares ``shell: pwsh``, so no bash ever sees
#: it and the quoting rules above are a category error there. It gets its own
#: assertion instead — a reviewer was right that the file where the command
#: really executes must be inside the guard, but it is inside it on its own
#: terms.
_RELEASE_WORKFLOW = ".github/workflows/release.yml"

_EXE = "OpenGardenPlanner.exe"

#: Lines allowed to name the exe without being a command: prose that refers to
#: the build output, and the ADR's historical spike record.
_PROSE_ALLOWLIST = (
    "docs/09-architecture-decisions/README.md",
)

_SELFTEST_LINE = re.compile(r"^.*powershell -Command .*--selftest.*$", re.MULTILINE)


def is_runnable_invocation(line: str) -> bool:
    """Whether ``line`` *invokes* the exe rather than merely naming it.

    Deliberately broad. Every previous version of this predicate enumerated
    launcher spellings — ``^timeout \\d+ …`` and ``^powershell -Command …`` — and
    a reviewer walked past it four times in one round with ``pwsh -Command``,
    ``powershell -c``, a bare ``…exe --selftest`` and a bullet-prefixed
    ``- timeout 8 …``, while three real violations already in the tree stayed
    invisible. Reality has more spellings than a regex, so this recognises the
    **path in a command position** and treats only clear prose as exempt.

    Prose, for this purpose, is a line where the exe appears inside inline
    backticks *as a bare path* with no shell verb anywhere on the line.
    """
    if _EXE not in line:
        return False
    stripped = line.strip().lstrip("-*>| `").strip()
    lowered = stripped.lower()
    # A launcher anywhere on the line, or the exe path invoked directly at the
    # start of it (`dist/…exe --selftest`). Both spellings have been used to
    # walk past narrower versions of this predicate.
    launched = any(
        token in lowered
        for token in ("timeout ", "powershell ", "pwsh ", "start-process")
    ) or lowered.startswith(("dist/", "./dist/", "$exe", "&"))
    if not launched:
        return False
    # ...but a sentence that merely NAMES the path is prose, even though it
    # contains "dist/": "a 3D engine that … dies in `dist/…exe`".
    return not re.search(r"\b(dies|lives|found|produced|appears|exists)\b", lowered)

#: ``$NAME`` / ``${NAME}`` / ``${?}``, and bash's special parameters — ``$?`` is
#: the one a reviewer used to walk past an earlier version of this guard.
_VARIABLE = re.compile(r"\$\{\w+\}|\$\{[?$#!*@\-0-9]\}|\$\w+|\$[?$#!*@\-0-9]")


def _tracked(*patterns: str) -> list[Path]:
    """Tracked files matching ``patterns``, from git.

    Skipped rather than failed when git is unavailable (a source tarball or
    ``git archive`` export), so this file cannot become a collection error for
    the whole suite.
    """
    try:
        out = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "ls-files", *patterns],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        pytest.skip(
            "git unavailable; cannot enumerate tracked files",
            allow_module_level=True,
        )
    return [_REPO_ROOT / line for line in out.stdout.split("\n") if line.strip()]


def _strip_comment(line: str) -> str:
    """Drop a trailing ``#`` comment that is not inside quotes.

    Without this, ``-Wait -PassThru`` appearing only in an explanatory comment
    would satisfy the shape checks while the real command lacked them.
    """
    in_single = in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def shell_exposed_variables(line: str) -> list[str]:
    """What bash would expand or execute before the child process sees ``line``.

    Models the subset of bash that can silently rewrite a documented command:
    ``$VAR`` / ``${VAR}``, the special parameters (``$?`` ``$$`` ``$#`` …),
    ``$(…)`` and backtick command substitution — each neutralised inside
    **single** quotes, live inside double quotes or unquoted. Backslash escapes
    are honoured outside single quotes. An unterminated quote is reported, since
    bash rejects such a line outright.

    Not a complete shell parser, and the docstring says so deliberately: an
    earlier version claimed to "apply bash's quoting rules" while implementing a
    ``$NAME`` scanner, which invited trust it had not earned.
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


def _files_with_runnable_invocations() -> dict[str, list[str]]:
    """Map of file → the lines in it that invoke the exe."""
    found: dict[str, list[str]] = {}
    for path in _tracked("*.md", "*.yml", "*.yaml"):
        name = path.relative_to(_REPO_ROOT).as_posix()
        if name in _PROSE_ALLOWLIST or name == _RELEASE_WORKFLOW:
            continue
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if is_runnable_invocation(line)
        ]
        if lines:
            found[name] = lines
    return found


def _selftest_lines() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _tracked("*.md", "*.yml", "*.yaml"):
        name = path.relative_to(_REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        found.extend((name, line.strip()) for line in _SELFTEST_LINE.findall(text))
    return found


_LINES = _selftest_lines()
_IDS = [f"{name}#{index}" for index, (name, _) in enumerate(_LINES)]


def test_only_sanctioned_homes_carry_the_command() -> None:
    """Rule 1. Everything else cites ``ogp-change-control`` §2.8 by name."""
    found = _files_with_runnable_invocations()
    strays = {
        name: lines for name, lines in found.items() if name not in SANCTIONED_HOMES
    }
    detail = "; ".join(
        f"{name} -> {lines[0].strip()[:70]}" for name, lines in sorted(strays.items())
    )
    assert not strays, (
        "these files carry a runnable frozen-exe invocation instead of citing "
        "`ogp-change-control` §2.8 — a second copy of a gate list is how a gate "
        f"goes missing: {detail}"
    )


def test_every_sanctioned_home_still_carries_it() -> None:
    """The other direction: a home that quietly loses the gate is the original
    failure mode (#291 hid for six releases behind a weaker check)."""
    missing = sorted(SANCTIONED_HOMES - set(_files_with_runnable_invocations()))
    assert not missing, f"sanctioned homes with no exe invocation at all: {missing}"


def test_the_canonical_definition_prescribes_selftest() -> None:
    """§2.8 defines the command; it must define the *whole* gate, not half."""
    for name in (
        ".claude/skills/ogp-change-control/SKILL.md",
        ".agents/skills/ogp-change-control/SKILL.md",
    ):
        text = (_REPO_ROOT / name).read_text(encoding="utf-8")
        assert _SELFTEST_LINE.search(text), f"{name} does not prescribe --selftest"


def test_the_release_workflow_still_runs_selftest() -> None:
    """The one place the gate actually executes, checked on its own terms.

    ``shell: pwsh`` means bash never touches it, so the quoting rules do not
    apply — but the shape does: without ``-Wait -PassThru`` and an exit-code
    comparison, CI would green-light a frozen build whose subsystems are dead,
    which is precisely #291.
    """
    text = (_REPO_ROOT / _RELEASE_WORKFLOW).read_text(encoding="utf-8")
    # Scoped to the COMMAND line, not the file: the explanatory comment block
    # above the step already contains every token, so a whole-file check passed
    # with the argument deleted from the real command.
    command = next(
        (ln for ln in text.splitlines() if "Start-Process" in ln and "#" not in ln),
        "",
    )
    assert command, "release.yml no longer starts the frozen exe at all"
    for required in ("--selftest", "-Wait", "-PassThru"):
        assert required in command, (
            f"release.yml's selftest command is missing {required!r}: {command.strip()}"
        )
    assert re.search(r"\$p\s*=\s*Start-Process", command), (
        "release.yml must ASSIGN the process object, or $p.ExitCode is null and "
        "the check passes whatever the selftest found"
    )
    assert "$p.ExitCode" in text, "release.yml never inspects the exit code"


def test_discovery_is_not_vacuous() -> None:
    """Guard the guard: a changed marker would make the rules pass over nothing."""
    assert _LINES, "no --selftest invocations discovered at all"
    assert set(_files_with_runnable_invocations()) == SANCTIONED_HOMES


@pytest.mark.parametrize("doc,line", _LINES, ids=_IDS)
def test_selftest_survives_the_shell(doc: str, line: str) -> None:
    """Rule 2a. No ``$``/backtick construct may be eaten or run by bash first."""
    exposed = shell_exposed_variables(line)
    assert not exposed, (
        f"{doc}: bash would expand or execute {exposed} before PowerShell sees "
        "the command — the outer string must be SINGLE-quoted, with the inner "
        f"PowerShell arguments double-quoted. Line: {line}"
    )


@pytest.mark.parametrize("doc,line", _LINES, ids=_IDS)
def test_selftest_actually_reports_the_childs_exit_code(doc: str, line: str) -> None:
    """Rule 2b. The shape must make the gate *capable of failing*.

    Requires the literal ``$p = Start-Process`` — not merely the presence of the
    words. Dropping the assignment while keeping ``exit $p.ExitCode`` satisfies
    every substring check and makes the gate exit 0 whatever the child returned;
    that bypass was demonstrated against real PowerShell (child exits 3, gate
    exits 0). Trailing ``#`` comments are stripped first, so an explanatory
    comment cannot supply a token the command itself lacks.
    """
    command = _strip_comment(line)
    assert re.search(r"\$p\s*=\s*Start-Process", command), (
        f"{doc}: the command must ASSIGN the process object (`$p = Start-Process "
        "…`). Without the assignment `$p.ExitCode` is null, `exit` yields 0, and "
        f"the gate passes whatever the selftest found. Line: {line}"
    )
    for required in ("--selftest", "-Wait", "-PassThru", "exit $p.ExitCode"):
        assert required in command, f"{doc}: gate command is missing {required!r}"
    assert _EXE in command, doc


class TestTheGuardItself:
    """Teeth, pinned against the defects that shipped or bypassed earlier versions."""

    def test_rejects_the_defect_that_shipped(self) -> None:
        shipped = (
            'powershell -Command "$p = Start-Process '
            "'dist/OpenGardenPlanner/OpenGardenPlanner.exe' -ArgumentList "
            "'--selftest' -Wait -PassThru; exit $p.ExitCode\""
        )
        assert shell_exposed_variables(shipped) == ["$p", "$p"]

    def test_rejects_the_dollar_question_bypass(self) -> None:
        bypass = (
            "powershell -Command \"Start-Process 'x' -Wait -PassThru; "
            'if ($?) { exit 0 } else { exit 1 }"'
        )
        assert "$?" in shell_exposed_variables(bypass)

    def test_rejects_the_unassigned_process_bypass(self) -> None:
        """Shell-clean, every keyword present — and always exits 0."""
        bypass = (
            "powershell -Command 'Start-Process "
            '"dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList '
            "\"--selftest\" -Wait -PassThru; exit $p.ExitCode'"
        )
        assert shell_exposed_variables(bypass) == []
        assert not re.search(r"\$p\s*=\s*Start-Process", _strip_comment(bypass))

    def test_rejects_tokens_that_live_only_in_a_comment(self) -> None:
        commented = (
            "powershell -Command '$p = Start-Process \"x\"; exit $p.ExitCode'"
            "   # -Wait -PassThru"
        )
        assert "-Wait" not in _strip_comment(commented)

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
            '"dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList '
            "\"--selftest\" -Wait -PassThru; exit $p.ExitCode'"
        )
        assert shell_exposed_variables(corrected) == []
        assert re.search(r"\$p\s*=\s*Start-Process", corrected)

    def test_quoting_model_matches_bash(self) -> None:
        assert shell_exposed_variables("echo $HOME") == ["$HOME"]
        assert shell_exposed_variables("echo '$HOME'") == []
        assert shell_exposed_variables('echo "$HOME"') == ["$HOME"]
        assert shell_exposed_variables('echo "\\$HOME"') == []
        assert shell_exposed_variables("echo '\"$HOME\"'") == []
        assert shell_exposed_variables('echo "\'$HOME\'"') == ["$HOME"]
        assert shell_exposed_variables("echo ${HOME}") == ["${HOME}"]
        assert shell_exposed_variables('echo "$$"') == ["$$"]
        assert shell_exposed_variables('echo "${?}"') == ["${?}"]

    def test_comment_stripper_respects_quotes(self) -> None:
        assert _strip_comment("cmd 'a # b' # real") == "cmd 'a # b' "
        assert _strip_comment('cmd "a # b"') == 'cmd "a # b"'
