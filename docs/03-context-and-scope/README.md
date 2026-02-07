# 3. Context and Scope

## 3.1 Business Context

Open Garden Planner operates as a standalone desktop application with optional connections to external plant databases.

```
                        ┌─────────────────────────┐
                        │   Open Garden Planner    │
                        │   (Desktop Application)  │
                        └────┬──────┬──────┬───────┘
                             │      │      │
              ┌──────────────┘      │      └──────────────┐
              │                     │                     │
              v                     v                     v
     ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
     │   Trefle.io    │   │  Permapeople   │   │  Local Files   │
     │   Plant API    │   │   Plant API    │   │  (.ogp, PNG,   │
     │  (Primary)     │   │  (Fallback)    │   │   SVG, CSV)    │
     └────────────────┘   └────────────────┘   └────────────────┘
```

| External System | Purpose | Interface |
|----------------|---------|-----------|
| **Trefle.io API** | Primary plant species database | REST API (HTTPS) |
| **Permapeople API** | Fallback plant database | REST API (HTTPS) |
| **File System** | Project files, exports, user plant library | .ogp (JSON), PNG, SVG, CSV |
| **Windows OS** | File associations, Start Menu, printer | Win32 APIs via Qt |

## 3.2 Competitive Analysis

### Existing Solutions

| Tool | Type | Strengths | Weaknesses |
|------|------|-----------|------------|
| **Gardena My Garden** | Commercial, web-based | Beautiful illustrated graphics, lush textures, organic shapes, furniture library | Web-only, no metric precision, limited plant metadata |
| **Garden Planner (smallblueprinter.com)** | Commercial, subscription | Easy to use, plant database, illustrated objects | Expensive, no metric precision, web-only |
| **iScape** | Commercial, subscription | Good visualization, AR features | Mobile-focused, expensive, no precision tools |
| **FreeCAD** | Open source CAD | Excellent precision, 3D capable | Not garden-focused, steep learning curve, no plant metadata |
| **QCAD** | Open source CAD | Good 2D precision, DXF support | No garden features, technical UI |
| **elbotho/open-garden-planer** | Open source (GitHub) | Good concept, SVG-based | Incomplete, not usable, web-based |
| **Plant-it** | Open source (GitHub) | Plant tracking, Android | No spatial planning, mobile only |

### Market Gap

No existing tool combines:
- Open source + free
- Desktop application with native feel
- CAD-like metric precision
- Garden-specific metadata and workflows
- Image import with calibration
- Modern, attractive illustrated UI

**Open Garden Planner fills this gap.**

### Visual Benchmark (Competitor Analysis)

Based on detailed analysis of Gardena My Garden and Garden Planner 3 screenshots:

| Visual Aspect | Gardena My Garden | Garden Planner 3 | Our Target |
|--------------|-------------------|-------------------|------------|
| Plant rendering | Organic canopy shapes with textures/shadows | Colorful illustrated icons | Lush illustrated SVGs (Gardena-inspired) |
| Textures | Rich grass/soil/wood/stone/water | Photorealistic patterns | Tileable PNG textures |
| Object library | Category sidebar with thumbnails | Dropdown categories with previews | Visual thumbnail gallery |
| Shadows | Subtle drop shadows on all objects | Shadow rendering present | Toggleable drop shadows |
| Scale reference | "1m" scale bar on canvas | Grid-based | Scale bar overlay |
| Furniture/extras | Tables, chairs, parasols, BBQ, pool | Extensive object library | Comprehensive: furniture + garden infrastructure |

For detailed plant API setup instructions, see [Plant API Setup Guide](PLANT_API_SETUP.md).

## 3.3 Technical Context

```
┌─────────────────────────────────────────────────┐
│                  User's Computer                 │
│                                                  │
│  ┌──────────────────────────────────────────┐   │
│  │         Open Garden Planner (PyQt6)       │   │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌─────────┐ │   │
│  │  │Canvas│ │Panels│ │Tools │ │ Dialogs │ │   │
│  │  └──┬───┘ └──┬───┘ └──┬───┘ └────┬────┘ │   │
│  │     └────────┴────────┴──────────┘       │   │
│  │              Core Engine                   │   │
│  │  ┌─────────┐ ┌─────────┐ ┌────────────┐  │   │
│  │  │Geometry │ │ Objects │ │   Plant    │  │   │
│  │  │ Engine  │ │  Model  │ │  Service   │  │   │
│  │  └─────────┘ └─────────┘ └─────┬──────┘  │   │
│  └────────────┬───────────────────┼──────────┘   │
│               │                   │              │
│   ┌───────────v──────┐  ┌────────v─────────┐    │
│   │   Local Files    │  │   HTTPS / REST   │    │
│   │ (.ogp, exports)  │  │  (Plant APIs)    │    │
│   └──────────────────┘  └──────────────────┘    │
└─────────────────────────────────────────────────┘
```
