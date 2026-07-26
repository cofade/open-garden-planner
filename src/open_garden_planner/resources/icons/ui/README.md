# UI Icon Set — House Style Contract (#279, ADR-039)

This directory holds every chrome icon (toolbar tools, constraint tools,
gallery category chips, menu actions). The contract below is **binding** —
it is enforced mechanically by `scripts/check_icon_conformance.py` and pinned
into the test battery by `tests/unit/test_icon_conformance.py`.

## The contract

- **Canvas**: `viewBox="0 0 24 24"`, square; keep ~1px optical padding so
  strokes never clip at the edge.
- **Geometry**: stroke-first line icons — root attrs exactly
  `fill="none" stroke="currentColor" stroke-width="2"
  stroke-linecap="round" stroke-linejoin="round"`. Per-element
  `stroke-width` overrides only within **[1.25, 2.5]**. Small solid dots
  (`fill="currentColor"`) are allowed as emphasis; nothing larger.
- **Colors — exactly three values, anywhere**: `none`, `currentColor`
  (the primary line, tinted at runtime from the active theme), and the
  **accent sentinel `#3D8B37`** (replaced with the theme accent at render
  time; use sparingly — at most one accent element per icon).
- **Never**: raster embeds/data URIs, `<text>` (i18n rule — icons are
  language-neutral), `<style>`, `<defs>`/`<use>`/`<g>`, gradients, filters,
  baked colors, editor metadata.
- **Naming**: semantic snake_case matching the name the code requests
  (`select.svg`, `constraint_distance.svg`, …) — not the upstream name.

## Rendering rule

Never feed these files to `QSvgRenderer` directly — it paints raw
`currentColor` **black**. All rendering goes through the provider
`ui/icons.py` (`get_icon` / `get_pixmap`), which substitutes the tokens
from the active theme before rasterizing.

## Adding an icon

1. Vendor from Tabler (https://tabler.io/icons, MIT — note glyph name +
   release tag) or author bespoke at 24×24 on this contract.
2. Rename to the semantic name and run
   `venv/Scripts/python.exe scripts/normalize_icons.py <file> --out src/open_garden_planner/resources/icons/ui/`.
3. Add the `PROVENANCE.md` entry — **no entry, no merge**.
4. Register the name where it is used (toolbar/gallery/menu code).
5. `venv/Scripts/python.exe scripts/check_icon_conformance.py` and the test
   battery must be green.

## Licensing

Vendored glyphs: Tabler Icons, MIT — see `LICENSE-tabler-icons.txt`.
Bespoke icons: original work, project license (GPL-3.0-or-later).
