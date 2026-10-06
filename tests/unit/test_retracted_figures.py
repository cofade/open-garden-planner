"""Stop a retracted measurement from living on in the documents (#415/#416).

Four review rounds each found a documented figure that the code contradicts.
Round 5 found the worst instance: the commit that ADDED
`scripts/measure_harvest_offsets.py` and wrote "those numbers matched no harness
and were wrong" into that script's docstring left the identical wrong numbers
standing in ADR-049, in the §11.4 bullet it had corrected, and in the roadmap —
in ADR-049's case asserting the *opposite* conclusion in the same paragraph.

A guard that lives in a script and not in the documents does not propagate. This
is the guard that lives in the suite, so the fifth round is not needed.

Two halves:

* **Retraction.** Every figure that was measured, found wrong and corrected is
  listed here. If one reappears in a document or a test docstring, the commit
  that reintroduced it did not know it had been retracted.
* **Agreement.** The surviving figures are re-derived by running the committed
  harnesses and compared with what the documents claim, so a figure that was
  never retracted but has since drifted is also caught.

The two files that quote a retraction *in order to record it* are exempted, and
the exemption is explicit rather than a broad path filter — a blanket "ignore
scripts/" would also hide a real reintroduction.
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

#: Files allowed to NAME a retracted figure, because they record the retraction.
#: Listed by path, not by directory: a broad exemption would also hide a real
#: reintroduction somewhere else under tests/.
_RETACTION_RECORDERS = (
    REPO_ROOT / "tests" / "unit" / "test_harvest_offset_semantics.py",
    REPO_ROOT / "scripts" / "measure_harvest_offsets.py",
    # This file quotes the retracted figures in RETRACTED, so it must exempt
    # itself — by exact path, for the same reason as the other two.
    REPO_ROOT / "tests" / "unit" / "test_retracted_figures.py",
)

#: figure -> what it was, and what replaced it. The key is the retracted form.
RETRACTED = {
    "1 of 64": "38 of 64 (frost-relative) — see scripts/measure_harvest_offsets.py",
    "10 of 54": "45 of 64 (planting-relative) — see scripts/measure_harvest_offsets.py",
    "1 fits / 63 miss": "38 fit / 26 miss",
    "10 fits / 54 miss": "45 fit / 19 miss",
    "2,669": "18,007 (all 118 species, every day) — see "
             "scripts/measure_task_window_sweep.py --wide",
    "2 months early": "garlic's harvest window lands ~3 months LATE (October)",
    "all 118 species on every day gives all 118 species": (
        "a botched find/replace of the same sentence; see ADR-029"
    ),
    "so the data is not irreconcilable": (
        "the correct conclusion; the retracted claim was that it COULD NOT be "
        "reconciled. Listed so the negative form is caught if reintroduced."
    ),
}


def _retracted_occurrences() -> list[str]:
    hits: list[str] = []
    for path in _CORPUS:
        if path in _RETACTION_RECORDERS:
            continue
        text = path.read_text(encoding="utf-8")
        for figure, replacement in RETRACTED.items():
            if figure == "so the data is not irreconcilable":
                continue
            for match in re.finditer(re.escape(figure), text, re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                hits.append(
                    f"{path.relative_to(REPO_ROOT)}:{line} quotes the retracted "
                    f"figure {figure!r}; the measured value is {replacement}"
                )
    return hits


class TestNoRetractedFigureSurvives:
    def test_no_document_quotes_a_retracted_measurement(self) -> None:
        hits = _retracted_occurrences()
        assert not hits, (
            "a measurement that was measured, found wrong and corrected is being "
            "quoted again:\n  " + "\n  ".join(hits)
        )

    def test_the_corpus_is_not_empty(self) -> None:
        """A guard that reads nothing passes; make that visible."""
        assert len(_CORPUS) > 20, len(_CORPUS)

    def test_the_retraction_recorders_still_record_the_retraction(self) -> None:
        """The exemption must not rot into a blanket silence."""
        for path in _RETACTION_RECORDERS:
            assert path.exists(), f"exempted file is gone: {path}"
            text = path.read_text(encoding="utf-8")
            assert any(
                phrase in text
                for phrase in ("were wrong", "were retracted", "the conclusion was wrong")
            ), (
                f"{path.relative_to(REPO_ROOT)} is exempt from the retraction "
                "check but no longer records the retraction"
            )


class TestDocumentedFiguresMatchTheCommittedHarnesses:
    """The second half: re-derive, then compare with what the documents claim.

    Catches a figure that was never retracted but has drifted since — which is
    how "2,669" and "1 of 64" survived in the first place: nobody re-ran
    anything, they just believed the prose.
    """

    @staticmethod
    def _run(script: str, *args: str) -> str:
        proc = subprocess.run(
            [sys.executable, script, *args],
            cwd=REPO_ROOT, capture_output=True, text=True,
            env={"PATH": "", "PYTHONUTF8": "1", "SYSTEMROOT": r"C:\Windows",
                 "QT_QPA_PLATFORM": "offscreen"},
        )
        assert proc.returncode == 0, f"{script} failed:\n{proc.stdout}\n{proc.stderr}"
        return proc.stdout

    def test_the_task_window_sweep_reproduces_both_quoted_harnesses(self) -> None:
        default = self._run("scripts/measure_task_window_sweep.py")
        wide = self._run("scripts/measure_task_window_sweep.py", "--wide")

        assert "1849" in default and "0" in default, default
        assert "18007" in wide, wide
        # The invariant, not just the numbers: nothing missed, nothing added.
        for name, output in (("default", default), ("--wide", wide)):
            missed_after = _figure(output, "missed by the GUI now")
            surplus = _figure(output, "listed now but not by the agent")
            assert missed_after == 0, f"{name} harness missed {missed_after}"
            assert surplus == 0, f"{name} harness added {surplus} surplus tasks"

    def test_the_harvest_sweep_reproduces_the_quoted_figures(self) -> None:
        output = self._run("scripts/measure_harvest_offsets.py")
        assert "38 fit / 26 miss" in output, output
        assert "45 fit / 19 miss" in output, output
        assert re.search(r"species that fit neither reading:\s*11\b", output), output

    #: The measured fit/miss pairs, from scripts/measure_harvest_offsets.py.
    MEASURED_PAIRS = {(38, 26), (45, 19)}
    #: The measured fit/population counts, i.e. "N of 64".
    MEASURED_OF_TOTAL = {(38, 64), (45, 64)}

    def test_the_documents_quote_the_measured_harvest_figures(self) -> None:
        """If a document quotes a harvest count, it must be one a harness produces.

        Two shapes are in use and they mean different things, which an earlier
        version of this check conflated: ``N fit / M miss`` reports a PAIR of
        counts summing to the population, while ``N of T`` reports a fit against
        the population. Reading the second number of the first form as the total
        made the check reject the correct figure it was written to protect.
        """
        stale: list[str] = []
        pair = re.compile(r"(\d+) fits? / (\d+) miss")
        of_total = re.compile(r"fits? \*\*(\d+) of (\d+)\*\*")
        for path in _CORPUS:
            if path in _RETACTION_RECORDERS:
                continue
            text = path.read_text(encoding="utf-8")
            for pattern, allowed in (
                (pair, self.MEASURED_PAIRS), (of_total, self.MEASURED_OF_TOTAL)
            ):
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    numbers = tuple(int(g) for g in match.groups())
                    if numbers not in allowed:
                        stale.append(
                            f"{path.relative_to(REPO_ROOT)}:{line} claims "
                            f"{numbers[0]}/{numbers[1]}, which no harness produces"
                        )
        assert not stale, "\n  ".join(stale)


def _figure(output: str, label: str) -> int:
    match = re.search(rf"{re.escape(label)}\s*:\s*(\d+)", output)
    assert match is not None, f"{label!r} not in output:\n{output}"
    return int(match.group(1))
