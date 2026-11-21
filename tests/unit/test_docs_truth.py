"""#976: the user-facing documents describe the product of today.

Three facts go stale quietly and cost a newcomer trust: a shipped feature called
"planned", a scope list that still excludes what the app does, and a launch checklist
presented as the current measure of success. This guard reads the documents a newcomer
meets first and fails when one of those statements comes back.
"""

from __future__ import annotations

import json
import re
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


def _backticked_codes(text: str) -> set[str]:
    """The two-letter locale codes written as ``code`` in a sentence."""
    return set(re.findall(r"`([a-z]{2})`", text))


def _sentence_around(text: str, needle: str) -> str:
    """The line carrying *needle*, plus the one before it for a wrapped sentence."""
    lines = text.splitlines()
    index = next(i for i, line in enumerate(lines) if needle in line)
    return "\n".join(lines[max(0, index - 1) : index + 1])


_LOCALE_NAMES = {
    "en": "English",
    "de": "German",
    "es": "Spanish",
    "fr": "French",
    "ru": "Russian",
}


def test_the_accessibility_statement_names_every_shipped_ui_locale() -> None:
    """#987: the public statement a newcomer reads must not lag behind the app."""
    from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES

    sentence = _sentence_around(_text("ACCESSIBILITY.md"), "Application text")
    for code in SUPPORTED_LANGUAGES:
        assert _LOCALE_NAMES[code] in sentence, code


def test_the_quality_tree_names_every_shipped_ui_locale() -> None:
    """#987: the tree must not lag behind SUPPORTED_LANGUAGES."""
    from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES

    line = _sentence_around(_text("docs/10-quality-requirements/README.md"), "Multilingual")
    assert _backticked_codes(line) == set(SUPPORTED_LANGUAGES)


def test_the_website_catalog_docs_name_every_shipped_site_locale() -> None:
    """#987: §5 and §7 describe the download-stats site's own catalogs."""
    catalogs = json.loads(
        (ROOT / "scripts" / "download_stats_web" / "messages.json").read_text(
            encoding="utf-8"
        )
    )
    for document, needle in (
        ("docs/05-building-block-view/README.md", "website controls"),
        ("docs/07-deployment-view/README.md", "messages.json"),
    ):
        sentence = _sentence_around(_text(document), needle)
        assert _backticked_codes(sentence) == set(catalogs), document
