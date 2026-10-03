"""Dormant Qt Quick 3D renderer spike — evidence tooling for ADR-047 (Phase 17, L0).

Reached ONLY through ``--spike-q3d`` (``main.py``); never imported at app
startup (pinned by ``tests/unit/test_spike_q3d_isolation.py``). Its job is to
prove, with measurements and screenshots, whether Qt Quick 3D can carry the
"Lush Cinematic" 3D mode — inside the frozen exe, next to WebEngine, within
the budgets ADR-047 wrote down before any evidence was gathered.

``meshes`` is Qt-free (numpy, scene frame) — the procedural prototypes that
graduate into ``core/`` in Package L1. Everything that touches Qt Quick 3D
lives in ``quick`` (the spike's single engine-import module). Spike strings are
deliberately untranslated (dev evidence tooling — the ADR-038 exemption). The
package is deleted when Package L1.2 lands the production engine boundary.
"""
