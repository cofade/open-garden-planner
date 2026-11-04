## Case study: a complete catalog can hide the wrong source inventory (#496 review)

**Symptom.** The new gate passed, yet helper keyword calls and unmarked table members
were absent; offset-tool status text still appeared in English with German installed.
**Wrong theory.** Marker presence and an enclosing class identify every runtime key.
**Evidence.** Four independent mutation tests failed first. A real CanvasView/OffsetTool
regression returned `Select a shape to offset` instead of the German status message.
**Root cause.** Helper keyword arguments were skipped; marker scans omitted plain table
values; dynamic disambiguation was discarded; `.tr()` inherited the caller's context
instead of its receiver's context.
**Fix.** Bind supported helper arguments, enumerate complete display fields/values,
preserve dynamic comments, require explicit external receiver contexts, and translate
offset status through CanvasView explicitly. Reject escaping/imported helper aliases.
**Lesson.** Validate extraction with mutations at real production source shapes and
runtime lookups, not only against catalogs generated from that same extractor.

