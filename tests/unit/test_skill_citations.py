"""Pins the skill-library citation-resolver gate into the test battery (#336).

Mirrors ``tests/unit/test_agent_context_sync.py``: the real corpus must be
clean, plus synthetic ``tmp_path`` cases pin each failure mode the gate is
supposed to catch.
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_skill_citations import (
    KNOWN_EXCEPTIONS,
    REPO_ROOT,
    build_adr_pool,
    build_fr_pool,
    build_section_pool,
    check_adr_refs,
    check_file_line_refs,
    check_fr_refs,
    check_issue_refs,
    check_repo,
    check_section_refs,
    find_corpus_files,
)


def test_real_corpus_citations_all_resolve() -> None:
    assert check_repo(REPO_ROOT) == []


def test_no_exemption_is_dead(monkeypatch) -> None:
    """An exemption that no longer needs to exist is an unwatched open door
    (mirrors tests/unit/test_settings_chokepoint.py's guard of the same name).
    """
    import scripts.check_skill_citations as mod

    for rel_file, raw in KNOWN_EXCEPTIONS:
        path = REPO_ROOT / rel_file
        assert path.exists(), f"exempt file no longer exists: {rel_file}"
        assert raw in path.read_text(encoding="utf-8"), (
            f"{rel_file} no longer contains the exempted citation {raw!r} — "
            "drop its exemption"
        )

    monkeypatch.setattr(mod, "KNOWN_EXCEPTIONS", {})
    errors = mod.check_repo(REPO_ROOT)
    for rel_file, raw in KNOWN_EXCEPTIONS:
        assert any(rel_file in e and raw in e for e in errors), (
            f"removing the exemption for {rel_file}:{raw!r} produced no "
            "error — this exemption is no longer needed, drop it"
        )


def _write_corpus_file(root: Path, text: str) -> Path:
    skill_dir = root / ".claude" / "skills" / "example"
    skill_dir.mkdir(parents=True, exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_detects_nonexistent_section_reference(tmp_path: Path) -> None:
    _write_corpus_file(tmp_path, "See §8.99 for details.\n")

    errors = check_section_refs(
        tmp_path, find_corpus_files(tmp_path), build_section_pool(tmp_path, [])
    )

    assert any("8.99" in e and "section reference" in e for e in errors)


def test_section_reference_passes_when_heading_exists_anywhere(tmp_path: Path) -> None:
    path = _write_corpus_file(tmp_path, "## 8.99 A real heading\n\nSee §8.99.\n")

    errors = check_section_refs(
        tmp_path,
        find_corpus_files(tmp_path),
        build_section_pool(tmp_path, [path]),
    )

    assert errors == []


def test_detects_nonexistent_adr(tmp_path: Path) -> None:
    (tmp_path / "docs" / "09-architecture-decisions").mkdir(parents=True)
    (tmp_path / "docs" / "09-architecture-decisions" / "README.md").write_text(
        "## ADR-001: Real decision\n", encoding="utf-8"
    )
    _write_corpus_file(tmp_path, "Per ADR-099 this is required.\n")

    errors = check_adr_refs(
        tmp_path, find_corpus_files(tmp_path), build_adr_pool(tmp_path)
    )

    assert any("ADR-099" in e for e in errors)


def test_detects_nonexistent_adr_in_the_middle_of_a_slash_list(tmp_path: Path) -> None:
    """Regression: a repeated regex group only keeps its LAST match, so
    'ADR-001/999/002' silently dropped the middle number from .groups().
    """
    (tmp_path / "docs" / "09-architecture-decisions").mkdir(parents=True)
    (tmp_path / "docs" / "09-architecture-decisions" / "README.md").write_text(
        "## ADR-001: Real decision\n## ADR-002: Another\n", encoding="utf-8"
    )
    _write_corpus_file(tmp_path, "Rejected repeatedly (ADR-001/999/002).\n")

    errors = check_adr_refs(
        tmp_path, find_corpus_files(tmp_path), build_adr_pool(tmp_path)
    )

    assert any("ADR-999" in e for e in errors)


def test_real_adr_passes(tmp_path: Path) -> None:
    (tmp_path / "docs" / "09-architecture-decisions").mkdir(parents=True)
    (tmp_path / "docs" / "09-architecture-decisions" / "README.md").write_text(
        "## ADR-001: Real decision\n", encoding="utf-8"
    )
    _write_corpus_file(tmp_path, "Per ADR-001 this is required.\n")

    errors = check_adr_refs(
        tmp_path, find_corpus_files(tmp_path), build_adr_pool(tmp_path)
    )

    assert errors == []


def test_detects_nonexistent_fr(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "functional-requirements.md").write_text(
        "## FR-1: Real requirement\n- **FR-AGENT-01**: something\n",
        encoding="utf-8",
    )
    _write_corpus_file(tmp_path, "See FR-77 and FR-AGENT-99 for the contract.\n")

    errors = check_fr_refs(tmp_path, find_corpus_files(tmp_path), build_fr_pool(tmp_path))

    assert any("FR-77" in e for e in errors)
    assert any("FR-AGENT-99" in e for e in errors)


def test_real_fr_ids_pass(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs" / "functional-requirements.md").write_text(
        "## FR-1: Real requirement\n- **FR-AGENT-01**: something\n",
        encoding="utf-8",
    )
    _write_corpus_file(tmp_path, "See FR-1 and FR-AGENT-01 for the contract.\n")

    errors = check_fr_refs(tmp_path, find_corpus_files(tmp_path), build_fr_pool(tmp_path))

    assert errors == []


def test_file_line_citation_to_deleted_file_fails(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    _write_corpus_file(tmp_path, "See `nonexistent_module.py:10` for the fix.\n")

    errors = check_file_line_refs(tmp_path, find_corpus_files(tmp_path))

    assert any("does not exist under" in e for e in errors)


def test_file_line_citation_resolves_outside_src(tmp_path: Path) -> None:
    """Regression: the resolver used to search src/ only, so a citation to a
    real file under tests/ or scripts/ was reported as nonexistent.
    """
    tests_dir = tmp_path / "tests" / "unit"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_thing.py").write_text("def test_it():\n    pass\n" * 10, encoding="utf-8")
    _write_corpus_file(tmp_path, "See `tests/unit/test_thing.py:1` for the fixture.\n")

    errors = check_file_line_refs(tmp_path, find_corpus_files(tmp_path))

    assert errors == []


def test_file_line_citation_with_generic_symbol_needs_matching_literal(
    tmp_path: Path,
) -> None:
    """Regression: a generic, recurring name (like a one-line setter reused
    for several panels) must not pass just because *some* call to it exists
    in the window — the specific call the citation names (its smart_symbols
    argument) has to have actually existed somewhere nearby, not merely the
    function name in a call for an unrelated panel.
    """
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    lines = ["# padding\n"] * 20
    lines[4] = 'set_panel_visible("plant_details", True)\n'
    (src / "mod.py").write_text("".join(lines), encoding="utf-8")
    _write_corpus_file(
        tmp_path, 'See `pkg/mod.py:5` `set_panel_visible("smart_symbols", False)`.\n'
    )

    errors = check_file_line_refs(tmp_path, find_corpus_files(tmp_path))

    assert any("smart_symbols" in e for e in errors)


def test_file_line_citation_literal_must_be_NEAR_the_symbol_not_just_in_window(
    tmp_path: Path,
) -> None:
    """Stronger regression than the above: the literal genuinely exists
    somewhere in the 300-line window (so a naive "literal found anywhere in
    the window" check would wrongly pass) but nowhere near any occurrence of
    the symbol — only a call tied to a DIFFERENT literal is nearby. Proximity
    to the specific call, not mere co-membership in the window, is what must
    be required.
    """
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    lines = ["# padding\n"] * 400
    lines[4] = 'set_panel_visible("plant_details", True)\n'
    lines[199] = "# note: smart_symbols used to live here\n"
    (src / "mod.py").write_text("".join(lines), encoding="utf-8")
    _write_corpus_file(
        tmp_path, 'See `pkg/mod.py:5` `set_panel_visible("smart_symbols", False)`.\n'
    )

    errors = check_file_line_refs(tmp_path, find_corpus_files(tmp_path))

    assert any("smart_symbols" in e for e in errors)


def test_file_line_citation_extracts_call_name_not_receiver(tmp_path: Path) -> None:
    """Regression: symbol extraction used to take the leading identifier of
    the cited snippet, so `self._x.set_panel_visible(...)` checked for
    "self" — trivially present in every Python file — instead of the call
    actually being cited. No string literal in the snippet here, so the
    literal-proximity check (a separate safety net) can't mask the bug:
    this fails or passes purely on which identifier got extracted.
    """
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    lines = ["    self.value = 1\n"] * 20  # "self" on every line; no such method
    (src / "mod.py").write_text("".join(lines), encoding="utf-8")
    _write_corpus_file(
        tmp_path,
        "See `pkg/mod.py:5` `self._sidebar_controller.set_panel_visible(mode)`.\n",
    )

    errors = check_file_line_refs(tmp_path, find_corpus_files(tmp_path))

    assert any("set_panel_visible" in e for e in errors)


def test_file_line_citation_with_drifted_line_but_surviving_symbol_passes(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    lines = ["# padding\n"] * 500
    lines[299] = "def still_here():\n"
    (src / "mod.py").write_text("".join(lines), encoding="utf-8")
    # Cited line (100) is 200 lines from the symbol's real line (300) — real
    # drift (a function moved within its file), but within the tolerance
    # window, unlike the #336 case this gate actually caught (~1300 lines).
    _write_corpus_file(tmp_path, "See `pkg/mod.py:100` `still_here()`.\n")

    errors = check_file_line_refs(tmp_path, find_corpus_files(tmp_path))

    assert errors == []


def test_file_line_citation_whose_symbol_is_gone_fails(tmp_path: Path) -> None:
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "mod.py").write_text("x = 1\n" * 500, encoding="utf-8")
    _write_corpus_file(tmp_path, "See `pkg/mod.py:10` `removed_function()`.\n")

    errors = check_file_line_refs(tmp_path, find_corpus_files(tmp_path))

    assert any("removed_function" in e for e in errors)


def test_file_line_citation_past_end_of_file_fails(tmp_path: Path) -> None:
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "mod.py").write_text("x = 1\n", encoding="utf-8")
    _write_corpus_file(tmp_path, "See `pkg/mod.py:9999` for the fix.\n")

    errors = check_file_line_refs(tmp_path, find_corpus_files(tmp_path))

    assert any("out of range" in e for e in errors)


def _registry(tmp_path: Path, entries: dict) -> None:
    import json

    data_dir = tmp_path / "tests" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "issue_registry.json").write_text(
        json.dumps(entries), encoding="utf-8"
    )


def test_detects_unknown_issue_number(tmp_path: Path) -> None:
    _registry(tmp_path, {})
    _write_corpus_file(tmp_path, "Fixed in #99999.\n")

    from scripts.check_skill_citations import load_issue_registry

    errors = check_issue_refs(
        tmp_path, find_corpus_files(tmp_path), load_issue_registry(tmp_path)
    )

    assert any("does not match any known issue or PR" in e for e in errors)


def test_detects_pr_referenced_as_issue(tmp_path: Path) -> None:
    _registry(
        tmp_path,
        {"42": {"title": "Some PR", "state": "MERGED", "is_pr": True}},
    )
    _write_corpus_file(tmp_path, "See issue #42 for context.\n")

    from scripts.check_skill_citations import load_issue_registry

    errors = check_issue_refs(
        tmp_path, find_corpus_files(tmp_path), load_issue_registry(tmp_path)
    )

    assert any("is labeled an issue but #42 is a PR" in e for e in errors)


def test_detects_issue_referenced_as_pr(tmp_path: Path) -> None:
    _registry(
        tmp_path,
        {"42": {"title": "Some issue", "state": "OPEN", "is_pr": False}},
    )
    _write_corpus_file(tmp_path, "See PR #42 for context.\n")

    from scripts.check_skill_citations import load_issue_registry

    errors = check_issue_refs(
        tmp_path, find_corpus_files(tmp_path), load_issue_registry(tmp_path)
    )

    assert any("is labeled a PR but #42 is an issue" in e for e in errors)


def test_bare_issue_reference_does_not_require_open_state(tmp_path: Path) -> None:
    """A bare '#NNN' with no 'issue'/'PR' keyword only needs to exist — most
    citations in this corpus are historical references to long-closed bugs.
    """

    _registry(
        tmp_path,
        {"42": {"title": "Old closed bug", "state": "CLOSED", "is_pr": False}},
    )
    _write_corpus_file(tmp_path, "This was the exact #42 bug.\n")

    from scripts.check_skill_citations import load_issue_registry

    errors = check_issue_refs(
        tmp_path, find_corpus_files(tmp_path), load_issue_registry(tmp_path)
    )

    assert errors == []
