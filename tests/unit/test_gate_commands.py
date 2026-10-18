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
        if name == _RELEASE_WORKFLOW:
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
        if name == _RELEASE_WORKFLOW:
            continue  # checked by its own test, on pwsh terms (no bash involved)
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


def _script_lines(run: object) -> list[str]:
    """A step's `run` as executable lines, with line-initial shell comments removed.

    A `#` that starts a line inside a `run:` block is text, not a command. Measured: a step
    whose script was

        # pytest tests/ -m perf -v -n 0
        pytest tests/ -m 'not perf' -v -n 0

    left both pins green while the perf tests ran nothing - the selector and the substring
    assertions were reading the comment.

    A `run:` expressed as a YAML list returns `[]`, which shows up as `found == 0` rather
    than as a TypeError from a regex.
    """
    if isinstance(run, list):
        return []
    return [
        line
        for line in str(run).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _argv_of(script: str) -> list[str]:
    """The argv of a step's script, with shell comments stripped.

    Every line is tokenised and the tokens are concatenated, NOT just the last line: a
    `run: >` folded scalar is one command spread over several source lines, and the CI
    Coverage steps are written that way - reading only the last line of one finds
    `--cov=...` and no `-m` at all. Measured: the first version of this helper made both
    pins go from 3 matching steps to 1.

    `comments=True` is what a shell does with `#`: it ends the command. Without it the
    trailing `# -n 0 would need the quiet runner` in a signaller script became real argv
    tokens and satisfied the `-n 0` check.

    Unbalanced quotes return `[]`, which surfaces as "found 0" - loud, if unhelpful.
    """
    argv: list[str] = []
    for line in _script_lines(script):
        try:
            argv.extend(shlex.split(line, comments=True))
        except ValueError:
            return []
    return argv


def _marker_arg(argv: list[str]) -> str | None:
    """The value of pytest's `-m`, if the argv carries one.

    Not simply "the first `-m`": `python -m pytest ... -m 'not perf'` has two, and the
    first means "run module". Measured - taking the first made the coverage job's parallel
    step report its marker as `pytest` and drop out of the matched set. So the search starts
    at the `pytest` token, and falls back to the LAST `-m` when there is none, because a
    later flag is the one that overrides.
    """
    starts: list[int] = []
    for index, token in enumerate(argv):
        if token == "pytest" or token.endswith("/pytest") or token.endswith("\\pytest.exe"):
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
    for index, token in enumerate(argv):
        if token == "pytest":
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
    tokens = {part.strip() for part in value.replace("(", " ").replace(")", " ").split()}
    has_perf = any(tok == "perf" for tok in tokens)
    negated = "not" in tokens
    return has_perf and (not negated if want_marker else negated)


def _needs_of(job: dict) -> list[str]:
    """Normalise a job's `needs`, which YAML may give as a string or a list."""
    needs = job.get("needs")
    if needs is None:
        return []
    return [needs] if isinstance(needs, str) else list(needs)


def test_ci_runs_the_whole_perf_set_serially() -> None:
    """The three perf steps are pinned by their argv, and by the two keys that can make a
    step or a job not gate at all. Both halves exist because prose got them wrong.

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

    **Why this parses the YAML rather than grepping the file.** The first version of this
    test grepped for `"tests/ -m perf"` and `"-m perf -n 0"` in the whole text, and it
    passed for the wrong reason: both substrings are satisfied by the COVERAGE job's copy
    of the command, so mutating the TEST job's step - the one actually named "Run
    performance budgets on a quiet runner", the one carrying the three zero-slack budgets -
    to `pytest tests/ -m perf -v` or to the directory form left this test GREEN. Both
    mutations were run; both passed. A pin that cannot fail is worse than no pin, because
    it reads as protection. `text.split("  coverage:", 1)[-1]` had the same defect wearing
    a disguise: if the separator ever goes missing the "scoped" assertion silently becomes
    a whole-file assertion with the same outcome. So each job is looked up by key, and a
    missing key is a failure rather than an empty result.

    The marker half of this contract was already mechanised - `test_perf_marker_guard.py`
    fails the build if a wall-clock assertion is added without the marker - so the marker
    was the safe half to leave in prose and the invocation the dangerous one. Four
    documents carried a wrong invocation inside this change while every check stayed
    green.
    """
    import yaml

    workflow = yaml.safe_load(
        (_REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    jobs = workflow["jobs"]

    def perf_steps(job: str) -> list[list[str]]:
        assert job in jobs, f"ci.yml no longer has a `{job}` job"
        found: list[list[str]] = []
        for step in jobs[job]["steps"]:
            argv = _argv_of(step.get("run"))
            if argv and _marker_arg(argv) is not None and "perf" in str(_marker_arg(argv)):
                found.append(argv)
        return found

    test_steps = perf_steps("test")
    # ONE assertion, not two: an `assert test_steps` after this could never fire, because
    # `len(test_steps) == 1` is already false at zero and the message documenting the
    # unquoted-`echo` hole would never print. A dead assertion reads as coverage.
    assert len(test_steps) == 1, (
        f"expected exactly one perf step in the `test` job, found {len(test_steps)}: "
        f"{test_steps}. `-m` is read as a token pair, which catches a command hidden inside "
        "a comment - but NOT one hidden inside an unquoted `echo`, because `_argv_of` "
        "concatenates the tokens of every line; see the measured-open list below"
    )
    quiet = test_steps[0]
    assert _covers_the_perf_marker(quiet, want_marker=True), (
        f"the test job's perf step is `{' '.join(quiet)}`. Its `-m` must SELECT `perf`, not "
        "deselect it"
    )
    assert _targets_tests_dir(quiet), (
        f"the test job's perf step is `{' '.join(quiet)}`. It must name `tests/`, not "
        "`tests/perf`: the marker means 'wall-clock sensitive', 7 of the 14 marked tests "
        "live outside tests/perf/, and the directory form collects those 7 and PASSES"
    )
    assert _flag_value(quiet, "-n") == "0", (
        f"the test job's perf step is `{' '.join(quiet)}`; `-n` must be `0`. Without it the "
        "timing tests run across workers, which is the condition the split exists to prevent"
    )

    coverage_steps = perf_steps("coverage")
    parallel = [argv for argv in coverage_steps if _covers_the_perf_marker(argv, want_marker=False)]
    serial = [argv for argv in coverage_steps if _covers_the_perf_marker(argv, want_marker=True)]
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
    assert any(token == "--cov-append" for token in serial[0]), (
        "the serial step must append, and it is LOAD-BEARING, not tidiness. Measured with "
        "the gate itself: step 1 alone leaves `agent_api` at 2012 of 2195 and the gate "
        "exiting 1; with the append it is 2026 and `regressions: []`. The delta is the "
        "fourteen `stop()` escalation lines. Delete the append and Coverage goes red on "
        "agent_api; delete the deselect and the append becomes redundant."
    )
    assert _flag_value(serial[0], "-n") == "0", (
        f"the serial step is `{' '.join(serial[0])}`; `-n` must be `0`, because running the "
        "timing tests across workers is the condition the split exists to prevent"
    )

    # Derived from the argv results rather than counted in the loop above, because the
    # count is what stops this pin from silently looking at nothing after a rename.
    found = len(test_steps) + len(coverage_steps)
    assert found >= 3, (
        f"expected the perf step in `test` and the two in `coverage`, found {found} - if a "
        "step was renamed or moved, this check has silently stopped looking at it"
    )

    # The `needs` graph, because a skipped dependency skips everything downstream of it.
    # Measured: a job with `if: false`, plus `needs: [that-job]` on `test`, leaves both
    # pins green while the perf step never executes. Plain YAML, no shell involved, and the
    # same "a skipped check is not a passing check" failure as an `if:` on the job itself.
    for gate_job in ("test", "coverage"):
        _seen: set[str] = set()
        _queue = list(_needs_of(jobs[gate_job]))
        while _queue:
            _dependency = _queue.pop()
            assert _dependency in jobs, (
                f"`{gate_job}` needs `{_dependency}`, which does not exist - GitHub would "
                "fail the workflow, and nothing here was checking that either"
            )
            # A processed-set, not a "seen" set used as a cycle test: a DIAMOND is
            # valid YAML and common (two jobs that both need a shared setup), and a first
            # version of this walk failed `test.needs: [lint, agent-context]` plus
            # `lint.needs: [agent-context]` with "cycle in the needs graph" - three lines
            # of valid configuration diagnosed as a defect that did not exist.
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

    # The step-level and job-level neutralisations. These assertions lived in a separate test
    # (`test_the_perf_steps_cannot_be_neutralised`) until `d9d18860` deleted it while the
    # comment below went on claiming they were checked; seven mutations were then measured
    # green against this pin. They belong here rather than in a second test because the pin
    # that finds the steps is the pin that must insist they can fail.
    for _job_name in ("test", "coverage"):
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
            _argv = _argv_of(_step.get("run"))
            if not (_argv and "perf" in str(_marker_arg(_argv))):
                continue
            _where = f"{_job_name} / {_step.get('name') or ' '.join(_argv)[:40]}"
            assert not _step.get("continue-on-error"), (
                f"`{_where}` has continue-on-error: the perf tests would run, could fail, "
                "and the job would still be green - a gate that reports nothing"
            )
            # The loop matches BOTH perf steps of the Coverage job, and the two have
            # opposite consequences when skipped - so the message names the one that
            # applies instead of describing only the selecting case. Skipping the
            # deselecting step is not a weaker neutralisation than skipping the serial one:
            # the perf tests then run under `-n auto` in the parallel step, which is what
            # the three zero-slack budgets must not do.
            _skipped = (
                "the perf tests would never run"
                if _covers_the_perf_marker(_argv, want_marker=True)
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
    # list of shapes reads as coverage even when nothing checks them - which is exactly what
    # happened here: `d9d18860` deleted the test holding the step/job assertions while this
    # comment went on claiming the shapes were verified, and seven mutations then passed.
    #
    #   * a `#` comment naming the perf command - line-initial, mid-line in a block scalar,
    #     inside an `echo`, and after `true;`
    #         -> `_argv_of` tokenises each line with `shlex.split(comments=True)`, so a
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
    #
    # STILL OPEN, measured:
    #   * `-o addopts="--collect-only"`, `--co`, or `env: PYTEST_ADDOPTS: --co` on a perf
    #     step's command - the step succeeds without running a single test.
    #   * `|| true`, or a pipe to `tee` without `pipefail`, on the same command. Note this
    #     is NOT unpinnable: `shlex.split` yields `||` and `true` as tokens, so a check for a
    #     disjunction after the command is a few lines. An earlier version of this note said
    #     "shell semantics cannot be pinned statically", which was an overclaim - it is
    #     unwritten, not unwritable.
    #   * tokens belonging to a different command taken as the command's. `_argv_of`
    #     concatenates every line's tokens, so a script whose real command lacks `-n 0` and
    #     whose earlier line is `echo pytest tests/ -m perf -n 0` satisfies all three
    #     assertions while running nothing. Same shape: a here-doc body supplying the flags,
    #     and `bash scripts/ci_perf.sh tests/ -m perf -n 0`. The fix is to split the token
    #     stream into commands and evaluate the checks on the one that selects the marker;
    #     it is not written yet, and an earlier version of the assertion message claimed it
    #     was covered.
    #   * `strategy.matrix` producing zero combinations, and a `concurrency` group that
    #     cancels the run. Neither has a pinned check; a `timeout-minutes` short enough to
    #     kill the step does fail the job, which is loud enough to count as covered.
    #
    # NOT holes, though earlier drafts claimed they were:
    #   * a `run:` expressed as a YAML list is caught as `found == 0` - loud, and not for the
    #     reason a draft gave (a TypeError from a regex);
    #   * a perf step moved into a reusable workflow is caught by the `found >= 3` guard.


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
