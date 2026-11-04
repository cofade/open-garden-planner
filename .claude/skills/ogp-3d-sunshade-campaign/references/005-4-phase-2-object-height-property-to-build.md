## 4. Phase 2 — Object height property — TO BUILD

**Contract:** additive metadata key **`object_height_cm`** on garden items —
follow the `container_height_cm` precedent (`core/container_model.py`
docstring; `.ogp` round-trips metadata wholesale, old apps ignore unknown
keys → graceful degrade, **no FILE_VERSION bump**).

**Old-app graceful-degrade statement (put it in the PR body):** a `.ogp`
saved by v2.0 with `object_height_cm` opens in v1.x unchanged — the key rides
in `metadata`, which v1.x preserves on load/save (verified: `project.py`
serializes `item.metadata` wholesale, and unknown keys are untouched). No
migration, no warning needed.

### Design decisions (make them explicitly, record in ADR-037)

1. **One Qt-free resolver** — `core/object_height.py` (pattern:
   `core/plant_sizing.py`). Precedence:
   `metadata["object_height_cm"]` (explicit) → container: `container_height_cm`
   → plant with species: `plant_species["max_height_cm"]` (present in 118/118
   bundled records) → per-`ObjectType` default table → `None` (casts no shadow).
   Suggested defaults (agree with the owner in Phase 0 review): FENCE 120,
   WALL 200, HEDGE_* 150, HOUSE 450, GARAGE_SHED 250, GREENHOUSE 220,
   TRELLIS 180, RAISED_BED 40, furniture 75–90, everything else `None`.
2. **Do NOT alias `container_height_cm`.** It means *soil fill height* and
   drives soil volume; a tall pot on legs can have `object_height_cm` 90 with
   fill 30. Two keys, resolver arbitrates.
3. **Properties panel**: "Height" spin in a new/existing section — but
   **undoable**, via `ChangePropertyCommand` with an `apply_func` writing the
   metadata key (`core/commands.py` line 463 supports exactly this). The
   existing container section mutates `meta[...]` directly with no command —
   that is documented debt (#-file if you touch it), NOT the pattern.
   Respect the #206 incremental-refresh contract: `_register_refresh` for the
   new widget; and the #210 lesson does not apply (spin, not free text).
4. **i18n**: `self.tr("Height:")`, `self.tr("cm")` suffix if any, the command
   description fragment registered under the `Commands` context in
   `scripts/fill_translations.py` (per the ChangePropertyCommand localization
   scheme, #210).

### Gate P2

| Command | Expected | If not → |
|---|---|---|
| `venv/Scripts/python.exe -m pytest tests/unit/test_object_height.py tests/integration/test_height_property.py -v` | Round-trip test green: set height 250 on a WALL → save `.ogp` → load → resolver returns 250; unset item of type FENCE → default 120; plant w/ species Tomato → 200 (from `max_height_cm`) | If round-trip loses the key: you bypassed `set_metadata` or built the item without passing `metadata=` through the deserializer — trace `project.py` item-load path for your item class. |
| `venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished -v` after `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py && PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py` | pass | A UI string missed `tr()` — remember the f-string trap (CLAUDE.md i18n section). |
| Manual: edit height, Ctrl+Z | Height reverts in one step; dirty flag set (the #209 invariant) | You mutated metadata outside `execute()`/`register_applied()` — route through the command. |

---

