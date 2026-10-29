## Case study: translucent path rims and render measurements after L4 (#617/#600/#603/#609/#626/#536)

**Symptom.** A half-opacity gravel path had a dark middle; workspace click and
reload tests compared different plant generations; a Windows memory gate read
2.06 MB/cycle, just above its unchanged 2.0 bound; first expose and fractional-DPR
probes made environmental assumptions.
**Rejected assumptions.** An odd-even ring would remove all underpaint, a
registry rebuild would reproduce admitted forged LODs, and 20 ms of event pumping
would retire all texture uploads. Each was contradicted by a measured case.
**Evidence.** `[617-RIM] gravel opacity=0.5 alpha=255 max_delta=26` and dirt 8.
The odd-even attempt failed bends/crossings; exact vector subtraction cost
6,628 ms at 4,096 points. The downloaded failed CI curve alternated near
661/693 MB. After two presented frames per cycle, GPU/WARP read 0.000/0.030
MB/cycle, while retained-texture controls read 32.190/32.195. No bound changed.
The baseline selection module reported four expected failures against v0.
**Root cause and fix.** Primitive underpaint survives alpha composition. A
512-pixel device-tile mask removes the entire inner stroke before the rim is
composited. Render waits now include forge, camera LOD and ground; CPU rays use
sink-held triangles with the shader wind at zero. Document replacement re-admits
forged plants; unchanged same-document passes remain upload-free. Pin both Qt
scale factors, fit desktop windows, and retry driver-only startup refusals within
one total deadline. The product host's idle contract remains unchanged.
**Lesson.** Measure the production state at a defined boundary. Neither a
plausible alternative mesh nor a fixed sleep establishes that boundary.

