"""Record the exact toolchain a build/package run used (AUD-049).

Writes a small machine-readable file so a release can be tied to reproducible
tool versions instead of "whatever the runner had that day". Read-only with
respect to the repository: it only writes the requested ``--output`` path.

Usage:
    python scripts/emit_build_evidence.py --output dist/build-evidence.json \
        --commit "$GITHUB_SHA" --run-id "$GITHUB_RUN_ID" --require-complete

Exit codes: 0 = evidence written; 2 = a required tool version is missing (with
``--require-complete``) or the file could not be written.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _distribution_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def _uv_version() -> str | None:
    for command in (["uv", "--version"], [sys.executable, "-m", "uv", "--version"]):
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError):
            continue
        parts = result.stdout.split()
        if len(parts) >= 2:
            return parts[1]
        text = result.stdout.strip()
        if text:
            return text
    return None


def _nsis_executable(explicit: str | None = None) -> str | None:
    if explicit and Path(explicit).exists():
        return explicit
    found = shutil.which("makensis")
    if found:
        return found
    for candidate in (
        Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
        Path(r"C:\Program Files\NSIS\makensis.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _nsis_version(explicit: str | None = None) -> str | None:
    makensis = _nsis_executable(explicit)
    if not makensis:
        return None
    try:
        result = subprocess.run(
            [makensis, "/VERSION"], capture_output=True, text=True, check=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (result.stdout or result.stderr).strip() or None


def collect(
    *,
    commit: str | None = None,
    run_id: str | None = None,
    nsis_path: str | None = None,
    uv: str | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": commit,
        "run_id": run_id,
        "python": {
            "version": platform.python_version(),
            "full": sys.version.replace("\n", " "),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": platform.platform(),
        "distribution_versions": {
            "pyinstaller": _distribution_version("pyinstaller"),
            "pyinstaller-hooks-contrib": _distribution_version("pyinstaller-hooks-contrib"),
            "setuptools": _distribution_version("setuptools"),
            "wheel": _distribution_version("wheel"),
        },
        "uv": uv if uv is not None else _uv_version(),
        "nsis": _nsis_version(nsis_path),
    }


def missing_required(evidence: dict[str, object]) -> list[str]:
    """Return the required fields that could not be established."""
    missing: list[str] = []
    for name, value in dict(evidence["distribution_versions"]).items():  # type: ignore[arg-type]
        if not value:
            missing.append(f"distribution_versions.{name}")
    if not evidence.get("uv"):
        missing.append("uv")
    if not evidence.get("nsis"):
        missing.append("nsis")
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--nsis-path", default=None)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail (exit 2) when a required tool version cannot be established.",
    )
    args = parser.parse_args(argv)

    evidence = collect(commit=args.commit, run_id=args.run_id, nsis_path=args.nsis_path)
    missing = missing_required(evidence)
    evidence["complete"] = not missing

    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"Cannot write build evidence to {args.output}: {exc}", file=sys.stderr)
        return 2

    print(f"Build evidence written to {args.output}")
    if missing:
        print("Missing tool versions: " + ", ".join(missing), file=sys.stderr)
        if args.require_complete:
            print("Build evidence is incomplete", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
