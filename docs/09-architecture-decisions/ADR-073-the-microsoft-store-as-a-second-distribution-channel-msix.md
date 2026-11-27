---
id: ADR-073
title: "The Microsoft Store as a second distribution channel (MSIX), and the #375 decision record"
status: "Accepted (2026-11-06). Packaging and pipeline shipped; the Store listing itself requires the owner's Partner Center registration and is reported **pending** until the first certified version is live."
refs: ["#375", "#358", "#356"]
legacy_anchor: adr-073-the-microsoft-store-as-a-second-distribution-channel-msix-and-the-375-decision-record-issue-375-358-356
---

# ADR-073: The Microsoft Store as a second distribution channel (MSIX), and the #375 decision record

**Status**: Accepted (2026-11-06). Packaging and pipeline shipped; the Store listing itself
requires the owner's Partner Center registration and is reported **pending** until the
first certified version is live.

**Context**: Three detections and one owner observation define the problem. Defender
quarantined the installed exe (#356), Norton quarantined the installer (#358), and on
2026-11-06 the owner's own Edge download of v1.37.6 showed SmartScreen's "is not commonly
downloaded" wall with *Publisher: Unknown* and a default button of *Delete* — the same wall
every prospective user sees. The owner had already reported the file as safe through the
Edge dialog with no effect.

Why nothing short of a signature or a different channel can move this (Microsoft's own
SmartScreen documentation, verified 2026-11-06):

1. **Unsigned files start from zero reputation with every new file hash**, and reputation
   cannot carry across versions unless both are signed with the same publisher identity.
2. **This project ships several releases a day.** On 2026-11-06 alone v1.37.4, v1.37.5 and
   v1.37.6 were published; the download counts of the last six installers were 1–4 each.
   A "report as safe" covers exactly one hash, which is superseded within hours.
3. **No certificate type grants instant reputation any more.** Since 2024 Microsoft treats
   EV and OV alike for SmartScreen; a signature replaces "Unknown" with a name and lets
   reputation accrue across releases, but at 1–4 downloads per release that accrual is a
   matter of months.
4. **Store-distributed MSIX packages do not pass through the browser download path at all.**
   Microsoft signs them after certification; the Learn page on code-signing options lists
   them as the one distribution form with no SmartScreen warning.

The owner decision of 2026-10-24 in #375 deferred Authenticode with four event-based
re-evaluation triggers. Trigger 1 ("a visible increase in user reports / a visible barrier")
is met by the owner's own observation. This ADR is the record that decision asked for: every
option scored against the issue's ten criteria, with the evidence behind each score.

## The options, scored (criteria 1–10 of #375)

Criteria: (1) publisher identity shown to the user, (2) bytes returned whole vs. a detached
signature, (3) trust anchor and revocation blast radius, (4) supply-chain properties of the CI
integration, (5) failure mode must never cost a release, (6) cost, renewal, lapse,
(7) OSS eligibility and terms, (8) RFC 3161 timestamp, (9) evidence it fixes the actual
detections, (10) reversibility.

| Option | Verified facts (source, 2026-11-06) | Fails | Passes / open | Verdict |
|---|---|---|---|---|
| **Status quo** (attestation + checksum + manual FP reports) | Per-hash reputation; 1–4 downloads per release; three releases a day | 1, 9 (structurally cannot improve) | 2–8, 10 | Keep as the GitHub channel's truth; it is not a fix |
| **Azure Artifact Signing** (Trusted Signing) | Individuals only in the USA and Canada (Microsoft Learn quickstart; Q&A threads report the form offers four countries); organisations need a registered business. The owner is an individual in Germany | 7 (not eligible) | — | **Not available** |
| **SignPath Foundation** | The certificate is issued to SignPath Foundation; signed binaries show *SignPath Foundation* as publisher (SignPath terms and docs). GitHub Action with an API token in CI | 1 (not this project's name), 3 (shared anchor), 4 (a credential and a third party in the release job) | 2, 5 (could be made non-blocking), 6, 7, 8; 9 open | Deferred, unchanged from 2026-10-24 |
| **OSSign** | Application-gated; publisher name not verified beyond the issue's own table | 9 open, 1 unverified | — | Not pursued; same shape as SignPath |
| **Necessary Innovations** | Signs as "Necessary Innovations AB" | 1 | — | Rejected on identity |
| **Certum Open Source Code Signing** | €49 (cloud, SimplySign) to €69 (card) per year, issued to the developer personally, Microsoft-trusted per Certum; the private key is not exportable, so a GitHub-hosted runner cannot hold it | 4/5 in practice (needs a self-hosted runner or a local signing step, which breaks "CI owns releases"), 9 (reputation still accrues per hash) | 1, 2, 3, 6, 7, 8, 10 | The best *signature* option if the owner funds it; a separate decision |
| **Third-party cloud signing** (the #358 proposal) | Shared certificate, service's name as publisher, mutable action tag running `npx` of a second repository | 1, 3, 4 | — | **Rejected** (2026-10-24, confirmed) |
| **Microsoft Store (MSIX)** | Individual developer registration free since 2025-09-10 (Windows Developer Blog); Microsoft hosts and re-signs the package after certification; Win32 apps accepted without code changes; GPLv3 precedent: Krita, Inkscape. Store installs bypass the browser download path | — | 1 (the owner's Partner Center display name), 2 (the project ships no re-signed bytes itself; Microsoft is the distributor), 3 (Microsoft's certificate, per-listing blast radius), 4 (no signing credential anywhere in CI; the upload is a manual owner action), 5 (the step is `continue-on-error` after the release), 6 (€0, no lapse), 7 (free individual tier, GPL precedent), 8 (Microsoft's signature), 10 (unlisting leaves installed copies working; the GitHub channel is untouched). 9: strongest available by Microsoft's own documentation, **to be confirmed by the first certified version** | **Adopted as a second channel** |

## Decision

1. **Add the Microsoft Store as a second distribution channel; keep GitHub Releases as the
   first.** The 2026-10-24 decision declined the Store because of "loss of distribution
   control"; that objection applies to a *replacement*, not to an *additional* channel. Both
   channels ship the same frozen bundle, built once.
2. **Package, do not rebuild.** `installer/build_msix.py` packages `dist/OpenGardenPlanner`
   (the PyInstaller output `build_installer.py` already produced) into
   `OpenGardenPlanner-v<version>.msix` with a makeappx mapping file, so the 600 MiB bundle is
   never copied and the installer and the Store package are the same application byte for
   byte. It never runs PyInstaller.
3. **The release workflow builds the package after the release and the attestation, with
   `continue-on-error`,** and uploads it as a 90-day **workflow artifact**, not a release
   asset: unsigned, it cannot be installed by anyone, and a Store upload must be unsigned
   (Microsoft signs it). ADR-044's placement rule is preserved: a missing SDK tool, an
   identity typo or a makeappx regression can never cost a GitHub release. The attestation
   subject list is unchanged.
4. **Identity comes from repository variables**, never from the source tree:
   `OGP_MSIX_IDENTITY_NAME`, `OGP_MSIX_PUBLISHER` (`CN=<GUID>`), and
   `OGP_MSIX_PUBLISHER_DISPLAY_NAME`, copied from Partner Center › Product identity once the
   owner has reserved the name. Until then the script uses development placeholders, says so
   on stdout and in the sidecar `.msix.json`, and the Store rejects such a package.
5. **The package runs as a full-trust packaged desktop app with Windows' default container**
   (`runFullTrust`, file-system and registry write virtualisation ON). Disabling the
   virtualisation needs the restricted capability `unvirtualizedResources`, which needs
   Partner Center approval; the first submission does not ask for it. Consequence: under
   the Store install the files the app creates in `AppData` (`app.log` and the Qt caches
   were measured there, see the addendum; seed inventory, custom companion rules,
   templates, plant lists and the weather/companion caches use the same folders) live in
   the package's `LocalCache`, and the `QSettings` registry values in the package's
   private hive (Microsoft's documented HKCU virtualisation, not measured); a Store
   uninstall removes both. Plans live in `Documents\Open Garden Planner`, outside the
   container, and are not affected, nor are autosaves, which are written next to the plan
   file (an unsaved plan's autosave goes to `%LOCALAPPDATA%\Temp`, whose fate under the
   container is not measured). Files that an earlier GitHub install left in the real
   `AppData` are edited in place and survive (Microsoft's documented 1903+ rule, not
   measured). `PRIVACY.md` tells users which data an uninstall deletes.
6. **An app execution alias `OpenGardenPlanner.exe`** is declared, because a Store install's
   folder under `WindowsApps` cannot be executed directly by the user: the alias is how a
   shell starts the installed package with arguments — the frozen self-test in CI, or an MCP
   client starting the app. A double-clicked `.ogp` reaches the app through the manifest's
   file-type association, which activates the executable with the path as its argument.
6a. **A Store install shows no GitHub update bar.** The bar offers "Download && Install" of
   the NSIS installer; in a packaged install that would put a second, unsigned copy under
   `Program Files (x86)` through the very SmartScreen wall this channel avoids.
   `application._start_update_check` returns early when
   `services.update_checker.has_package_identity()` is true
   (`kernel32.GetCurrentPackageFullName`); the Store delivers updates.
7. **A verification workflow** (`msix-store-verify.yml`, on demand and on pull requests that
   change the packaging) builds the bundle with the release recipe, packages it, signs it
   with a throw-away certificate, trusts that certificate in the runner's machine store,
   installs the package, runs the 8-second smoke (with a probe of the Agent API port from
   outside the package) and `--selftest` through the alias, reports where the per-user
   files landed, and removes the package. Its first run on PR #761's branch is the
   measurement this ADR's item 5 and item 9 of the table refer to; see "Measurements".
8. **Authenticode for the GitHub installer stays deferred** with the same four triggers;
   trigger 3 is now concrete: the Certum Open Source certificate at €49–69 a year, with a
   self-hosted or local signing step as the price.
9. **Not done, deliberately:** reducing the public release cadence (marking intermediate
   releases as pre-releases) was considered and left out — with 1–4 downloads per release it
   cannot reach SmartScreen's thresholds either, and it changes what `download-stats.yml`
   and the update checker treat as the current release. It is an owner decision if wanted.

## Measurements

- `makeappx pack` validates the manifest against Microsoft's schema and refused the first
  draft: `ExecutionAlias` lives in the `uap5` namespace, not `desktop` (PF-CI-20). The
  corrected manifest packs.
- The package holds the bundle plus 52 entries of its own (manifest, 46 logo files,
  `resources.pri`, block map, content types, signature and the signature's catalog). On the
  runner the v1.37.6 bundle of 3,802 files became 3,854 entries and 285,322,016 bytes
  (272.1 MB; run 42260902878 - the log prints the size, the entry and byte counts are in
  the run's artifact `store-package-verify-42260902878`, the package's `.msix.json`); the
  developer machine's older bundle of 3,714 files gave 268.5 MB. The NSIS installer of the same bundle is about 171 MiB because NSIS uses solid
  LZMA where MSIX uses per-file deflate.
- `makepri` indexes the scale (100–400) and target-size (16–256) logo variants; the
  manifest declares one resource language (`en-US`) because the images are language-neutral
  and the app localises itself at runtime.
- **A per-user Trusted People store does not satisfy `Add-AppxPackage`:** importing the test
  certificate into `Cert:\CurrentUser\TrustedPeople` and installing fails with
  `0x800B0109` (root not trusted). The machine store needs administrator rights, which an
  unattended developer session does not have; the install measurement therefore runs on the
  CI runner (PF-CI-19).
- The Windows SDK tools are not installed on the developer machine; the NuGet package
  `Microsoft.Windows.SDK.BuildTools` (10.0.26100.9457) carries `makeappx`, `makepri` and
  `signtool`, usable without installation **only from its complete `bin/<ver>/x64` folder**
  — the executables copied alone fail with `WinError 14001` (side-by-side configuration)
  because they ship their own `*.dll.manifest` files (PF-CI-20).
- CI install, smoke, Agent API reachability, the frozen self-test in the installed package
  and the per-user file locations: measured by `msix-store-verify.yml` run 42260902878 on
  `f24efab3` (PR #761) — the addendum below quotes it. The first run, 42257636976 on
  `aecf516d`, died before the install: Windows PowerShell started from pwsh had no `Cert:`
  drive (PF-CI-21).

## ADR-073 addendum: the first runner measurement (run 42260902878, 6 November 2026)

What the workflow proved on `windows-latest` (image 26100, an administrator session):

| Step | Result |
|---|---|
| Packaging tests with the real SDK tools | `40 passed in 26.90s` — including the real `makeappx`/`makepri` test; one `resources.pri`, no split resource packs |
| Package | `Package created: dist/OpenGardenPlanner-v1.37.6.msix (272.1 MB)`; 3,802 bundle files, 3,854 entries, test-signed |
| Install | `Installed OpenGardenPlanner.Dev_1.37.6.0_x64__7sjkjxhj42b3c at C:\Program Files\WindowsApps\…`; execution alias created at `%LOCALAPPDATA%\Microsoft\WindowsApps\OpenGardenPlanner.exe` |
| Smoke through the alias | `Smoke test passed: the packaged process was still running after 8 seconds.` |
| Agent API from outside the package | `Agent API port 127.0.0.1:8765 accepted a connection from outside the package.` — an MCP client can reach a Store install |
| Frozen self-test in the installed package | `Self-test passed (exit 0)`; log: `37.455s [selftest_exit] code=0 result=PASS` (Agent API, A1 checks, Qt Quick 3D frame on WARP) |
| Per-user files | Nothing under `%APPDATA%\cofade\Open Garden Planner` or `%LOCALAPPDATA%\cofade\…`; everything under `%LOCALAPPDATA%\Packages\OpenGardenPlanner.Dev_7sjkjxhj42b3c\LocalCache\` — `Roaming\cofade\Open Garden Planner\app.log` and `Local\cofade\Open Garden Planner\cache\{qmlcache, q3dshadercache-…, qtpipelinecache-…}` |
| Clean-up | `Remove-AppxPackage` and the certificate removal succeeded |

So item 5's virtualisation story is data, not assumption: a full-trust packaged app's
AppData writes are redirected into the package's `LocalCache`, which a Store uninstall
removes (for settings in the registry Microsoft documents the same for the package's
private hive; that part was not measured). Plans in
`Documents\Open Garden Planner` are outside the container. If that ever matters to a user
report, the restricted capability `unvirtualizedResources` is the lever, and it needs
Partner Center approval.

Not measured by this run: the Store's own certification outcome and SmartScreen's behaviour
on a Microsoft-signed install — those need the owner's Partner Center registration and the
first certified version (see "What the owner must do").

## What the owner must do (the part no agent can)

1. Register at Partner Center as an individual developer (free since 2025-09-10) and reserve
   the name *Open Garden Planner*.
2. Copy *Package/Identity/Name*, *Package/Identity/Publisher* and *Publisher display name*
   from Partner Center › Product identity into the three repository variables above.
3. After the next release, download `store-package-v<version>` from the release run and
   upload the `.msix` in a new Store submission; fill the listing (description, screenshots,
   age rating, privacy policy URL
   `https://github.com/cofade/open-garden-planner/blob/master/PRIVACY.md` — it lists every
   online feature, what it sends and when, and what a connected AI assistant can read; the
   URL resolves only after this ADR's PR is merged, so the submission comes after the merge).
4. Once the first version is certified: add the Store link to the README's download
   section and the wiki's Installation page, record the certification outcome and the
   Store's reputation behaviour here, and update §11.1/§11.2.

## Consequences

- Two artifacts per release from one bundle; one extra workflow; three repository variables;
  no new Python dependency (Pillow already ships; the SDK tools are on `windows-latest`).
- The Store listing adds a certification step between a release and its Store availability,
  and the Store's own update mechanism replaces the in-app update bar for Store users: the
  GitHub update check is not started in a packaged install (item 6a), so a Store user is
  never offered the NSIS installer.
- `tests/unit/test_build_msix.py` pins the manifest's load-bearing elements, the identity
  rules, the version mapping, the mapping file, SDK discovery, and the release workflow's
  placement/`continue-on-error`/artifact rules; `tests/integration/test_msix_packaging.py`
  runs the stage on every OS and the real `makeappx` where it exists.
- `PRIVACY.md` is the listing's privacy-policy URL, a public promise about the network
  surface: `tests/unit/test_privacy_inventory.py` pins the set of network-using modules and
  the PRIVACY.md text that discloses each, so a new one fails until it is disclosed, and it
  fails if the dormant plant-thumbnail download (`fetch_thumbnail`) gains a caller. It is a
  tripwire, not a proof: it matches import lines and known Qt network classes, so a new
  caller of an existing client (the companion panel was one, review round 4) or an unusual
  transport passes it. A change touching `services/plant_api`, `image_download` or the map
  picker still needs PRIVACY.md's "When" column checked in review.
- README, docs/07 §7.1/§7.2a/§7.3/§7.4, §11.1/§11.2, the glossary and PF-CI-19/20 are
  updated in the same change.

Cross-refs: ADR-044 (and its addendum of the same date), issues #89, #356, #358, #375,
`installer/build_msix.py`, `.github/workflows/release.yml`,
`.github/workflows/msix-store-verify.yml`, docs/07 §7.2a.
