"""Check that Claude Code and Codex receive the same project context."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

HOST_ONLY_SKILLS = frozenset({"agent-tools", "find-skills", "skill-creator"})
"""Skills supplied by the host rather than maintained by this repository."""

def _normalise_line_endings(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _normalise_shared_text(value: str) -> str:
    """Remove only the platform-specific path names from shared instructions."""

    value = _normalise_line_endings(value)
    replacements = (
        (".claude/skills", "<shared-skills>"),
        (".agents/skills", "<shared-skills>"),
        (".claude/agents/senior-reviewer.md", "<reviewer-agent-file>"),
        (".codex/agents/senior-reviewer.toml", "<reviewer-agent-file>"),
        (".claude/agents", "<reviewer-agents>"),
        (".codex/agents", "<reviewer-agents>"),
        ("CLAUDE.md", "<root-instructions>"),
        ("AGENTS.md", "<root-instructions>"),
    )
    for source, replacement in replacements:
        value = value.replace(source, replacement)
    # Native clients use their own product names in commands, footers, and
    # explanatory examples. Those bindings are not project-context drift.
    value = re.sub(r"claude|codex", "<agent>", value, flags=re.IGNORECASE)
    value = value.replace("the <agent> Code footer", "the agent footer")
    value = value.replace("the <agent> footer", "the agent footer")
    value = value.replace(
        "preferred — <agent> Code drops configured headers on tool calls",
        "preferred — the client drops configured headers on tool calls",
    )
    value = value.replace(
        "preferred — <agent> drops configured headers on tool calls",
        "preferred — the client drops configured headers on tool calls",
    )
    return value


def _files_under(path: Path) -> set[str]:
    if not path.is_dir():
        return set()
    return {
        item.relative_to(path).as_posix()
        for item in path.rglob("*")
        if item.is_file()
    }


def _skill_dirs(path: Path) -> set[str]:
    if not path.is_dir():
        return set()
    return {
        item.name
        for item in path.iterdir()
        if item.is_dir() and item.name not in HOST_ONLY_SKILLS
    }


def _frontmatter_value(text: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _claude_agent_parts(path: Path) -> tuple[str, str, str] | None:
    text = path.read_text(encoding="utf-8")
    sections = text.split("---", 2)
    if len(sections) != 3:
        return None
    name = _frontmatter_value(sections[1], "name")
    description = _frontmatter_value(sections[1], "description")
    if name is None or description is None:
        return None
    return name, description, sections[2].strip()


def _configured_doc_max_bytes(root: Path, errors: list[str]) -> int | None:
    config_path = root / ".codex" / "config.toml"
    if not config_path.is_file():
        errors.append("missing .codex/config.toml")
        return None
    try:
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"invalid .codex/config.toml: {exc}")
        return None
    value = config.get("project_doc_max_bytes")
    if not isinstance(value, int) or value <= 0:
        errors.append(".codex/config.toml has no positive project_doc_max_bytes")
        return None
    return value


def _check_root_docs(root: Path, errors: list[str]) -> None:
    claude = root / "CLAUDE.md"
    codex = root / "AGENTS.md"
    if not claude.is_file():
        errors.append("missing CLAUDE.md")
    if not codex.is_file():
        errors.append("missing AGENTS.md")
    if (
        claude.is_file()
        and codex.is_file()
        and _normalise_line_endings(claude.read_text(encoding="utf-8"))
        != _normalise_line_endings(codex.read_text(encoding="utf-8"))
    ):
        errors.append("CLAUDE.md and AGENTS.md differ")
    max_bytes = _configured_doc_max_bytes(root, errors)
    if codex.is_file() and max_bytes is not None and codex.stat().st_size > max_bytes:
        errors.append(
            f"AGENTS.md exceeds the Codex project-doc budget of {max_bytes} bytes"
        )


def _check_skills(root: Path, errors: list[str]) -> None:
    claude_root = root / ".claude" / "skills"
    codex_root = root / ".agents" / "skills"
    claude_dirs = _skill_dirs(claude_root)
    codex_dirs = _skill_dirs(codex_root)

    for name in sorted(claude_dirs - codex_dirs):
        errors.append(f"skill missing from .agents/skills: {name}")
    for name in sorted(codex_dirs - claude_dirs):
        errors.append(f"skill missing from .claude/skills: {name}")

    for name in sorted(claude_dirs & codex_dirs):
        claude_skill = claude_root / name
        codex_skill = codex_root / name
        for skill_root, label in ((claude_skill, ".claude/skills"), (codex_skill, ".agents/skills")):
            if not (skill_root / "SKILL.md").is_file():
                errors.append(f"skill entry point missing from {label}: {name}/SKILL.md")
        claude_files = _files_under(claude_skill)
        codex_files = _files_under(codex_skill)
        for relative in sorted(claude_files - codex_files):
            errors.append(f"skill file missing from .agents/skills: {name}/{relative}")
        for relative in sorted(codex_files - claude_files):
            errors.append(f"skill file missing from .claude/skills: {name}/{relative}")
        for relative in sorted(claude_files & codex_files):
            left = _normalise_shared_text((claude_skill / relative).read_text(encoding="utf-8"))
            right = _normalise_shared_text((codex_skill / relative).read_text(encoding="utf-8"))
            if left != right:
                errors.append(f"skill content differs: {name}/{relative}")


def _check_agents(root: Path, errors: list[str]) -> None:
    claude_root = root / ".claude" / "agents"
    codex_root = root / ".codex" / "agents"
    claude_files = {path.stem: path for path in claude_root.glob("*.md")}
    codex_files = {path.stem: path for path in codex_root.glob("*.toml")}

    for name in sorted(claude_files.keys() - codex_files.keys()):
        errors.append(f"agent missing from .codex/agents: {name}")
    for name in sorted(codex_files.keys() - claude_files.keys()):
        errors.append(f"agent missing from .claude/agents: {name}")

    for name in sorted(claude_files.keys() & codex_files.keys()):
        claude_parts = _claude_agent_parts(claude_files[name])
        if claude_parts is None:
            errors.append(f"invalid Claude agent frontmatter: {claude_files[name]}")
            continue
        try:
            codex = tomllib.loads(codex_files[name].read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"invalid Codex agent TOML: {codex_files[name]} ({exc})")
            continue

        claude_name, claude_description, claude_instructions = claude_parts
        if codex.get("name") != claude_name:
            errors.append(f"agent name differs: {name}")
        if codex.get("description") != claude_description:
            errors.append(f"agent description differs: {name}")
        codex_instructions = codex.get("developer_instructions")
        if not isinstance(codex_instructions, str):
            errors.append(f"agent instructions missing: {name}")
        elif _normalise_shared_text(claude_instructions) != _normalise_shared_text(
            codex_instructions
        ):
            errors.append(f"agent instructions differ: {name}")


def check_repo(root: Path) -> list[str]:
    """Return all parity errors for ``root`` without modifying the repository."""

    errors: list[str] = []
    _check_root_docs(root, errors)
    _check_skills(root, errors)
    _check_agents(root, errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the parent of scripts/)",
    )
    args = parser.parse_args(argv)
    errors = check_repo(args.root.resolve())
    if errors:
        print("Agent context parity check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Agent context parity check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
