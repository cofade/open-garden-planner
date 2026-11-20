# 1. Introduction and Goals

## 1.1 Product Vision

Open Garden Planner is an open-source desktop application that enables home gardeners to create metrically accurate 2D plans of their property and garden. Unlike existing tools that are either expensive subscription-based software or imprecise visual-only planners, Open Garden Planner combines CAD-like precision with garden-specific features — all in a free, open-source package.

**For gardeners who value precision and modern tools while staying independent and valuing transparency. We garden with passion — and we want tools that match that passion.**

## 1.2 Goals

| Priority | Goal | Description |
|----------|------|-------------|
| 1 | **Metric Accuracy** | Allow users to plan with centimeter-level precision, not just visual approximation |
| 2 | **Rich Metadata** | Track plant species, varieties, planting dates, and growing requirements as first-class data |
| 3 | **No Lock-in** | Open-source with standard file formats (JSON project files, PNG/SVG/PDF/DXF export) |
| 4 | **Attractive UI** | Modern, polished interface that feels native to Windows, with lush illustrated graphics in 2D and 3D |
| 5 | **Extensible** | Engine-independent core modules (the sim clock, solar, plan time, units, geometry) and documented seams let new analysis, views and integrations be added without a second implementation of an existing one |
| 6 | **Contributor-Friendly** | Clean architecture, comprehensive tests, and CI/CD to attract open source contributors |

## 1.3 Target Users

| Persona | Description | Primary Needs |
|---------|-------------|---------------|
| **Precision Gardener** | Engineering-minded hobbyist who wants exact measurements and documentation | Metric accuracy, plant metadata, exportable plans |
| **Property Planner** | Homeowner planning landscaping changes, needs to communicate with contractors | Scale drawings, dimension annotations, image tracing |
| **Vegetable Gardener** | Plans crop rotation, bed layouts, and companion planting | Bed definitions, plant spacing, variety tracking |

## 1.4 Out of Scope

These are deliberate limits of the product today, not a promise about later versions:

- **Mobile applications.** The app is a Windows desktop application.
- **Multi-user collaboration and cloud sync.** Plans are files on your own computer;
  sharing means sending the file.
- **Irrigation planning.** Beds, water taps and barrels are drawn objects; the app does
  not size or schedule irrigation.
- **Terrain.** The ground is flat; site elevation and slopes do not shape shadows.
- **A Linux or macOS installer.** The source runs on other platforms and CI tests Linux,
  but only the Windows installer and frozen build are supported products.
- **A code-signed installer and a Microsoft Store listing.** Signing stays deferred
  (ADR-073) and the Store listing is not live; the GitHub installer is unsigned and is
  verified by checksum and build-provenance attestation.

3D visualisation and sun/shadow simulation are **not** out of scope: they have shipped
(Phases 14 and 17). The functional requirements in
[`docs/functional-requirements.md`](../functional-requirements.md) are the record of what
the app does.

## 1.5 Success Metrics

What success means for the project today:

- A user can complete the end-to-end workflow on a real garden: import or draw a site,
  calibrate it, add beds, plants and structures, give the plan a location, read shadows
  and hours of sun, save it, reopen it, and export or print it at scale.
- A plan remains readable by an older version unless a documented `FILE_VERSION` change
  says otherwise, and an Agent API client reads the same plan the window shows.
- Every release passes the full quality-gate battery on CI, and the frozen Windows build
  passes both the startup smoke and `--selftest` before it is published.
- The issue tracker is the single work list; a release exists because the owner accepted
  the manual test, not because CI was green.

Long-term goals: be a dependable open-source garden planning tool, keep an active
contributor community, and be cited in gardening/open-source publications when the
project is advertised.
