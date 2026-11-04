## 9. Packaging (PyInstaller)

- The spec needs a data loop for the QML + shader files and hidden imports for
  `PyQt6.QtQuick`, `QtQml`, `QtQuick3D` (`QtQuickWidgets` left the spec with the spike in
  L1.10: the product never uses a `QQuickWidget`).
- **The Qt Quick 3D runtime already ships in today's bundle.** Windows dist, branch vs master
  built in the same job: 626.2 MB vs 624.5 MB → **+1.7 MB** (only `QtQuick3D.pyd` and the QML
  files are new). Quick3D + ShaderTools files: 21.1 MB (Windows), ~23 MB (Linux); the Qt 3D DLLs
  it replaced: 5.8 MB (L1.10 removed them; the bundle before and after is ADR-048's closing
  addendum).
- Frozen Windows exe with the spike bundled: the `--selftest` gate exited 0 (ogp-change-control
  §2.8 is its home); it exits 0 without the spike and the Qt 3D wheels too (L1.10, ADR-048's
  closing addendum).
- **L1.2:** the production package adds its five QML and shader files (a data loop in
  `installer/ogp.spec`) and eleven modules: **+79,008 bytes** (650,815,562 vs 650,736,554,
  same machine, same day, same shell). `--selftest` now also RENDERS one hidden 160 × 120
  frame from the bundle's QML and shaders and judges its pixels (§12); frozen exe 2.9–4.1 s on
  an RTX 4070 and 2.9–3.3 s on WARP for the whole command (6.1–7.2 s on a busy machine).
- **A local bundle's content depends on PATH (L1.2, review round 1).** Built from Git Bash it
  carries `libcrypto-3-x64.dll` and `libssl-3-x64.dll` (5,531,448 bytes) — byte for byte the
  files in Git for Windows' `mingw64/bin`, which is on that shell's PATH; built from a plain
  PowerShell process it does not (650,815,562 vs 645,326,627 bytes, 2,450 vs 2,448 files).
  Both exes pass the smoke and `--selftest`. Compare bundle sizes only between builds made
  from the same shell.

