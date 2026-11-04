## Case study: the Welcome gallery had content but no visible card (#316 review)

**Symptom.** At the supported 600 x 500 dialog size, the first gallery viewport
was 59 px tall and shrank to 35 px on selection for a 122 px card; 12 pt font
produced a 27 px viewport for a 148 px card.
**Wrong theory.** Layout stretch and successful selection tests implied usability.
**Evidence.** The independent reviewer measured actual item rectangles with real
fonts. The new minimum-size visibility test pins all three locales at 9/12 pt.
**Fix.** Hide the large banner on the gallery tab and put description/attribution
in a bounded, scrollable read-only details area. Whole selected cards remain visible.
**Lesson.** Test the viewport and its content rectangles, not only that widgets exist.


