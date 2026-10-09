"""Prepare mechanical release-version sync; default is a dry run (#399/#404)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.check_dependency_lock import EXPORT_ARGS

ROOT = Path(__file__).resolve().parents[1]
SYNC_FILES = ("pyproject.toml", "src/open_garden_planner/__init__.py", "uv.lock", "pylock.toml")


def third_party_packages(content: bytes) -> list[str]:
    data = tomllib.loads(content.decode("utf-8"))
    packages = data.get("package")
    if not isinstance(packages, list) or not packages:
        raise ValueError("Lock has no package records")
    local = [p for p in packages if p.get("name") == "open-garden-planner"]
    if len(local) != 1 or local[0].get("source") != {"editable": "."}:
        raise ValueError("Lock must contain exactly one editable project record")
    return sorted(json.dumps(p, sort_keys=True) for p in packages
                  if p.get("name") != "open-garden-planner")


def replace_manifest_version(content: str, version: str) -> str:
    lines = content.splitlines(keepends=True)
    in_project = False
    replaced = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith("["):
            in_project = line.strip() == "[project]"
        if in_project and re.match(r"^version\s*=", line):
            updated, count = re.subn(r'^(version\s*=\s*)"[^"]+"',
                                    lambda m: m.group(1) + f'"{version}"', line)
            replaced += count
            lines[i] = updated
    if replaced != 1:
        raise ValueError("Manifest must have exactly one project version declaration")
    return "".join(lines)


def replace_project_lock_version(content: str, version: str) -> str:
    """Seed only editable-project metadata before uv validates the lock offline.

    A changed project version otherwise triggers universal dependency resolution,
    which needs registry metadata for platforms not installed in the active env.
    uv remains responsible for checking all other manifest/lock relationships.
    """
    third_party_packages(content.encode("utf-8"))  # validates the editable record
    blocks = list(re.finditer(r"^\[\[package\]\]\s*$", content, re.M))
    for index, start in enumerate(blocks):
        end = blocks[index + 1].start() if index + 1 < len(blocks) else len(content)
        block = content[start.start():end]
        if tomllib.loads(block)["package"][0]["name"] != "open-garden-planner":
            continue
        updated, count = re.subn(r'^(version\s*=\s*)"[^"]+"',
                                lambda m: m.group(1) + f'"{version}"', block, flags=re.M)
        if count != 1:
            raise ValueError("Editable lock record must have exactly one version")
        return content[:start.start()] + updated + content[end:]
    raise ValueError("Editable lock record is missing")


def prepare(root: Path, tag: str, source_pr: int, uv: str) -> dict[str, bytes]:
    match = re.fullmatch(r"v(\d+\.\d+\.\d+)", tag)
    if match is None or source_pr <= 0:
        raise ValueError("Expected vMAJOR.MINOR.PATCH and a positive source PR")
    version = match.group(1)
    originals = {name: (root / name).read_bytes() for name in SYNC_FILES}
    manifest = originals["pyproject.toml"].decode("utf-8")
    current = tomllib.loads(manifest)["project"]["version"]
    if tuple(map(int, version.split("."))) < tuple(map(int, current.split("."))):
        raise ValueError("Refusing to sync to an older version")
    init, count = re.subn(
        r'^(__version__\s*=\s*)"[^"]+"',
        lambda m: m.group(1) + f'"{version}"',
        originals[SYNC_FILES[1]].decode("utf-8"), flags=re.M,
    )
    if count != 1:
        raise ValueError("Source must have exactly one __version__ declaration")
    with tempfile.TemporaryDirectory(prefix="ogp-version-sync-") as tmp:
        stage = Path(tmp)
        for name, content in originals.items():
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (stage / "README.md").write_text("Temporary lock metadata validation\n", encoding="utf-8")
        (stage / "pyproject.toml").write_text(replace_manifest_version(manifest, version),
                                              encoding="utf-8", newline="")
        (stage / SYNC_FILES[1]).write_text(init, encoding="utf-8", newline="")
        (stage / "uv.lock").write_text(
            replace_project_lock_version(originals["uv.lock"].decode("utf-8"), version),
            encoding="utf-8", newline="",
        )
        subprocess.run([uv, "lock", "--offline", "--python", sys.executable], cwd=stage,
                       check=True, capture_output=True, text=True, encoding="utf-8", timeout=180)
        subprocess.run([uv, *EXPORT_ARGS, "--offline", "--output-file", "pylock.toml"],
                       cwd=stage, check=True, capture_output=True, text=True,
                       encoding="utf-8", timeout=180)
        prepared = {name: (stage / name).read_bytes() for name in SYNC_FILES}
    if third_party_packages(prepared["uv.lock"]) != third_party_packages(originals["uv.lock"]):
        raise ValueError("Version sync changed a third-party package record")
    return prepared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-pr", type=int, required=True)
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        prepared = prepare(root, args.tag, args.source_pr, args.uv)
        originals = {name: (root / name).read_bytes() for name in SYNC_FILES}
        changed = [name for name in SYNC_FILES if prepared[name] != originals[name]]
        if args.apply:
            try:
                for name in changed:
                    (root / name).write_bytes(prepared[name])
            except OSError:
                for name in changed:
                    (root / name).write_bytes(originals[name])
                raise
        result: dict[str, Any] = {
            "tag": args.tag, "changed_files": changed, "applied": args.apply,
            "already_synced": not changed,
            "branch": f"chore/sync-{args.tag}-pr-{args.source_pr}",
            "commit_message": f"chore: sync version to {args.tag} after PR #{args.source_pr}",
        }
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f"Version sync preparation failed: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
