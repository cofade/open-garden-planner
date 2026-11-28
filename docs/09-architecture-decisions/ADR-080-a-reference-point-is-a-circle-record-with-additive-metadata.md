---
id: ADR-080
title: "A reference point is a circle record with additive metadata"
status: "Shipped in v1.40.13 after owner acceptance ([PR #985](https://github.com/cofade/open-garden-planner/pull/985))."
refs: ["#666"]
legacy_anchor: adr-080-a-reference-point-is-a-circle-record-with-additive-metadata-666
---

# ADR-080: A reference point is a circle record with additive metadata

**Status**: Shipped in v1.40.13 after owner acceptance ([PR #985](https://github.com/cofade/open-garden-planner/pull/985)).

**Context**: A plan could record footprints, plants, annotations and construction
geometry, but not a first-class survey stake, fence post, datum or measurement
reference. Reusing a tiny plant circle gives it botanical semantics and puts it in
plant lists and diagnostics; a callout or journal pin is attached to something else;
construction geometry is not a durable document object. The requested object is a
named target/cross whose exact centre is the snap and measure point, optionally bound
to a parent's outline, with the ordinary layer/lock/copy/undo/save rules. The issue's
design study is `Sevoiger/open-garden-planner` PRs #26 and #30; its object model and
Qt item base have moved since, so this ADR settles the kind before code.

**Decision**:
1. **Object kind.** A reference point is the existing `GENERIC_CIRCLE` record with
   `metadata["reference_point"] = true`, not a new `ObjectType`. `ProjectManager`'s
   ordinary circle branch writes and loads it, and an older version reads it as a small
   circle. No `.ogp` `FILE_VERSION` bump and no second serializer path.
2. **One exact coordinate.** `ReferencePointItem` keeps `rect()` centred on `(0, 0)`
   and its `pos()` is the datum, so `mapToScene(rect().center())` is the exact point in
   both size modes. `core.measure_snapper.get_anchor_points` returns only
   `AnchorType.CENTER` for a reference point; the halo arms are decoration, never
   snap targets.
3. **Binding is additive metadata.** `reference_point_parent_id` and
   `reference_point_on_contour` name the parent and the contour rule. The legacy
   `parent_bed_id` link is deliberately not used, so bed membership, plant lists,
   capacity and deletion cascades keep their old meaning. A bound point is projected
   onto the nearest straight parent edge (`core.snap.geometry.item_edges` +
   `core.cad_geometry.point_to_segment_distance`) when placed or moved; an off-contour
   move is refused, and the dialog's Independent point choice is the explicit detach.
   Parent translation moves the point; parent rotation or vertex edits do not move an
   existing point, which is the documented limitation.
4. **A parent move and its point are one undo step.** `core.commands.expand_with_bed_children`
   appends each moved parent's attached points with that parent's delta, so drag,
   keyboard, typed-coordinate, align/distribute and agent move paths all carry the
   point inside the same command. The live drag propagates attached points like bed
   children and resets them before the command re-applies the delta. There is no scene
   watcher and no second write path.
5. **Two size modes.** `reference_point_size_mode` is `plan_cm` (default, 6 cm, scales
   with zoom) or `screen_px` (default 16 px, `ItemIgnoresTransformations`); colour and
   cosmetic stroke width are metadata. The symbol is a target/cross with a centre dot;
   `boundingRect`/`shape` keep the halo clickable and the minimap paints a dot.
6. **No 3D form.** A generic shape has no height, so the built world produces nothing
   for it. A measurement datum stays a 2D plan object; `core/scene3d` is unchanged.
7. **Ordinary object rules.** Placement is one `CreateItemCommand`; every edit is one
   `ChangePropertyCommand` over `(name, binding, size, colour, stroke, position)`.
   Layer, lock, copy/duplicate, delete, context menu, save and reload use the existing
   mixins and commands.
8. **Translations.** All strings use `ReferencePoints`, `MainToolbar` and `Commands`
   contexts and are complete in every registered locale (en/de/es/ru/fr). The French
   locale lands in the same package (#553) so this object's strings exist everywhere.

**Alternatives considered**:
- *A new `ObjectType` and item class.* Rejected: it needs a `FILE_VERSION` bump, an
  old version cannot read a file that contains it, and it repeats the ~16 dispatch sites
  ADR-031 already rejected for "things plants live in".
- *A tiny generic circle without metadata.* Rejected: it cannot be named, bound,
  snapped from a declared datum, or distinguished from a surface.
- *A callout or journal pin.* Rejected: both attach to another object and cannot be a
  free-standing datum.
- *A Qt child of the parent item.* Rejected: a parent rotation would move the datum,
  and the group serializer would treat it as nested content rather than a plan object.
- *A scene-change watcher that follows the parent.* Rejected: it mutates outside the
  undo stack and adds a chatty teardown signal (invariant 18).

**Consequences**: Adds `core/reference_points.py`, `ui/reference_points.py`,
`ui/canvas/items/reference_point_item.py`, `core/tools/reference_point_tool.py`, and
the dialog strings. The tool is armed from **Garden > Reference point**; it is not a
sixth main-toolbar button. A sixth button, like any extra per-window widget, amplified
a teardown fault during this delivery (PF-TST-14's armed timer, PF-TST-41's churn);
the menu action is the stable entry and keeps the toolbar at the five tools ADR-018
defines.
Deleting a bound parent leaves the datum in place; it reads as independent and the
dangling key is cleared on its next edit. No dependency, `.ogp` format, or 3D change.
Tests: `tests/unit/test_reference_points.py` and
`tests/integration/test_reference_points.py` (placement, contour projection, parent
translation with one undo step, detach, edit, copy, layer, save/reload, legacy circle
fallback and both size modes). Cross-refs: FR-REF (FR-REF-01..06), §8.9.20, glossary
"Reference point", ADR-017/ADR-031 (bed predicates), ADR-004 (commands), ADR-078
(measurement display).


**Review addendum (PR #985).** A direct move projects the requested coordinate once.
Undo and redo restore the captured coordinates, including a point left off the
contour by a parent geometry edit. Changing a name or symbol does not project
the point. A parent translation carries unlocked points in their own coordinate
frame, including a point inside a separate stationary group. A position lock
or locked layer prevents this implicit move. A point and its parent copied
together rebind by UUID even when nested. An ordinary translation of a Qt group
also moves its members. Constraints treat reference points as stationary
anchors during the solve. If the solve moves a binding parent, its unlocked
points follow that parent in the same command. A datum may have an attachment or
participate in a geometric constraint. Attachment still permits centre snapping,
measurement and a position lock. The dialog offers only persistent rectangles
and polygons for new bindings; construction guides remain snap aids. The datum's rendered perimeter
does not participate in snapping or rectangle-based geometry editors.
