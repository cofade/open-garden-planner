## 13. Retired feature: US-B7 Paper Space (dropped in PR #191 review)

Source: `docs/roadmap.md` (~line 2277, "US-B7 dropped during manual-test review"),
CLAUDE.md Package B note.

- US-B7 added a "Layout" tab (Ctrl+4) with one page / viewport / title block / scale
  bar. Manual testing showed the abstraction added **no user-visible value** over what
  `pdf_report_service` already does (multi-page PDF at A4/A3/Letter/Legal, fit-to-page,
  built-in scale bar). Everything was removed from PR #191 before merge.
- Durable residue you may trip over: `FILE_VERSION` stayed at **1.4** (the bezier + arc
  item types from the same phase are real); the loader **silently ignores** a
  `paper_layouts` key found in `.ogp` files saved by short-lived draft builds. If you
  see that ignore branch, it is intentional — don't "implement" it and don't warn on it.
- Status: retired. Do not re-propose a second-space CAD print workflow without new
  evidence the PDF pipeline is insufficient.

---

