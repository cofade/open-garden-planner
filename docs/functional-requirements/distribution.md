---
title: "Distribution"
prefixes: ["FR-STATS"]
---

# Distribution

## Public download reporting

- **FR-STATS-01**: The public chart shows installer downloads of the then-current regular
  release (`"version": 2`, `"basis": "current_release"`), defaulting to daily bars and a year
  of available UTC history. Independent controls select day/Monday-week/month/year and
  30/90/365 days/all history. Aggregation sums daily values without changing the selected
  total; partial buckets are labelled.
- **FR-STATS-02**: Pre-observation values are explicitly historical estimates using a
  frozen first snapshot and uniform allocation over each release's tenure as latest.
  Fractions and multiple releases per day are supported. Subsequent measurements never
  revise that historical component. An older release is closed once a newer regular release
  is published (#677): at each post-seed snapshot only the current release's installer
  contributes to observed/gap bars, while `SUMMARY.md` reports raw counters across all
  releases so the chart total and `SUMMARY.md` **All** differ by design.
- **FR-STATS-03**: Recorded increments of the current release approximate UTC dates and
  expose actual measurement windows in a single HTML tooltip (without duplicate native SVG
  `<title>` tooltips or concatenated multi-kind strings). Missed dates share increments evenly
  with an estimate label. Unchanged counters show zero; dates outside coverage are not
  invented. No user-count or in-app/web attribution is inferred, and the app sends no telemetry.
- **FR-STATS-04**: The existing summary embeds a static preview and links to a keyboard-
  accessible, English/German/Spanish/French/Russian, light/dark responsive website and downloadable daily JSON.
  Durable data is pushed before Pages deployment; reports can be rebuilt offline.

Section 7.4 owns Pages deployment.
