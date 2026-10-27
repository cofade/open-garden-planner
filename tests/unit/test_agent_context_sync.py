"""Regression tests for the Claude Code/Codex context parity gate."""

from pathlib import Path

from scripts.check_agent_context import _normalise_shared_text, check_repo

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Bytes the root instructions must leave unused out of the Codex project-doc budget.
#: The files are edited by every change (each one adds a pickup bullet), so this is a
#: real budget decision, not a zero: the pre-v1.30 pickup history was moved to
#: ``docs/agent-pickup-history.md`` on 2026-10-27 to buy the margin, and this floor is
#: what the next few dozen changes may spend before the oldest entries move again.
MIN_CONTEXT_HEADROOM_BYTES = 8192


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


def test_the_doc_budget_counts_the_bytes_on_disk(tmp_path: Path) -> None:
    """CRLF spends the budget, deliberately: the limit is on the file a reader loads.

    A byte-limited reader truncates the checkouts whose tail is past the limit, and a
    CRLF working copy (the Windows default here) is one byte per line larger than the
    LF blob CI checks out. Measuring the normalised text hid that: #444's batch landed
    with 5 bytes of headroom on Windows while the gate said OK. So the gate reads what
    ``stat`` reports, and the document keeps real headroom instead
    (``test_the_checked_in_documents_keep_headroom``).
    """
    root = _minimal_context_repo(tmp_path)
    text = "shared instructions\n" * 4                      # 80 bytes as LF
    assert len(text.encode("utf-8")) == 80
    crlf = text.replace("\n", "\r\n")                        # 84 bytes on disk
    assert len(crlf.encode("utf-8")) == 84
    (root / "CLAUDE.md").write_bytes(crlf.encode("utf-8"))
    (root / "AGENTS.md").write_bytes(crlf.encode("utf-8"))
    (root / ".codex" / "config.toml").write_text(
        "project_doc_max_bytes = 80\n", encoding="utf-8"
    )
    assert any("project-doc budget" in error for error in check_repo(root))

    (root / ".codex" / "config.toml").write_text(
        "project_doc_max_bytes = 84\n", encoding="utf-8"
    )
    assert not any("project-doc budget" in error for error in check_repo(root))


def test_the_checked_in_documents_keep_headroom() -> None:
    """The root instructions must not ride the limit (#444's batch hit 5 bytes).

    Both files are edited by every change ("add a pickup bullet"), and a gate that only
    reports "over budget" once is discovered at the worst moment — on the dev box, with
    a document whose tail a reader may already be truncating. So a real margin is
    required, not zero.
    """
    from scripts.check_agent_context import _configured_doc_max_bytes

    max_bytes = _configured_doc_max_bytes(REPO_ROOT, [])
    assert max_bytes is not None
    for name in ("AGENTS.md", "CLAUDE.md"):
        size = (REPO_ROOT / name).stat().st_size
        assert size <= max_bytes - MIN_CONTEXT_HEADROOM_BYTES, (
            f"{name} is {size} bytes against a {max_bytes}-byte budget: keep at least "
            f"{MIN_CONTEXT_HEADROOM_BYTES} bytes of headroom (see the module docstring "
            "of this test for why)"
        )


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
