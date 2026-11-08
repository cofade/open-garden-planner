"""Smart-symbol library loader (US-C4; bundled templates retired by #770).

Loads parametric symbol definitions from two sources:

* **Bundled** — a directory of ``*.json`` files (used by tests; the app ships
  none since #770 retired the fixed templates in favour of the parametric
  HOUSE / GREENHOUSE / PERGOLA tools). Validated eagerly; a malformed bundled
  file is a packaging bug and crashes loud (mirrors
  ``services/amendment_loader.py``).
* **User** — ``<app-data>/smart_symbols/*.json`` (auto-created). Users drop a
  JSON here to add a symbol; it loads on next launch. A malformed *user* file is
  skipped with a warning (one bad file must not break the app). No sidebar panel
  inserts new symbols since #770; this path keeps existing/user definitions
  available to the properties panel.

Existing plans are unaffected: a smart symbol stores its generated child shapes,
so it loads and draws without its definition. A user file may override a bundled
symbol by reusing its ``id``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from open_garden_planner.models.smart_symbol import SmartSymbolDefinition

logger = logging.getLogger(__name__)

#: No bundled templates ship since #770; tests pass their own ``bundled_dir``.
_BUNDLED_DIR: Path | None = None


def _user_dir() -> Path:
    from open_garden_planner.services.plant_library import get_app_data_dir

    d = get_app_data_dir() / "smart_symbols"
    d.mkdir(parents=True, exist_ok=True)
    return d


class SmartSymbolLibrary:
    """Loads + caches smart-symbol definitions (bundled + user)."""

    def __init__(
        self, bundled_dir: Path | None = None, user_dir: Path | None = None
    ) -> None:
        self._bundled_dir = bundled_dir or _BUNDLED_DIR
        self._user_dir = user_dir
        self._symbols: dict[str, SmartSymbolDefinition] | None = None

    def definitions(self) -> list[SmartSymbolDefinition]:
        """All symbols, sorted by display name; loads on first access."""
        self._ensure_loaded()
        assert self._symbols is not None
        return sorted(self._symbols.values(), key=lambda d: d.name.lower())

    def get(self, symbol_id: str) -> SmartSymbolDefinition | None:
        """Return the definition for ``symbol_id``, or None if unknown."""
        self._ensure_loaded()
        assert self._symbols is not None
        return self._symbols.get(symbol_id)

    def reload(self) -> None:
        """Drop the cache so the next access re-reads from disk."""
        self._symbols = None

    def _ensure_loaded(self) -> None:
        if self._symbols is not None:
            return
        symbols: dict[str, SmartSymbolDefinition] = {}
        # Bundled: crash loud on malformed (packaging bug). None since #770.
        if self._bundled_dir is not None:
            for path in sorted(self._bundled_dir.glob("*.json")):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                definition = SmartSymbolDefinition.from_dict(data)
                symbols[definition.id] = definition
        # User: skip-with-warning on ANY failure (a bad user file must never
        # crash startup). This loop is THE trust boundary for untrusted JSON, so
        # it catches ``Exception`` rather than a hand-picked tuple — every prior
        # crash here was a too-narrow catch missing a new exception family
        # (ValueError → ArithmeticError → RecursionError → AttributeError from a
        # non-dict ``parameters`` entry). A blind catch makes "a user file never
        # crashes the app" total by construction; ``BaseException`` (Ctrl-C /
        # SystemExit) still propagates, and the bundled loop above stays
        # narrow-and-loud so OUR packaging bugs are never silently swallowed.
        user_dir = self._user_dir if self._user_dir is not None else _user_dir()
        for path in sorted(user_dir.glob("*.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                definition = SmartSymbolDefinition.from_dict(data)
                symbols[definition.id] = definition  # user may override a bundled id
            except Exception as exc:
                logger.warning("Skipping invalid smart-symbol file %s: %s", path, exc)
        self._symbols = symbols


_default_library: SmartSymbolLibrary | None = None


def get_smart_symbol_library() -> SmartSymbolLibrary:
    """Return the process-wide singleton library (created on first access)."""
    global _default_library
    if _default_library is None:
        _default_library = SmartSymbolLibrary()
    return _default_library


__all__ = ["SmartSymbolLibrary", "get_smart_symbol_library"]
