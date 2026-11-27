---
id: ADR-067
title: "Release download statistics without telemetry"
status: "Accepted (owner decision, 28 October 2026: no telemetry; chart accepted as \"perfect\" on the same date)."
legacy_anchor: adr-067-release-download-statistics-without-telemetry
---

# ADR-067: Release download statistics without telemetry

**Status:** Accepted (owner decision, 28 October 2026: no telemetry; chart accepted as "perfect" on the same date).
**Date:** 2026-10-28.

**Context.** We want to know how often the release executables are downloaded over time.
GitHub exposes only a cumulative `download_count` per asset
(`GET /repos/{owner}/{repo}/releases`), no history and no per-day, per-country or per-user
breakdown; *Insights → Traffic* covers page views and clones, not release downloads. The
app must not report anything about itself.

**Decision.** A scheduled workflow (`download-stats.yml`) snapshots the counters daily;
`scripts/download_stats.py` derives the values between consecutive snapshots. Snapshots
carry a timestamp and the asset id, only the installer and `SHA256SUMS.txt` of non-draft
releases are recorded, and files are split per month. The snapshots are the only source of
truth; `daily/` and `SUMMARY.md` are rebuilt from them. A value is a window in hours, not a
calendar day.

The data goes to the orphan branch `download-stats`. `master` requires a pull request and
green checks (`quality/master-protection.json`, administrators included), and every push
to it runs `release.yml`; a bot could not commit there at all, and a pull request per day
would be noise. The orphan branch shares no history with `master`, and neither `ci.yml`
nor `release.yml` runs for it (and a `GITHUB_TOKEN` push starts no workflow anyway).

**Rejected.**
- *App telemetry or an update ping:* the owner ruled it out; it would also count users
  who never download.
- *Splitting in-app from web via `SHA256SUMS.txt`:* first planned (an in-app update fetches
  the checksum file and the installer, a web visitor the installer only) and dropped after
  review. Two of our own artifacts break the inference: the README, wiki and release notes
  tell web users to fetch the checksum file, and apps older than v1.30.3 update without
  fetching it. The errors point in opposite directions, so the sign of the error is
  unknown and a derived column would look more certain than it is. The summary reports
  the raw columns and says so.
- *One ever-growing CSV recording every asset:* at the current release rate (about five
  assets per release, 40+ releases a month) it would pass GitHub's 100 MB file limit in
  under two years and every push would then fail. Per-month files of two asset kinds
  avoid a later migration.
- *Commit to `master`:* blocked by the protection and would trigger a release run.
- *Actions artifacts:* expire after 90 days by default; history is the point.
- *Issue comment per day (as `dependency-review.yml` does):* a month of noise and no
  machine-readable form.
- *Presenting reconstructed history as measured:* GitHub keeps no history; the raw
  series starts at the first snapshot. The addendum below permits a labelled model.

**Consequences.** The numbers include bots, virus scanners and retries and are not users.
A skipped scheduled run or a manual run gives a window of a different length, reported in
hours and flagged. A falling counter is a reset; a re-uploaded asset (new id) counts from
zero. The listing is validated before anything is written; an empty or sharply shrunken
listing fails the run. A snapshot row is only ever replaced by a rerun on the same UTC
date, and a snapshot older than the latest stored one is refused. A listing that lost
more than half of the assets is refused unless `--accept-shrink` (the `accept_shrink`
dispatch input) says the releases were pruned on purpose. Steps of one job are not
isolated, so the workflow does not claim a token boundary between them: it relies on the
`master`-only job, no persisted credentials, hook-free commits and a publish step that
checks it is committing in the data worktree. Scheduled workflows stop after 60 days of
repository inactivity (§7.4). See `docs/07-deployment-view/README.md` §7.4.

## Addendum — daily chart and explicit historical model (28 October 2026)

**Owner decision.** Show daily installer downloads, with sum-preserving week/month/year
switches, rather than only release totals. Model the pre-observation past by allocating
each baseline release's count uniformly while it was the latest regular release. This
is an assumption, not an inference of download timestamps. UTC was explicitly chosen;
missing observations are bridged by equal daily estimates. The owner accepted the chart
on 28 October 2026 ("perfect") and authorized finalization. Pages deploys after protected merge.

**Decision.** Preserve the earliest available snapshot in immutable `baseline.json`
BEFORE a same-date run can replace it. Exact elapsed-second fractions handle multiple
releases on one date and retain every baseline download. The most recent seed release
ends at the seed time. Future increments are computed against this seed once and then
against their own previous asset observation; the frozen historical component never
changes. One-date windows approximate the previous UTC date, same-date manual windows
are partial, longer windows are shared equally and coloured as gap estimates. Schedule
00:17 UTC, off the hour. Preserve actual timestamps and new/reset markers in daily JSON.
Raw snapshot/delta CSV schemas and meanings remain unchanged. No in-app/web inference.

The standard-library report module emits a daily series, SVG and a local-asset website.
Its browser code SUMS days into Monday weeks, calendar months or years after applying
the selected date range; cut-off buckets retain partial labels and estimate components.
Default view: daily, last 365 covered calendar dates. Website catalogs
(`en`/`de`/`es`/`fr`/`ru`) are separate from Qt: reporting runs on a plain Python runner, not an installed app.
Both themes, mobile layout, accessible bar descriptions and keyboard inspection are
supported without an external chart dependency or CDN.

Persist data before uploading/deploying only the site through a separate least-privilege
Pages job. Pages is enabled once after owner acceptance and merge. A deploy failure
cannot lose the stored measurement; `--report-only` rebuilds without a network call or
new snapshot. Do not use branch-triggered publication: bot-token pushes do not start
workflows. The owner-requested estimates supersede the earlier exclusion of all past
modelling; the rejection of unlabelled reconstruction remains.

**Evidence.** Unit cases pin the owner's 4/2 and 12/4 example, fractions, subday releases,
migration, immutable reruns, zero counts, missing asset windows, promotions and resets.
The CLI integration test produces a complete site from existing snapshots. Tests execute
the real browser aggregation with Node for all four grains, ISO boundaries and leap day.
Browser look/interaction evidence and the manual acceptance checklist accompany the PR.

## Addendum — current-release observation basis and single tooltip (1 November 2026, #677)

**Context.** In the `2026-10-30T05:51:20Z` snapshot window, 386 of 408 tracked assets across
every historical release moved by `+1` (204 installer rows summing to 218 and 204 checksum rows
summing to 217) — the fingerprint of a release-history crawl. Because `_history()` distributed
baseline counters across each release's tenure as the latest release while `calendar_series()`
summed post-seed increments across all ~200 installer assets, the `2026-10-29` bar reached 218
(24 % of the chart total), forcing the Y-axis maximum to 250 and compressing every normal day
(1–8 downloads) to a hairline. In addition, `SUMMARY.md` labelled that 386-row `normal` window
`new release or asset` because 4 new releases were also present, `chart.js` appended an SVG
`<title>` alongside the HTML `#tooltip` overlay (producing a doubled tooltip on hover in
Chromium), and multi-window tooltips concatenated distinct `kind` labels after a bare count
(`5 · Zählerdifferenz, Neuer Release, neues Asset oder Freigabe`).

**Owner decision (2026-11-01, #677).** An older release is **closed** the moment a newer
non-prerelease release is published. Only the counter of the release that is current at a
snapshot contributes to the observed/gap chart series.

**Decision.**
1. **Per-snapshot current-release resolution (`scripts/download_stats_report.py`).**
   `current_release(snapshot_rows)` selects the non-prerelease installer row (`*-Setup.exe`)
   with the highest `(instant(published_at), asset_id)` present in that snapshot.
   `calendar_series()` accumulates `observed` and `gap` increments only for that asset and
   closes superseded regular releases at each snapshot so crawls of older releases never enter
   the chart. `_history()` is unchanged, so historical and observed components now share one
   definition. `timeline.json` emits `"version": 2` and `"basis": "current_release"`.
2. **Auditable raw tables and tightened window note (`scripts/download_stats.py`).**
   `snapshots/`, `daily/`, and `SUMMARY.md` per-release totals remain raw across all releases
   so bulk crawls stay auditable. The `SUMMARY.md` preamble states why the chart total and the
   `**All**` row differ by design. `_summary_row()` appends `new release or asset` only when
   `KIND_NEW` deltas are the reason for the window's numbers (`new_total > 0 and normal_total == 0`).
3. **Single tooltip and unmixed window summary (`scripts/download_stats_web/`).**
   `chart.js` removes the SVG `<title>` nodes (retaining `role="img"` and `aria-label` on each
   bar `<g>`) so hovering displays only the HTML `#tooltip` overlay. `describe()` is exported on
   `globalThis.DownloadChart` and formats multi-window buckets (`windows.length > 3`) with the
   localized `windowCount` key (`{count} observation windows` / `{count} Messfenster` /
   `{count} intervalos de medición`) instead of joining distinct `kind` strings behind a bare
   count. `messages.json` updates the `observed` legend to `Increment of the current release`
   (and its German/Spanish equivalents) and documents the current-release basis and release-cadence
   effect in `method`.

**Trade-offs and consequences.** On the stored snapshots, `2026-10-29` drops from 218 to 2 and
the year maximum is the historical ~19.7 on `2026-07-23`. Real downloads of older releases are
deliberately excluded from the chart (the chart is a floor for current-release uptake, while
`SUMMARY.md` retains all-release counters); mid-window releases attribute their initial counter
to the window ending at the next snapshot; and with roughly daily releases each bar reflects
uptake while a release is current. This is not a bot filter and is not described as one. Pinned
by `tests/unit/test_download_stats_report.py`, `tests/unit/test_download_stats.py`, and
`tests/integration/test_download_stats_report.py`.
