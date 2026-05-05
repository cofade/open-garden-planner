"""Amendment loader (US-12.10c).

Loads ``resources/data/amendments.json`` once at first access. The bundled
file is small (~12 entries), so eager validation is cheap and lets us crash
loud at startup rather than mid-dialog if a release ships a corrupted asset.
"""
from __future__ import annotations

import json
from pathlib import Path

from open_garden_planner.models.amendment import Amendment

_DATA_DIR = Path(__file__).parent.parent / "resources" / "data"
_AMENDMENTS_FILENAME = "amendments.json"


class AmendmentLoader:
    """Loads and caches the bundled amendments JSON.

    Pass ``path`` to override the data file (used by tests). Otherwise the
    bundled ``resources/data/amendments.json`` is read on first ``get_amendments``.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (_DATA_DIR / _AMENDMENTS_FILENAME)
        self._amendments: list[Amendment] | None = None

    def get_amendments(self) -> list[Amendment]:
        """Return the list of amendments, loading on first call."""
        if self._amendments is None:
            self._amendments = self._load()
        return self._amendments

    def _load(self) -> list[Amendment]:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Failed to read amendments file {self._path}: {exc}"
            ) from exc
        if not isinstance(data, dict) or "substances" not in data:
            raise ValueError(
                f"amendments JSON missing 'substances' key: {self._path}"
            )
        substances = data["substances"]
        if not isinstance(substances, list):
            raise ValueError(
                f"amendments 'substances' must be a list, got {type(substances).__name__}"
            )
        return [Amendment.from_dict(row) for row in substances]


_default_loader: AmendmentLoader | None = None


def get_default_loader() -> AmendmentLoader:
    """Return the process-wide singleton loader (created on first access)."""
    global _default_loader
    if _default_loader is None:
        _default_loader = AmendmentLoader()
    return _default_loader


__all__ = ["AmendmentLoader", "get_default_loader"]
