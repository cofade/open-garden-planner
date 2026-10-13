"""One resolver for the frozen bundle's runtime distribution closure (AUD-051/AUD-055).

The third-party notices and the SBOM must describe the distributions the frozen
bundle actually carries. Rather than keeping a hand-typed list that silently
rots when a dependency is added, both the PyInstaller spec (which decides what
metadata to bundle) and ``scripts/generate_distribution_inventory.py`` (which
reads it back out of the built artifact) call this module.

The walk starts from the **manifest's** ``[project].dependencies`` and resolves
``Requires-Dist`` transitively against the installed build environment:

* anchoring on ``pyproject.toml`` rather than the project's own installed
  metadata keeps the result independent of a stale editable ``*.egg-info`` that
  can shadow the real metadata on ``sys.path`` (observed on a dev machine:
  ``src/open_garden_planner.egg-info`` reported version 0.1.0);
* a requirement gated behind an extra is included only when that extra was
  requested of the distribution by something else (for example
  ``pyjwt[crypto]`` pulls in ``cryptography``);
* platform/environment markers are evaluated in the build environment, so a
  Windows-only runtime dependency is included on Windows;
* a name that is not installed (optional or unreachable for this environment)
  is skipped, because the build cannot bundle metadata that does not exist.

The project's own distribution is excluded — it is not a third party. Only
``packaging`` (a PyInstaller build dependency) is needed at build time.
"""

from __future__ import annotations

import re
import tomllib
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

PROJECT_DISTRIBUTION = "open-garden-planner"
DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "pyproject.toml"


def canonicalize(name: str) -> str:
    """PEP 503 normalization: ``typing_extensions`` and ``typing-extensions`` are one name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def project_requirements(manifest: Path = DEFAULT_MANIFEST) -> list[str]:
    """The project's declared runtime requirements, straight from the manifest."""
    data = tomllib.loads(Path(manifest).read_text(encoding="utf-8"))
    return list(data["project"]["dependencies"])


def runtime_distribution_names(manifest: Path = DEFAULT_MANIFEST) -> list[str]:
    """Canonical names of the installed runtime closure, sorted, project excluded."""
    requested: dict[str, set[str]] = {}
    queue: list[tuple[str, frozenset[str]]] = []
    for raw in project_requirements(manifest):
        requirement = Requirement(raw)
        if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
            continue
        queue.append((requirement.name, frozenset(requirement.extras)))

    while queue:
        name, extras = queue.pop()
        key = canonicalize(name)
        previous = requested.get(key)
        if previous is not None and extras <= previous:
            continue
        requested.setdefault(key, set()).update(extras)
        try:
            dist = metadata.distribution(key)
        except metadata.PackageNotFoundError:
            continue
        for raw in dist.requires or []:
            requirement = Requirement(raw)
            wanted = False
            for extra in extras | {""}:
                if requirement.marker is None or requirement.marker.evaluate({"extra": extra}):
                    wanted = True
                    break
            if wanted:
                queue.append((requirement.name, frozenset(requirement.extras)))

    requested.pop(canonicalize(PROJECT_DISTRIBUTION), None)
    return sorted(requested)


def installed_version(name: str) -> str | None:
    try:
        return metadata.version(canonicalize(name))
    except metadata.PackageNotFoundError:
        return None
