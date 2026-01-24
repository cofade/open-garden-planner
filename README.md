# Open Garden Planner

**Precision garden planning for passionate gardeners who value independence and transparency.**

Open Garden Planner is an open-source desktop application that combines CAD-like metric accuracy with garden-specific features. Plan your garden with centimeter precision, track plants with rich metadata, and export to standard formats - all without subscription fees or vendor lock-in.

## Why Open Garden Planner?

Existing tools are either:
- **Expensive commercial software** with subscription fees and proprietary formats
- **Visual-only planners** that lack metric precision
- **General CAD tools** that require steep learning curves and lack garden features

Open Garden Planner fills the gap: **engineering-grade precision meets gardener-friendly workflows**.

## Features (Planned)

- **Metric Accuracy**: Plan with centimeter-level precision on a calibrated canvas
- **Image Calibration**: Import satellite imagery and calibrate to real-world scale
- **Rich Plant Metadata**: Track species, varieties, planting dates, and growing requirements
- **Object Library**: Define custom plants, structures, and garden elements
- **Standard Formats**: JSON project files, PNG/SVG export - your data, your control
- **Modern UI**: Clean, native Windows interface with both light and dark modes

## Status

This project is in active development. See [prd.md](prd.md) for the detailed product requirements document and roadmap.

## Tech Stack

- **Python 3.11+** with **PyQt6** for cross-platform desktop UI
- **QGraphicsView** for hardware-accelerated 2D canvas
- **SQLite** for local plant database caching
- **Trefle.io API** for plant species data

## Getting Started

*Coming soon - we're building the foundation.*

## Contributing

We welcome contributions! This project aims to be technically clean and attractive for both users and contributors.

- Read the [PRD](prd.md) to understand the vision and architecture
- Check the Issues for tasks and discussions
- PRs must pass CI (tests, linting, type checking)

**AI-assisted development is welcome.** Feel free to use Claude Code, GitHub Copilot, Cursor, or other AI-powered coding tools. We care about the quality of the result, not how you got there. Just ensure every contribution includes proper tests - unit tests, integration tests, and UI tests where applicable.

## License

[GPLv3](LICENSE) - Free software, free forever.

---

*Built with passion for gardeners who demand precision.*
