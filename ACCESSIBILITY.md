# Accessibility

Open Garden Planner aims to make garden planning usable by more people.
Accessibility work remains incomplete. This statement describes current behaviour, not a conformance certification.

## Current support

- Common actions have keyboard shortcuts. See [the shortcut reference](docs/12-glossary/README.md#122-keyboard-shortcuts).
- Properties support numeric entry for position and dimensions.
- Light and dark themes are available.
- Application text supports English and German.

Windows 10/11 is the primary application environment.
We have not verified compatibility with screen readers or other assistive technology.
Linux CI tests do not establish assistive-technology support on Linux or macOS.

## Known barriers

- Drawing, handle editing, and some canvas interactions depend on pointer gestures.
- Sidebar accordion headers use hover and click. Equivalent keyboard controls remain deferred.
- Colour communicates information in several warnings and visualisations.
- A complete keyboard-only garden-planning workflow has not been verified.

The project does not currently claim WCAG conformance or complete screen-reader support.

## Report an accessibility barrier

Use the [bug-report template](https://github.com/cofade/open-garden-planner/issues/new?template=bug_report.md).
Describe the action, expected result, observed barrier, application version, operating system,
and any assistive technology you used. Screenshots or recordings are optional.
Remove personal information and credentials before attaching files.
Do not disclose medical information to explain a barrier.

For public questions, use [Discussions](https://github.com/cofade/open-garden-planner/discussions).
For harassment or vulnerabilities, use the separate conduct or security reporting procedures.

## Contributions and maintenance

For UI changes, consider keyboard access, focus visibility, readable text, and alternatives to colour-only cues.
Report any unverified accessibility claim explicitly in the PR.
The maintainer reviews this statement when relevant support or barriers change.
