## Case study: undo raised on a line just drawn — and worked once the plan had been reopened (Phase 17 L1.5 review, fixed 2026-10-12)

**Symptom** (shipped in v1.30.1): draw a fence, change its stroke width in the properties
panel, Ctrl+Z — `TypeError: setWidthF(self, width: float): argument 1 has unexpected type
'NoneType'`, and the line keeps the new width. The same for a dash edit (`AttributeError:
'NoneType' object has no attribute 'to_qt_pen_style'`) and for a type change made in the panel.
Save, reopen, repeat: no error.

**Wrong theories**:

1. *"The stroke attributes of lines were fixed last round."* The LOADER was (`adopt_pen` after a
   load), and every pin of that fix went through a project file.
2. *"The guard walks every operation that makes an item from an item."* A constructor is not
   one; nothing judged an item that was merely built.

**Key evidence**: the attributes printed next to the pen they mirror —

```
fresh line    pen #ff8b4513 3 SolidLine | states None None None
loaded line   pen #ff8b4513 3 SolidLine | states #ff8b4513 3.0 SOLID
```

**Root cause**: `PolylineItem.__init__` handed no stroke to `GardenItemMixin`, and
`_setup_styling` built the pen without writing the attributes; the panel's undo takes the value
to go back to from the attribute.

**Fix**: `_setup_styling` builds a line's pen from the stroke it STATES (else its type's) and
ends in `adopt_pen` — which also makes the context menu's undo restore a re-stroked line. The
guard is behaviour now: at the end of every integration test, every item of every scene must
state the look it paints (`tests/integration/conftest.py`).

**Lesson**: **an object with two ways into existence (constructed, loaded) needs every state pin
on BOTH** — a fix on one way makes the two behave differently, which is harder to find than
both being wrong. And print a mirrored attribute NEXT to the Qt state it mirrors.

