# Drawing Tool Icons

This directory contains SVG icons for the drawing tools panel.

## Icon Naming Convention

Icons should be named according to their tool function:
- `select.svg` - Selection tool
- `measure.svg` - Measurement tool
- `rectangle.svg` - Rectangle tool
- `polygon.svg` - Polygon tool
- `circle.svg` - Circle tool
- `house.svg` - House tool
- `shed.svg` - Garage/Shed tool
- `greenhouse.svg` - Greenhouse tool
- `terrace.svg` - Terrace/Patio tool
- `driveway.svg` - Driveway tool
- `pond.svg` - Pond/Pool tool
- `fence.svg` - Fence tool
- `wall.svg` - Wall tool
- `path.svg` - Path tool
- `tree.svg` - Tree tool
- `shrub.svg` - Shrub tool
- `flower.svg` - Perennial/Flower tool

## Icon Requirements

- **Format**: SVG (Scalable Vector Graphics)
- **Size**: Icons should be designed on a square canvas (recommended: 24×24, 32×32, or 48×48 pixels)
- **Color**: Can be colored or monochrome
- **Style**: Should be consistent across all icons

## Recommended Free Icon Sources

### 1. Tabler Icons (MIT License)
- **Website**: https://tabler.io/icons
- **License**: MIT (commercial use allowed)
- **Style**: Clean, minimal, consistent
- **Download**: Browse and download individual SVG files
- **Examples**:
  - Tree: https://tabler.io/icons/icon/tree
  - Fence: https://tabler.io/icons/icon/fence
  - Building: https://tabler.io/icons/icon/building

### 2. Heroicons (MIT License)
- **Website**: https://heroicons.com
- **License**: MIT (commercial use allowed)
- **Style**: Modern, clean

### 3. Lucide Icons (ISC License)
- **Website**: https://lucide.dev
- **License**: ISC (similar to MIT)
- **Style**: Feather-inspired, minimal

## Using IconScout Icons

If you purchase icons from IconScout:
1. Download the SVG file
2. Rename it according to the naming convention above
3. Place it in this directory
4. Restart the application

The icons you mentioned are great choices:
- Tree icon: https://iconscout.com/icon/tree-icon_7124175
- Fence icon: https://iconscout.com/icon/fence-icon_7124194

## How It Works

The application automatically:
1. Looks for SVG files in this directory
2. If found, loads the SVG and displays it in the button
3. If not found, falls back to emoji icons
4. Icons are rendered at 32×32 pixels

No code changes needed - just drop SVG files here!
