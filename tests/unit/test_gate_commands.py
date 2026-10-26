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
which exits 0 whatever the child returned. Round 8 added three walkable
spellings of the discovery predicate — a quoted path at line start
(``"dist/…exe" --selftest``), ``powershell.exe``, and a prose word in a
trailing comment (``# the gate exists``) — plus the launcher-variant seam in
the shape checks. Each is now a teeth case.

Static by design: it does not run the gates (that needs a built exe and minutes
of wall clock). Issue #336 proposes a citation resolver for the skill library;
that checks references *resolve*, this checks commands *run*.
"""

from __future__ import annotations

import re
import shlex
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

#: The same gate on pull requests (L1.2 review, P1-4): it builds the bundle with
#: the release recipe and runs the 8-second smoke and ``--selftest`` BEFORE a
#: merge. Like the release workflow it is a place where the gate EXECUTES, in
#: shells it declares itself — so it is checked on its own terms too, and is
#: not a "copy of the command literal" in the sense of Rule 1.
_FROZEN_SELFTEST_WORKFLOW = ".github/workflows/frozen-selftest.yml"

#: Every workflow that runs the frozen-exe gate. Adding a name here is a decision
#: to exempt a file from Rule 1 — it must then pass
#: ``test_a_gate_workflow_runs_selftest_in_the_one_shape``.
_GATE_WORKFLOWS = (_RELEASE_WORKFLOW, _FROZEN_SELFTEST_WORKFLOW)

_EXE = "OpenGardenPlanner.exe"

#: The historical ADR spike record: a plain exe invocation with the --spike-3d
#: flag and no launcher. The exemption is anchored to that shape, not to the
#: substring (the unanchored skip the commit security scan flagged): a gate
#: copy that hides the flag in a trailing comment still carries its launcher
#: verb and is still caught. A whole-file exception would be worse — a future
#: ADR pasting the gate literal would go unseen (round 11).
_SPIKE_RECORD_FLAG = "--spike-3d"


def _is_spike_record(line: str) -> bool:
    """Whether ``line`` is the ADR-038 spike record, not a gate copy.

    The record invokes the exe directly with the full flag trio:
    ``dist/…exe --spike-3d --spike-screenshot … --spike-autoclose 6``. The
    comment is stripped first, so a flag in a trailing comment cannot exempt
    a real command (round 13). The trio AND the ellipsis marker anchor the
    exemption to the record itself: a real command never carries an ellipsis,
    so a gate copy that happens to append the trio is still a command
    (round 14). Delete this exemption when the spike record is retired from
    the ADR.
    """
    stripped = _strip_comment(line)
    return (
        _SPIKE_RECORD_FLAG in stripped
        and "--spike-screenshot" in stripped
        and "--spike-autoclose" in stripped
        and "…" in stripped
        and _EXE in stripped
        and not _SHELL_VERB.search(stripped.lower())
    )

#: Lines that name the exe and a ``--selftest`` flag behind a launcher verb.
#: The verb requirement keeps historical examples out of the shape checks
#: (``"`& \"…\\OpenGardenPlanner.exe\" --selftest` returns in ~6 ms"`` in
#: ogp-build-and-run describes the old defect, it does not prescribe the gate)
#: while still covering launcher variants like ``pwsh -Command`` and
#: ``powershell -c``. Round 8 showed the old key (``powershell -Command``) let
#: the shape checks go quiet for such variants while the discovery check
#: stayed green.
_SELFTEST_LINE = re.compile(
    rf"^.*(?:timeout|powershell|pwsh|start-process).*{re.escape(_EXE)}.*--selftest.*$",
    re.MULTILINE | re.IGNORECASE,
)


#: Shell verbs that make a line a command. Word-boundary matched, so the
#: ``powershell.exe`` and ``pwsh -c`` spellings count too. Round 8 used
#: ``powershell.exe`` to walk past the old ``"powershell "`` substring token.
_SHELL_VERB = re.compile(r"\b(?:timeout|powershell|pwsh|start-process)\b")

#: A gate flag makes a line a command even when no launcher is present.
_FLAG = re.compile(r"--selftest|--spike")

#: Prose words. They exempt a bare-path sentence, but never a real command.
_PROSE_WORDS = re.compile(r"\b(dies|lives|found|produced|appears|exists)\b")


def is_runnable_invocation(line: str) -> bool:
    """Return True when ``line`` runs the exe, not merely names it.

    This predicate is deliberately broad. Every earlier version listed launcher
    spellings: ``^timeout \\d+ …`` and ``^powershell -Command …``. A reviewer
    then walked past it with four other spellings: ``pwsh -Command``,
    ``powershell -c``, a bare ``…exe --selftest``, and a bullet-prefixed
    ``- timeout 8 …``. Three real violations already in the tree stayed
    invisible. Reality has more spellings than a regex, so this predicate finds
    the exe path in a command position and exempts only clear prose.

    A line is a command when it carries a shell verb, or a gate flag, or starts
    with the exe path, quoted or not. Round 8 used ``"dist/…exe" --selftest``
    to walk past the old ``startswith`` check, which saw the quote, not the
    path. The prose-word exemption applies only to the bare-path start. A
    sentence like "a 3D engine that … dies in `dist/…exe`" has no verb and no
    flag, so it is prose. A command whose trailing comment holds one of those
    words is still a command: ``timeout 8 …exe # the gate exists``.
    """
    if _EXE not in line:
        return False
    if re.search(rf"…[\\/]?{re.escape(_EXE)}", line):
        return False  # an ellipsized path is an example, not a runnable command
    stripped = line.strip().lstrip("-*>| `").strip()
    for quote in ("'", '"'):
        # Iterate, not once: the bash-safe nested spelling
        # ('"dist/…exe"') walked past a single strip (round 11). Each pass
        # removes a leading quote and, when the matching closing quote wraps
        # the path alone, that closing quote too — so the comment stripper
        # below sees balanced quotes (round 10).
        while stripped.startswith(quote):
            body = stripped[1:].lstrip()
            close = body.find(quote)
            if close != -1 and " " not in body[:close]:
                body = body[:close] + body[close + 1 :]
            stripped = body.strip()
    lowered = stripped.lower()
    if _SHELL_VERB.search(lowered) or _FLAG.search(lowered):
        return True
    if lowered.startswith(("dist/", "dist\\", "./dist/", "$exe", "&", ".\\", "..\\")):
        # Strip comments first: a trailing ``# the gate exists`` must not
        # exempt a bare-path command (round 9 walked past this with exactly
        # that spelling).
        return not _PROSE_WORDS.search(_strip_comment(lowered))
    return False

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
        out = subprocess.run(
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
        if name in _GATE_WORKFLOWS:
            continue
        lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if is_runnable_invocation(line)
            and not _is_spike_record(line)  # ADR-038's historical record
        ]
        if lines:
            found[name] = lines
    return found


def _selftest_lines() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _tracked("*.md", "*.yml", "*.yaml"):
        name = path.relative_to(_REPO_ROOT).as_posix()
        if name in _GATE_WORKFLOWS:
            continue  # checked by their own test, on pwsh terms (no bash involved)
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


def _workflow_code(name: str) -> list[str]:
    """A workflow's lines without its YAML comment lines: a token that appears only
    in an explanatory comment must not satisfy a shape check."""
    text = (_REPO_ROOT / name).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if not line.lstrip().startswith("#")]


@pytest.mark.parametrize("workflow", _GATE_WORKFLOWS)
def test_a_gate_workflow_runs_selftest_in_the_one_shape(workflow: str) -> None:
    """The places the gate actually executes, checked on their own terms.

    ``shell: pwsh`` means bash never touches the command, so the quoting rules do
    not apply — but the shape does: without ``-Wait -PassThru`` and an exit-code
    comparison, CI would green-light a frozen build whose subsystems are dead,
    which is precisely #291.
    """
    lines = _workflow_code(workflow)
    # Scoped to the COMMAND line, not the file: the explanatory comment block
    # above the step already contains every token, so a whole-file check passed
    # with the argument deleted from the real command.
    commands = [ln for ln in lines if "Start-Process" in ln]
    assert len(commands) == 1, f"{workflow} must start the frozen exe exactly once: {commands}"
    command = commands[0]
    for required in ("--selftest", "-Wait", "-PassThru"):
        assert required in command, (
            f"{workflow}'s selftest command is missing {required!r}: {command.strip()}"
        )
    assert re.search(r"\$p\s*=\s*Start-Process", command), (
        f"{workflow} must ASSIGN the process object, or $p.ExitCode is null and "
        "the check passes whatever the selftest found"
    )
    # … and the exit code must be able to FAIL the step: compared, and acted on — as
    # the very next thing, with nothing in between that could end the step first.
    after = [ln.strip() for ln in lines[lines.index(command) + 1:]]
    assert after[0] == "if ($p.ExitCode -ne 0) {", f"{workflow} never inspects the exit code"
    failed_branch = after[1:after.index("}")]
    assert failed_branch[-1] == "exit 1", f"{workflow} does not fail on a failed self-test"
    assert all(ln.startswith("Write-Host ") for ln in failed_branch[:-1]), failed_branch


def _steps(workflow: str) -> list[list[str]]:
    """The workflow's steps, each as its stripped lines (comment lines dropped)."""
    steps: list[list[str]] = []
    for line in _workflow_code(workflow):
        if line.startswith("      - "):
            steps.append([])
        if steps and line.startswith("      "):
            steps[-1].append(line.strip())
    return steps


@pytest.mark.parametrize("workflow", _GATE_WORKFLOWS)
def test_a_gate_workflow_cannot_hang_and_never_loses_its_log(workflow: str) -> None:
    """L1.2 review, P1-4 and round 2 P2-6. The ways the step used to be able to go wrong:

    * no limit — a self-test that hung held the job for GitHub's six hours;
    * the log was printed BEFORE the verdict by a bare ``Get-Content``: under
      GitHub's pwsh (``$ErrorActionPreference = 'stop'``) a log that cannot be read
      ends the step there — a passing build goes red, a failing one fails with the
      wrong error;
    * ``Write-Error`` for the verdict: it ends the step at once;
    * the log was printed by the SAME step, after the verdict: a step that is cut
      off by its time limit prints nothing after the cut — and that is exactly the
      run whose log is needed.

    So: the self-test step only decides; the step right after it prints the log, runs
    ``always()``, reads inside try/catch and cannot fail.
    """
    lines = _workflow_code(workflow)
    job_limits = [ln for ln in lines if re.fullmatch(r"    timeout-minutes: \d+", ln)]
    assert len(job_limits) == 1, f"{workflow}: the job has no time limit"
    steps = _steps(workflow)
    index = next(i for i, step in enumerate(steps)
                 if step[0].startswith("- name: Verify frozen subsystems"))
    verify, log = steps[index], steps[index + 1]

    assert "timeout-minutes: 10" in verify, f"{workflow}: the self-test step has no time limit"
    assert not [ln for ln in verify + log if "Write-Error" in ln], (
        f"{workflow}: Write-Error ends a step at once")
    assert not [ln for ln in verify if "Get-Content" in ln], (
        f"{workflow}: the self-test step does not read the log — the next step does")
    # the only ways out of the self-test step: the missing exe, and the verdict
    assert [ln for ln in verify if "exit " in ln and not ln.startswith("Write-Host")] == [
        'if (-not (Test-Path $exe)) { Write-Host "::error::Frozen exe not found: $exe"; exit 1 }',
        "exit 1",
    ]

    assert log[0] == "- name: Print the self-test log", f"{workflow}: {log[0]}"
    condition = next(ln for ln in log if ln.startswith("if: "))
    assert condition.startswith("if: always()"), f"{workflow}: the log step must always run"
    reading = next(i for i, ln in enumerate(log) if "Get-Content" in ln)
    assert log.index("try {") < reading < log.index("} catch {"), (
        f"{workflow}: the log must be read inside try/catch")
    assert log[-1] == "exit 0" and not [ln for ln in log if "exit 1" in ln], (
        f"{workflow}: the log step can fail nothing")
    # both steps mean the same file: the exe writes where the next step reads
    path = "OGP_SELFTEST_LOG: ${{ runner.temp }}/ogp-selftest-3d.log"
    assert path in verify and path in log, f"{workflow}: the two steps disagree about the log"


def test_the_pull_request_gate_also_runs_the_smoke_test() -> None:
    """Check 1 of ``ogp-change-control`` §2.8 in the pull-request workflow: the process
    is still up after 8 seconds — exit code 124, and ONLY 124, is the pass."""
    lines = [ln.strip() for ln in _workflow_code(_FROZEN_SELFTEST_WORKFLOW)]
    smoke = lines.index("timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe")
    assert lines[smoke - 1] == "set +e", "GitHub's bash is -e: the 124 would end the step"
    assert lines[smoke + 1] == "code=$?"
    assert 'if [ "$code" -ne 124 ]; then' in lines[smoke:smoke + 5]
    assert "exit 1" in lines[smoke:smoke + 8]
    assert smoke < next(i for i, ln in enumerate(lines) if "Start-Process" in ln)


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

    def test_rejects_the_quoted_path_bypasses(self) -> None:
        """Round 8: the old ``startswith`` check saw the quote, not the path."""
        assert is_runnable_invocation(
            '"dist/OpenGardenPlanner/OpenGardenPlanner.exe" --selftest'
        ), "a double-quoted path at line start must be a command"
        assert is_runnable_invocation(
            "'dist/OpenGardenPlanner/OpenGardenPlanner.exe' --selftest"
        ), "a single-quoted path at line start must be a command"

    def test_rejects_the_powershell_exe_bypass(self) -> None:
        """Round 8: ``powershell.exe`` did not contain the ``"powershell "`` token."""
        assert is_runnable_invocation(
            'powershell.exe -Command "dist/OpenGardenPlanner/OpenGardenPlanner.exe --selftest"'
        ), "the .exe spelling of powershell must be a command"

    def test_prose_words_do_not_exempt_a_real_command(self) -> None:
        """Round 8: ``# the gate exists`` exempted a genuine command."""
        assert is_runnable_invocation(
            "timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe # the gate exists"
        ), "a prose word in a trailing comment must not exempt a command"

    def test_still_exempts_clear_prose(self) -> None:
        assert not is_runnable_invocation(
            "a 3D engine that … dies in `dist/OpenGardenPlanner/OpenGardenPlanner.exe`"
        ), "a sentence that merely names the path must stay exempt"

    def test_an_ellipsized_path_is_not_runnable(self) -> None:
        assert not is_runnable_invocation(
            "`& \"…\\OpenGardenPlanner.exe\" --selftest` returns in ~6 ms"
        ), "an ellipsized path describes a defect, it does not prescribe a gate"

    def test_prose_word_in_comment_does_not_exempt_a_bare_path(self) -> None:
        """Round 9: the prose exemption fired on a trailing comment."""
        assert is_runnable_invocation(
            "dist/OpenGardenPlanner/OpenGardenPlanner.exe # the gate exists"
        ), "a trailing comment must not exempt a bare-path command"

    def test_a_backslash_path_is_runnable(self) -> None:
        """Round 9: a PowerShell-style backslash path walked past the path check."""
        assert is_runnable_invocation(
            r".\dist\OpenGardenPlanner\OpenGardenPlanner.exe"
        ), "a backslash path must be a command"

    def test_the_shape_checks_cover_a_pwsh_rewrite(self) -> None:
        """Round 9: the launcher-variant seam was claimed as a teeth case but no
        tooth pinned it. This one does."""
        variant = (
            "pwsh -Command '$p = Start-Process "
            '"dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList '
            '"--selftest" -Wait -PassThru; exit $p.ExitCode\''
        )
        assert _SELFTEST_LINE.search(variant), (
            "a pwsh -Command rewrite of the sanctioned literal must still be "
            "discovered for shape checking"
        )
        assert shell_exposed_variables(variant) == []
        assert re.search(r"\$p\s*=\s*Start-Process", _strip_comment(variant))
        for required in ("--selftest", "-Wait", "-PassThru", "exit $p.ExitCode"):
            assert required in variant

    def test_a_quoted_path_with_trailing_comment_is_a_command(self) -> None:
        """Round 10: the opening-quote strip unbalanced _strip_comment, so the
        prose word in a trailing comment exempted a quoted-path command."""
        assert is_runnable_invocation(
            '"dist/OpenGardenPlanner/OpenGardenPlanner.exe" # the gate exists'
        ), "a quoted path with a trailing comment must be a command"
        assert is_runnable_invocation(
            "'dist/OpenGardenPlanner/OpenGardenPlanner.exe' # the gate exists"
        ), "the single-quoted twin must be a command too"

    def test_a_bare_backslash_path_is_runnable(self) -> None:
        """Round 10: the direct sibling of the .\\ tooth — no leading dot."""
        assert is_runnable_invocation(
            r"dist\OpenGardenPlanner\OpenGardenPlanner.exe"
        ), "a bare backslash path must be a command"

    def test_a_forward_slash_ellipsized_path_is_not_runnable(self) -> None:
        """Round 10: the ellipsis regex only exempted the backslash form."""
        assert not is_runnable_invocation(
            "…/OpenGardenPlanner.exe --selftest"
        ), "a forward-slash ellipsis describes a defect, it does not prescribe a gate"

    def test_a_nested_quoted_path_is_a_command(self) -> None:
        """Round 11: the quote strip handled one nesting level. The docstring
        promises "quoted or not"; this pins the bash-safe nested spelling."""
        assert is_runnable_invocation(
            '\'"dist/OpenGardenPlanner/OpenGardenPlanner.exe"\''
        ), "a nested-quoted path must be a command"

    def test_the_spike_record_skip_is_anchored_to_the_record_shape(self) -> None:
        """A gate copy must not hide behind the --spike-3d flag in a comment."""
        assert _is_spike_record(
            "`dist/OpenGardenPlanner/OpenGardenPlanner.exe --spike-3d "
            "--spike-screenshot … --spike-autoclose 6`"
        ), "the historical record shape must stay exempt"
        assert not _is_spike_record(
            "timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe "
            "# --spike-3d"
        ), "a launcher plus a flag in a comment must NOT be exempt"
        assert not _is_spike_record(
            "powershell -Command '$p = Start-Process "
            '"dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList '
            '"--selftest" -Wait -PassThru; exit $p.ExitCode\' # --spike-3d'
        ), "the real gate command plus a flag in a comment must NOT be exempt"
        assert not _is_spike_record(
            "dist/OpenGardenPlanner/OpenGardenPlanner.exe --selftest "
            "# --spike-3d"
        ), "a bare selftest copy must NOT hide behind the spike flag in a comment"
        assert not _is_spike_record(
            "dist/OpenGardenPlanner/OpenGardenPlanner.exe --selftest "
            "--spike-3d --spike-screenshot --spike-autoclose"
        ), "a gate copy that appends the trio must NOT be exempt"


#: `actions/attest-build-provenance` v1 and v2 both pin a node20 `actions/attest`;
#: GitHub is removing the node20 runtime from Actions runners (2026), at which
#: point either hard-fails and, being wired ahead of release creation
#: originally, would have taken every future release with it (senior review,
#: issue #356). node24 arrived in v3.0.0 (upstream release notes: "Bump to
#: node24 runtime"), not v4 — a v2 pin looks close enough to "not v1" to read
#: as safe and is exactly as broken. Anything below v3 is the stale shape this
#: guards against; the bar is "not node20", not "must equal today's latest".
_MIN_ATTEST_ACTION_MAJOR = 3

#: Matches either a tag pin (``@v4``) or a hardened SHA pin with the major
#: recorded in a trailing comment (``@abc123...  # v4.2.2``) — the standard
#: supply-chain-hardening spelling for an action whose entire purpose is
#: supply-chain trust. A bare SHA pin with no version comment is rejected:
#: the guard needs a major to check, not just "some commit or other".
_ATTEST_USES_LINE = re.compile(
    r"uses:\s*actions/attest-build-provenance@"
    r"(?:v(?P<tag_major>\d+)|[0-9a-f]{40}\s*#\s*v(?P<sha_major>\d+))"
)


def test_the_release_workflow_still_attests_build_provenance() -> None:
    """Issue #356: prove releases are built by public CI from public source.

    Pins the six things review rounds actually caught regressing
    (hand-verified against the fixes, not hypothetical — see ADR-044
    "Rejected placement"): the step existing at all; pinned to an action
    major new enough to survive the node20 runtime removal; running *after*
    release creation, not before (a never-yet-exercised step ahead of
    release creation can take every future release down with it); the job
    actually granting the OIDC permissions the step needs; covering the
    exact file Defender quarantined in #356 (the raw app exe) and
    `SHA256SUMS.txt`, not just the NSIS installer that wraps it; and the
    release-notes preamble actually being wired into the release (a deleted
    `--notes-file` flag would silently drop the trust signal from every
    future release page with every other assertion here still green).
    """
    text = (_REPO_ROOT / _RELEASE_WORKFLOW).read_text(encoding="utf-8")

    uses_match = _ATTEST_USES_LINE.search(text)
    assert uses_match, "release.yml no longer attests build provenance at all"
    major = int(uses_match.group("tag_major") or uses_match.group("sha_major"))
    assert major >= _MIN_ATTEST_ACTION_MAJOR, (
        f"actions/attest-build-provenance@v{major} predates the node20 "
        f"runtime removal fix — bump to v{_MIN_ATTEST_ACTION_MAJOR}+"
    )

    create_release_pos = text.index("- name: Create GitHub Release")
    attest_pos = text.index("- name: Attest build provenance")
    assert attest_pos > create_release_pos, (
        "'Attest build provenance' must run AFTER 'Create GitHub Release' — "
        "attestation is keyed to the artifact digest, not the release, so "
        "nothing requires it to run first, and a never-yet-exercised step "
        "ahead of release creation can take every future release down with "
        "it if Sigstore/the attestations API hiccups (ADR-044 'Rejected "
        "placement')"
    )

    job_block = text[text.index("jobs:") : create_release_pos]
    assert "id-token: write" in job_block and "attestations: write" in job_block, (
        "the release job no longer grants id-token/attestations permissions "
        "— actions/attest-build-provenance requires both to mint a Sigstore "
        "attestation; without them the step fails every run"
    )

    assert "--notes-file" in text, (
        "release.yml no longer wires the verification preamble into "
        "`gh release create` — a deleted --notes-file flag would silently "
        "drop the trust signal from every future release page while every "
        "other assertion in this test stays green"
    )

    # Bounded to the attest step's own block (up to the next top-level step
    # or end of file), not an arbitrary character window — a step appended
    # after it that happens to mention the exe path must not make this pass
    # vacuously. A step can start with either `- name:` or `- uses:` (this
    # workflow's own first step is `- uses: actions/checkout@v4`), so both
    # spellings bound the window.
    subject_path_start = text.index("subject-path:", attest_pos)
    next_step_match = re.search(r"\n {6}- (?:name|uses):", text[subject_path_start:])
    subject_path_end = (
        subject_path_start + next_step_match.start()
        if next_step_match
        else len(text)
    )
    subject_path_block = text[subject_path_start:subject_path_end]
    assert "OpenGardenPlanner-v" in subject_path_block and "Setup.exe" in subject_path_block, (
        "the attest step no longer covers the installer"
    )
    assert "SHA256SUMS.txt" in subject_path_block, (
        "the attest step no longer covers SHA256SUMS.txt"
    )
    assert "OpenGardenPlanner/OpenGardenPlanner.exe" in subject_path_block, (
        "the attest step no longer covers the raw app exe — this is the "
        "exact file Defender quarantined in issue #356, attesting only the "
        "installer does not let a user verify it"
    )


def test_ci_still_scans_for_committed_secrets() -> None:
    """A live Agent API write token was committed and pushed (PR #369, 2026-09-29).

    The token had to be rotated by hand, because Bandit runs as `-r src/` (the
    file was at the repo root) and has no rule for a credential in a URL query
    string — which is exactly how OGP's token travels.

    Pins the three things that make the gate load-bearing, each of which a
    plausible edit could silently drop while every other assertion here stays
    green:

    * the step existing at all, and running in the SECURITY job rather than
      being tucked somewhere that is allowed to fail;
    * the checker itself still existing as a script CI invokes — a deleted
      script with a passing `if [ -f ]` guard is a gate that is simply gone;
    * Bandit still running alongside it, since a credential scan and SAST are
      complementary, not substitutes.
    """
    text = (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "check_no_secrets.py" in text, (
        "ci.yml no longer runs the committed-secret scan — the repo has no "
        "other check that would notice a credential, and a committed write "
        "token is exactly the failure no other gate covers"
    )

    script = _REPO_ROOT / "scripts" / "check_no_secrets.py"
    assert script.is_file(), (
        "ci.yml invokes scripts/check_no_secrets.py but the script is gone — "
        "the step will fail on every run until it is restored"
    )

    assert "bandit" in text, (
        "ci.yml no longer runs Bandit — the secret scan is a credential check, "
        "not a replacement for SAST"
    )


#: Shell control operators that separate one command from the next. `shlex.split` yields
#: these as standalone tokens whenever the source has whitespace around them, which every
#: documented shape does. `2>&1` is deliberately NOT one: it is a redirection with no
#: surrounding whitespace, so it survives as a single token and the line stays whole.
_COMMAND_OPERATORS = frozenset({";", "&&", "||", "|", "&"})

#: Operators that also split when they LEAD a token (`… -n 0 ||true`, `… |tee out`). Bare
#: `&` is excluded: it leads bash's `&>file` redirection, where splitting would be wrong.
_LEADING_OPERATORS = ("||", "&&", "|", ";")


def _leading_operator(token: str) -> str | None:
    """The control operator `token` starts with, if any, else None."""
    for operator in _LEADING_OPERATORS:
        if token.startswith(operator):
            return operator
    return None


def _commands_of(run: object) -> list[list[str]]:
    """A step's `run` as a list of commands, each an argv.

    Issue #513. The old helper tokenised every line and CONCATENATED the tokens, so a
    script whose earlier line merely *named* the perf command (`echo pytest tests/ -m perf
    -n 0`) satisfied all three substring assertions while the step ran nothing. A step's
    `run` is a SCRIPT, not one command: the pin has to evaluate the command whose exit
    status is the step's, which is the last one.

    Newlines and the control operators `;`, `&&`, `||`, `|` and `&` end a command, whether
    they stand alone (`… || true`) or lead the next token (`… ||true`). A `run: >` folded
    scalar is one logical line after YAML folding, so it stays one command; a `run: |`
    literal block keeps its newlines and becomes one command per line. Quotes are honoured
    by `shlex`, so `echo "a;b"` is one token and does not split.

    A `#` comment is stripped the way a shell strips it (`comments=True`), so a comment
    naming the perf command never reaches `_marker_arg`. A `run:` expressed as a YAML list
    returns `[]`, which surfaces as `found == 0` below rather than as a TypeError.
    Unbalanced quotes also return `[]` — loud, if unhelpful.
    """
    if isinstance(run, list):
        return []
    commands: list[list[str]] = []
    current: list[str] = []
    for line in str(run).splitlines():
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            return []
        for token in tokens:
            operator = token if token in _COMMAND_OPERATORS else _leading_operator(token)
            if operator is not None:
                if current:
                    commands.append(current)
                    current = []
                rest = token[len(operator) :]
                if rest:
                    current.append(rest)
                continue
            current.append(token)
        if current:
            commands.append(current)
            current = []
    return commands


def _is_pytest_run(argv: list[str]) -> bool:
    """Whether `argv` actually invokes pytest, rather than naming it in its arguments.

    Closes the delegating-script shape (`bash scripts/ci_perf.sh tests/ -m perf -n 0`,
    which `_marker_arg` reads as a selection) and the bare-`echo` shape (`echo pytest
    tests/ -m perf -n 0`), where the marker is real but no test would run. Only a `pytest`
    head, or a python interpreter invoking it with `-m pytest`, is a runner.
    """
    if not argv:
        return False
    head = argv[0].replace("\\", "/")
    if head == "pytest" or head.endswith("/pytest") or head.endswith("/pytest.exe"):
        return True

    head_base = head.rsplit("/", 1)[-1]
    is_python = (
        head_base in ("python", "python3", "python.exe", "python3.exe")
        or head_base.startswith("python3.")
    )
    if is_python:
        for i in range(1, len(argv) - 1):
            if argv[i] == "-m":
                target = argv[i + 1].replace("\\", "/")
                if target == "pytest" or target.endswith("/pytest") or target.endswith("/pytest.exe"):
                    return True
    return False


def _collect_only_requested(argv: list[str]) -> str | None:
    """A collect-only flag the command carries, whether spelled directly or inside `-o`.

    Closes the `-o addopts="--co"` injection: the step would succeed having run no test.
    The override value is split like the argv, so an exact `--co`/`--collect-only` word is
    required and `--cov`, `--cov-branch` and friends are not mistaken for it.
    """
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in ("--co", "--collect-only"):
            return token
        if token in ("-o", "--override-ini") and index + 1 < len(argv):
            value = argv[index + 1]
            if value.startswith("addopts="):
                value = value.split("=", 1)[1]
            value = value.strip().strip('"').strip("'")
            match = re.search(r"(?:^|\s)(--co|--collect-only)(?=\s|$)", value)
            if match:
                return f"{match.group(1)} inside an addopts override"
            index += 2
            continue
        index += 1
    return None


def _pytest_addopts_env(step: dict, *jobs: dict) -> bool:
    """Whether a step or any of its jobs sets `PYTEST_ADDOPTS`.

    Closes the `env: PYTEST_ADDOPTS: --co` shape, which is literal YAML text and therefore
    pinnable: the flag would reach every pytest invocation in the step without appearing in
    any `run:` line.
    """
    sources = [step, *jobs]
    for source in sources:
        mapping = source.get("env") if isinstance(source, dict) else None
        if isinstance(mapping, dict) and "PYTEST_ADDOPTS" in mapping:
            return True
    return False



def _marker_arg(argv: list[str]) -> str | None:
    """The value of pytest's `-m`, if the argv carries one.

    Not simply "the first `-m`": `python -m pytest ... -m 'not perf'` has two, and the
    first means "run module". Measured - taking the first made the coverage job's parallel
    step report its marker as `pytest` and drop out of the matched set. So the search starts
    at the `pytest` token, and falls back to the LAST `-m` when there is none, because a
    later flag is the one that overrides.
    """
    starts: list[int] = []
    for index, raw_token in enumerate(argv):
        token = raw_token.replace("\\", "/")
        if token == "pytest" or token.endswith("/pytest") or token.endswith("/pytest.exe"):
            starts.append(index + 1)
    candidates = range(starts[-1], len(argv)) if starts else range(len(argv))

    values: list[str] = []
    for index in candidates:
        if argv[index] == "-m" and index + 1 < len(argv):
            values.append(argv[index + 1])
    if values:
        return values[-1]

    # No `pytest` token: any `-m` will do, last one wins.
    for index in range(len(argv) - 1, -1, -1):
        if argv[index] == "-m" and index + 1 < len(argv):
            return argv[index + 1]
    return None


def _flag_value(argv: list[str], flag: str) -> str | None:
    """The value of a single-token flag such as `-n 0`, read AFTER the `pytest` token.

    Same reason as `_marker_arg`: `python -m pytest` uses `-m`, and a shell command may
    carry other single-letter flags before the test runner starts.
    """
    for index, raw_token in enumerate(argv):
        token = raw_token.replace("\\", "/")
        if token == "pytest" or token.endswith("/pytest") or token.endswith("/pytest.exe"):
            for pos in range(index + 1, len(argv) - 1):
                if argv[pos] == flag:
                    return argv[pos + 1]
            return None
    for pos in range(len(argv) - 1):
        if argv[pos] == flag:
            return argv[pos + 1]
    return None


def _targets_tests_dir(argv: list[str]) -> bool:
    """True when the argv names `tests/` and not a SUBDIRECTORY of it.

    `tests/perf` is a subdirectory, and it is the whole defect: it collects 7 of the 14 and
    passes. Comparing path tokens rather than searching the string is what makes `tests/perf`
    distinguishable from `tests/`.
    """
    for token in argv:
        if token.startswith("-"):
            continue
        normalised = token.replace("\\", "/").rstrip("/")
        if normalised == "tests":
            return True
    return False


def _covers_the_perf_marker(argv: list[str], want_marker: bool) -> bool:
    """Whether `-m` selects (`want_marker`) or deselects the `perf` marker."""
    value = _marker_arg(argv)
    if value is None:
        return False
    # Check if perf is referenced in the marker expression
    if not re.search(r"\bperf\b", value):
        return False
    # Check if perf is specifically negated: e.g. "not perf", "not (perf)", "not(perf)"
    negated = bool(re.search(r"\bnot\s*\(?\s*perf\b", value))
    return not negated if want_marker else negated


def _needs_of(job: dict) -> list[str]:
    """Normalise a job's `needs`, which YAML may give as a string or a list."""
    needs = job.get("needs")
    if needs is None:
        return []
    return [needs] if isinstance(needs, str) else list(needs)


class TestTheCommandSplit:
    """Teeth for the #513 per-command matcher, pinned against the shapes it must close."""

    def test_separators_end_a_command(self) -> None:
        assert _commands_of("a ; b && c || d | e") == [["a"], ["b"], ["c"], ["d"], ["e"]]

    def test_newlines_end_a_command(self) -> None:
        assert _commands_of("a\nb") == [["a"], ["b"]]

    def test_a_quoted_separator_does_not_split(self) -> None:
        # shlex honours the quotes, so `"a;b"` is one token and the command stays whole.
        assert _commands_of('echo "a;b" && pytest tests/') == [
            ["echo", "a;b"],
            ["pytest", "tests/"],
        ]

    def test_an_operator_leading_a_token_still_splits(self) -> None:
        assert _commands_of("pytest x -n 0 ||true") == [["pytest", "x", "-n", "0"], ["true"]]
        assert _commands_of("pytest x |tee out") == [["pytest", "x"], ["tee", "out"]]

    def test_a_redirection_survives_as_one_token(self) -> None:
        # `2>&1` has no surrounding whitespace, so it must not be treated as an operator.
        assert _commands_of("pytest x 2>&1 | tee out") == [["pytest", "x", "2>&1"], ["tee", "out"]]

    def test_a_comment_is_not_a_command(self) -> None:
        commands = _commands_of("# pytest tests/ -m perf -n 0\npytest tests/ -m 'not perf' -v")
        assert commands == [["pytest", "tests/", "-m", "not perf", "-v"]]
        assert _covers_the_perf_marker(commands[0], want_marker=False)

    def test_a_yaml_list_is_empty(self) -> None:
        assert _commands_of(["pytest", "tests/"]) == []

    def test_runner_identity_distinguishes_pytest_from_a_delegating_script(self) -> None:
        assert _is_pytest_run(["pytest", "tests/"])
        assert _is_pytest_run(["python", "-m", "pytest", "tests/"])
        assert _is_pytest_run(["python3", "-m", "pytest", "tests/"])
        assert _is_pytest_run(["python", "-u", "-m", "pytest", "tests/"])
        assert _is_pytest_run(["./venv/bin/pytest", "tests/"])
        assert not _is_pytest_run(["bash", "-m", "pytest", "tests/"])
        assert not _is_pytest_run(["bash", "scripts/ci_perf.sh", "tests/", "-m", "perf", "-n", "0"])
        assert not _is_pytest_run(["echo", "pytest", "tests/"])

    def test_covers_the_perf_marker_handles_compound_expressions(self) -> None:
        assert _covers_the_perf_marker(["pytest", "-m", "perf"], want_marker=True)
        assert not _covers_the_perf_marker(["pytest", "-m", "perf"], want_marker=False)
        assert _covers_the_perf_marker(["pytest", "-m", "not perf"], want_marker=False)
        assert not _covers_the_perf_marker(["pytest", "-m", "not perf"], want_marker=True)
        assert _covers_the_perf_marker(["pytest", "-m", "perf and not slow"], want_marker=True)
        assert not _covers_the_perf_marker(["pytest", "-m", "perf and not slow"], want_marker=False)
        assert _covers_the_perf_marker(["pytest", "-m", "not perf and not flaky"], want_marker=False)
        assert not _covers_the_perf_marker(["pytest", "-m", "not perf and not flaky"], want_marker=True)
        assert not _covers_the_perf_marker(["pytest", "-m", "slow"], want_marker=True)
        assert not _covers_the_perf_marker(["pytest", "-m", "slow"], want_marker=False)

    def test_flag_value_anchors_to_pytest(self) -> None:
        assert _flag_value(["./venv/bin/pytest", "tests/", "-n", "0"], "-n") == "0"
        assert _flag_value(["python", "-u", "-m", "pytest", "tests/", "-n", "0"], "-n") == "0"

    def test_collect_only_is_read_directly_and_inside_addopts(self) -> None:
        assert _collect_only_requested(["pytest", "tests/", "--co"]) == "--co"
        assert _collect_only_requested(["pytest", "tests/", "--collect-only"]) == "--collect-only"
        assert (
            _collect_only_requested(["pytest", "tests/", "-o", 'addopts="--co"'])
            == "--co inside an addopts override"
        )
        # The legitimate Coverage step's override and the coverage flags must stay green.
        assert _collect_only_requested(["pytest", "tests/", "--cov-branch", "--cov-append"]) is None
        assert (
            _collect_only_requested(
                ["pytest", "tests/", "-o", 'addopts="-v --tb=short -n auto -m not perf"']
            )
            is None
        )

    def test_pytest_addopts_is_found_on_the_step_or_its_job(self) -> None:
        assert _pytest_addopts_env({"env": {"PYTEST_ADDOPTS": "--co"}})
        assert _pytest_addopts_env({"env": {}}, {"env": {"PYTEST_ADDOPTS": "--co"}})
        assert not _pytest_addopts_env({"env": {"QT_QPA_PLATFORM": "offscreen"}}, {})

    def test_the_echo_smuggle_has_a_gate_command_that_is_not_last(self) -> None:
        commands = _commands_of("echo pytest tests/ -m perf -n 0\ntrue")
        gate = [c for c in commands if _marker_arg(c) is not None and "perf" in str(_marker_arg(c))]
        assert len(gate) == 1, "an echo naming the command is still one marker-carrying command"
        assert commands[-1] is not gate[0], "the gate command must not be the step's last command"


def test_ci_runs_the_whole_perf_set_serially() -> None:
    """The three perf steps are pinned by their commands, and by the two keys that can make
    a step or a job not gate at all. Both halves exist because prose got them wrong.

    `addopts` carries `-n auto --dist worksteal -m 'not perf'` (#509), so the perf tests
    run in neither mode by default: the battery deselects them, and the workers are the
    thing they must not share a runner with. Both jobs that run them have to say so
    explicitly, and each of the three details fails SILENTLY:

    * `tests/perf -m perf` collects **7 of the 14** and passes. Seven of the marked tests
      live outside `tests/perf/`, so a directory-scoped command looks complete and is
      not - CONTRIBUTING.md tabulates it as "the worst kind of wrong".
    * omitting `-m perf` lets `addopts`' own `-m 'not perf'` win and collects **nothing**.
    * omitting `-n 0` runs all 14 across 4 workers on a 4-vCPU runner, which is precisely
      the load the marker exists to avoid, and three of the fourteen carry no CI slack
      at all (map-picker close < 0.5 s, point-snapper mean < 16 ms, spatial-index
      medians < 200 ms / < 1 ms).

    **Why this parses the YAML rather than grepping the file.** Substring grepping
    for `"tests/ -m perf"` and `"-m perf -n 0"` in the whole text is satisfied by the
    Coverage job's copy of the command alone, so mutating the Test job's step ("Run
    performance budgets on a quiet runner") would leave a whole-file grep silently green.
    Each job and step must be looked up by key in the parsed structure so that each
    runner's configuration is validated independently.

    The marker half of this contract was already mechanised - `test_perf_marker_guard.py`
    fails the build if a wall-clock assertion is added without the marker - so the marker
    was the safe half to leave in prose and the invocation the dangerous one. Four
    documents carried a wrong invocation inside this change while every check stayed
    green.

    **Why it evaluates each COMMAND, not the step's whole token stream (#513).** A `run:`
    script may hold several commands; the one whose exit status is the step's is the LAST.
    Evaluating the concatenation let a script satisfy every assertion with a command that
    runs nothing - an earlier line naming the perf invocation, a here-doc body supplying
    the flags, a `|| true`, or an `-o addopts="--co"` at the end. So the marker-selecting
    command is identified, required to be the last command, required to actually invoke
    pytest, and refused if it collects-only. `scripts/replay_gate_mutations.py` replays
    each of these shapes and asserts this pin notices; run it after changing the matcher.
    """
    import yaml

    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]

    def perf_steps(job: str) -> list[tuple[dict, list[list[str]], list[list[str]]]]:
        """Each step in `job` carrying at least one perf-marker command.

        Returns `(step, commands, gate)`; `gate` is the commands whose `-m` selects the
        marker. The helper below requires exactly one such command per step and that it is
        the step's last command.
        """
        assert job in jobs, f"ci.yml no longer has a `{job}` job"
        found: list[tuple[dict, list[list[str]], list[list[str]]]] = []
        for step in jobs[job]["steps"]:
            commands = _commands_of(step.get("run"))
            gate = [
                argv
                for argv in commands
                if _marker_arg(argv) is not None and "perf" in str(_marker_arg(argv))
            ]
            if gate:
                found.append((step, commands, gate))
        return found

    def gated_command(
        job_name: str, step: dict, commands: list[list[str]], gate: list[list[str]]
    ) -> list[str]:
        """The one command that gates `step`, with the #513 shape checks applied."""
        _name = step.get("name") or step.get("run")
        assert len(gate) == 1, (
            f"`{_name}` carries {len(gate)} commands that select the perf marker; exactly "
            "one may, or the pin cannot say which one gates the step. A second "
            "marker-carrying command is how an `echo` or a here-doc body smuggles the flags "
            "into the token stream"
        )
        argv = gate[0]
        assert _is_pytest_run(argv), (
            f"`{_name}`'s perf command is `{' '.join(argv)}`, which does not invoke pytest - "
            "a delegating script (`bash scripts/ci_perf.sh …`) carries the marker without "
            "running a test"
        )
        assert commands[-1] is argv, (
            f"`{_name}`'s perf command is not the LAST command of the step, so it does not "
            "decide the step's exit status: `|| true`, a pipe to `tee`, or a script ending "
            "with another executor would let the step pass with the perf tests not run"
        )
        collect_only = _collect_only_requested(argv)
        assert collect_only is None, (
            f"`{_name}`'s perf command collects without running: {collect_only}. "
            "`--co`/`--collect-only` make the step succeed having run no test"
        )
        assert not _pytest_addopts_env(step, jobs[job_name]), (
            f"`{_name}` or its job sets PYTEST_ADDOPTS, which reaches every pytest "
            "invocation in the step without appearing in any `run:` line"
        )
        return argv

    test_steps = perf_steps("test")
    # ONE assertion, not two: an `assert test_steps` after this could never fire, because
    # `len(test_steps) == 1` is already false at zero and this message would never print.
    # A dead assertion reads as coverage.
    assert len(test_steps) == 1, (
        f"expected exactly one step carrying the perf marker in the `test` job, found "
        f"{len(test_steps)}. A renamed or moved step is a failure here rather than an empty "
        "result"
    )
    quiet_step, quiet_commands, quiet_gate = test_steps[0]
    quiet = gated_command("test", quiet_step, quiet_commands, quiet_gate)
    assert _covers_the_perf_marker(quiet, want_marker=True), (
        f"the test job's perf command is `{' '.join(quiet)}`. Its `-m` must SELECT `perf`, "
        "not deselect it"
    )
    assert _targets_tests_dir(quiet), (
        f"the test job's perf command is `{' '.join(quiet)}`. It must name `tests/`, not "
        "`tests/perf`: the marker means 'wall-clock sensitive', 7 of the 14 marked tests "
        "live outside tests/perf/, and the directory form collects those 7 and PASSES"
    )
    assert _flag_value(quiet, "-n") == "0", (
        f"the test job's perf command is `{' '.join(quiet)}`; `-n` must be `0`. Without it "
        "the timing tests run across workers, which is the condition the split exists to "
        "prevent"
    )

    coverage_steps = perf_steps("coverage") + perf_steps("coverage-perf")
    parallel: list[list[str]] = []
    serial: list[list[str]] = []
    for _step, _commands, _gate in coverage_steps:
        _job = "coverage" if _step in jobs["coverage"]["steps"] else "coverage-perf"
        _argv = gated_command(_job, _step, _commands, _gate)
        if _covers_the_perf_marker(_argv, want_marker=False):
            parallel.append(_argv)
        elif _covers_the_perf_marker(_argv, want_marker=True):
            serial.append(_argv)
    assert parallel, (
        "the Coverage job's parallel step must deselect the perf tests with `-m 'not perf'`; "
        "the perf set is then measured by the serial step instead of running under `-n auto`, "
        "which is where the three zero-slack budgets break"
    )
    assert any("--cov" in token for token in parallel[0]), (
        f"the deselecting step is `{' '.join(parallel[0])}`, which does not run under --cov"
    )
    assert serial, (
        "the Coverage job needs a serial step that SELECTS the perf marker - without it the "
        "perf set runs only in the parallel step, beside workers"
    )
    assert "--cov=open_garden_planner" in serial[0], "the serial tests must contribute coverage"
    assert _targets_tests_dir(serial[0]), "serial coverage must include the whole perf set"
    assert _flag_value(serial[0], "-n") == "0", (
        f"the serial step is `{' '.join(serial[0])}`; `-n` must be `0`, because running the "
        "timing tests across workers is the condition the split exists to prevent"
    )

    # Derived from the argv results rather than counted in the loop above, because the
    # count is what stops this pin from silently looking at nothing after a rename.
    found = len(test_steps) + len(coverage_steps)
    assert found >= 3, (
        f"expected the perf step in `test` plus parallel and serial coverage, found {found} - if a "
        "step was renamed or moved, this check has silently stopped looking at it"
    )

    # The `needs` graph, because a skipped dependency skips everything downstream of it.
    # Measured: a job with `if: false`, plus `needs: [that-job]` on `test`, leaves both
    # pins green while the perf step never executes. Plain YAML, no shell involved, and the
    # same "a skipped check is not a passing check" failure as an `if:` on the job itself.
    for gate_job in ("test", "coverage", "coverage-perf"):
        _seen: set[str] = set()
        _queue = list(_needs_of(jobs[gate_job]))
        while _queue:
            _dependency = _queue.pop()
            assert _dependency in jobs, (
                f"`{gate_job}` needs `{_dependency}`, which does not exist - GitHub would "
                "fail the workflow, and nothing here was checking that either"
            )
            # A processed-set, not a "seen" set used as a cycle test: a DIAMOND is
            # valid YAML and common (two jobs that both need a shared setup), e.g.
            # `test.needs: [lint, agent-context]` plus `lint.needs: [agent-context]`.
            if _dependency in _seen:
                continue
            _seen.add(_dependency)
            assert "if" not in jobs[_dependency], (
                f"`{gate_job}` needs `{_dependency}`, which is conditional. If that `if:` is "
                f"false the job is skipped, and so is `{gate_job}` with its perf gate - and "
                "a skipped job is reported differently from a passing one"
            )
            assert not jobs[_dependency].get("continue-on-error"), (
                f"`{_dependency}` can fail without failing the workflow, and `{gate_job}` "
                "depends on it"
            )
            _queue.extend(_needs_of(jobs[_dependency]))

    # The step-level and job-level neutralisations. They belong here because the pin
    # that finds the steps is the pin that must insist they can fail.
    for _job_name in ("test", "coverage", "coverage-perf"):
        _gate = jobs[_job_name]
        assert not _gate.get("continue-on-error"), (
            f"the `{_job_name}` job has continue-on-error: every gate inside it - including "
            "the perf budgets - becomes advisory while the check reports pass"
        )
        assert "if" not in _gate, (
            f"the `{_job_name}` job is conditional, and it carries a perf gate: it may be "
            "skipped entirely, which is reported differently from passing"
        )
        for _step in _gate.get("steps", []):
            _commands = _commands_of(_step.get("run"))
            _gate_commands = [
                _argv
                for _argv in _commands
                if _marker_arg(_argv) is not None and "perf" in str(_marker_arg(_argv))
            ]
            if not _gate_commands:
                continue
            _where = f"{_job_name} / {_step.get('name') or ' '.join(_gate_commands[0])[:40]}"
            assert not _step.get("continue-on-error"), (
                f"`{_where}` has continue-on-error: the perf tests would run, could fail, "
                "and the job would still be green - a gate that reports nothing"
            )
            # The loop matches parallel and serial coverage steps, and the two have
            # opposite consequences when skipped - so the message names the one that
            # applies instead of describing only the selecting case. Skipping the
            # deselecting step is not a weaker neutralisation than skipping the serial one:
            # the perf tests then run under `-n auto` in the parallel step, which is what
            # the three zero-slack budgets must not do.
            _skipped = (
                "the perf tests would never run"
                if _covers_the_perf_marker(_gate_commands[0], want_marker=True)
                else "the deselect would be skipped, so the perf tests would run under "
                "`-n auto` in the parallel step beside workers"
            )
            assert "if" not in _step, (
                f"`{_where}` is conditional, and it carries the perf gate: skip it and "
                f"{_skipped} - a skipped check is reported differently from a passing one"
            )

    # WHAT THIS CANNOT SEE, as measurements rather than as a claim of completeness. Every
    # entry below was run; the ones this file HAS closed are listed too, because a boundary
    # is only informative next to the things on the other side of it.
    #
    # CLOSED, and every entry names the ASSERTION that closes it rather than the shape. A
    # list of shapes reads as coverage even when nothing checks them;
    # `scripts/replay_gate_mutations.py` replays every closed shape and asserts each is
    # caught, so this list can be re-measured in one command rather than believed.
    #
    #   * a `#` comment naming the perf command - line-initial, mid-line in a block scalar,
    #     inside an `echo`, and after `true;`
    #         -> `_commands_of` strips comments with `shlex.split(comments=True)` (#513), so a
    #            comment never reaches `_marker_arg` / `_flag_value` / `_targets_tests_dir`.
    #   * `tests/perf` instead of `tests/`
    #         -> `_targets_tests_dir`, which compares a PATH token against `tests`.
    #   * a dropped `-n 0`
    #         -> `_flag_value(quiet, "-n") == "0"` and the same for `serial[0]`.
    #   * a dropped `--cov-append`
    #         -> `any(token == "--cov-append" for token in serial[0])`.
    #   * `continue-on-error` / `if:` on a perf STEP
    #         -> the `for _step in _gate.get("steps", [])` loop above.
    #   * `continue-on-error` / `if:` on `test` / `coverage` themselves
    #         -> the `for _job_name in ("test", "coverage")` loop above.
    #   * a `needs:` dependency that can never run
    #         -> the `needs` walk above. A skipped job is reported differently from a pass.
    #   * an earlier line naming the perf command, a here-doc body supplying the flags, and
    #     `bash scripts/ci_perf.sh tests/ -m perf -n 0` (#513)
    #         -> `gated_command`: the marker-selecting command must be the step's LAST command
    #            and must itself invoke pytest.
    #   * `|| true`, or a pipe to `tee` without `pipefail`, at the end of the command (#513)
    #         -> the same last-command rule: any command after the runner makes the runner
    #            not the step's exit status. A piped gate is refused even though `shell: bash`
    #            runs `-eo pipefail` and WOULD propagate the failure: the pin requires the gate
    #            to be the step's last command, so this is a shape it declines rather than one
    #            it reasons about. The one step that pipes (`pytest … | tee` for the duration
    #            report) carries no perf marker, so the rule does not touch it.
    #   * `-o addopts="--co"`, `--co`, `--collect-only` (#513)
    #         -> `_collect_only_requested`, which reads the flag directly or inside the
    #            `addopts=` override value.
    #   * `env: PYTEST_ADDOPTS: --co` on a perf step or its job (#513)
    #         -> `_pytest_addopts_env`.
    #
    # STILL OPEN, measured:
    #   * a control operator embedded in the MIDDLE of a token with no whitespace, e.g.
    #     `… ||true` is caught (`_leading_operator` splits the leading `||`), but a token
    #     like `a;b` or a `-n` value of `0;true` is not - though the latter fails the `-n`
    #     check loudly rather than passing, so it is over-strict, not a hole.
    #   * a `-k` / `--deselect` / `--ignore` filter, or a short `--maxfail`, inside the
    #     command or an `addopts` override. The command still runs tests, so this is a weaker
    #     shape than collect-only and is not screened yet.
    #   * `strategy.matrix` producing zero combinations, and a `concurrency` group that
    #     cancels the run. Neither has a pinned check; a `timeout-minutes` short enough to
    #     kill the step does fail the job, which is loud enough to count as covered.
    #
    # NOT holes, though earlier drafts claimed they were:
    #   * a `run:` expressed as a YAML list is caught as `found == 0` - loud, and not for the
    #     reason a draft gave (a TypeError from a regex);
    #   * a perf step moved into a reusable workflow is caught by the `found >= 3` guard.


def _assert_coverage_topology(workflow: dict) -> None:
    jobs = workflow["jobs"]
    parallel, perf, floor = (jobs[key] for key in ("coverage", "coverage-perf", "coverage-floor"))
    assert parallel["strategy"]["matrix"] == {"shard": [0, 1]}
    assert parallel["strategy"].get("fail-fast") is False
    for job in (parallel, perf):
        assert "if" not in job and not job.get("continue-on-error")
        commands = [step for step in job["steps"] if "--cov=" in str(step.get("run", ""))]
        assert len(commands) == 1
        step = commands[0]
        assert "if" not in step and not step.get("continue-on-error")
        assert "--cov-branch" in step["run"]
    measure = next(step["run"] for step in parallel["steps"] if "--cov=" in str(step.get("run", "")))
    assert "-p scripts.ci_coverage_shard" in measure
    assert "--coverage-shard=${{ matrix.shard }}/2" in measure
    for job, data_file, artifact_name in (
        (parallel, "coverage-data/nonperf-${{ matrix.shard }}.coverage", "coverage-data-${{ matrix.shard }}"),
        (perf, "coverage-data/perf.coverage", "coverage-data-perf"),
    ):
        step = next(step for step in job["steps"] if "--cov=" in str(step.get("run", "")))
        assert step["env"]["COVERAGE_FILE"] == data_file
        uploads = [step for step in job["steps"] if "upload-artifact@" in str(step.get("uses", ""))]
        assert len(uploads) == 1
        assert uploads[0]["with"] == {"name": artifact_name, "path": "coverage-data/",
                                     "if-no-files-found": "error"}
    assert floor["name"] == "Coverage" and floor["if"] == "always()"
    assert sorted(_needs_of(floor)) == ["coverage", "coverage-perf"]
    downloads = [step for step in floor["steps"] if "download-artifact@" in str(step.get("uses", ""))]
    assert len(downloads) == 1
    assert downloads[0]["with"] == {"pattern": "coverage-data-*", "merge-multiple": True,
                                    "path": "coverage-data/"}
    propagate = [step for step in floor["steps"] if step.get("name") == "Require every measurement"]
    assert len(propagate) == 1
    assert "if" not in propagate[0] and not propagate[0].get("continue-on-error")
    assert propagate[0]["run"].strip().splitlines() == [
        'test "${{ needs.coverage.result }}" = success',
        'test "${{ needs.coverage-perf.result }}" = success',
    ]
    combine = [step for step in floor["steps"] if step.get("name") == "Combine all coverage data"]
    assert len(combine) == 1
    assert "if" not in combine[0] and not combine[0].get("continue-on-error")
    commands = _commands_of(combine[0]["run"])
    assert commands == [
        ["python", "-m", "coverage", "combine", "coverage-data/nonperf-0.coverage",
         "coverage-data/nonperf-1.coverage", "coverage-data/perf.coverage"],
        ["python", "-m", "coverage", "xml", "-o", "coverage.xml"],
    ]


def test_coverage_shards_and_merge_are_pinned() -> None:
    import yaml

    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    _assert_coverage_topology(workflow)


@pytest.mark.parametrize("mutation", ["missing_shard", "missing_perf", "advisory",
                                      "skipped_measurement", "lost_branch", "lost_merge_input"])
def test_coverage_topology_pin_rejects_incomplete_measurements(mutation: str) -> None:
    import yaml

    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]
    if mutation == "missing_shard":
        jobs["coverage"]["strategy"]["matrix"]["shard"] = [0]
    elif mutation == "missing_perf":
        jobs["coverage-floor"]["needs"] = ["coverage"]
    elif mutation == "advisory":
        jobs["coverage-perf"]["continue-on-error"] = True
    elif mutation == "skipped_measurement":
        jobs["coverage"]["if"] = "false"
    elif mutation == "lost_branch":
        step = next(s for s in jobs["coverage"]["steps"] if "--cov=" in str(s.get("run", "")))
        step["run"] = step["run"].replace("--cov-branch", "")
    elif mutation == "lost_merge_input":
        step = next(s for s in jobs["coverage-floor"]["steps"] if s.get("name") == "Combine all coverage data")
        step["run"] = step["run"].replace("coverage-data/perf.coverage", "")
    with pytest.raises(AssertionError):
        _assert_coverage_topology(workflow)


def test_the_coverage_floor_step_is_pinned() -> None:
    """#514: the `Coverage` job's floor step must exist, always run, and read its report.

    `Coverage` is a required check now. The job's display name IS the branch-protection
    context, and the floor step is what decides the job: the two coverage steps are
    measurements, and this step is the gate. It must run `if: always()` so a skipped or
    failed measurement never reports a pass, and it must read `coverage.xml` explicitly.
    """
    import yaml

    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    coverage = workflow["jobs"]["coverage-floor"]
    assert coverage.get("name") == "Coverage", (
        "the Coverage job's display name IS the required-check context; a rename would "
        "leave branch protection waiting forever on a check that never reports"
    )
    floor_steps = [
        step
        for step in coverage["steps"]
        if "check_coverage_floors.py" in str(step.get("run", ""))
    ]
    assert len(floor_steps) == 1, (
        f"expected exactly one coverage-floor step in the Coverage job, found "
        f"{len(floor_steps)} - the floor is the gate, not an optional report"
    )
    step = floor_steps[0]
    assert step.get("if") == "always()", (
        "the floor step must run `if: always()`: it is the only step that decides the job, "
        "and skipping it when an earlier step failed would report success without a "
        "measurement"
    )
    assert "--xml coverage.xml" in str(step.get("run")), (
        "the floor step must read the `coverage.xml` the coverage steps write"
    )
    assert not step.get("continue-on-error"), (
        "the floor step must not set continue-on-error: it is the required status check"
    )
    assert not coverage.get("continue-on-error"), (
        "the Coverage job must not set continue-on-error"
    )


class TestCheckNoSecrets:
    """The secret checker must catch real credentials and nothing else.

    Both halves matter and they pull against each other. A checker that misses
    the real format is worse than no checker; one that fires on a variable
    named ``species_key`` is deleted after its first false alarm. gitleaks was
    rejected for exactly the second failure (29 findings, zero secrets) while
    being the thing that caught the real one — see the checker's module
    docstring.
    """

    # Each case is (label, filename-tag, line that MUST be reported).
    _MUST_CATCH = [
        (
            "ogp agent-api token in a url",
            "ogp",
            # 43 x "a": matches `?token=[A-Za-z0-9_-]{40,50}` (which is what
            # secrets.token_urlsafe() produces) while being unmistakably fake.
            'URL = "http://127.0.0.1:8765/mcp'
            '?token=' + "a" * 43 + '"',
        ),
        ("aws access key id", "aws", 'KEY = "AKIA' + "A" * 16 + '"'),
        ("github pat", "ghp", 'TOKEN = "ghp_' + "b" * 40 + '"'),
        ("slack token", "slack", 'T = "xoxb-' + "c" * 24 + '"'),
        # The Agent API token's OTHER supported delivery channel. Not
        # hypothetical: _bearer_token_middleware accepts it and
        # WriteAuthError's guidance tells users to fall back to it. A gate
        # written for a write-token incident that only covered ?token= would
        # have missed half the surface.
        (
            "ogp agent-api token as bearer",
            "bearer",
            'HEADERS = {"Authorization": "Bearer ' + "d" * 43 + '"}',
        ),
        # Same credential, LOWERCASE scheme. Not a contrived variant:
        # server.py:219 does `raw[:7].lower() == "bearer "`, so the server
        # accepts it and it is a working credential. A case-sensitive rule
        # would have flagged the canonical spelling and waved this through.
        (
            "ogp agent-api token as lowercase bearer",
            "bearer",
            'HEADERS = {"authorization": "bearer ' + "e" * 43 + '"}',
        ),
        # Assembled from fragments: the checker's own test file must not contain a
        # credential-shaped LITERAL, or it fails its own gate. Concatenation
        # defeats the single-regex-per-line match while producing the exact
        # bytes at runtime, which is what the assertion is about.
        ("private key header", "pk", "-----BEGIN " + "RSA " + "PRIVATE KEY" + "-----"),
    ]

    # Shapes that a generic high-entropy / identifier rule flags. These are the
    # 29 findings that disqualified gitleaks; every one of them must stay
    # silent, or the gate gets removed and then catches nothing.
    _MUST_NOT_FLAG = [
        ("species_key kwarg", "service, species_key, exclude_antagonists_of=exclude_antagonists_of"),
        ("translation-table Keys row", '"Shift+Arrow Keys": "Umschalt+Pfeiltasten",'),
        ("layer_id assignment", 'layer_id = meta.get("parent_bed_id")'),
        ("token_urlsafe call", "token = secrets.token_urlsafe(32)"),
        ("doc placeholder", 'url = "http://127.0.0.1:8765/mcp?token=<token>"'),
    ]

    def _scan_with_canary(self, tmp_path: Path, tag: str, line: str) -> list[str]:
        """Scan an ISOLATED git repo that contains nothing but the canary.

        The checker deliberately reads only git-TRACKED files, so an untracked
        scratch file must not be able to fail a build. That is why this stages the
        canary at all — staging is what a real leak would look like.

        **It used to stage the canary in the REAL repository**, at
        ``scripts/_canary_<tag>.py``, and #507 then had to harden that: the
        ``git add`` sat OUTSIDE the ``try``, so an interrupted run — Ctrl-C, a
        pytest-timeout kill, a crash between the two calls — left the canary
        staged and the next ``git commit -a`` published it. It happened: a
        one-line canary was committed on PR #507 before review caught it.

        This no longer touches the real index at all, so that failure is not
        hardened against — it is **structurally impossible**: nothing outside the
        temp directory is created, staged or deleted, under any scheduler, and
        including an interrupted run. That was measured, not assumed (#509):
        staging into the shared working tree was the only test in the suite that
        mutated shared state, and under ``pytest -n`` a sibling worker's
        ``root.rglob("*.py")`` in ``test_settings_chokepoint.py`` could list the
        canary inside the write-to-unlink window and die with
        ``FileNotFoundError``. The same window also let this file's own
        whole-repo scan read a *sibling worker's* staged canary and report a
        credential that was never committed anywhere.

        ``test_the_real_tree_is_clean`` still guards the real tree, which is now
        the third state to check rather than the only one.
        """
        import subprocess

        from scripts.check_no_secrets import check_repo

        root = tmp_path / f"repo_{tag}"
        (root / "scripts").mkdir(parents=True)
        # Not check=True, and the reason is NOT "git might be missing, so let the scan fall
        # back to walking the directory" — that fallback cannot happen. `subprocess.run`
        # raises FileNotFoundError when the binary is absent, which is an OSError and is
        # NOT caught here, so a machine without git would ERROR on this line and never
        # reach `_tracked_files` at all. (`scripts/check_no_secrets.py:187` does catch it;
        # this call site does not, which is a real exposure and a separate fix.)
        # The actual reason is narrower: `git init` writes to stderr and its exit status
        # is not what this helper asserts. The assertion is about DETECTION — that a
        # tracked canary is found — not about git being installed or configured.
        subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
        canary = root / "scripts" / f"_canary_{tag}.py"
        canary.write_text(line + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "--", "scripts"], cwd=root, capture_output=True)
        # No try/finally unstage, because there is nothing to unstage: `root` is a
        # throwaway repo under tmp_path, so the canary cannot reach the real index
        # even if this process dies mid-test. #507's `_assert_no_canary_residue`
        # contract ("stage, scan, unstage, delete") no longer describes what happens,
        # and the honest version is stronger: there is no fourth step to forget.
        return [f for f in check_repo(root) if canary.name in f]

    def _assert_no_canary_residue(self, tag: str) -> None:
        """Assert the REAL repository carries no canary residue.

        Added after a one-line ``_canary_fp_*.py`` was committed and pushed on
        PR #507 (#507, round 4 of review). No other gate could have caught it: the
        canary's own text is in ``_MUST_NOT_FLAG``, so the secrets scan is blind
        to it by construction, and a residue assertion is the only thing that
        turns "we hope the ``finally`` ran" into a checked invariant.

        **Rewritten in scope by #509.** It used to assert the helper's four-step
        contract — "stage, scan, unstage, delete" — against the real index, because
        the helper staged there. The helper now stages in a throwaway repo under
        ``tmp_path``, so there is no unstage and no delete to assert, and #507's
        hazard is structurally impossible rather than merely handled. What remains
        worth asserting is the state this change could still damage: the real tree.
        `test_the_real_tree_is_clean` covers the credential shape; this covers any
        residue at all, which is the broader of the two.
        """
        import subprocess
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        leftovers = sorted(p.name for p in (root / "scripts").glob("_canary_*"))
        assert not leftovers, f"canary file(s) left on disk after {tag}: {leftovers}"
        staged = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
        canaries = [p for p in staged if "_canary_" in p]
        assert not canaries, f"canary still staged in the index after {tag}: {canaries}"

    @pytest.mark.parametrize("label,tag,line", _MUST_CATCH, ids=[c[0] for c in _MUST_CATCH])
    def test_catches_real_credential(self, tmp_path: Path, label, tag, line) -> None:
        found = self._scan_with_canary(tmp_path, tag, line)
        assert found, f"the secret checker missed a real credential: {label}"
        self._assert_no_canary_residue(tag)

    @pytest.mark.parametrize(
        "index,label,line",
        [(i, label, line) for i, (label, line) in enumerate(_MUST_NOT_FLAG)],
        ids=[c[0] for c in _MUST_NOT_FLAG],
    )
    def test_does_not_flag_identifier_noise(self, tmp_path: Path, index, label, line) -> None:
        # Index-based, not `hash(line)`: str hashing is salted per process, so a
        # hash-derived filename changed on every run and every worker.
        found = self._scan_with_canary(tmp_path, f"fp_{index}", line)
        assert not found, (
            f"the secret checker flagged ordinary code ({label}): {found} — "
            "a gate that cries wolf on variable names gets deleted, and then "
            "it catches nothing"
        )

    def test_the_real_tree_is_clean(self) -> None:
        from scripts.check_no_secrets import check_repo

        assert check_repo(_REPO_ROOT) == [], (
            "the committed tree contains a credential-shaped string; if this is "
            "a real secret, ROTATE IT — deleting the file in a later commit "
            "does not unpublish it"
        )
