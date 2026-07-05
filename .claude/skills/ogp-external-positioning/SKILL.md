---
name: ogp-external-positioning
description: >
  Load when doing anything outward-facing for Open Garden Planner: writing or editing the
  README, release notes, announcements, wiki pages, or any public claim about capabilities;
  adding or upgrading a dependency (license-compatibility check); integrating or documenting
  an external service (Google Maps, plant APIs, weather); answering licensing questions
  (GPLv3, PyQt6, asset/texture licensing); positioning the project against other tools;
  or publishing benchmarks / accuracy claims. This skill is the anti-oversell guardian —
  it defines what may be claimed today, what must not be, and the trust obligations
  (checksums, unsigned installer, CI-owned releases) that come with every release.
---

# OGP External Positioning — licensing, claims, ecosystem, release trust

This skill governs everything the outside world sees. The internal rule is simple:
**every public statement must be traceable to shipped, tested code or a checked-in
document.** When in doubt, under-claim and link to the roadmap.

Date-stamped facts below were verified against the repo on **2026-07-05** (app version
1.23.0 per `pyproject.toml` and `src/open_garden_planner/__init__.py`). Re-verify with the
commands in "Provenance and maintenance" before relying on any volatile fact.

## 1. Licensing obligations (GPLv3 — load-bearing, not decorative)

| Fact | Source (verified) |
|------|-------------------|
| License is **GPL-3.0-or-later** | `LICENSE` (GPLv3 full text), `pyproject.toml` line 10: `license = {text = "GPL-3.0-or-later"}` + classifier "GPLv3+" |
| **Why**: PyQt6 is GPL/commercial dual-licensed; without a commercial Riverbank license the app **must** be GPLv3 | `docs/02-constraints/README.md` §2.1 ("PyQt6 (GPLv3) — GUI framework choice requires GPLv3 licensing for the project") and §2.4 rationale |
| GPL compliance is tracked as a **risk**, not a footnote | `docs/11-risks-and-technical-debt/README.md` §11.2: "PyQt6 licensing complexity (GPL/Commercial) — Likelihood Medium, Impact High — Use GPLv3, document clearly, ensure compliance" |
| All dependencies must be GPL-compatible and free | `docs/02-constraints/README.md` §2.2 ("all dependencies must be compatible", "No Budget … all dependencies must be free/open") |

**Consequences you must enforce:**

- Any dependency bundled into the PyInstaller exe becomes part of a GPLv3 distribution.
  A GPL-incompatible license (e.g. CC BY-NC for code, SSPL, proprietary SDKs) is a
  **blocker**, not a judgment call.
- **New-dependency checklist** (run before adding anything to `pyproject.toml` /
  `requirements.txt` / `installer/ogp.spec`):
  1. Identify the dependency's license (check PyPI metadata AND the repo's LICENSE file —
     PyPI classifiers are sometimes wrong).
  2. Confirm GPL-3.0 compatibility (MIT/BSD/Apache-2.0/LGPL/GPL: yes; permissive-with-
     advertising-clause, non-commercial, or source-available licenses: no or needs analysis).
  3. Confirm it survives PyInstaller bundling (it will be *distributed*, which is what
     triggers copyleft obligations).
  4. Note the check in the PR description. Cross-ref `ogp-change-control` for the PR gates.
- **Assets are licensed too.** Per ADR-006 (`docs/09-architecture-decisions/README.md`),
  object illustrations are AI-generated then converted to SVG, chosen partly for "no
  licensing issues"; per ADR-007, fill textures are tileable PNGs, "AI-generated or CC0
  sourced". §11.1 keeps **"Texture licensing for fill patterns?"** as an *open question*
  ("Use AI-generated or CC0/public domain textures, document sources"). Treat that as
  policy: any new texture/icon must be AI-generated in-project or CC0/public-domain,
  **with the source documented**. Do not import assets of unknown provenance.

## 2. Third-party service terms

All three integrations are optional enhancements — the app is offline-capable by
constraint (`docs/02-constraints` §2.1). Never present an online feature as core.

| Service | Used for | Key/config | Terms & obligations (as documented in-repo) |
|---------|----------|-----------|---------------------------------------------|
| **Google Maps** (JS API + Static Maps API) | Satellite background picker (`MapPickerDialog`, ADR-019) | `OGP_GOOGLE_MAPS_KEY` env var or project-root `.env` (python-dotenv). No fallback provider — feature disabled without a key. | §8.15 of `docs/08-crosscutting-concepts`: JS API display is free-tier; Static Maps burns the $200/month credit (~100k calls; app uses 1–9 per import via mosaic). **Never commit a key; never bundle the key into the release exe** — a pinned key is extractable via `strings` and abusable on the owner's bill. CI must not inject the secret into build artifacts. Each user obtains their own key. |
| **Plant APIs**: Trefle.io → Perenual → Permapeople (fallback chain in that order) | Online plant species search | `TREFLE_API_TOKEN`, `PERENUAL_API_KEY`, `PERMAPEOPLE_KEY_ID`/`_SECRET` (env or `.env`) | `docs/03-context-and-scope/PLANT_API_SETUP.md`: Trefle — free with **attribution**; Perenual — free personal/commercial; Permapeople — free **non-commercial**, data **CC BY-SA 4.0**, requires attribution + link-back. §11.2 documents the deprecation mitigation: "Fallback chain: Trefle → Permapeople → Bundled DB". A bundled species DB (118 records, ADR-014) exists as the offline layer. |
| **Open-Meteo** (`api.open-meteo.com/v1/forecast`) | Weather forecast widget + frost alerts (US-12.1/12.2) | No key required | Verified in `src/open_garden_planner/services/weather_service.py` (the URL is pinned and HTTPS-enforced). The repo docs do not restate Open-Meteo's usage terms — if you publish anything about the weather feature, check open-meteo.com's current terms yourself; do not invent them. |

**Rule:** when you name a provider in public text, name the one actually in the code.
"Uses a weather API" → wrong; "uses Open-Meteo" → right (and re-verify with the grep in
Provenance if the service layer has been touched).

## 3. What is genuinely novel vs known — strict claim labels

Be honest about the ecosystem. Positioning that survives scrutiny beats positioning that
sounds good.

**Known prior art — never imply OGP invented these:**
- Commercial garden planners (subscription web/desktop tools) — OGP's differentiators are
  price (free), openness (GPLv3, human-readable JSON `.ogp`), and metric precision, per
  the README's own framing.
- Generic CAD (snapping, fillet/chamfer, bezier/arc tools, DXF) — OGP *ports* CAD
  conventions to gardening; the CAD techniques themselves are standard (the roadmap even
  cites FreeCAD's Sketcher as a reference).
- MCP desktop integrations in general — MCP servers for desktop tools exist; the pattern
  is not OGP's invention.

**Candidate novelty (label as "to our knowledge" — plausible but unproven uniqueness):**
a desktop CAD-grade garden planner that **embeds a live MCP server in the running GUI**,
so any MCP client (Claude, Cursor, …) can read, query, and *see* (rendered PNG) the plan
currently open on screen. Verified basis: ADR-033 (embedded streamable-HTTP FastMCP server,
127.0.0.1-only, on by default, main-thread marshaling bridge) and ADR-034 + addenda
(curated schema, UUID addressing, spatial queries, diagnostics, `render_canvas_image`).
Nobody has done a prior-art survey — so the claim ceiling is "to our knowledge, the first
garden planner with…", never "the first" flat.

**Claimable TODAY (implemented, tested, shipped as of v1.23.0):**

| Claim | Evidence |
|-------|----------|
| Read-only MCP surface: `get_plan_summary`, `list_objects`, `get_object`, spatial tools, `get_diagnostics`, `render_canvas_image` | US-D1.1–D1.3 shipped (v1.21–1.23, PRs #239/#241/#242); integration tests incl. real MCP client end-to-end |
| Loopback-only, read-only, disable-able in Settings | ADR-033 (bound 127.0.0.1; Settings toggle) |
| cm-precision canvas, snap engine, bezier/arc/fillet, DXF import/export, satellite calibration | Phases 1–13 Packages A/B per roadmap/CLAUDE.md, each with tests |

**MUST NOT be claimed until shipped (do not let these leak into README/releases/replies):**

| Forbidden claim | Reality (2026-07-05) |
|-----------------|----------------------|
| "Agents can edit/modify your garden plan" | D2 write tools **unshipped**. ADR-033: current server has **no auth** (loopback trust); token auth is a hard prerequisite *before* any write tool exists. |
| "3D visualization / sun & shade simulation" | Phase 14 **not started** (roadmap lists it as Future, v2.0). Cross-ref `ogp-3d-sunshade-campaign` for the plan, `ogp-research-frontier` for what's open — plans are not features. |
| "Secure/authenticated agent API" | No auth today by design (read-only + loopback). Say "local-only, read-only" instead. |
| Any "first ever" without qualifier | No prior-art survey exists. |

## 4. README claims audit discipline

The README is a public promise. Drift is real and bidirectional — as of 2026-07-05 the
README **understates** the project: its Status section says *"Phases 1-5 complete.
Currently working on Phase 6"* while the app is at v1.23.0 with Phase 13 Packages A–C and
D1.1–D1.3 shipped, and the Features list omits DXF, PDF export, the tasks/harvest/journal
suite, and the MCP server entirely. Under-claiming is also a claims bug: fix it when you
touch the README, but only with shipped, tested items.

**Rules:**
- When a feature **ships**, the same change (or its release PR) updates README features/
  status, the wiki (`../open-garden-planner.wiki/Roadmap.md` — CLAUDE.md's "wiki synced"
  merge gate), and lets release notes describe it accurately. When a feature is
  **dropped** (precedent: US-B7 Paper Space, dropped in PR #191 review), remove or never
  add its README mention.
- Every README feature bullet must map to a shipped FR-* entry or roadmap ✅ line. No
  bullet for anything behind a hidden panel (e.g. Smart Symbols UI is deliberately hidden
  per US-C4 — describe the engine only if you also state the UI status, as FR-25 does).
- Mechanics of *how* to write/update docs live in `ogp-docs-and-writing`; this skill only
  fixes *what may be said*.

## 5. Release trust

- **Checksums:** every release ships `SHA256SUMS.txt` (generated by `release.yml`, see
  `docs/07-deployment-view` §7.3). The README's user-facing verify command (copy verbatim,
  keep in README):

  ```powershell
  # PowerShell — replace <version> with the actual version you downloaded
  (Get-FileHash .\OpenGardenPlanner-<version>-Setup.exe -Algorithm SHA256).Hash
  ```

  Compare against the hash in `SHA256SUMS.txt` from the release page.
- **The installer is UNSIGNED.** Documented as a known risk: §11.1 ("NSIS installer
  signing? … Unsigned initially, document for users; investigate free code signing
  options") and §11.2 ("Windows installer blocked by SmartScreen — Document workaround").
  In any public text: state plainly that Windows SmartScreen may warn, that the workaround
  is "More info → Run anyway" *after* verifying the SHA-256 checksum, and never phrase the
  warning away as a false positive users should blindly click through — the checksum step
  is the compensating control.
- **CI owns releases.** Never publish a release, create a tag, or upload assets manually —
  `release.yml` auto-tags, generates checksums, and creates the GitHub Release on merge to
  master (docs/07 §7.3; CLAUDE.md: "Never create git tags manually"). The docs/07 "manual
  fallback" is for CI-outage emergencies only. Pipeline mechanics: `ogp-change-control`.

## 6. Reproducibility standard for public claims

Any published number — accuracy, performance, comparison against another tool — needs a
**documented, re-runnable procedure** checked into the repo (or the claim doesn't go out).

- The model to follow is ADR-019's satellite scale: the "no manual calibration" claim
  rests on an *analytical* Web-Mercator pixel→meter derivation,
  `mpp = cos(lat) × 2π × 6378137 / (256 × 2^zoom)`, not on eyeballing. Anyone can recompute
  it. That is the bar.
- "Centimeter precision" is claimable for the **canvas model** (coordinates are stored and
  edited in cm). It is NOT automatically claimable for **satellite-derived real-world
  accuracy** — that depends on zoom, latitude, and Google's imagery georegistration. If
  you ever publish an end-to-end accuracy figure, ship the measurement procedure (known
  ground-truth distance, zoom/lat, expected mpp) alongside it. Cross-ref
  `ogp-proof-and-analysis-toolkit` for building such procedures and
  `ogp-research-methodology` for experiment write-ups.
- Benchmarks vs other software: name versions, hardware, exact steps; never compare
  against a competitor's marketing copy.

## 7. Community surface

- **Contribution channels** (README, verified): GitHub Discussions for questions/ideas,
  Issues for bugs/confirmed tasks, the public Project Board (Todo column = ready-to-pick),
  wiki roadmap mirror.
- **Contributor expectations** (README + docs/02 §2.3): PRs must pass CI (tests, lint,
  type check); every contribution needs unit + integration + UI tests where applicable;
  conventional commits; feature branches only. **AI-assisted development is explicitly
  welcome** — quality of result is what's judged.
- **Install-from-source** is the contributor on-ramp (README: Python 3.11+, `pip install
  -e .`, `python -m open_garden_planner`) — keep those commands working; they are a public
  claim too.
- Scope/context for what OGP is and is not: `docs/03-context-and-scope/`. Keep public
  positioning inside that scope.

## When NOT to use this skill

- Internal documentation mechanics (arc42 structure, where a lesson goes, ADR templates)
  → `ogp-docs-and-writing`.
- Branch/PR/merge/version/release *pipeline* mechanics → `ogp-change-control`.
- Deciding what future work is worth doing or claiming research directions →
  `ogp-research-frontier` / `ogp-3d-sunshade-campaign`.
- Building the app or debugging it → `ogp-build-and-run`, `ogp-debugging-playbook`.
- Purely internal code changes with no user-visible or public-facing surface — no claim,
  no skill needed.

## Provenance and maintenance

Facts verified 2026-07-05 against v1.23.0. Re-verify volatile facts before public use:

- License: `head -5 LICENSE && grep -n license pyproject.toml`
- Version: `grep -n '^version' pyproject.toml src/open_garden_planner/__init__.py`
- Weather provider: `grep -n 'URL\|api\.' src/open_garden_planner/services/weather_service.py | head -5`
- Plant API chain/terms: `sed -n '1,15p;140,150p' docs/03-context-and-scope/PLANT_API_SETUP.md`
- Google Maps key rules: `grep -n -A5 '8.15' docs/08-crosscutting-concepts/README.md | head -30`
- MCP shipped surface (claim ceiling): `grep -n 'D1\.\|D2' CLAUDE.md | head` and `ls src/open_garden_planner/agent_api/`
- Unsigned/SmartScreen risk: `grep -rn -i 'smartscreen\|signing' docs/11-risks-and-technical-debt/README.md`
- Release/checksum ownership: `grep -n -i 'SHA256\|release' docs/07-deployment-view/README.md | head`
- README drift check: `grep -n 'Phases\|Status' README.md` (fix staleness when touched)
