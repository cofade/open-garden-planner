---
title: "Walkthrough"
prefixes: ["FR-3D-WALK"]
---

# Walkthrough

- **FR-3D-WALK-01** (L1.8): "Walk" in the 3D pane puts the user into the garden at eye height, where the 3D view was looking, facing the way it looked — on the nearest free ground if that spot is inside a building. W A S D or the arrow keys walk (140 cm/s; twice that with Shift), dragging the mouse looks around, Escape or the "Walk" button leaves. "Walk" gives the 3D view the keyboard, and leaving gives it back. While walking, W A S D, the arrow keys, Shift and Escape belong to the walker — no shortcut of the application fires for them (S does not toggle Snap to Grid) — and every other key, and every key with Ctrl or Alt (Ctrl+Z undoes), works as everywhere else. Eye height is chosen from three presets in the Walk button's menu: adult (165 cm), smaller adult (150 cm), child (110 cm). There is no head bob and no camera smoothing.
- **FR-3D-WALK-02** (L1.8): The walker has a body (45 cm wide) and cannot walk through the built garden: walls, fences, houses, sheds, hedges, raised beds and containers — and a greenhouse that has been given a height — stop it when they are higher than a step (25 cm) — where they are DRAWN in 3D, not at the plan's thinner line. A gap of 20 cm does not let it through; a 60 cm garden gate does. Along an obstacle it slides instead of sticking, and no corner traps it. A courtyard inside a closed wall can be walked in by whoever gets in. The plan's edge is the edge of the world. Standing against a wall never shows what is behind it. Plants other than hedges, furniture and flat surfaces do not stop the walker in this version; there are no stairs or slopes.
- **FR-3D-WALK-03** (L1.8): Walking changes nothing: not the plan, not the undo history, not the selection rules (a click still selects), and not the 3D view the user had — leaving walk mode shows exactly that view again. Hiding the 3D view while walking keeps the walker where it is; editing the plan while walking is seen at once, and a walker that something was built on is moved to free ground. The pace does not depend on the computer's frame rate.

Acceptance: shared with [3D selection](selection.md), whose acceptance paragraph names the tests.
