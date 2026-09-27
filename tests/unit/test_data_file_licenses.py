"""Unit tests for the data-file licence gate (US-G1, issue #311).

Every JSON file under ``resources/data/`` must carry a ``license`` and
``attribution`` object before it merges — same rule as the asset sets
(``ogp-asset-forge``: no provenance, no merge). This test enforces that
gate.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "src" / "open_garden_planner" / "resources" / "data"

# Files that must have license + attribution
REQUIRED_FILES = [
    "plant_species.json",
    "companion_planting.json",
    "seed_viability.json",
    "amendments.json",
]


class TestDataFileLicenses:
    def test_all_required_files_exist(self) -> None:
        for filename in REQUIRED_FILES:
            assert (DATA_DIR / filename).exists(), f"Missing data file: {filename}"

    def test_all_required_files_have_license(self) -> None:
        for filename in REQUIRED_FILES:
            data = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
            assert "license" in data, f"{filename} missing 'license' key"
            license_obj = data["license"]
            assert isinstance(license_obj, dict), f"{filename} 'license' is not a dict"
            assert "spdx" in license_obj, f"{filename} license missing 'spdx'"
            assert "name" in license_obj, f"{filename} license missing 'name'"
            assert "url" in license_obj, f"{filename} license missing 'url'"

    def test_all_required_files_have_attribution(self) -> None:
        for filename in REQUIRED_FILES:
            data = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
            assert "attribution" in data, f"{filename} missing 'attribution' key"
            attr = data["attribution"]
            assert isinstance(attr, dict), f"{filename} 'attribution' is not a dict"
            assert "sources" in attr, f"{filename} attribution missing 'sources'"
            assert isinstance(attr["sources"], list), f"{filename} sources is not a list"
            assert len(attr["sources"]) > 0, f"{filename} sources is empty"

    def test_license_spdx_is_cc_by_sa(self) -> None:
        for filename in REQUIRED_FILES:
            data = json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))
            spdx = data["license"]["spdx"]
            assert spdx == "CC-BY-SA-4.0", f"{filename} has unexpected SPDX: {spdx}"

    def test_provenance_md_exists(self) -> None:
        assert (DATA_DIR / "PROVENANCE.md").exists(), "Missing PROVENANCE.md"
