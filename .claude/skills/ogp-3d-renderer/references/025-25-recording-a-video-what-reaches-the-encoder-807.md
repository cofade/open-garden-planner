## 25. Recording a video: what reaches Windows' encoder, and what the file says (#807)

Decisions: ADR-072 addendum "review-grade video"; lessons: PF-E3D-30, PF-E3D-31; module:
`core/mp4_stream.py`. Measured on the dev box (RTX 4070, Windows 11, PyQt6 / PyQt6-Qt6 6.12.0 with
its FFmpeg 9.0.1), 2026-11-10, with probes that encode a PNG sequence through `Mp4Writer`, parse the
MP4 in Python and read it back through `QMediaPlayer` + `QVideoSink`:

- **H.264 is `h264_mf` and nothing else.** The wheel's `avcodec-63.dll` holds no `h264_nvenc`,
  `h264_qsv` or `libx264` (Qt's plugin names them, the codec library does not), and Media Foundation
  picks its software encoder (`MFT name: 'H264 Encoder MFT'` on stderr).
- **What Qt hands it** (the strings in `plugins/multimedia/ffmpegmediaplugin.dll`): `rate_control`
  and `quality`, never `profile`. `AverageBitRateEncoding` and `ConstantBitRateEncoding` wrote
  byte-identical files: CBR. Its first 18 frames read 40.4-42.0 dB Y-PSNR at every rate from 0.2 to
  1.0 bit/px, and above 0.7 bit/px it spent no more (1080p30 orbit: 31.0, then 32.1 Mbit/s).
  `ConstantQualityEncoding` sends a quality instead: Normal / High / Very High gave 16.7 / 26.5 /
  35.7 Mbit/s on the same orbit, 44.4 / 47.5 / 49.5 dB, each frame within 0.5 dB of the mean. In
  that mode a `setVideoBitRate` is not passed on (identical files with and without).
- **Always Constrained Baseline** (profile_idc 66, constraint_set1): no CABAC, no 8x8 transform,
  no B-frames. FFmpeg's encoder maps an unset profile to Baseline, and Qt offers no way to set one.
- **The level follows the requested bit rate**, not what is spent: 1080p30 is 4.0 up to 0.35 bit/px,
  4.1 at 0.5-0.7, 5.0 at 1.0; at constant quality (no bit rate) 4.0 at any rate, 36 Mbit/s included,
  and 4K30 5.1. `core/mp4_stream.needed_level` raises it to what the samples need.
- **The stream:** an IDR frame every 30 frames, each sample of it AUD, SPS, PPS, two SEI, IDR, so
  the SPS repeats in the stream; the SPS has a VUI with timing only (num_units_in_tick 1,
  time_scale 60 at 30 fps) and no video signal type; the sample entry has no `colr`. Layout
  `ftyp`, `free` (8 bytes, for a later 64-bit mdat), `mdat`, `moov`; one track; `stco`; timescale
  15360, every sample 512 ticks.
- **Qt's decoder reads the tags.** For that file every frame said `ColorSpace_Undefined`,
  `ColorTransfer_Unknown`, `ColorRange_Unknown`; with a `colr` box and SPS colour it says
  `ColorSpace_BT709`, `ColorTransfer_BT709`, `ColorRange_Video`, and the decoded planes are the same
  bytes. `QMediaPlayer` prints FFmpeg's stream line on stderr - `yuv420p(progressive)` against
  `yuv420p(tv, bt709, progressive)`: an ffprobe already in the wheel.
- **Reading a video back:** `QVideoSink` delivers every frame of a 1080p or 4K file at playback rate
  1 with exact stamps (33.333 ms); frames are NV12 (hardware decoding). Map, copy the planes, unmap,
  and pause the player while measuring: a probe that kept up to 8 frames pending at 1080p ran out of
  memory only when other processes had taken the machine's commit.
- **A 4K tour end to end** (3840 x 2160, 30 fps, Ultra, a 6 s orbit, the MP4 at Best and a PNG of
  every frame written by the same run): 180 of 180 frames in 61.9 s; the process's peak working set
  3.3 GB and peak commit 7.1 GB (the PNG writers' queue included); the GPU from 0.76 to 3.65 GB;
  109.9 Mbit/s, level 5.1, 50.0 / 49.7 dB (mean / worst frame), detail kept 0.987 / 0.978. No
  out-of-memory error this time (#809 records one on a machine short of commit).
- **Not measured:** a machine whose Media Foundation picks a hardware encoder; a Windows N edition
  (no H.264: MPEG-4 Part 2, whose constant quality is Qt's `qscale`); 60 fps and 1440p sizes at
  constant quality; players beyond Qt's own decoder.
