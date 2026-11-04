## Case study: frozen code absent from a passing SBOM (#454, 2026-10-14)

**Symptom.** The inventory check passed for 47 components, but an independent review
of the newly built executable found frozen setuptools/packaging, development dependencies
and setuptools-vendored copies absent from both the SBOM and notices.

**Wrong theories.** No alternate runtime theory was adopted. The earlier special case
for vendored importlib-metadata described one observed hook; it was not an inventory.

**Evidence.** Reading the actual executable PYZ and physical collected source paths gave
`[490-OWNERS] packaging 26.3; setuptools._vendor.packaging 26.0; zipp 3.23.0`.
The independent artifact regression failed with `frozen setuptools has no inventory component`.

**Root cause.** The metadata collector and synthetic tests both used the same declared
Requires-Dist closure. PyInstaller's actual code collection independently included hook
and vendored files, so a check of the declared set could not detect those omissions.

**Fix.** Attribute actual Analysis pure/binary/data/runtime-script paths through wheel
RECORD ownership, with nested vendored precedence. Bundle those owners' exact metadata
and declared license texts. Record module/file ownership and verify the manifest against
the actual executable PYZ; tie vendored versions to their locked containing wheel rather
than a name-based exemption. Preserve distinct installed/vendored versions. Temporary
probe output stays out of committed code.

**Lesson.** A fixture generated from the expected inventory cannot prove actual shipped
composition. Inspect the executable and physical source ownership independently.


