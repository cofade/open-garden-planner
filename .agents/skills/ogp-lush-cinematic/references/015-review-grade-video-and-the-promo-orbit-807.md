# A tour video good enough to publish, and the orbit that films it (#807)

ADR-072 addendum "review-grade video"; the engine facts are `ogp-3d-renderer` reference 25; the
values a new orbit starts with are in reference 12. A tour video is judged like a frame of the
board: against its own truth, the PNG frames of the same tour, and by numbers.

## How to measure a tour video

- Render the tour once as a PNG sequence (or write both from one run) and encode those frames
  through `Mp4Writer`; read the MP4 back through Qt's decoder and compare each frame's planes with
  `rgb_to_yuv420` of its PNG - the very YUV the encoder was given. The codec's loss is all that is
  left.
- **Per frame, never one mean:** Y-PSNR mean AND worst frame. The average-bit-rate mode's first
  second was 5-7 dB under the rest at every rate, and a mean hid it.
- **Detail kept:** mean gradient decoded / source over 32 px tiles whose source gradient is 8
  levels or more (leaves, mulch, pickets; the sky's dither and the flat meadow read 1-3 and would
  report the encoder removing noise as lost detail).
- **Colour:** the frame mean through the BT.709 oracle (within 1 level), and the 32 px tile means
  (the 4:2:0 round trip alone reads 0.7-1.1 at worst, a codec adds about one level).
- **The file:** `core/mp4_stream.read_stream` for profile, level, tags, samples and their
  durations; Qt's player prints FFmpeg's stream line (`yuv420p(tv, bt709, progressive)`).

## Measured (1080p30 unless named; RTX 4070, Ultra, 2026-11-10)

| clip | quality | Mbit/s | MB per minute | Y-PSNR mean / worst | detail mean / worst |
|---|---|---|---|---|---|
| slow orbit (family garden, 0.5 degrees a frame) | before (0.2 bit/px) | 12.0 | 90 | 42.6 / 41.8 | 0.966 / 0.941 |
| | Standard | 26.5 | 199 | 47.5 / 47.1 | 0.983 / 0.969 |
| | Best | 35.7 | 268 | 49.5 / 49.2 | 0.986 / 0.978 |
| foliage (food forest, held, wind) | before | 10.0 | 75 | 46.7 / 40.4 | 0.988 / 0.957 |
| | Standard | 7.9 | 59 | 46.0 / 45.8 | 0.986 / 0.977 |
| | Best | 11.4 | 86 | 48.2 / 48.1 | 0.992 / 0.985 |
| the new default orbit (18 degrees, 30 s, eased) | Best | 24.8 | 186 | 50.5 / 49.9 | 0.986 / 0.972 |
| slow orbit at 4K | before | 44.6 | 335 | 45.1 / 43.0 | 0.973 / 0.938 |
| | Standard | 76.7 | 575 | 48.1 / 47.7 | 0.984 / 0.967 |
| | Best | 109.9 | 824 | 50.0 / 49.7 | 0.987 / 0.978 |

Colour within 0.66 levels (frame mean) everywhere; every frame 33.333 ms; BT.709 limited range
stated in the file. Constant quality spends what the picture needs: a held foliage shot costs a
third of an orbit.

## The orbit for a promo

- A turn is a slow move: 30 s at 30 fps is 0.4 degrees a frame (the horizon 10 px a frame at
  1080p). 12 s, the old default, moved it 26 px a frame - judder on any wide shot.
- Tilt for a horizon: 18 degrees puts a 5 % band of sky and the haze above a garden that still
  shows every bed; at 12 the house of the family garden hides the beds at the half turn; 31.6
  shows no sky at all.
- Ease for a clip that is played once; no ease for a clip that loops.
- The orbit keeps the VIEW's distance: frame the plan tighter in the view before "Use Current
  View" if the plan should fill more of the picture (at 18 degrees the default framing leaves the
  family garden in the middle third).
- Shadows: a moving camera keeps the locked map; an eased orbit's slow ends crawl less than its
  cruise (the board's `--stairs` orbit at 0.05 and 0.01 degrees a frame).

## What is left and is the encoder's

Constrained Baseline has no CABAC, no 8x8 transform and no B-frames, so High profile would need
fewer bits for the same picture (not measured: Qt gives no way to ask for High, reference 25 of
the renderer skill). A master for an external encoder is a PNG sequence ("Save PNG Sequence...").
