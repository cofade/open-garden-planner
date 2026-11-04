## 12. Agent API render tool (D1.3, PR #242) — layers fix + two empirical mcp facts

Source: CLAUDE.md D1.3 row, docs §8.19, ADR-034 addendum.

- **Manual-test fix**: `render_canvas_image`'s `layers` parameter was originally
  *subtractive-only* — it could hide layers but never show one the user had toggled off
  in the live Layers panel, so an agent explicitly requesting a hidden layer got nothing.
  Fix: `_hidden_layers_not_in` snapshots every layer-bearing item's original visibility,
  **forces the full requested set**, and restores the exact original state afterwards —
  no lasting UI side effect.
- **Two facts empirically verified against mcp 1.28.1 — do not "clean these up":**
  (1) `Image` is not pydantic-representable, so the tool needs
  `@mcp.tool(structured_output=False)` — a naive `list[Image | RenderMeta]` annotation
  crashes `build_server()`; and `Image` must be a genuine **top-level import** in
  `server.py`, because `inspect.signature(func, eval_str=True)` resolves stringified
  annotations via the tool's own `__globals__` (a function-local import breaks it).
  (2) `render_scene_region`'s `y_flip=True` inverts the rendered pixel Y-axis relative
  to D1.2's scene frame — the correction formula is documented on
  `RenderMeta.px_per_cm`.
- Status: closed. Pinned by `tests/unit/test_agent_api_render_coordinate_frame.py`
  (coordinate frame) and `tests/integration/test_agent_api_render.py`. Facts dated:
  verified against mcp 1.28.1, 2026-06/07 — re-verify on any mcp version bump.

---

