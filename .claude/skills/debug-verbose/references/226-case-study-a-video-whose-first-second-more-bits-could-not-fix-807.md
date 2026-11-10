# Case study: a video whose first second more bits could not fix (#807)

## Symptom

The 3D promo survey read a tour's MP4 at 41.5 dB Y-PSNR (H.264 Constrained Baseline, 0.2 bit/px,
12 Mbit/s at 1080p30) and proposed 0.35 bit/px. Measured per frame on a 6 s held foliage shot and
a 6 s slow orbit, the mean did rise with the bit rate, but the WORST frames did not move at all:
40.4 dB on the foliage and 42.0 on the orbit at every rate from 0.35 to 1.0 bit/px, while the
frames after the first second read 45 to 49.

## Wrong theories

1. **"More bits fix it."** The issue's own proposal. From 0.7 to 1.0 bit/px the encoder spent
   31.0, then 32.1 Mbit/s: it stopped taking more, and the first 18 frames stayed where they were.
2. **The content is hardest at the start.** The foliage shot is a held camera in steady wind; its
   first second is no harder than its fifth.
3. **Keyframes.** Media Foundation writes an IDR frame every 30 frames, but the dip was one long
   ramp over frames 0 to 18, not a beat every second.

## Key evidence

The per-frame table of one run (Y-PSNR, then detail kept), foliage at 0.2 bit/px:

| frame | 0 | 5 | 10 | 17 | 18 | 19 | 30+ |
|---|---|---|---|---|---|---|---|
| dB | 41.1 | 40.7 | 40.5 | 40.4 | 41.3 | 43.0 | 47-49 |

and the files: the "average bit rate" mode and the "constant bit rate" mode wrote byte-identical
MP4s. The strings in Qt's `ffmpegmediaplugin.dll` name what it hands `h264_mf`: `rate_control`
(`cbr`) or, in constant-quality mode, `quality` (50, 75, 90, 100), and no `profile`.

## Root cause

Qt maps `AverageBitRateEncoding` to Media Foundation's CBR. A CBR encoder starts with an empty
buffer model and spends little until it has some: the first second is starved whatever the target.
The profile cannot be asked for at all, so FFmpeg's encoder takes Baseline.

## Fix

`Mp4Writer` asks for `ConstantQualityEncoding` at Qt's High or Very High (Media Foundation 90 or
100: the dialog's Standard and Best). Worst frames: 45.8 / 48.1 dB on the foliage, 47.1 / 49.2 on
the orbit. PF-E3D-30; ADR-072 addendum "review-grade video". Pinned by
`test_a_video_is_made_at_constant_quality_as_chosen`.

## Lesson

Read a video's quality per frame, never as one mean: a mean hides the opening second that every
viewer sees first. And before raising a knob, check what the knob reaches - here a bit rate that
became CBR two layers down, in a binary whose strings told more than its documentation.
