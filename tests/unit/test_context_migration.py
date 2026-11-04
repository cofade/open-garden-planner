"""A12: moved knowledge remains present, byte-checked and reachable in both trees."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_all_migrated_fragments_remain_present_and_indexed():
    data = json.loads((ROOT / "quality/context-migration.json").read_text(encoding="utf-8"))
    for entry, record in data["skills"].items():
        index = (ROOT / entry).read_text(encoding="utf-8")
        if "debug-verbose" in entry:
            index += (ROOT / entry).parent.joinpath("references/case-index.md").read_text(encoding="utf-8")
        assert len(record["original_sha256"]) == 64
        for fragment in record["fragments"]:
            path = ROOT / fragment["path"]
            text = path.read_text(encoding="utf-8")
            assert hashlib.sha256(text.encode("utf-8")).hexdigest() == fragment["current_sha256"]
            assert path.name in index
            assert text.strip(), path


def test_the_clone_receives_every_migrated_reference():
    """A working-copy parity pass must not hide files excluded by gitignore."""
    tracked = set(subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT, encoding="utf-8"
    ).split("\0"))
    data = json.loads((ROOT / "quality/context-migration.json").read_text(encoding="utf-8"))
    for record in data["skills"].values():
        for fragment in record["fragments"]:
            assert fragment["path"] in tracked, fragment["path"]


def test_routing_descriptions_have_discriminating_scope_signatures():
    """Contrast task scopes; this does not claim to simulate an agent's router."""
    descriptions = {}
    for skill in (ROOT / ".agents/skills").glob("*/SKILL.md"):
        descriptions[skill.parent.name] = skill.read_text(encoding="utf-8").split("---", 2)[1].lower()
    cases = [
        ("Fix an existing solar shadow", "ogp-3d-sunshade-campaign", ("maintaining", "solar")),
        ("Explain why a regression happens", "ogp-research-methodology", ("investigation", "hypothesis")),
        ("Choose the next research direction", "ogp-research-frontier", ("next big direction", "frontier")),
        ("Deliver a cluster of related issues", "deliver-package", ("cluster", "draft pr")),
    ]
    for prompt, skill, words in cases:
        assert all(word in descriptions[skill] for word in words), (prompt, skill)
        for _other_prompt, competing, _other_words in cases:
            if competing != skill:
                assert not all(word in descriptions[competing] for word in words), (
                    prompt, skill, competing, "scope signature is ambiguous"
                )
    assert "shipped" in descriptions["ogp-3d-sunshade-campaign"]
