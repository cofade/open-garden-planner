# 4. Solution Strategy

## 4.1 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Language** | Python 3.11+ | Rapid development, strong ecosystem, contributor accessibility |
| **GUI Framework** | PyQt6 | Mature, native look, excellent 2D graphics (QGraphicsView), 3D-ready (Qt3D) |
| **Graphics** | QGraphicsView/Scene | Hardware-accelerated, handles thousands of objects, built-in pan/zoom |
| **Data Storage** | JSON (project files) | Human-readable, VCS-friendly, no external database needed |
| **Plant API** | Trefle.io REST API | Free, open source, comprehensive plant data |
| **Local Cache** | SQLite | Efficient local plant database cache |
| **Image Handling** | Pillow + Qt | Format support, scaling, memory efficiency |
| **Packaging** | PyInstaller + NSIS | Professional Windows installer with file association |
| **CI/CD** | GitHub Actions | Automated testing, linting, and release builds |
| **i18n** | Qt Linguist (.ts/.qm) | Qt's native translation system; `tr()` calls, .ts XML files |
| **Linting** | ruff | Fast Python linter, replaces flake8 + more |
| **Formatting** | Black (via ruff) | Consistent code style, 110 char line length |
| **Testing** | pytest + pytest-qt | Python testing framework with Qt widget testing support |

## 4.2 Key Design Decisions

| Area | Decision | Rationale |
|------|----------|-----------|
| **Distribution** | Windows installer (NSIS) + pip install | Maximum accessibility for different user types |
| **Coordinate Origin** | Bottom-left, Y-axis up | CAD convention, eases future 3D transition |
| **Panel Layout** | Fixed sidebar (not dockable) | Simpler UX, consistent layout |
| **Image Calibration** | Global scale for entire project | Simpler model, assumes consistent image sources |
| **Image Storage** | Embedded in project file by default | Portability over file size |
| **Snapping** | Both grid snap AND object snap | Professional-grade precision |
| **Box Selection** | AutoCAD convention (drag direction matters) | Left->right = enclosing, right->left = crossing |
| **Selection Click** | Click inside filled shapes selects | Intuitive for solid objects |
| **Rotation Pivot** | Object center | Simple, predictable behavior |
| **Label Scaling** | Scale with minimum readable size | Always readable at any zoom |
| **Canvas Size** | User specifies initial size, resizable later | Flexible without being unbounded |
| **Plant Visuals** | Illustrated SVG shapes (hybrid approach) | Category-based shapes + unique popular species |
| **Textures** | Tileable PNG textures | Realistic, immediately recognizable materials |
| **Shadows** | Subtle drop shadows (toggleable) | Visual depth, professional look |
| **Undo History** | Clears on project close | Standard behavior, simpler implementation |
| **Session State** | Remember window size, position, recent files | Professional, convenient UX |
| **Plant Data** | API first, then custom entries | Leverage existing plant databases |
| **API Fallback** | Trefle.io -> Permapeople -> Bundled DB -> Custom | Graceful degradation |
| **Theme** | Branded green with light/dark variants | Strong visual identity, garden-appropriate |
| **i18n** | Qt Linguist, EN + DE extensible | Native Qt integration, community can add languages |
| **Graphics Assets** | AI-generated SVGs | Consistent style, fully custom, no licensing issues |

## 4.3 Architecture Approach

The application follows a **layered desktop architecture** with clear separation of concerns:

1. **Presentation Layer**: Qt widgets, canvas rendering, panels, dialogs
2. **Application Layer**: Tool management, document/project management, command system (undo/redo)
3. **Domain Layer**: Geometry engine, object model, plant model, layer model
4. **Infrastructure Layer**: File I/O, export engines, plant API client, settings storage

Key patterns:
- **Command Pattern** for undo/redo (all modifications wrapped in commands)
- **Observer Pattern** via Qt signals/slots for UI updates
- **Strategy Pattern** for tools (each tool is a strategy for mouse/keyboard input)
- **Repository Pattern** for plant data (API -> cache -> local library fallback chain)

## 4.4 Visual Strategy

Target visual quality: **Lush illustrated style** inspired by Gardena My Garden.

| Aspect | Approach |
|--------|----------|
| **Plant rendering** | AI-generated SVG illustrations; ~15-20 category shapes + ~10 unique popular species |
| **Textures** | Tileable PNG textures (256-512px); grass, wood, stone, water, soil, gravel, concrete |
| **Shadows** | QGraphicsDropShadowEffect on all objects; toggleable in settings |
| **Object library** | Visual thumbnail gallery with categories, drag-to-canvas |
| **Theme** | Branded green palette; refined light/dark variants |
| **Labels** | Toggleable text labels on objects (plant names, custom text) |
| **Scale bar** | Persistent overlay widget, updates with zoom |
