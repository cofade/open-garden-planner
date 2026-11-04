## Case study: Properties panel missing icons for certain object types (#643)

**Symptom.** In the Properties panel ObjectType dropdown, items like planters,
trellises, round containers, wall planters, ellipses, and hedges showed blank/missing
icons or fell back to generic icons.
**Wrong assumption.** All `ObjectType` enum values were thought to be covered by the
existing `_TOOL_ICONS` dictionary.
**Evidence.** Inspection of `ui/panels/properties_panel.py` revealed that `_TOOL_ICONS`
only mapped a subset of types (about 25 out of 52). Newly added object types or sub-types
(`CONTAINER`, `CONTAINER_ROUND`, `WALL_PLANTER`, `TRELLIS`, `GENERIC_ELLIPSE`, `HEDGE_POLYGON`)
had no entries in `_TOOL_ICONS` and no fallback logic to load their bundled SVGs.
**Fix.** Extracted `_TOOL_ICONS` and `_EXTRA_SVG_FILES` to module-level static dicts.
Created helper `_get_object_type_icon(obj_type)` which looks up `_TOOL_ICONS`,
`_EXTRA_SVG_FILES`, and `get_furniture_svg_path()`, covering 100% of all 52 `ObjectType`
enum values with non-null `QIcon` instances. Pinned by `tests/ui/test_properties_panel.py`.
**Lesson.** When a UI combo box enumerates all variants of an enum, test that 100% of enum
members resolve to valid non-null visual assets to prevent blank UI states.
