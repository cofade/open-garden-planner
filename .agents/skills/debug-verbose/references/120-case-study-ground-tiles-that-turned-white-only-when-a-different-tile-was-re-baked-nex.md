## Case study: ground tiles that turned white — only when a DIFFERENT tile was re-baked next (Phase 17 L1.5, fixed 2026-10-12)

**Symptom**: the first run of the ground bake's time budget on a real engine painted a plan over
fourteen transactions, one tile each — and the finished frame showed most tiles WHITE. Every
count was right: 20 Models, 20 textures alive, the tile bytes bit-identical to the one-pass
bake, `sink.state() == sync.expected_state()`. The same code had passed a whole story's render
tier, a review and two security passes.

**Wrong theories**:

1. *"A replaced texture was let go before the scene had shown its successor — keep it until a
   frame was rendered."* It matched the keep-alive rule's own wording, and a probe that kept
   every replaced texture until the next frame did show the right picture — in THAT frame. One
   frame later, after the textures were let go, the tile was white again. Keeping it longer only
   moved the white frame.
2. *"Only textures the render side has already seen matter; one that was attached and replaced
   without a frame can go at once."* Two sequences that differ in nothing but length (the same
   tile re-textured twice, and five times) came out white and right.

**Key evidence** — a render-tier child with two tiles, three ways of replacing a texture, four
sequences, each tile's mean colour in the frame after and one frame later (white is 255,255,255):

```
          as_is / two tiles in turn      after [[255, 46, 234], [255, 255, 255]]  again [[255, 46, 234], [255, 255, 255]]
as_is+presented / frame between          after [[7, 7, 234], [90, 84, 78]]        again [[255, 255, 255], [90, 84, 78]]
      new_model / two tiles in turn      after [[255, 46, 234], [7, 7, 234]]      again [[255, 46, 234], [7, 7, 234]]
```

`as_is+presented` is the product in a window that presents frames (the replaced texture is let
go after each): EVERY re-textured tile is white one frame after its edit.

**Root cause**: when a `QQuick3DTextureData` that a `Texture` element once held is destroyed, Qt
resets that element's `textureData` to null — whatever it holds by then. The tile's QML binding
`textureData: tileData` does not run again, because `tileData` did not change. The tile stays
untextured until its property is set once more — which is why a scenario that re-bakes the SAME
tiles after every frame never shows it, and why the dev box, whose hardware window presented no
frames that week, never ran the release after a frame at all.

**Fix**: one texture per `Texture` element, for life — a re-baked tile is a new Model with its
own texture, and the old Model is destroyed (`quick3d/ground_tiles.py::_replace` = drop +
create). Five update sequences on the render tier, judged against a reference frame of each
colour right after the last update AND one frame later; the old replacement fails four of them
on the GPU and on WARP.

**Lesson**: **a test that always re-does what it just did cannot see what the second thing
broke.** Twenty re-bakes of all tiles, twenty moves there and back: each step repaired the
damage of the one before. Vary WHICH object the next step touches, do two steps without a frame
between them, and look again one frame after the last one. And **"the object is alive, the
counts are right, the state equals the reference" is bookkeeping** — for anything the user sees,
one assertion must be on pixels.

