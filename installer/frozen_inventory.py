"""Map actual PyInstaller inputs to their wheel metadata, including vendored copies.

RECORD ownership, rather than import names or Requires-Dist, is the authority.
Nested dist-info records override their containing wheel's RECORD entries. This
preserves both packaging 26.0 vendored by setuptools and installed packaging 26.2,
for example. The emitted manifest also records the complete PYZ module set so the
inventory checker can reconcile it with the executable it is about to publish.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from importlib import metadata
from pathlib import Path

from packaging.utils import canonicalize_name

MANIFEST_NAME = "ogp-collected-distributions.json"


def _key(path: Path) -> str:
    return str(path.resolve()).casefold()


def distribution_index(distributions: Iterable[metadata.Distribution] | None = None) -> tuple[
    dict[str, str], dict[str, tuple[metadata.Distribution, dict[str, str] | None]]
]:
    """Index installed and nested vendored RECORDs by physical collected file."""
    installed = list(metadata.distributions() if distributions is None else distributions)
    owners = {}
    details = {}
    nested = []
    for dist in installed:
        info = Path(dist._path)  # importlib.metadata's filesystem distribution
        if info.suffix != ".dist-info":
            continue
        parent = {"name": dist.metadata["Name"], "version": dist.version}
        details[_key(info)] = (dist, None)
        for entry in dist.files or []:
            path = Path(dist.locate_file(entry))
            owners[_key(path)] = _key(info)
            if path.name == "METADATA" and path.parent.suffix == ".dist-info" and path.parent != info:
                nested.append((path.parent, parent))
    for info, parent in nested:
        dist = metadata.PathDistribution(info)
        details[_key(info)] = (dist, parent)
        if not dist.files:
            raise RuntimeError(f"Vendored metadata has no RECORD: {info}")
        for entry in dist.files:
            owners[_key(Path(dist.locate_file(entry)))] = _key(info)
    return owners, details


def collected_metadata(
    pure: Iterable[tuple[str, str, str]],
    binaries: Iterable[tuple[str, str, str]],
    datas: Iterable[tuple[str, str, str]],
    *,
    required_names: Iterable[str] = (),
    distributions: Iterable[metadata.Distribution] | None = None,
    scripts: Iterable[tuple[str, str, str]] = (),
) -> tuple[list[tuple[str, str, str]], dict]:
    """Return extra DATA tuples and an auditable manifest for this Analysis.

    Code/resource files under a distribution root must have a RECORD owner;
    otherwise the build refuses an inventory it cannot establish. Python's own
    stdlib, the project and OS DLLs are outside third-party wheel attribution.
    """
    pure = list(pure)
    owners, details = distribution_index(distributions)
    roots = {Path(dist._path).parent.resolve() for dist, _parent in details.values()}
    selected = set()
    by_name = {}
    for key, (dist, parent) in details.items():
        if parent is None:
            by_name[canonicalize_name(dist.metadata["Name"])] = key
    for name in required_names:
        if name not in by_name:
            raise RuntimeError(f"Required distribution has no wheel metadata: {name}")
        selected.add(by_name[name])

    input_owners = {"module_owners": {}, "script_owners": {}, "file_owners": {}}
    rows = [("module_owners", row) for row in pure]
    rows += [("script_owners", row) for row in scripts]
    rows += [("file_owners", row) for row in [*binaries, *datas]]
    for category, (dest, source, _kind) in rows:
        if not source or source == "-":
            continue
        path = Path(source).resolve()
        owner = owners.get(_key(path))
        if owner:
            selected.add(owner)
            input_owners[category][dest] = owner
        elif path.is_file() and any(path.is_relative_to(root) for root in roots):
            # Shared namespace __init__ files may be synthesized by PyInstaller,
            # but a physical wheel file without ownership must never disappear.
            raise RuntimeError(f"Collected third-party file has no RECORD owner: {path}")

    additions = []
    records = []
    destinations = {}
    for key in sorted(selected):
        dist, parent = details[key]
        info = Path(dist._path)
        # Namespace + identity keeps distinct vendored and installed versions.
        destination = (
            info.name if parent is None else f"ogp-vendored/{parent['name']}/{info.name}"
        )
        record = {
            "name": dist.metadata["Name"], "version": dist.version,
            "metadata_path": destination, "container": parent,
        }
        destinations[key] = destination
        records.append(record)
        for path in sorted(info.rglob("*")):
            if path.is_file():
                additions.append((f"{destination}/{path.relative_to(info).as_posix()}",
                                  str(path), "DATA"))
    manifest = {
        "schema_version": 1,
        "distributions": records,
        "python_modules": sorted(row[0] for row in pure),
        **{category: {dest: destinations[owner] for dest, owner in mapping.items()}
           for category, mapping in input_owners.items()},
    }
    return additions, manifest


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
