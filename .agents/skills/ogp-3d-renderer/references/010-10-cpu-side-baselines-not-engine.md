## 10. CPU-side baselines (not engine)

`bench_small.ogp` (99 items): plan load 0.1–0.5 s, ground bake 0.1–0.3 s, mesh build ~0.5 s
for 185k triangles (Linux and Windows alike). `bench_large.ogp` (425 items): 2.28 s for 1.46M
triangles (`scripts/bench_view3d.py`, deleted with the spike in L1.10; its last run, on the
L1.9 tree: small 260 ms for 205,032 triangles, large 1,523 ms for 1,429,032, the spike's
build).

