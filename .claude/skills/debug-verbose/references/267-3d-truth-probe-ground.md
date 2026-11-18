## Case study: the 3D truth probes measured ground they did not ask for (#885, #886)

**Symptom:** The documented Beauty Board rejected a clear sunset, and grass
appeared in the box-caster shadow comparison.

**Theories checked:** A black sunset disc or an outdated luma limit could explain
the failed gate. The darkest band was actually below the horizon and the frame
showed meadow there. Changing the shadow map would leave grass in the IoU oracle.

**Evidence (Qt 6.12, Direct3D 11):** The 1280 x 720 baseline read a dip of 11.71
luma at -0.62 degrees at Low. With the same camera and sky and the meadow omitted,
painted and atmosphere weather probes read at most 1.8 luma of dip. The flat
box-caster frames had IoU 0.9185 to 0.9851 at 640 x 360.

**Fix:** Omit the meadow along with the plan ground for the set-sun frames. Keep
the receiver flat for the box-caster sample even when the board requests grass.

**Lesson:** Check which surface each projected ray can actually hit before
recalibrating a pixel limit. Bare ground and an absent ground surface serve
different probes.
