---
id: ADR-079
title: "The IANA time-zone data (`tzdata`) is a runtime dependency"
status: "Accepted (2026-11-20). Shipped in v1.40.11 (PR #981) with the plan-time-zone change (ADR-053 addendum)."
refs: ["#945"]
legacy_anchor: adr-079-the-iana-time-zone-data-tzdata-is-a-runtime-dependency-945
---

# ADR-079: The IANA time-zone data (`tzdata`) is a runtime dependency

**Status**: Accepted (2026-11-20). Shipped in v1.40.11 (PR #981) with the plan-time-zone change (ADR-053 addendum).

**Context**: The plan's location may name an IANA zone (`"Europe/Berlin"`), and
`core/plan_time.py` resolves it with `zoneinfo.ZoneInfo` so the clock, toolbar, a camera
tour's wall-time range and "Today" use the garden's time. Python's `zoneinfo` reads the
operating system's database on Linux/macOS, but **Windows ships none**; without a data
package every named zone raises `ZoneInfoNotFoundError` and the plan silently falls back
to the computer's zone. The CI Linux runners have system tz data, so the gap is invisible
there and only appears on the product's primary platform.

**Decision**: Add `tzdata` (the IANA database packaged for Python, Apache-2.0) as a
runtime dependency. The pinned `pyinstaller-hooks-contrib` hooks carry it into the frozen
build: `hook-zoneinfo.py` adds `tzdata` as a hidden import on Windows and `hook-tzdata.py`
collects its data and submodules. `--selftest` queries `available_timezones()` (at least
400 names, including one representative per populated continent) and checks
`Europe/Berlin` and `America/New_York` in summer **and** winter, so a hook regression, a
missing continent or a truncated zone list fails the frozen gate rather than a user's
plan. No application
code imports `tzdata` at startup; the frozen graph includes it through those hooks. The
data is versioned by the IANA release and refreshed by the normal dependency-update
chore. A plan without a zone, or with an unknown name, still behaves exactly as before.

**Alternatives considered**:
- *Fixed UTC offsets.* Rejected: a plan spans dates across both daylight-saving changes;
  a fixed offset makes a summer shadow wrong in winter and a year tour jump by an hour.
- *Map the Windows zone name through the registry.* Rejected: it yields a localized
  display name, not a stable IANA key, and cannot round-trip a plan opened elsewhere.
- *Ship a private subset of the IANA database.* Rejected: a garden can be anywhere, and a
  hand-maintained subset would go stale exactly like the data it replaces.
- *Keep the computer's zone and document the limit.* Rejected: it is the #945 defect.

**Consequences**: The lock, `pylock.toml`, the SBOM and the installer carry one more
runtime distribution; the frozen build is larger by the compressed database and its
dist-info. Tests that used to skip on a bare Windows venv (the IANA cases in
`test_sim_clock.py`) now run there. See ADR-053 addendum, FR-SUN-04, PF-DOM-35 and
`tests/unit/test_plan_time.py`.

## ADR-076 addendum: canvas pictures have explicit consumers (#847, #848, #877, #878)

**Status:** Shipped in v1.40.4 (PR #926); owner acceptance confirmed on 2026-11-15.

**Decision (2026-11-15):** A minimap keeps the live scene's item-cache modes.
Qt's device caches preserve the viewport picture when the thumbnail is painted
(measured on Qt 6.12.0). Its existing scoped walk cap also selects a styled
line's whole-item clip. Exports continue to disable caches for exact output.
The shadow overlay uses the same capped-render scope to paint exactly without
changing its live zoom state; cache mode alone no longer identifies a thumbnail.
The shared interactive-paint predicate excludes capped scene renders as well,
preserving filled polygon thumbnails. Polylines explicitly apply their new
outline bound to thumbnails; other consumers keep their previous classification.
Do not select the thumbnail's clip from the live viewport or introduce a
second scene-construction path just to preserve caches.

The grid builds its visible picture on the first nonempty partial paint after
invalidation. Up to four exact subpixel phases share its existing 64 MB bound;
phase and scale changes never reuse resampled pixels. This replaces repeatedly
painting small uncached dirty rectangles, which never established a new cache.

Polylines adopt the existing polygon threshold: above 256 points, unselected
interactive painting uses a cosmetic one-pixel exact outline. Selected items
and exports retain full detail. This bounds the costly wide stroke without
decimating geometric data. The shared paint revision invalidates the snap
index too, including before delivery of Qt's queued change signal. No new
setting, dependency, serialization field or file-version change.

Embedded pixel tests capture the owning window and crop its viewport; a
viewport-only grab cannot prove backing-store offset handling. Tests and
measurements: §8.37; FR-GRID-05 and FR-EDIT-20.


## ADR-076 addendum: editing frames and plan writing (#840, #841, #843, #844, #853, #867, #872, #874)

**Status:** Shipped in v1.40.6 (PR #934) after owner manual acceptance.

**Decision (2026-11-17):**

1. `core/item_geometry.py` owns `selection_frame_rect` and its scene-space adapter.
   The old handle-module import re-exports the same function. Object snapping uses
   it for both the moving selection and targets; alignment and distribution use
   the same frame. Capacity badges read the local frame. Paint bounds remain free
   to include rings, foliage, strokes and diagnostic overflow. Nested groups derive
   their frame from document members, excluding their labels.
2. A multi-selection keeps object outlines and suppresses individual resize and
   rotation handles. One logical edit target, including a drilled-down member,
   retains handles. Resize corners need 16 screen pixels on both local axes;
   edge handles need 32. These bounds leave one 8-pixel handle-width between
   neighbours. A grabbed handle stays visible until release. Zoom and selection
   refresh the existing handles; the rotation offset is 25 device-independent
   pixels along the parent's local Y axis, including ancestor transforms.
3. Dimension text joins the retained foreground label pass. Labels of one owner
   move together inside the plan edge before collision placement. Upright succession
   tags fit inside the bed's actual transformed outline, including concave polygons,
   and reserve their space against names. A bounded 9-by-9 placement search favours
   the visual bottom-left; if full text has no safe position it becomes a compact
   square crop-following arrow, independent of crop-name length and row count. The retained placement carries its variant explicitly and its paint signature tracks same-size content changes. Beds smaller than 3 pixels cannot carry a readable indicator.
   Warning arcs exclude editing handles and annotations using one retained device-space exclusion path per paint revision and view transform. A shared editing-decoration mixin also invalidates it on transient scene, parent, visibility, position and transform mutations; measured-text setters cover annotation size changes. The minimap suppresses
   diagnostic paint in a restoring scope that schedules no scene updates.
   Every occupied rectangle is indexed before label placement, even when two
   occupied regions overlap. Measured angles share the dimension label pass.
   Plants with visible warning arcs bypass the Qt item paint cache so exclusions
   follow a nearby selection immediately. Their existing sprite rasters are reused.
4. Text notes resolve historical whole-point sizes at a fixed 96 dpi and give Qt
   a pixel-sized font. This preserves the historical 96 dpi appearance and the
   stored `font_size`; hosts with another logical DPI now show the same plan size.
   No file-format bump or rewriting of stored sizes. The Properties conversion
   uses this same fixed reference. Fonts remain unhinted. A native Windows pixel
   test compares letter gaps with a 12-times-size reference and proves sensitivity
   by restoring full hinting as a negative control.
5. Fit-to-window reserves the ruler strips and an 8-pixel stroke/rounding margin.
   Text notes reserve room from contour labels and contour lines. Contours read a
   retained annotation-cover path keyed by the paint revision; moving or editing
   a note, including live document edits through `contentsChanged`, invalidates that path without recomputing the hours-of-sun field.

**Alternatives:** A group-wide resize frame would introduce group scaling semantics;
retain outlines instead. Changing stored text sizes would corrupt old plans; keep
stored values and fix their resolution. Rotating the succession text with its bed
would lose upright writing; place the upright rectangle inside the actual outline.
Hiding every zoomed-out tag loses the only hint of a succession plan; use an arrow.

**Evidence:** `tests/integration/test_canvas_editing_precision.py`,
`test_canvas_label_precision.py`, `test_canvas_native_pixels.py`,
`test_text_note_size.py`, `test_export_text_notes.py`, and
`tests/unit/test_item_geometry.py`. The rectangle-only #879 probe found no
difference when #934 was reviewed. The expanded main-window probe now drives
the selected shed-to-glasshouse conversion, move, rotation, undo, redo and
resize against the Family Garden. At 77% zoom, a 633 × 498 viewport and device
pixel ratio 1, #838 (`7e4d42ee`) differed by four pixels in three steps, within
one channel level at the selection frame. #934 (`b5c434b0`) differed by up to
322 pixels. The same seven captures on v1.40.8 matched a full repaint exactly
after the minimap thumbnail settled. A second full repaint matched the first
on each of those revisions. The new comparison gates the shipped behavior
and records the event regions. The original 131-pixel capture was unavailable.

## ADR-076 addendum — roof style in the plan (#946, #862)

**Status.** Shipped in v1.40.10 (PR #978, owner acceptance 2026-11-19).

The rectangle and polygon roof painters share the plan footprint and the
stored roof style. The 3D builder supplies the hip's nearest-eave partition
and the automatic garage/shed ridge direction. Non-convex hips use a gable.
The plan uses its own footprint for tile faces, while the 3D roof and solar
caster use the modeled pitch and overhang. A linked house ridge stays in the
document as the gable's editable axis. Scene visibility and selection flags
activate it while the roof is gabled. An older one-way link resolves through
the building's forward reference. A roof-style edit and a type conversion
refresh the same derived visibility rule. A layer-filtered image can reveal
a hidden layer while keeping an inactive cap out of the picture.
New garage/shed objects default to gray
roof tiles. Existing fill choices are read from the saved item. Flat roofs
use a single surface with the selected fill. An automatic tool shed uses its
sprite. An explicit roof style uses the shared painter with the shed's stored
fill and outline. The properties command refreshes those styles on edits and
history steps. `test_house_roof_ridge.py` checks scene pixels after edits,
undo and redo, and reloads a plan for every explicit tool-shed roof style.

An explicitly selected flat roof has a separate 3D top surface with plan UVs.
The shared fill pipeline supplies its texture and tint. A fill edit updates
the material. The slab's sides and underside use their own finish, and an
automatic concrete slab keeps its legacy finish.
