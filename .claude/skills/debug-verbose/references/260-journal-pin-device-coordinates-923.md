## Case study: A pin probe clicked below the painted head (#923) (2026-11-16)

**Symptom:** PF-CAN-40 claimed itemAt could never return transform-ignoring items.

**Theories checked:** The pin's shape or Qt picking might be broken. A plain QGraphicsScene instead returned it at the actual device-mapped head.

**Evidence:**

```text
[PIN923] scale=-0.3 shape=True actual_head_hit=JournalPinItem; old local-to-scene query misses
```

**Root cause:** mapToScene treated the pin's screen pixels as plan units. The view's custom query also omitted its device transform.

**Fix:** Map the visible head through deviceTransform(viewportTransform()), and supply viewportTransform to the candidate query. Correcting the QTest head exposed a zero-undo lost release; the transformed query restored the one-step contract.

**Lesson:** Reproduce coordinate claims using the painted device position. A wrong probe does not establish an upstream API limitation.
