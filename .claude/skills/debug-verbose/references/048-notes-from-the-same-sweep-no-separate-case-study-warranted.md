## Notes from the same sweep (no separate case study warranted)

- **F2.10b — bed history merge with global default**: a UX-semantics fix. The default test should be the bed's *fallback*, not a permanent overlay. Once a bed is tested, the default vanishes from its history; delete the last bed record and the default reappears. Lesson worth remembering: when implementing a "fallback" relationship, the UI should show the fallback *only when actually applied* — having it always visible obscures whether the bed has its own data.

- **F2.10c — RAISED_BED on circles/ellipses**: pixmap-based rendering doesn't clip to the underlying shape. A round bed with `RAISED_BED` rendered as a square wooden frame. Lesson: when a type carries a fixed-aspect-ratio raster asset (the wooden-frame pixmap), the "valid shapes" list for that type must match the asset's aspect — otherwise the result is incoherent. Drop the option from incompatible shape lists rather than trying to clip the pixmap (which would distort it).

---

