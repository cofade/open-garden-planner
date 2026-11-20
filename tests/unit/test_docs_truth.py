"""#976: the user-facing documents describe the product of today.

Three facts go stale quietly and cost a newcomer trust: a shipped feature called
"planned", a scope list that still excludes what the app does, and a launch checklist
presented as the current measure of success. This guard reads the documents a newcomer
meets first and fails when one of those statements comes back.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: The first documents a visitor or a new user reads.
USER_FACING = (
    "README.md",
    "docs/01-introduction-and-goals/README.md",
    "docs/wiki/Home.md",
    "docs/wiki/Roadmap.md",
    "docs/wiki/Installation.md",
)

#: Statements that were true at v1.0 and are false now (Phase 14 and 17 shipped).
STALE_CLAIMS = (
    "3D visualization (planned",
    "Sun/shadow simulation (planned",
    "3D visualization (planned for future versions)",
    "Sun/shadow simulation (planned for future versions)",
    "MVP (v1.0) Success Criteria",
    "10+ GitHub stars (indicator of interest)",
)


def _text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_no_user_facing_document_calls_a_shipped_feature_planned() -> None:
    for document in USER_FACING:
        text = _text(document)
        for claim in STALE_CLAIMS:
            assert claim not in text, f"{document} still says {claim!r}"


def test_the_introduction_does_not_present_the_v1_launch_checklist() -> None:
    text = _text("docs/01-introduction-and-goals/README.md")
    assert "Out of Scope" in text, "the section still exists, now as today's limits"
    out_of_scope = text.split("## 1.4 Out of Scope", 1)[1].split("## 1.5", 1)[0]
    bullets = [
        line for line in out_of_scope.splitlines() if line.startswith("- ")
    ]
    assert bullets, "the out-of-scope section lists its limits"
    # The bold lead names the limit itself ("**Mobile applications.**", "**Terrain.**").
    leads = [line.split("**")[1].lower() for line in bullets if "**" in line]
    assert leads, "each limit has a lead"
    for shipped in ("3d", "sun", "shadow"):
        assert all(shipped not in lead for lead in leads), (
            f"{shipped!r} is shipped, so no limit may be led by it"
        )


def test_the_readme_points_at_the_issue_trace_and_its_claim_label() -> None:
    """An issue marked ``claimed`` is not free work; the contribution text says so."""
    text = _text("README.md")
    assert "`claimed`" in text, "README explains the claim label"
    assert "not labelled `claimed`" in text
