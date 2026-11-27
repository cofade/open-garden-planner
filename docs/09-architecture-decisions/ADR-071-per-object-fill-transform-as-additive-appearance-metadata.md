---
id: ADR-071
title: "Per-object fill transform as additive appearance metadata"
status: "Accepted (2026-11-02, package #674/#665/#690)."
refs: ["#665"]
legacy_anchor: adr-071-per-object-fill-transform-as-additive-appearance-metadata-issue-665
---

# ADR-071: Per-object fill transform as additive appearance metadata

**Status**: Accepted (2026-11-02, package #674/#665/#690).

**Context.** Fill textures were painted at one fixed tile scale and orientation.
Rotating the object to align decking, roof tiles or paving also rotates its
geometry and every measurement, and baking rotated assets is combinatorial. The
only fudge was picking a different pattern — the plan stayed geometrically exact
but visually misleading (boards running the wrong way, tiles out of phase between
two roof planes).

**Decision.** Add three **display-only** values per filled object: pattern angle
(degrees clockwise as displayed, 0 = as authored), pattern scale (multiplier,
1.0 = the authored tile) and pattern offset X/Y (centimetres in the item's own
frame, negative allowed). They live in `core/fill_patterns.FillTransform`, are
applied as a `QBrush` transform on top of the cached tinted texture, and travel
in an additive `.ogp` block:

```json
"fill_transform": {"angle_deg": 30.0, "scale": 1.5, "offset_x_cm": -12.5, "offset_y_cm": 7.0}
```

The identity is **never serialized**; old plans load with the identity and no
visible change, so `FILE_VERSION` stays `"1.4"`. The stored block is read
leniently (unknown/malformed/non-finite fields fall back; a zero or negative
scale becomes 1.0), and a non-finite value is never written — `json.dump` would
otherwise emit a JSON `NaN` that cannot reopen. An integer too large to become
a float (`10**400`) is malformed for these fields and falls back to its default
on read; `to_dict()` drops the block rather than raising `OverflowError`.

**Composition.** The offset is applied in centimetres in the item frame and is
independent of angle and scale (`translate · rotate · scale`). A HOUSE's
`_paint_with_ridge` composes the user transform *inside* the canonical ridge
frame (`ridge_tx · user_tx`), on both the normal and mirrored halves, so a
default transform is byte-identical to the previous roof and a user angle turns
the tiles relative to the roof while the two planes stay mirror images.

**Scope.** Geometry, area, snapping, selection, DXF/export coordinates and the
Agent API's centimetre contract are untouched. The Properties panel exposes the
four controls for filled shapes AND for the patterned path styles (gravel path,
dirt path), whose stroke samples the same brush; a plain line has no pattern
row. The 3D ground/face texture sampling keeps its existing untransformed tile
ruler; this is a 2D display property, stated in FR-EDIT-23 and the Properties
tooltip. Extending the transform into 3D materials is separate work.

**Consequences.** A new appearance attribute must be added to the one
copy/restore list (`core/item_look._LOOK_ATTRIBUTES`), the one brush builder
(`fill_brush`) and the save/load look path (`restore_stored_look`) — those three
seams already exist, so Copy appearance, material changes, undo/redo and reload
stay in step (`style_gaps` verifies it). Pinned by
`tests/unit/test_fill_transform.py` (model, leniency, composition, rendered
clockwise sign and tile period) and `tests/integration/test_fill_transform.py`
(panel spins + Reset, one command per change, geometry unchanged, save/reload,
copy appearance, roof composition).

**Alternatives rejected.** *Rotate the object* (changes geometry and all
measurements); *bake one texture per angle/scale* (combinatorial and still not
user-adjustable); *do nothing* (the status quo the issue documents). A per-object
key inside `metadata` was also rejected: this is appearance, and the existing
appearance seams all operate on typed attributes, not free-form metadata.
