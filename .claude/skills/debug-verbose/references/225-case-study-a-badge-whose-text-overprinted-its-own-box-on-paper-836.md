## Case study: a badge whose text overprinted its own box on paper — a font in points is resolved per paint device (#836, fixed 2026-11-10)

**Symptom**: on a printout of the raised-bed example the succession badge (the green tag with the crops that follow in a bed) was a smear at the bed's corner: its three crop names printed over one another, far larger than the tag. In a 300-dpi PNG and in the PDF report the same tag was whole but 4 mm tall for three lines. On the canvas it looked right.

**Theories entertained (wrong)**:
- *"It is a constant-pixel overlay, so it is only too small; scale the box with the export."* True for the PNG, and it does not explain the printout: there the text was too LARGE for the box.
- *"The export seam forgot it."* `retarget_constant_size_text` did skip it (it looked for Qt's two text item classes), but nothing about the printout changes when the seam is taught the badge, as long as the badge draws as it did.

**What instrumentation revealed** (a probe that resolved one font on three devices):

```
platform windows  screen logical dpi 96.0
28 pt   QFontMetricsF(font).height() 41.3   QFontInfo(font).pixelSize() 37      <- no device: the screen's 96 dpi
painter on QImage    fm.height 41    pixelSize 37                               <- a picture has 96 dpi too
painter on QPrinter  fm.height 522   pixelSize 467     (printer.logicalDpiY() 1200)
```

The badge measured its box with `QFontMetricsF(self._font)` and constants in pixels (`_LINE_HEIGHT = 12`), then called `painter.setFont(self._font)` with a font in points. `QPainter.setFont` resolves a font in points for the painter's device.

**Root cause**: two layouts of one text. The box was laid out for the screen, the text was drawn for the device. They agree on the canvas and on a `QImage` because both have 96 dots per inch, which is why every picture-based check passed. `QGraphicsSimpleTextItem` never shows this: it draws the layout it measured, with no device in between.

**Fix**: the badge draws with `layout_font.device_independent(font)` (the same font sized in pixels, which no device rescales), takes every measure from that font's line height, and offers `font()` / `setFont()` so the export seam gives it the object labels' size. It is painted in the scene's label pass, so the plants of its bed no longer cover it, and only where it has room on its bed.

**The same confusion, found beside it**: `TextItem.font_size` was documented as centimetres. A note's font is `round(font_size x 28.35)` points, laid out at 96 pixels per inch, and a pixel of a scene item is a plan centimetre: 1.0 is an em of 37 cm. The Properties panel showed "1.0 cm" for letters 27 cm tall, and its one-decimal field showed a stored 0.24 as 0.2: retyping what it showed changed the font from 7 pt to 6 pt.

**After**: a line of the badge is 4.2 mm in a 300-dpi PNG and in a printout (was 1.0 mm and 0.25 mm); no ink of its text lies outside its box.

**Lesson**: a number of points is not a size until a device is named. Where an item draws text by hand, measure and draw with one font sized in pixels, and test on a printer's resolution: a `QImage` shares the screen's logical resolution and cannot show the defect.
