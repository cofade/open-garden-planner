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


class TestDocumentsOnlyQuoteFiguresTheHarnessesProduce:
    """The lint: any count in a known shape must be one the harness printed.

    This is what would have caught `1.0-1.5x`, `317 now covered` and
    `(2,190 cases)6` — each was a number in a shape the harness already speaks in.
    """

    @staticmethod
    def _stale(patterns: list[tuple[re.Pattern[str], set]], what: str) -> list[str]:
        stale: list[str] = []
        for path in _CORPUS:
            if path in _RETRACTION_RECORDERS:
                continue
            # Whitespace-collapsed: a claim split across a line is still a claim.
            text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
            for pattern, allowed in patterns:
                for match in pattern.finditer(text):
                    numbers = tuple(int(g) for g in match.groups())
                    if numbers not in allowed:
                        stale.append(
                            f"{path.relative_to(REPO_ROOT)} quotes {what} "
                            f"{'/'.join(map(str, numbers))}, which no run of the "
                            f"committed harnesses produced"
                        )
        return stale

    def test_no_document_quotes_an_unmeasured_harvest_count(self) -> None:
        pairs = _harvest_pairs(_run(HARVEST))
        allowed = [
            # "N fit / M miss" is a PAIR summing to the population.
            (re.compile(r"(\d+) fits? / (\d+) miss"), pairs),
            # "N of T" is a fit against the population.
            (
                re.compile(r"fits? \*\*(\d+) of (\d+)\*\*"),
                {(fit, _harvest_population()) for fit, _ in pairs},
            ),
        ]
        stale = self._stale(allowed, "a harvest count")
        assert not stale, "\n  ".join(stale)

    def test_no_document_quotes_an_unmeasured_sweep_count(self) -> None:
        """The ``1,849`` / ``18,007`` class, in the shape documents use it in.

        Only checked where the sentence names the quantity, so the check cannot
        fire on an unrelated ``N of 64`` in the same document.
        """
        counts = _sweep_counts(_run(SWEEP)) | _sweep_counts(_run(SWEEP, "--wide"))
        pattern = re.compile(
            # "frost-date" and "frost date" both appear in the wild; the wording
            # drifted between the documents, and a pattern that matched only one
            # of them was silently inert on the other.
            r"(\d[\d,]*)\s*\((?:task,\s*frost[- ]date,\s*day\)|"
            r"(?:task, frost date, day) cases the GUI missed)"
        )
        stale: list[str] = []
        for path in _CORPUS:
            if path in _RETRACTION_RECORDERS:
                continue
            text = re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))
            for match in pattern.finditer(text):
                value = int(match.group(1).replace(",", ""))
                if value not in counts:
                    stale.append(
                        f"{path.relative_to(REPO_ROOT)} quotes {value} cases the "
                        f"GUI missed; the harnesses produce {sorted(counts)}"
                    )
        assert not stale, "\n  ".join(stale)
