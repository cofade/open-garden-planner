"""Documented figures must be the figures the committed harnesses produce.

**Why this exists.** Seven review rounds each found a documented number that the
code contradicts: `2,669`, `1 of 64` / `10 of 54`, garlic "two months early" (the
direction was wrong), `1.0-1.5x`, "317 previously-unrun statements now covered",
the third-vs-fourth "offset to date" count, `(2,190 cases)6`. The retractions are
all in the git history; nothing prevented them being written.

**What this guard is.** It re-runs the two committed measurement harnesses, parses
what they printed, and fails if a document quotes a number in a *known shape* that
the harness did not produce. It exercises a function, so it survives refactoring
and it moves with the data.

**What this guard is deliberately not.** An earlier version also carried a
hand-typed table of retracted strings (`RETRACTED`) plus two test classes that
scanned documents for them. Round 7's objection was correct: that mechanism
"cannot catch a *new* wrong figure, which is the failure mode that actually produced
six rounds of findings — every one of those is a fresh false claim in a document,
and the guard was green through all of them because none of them is in the table."
A list of strings someone typed guards against re-pasting a *known* wrong string
and costs real maintenance. It is deleted.

The hole that leaves is narrow and worth stating plainly: a wrong figure in a
**brand-new shape** — nobody has ever written "1.0-1.5x" before, so no pattern
covers it. That is much smaller than "only figures I already knew about", and it
is not closable by a static check at all.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Every place prose can assert a number about this work.
_CORPUS = sorted(
    [
        *REPO_ROOT.glob("docs/**/*.md"),
        REPO_ROOT / "docs" / "roadmap.md",
        REPO_ROOT / "CLAUDE.md",
        REPO_ROOT / "AGENTS.md",
        *REPO_ROOT.glob(".claude/skills/*/SKILL.md"),
        *REPO_ROOT.glob(".agents/skills/*/SKILL.md"),
        *REPO_ROOT.glob("tests/**/*.py"),
    ]
)

#: The two committed harnesses whose output is the source of truth for these
#: figures.
SWEEP = "scripts/measure_task_window_sweep.py"
HARVEST = "scripts/measure_harvest_offsets.py"

#: Files allowed to NAME a retracted figure, because they record the retraction.
#:
#: This is a path exemption, not a blacklist of strings — the mechanism round 7
#: asked this guard to stop being. Two files quote the old numbers *in order to
#: say they were wrong* (`test_harvest_offset_semantics.py` and the harvest
#: harness's own docstring), and the lint below correctly flags both, which is how
#: the exemption came to exist. `test_the_recorders_still_record_the_retraction`
#: keeps it from rotting into a blanket silence.
_RETRACTION_RECORDERS = (
    REPO_ROOT / "tests" / "unit" / "test_harvest_offset_semantics.py",
    REPO_ROOT / HARVEST,
)

#: This file is in `_CORPUS` and necessarily contains literal wrong figures as
#: positive-control fixtures ("it is 44 fit / 20 miss here"). Exempted explicitly
#: rather than by a broad `tests/` filter, which would hide a real reintroduction
#: anywhere else under `tests/`.
_LINT_FIXTURES = (REPO_ROOT / "tests" / "unit" / "test_retracted_figures.py",)


def _stale_over(corpus, patterns) -> list[str]:
    """The lint's real matching, over a supplied corpus.

    Extracted from `_stale` so the positive controls run the SAME code the suite
    does. A control that re-implements the check tests the re-implementation —
    which is a mistake this branch has already made once, in the retraction scan.
    """
    hits: list[str] = []
    for path in corpus:
        if path in _RETRACTION_RECORDERS or path in _LINT_FIXTURES:
            continue
        text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
        for pattern, allowed in patterns:
            for match in pattern.finditer(text):
                # Groups can carry thousands separators (`1,849`); the inline
                # loop this helper replaced stripped them, and consolidating the
                # matching into one place lost that until the sweep test ran.
                numbers = tuple(int(g.replace(",", "")) for g in match.groups())
                if numbers not in allowed:
                    try:
                        shown = str(path.relative_to(REPO_ROOT))
                    except ValueError:
                        shown = path.name
                    hits.append(f"{shown} quotes {'/'.join(map(str, numbers))}")
    return hits


def _figure(output: str, label: str) -> int:
    match = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", output)
    assert match is not None, f"{label!r} not in output:\n{output}"
    return int(match.group(1))


def _run(script: str, *args: str) -> str:
    proc = subprocess.run(
        [sys.executable, script, *args],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={"PATH": "", "PYTHONUTF8": "1", "SYSTEMROOT": r"C:\Windows",
             "QT_QPA_PLATFORM": "offscreen"},
    )
    assert proc.returncode == 0, f"{script} failed:\n{proc.stdout}\n{proc.stderr}"
    return proc.stdout


def _harvest_pairs(output: str) -> set[tuple[int, int]]:
    """The ``N fit / M miss`` pairs the harvest harness actually printed.

    Parsed from the harness output rather than typed in. A typed list is exactly
    the hand-maintained constant this guard stopped being: it goes stale silently
    when the harness changes, which is how the figures drifted four times.
    """
    pairs = {
        (int(fit), int(miss))
        for fit, miss in re.findall(
            r"reading [AB] \([^)]*\)\s*:\s*(\d+) fit / (\d+) miss", output
        )
    }
    assert pairs, f"could not parse any reading from the harness output:\n{output}"
    return pairs


def _harvest_population() -> int:
    """Species carrying both harvest offsets and a maturity range.

    Computed from the bundled data, not typed as ``64`` — a pinned constant goes
    stale the next time a species row changes, which is the same failure as the ADR
    counts deleted in round 6.
    """
    import json

    data = json.loads(
        (
            REPO_ROOT / "src" / "open_garden_planner" / "resources" / "data"
            / "plant_species.json"
        ).read_text(encoding="utf-8")
    )
    return sum(
        1
        for row in data["plants"]
        if row.get("harvest_start") is not None
        and row.get("harvest_end") is not None
        and row.get("days_to_maturity_min") is not None
        and row.get("days_to_maturity_max") is not None
    )


def _sweep_counts(output: str) -> set[int]:
    """The ``N (task, frost date, day) cases the GUI missed`` values printed."""
    return {
        int(n) for n in re.findall(r"missed by the GUI on master\s*:\s*(\d+)", output)
    }


#: The lint's patterns, as module constants so a positive control imports the SAME
#: regex the suite runs. An earlier control compiled its own copy of the sweep
#: pattern and got it wrong, so it proved that a pattern nothing runs can fire while
#: the real one was never tested — a control that re-implements the check.
PATTERN_FIT_MISS = re.compile(r"(\d+) fits? / (\d+) miss")
PATTERN_OF_TOTAL = re.compile(r"fits? \*\*(\d+) of (\d+)\*\*")
PATTERN_SWEEP_CASES = re.compile(
    # "frost-date" and "frost date" both appear in the wild; the wording drifted
    # between the documents, and a pattern matching only one was silently inert.
    #
    # A second alternative used to require "(task, frost date, day) cases the GUI
    # missed)" — but real documents put the `)` straight after `day`, which this
    # already matches, so it could never fire. Dead code in a pattern makes it look
    # broader than it is; removed.
    r"(\d[\d,]*)\s*\(task,\s*frost[- ]date,\s*day\)"
)


class TestTheHarnessesStillProduceWhatTheDocumentsQuote:
    """The invariant, checked against a live run rather than a remembered number."""

    def test_the_task_window_sweep_reproduces_both_quoted_harnesses(self) -> None:
        default = _run(SWEEP)
        wide = _run(SWEEP, "--wide")

        # The invariant, not just the numbers: nothing missed AND nothing added.
        # A "0 missed" that also added surplus tasks would be a regression that
        # hides behind the headline figure.
        for name, output in (("default", default), ("--wide", wide)):
            missed_after = _figure(output, "missed by the GUI now")
            surplus = _figure(output, "listed now but not by the agent")
            assert missed_after == 0, f"{name} harness missed {missed_after}"
            assert surplus == 0, f"{name} harness added {surplus} surplus tasks"

        # Both harnesses' headline counts, so a change in either is visible here
        # rather than in whichever document happens to quote it.
        assert _sweep_counts(default) == {1849}, default
        assert _sweep_counts(wide) == {18007}, wide

    def test_the_harvest_harness_still_produces_two_readings(self) -> None:
        output = _run(HARVEST)
        assert len(_harvest_pairs(output)) == 2, output
        assert re.search(r"species that fit neither reading:\s*\d+", output), output

    def test_the_corpus_is_not_empty(self) -> None:
        """A guard that reads nothing passes; make that visible."""
        assert len(_CORPUS) > 20, len(_CORPUS)

    def test_the_recorders_still_record_the_retraction(self) -> None:
        """The path exemption must not rot into a blanket silence.

        The exemption exists so two files can quote the old numbers while saying
        they were wrong. If they stop saying that, the exemption is hiding a live
        reintroduction instead of a retraction, and this fails.
        """
        for path in _RETRACTION_RECORDERS:
            assert path.exists(), f"exempted file is gone: {path}"
            text = path.read_text(encoding="utf-8")
            assert any(
                phrase in text
                for phrase in (
                    "were wrong",
                    "were retracted",
                    "the conclusion was wrong",
                )
            ), (
                f"{path.relative_to(REPO_ROOT)} is exempt from the figure lint but "
                "no longer records a retraction, so the exemption is now hiding "
                "something"
            )

    def test_the_lint_fixture_exemption_is_still_justified(self) -> None:
        """The other exemption has a different reason, asserted separately.

        `_LINT_FIXTURES` exists because this file necessarily contains literal
        wrong figures as positive controls. If those fixtures are ever removed, the
        exemption should go with them — otherwise it is a silent hole in the lint.
        """
        for path in _LINT_FIXTURES:
            assert path.exists(), f"exempted file is gone: {path}"
            text = path.read_text(encoding="utf-8")
            assert "positive control" in text or "fits **1 of 64**" in text, (
                f"{path.relative_to(REPO_ROOT)} is exempt from the figure lint but "
                "no longer carries the positive-control fixtures that justify it"
            )


class TestDocumentsOnlyQuoteFiguresTheHarnessesProduce:
    """The lint: any count in a shape the harness speaks must be one it printed.

    **What this covers**, precisely: the two harvest fit/miss shapes (`N fit /
    M miss`, `N of T`) and the sweep's `N (task, frost-date, day) cases the GUI
    missed`. Those are the shapes with a committed source of truth, and each
    pattern has a positive control below so it is demonstrably able to fire.

    **What it does not cover**, and cannot: a ratio range like `1.0-1.5x` (no
    harness prints it, so there is nothing to compare against); a coverage figure
    like `317` (that belongs to `scripts/measure_array_tool_coverage.py`, a harness
    this lint does not run); and a plain typo like `(2,190 cases)6` (a typo has no
    shape to key on).

    An earlier docstring claimed all three of those were caught. Round 8 ran the
    patterns against them and got `[False, False, False]`. Making the claim true
    would mean inventing shapes with no source of truth behind them — the very
    blacklist this guard was rebuilt to escape — so the claim is cut. Stating the
    boundary is the honest version, and it is what tells the next reader which
    numbers still need a human.
    """

    @staticmethod
    def _stale(patterns: list[tuple[re.Pattern[str], set]], what: str) -> list[str]:
        """The lint over the real corpus; `_stale_over` holds the matching."""
        return [
            f"{hit} — {what} no run of the committed harnesses produced"
            for hit in _stale_over(_CORPUS, patterns)
        ]

    def test_no_document_quotes_an_unmeasured_harvest_count(self) -> None:
        pairs = _harvest_pairs(_run(HARVEST))
        allowed = [
            # "N fit / M miss" is a PAIR summing to the population.
            (PATTERN_FIT_MISS, pairs),
            # "N of T" is a fit against the population.
            (PATTERN_OF_TOTAL, {(fit, _harvest_population()) for fit, _ in pairs}),
        ]
        stale = self._stale(allowed, "a harvest count")
        assert not stale, "\n  ".join(stale)

    def test_no_document_quotes_an_unmeasured_sweep_count(self) -> None:
        """The ``1,849`` / ``18,007`` class, in the shape documents use it in.

        Runs through the same `_stale_over` the rest of the class uses, so this
        check cannot drift from the others — an earlier version had its own inline
        loop and silently missed the `_LINT_FIXTURES` exemption, which made the
        guard flag its own positive controls.
        """
        counts = _sweep_counts(_run(SWEEP)) | _sweep_counts(_run(SWEEP, "--wide"))
        stale = [
            f"{hit} — the harnesses produce {sorted(counts)}"
            for hit in _stale_over(
                _CORPUS, [(PATTERN_SWEEP_CASES, {(c,) for c in counts})]
            )
        ]
        assert not stale, "\n  ".join(stale)


class TestEachLintPatternCanActuallyFire:
    """A pattern that cannot fire is not a guard.

    Round 8's method: run each regex against a string it is supposed to catch. These
    do exactly that through the REAL ``_stale`` helper, so a pattern that is
    silently inert (a wrong escape, a missing group, an adjacency that never holds)
    fails here instead of passing everything.
    """

    @staticmethod
    def _stale_for(path: Path, patterns) -> list[str]:
        """The real `_stale`, pointed at a single synthetic file."""
        return _stale_over([path], patterns)

    def _check(self, tmp_path: Path, body: str, patterns, expect_fire: bool) -> None:
        target = tmp_path / "sample.md"
        target.write_text(body, encoding="utf-8")
        hits = _stale_over([target], patterns)
        fired = bool(hits)
        assert fired is expect_fire, (
            f"expected fire={expect_fire}, got {fired}, for {body!r}: {hits}"
        )

    def test_the_harvest_pair_pattern_fires(self, tmp_path: Path) -> None:
        patterns = [(PATTERN_FIT_MISS, {(38, 26), (45, 19)})]
        self._check(tmp_path, "it is 44 fit / 20 miss here", patterns, True)
        self._check(tmp_path, "it is 38 fit / 26 miss here", patterns, False)

    def test_the_harvest_of_total_pattern_fires(self, tmp_path: Path) -> None:
        patterns = [(PATTERN_OF_TOTAL, {(38, 64)})]
        self._check(tmp_path, "fits **1 of 64**", patterns, True)
        self._check(tmp_path, "fits **38 of 64**", patterns, False)

    def test_the_sweep_case_pattern_fires(self, tmp_path: Path) -> None:
        # `_stale_over` keys on `match.groups()`, so a one-group pattern yields a
        # 1-tuple. `{1849, 18007}` here would make the control fire on a CORRECT
        # value and prove nothing — which is what it did before this was fixed.
        # The REAL pattern, which requires the "(task, frost date, day)" prefix.
        # The previous control compiled a looser regex of its own and therefore
        # tested nothing the suite runs.
        patterns = [(PATTERN_SWEEP_CASES, {(1849,), (18007,)})]
        self._check(
            tmp_path,
            "**999 (task, frost-date, day) cases the GUI missed**",
            patterns,
            True,
        )
        self._check(
            tmp_path,
            "**1849 (task, frost-date, day) cases the GUI missed**",
            patterns,
            False,
        )

    def test_a_clean_document_fires_nothing(self, tmp_path: Path) -> None:
        """The negative case the whole suite depends on."""
        patterns = [
            (PATTERN_FIT_MISS, {(38, 26)}),
            (PATTERN_OF_TOTAL, {(38, 64)}),
            (PATTERN_SWEEP_CASES, {(1849,)}),
        ]
        self._check(tmp_path, "Nothing quotable is claimed here.\n", patterns, False)
