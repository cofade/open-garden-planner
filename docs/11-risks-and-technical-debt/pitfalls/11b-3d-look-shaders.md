# Pitfalls: 3D look, shaders and build (continued)

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Continues [11-3d-look-ground-build.md](11-3d-look-ground-build.md) from PF-L3D-40. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-L3D-40

- **Rule:** Never reference `CustomMaterial` uniforms inside top-level GLSL helper functions: Qt Quick 3D splices declared material uniforms into the generated shader after user helper functions, so pass uniform values in as parameters from `MAIN()` / `IBL_PROBE()`.
- **Pinned by:** `tests/ui/test_quick3d_host.py`; `tests/integration/test_quick3d_selftest.py`
- **Source:** #941, #992; ADR-059 addendum
- **Status:** standing
- **Legacy:** none (new entry)

### PF-L3D-41

- **Rule:** Every `CustomMaterial` in `Garden.qml` (including `shaderWarmer` instances) must declare every `u[A-Z]...` uniform referenced by its bound vertex and fragment shaders and declare no dead uniform.
- **Pinned by:** `tests/unit/test_quick3d_qml.py::test_every_custom_material_declares_every_uniform_its_shaders_use`
- **Source:** #992; ADR-059 addendum
- **Status:** standing
- **Legacy:** none (new entry)
