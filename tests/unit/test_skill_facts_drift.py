"""#398 — skill prose must not contradict the repository it describes.

Agent skills are loaded *before* an agent touches CI, the Agent API or an ADR, so
a stale statement in them is acted on as fact. The audit found four that the code
contradicted: the CI job count ("Three parallel jobs" while `ci.yml` had four),
a second copy of the same error in the QA skill, "no token auth on the loopback
Agent API" (superseded for writes by US-D2.0/ADR-036), and an ADR range written
as "ADR-001…ADR-034" while the file carried ADR-046.

`scripts/check_skill_citations.py` resolves identifiers (§N.M, ADR-0NN,
path:line) but is structurally blind to **counts and negations** — "no auth",
"three jobs" — because those are prose, not citations. This file is the drift
guard for exactly that blind spot: it derives the facts from the real sources and
compares them with the prose.

Each check below failed on `84ead2e` before the #398 corrections.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_TREES = (REPO_ROOT / ".claude" / "skills", REPO_ROOT / ".agents" / "skills")


def _skill_text(rel: str) -> str:
    """Read a skill from both trees and assert they agree before asserting content.

    A per-tree read would let one copy rot unnoticed; the project owns the two
    trees in lockstep (`scripts/check_agent_context.py`), so the content
    assertions below are made against both.
    """
    return "\n".join((tree / rel).read_text(encoding="utf-8") for tree in SKILL_TREES)


def _ci_job_names() -> set[str]:
    """Job names declared by the ``jobs:`` block of ci.yml."""
    text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    in_jobs = False
    names: set[str] = set()
    for line in text.splitlines():
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if in_jobs:
            match = re.match(r"^ {2}([A-Za-z0-9_-]+):\s*$", line)
            if match:
                names.add(match.group(1))
            elif line and not line.startswith(" ") and not line.startswith("#"):
                break
    return names


class TestCiJobCount:
    def test_ci_job_names_are_found(self) -> None:
        """Guard the parser itself: an empty parse would make every check vacuous."""
        jobs = _ci_job_names()
        assert {"lint", "test", "security"} <= jobs, jobs
        assert "push" not in jobs, "'push:' is a trigger, not a job"

    @pytest.mark.parametrize(
        "rel",
        [
            "ogp-change-control/SKILL.md",
            "ogp-validation-and-qa/SKILL.md",
        ],
    )
    def test_skill_job_count_claims_match_ci_yml(self, rel: str) -> None:
        """Any "<N> (parallel )?jobs" claim must equal the real job count.

        Matches the phrasing the audit found stale, in both the word-number form
        ("Three parallel jobs") and the digit form ("4 jobs").
        """
        text = _skill_text(rel)
        expected = len(_ci_job_names())
        words = {
            "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        claims: list[int] = []
        for match in re.finditer(
            r"\b(two|three|four|five|six|seven|eight|nine|ten|\d+)\s+(?:parallel\s+)?jobs\b",
            text,
            re.IGNORECASE,
        ):
            token = match.group(1).lower()
            claims.append(int(token) if token.isdigit() else words[token])
        # A skill that makes no such claim is not wrong; assert only if it does.
        for claim in claims:
            assert claim == expected, (
                f"{rel} says '{claim} jobs' but ci.yml defines {expected} "
                f"({sorted(_ci_job_names())})"
            )

    def test_no_skill_claims_ci_has_only_three_jobs(self) -> None:
        """The exact stale sentence from the audit, as a regression guard."""
        for rel in ("ogp-change-control/SKILL.md", "ogp-validation-and-qa/SKILL.md"):
            text = _skill_text(rel)
            assert "only lint/test/security jobs" not in text, (
                f"{rel} still claims ci.yml has only the three pre-2026-08 jobs"
            )


class TestAgentApiAuthClaim:
    def test_failure_archaeology_marks_token_auth_as_shipped(self) -> None:
        """Reads are still loopback trust, so the correction must stay precise."""
        text = _skill_text("ogp-failure-archaeology/SKILL.md")
        assert "**no auth**" not in text, (
            "ogp-failure-archaeology still states the loopback Agent API has "
            "no auth; US-D2.0 shipped the bearer-token gate for writes (ADR-036)"
        )
        assert "ADR-036" in text, "the corrected entry must cite ADR-036"

    def test_correction_states_that_reads_remain_ungated(self) -> None:
        """Over-correcting into "everything is authenticated" is also wrong.

        Asserted positively (the correction must name the read path) rather than
        by banning a phrase, because the corrected entry legitimately quotes
        that overclaim in order to warn against it.
        """
        text = _skill_text("ogp-failure-archaeology/SKILL.md").lower()
        assert "reads" in text and "loopback" in text, (
            "the #398 correction must keep reads explicitly unauthenticated"
        )
        assert "challenge" in text or "still open" in text, (
            "the correction must mark the read path as a remaining open question"
        )


class TestAdrRangeClaim:
    @staticmethod
    def _real_adr_count() -> int:
        adr_file = REPO_ROOT / "docs" / "09-architecture-decisions" / "README.md"
        return len(
            re.findall(r"^## ADR-\d{3}", adr_file.read_text(encoding="utf-8"), re.M)
        )

    def test_architecture_contract_does_not_pin_a_closed_adr_range(self) -> None:
        """A hardcoded range is the defect; the fix is to not write one.

        Scoped to the glossary line that *declares* the ADR index — the corrected
        text quotes the old stale range inside its own warning, so a whole-file
        scan would flag the warning. (Measured: the audit reported 46 ADRs;
        docs/09 actually carries 48 — ADR-047 and ADR-048 landed after it. Any
        pinned number is stale the next time an ADR is accepted.)
        """
        text = _skill_text("ogp-architecture-contract/SKILL.md")
        declaration = next(
            line for line in text.splitlines()
            if "docs/09-architecture-decisions/README.md` (" in line
        )
        pinned = re.search(r"ADR-0\d\d\D+ADR-0\d\d", declaration)
        assert pinned is None, (
            f"the ADR-index declaration pins a closed range ({pinned.group(0)}); "
            "state no count — it is stale the moment an ADR is accepted"
        )
        assert "ADR-001" in declaration, "the glossary must still point at ADR-001"

    def test_the_real_adr_count_is_what_the_guard_reads(self) -> None:
        """Guard the guard: the count the tests compare against must be real."""
        assert self._real_adr_count() >= 46, (
            "docs/09 ADR count unexpectedly low — the §N.M heading form may "
            "have changed and this guard would pass vacuously"
        )


class TestSkillTreesStayIdentical:
    @pytest.mark.parametrize(
        "rel",
        [
            "ogp-change-control/SKILL.md",
            "ogp-validation-and-qa/SKILL.md",
            "ogp-failure-archaeology/SKILL.md",
            "ogp-architecture-contract/SKILL.md",
        ],
    )
    def test_both_copies_are_byte_identical(self, rel: str) -> None:
        claude = (SKILL_TREES[0] / rel).read_bytes()
        agents = (SKILL_TREES[1] / rel).read_bytes()
        assert claude == agents, f"{rel} differs between .claude and .agents"


class TestDependencyPinsMatchPyproject:
    """#398's premise generalises: skill prose must not contradict the repo.

    #396 raised the ``mcp`` floor to 1.23 and left two skills quoting 1.12 — the
    exact failure #398 was opened for, reintroduced by the fix. A version pin is
    a countable fact, so it is drift-guarded the same way the CI job count is:
    derive it from ``pyproject.toml`` and compare, across EVERY skill rather than
    a hand-picked list (the hand-picked list is what let the two slip through).
    """

    #: Runtime dependencies whose pins a skill may legitimately quote.
    _PINNED = ("mcp", "numpy", "pyclipper", "ezdxf", "uvicorn", "starlette", "pydantic")

    def _pyproject_pins(self) -> dict[str, str]:
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        pins: dict[str, str] = {}
        for name in self._PINNED:
            match = re.search(rf'"{re.escape(name)}([<>=\d.,*]*)"', text)
            if match:
                pins[name] = f"{name}{match.group(1)}"
        return pins

    def test_pins_were_found(self) -> None:
        """Guard the parser: an empty result would make every check vacuous."""
        pins = self._pyproject_pins()
        assert pins, "no dependency pins found in pyproject.toml"
        assert "mcp" in pins

    def test_no_skill_quotes_a_stale_version_pin(self) -> None:
        """Any ``<name>>=X.Y`` in a skill must match pyproject exactly."""
        pins = self._pyproject_pins()
        stale: list[str] = []
        for tree in SKILL_TREES:
            for path in sorted(tree.rglob("SKILL.md")):
                text = path.read_text(encoding="utf-8")
                for name, actual in pins.items():
                    for match in re.finditer(
                        rf"`?{re.escape(name)}([<>]=[\d.,*]+)`,?", text
                    ):
                        quoted = f"{name}{match.group(1)}"
                        if quoted != actual:
                            stale.append(
                                f"{path.relative_to(REPO_ROOT)}: quotes {quoted!r}, "
                                f"pyproject says {actual!r}"
                            )
        assert not stale, "stale dependency pins in the skill library:\n  " + "\n  ".join(stale)

    def test_the_mcp_floor_is_at_least_1_23(self) -> None:
        """The DNS-rebinding guard's floor, asserted once, in one place."""
        pins = self._pyproject_pins()
        match = re.search(r"mcp>=(\d+)\.(\d+)", pins["mcp"])
        assert match is not None, pins["mcp"]
        assert (int(match.group(1)), int(match.group(2))) >= (1, 23)
