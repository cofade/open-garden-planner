"""Regression tests for the Claude Code/Codex context parity gate."""

from pathlib import Path

from scripts.check_agent_context import _normalise_shared_text, check_repo

REPO_ROOT = Path(__file__).resolve().parents[2]


def _minimal_context_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for path in (
        root / ".claude" / "skills" / "example",
        root / ".agents" / "skills" / "example",
        root / ".claude" / "agents",
        root / ".codex" / "agents",
    ):
        path.mkdir(parents=True, exist_ok=True)
    (root / "CLAUDE.md").write_text("shared instructions\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("shared instructions\n", encoding="utf-8")
    (root / ".codex" / "config.toml").write_text(
        "project_doc_max_bytes = 32768\n", encoding="utf-8"
    )
    skill = "---\nname: example\ndescription: Example\n---\nshared skill\n"
    (root / ".claude" / "skills" / "example" / "SKILL.md").write_text(
        skill, encoding="utf-8"
    )
    (root / ".agents" / "skills" / "example" / "SKILL.md").write_text(
        skill, encoding="utf-8"
    )
    (root / ".claude" / "agents" / "reviewer.md").write_text(
        "---\nname: reviewer\ndescription: Review\n---\ninstructions\n",
        encoding="utf-8",
    )
    (root / ".codex" / "agents" / "reviewer.toml").write_text(
        'name = "reviewer"\ndescription = "Review"\ndeveloper_instructions = "instructions"\n',
        encoding="utf-8",
    )
    return root


def test_platform_specific_agent_paths_normalise_to_the_same_contract() -> None:
    claude = "CLAUDE.md uses .claude/skills and .claude/agents."
    codex = "AGENTS.md uses .agents/skills and .codex/agents."

    assert _normalise_shared_text(claude) == _normalise_shared_text(codex)


def test_checked_in_context_is_in_parity() -> None:
    assert check_repo(REPO_ROOT) == []


def test_detects_missing_skill_entrypoint_and_doc_budget(tmp_path: Path) -> None:
    root = _minimal_context_repo(tmp_path)
    (root / ".agents" / "skills" / "example" / "SKILL.md").unlink()
    (root / "AGENTS.md").write_text("x" * 20, encoding="utf-8")
    (root / ".codex" / "config.toml").write_text(
        "project_doc_max_bytes = 10\n", encoding="utf-8"
    )

    errors = check_repo(root)

    assert any("skill entry point missing" in error for error in errors)
    assert any("project-doc budget" in error for error in errors)


def test_detects_skill_content_drift_and_stale_alias(tmp_path: Path) -> None:
    root = _minimal_context_repo(tmp_path)
    (root / ".agents" / "skills" / "example" / "SKILL.md").write_text(
        ".Codex/skills/example/SKILL.md\n", encoding="utf-8"
    )

    errors = check_repo(root)

    assert any("skill content differs" in error for error in errors)


def test_detects_invalid_native_agent_files(tmp_path: Path) -> None:
    root = _minimal_context_repo(tmp_path)
    (root / ".codex" / "agents" / "reviewer.toml").write_text(
        "developer_instructions = [\n", encoding="utf-8"
    )

    errors = check_repo(root)

    assert any("invalid Codex agent TOML" in error for error in errors)
