## Case study: green renderer gates bypassed Plant Forge (PR #593)

**Symptom.** Render CI was green, but the actual forged board showed summer birch
as a pitchfork and winter willow floating 30.418 cm above soil. Apples carried
ripe fruit and blossom in both April and September.
**Wrong theories.** Green builder bounds and a fast phenology evaluator were
assumed to prove production appearance and responsiveness. Neither included the
workspace's actual upgrade or material work.
**Evidence.** Independent boards had 98 old parts versus 191 forged parts.
`[593-SEASON] date=2026-03-21 frost=2026-03-01 ripeness=0.7` showed a radish ripe
one day before its exact window; an October southern radish read 0 after a
second hemisphere shift. A six-apple GUI batch took 116.6 ms. Resetting SceneSync
restored v0 while the worker still reported pending_count 0.
**Root cause.** Test environment flags disabled the new feature. A separate
worker remembered installed state outside recovery, combined seasonal accents,
removed the leaves that made fitting pass, and evaluated whole-month harvests.
Fixed leaf counts left tall crowns at 0.077–0.315 area coverage.
**Fix.** The real render/frozen paths exercise the forge. One background job
returns through document/geometry/LOD admission; recovery invalidates upgrades.
Seasonal values update persistent Models; distinct flowers/fruits/tubers and
shared exact-day calendar windows keep seasons independent. Structural wood is
fit independently, and foliage area follows the crown at every LOD. Regression
pins live in the forge workspace/calendar/review tests. All probes remained
outside production source.
**Second visual pass.** Raising wood independently left summer branch spikes
outside the foliage. A shared wood-derived vertical frame and leaf anchors at
actual twig tips reduced a measured attachment gap from 74.416 cm to 0.000015 cm.
Tall conifers still had separated tiers: aspect-derived tier counts reduced
21-72 pixel bare runs to zero over three seeds and every LOD. The 300-Model
material update is now an actual render-tier perf assertion, separate from the
non-timing render check. A further regression keeps fruit tint changing while
the same plant also flowers; only the fruit Model receives that tint.

The final FPS instrument still had a separate legacy builder path. Both still
frames and the FPS probe now call `forge_scene_plants`; the FPS metrics expose
61 forged plants / 212 parts. A source gate pins both calls and date inputs.
A session presenting zero frames cannot establish FPS; report readback costs
separately and leave presented FPS to owner hardware acceptance.

**Support follow-up.** A jasmine whose fence face lay 40 cm from its centre
reached only 26.6055 cm toward it, leaving 13.3945 cm of air at three rotations.
The guide retained orientation but discarded position and side. Finite local
segments, width and relative height now train reachable vines into the support
without recentering them away again. A 540-build sweep retained height, canopy
and all LOD budgets; the reproduced wood reaches 43.51 cm toward the 40 cm face.
The first production timing probe then exposed 73.7–83.4 ms for 300 climbers and
10 fences, rising to 518–617 ms with 100 fences: the GUI repeated support
discovery on every date. Move discovery into the synthesis job, cache only its
guide against exact structural inputs, and reject obsolete in-flight results.
The real 300-Model / 100-support workspace refresh now passes 16 ms with no
new geometry work; the old evaluator-only route could not establish that claim.

**Lesson.** A render gate must execute the shipping path. Measure the final
seasonal structure and actual Model update, not a pre-removal fit or evaluator.

