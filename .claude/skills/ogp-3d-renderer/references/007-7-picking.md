## 7. Picking

`pickAt(x, y)` in QML → `{hit, id, x, y, z}` (engine frame). Models must set
`pickable: true`. `--pick` checks it in a top-down orthographic view against a CPU oracle (the
topmost triangle under a vertical ray over every pickable mesh, merged per item):

- **Easy targets** (each item's highest unoccluded triangle): **20/20**, 0.15–0.24 ms per pick
  (llvmpipe); 20/20 in the frozen Windows D3D11 exe. Easy targets alone prove little — a picker
  that only tests bounding boxes scores 18/20 on them.
- **Adversarial targets** (points inside a tall item's bounding box but off its mesh, where a
  box picker names the wrong item): **10/10** on llvmpipe at 6f0c4f4.
- **Independent projection:** the click pixel comes from the engine's `mapFrom3DScene`, so a
  wrong engine projection could aim and pick consistently wrong. An orthographic projection of
  our own (`measure.top_down_pixel`) agreed with it to **0.0 px**, and the picked point lay
  **0.0 cm** from the target (llvmpipe, 6f0c4f4).
- **Re-attach:** 20/20 again after a detach/re-attach cycle, and the frame is pixel-identical
  (mean abs diff 0.0) — 0/20 and a blank frame without the re-upload rule in §2.

