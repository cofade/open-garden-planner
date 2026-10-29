## Case study: same-zValue items reverse stacking after .ogp save/load (US-12.10/F2.7, fixed 2026-05-03)

**Symptom**: A tomato dropped on a polygon bed rendered correctly during the live session. After saving the project and reopening it, the bed was on top — the tomato was gone (actually still in the scene, just hidden behind the bed).

**Wrong theories**:
- The plant wasn't being saved (`scene.items()` after load showed it present).
- The plant's transform was wrong (correct — the dot was just hidden).
- A z-value field wasn't being persisted in `.ogp` (it isn't, but that's a symptom not the cause).

**Key signal**: in the live session, both bed and plant had `zValue() == 0`. The plant was on top. After load, both still had `zValue() == 0` — but the bed was on top. So the *tie-break* between same-z items had flipped between sessions.

**Root cause**: `ui/canvas/canvas_scene.py:1337` `_refresh_layer_z` set every item's z to `layer.z_order * 100` (since revised by #338/ADR-043 into a per-item ranked z within that band — §8.25). Items in the same layer get *the same z*. Qt's `QGraphicsScene` then tie-breaks by item insertion order. The live session inserts bed first, then plant — plant on top. The post-load reconstruction inserts items in scene-traversal order from the saved JSON, which is reversed by serialization, putting the plant first and the bed on top.

**Fix**: Add a third pass in `_update_items_z_order` (mirroring the existing ROOF_RIDGE special case, now `ui/canvas/canvas_scene.py:1228` `ROOF_RIDGE` inside `_stack_entries` since #338/ADR-043's rewrite — §8.25) that walks every item with `_parent_bed_id` set and bumps its z to `parent.zValue() + 1`. Now plants always have a strictly higher z than their bed, regardless of insertion order.

**Lesson**: Identical zValues are a footgun across save/load boundaries because `QGraphicsScene` tie-breaks by *insertion order*, which is **not stable** between live mutation order and JSON-load order. Whenever a parent-child draw relationship matters, encode it explicitly via `parent.zValue() + 1` — never rely on "I inserted them in the right order, it'll just work". Pattern: anywhere `_update_items_z_order` touches multiple item categories, add an explicit ordering pass per parent-child relationship.

---

