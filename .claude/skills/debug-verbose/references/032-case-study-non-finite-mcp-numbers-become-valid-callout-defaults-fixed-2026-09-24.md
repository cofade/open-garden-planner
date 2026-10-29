## Case study: non-finite MCP numbers become valid callout defaults (fixed 2026-09-24)

**Symptom**: `1e308` callout offsets were rejected, but `Infinity`/`NaN` sent through the real MCP client unexpectedly created ordinary callouts instead of failing.

**Theories entertained (wrong)**:
- `require_finite()` was not being called for callout offsets.
- Qt accepted the values and the problem was only a rendering issue.
- The client would preserve non-finite JSON values all the way to the Python provider.

**What instrumentation revealed**: the hostile-call test showed the first two calls failed in `require_bounded_signed_offset`, while the Infinity/NaN calls returned ordinary create results. The transport had normalized those JSON values to `null`; `float | None = None` made the provider interpret them as omitted and apply default offsets.

**Root cause**: validation happened after the transport had erased the distinction between an omitted optional argument and a hostile null/non-finite value.

**Fix**: validate signed, canvas-relative offsets before the loader, use an omission sentinel in the MCP handler, and reject explicit null before dispatch. Refusals now occur before `_deserialize_item_core` and `CreateItemCommand`.

**Lesson**: adversarial-input coverage must cross the real transport; a direct pure-function test cannot see JSON/Pydantic normalization.

---

