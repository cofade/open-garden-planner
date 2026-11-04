## Case study: a moved settings factory left the child isolation hook on its alias (audit A4, 2026-10-29)

**Symptom:** child-process tests failed before opening a settings store after
moving the factory into a shared leaf module. The synthetic macOS route also
left the seed store pointed into a previous test's temporary directory.

**Theories checked:** an import cycle or a broken settings singleton. Both were
refuted by the loader trace and the already-passing module-identity tests.

**Evidence:** the temporary tagged loader probe reported
`[A4-LOADER] factory=False registry_same=False` for the old compatibility
module, with `traceback.format_stack()` locating the call after its loader ran.
The loader's argument was the alias shell; `sys.modules` held the canonical
implementation. No store had been built. The macOS test restored a fixed list
of three service bindings while its rebinder intentionally updated every loaded
binding, including the newly shared model resolver.

**Root cause:** instrumentation and test cleanup followed former implementation
locations. Compatibility exports preserve runtime identity, but they do not move
an import-loader hook or a monkeypatch target automatically.

**Fix:** intercept `config.settings` before any consumer can build a store;
snapshot and restore every matching data-path binding in the synthetic macOS
test. Private handle spies likewise patch `vertex_handles`, their defining module.

**Lesson:** after extraction, update the instruments and their cleanup scopes.
Keep behavioral assertions intact; do not add runtime proxy machinery to satisfy
a spy attached to a retired implementation location. The focused regression
failed before this correction and passes after it. Temporary prints were removed.
