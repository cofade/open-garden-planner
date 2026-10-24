"""Compare the build environment with the locked dependency set (#538).

The local frozen-build recipe used to bundle whatever the developer's virtual
environment happened to contain. Removing a dependency from ``uv.lock`` does not
uninstall it, so a machine that once held the retired 3D wheels kept shipping
their DLLs and QML module in every locally built exe long after Phase 17 L1.10
removed them from the project. CI builds from the lock and was never affected;
the local gate was.

This module is the one place that answers "which installed distributions does
``pylock.toml`` not pin?". Both the PyInstaller spec (a warning at the start of
every build) and the local build script use it. The warnings are advisory;
``--strict`` turns them into a failed check for a caller that wants a gate.

Only distributions the lock does not list are reported. A package in the lock
but missing from this environment is not an error here: platform-gated
requirements (``macholib`` on Windows, for example) are legitimately absent,
and PyInstaller reports a genuinely missing runtime import itself.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import re
import sys
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO

from packaging.markers import Marker

PROJECT_DISTRIBUTION = "open-garden-planner"
DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "pylock.toml"

#: Tools a developer environment may carry without them being part of the
#: application's locked set. They are skipped only when the lock does not pin
#: them: ``pip``, ``setuptools`` and ``wheel`` ARE locked here (the build group),
#: and their versions reach ``dist/build-evidence.json``, so a stale one is a
#: real mismatch — exactly the advisory case that failed CI in #571.
BUILD_TOOL_ALLOWLIST = frozenset({"pip", "setuptools", "wheel", "uv"})


class _Distribution(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def metadata(self) -> dict[str, str]: ...


def canonicalize(name: str) -> str:
    """PEP 503 normalization: ``typing_extensions`` and ``typing-extensions`` are one name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_distributions(lock_path: Path = DEFAULT_LOCK) -> dict[str, str]:
    """Canonical name → locked version for every package in the PEP 751 lock."""
    data = tomllib.loads(Path(lock_path).read_text(encoding="utf-8"))
    packages = data.get("packages")
    if not isinstance(packages, list):
        raise ValueError(f"{lock_path} has no packages list")
    locked: dict[str, str] = {}
    for package in packages:
        if not isinstance(package, dict) or "name" not in package:
            continue
        marker = package.get("marker")
        if marker and not Marker(str(marker)).evaluate():
            continue
        locked[canonicalize(str(package["name"]))] = str(package.get("version", ""))
    if not locked:
        raise ValueError(f"{lock_path} lists no packages")
    return locked


def locked_distribution_names(lock_path: Path = DEFAULT_LOCK) -> set[str]:
    """Canonical names of every package in the PEP 751 lock."""
    return set(locked_distributions(lock_path))


@dataclass(frozen=True, slots=True)
class EnvironmentProblem:
    """One installed distribution that does not match the lock.

    ``expected`` is None when the lock does not list the package at all; a
    string means the package is listed but at a different version.
    """

    name: str
    installed: str
    expected: str | None


def environment_problems(
    lock_path: Path = DEFAULT_LOCK,
    *,
    installed: Iterable[_Distribution] | None = None,
) -> list[EnvironmentProblem]:
    """Installed distributions the lock omits or pins at another version.

    The project itself is ignored, and so is a packaging tool in
    :data:`BUILD_TOOL_ALLOWLIST` only while the lock does not pin it (``uv``
    today; ``pip``/``setuptools``/``wheel`` are pinned and checked). ``installed``
    exists for tests; production reads
    :func:`importlib.metadata.distributions`.
    """
    locked = locked_distributions(lock_path)
    found: dict[str, str] = {}
    for distribution in installed if installed is not None else importlib.metadata.distributions():
        raw_name = distribution.metadata.get("Name")
        if not raw_name:
            continue
        name = canonicalize(raw_name)
        if name == canonicalize(PROJECT_DISTRIBUTION) or (
            name in BUILD_TOOL_ALLOWLIST and name not in locked
        ):
            continue
        found[name] = distribution.version
    problems: list[EnvironmentProblem] = []
    for name, version in sorted(found.items()):
        expected = locked.get(name)
        if expected is None:
            problems.append(EnvironmentProblem(name, version, None))
        elif version != expected:
            problems.append(EnvironmentProblem(name, version, expected))
    return problems


def _check(
    lock_path: Path,
    *,
    installed: Iterable[_Distribution] | None = None,
) -> tuple[list[EnvironmentProblem], str | None]:
    try:
        return environment_problems(lock_path, installed=installed), None
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        return [], str(exc)


def warn_if_unpinned(
    lock_path: Path = DEFAULT_LOCK,
    *,
    stream: TextIO | None = None,
    installed: Iterable[_Distribution] | None = None,
) -> list[EnvironmentProblem]:
    """Print a clear warning for every installed distribution that differs from the lock.

    Returns the problems so a caller (or a test) can assert what was reported. A
    missing or malformed lock file is a warning here, not a crash: the build
    should still start, and the message says why the check could not run.
    ``main --strict`` treats that same condition as a failed gate (exit 2).
    """
    if stream is None:
        stream = sys.stderr
    problems, error = _check(lock_path, installed=installed)
    if error is not None:
        print(
            f"WARNING: cannot compare the build environment with {lock_path.name}: {error}",
            file=stream,
        )
        return []
    if not problems:
        return []
    print(
        "WARNING: the build environment differs from "
        f"{Path(lock_path).name}:",
        file=stream,
    )
    for problem in problems:
        if problem.expected is None:
            print(f"  {problem.name}=={problem.installed} (not in the lock)", file=stream)
        else:
            print(
                f"  {problem.name}=={problem.installed} "
                f"(lock pins {problem.expected})",
                file=stream,
            )
    print(
        "Rebuild after `uv sync --locked --all-extras --group build` with "
        "UV_PROJECT_ENVIRONMENT=venv (PowerShell: "
        "$env:UV_PROJECT_ENVIRONMENT='venv') if any of these is a runtime "
        "package; PyInstaller can bundle its files even when the application "
        "does not import it.",
        file=stream,
    )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 on a version mismatch, 2 when the lock cannot be read",
    )
    args = parser.parse_args(argv)
    problems, error = _check(args.lock)
    if error is not None:
        print(
            f"Build environment check failed: cannot read {args.lock.name}: {error}",
            file=sys.stderr,
        )
        return 2 if args.strict else 0
    if not problems:
        print(f"Build environment matches {args.lock.name}")
        return 0
    warn_if_unpinned(args.lock)
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
