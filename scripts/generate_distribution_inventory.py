"""Generate third-party notices + a CycloneDX SBOM from the FROZEN bundle (AUD-051/055).

Reads the ``.dist-info`` metadata that ``installer/ogp.spec`` bundles into the
PyInstaller output, so the inventory describes the executable artifact rather
than a developer's environment or a historical count.

Modes
-----
* default: write ``THIRD_PARTY_NOTICES.md`` and ``ogp-sbom.cdx.json``.
* ``--check``: rebuild in memory and verify
    - every runtime distribution from the live build environment appears in the
      bundle (``installer/runtime_closure.py`` — one resolver, not a second one);
    - the on-disk SBOM matches the bundle's metadata;
    - with ``--lock pylock.toml``: every bundled distribution's version equals
      the locked version.

Exit codes: 0 = ok, 2 = failure (missing metadata, unknown license, drift).
Fails closed: a distribution with no discoverable license is an error naming
that distribution, never an "UNKNOWN" row in a shipped notice.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import tomllib
from datetime import UTC, datetime
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1

#: Distributions whose metadata carries no usable license declaration. Entries
#: normally carry ``spdx`` (the verified SPDX id, checked against the upstream
#: project's own LICENSE file); an optional ``text`` replaces the license text
#: taken from the wheel. Do not add one without checking upstream.
LICENSE_OVERRIDES: dict[str, dict[str, str]] = {
    # The Qt runtime wheels (:PyQt6-Qt6, :PyQt6-3D-Qt6, :PyQt6-WebEngine-Qt6)
    # declare the prose "LGPL v3" in their metadata; LGPL-3.0-only is that
    # license's SPDX identifier. The license text below is the wheel's own.
    "pyqt6-qt6": {"spdx": "LGPL-3.0-only"},
    "pyqt6-3d-qt6": {"spdx": "LGPL-3.0-only"},
    "pyqt6-webengine-qt6": {"spdx": "LGPL-3.0-only"},
}

#: Distributions whose code reaches the frozen bundle through PyInstaller
#: machinery rather than a ``Requires-Dist`` edge, with the verified reason.
#: They are expected in the bundle, reported as ordinary SBOM components (so
#: their license text is published), and exempt from the lock-identity check
#: because they are not lock packages. If PyInstaller stops bundling one, the
#: check fails loudly rather than under-reporting.
VENDORED_BUNDLE_EXTRAS = {
    "importlib-metadata": (
        "PyInstaller's hook-importlib_metadata aliases the setuptools-vendored copy "
        "(setuptools._vendor.importlib_metadata, Apache-2.0) when a bundled dependency "
        "imports the backport; that code is distributed with the executable."
    ),
}


def _load_runtime_closure():
    path = ROOT / "installer" / "runtime_closure.py"
    spec = importlib.util.spec_from_file_location("ogp_runtime_closure", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime_closure = _load_runtime_closure()

CLASSIFIER_PREFIX = "License :: OSI Approved :: "
CLASSIFIER_SPDX = {
    "MIT License": "MIT",
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "ISC License (ISCL)": "ISC",
    "Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "zlib/libpng License": "Zlib",
}
SHORT_LICENSE_RE = re.compile(r"^[A-Za-z0-9.\-+()/ ,]{1,80}$")
LICENSE_FILE_NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE", "LICENSE.txt", "LICENSE.md")

#: Metadata sentinels that mean "no license was declared". They match
#: ``SHORT_LICENSE_RE`` (and ``UNKNOWN`` matches ``SPDX_ID_RE``), so without an
#: explicit rejection the generator would ship ``License: UNKNOWN`` — the exact
#: outcome the fail-closed contract exists to prevent.
LICENSE_SENTINELS = frozenset(
    {"unknown", "none", "noassertion", "unknown or other", "n/a", "na", "not specified"}
)


class InventoryError(RuntimeError):
    """A distribution could not be described honestly."""


def _parse_metadata(path: Path) -> dict[str, list[str]]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    message = Parser().parsestr(raw)
    result: dict[str, list[str]] = {}
    for key in ("Name", "Version", "License", "License-Expression", "Home-page", "License-File"):
        values = message.get_all(key) or []
        result[key] = [v.strip() for v in values if v and v.strip()]
    result["Classifier"] = list(message.get_all("Classifier") or [])
    project_urls = message.get_all("Project-URL") or []
    result["Project-URL"] = [u.strip() for u in project_urls if u and u.strip()]
    return result


def _license_files(dist_info: Path) -> list[Path]:
    found: list[Path] = []
    for candidate in dist_info.rglob("*"):
        if not candidate.is_file():
            continue
        upper = candidate.name.upper()
        if any(upper.startswith(name) for name in LICENSE_FILE_NAMES):
            found.append(candidate)
    return sorted(found)


def _home_page(meta: dict[str, list[str]]) -> str | None:
    for entry in meta.get("Project-URL", []):
        label, _, url = entry.partition(",")
        if url.strip() and label.strip().lower() in {"homepage", "home", "source", "repository"}:
            return url.strip()
    if meta.get("Home-page"):
        return meta["Home-page"][0]
    for entry in meta.get("Project-URL", []):
        _, _, url = entry.partition(",")
        if url.strip():
            return url.strip()
    return None


def describe(dist_info: Path) -> dict[str, object]:
    """Turn one ``*.dist-info`` directory into a notice/SBOM record."""
    meta = _parse_metadata(dist_info / "METADATA")
    name = (meta.get("Name") or [dist_info.name.rsplit("-", 1)[0]])[0]
    version = (meta.get("Version") or ["?"])[0]

    expression = (meta.get("License-Expression") or [None])[0]
    spdx = expression
    if not spdx:
        for classifier in meta.get("Classifier", []):
            if classifier.startswith(CLASSIFIER_PREFIX):
                mapped = CLASSIFIER_SPDX.get(classifier[len(CLASSIFIER_PREFIX):].strip())
                if mapped:
                    spdx = mapped
                    break
    if not spdx:
        raw_license = (meta.get("License") or [""])[0]
        if raw_license and SHORT_LICENSE_RE.match(raw_license):
            spdx = raw_license

    texts = []
    for path in _license_files(dist_info):
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            texts.append(text)
    if not texts:
        long_license = (meta.get("License") or [""])[0]
        if len(long_license) > 80:
            texts.append(long_license.strip())

    override = LICENSE_OVERRIDES.get(runtime_closure.canonicalize(name))
    if override:
        spdx = override.get("spdx") or spdx
        if override.get("text"):
            texts = [override["text"]]

    if spdx and spdx.strip().lower() in LICENSE_SENTINELS:
        spdx = None
    if not spdx and not texts:
        raise InventoryError(
            f"{name} {version}: no license declaration or license text found in "
            f"{dist_info.name} — add a verified entry to LICENSE_OVERRIDES"
        )
    return {
        "name": name,
        "canonical_name": runtime_closure.canonicalize(name),
        "version": version,
        "spdx": spdx,
        "license_texts": texts,
        "home_page": _home_page(meta),
        "dist_info": dist_info.name,
    }


def bundle_dist_infos(bundle: Path) -> list[Path]:
    return sorted(p for p in bundle.rglob("*.dist-info") if (p / "METADATA").is_file())


def collect_records(bundle: Path) -> list[dict[str, object]]:
    records = []
    for dist_info in bundle_dist_infos(bundle):
        record = describe(dist_info)
        if record["canonical_name"] == runtime_closure.canonicalize(
            runtime_closure.PROJECT_DISTRIBUTION
        ):
            continue
        records.append(record)
    records.sort(key=lambda r: str(r["canonical_name"]))
    return records


def render_notices(records: list[dict[str, object]], app_version: str) -> str:
    lines = [
        "# Third-party notices",
        "",
        f"Open Garden Planner {app_version} bundles the third-party Python",
        "distributions listed below. Each entry names the distribution, its version,",
        "its license and, where the distribution ships one, the license text.",
        "",
        "This file is generated from the built executable's own metadata by",
        "`scripts/generate_distribution_inventory.py`; do not edit it by hand.",
        "",
    ]
    for record in records:
        lines.append(f"## {record['name']} {record['version']}")
        lines.append("")
        lines.append(f"- License: {record['spdx'] or 'see text below'}")
        if record["home_page"]:
            lines.append(f"- Project: {record['home_page']}")
        lines.append("")
        for text in record["license_texts"]:
            lines.append("```")
            lines.append(str(text))
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


SPDX_ID_RE = re.compile(r"^[A-Za-z0-9.\-+]+$")
SPDX_EXPRESSION_RE = re.compile(
    r"^[A-Za-z0-9.\-+()]+(?: (?:AND|OR|WITH) [A-Za-z0-9.\-+()]+)+$"
)


def _license_entry(spdx: str | None) -> dict[str, object] | None:
    """CycloneDX license entry: ``id`` for an identifier, ``expression`` for a
    compound SPDX expression, ``name`` for prose that is not SPDX."""
    if not spdx:
        return None
    if SPDX_ID_RE.match(spdx):
        return {"license": {"id": spdx}}
    if SPDX_EXPRESSION_RE.match(spdx):
        return {"expression": spdx}
    return {"license": {"name": spdx}}


def render_sbom(records: list[dict[str, object]], app_version: str) -> dict[str, object]:
    components = []
    for record in records:
        component: dict[str, object] = {
            "type": "library",
            "name": record["canonical_name"],
            "version": record["version"],
            "purl": f"pkg:pypi/{record['canonical_name']}@{record['version']}",
        }
        licenses = _license_entry(record["spdx"])  # type: ignore[arg-type]
        if licenses:
            component["licenses"] = [licenses]
        if record["home_page"]:
            component["externalReferences"] = [{"type": "website", "url": record["home_page"]}]
        components.append(component)
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
            "component": {
                "type": "application",
                "name": "open-garden-planner",
                "version": app_version,
                "licenses": [{"license": {"id": "GPL-3.0-or-later"}}],
            },
            "tools": [
                {
                    "vendor": "open-garden-planner",
                    "name": "generate_distribution_inventory",
                    "version": str(SCHEMA_VERSION),
                }
            ],
        },
        "components": components,
    }


def _lock_versions(lock: Path) -> dict[str, str]:
    data = tomllib.loads(lock.read_text(encoding="utf-8"))
    return {
        runtime_closure.canonicalize(package["name"]): package["version"]
        for package in data.get("packages", [])
    }


def _app_version() -> str:
    manifest = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(manifest["project"]["version"])


def _expected_from_environment() -> set[str]:
    """The spec's closure for this build environment, plus hook-bundled extras.

    ``--check`` therefore proves "the spec bundled every distribution this
    environment declares" plus "the on-disk SBOM matches the bundle". It does
    **not** prove the environment matches the lock: that direction is covered
    per-version by the ``--lock`` comparison, and closure ⊆ lock by
    ``tests/integration/test_distribution_inventory_pipeline.py``.
    """
    names = {
        runtime_closure.canonicalize(n) for n in runtime_closure.runtime_distribution_names()
    }
    return names | set(VENDORED_BUNDLE_EXTRAS)


def _check(
    output_dir: Path, lock: Path | None, records: list[dict[str, object]]
) -> list[str]:
    problems: list[str] = []
    bundled = {str(r["canonical_name"]) for r in records}
    expected = _expected_from_environment()
    missing = sorted(expected - bundled)
    unexpected = sorted(bundled - expected)
    if missing:
        problems.append(
            "bundle carries no metadata for runtime distributions: " + ", ".join(missing)
        )
    if unexpected:
        problems.append(
            "bundle carries metadata for non-runtime distributions: " + ", ".join(unexpected)
        )

    sbom_path = output_dir / "ogp-sbom.cdx.json"
    notices_path = output_dir / "THIRD_PARTY_NOTICES.md"
    if not sbom_path.is_file():
        problems.append(f"{sbom_path} does not exist")
    else:
        on_disk = json.loads(sbom_path.read_text(encoding="utf-8"))
        on_disk_components = on_disk.get("components", [])
        fresh = render_sbom(records, _app_version())["components"]
        if on_disk_components != fresh:
            problems.append("ogp-sbom.cdx.json does not match the bundle's metadata")
    if not notices_path.is_file():
        problems.append(f"{notices_path} does not exist")

    if lock is not None:
        locked = _lock_versions(lock)
        for record in records:
            name = str(record["canonical_name"])
            if name in VENDORED_BUNDLE_EXTRAS:
                continue
            if name not in locked:
                problems.append(f"{name} is in the bundle but not in {lock.name}")
            elif locked[name] != record["version"]:
                problems.append(
                    f"{name}: bundle has {record['version']}, lock has {locked[name]} "
                    "— build from the locked environment (uv sync --locked)"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=ROOT / "dist" / "OpenGardenPlanner")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--lock", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    bundle = args.bundle.resolve()
    if not bundle.is_dir():
        print(f"Frozen bundle not found: {bundle}", file=sys.stderr)
        return 2

    try:
        records = collect_records(bundle)
    except InventoryError as exc:
        print(f"Distribution inventory failed: {exc}", file=sys.stderr)
        return 2
    if not records:
        print(
            f"No bundled .dist-info metadata under {bundle} — the spec change that "
            "bundles runtime metadata is missing from this build",
            file=sys.stderr,
        )
        return 2

    problems = (
        _check(args.output_dir.resolve(), args.lock, records) if args.check else []
    )

    if not args.check:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "THIRD_PARTY_NOTICES.md").write_text(
            render_notices(records, _app_version()), encoding="utf-8"
        )
        (args.output_dir / "ogp-sbom.cdx.json").write_text(
            json.dumps(render_sbom(records, _app_version()), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote notices and {len(records)} SBOM components to {args.output_dir}")

    if problems:
        for problem in problems:
            print(f"CHECK: {problem}", file=sys.stderr)
        return 2
    if args.check:
        print(f"Inventory check passed for {len(records)} bundled distributions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
