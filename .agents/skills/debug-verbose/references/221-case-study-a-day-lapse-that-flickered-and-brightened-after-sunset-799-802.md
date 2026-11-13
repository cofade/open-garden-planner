# Case study: a day lapse that flickered at dawn and grew brighter after sunset (#799, #802)

## Symptom

A held-camera time-lapse of 21 June (04:00-23:00, 10 s at 30 fps) over the family garden had
two faults. At dawn and dusk the top of the frame jumped 10-16 luma on every second frame
(sky-band zigzag RMS 3.86 at dawn; by day 0.07). And after sunset the garden got BRIGHTER: the
frame mean went from 37.2 at sunset to 51.5 an hour later, while the board's `--dusk` gate,
which reads the whole frame, passed.

## Wrong theories

1. **The twilight ramp (#802).** The survey blamed `twilight_rig` for ramping the moon and the
   night exposure linearly and proposed a square-root ramp. Simulated, a square-root moon makes
   the rise come earlier and fixes nothing.
2. **A darker night or a brighter sunset (#802).** Each lever alone fails a gate the owner
   accepted: exposure at the low sun brightens the sunset sky above the 6° sky; a moon already
   on at sunset is a step up at 0.5°; a darker night breaks the night rig.
3. **A sky texture per frame is too slow (#799).** One build is 0.1-0.25 s; a 300-frame lapse
   was 158 s before and 198 s after. Not the cost the theory feared.

## Key evidence

For #799 the per-frame log (`tools/app_probe.py --scenario lapse`, frames.json): `sky_builds`
1, 0, 1, 0 … while the sun moved 0.5-0.7° a frame, and a lag-2 peak in the frame-difference
autocorrelation. For #802 the ground sweep (the plan's own suns by elevation, the sky built for
each): on the default framing the ground luminance at the LAST sunlit frame (0.5°, 0.0196) was
already 0.95 EV under the night (0.0379), and crossed below the night at about 3.7°. No ramp
between those two anchors can fall monotonically.

## Root cause

#799: the tour's `settle_sky` used the live view's 1° staleness rule, so the sky, its light
probe and the fog that follows the shown sky's horizon changed on alternate frames while the key
light and the exposure changed every frame. #802: the night rig is "day for night" (a 0.32 moon
38° high at exposure 2.4) and lights flat ground more than a 0.5° sun's sky does (probe 0.42,
exposure 1.25): the anchors conflict.

## Fix

#799: `sky_is_stale(..., threshold_deg=0)` is exact; `settle_sky` asks for it
(`RECORDING_SKY_REBUILD_DEG`); the live view keeps 1° (PF-L3D-28). #802: the owner kept both
anchors; a twilight fill (an ambient in the sky top's colour, `look.twilight_fill`) lifts a
calibrated model of the ground's light to a target that falls from the golden anchor into the
night (PF-L3D-29). Its first prototype passed the default framing and brightened the board's
golden-hour camera 14 %; per-frame responses measured from three sweeps let the next
candidates be predicted before rendering.

## Lesson

Measure the anchors before blaming the ramp between them: if the end of the day already lies
under the night, the ramp is not the bug. Judge an evening on the garden's own light, not on a
sky-filled frame. And a zigzag statistic also counts a smooth curve's bend and a rig's
deliberate corners; to show a period-2 flicker is gone, measure the alternation itself (the
third difference over eight, exactly the step of a flicker and zero for any quadratic trend).
