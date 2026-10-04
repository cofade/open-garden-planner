"""L0.2 measurements beyond the shot board (ADR-047 GO criteria 2, 3, 5, 6, 7, 10).

Each function returns plain numbers for ``metrics.json``; none of them decides
GO by itself — the ADR's table does, on the owner's hardware where a criterion
says so. Numbers measured on Mesa llvmpipe or Windows WARP are software
rendering: ratios and pass/fail facts carry over, absolute times do not.

* ``pick_probe`` — criterion 7: 20 picks in a top-down orthographic view; the
  expected hit is computed on the CPU (topmost triangle under a vertical ray
  over every pickable mesh), so a correct engine pick must name the same item.
* ``update_bench`` — criterion 6: GUI-thread cost of replacing a 100k-vertex
  geometry (``NumpyGeometry.set_mesh``), and the time until the next frame.
* ``second_window`` — a second 3D window in the same process, showing the same view
  (criterion 5 context: L1.3 keeps one host alive instead).
* ``coexist_probe`` — criterion 2 (M1): a ``QWebEngineView`` and the 3D view
  in one process, the way the app imports WebEngine before ``QApplication``.
* ``pan_bench`` — criterion 3 (M2): 2D canvas pan cost with and without a
  ``QQuickWidget`` in the same top-level window.
* ``soak`` — criterion 10: show/hide and model churn.
* ``close_while_animating`` — criterion 10: the wind animation must really run
  (wind time and frames advance), then the window is closed and the event loop
  quits while it runs; judged on that exit code.

Every probe that moves the camera, preset, ground or sun runs inside
``SpikeRenderer.preserved_state`` so no measurement depends on flag order.
"""

from __future__ import annotations

import os
import statistics
import sys
import time
from typing import Any

import numpy as np

from open_garden_planner.spike_q3d import meshes as M


def _pump(ms: int) -> None:
    from PyQt6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def _stats(values: list[float]) -> dict[str, float]:
    """Median and max; a p95 only from 20 samples on (below that it IS the max)."""
    if not values:
        return {}
    ordered = sorted(values)
    out = {"n": len(ordered), "median": round(statistics.median(ordered), 2),
           "max": round(ordered[-1], 2)}
    if len(ordered) >= 20:
        out["p95"] = round(ordered[round(0.95 * (len(ordered) - 1))], 2)
    return out


def rss_mb() -> float | None:
    """Resident set size of this process in MiB (None where unmeasured)."""
    if sys.platform.startswith("linux"):
        with open("/proc/self/statm", encoding="ascii") as fh:
            pages = int(fh.read().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / 2**20, 1)
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]

        counters = _Counters()
        counters.cb = ctypes.sizeof(_Counters)
        windll = ctypes.windll  # type: ignore[attr-defined]
        # Declared types matter on 64-bit: the default int restype truncates the
        # pseudo-handle and the call fails (Windows evidence run v3 read None).
        windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        query = windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(_Counters), wintypes.DWORD]
        query.restype = wintypes.BOOL
        ok = query(windll.kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
        return round(counters.WorkingSetSize / 2**20, 1) if ok else None
    return None


# ── criterion 7: picking ────────────────────────────────────────────────


def _triangles(mesh: M.MeshData) -> np.ndarray:
    return mesh.positions[mesh.indices.reshape(-1, 3)]  # (T, 3, 3), scene frame


def cpu_topmost_hit(tris_by_id: dict[str, np.ndarray], x: float, y: float
                    ) -> tuple[str | None, float]:
    """Item whose geometry a vertical ray at scene ``(x, y)`` meets first."""
    best_id, best_z = None, -np.inf
    p = np.array([x, y], np.float64)
    for item_id, tri in tris_by_id.items():
        a, b, c = (tri[:, k, :].astype(np.float64) for k in range(3))
        v0, v1, v2 = c[:, :2] - a[:, :2], b[:, :2] - a[:, :2], p - a[:, :2]
        d00, d01, d11 = (v0 * v0).sum(1), (v0 * v1).sum(1), (v1 * v1).sum(1)
        d02, d12 = (v0 * v2).sum(1), (v1 * v2).sum(1)
        den = d00 * d11 - d01 * d01
        ok = np.abs(den) > 1e-9
        den = np.where(ok, den, 1.0)
        u = (d11 * d02 - d01 * d12) / den
        v = (d00 * d12 - d01 * d02) / den
        inside = ok & (u >= -1e-6) & (v >= -1e-6) & (u + v <= 1 + 1e-6)
        if not inside.any():
            continue
        z = a[:, 2] + u * (c[:, 2] - a[:, 2]) + v * (b[:, 2] - a[:, 2])
        top = float(z[inside].max())
        if top > best_z:
            best_id, best_z = item_id, top
    return best_id, best_z


def _top_target(tri: np.ndarray) -> tuple[float, float] | None:
    """Centroid of the highest upward-facing triangle (a point ON the mesh)."""
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(n, axis=1)
    up = (length > 1e-6) & (np.abs(n[:, 2]) > 0.35 * np.maximum(length, 1e-9))
    if not up.any():
        return None
    cent = tri.mean(axis=1)
    k = int(np.argmax(np.where(up, cent[:, 2], -np.inf)))
    return float(cent[k, 0]), float(cent[k, 1])


def _oracle_meshes(models: list) -> dict[str, np.ndarray]:
    """Every pickable model's triangles, merged per item id (frame + glass included)."""
    merged: dict[str, list[np.ndarray]] = {}
    for model in models:
        if model.geometry.mesh.vertex_count:
            merged.setdefault(model.itemId, []).append(_triangles(model.geometry.mesh))
    return {item_id: np.concatenate(parts) for item_id, parts in merged.items()}


def _robust_hit(tris: dict[str, np.ndarray], x: float, y: float,
                eps: float = 0.5) -> tuple[str | None, float] | None:
    """The oracle's answer if it is the same 0.5 cm around the point, else None."""
    hit, z = cpu_topmost_hit(tris, x, y)
    for dx, dy in ((eps, 0.0), (-eps, 0.0), (0.0, eps), (0.0, -eps)):
        if cpu_topmost_hit(tris, x + dx, y + dy)[0] != hit:
            return None
    return hit, z


def adversarial_targets(tris: dict[str, np.ndarray], k: int = 10,
                        grid: int = 9) -> list[tuple[float, float, str | None, str]]:
    """Points inside a tall item's bounding box whose topmost hit is ANOTHER item or nothing.

    A picker that only tests bounding boxes returns the tall item there; a correct
    one returns what the oracle says. The senior review measured that the easy
    targets alone let a bounding-box picker score 18/20.
    """
    tall = sorted(((float(t[..., 2].max()), item_id) for item_id, t in tris.items()
                   if not item_id.startswith("lawn-grass")), reverse=True)
    out: list[tuple[float, float, str | None, str]] = []  # (x, y, expected, box owner)
    for _, item_id in tall:
        flat = tris[item_id].reshape(-1, 3)
        lo, hi = flat.min(axis=0), flat.max(axis=0)
        for fx in np.linspace(0.06, 0.94, grid):
            for fy in np.linspace(0.06, 0.94, grid):
                x = float(lo[0] + fx * (hi[0] - lo[0]))
                y = float(lo[1] + fy * (hi[1] - lo[1]))
                answer = _robust_hit(tris, x, y)
                if answer is not None and answer[0] != item_id:
                    out.append((x, y, answer[0], item_id))
                    break
            else:
                continue
            break
        if len(out) >= k:
            break
    return out


def top_down_pixel(x: float, y: float, center: tuple[float, float], px_per_cm: float,
                   size: tuple[int, int]) -> tuple[float, float]:
    """Where an orthographic top-down camera puts scene point (x, y) — our own math."""
    w, h = size
    return w / 2 + (x - center[0]) * px_per_cm, h / 2 - (y - center[1]) * px_per_cm


def pick_probe(renderer: Any, width: float, height: float, n: int = 20) -> dict:
    with renderer.preserved_state():
        return _pick(renderer, width, height, n)


def _pick(renderer: Any, width: float, height: float, n: int) -> dict:
    from open_garden_planner.spike_q3d.probes import _image_to_array

    tris = _oracle_meshes(renderer.models)
    w, h = renderer.view_size()
    center = (width / 2, height / 2)
    mag = min(w / width, h / height) * 0.98
    renderer.set_top_down(center, mag)
    renderer.wait_frames(4, label="pick_view")

    def click(x: float, y: float, z: float) -> tuple[dict, float]:
        px, py = renderer.project(x, y, z)
        ox, oy = top_down_pixel(x, y, center, mag, (w, h))
        hit = renderer.pick(px, py)
        return hit, float(np.hypot(px - ox, py - oy))

    rows, times, proj_err = [], [], []
    for item_id in sorted(tris):
        if len(rows) >= n or item_id.startswith("lawn-grass"):
            continue  # grass blades are pickable but too thin to aim at
        target = _top_target(tris[item_id])
        if target is None:
            continue
        expected, z = cpu_topmost_hit(tris, *target)
        if expected != item_id:
            continue  # occluded from above: aim only at objects a user can see
        px, py = renderer.project(target[0], target[1], z)
        if not (0 <= px < w and 0 <= py < h):
            continue
        t0 = time.perf_counter()
        hit, err_px = click(target[0], target[1], z)
        times.append((time.perf_counter() - t0) * 1000.0)
        proj_err.append(err_px)
        got = hit.get("id") if hit.get("hit") else None
        err = None
        if got:  # engine frame (E, up, -N) → scene (E, N, up)
            err = round(float(np.hypot(hit["x"] - target[0], -hit["z"] - target[1])), 2)
        rows.append({"target": item_id, "hit": got, "ok": got == item_id, "xy_err_cm": err})
    hits = sum(r["ok"] for r in rows)

    adversarial = []
    for x, y, expected, owner in adversarial_targets(tris):
        hit, err_px = click(x, y, 0.0)
        proj_err.append(err_px)
        got = hit.get("id") if hit.get("hit") else None
        adversarial.append({"x": round(x, 1), "y": round(y, 1), "in_box_of": owner,
                            "expected": expected, "hit": got, "ok": got == expected})

    # The same picks after every model was removed and re-added: pins the
    # re-attach rule in SpikeRenderer.set_models (0/20 without it) — by picks AND pixels.
    before = _image_to_array(renderer.grab(label="pick_before_detach"))
    models = renderer.models
    renderer.set_models([])
    renderer.wait_frames(2, label="pick_detach")
    renderer.set_models(models)
    renderer.wait_frames(3, label="pick_reattach")
    after = _image_to_array(renderer.grab(label="pick_after_reattach"))
    again = 0
    for row in rows:
        target = _top_target(tris[row["target"]])
        if target is None:  # cannot happen: rows only hold targets that had one
            continue
        z = cpu_topmost_hit(tris, *target)[1]
        hit = renderer.pick(*renderer.project(target[0], target[1], z))
        again += bool(hit.get("hit")) and hit.get("id") == row["target"]
    errs = [r["xy_err_cm"] for r in rows if r["xy_err_cm"] is not None]
    return {"n": len(rows), "hits": hits, "hits_after_reattach": again,
            "reattach_frame_diff": round(float(np.abs(before - after).mean()), 3),
            "adversarial_n": len(adversarial),
            "adversarial_hits": sum(a["ok"] for a in adversarial),
            "adversarial_misses": [a for a in adversarial if not a["ok"]],
            "max_xy_err_cm": round(max(errs), 2) if errs else None,
            "max_projection_err_px": round(max(proj_err), 3) if proj_err else None,
            "pick_ms": _stats(times), "misses": [r for r in rows if not r["ok"]],
            "camera": "orthographic top-down"}


# ── criterion 6: 100k-vertex update ─────────────────────────────────────


def _grid_mesh(side: int, phase: float) -> M.MeshData:
    xs = np.linspace(-1500.0, -500.0, side, dtype=np.float32)
    gx, gy = np.meshgrid(xs, xs)
    z = (25.0 * np.sin(gx / 90.0 + phase) * np.cos(gy / 110.0)).astype(np.float32)
    pos = np.stack([gx.ravel(), gy.ravel(), z.ravel()], axis=1)
    nrm = np.tile(np.array([0, 0, 1], np.float32), (pos.shape[0], 1))
    col = np.tile(np.array([0.25, 0.45, 0.18, 1.0], np.float32), (pos.shape[0], 1))
    uv = np.zeros((pos.shape[0], 2), np.float32)
    i = np.arange(side - 1)
    a = (i[:, None] * side + i[None, :]).ravel().astype(np.uint32)
    quads = np.stack([a, a + 1, a + side, a + 1, a + side + 1, a + side], axis=1)
    return M.MeshData(pos, nrm, col, uv, quads.ravel().astype(np.uint32))


def update_bench(renderer: Any, side: int = 317, runs: int = 10) -> dict:
    with renderer.preserved_state():
        return _update_bench(renderer, side, runs)


def _update_bench(renderer: Any, side: int, runs: int) -> dict:
    from open_garden_planner.spike_q3d.quick import NumpyGeometry, SpikeModel

    saved = renderer.models
    geom = NumpyGeometry(_grid_mesh(side, 0.0))
    renderer.set_models([*saved, SpikeModel("update-bench", geom, "vc", False)])
    renderer.wait_frames(2, label="update_bench_add")
    cpu, to_frame = [], []
    for k in range(runs):
        mesh = _grid_mesh(side, 0.4 * (k + 1))  # built outside the timed region
        t0 = time.perf_counter()
        geom.set_mesh(mesh)
        t1 = time.perf_counter()
        renderer.wait_frames(1, label=f"update_{k}")
        cpu.append((t1 - t0) * 1000.0)
        to_frame.append((time.perf_counter() - t0) * 1000.0)
    renderer.set_models(saved)
    renderer.wait_frames(1, label="update_bench_remove")
    return {"vertices": side * side, "triangles": 2 * (side - 1) ** 2,
            "set_mesh_ms": _stats(cpu), "to_next_frame_ms": _stats(to_frame)}


# ── criterion 5: warm start ─────────────────────────────────────────────


def _fresh_models(models: list) -> list:
    from open_garden_planner.spike_q3d.quick import NumpyGeometry, SpikeModel

    return [SpikeModel(m.itemId, NumpyGeometry(m.geometry.mesh), m.kind, m.castsShadows)
            for m in models]


def second_window(renderer: Any, ground: Any, width: float, height: float, log: Any) -> dict:
    """The same view in a second window of the same process.

    Not "warm start": the product keeps ONE 3D host alive (L1.3), and a warm
    start is a second launch with populated disk caches (``shader_caches`` in the
    metrics says which a run was). This measures what a second window costs —
    with the camera, sun, sky and look the first one shows (the first version
    rendered the QML defaults: a different frame, senior review).
    """
    from open_garden_planner.spike_q3d.quick import SpikeRenderer

    t0 = time.perf_counter()
    second = SpikeRenderer(renderer.host_kind, renderer.size,
                           frame_timeout_s=renderer.frame_timeout_s, log=log)
    second.set_models(_fresh_models(renderer.models))
    second.set_ground(ground, 0, 0, width, height)
    second.copy_view_from(renderer)
    second.show()
    second.wait_frames(2, label="second_window_first_frame")
    second.grab(label="second_window_first_ready")  # a readback: the frame is finished
    result = {"qml_load_ms": round(second.qml_load_ms, 1),
              "first_frame_ms": round(second.first_frame_ms or -1.0, 1),
              "first_ready_ms": round((time.perf_counter() - (second.shown_at or t0)) * 1000.0, 1),
              "total_ms": round((time.perf_counter() - t0) * 1000.0, 1)}
    second.hide()
    second.set_models([])
    _pump(50)
    return result


# ── criterion 2 (M1): WebEngine + Quick 3D in one process ───────────────


def _center_rgb(image: Any) -> tuple[int, int, int]:
    c = image.pixelColor(image.width() // 2, image.height() // 2)
    return c.red(), c.green(), c.blue()


def coexist_probe(renderer: Any, log: Any, timeout_s: float = 30.0) -> dict:
    from PyQt6.QtCore import QCoreApplication, QEventLoop, Qt, QTimer
    from PyQt6.QtWebEngineWidgets import QWebEngineView

    from open_garden_planner.spike_q3d.probes import _image_to_array, _luma

    want = (58, 123, 213)  # #3a7bd5 — a page colour nothing else here uses
    # The 3D half is judged against the SAME view rendered before WebEngine
    # started: "mean luma > 20" also passed an empty frame (senior review).
    renderer.wait_frames(3, label="coexist_reference")
    reference = _image_to_array(renderer.grab(label="coexist_reference"))
    view = QWebEngineView()
    view.resize(320, 200)
    state: dict[str, Any] = {"loaded": None}
    loop = QEventLoop()

    def _done(ok: bool) -> None:
        state["loaded"] = ok
        loop.quit()

    view.loadFinished.connect(_done)
    view.setHtml("<html><body style='margin:0;background:#3a7bd5'></body></html>")
    view.show()
    QTimer.singleShot(int(timeout_s * 1000), loop.quit)
    loop.exec()

    def _web_rgb() -> tuple[int, int, int]:
        deadline = time.perf_counter() + timeout_s / 2
        rgb = _center_rgb(view.grab().toImage())
        while max(abs(a - b) for a, b in zip(rgb, want, strict=True)) > 8 \
                and time.perf_counter() < deadline:
            _pump(100)
            rgb = _center_rgb(view.grab().toImage())
        return rgb

    before = _web_rgb()
    log("coexist_web", loaded=state["loaded"], rgb=before)
    renderer.wait_frames(3, label="coexist_3d")
    frame = _image_to_array(renderer.grab(label="coexist_3d"))
    frame_diff = float(np.abs(frame - reference).mean())
    structure = float(_luma(reference).std())
    after = _web_rgb()

    def _close(rgb: tuple[int, int, int]) -> bool:
        return max(abs(a - b) for a, b in zip(rgb, want, strict=True)) <= 8

    view.close()
    view.deleteLater()
    _pump(50)
    return {
        "share_opengl_contexts": bool(QCoreApplication.testAttribute(
            Qt.ApplicationAttribute.AA_ShareOpenGLContexts)),
        "quick_graphics_api": renderer.graphics_api(),
        "web_loaded": state["loaded"], "web_rgb_before_3d": before, "web_rgb_after_3d": after,
        "web_ok": _close(before) and _close(after),
        "frame3d_diff_vs_reference": round(frame_diff, 3),
        "frame3d_reference_luma_std": round(structure, 1),
        "frame3d_ok": frame_diff < 2.0 and structure > 10.0,
    }


# ── criterion 3 (M2): 2D pan cost with a QQuickWidget in the window ─────


def pan_bench(scene: Any, renderer: Any, ground: Any, width: float, height: float,
              log: Any, steps: int = 120) -> dict:
    from PyQt6.QtWidgets import QApplication, QMainWindow, QSplitter, QWidget

    from open_garden_planner.spike_q3d.quick import SpikeRenderer
    from open_garden_planner.ui.canvas.canvas_view import CanvasView

    def run(with_3d: bool) -> list[float]:
        win = QMainWindow()
        split = QSplitter()
        canvas = CanvasView(scene)
        split.addWidget(canvas)
        side: Any = None
        if with_3d:
            side = SpikeRenderer("widget", (480, 540), frame_timeout_s=renderer.frame_timeout_s,
                                 log=log)
            side.set_models(_fresh_models(renderer.models))
            side.set_ground(ground, 0, 0, width, height)
            split.addWidget(side.widget)
        else:
            split.addWidget(QWidget())
        win.setCentralWidget(split)
        win.resize(1200, 600)
        win.show()
        if side is not None:
            side.wait_frames(2, label="pan_3d_ready")
        _pump(300)
        canvas.fit_in_view()
        canvas.set_zoom(canvas.zoom_factor * 4.0)
        bar = canvas.horizontalScrollBar()
        lo, hi = bar.minimum(), bar.maximum()
        app = QApplication.instance()
        times = []
        for k in range(steps):
            t0 = time.perf_counter()
            bar.setValue(lo + (hi - lo) * ((k * 7) % steps) // max(steps - 1, 1))
            canvas.viewport().update()
            # The flush (and, with a QQuickWidget in the window, the RHI
            # composition of the whole window) happens while events are
            # processed — a synchronous repaint() never sees it: measured
            # 0.08 ms "with 3D" vs 5.45 ms without, i.e. it skipped the flush.
            app.processEvents()
            app.processEvents()
            times.append((time.perf_counter() - t0) * 1000.0)
        win.close()
        if side is not None:
            side.set_models([])
        win.deleteLater()
        _pump(100)
        return times

    without = run(False)
    with3d = run(True)
    med_without = statistics.median(without)
    med_with = statistics.median(with3d)
    return {"steps": steps, "without_3d_ms": _stats(without), "with_3d_ms": _stats(with3d),
            "ratio_median": round(med_with / med_without, 3) if med_without > 0 else None,
            "note": "per pan step incl. flush/composition; vsync can cap real-GPU numbers"}


# ── criterion 10: soak ───────────────────────────────────────────────────


def rss_tail_slope(curve: list[float | None]) -> float | None:
    """MB per reload over the second half of an RSS curve (least squares).

    A leak keeps climbing at its per-reload size; an allocator settles after a
    few steps, so the first half (and a single step) is not a trend. None when
    there are fewer than three points or an unreadable RSS.
    """
    tail = curve[len(curve) // 2:]
    if len(tail) < 3 or any(v is None for v in tail):
        return None
    x = np.arange(len(tail), dtype=np.float64)
    return round(float(np.polyfit(x, np.asarray(tail, np.float64), 1)[0]), 2)


def soak(renderer: Any, cycles: int, reload: Any = None) -> dict:
    """Criterion 10: ``cycles`` hide/show cycles; every fifth one empties the scene
    and refills it.

    With ``reload`` (a callable returning fresh models) the refill is a full
    project reload — plan read from disk into a new scene, ground re-baked, every
    model and geometry built new — so ``--soak 50`` is the criterion's "50
    show/hide cycles, 10 project reloads", and the old geometries are released
    while the engine runs (the QML-vs-Python lifetime risk the soak exists for).
    """
    import gc

    models = renderer.models
    first_count = len(models)
    gc.collect()  # cyclic garbage is not a leak: collect before every reading
    rss_start = rss_mb()
    reentry, reload_ms, counts, rss_curve = [], [], [], []
    for k in range(cycles):
        renderer.hide()
        _pump(30)
        t0 = time.perf_counter()
        renderer.show()
        renderer.wait_frames(1, label=f"soak_show_{k}")
        reentry.append((time.perf_counter() - t0) * 1000.0)
        if k % 5 == 4:
            renderer.set_models([])
            renderer.wait_frames(1, label=f"soak_empty_{k}")
            if reload is not None:
                t0 = time.perf_counter()
                models = reload()
                reload_ms.append((time.perf_counter() - t0) * 1000.0)
                counts.append(len(models))
            renderer.set_models(models)
            renderer.wait_frames(1, label=f"soak_refill_{k}")
            gc.collect()
            rss_curve.append(rss_mb())
    gc.collect()
    rss_end = rss_mb()
    result = {"cycles": cycles, "reentry_ms": _stats(reentry), "rss_start_mb": rss_start,
              "rss_end_mb": rss_end, "rss_after_refill_mb": rss_curve}
    if reload is not None:
        result.update({"project_reloads": len(reload_ms), "reload_ms": _stats(reload_ms),
                       "models_per_reload_ok": all(c == first_count for c in counts),
                       "rss_tail_slope_mb_per_reload": rss_tail_slope(rss_curve)})
    return result


def close_while_animating(renderer: Any, app: Any, log: Any, frames: int = 8) -> dict:
    """Criterion 10's "app close while animating", measured instead of asserted.

    The wind animation must really run first (wind time and the frame counter
    advance — the first version returned a literal and the animation never
    ticked), then the window is closed and the event loop quits while it runs.
    A crash on that path takes the process down, so the witness is the PROCESS
    exit code (the driver and the render tier check it). ``event_loop_exit_code``
    is informational: ``app.exec()`` returns 0 on both quit paths.
    """
    from PyQt6.QtCore import QTimer

    renderer.set_animate(True)
    wind0, frames0 = float(renderer.root.property("windTime")), renderer.frames
    renderer.wait_frames(frames, label="animate_before_close")
    wind1, frames1 = float(renderer.root.property("windTime")), renderer.frames
    QTimer.singleShot(0, renderer.close)
    QTimer.singleShot(300, app.quit)
    code = int(app.exec())
    log("closed_while_animating", wind_time=round(wind1, 3), frames=frames1 - frames0,
        exit_code=code)
    return {"wind_time_before": round(wind0, 3), "wind_time_after": round(wind1, 3),
            "frames_while_animating": frames1 - frames0,
            "animation_advanced": wind1 > wind0 and frames1 - frames0 >= frames,
            "event_loop_exit_code": code}
