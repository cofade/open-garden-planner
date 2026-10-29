## Case study: same-scene reload duplicates and false-success deletes (fixed 2026-09-24)

**Symptom**: after a project was loaded into the same `CanvasScene`, `list_layers.object_count` exceeded the top-level `list_objects` roster; a call to `delete_object` could report success while a same-ID callout remained visible.

**Theories entertained (wrong)**:
- Concurrent MCP requests were bypassing the Qt main-thread queue and needed a second global lock.
- `CommandManager.execute()` could acknowledge a command before `DeleteItemsCommand` removed the item.
- The layer-count mapper was deliberately counting child/overlay items.

**What instrumentation and probes revealed**: `MainThreadBridge` already serialized the provider bodies on the main thread. The decisive probe was a same-scene save/load followed by a type/UUID census: old `CalloutItem`, `ArcItem`, and `BezierItem` instances remained because `_deserialize_to_scene()` removed only an older explicit class tuple. `find_item_by_id()` then returned the first duplicate, so deleting it left the other alive.

**Root cause**: the load cleanup roster had drifted from the serializer's actual document-item roster.

**Fix**: centralize a serialized-document-item predicate in `ProjectManager`, preserve compare/dimension overlay owners, refuse duplicate live UUIDs before agent deletion, and verify all requested targets are detached before returning success. The real-MCP integration test now exercises the round trip and concurrent delete contract.

**Lesson**: UUID identity is a scene invariant, not merely a lookup hint; a successful command receipt is not proof that the addressed object is gone.

---

