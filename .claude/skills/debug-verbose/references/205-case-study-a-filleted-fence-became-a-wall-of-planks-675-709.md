# Case study: a filleted fence became a wall of planks (#675/#709)

## Symptom

A fence or a string of lights with **one filleted corner** looked right in 2D but rendered
in 3D as a smooth, solid curved block: individual posts and planks merged into a wall. A
chamfer on the same corner was fine.

## Wrong theories

1. *The 3D builder's post size is too large at a corner.* The posts were the straight
   runs' 9 cm (wooden fence) / 4 cm (string); the size was never the problem.
2. *The rails overlap and fill the arc.* The rails are thin boxes at 25 % / 75 % height;
   they cannot fill the space between posts.
3. *Z-fighting or a bad normal merges the meshes.* The block was real geometry: a post
   at every 2–4 cm chord.

## Key evidence

- `FILLET_ARC_TOLERANCE_CM = 0.02` bakes a fillet as a dense run of 2–4 cm chords.
- `_Run.posts()` computed `max(2, ceil(segment_length / spacing) + 1)` **per segment**, so
  every 2 cm chord got its own posts (a shared corner once): measured 21 posts in a 39 cm arc (r 25) and 41 in a
  157 cm arc (r 100).
- The string's `_posts()` kept every point more than 1 cm from the previous one: the same
  21 / 41 posts, with bulbs sinking into them.
- The top-vertex count of the built mesh was the tell: dozens of distinct post-top
  clusters inside one corner, exact spacing on the straight runs.

## Root cause

Every consumer of a polyline treated each **drawn segment** as an independent run. A
baked fillet is a dense polyline: per-segment spacing is correct for a hand-drawn corner
and catastrophic for a sampled arc.

## Fix

- Fences (`_Run`): a turn below `CORNER_DEG = 20°` joins a smooth span; posts, pickets,
  bars and chain-link wires are spaced by **arc length** across the span, at the straight
  runs' pitch. Real corners (90°, a chamfer's 45°) still break. Rails stay per segment.
- Strings (`core/string_lights._posts`): `MIN_POST_GAP_CM = 40` along the line, first and
  drawn last point kept, a closed loop also checks the closing span. Bulbs move along
  their span until they clear every foreign post by `OTHER_POST_CLEAR_CM = 8.6`.

## Lesson

A curve baked into a polyline is not a set of independent segments. Any builder that
spaces things "per segment" must first group the smooth run; the test must assert the
**minimum gap and the count**, not just that the corner exists.
