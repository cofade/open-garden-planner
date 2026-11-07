# Privacy statement - Open Garden Planner

Last updated: 7 November 2026

**Open Garden Planner sends nothing to its developer.** It has no account, no telemetry,
no analytics, no advertising and no crash reporting. Your plans, settings and logs stay on
your computer.

## What stays on your computer

- Plan files (`.ogp`) are saved where you choose.
- Settings, autosaves, logs and cached weather/climate answers are kept in your user
  profile. In the Microsoft Store version Windows keeps them inside the app's own package
  folder and removes them when you uninstall the app.
- The built-in Agent API (for AI assistants that speak MCP) listens on `127.0.0.1` only,
  so other computers cannot reach it, and nothing leaves your computer through it.

## When the app goes online

Only the features below connect to the internet. Each connection goes directly from your
computer to the provider named; the developer is not involved and receives nothing. Like
every internet connection, each one shows the provider your IP address.

| Feature | Provider | What is sent | When |
| --- | --- | --- | --- |
| Today's weather and frost alerts | [Open-Meteo](https://open-meteo.com) | Latitude and longitude of the plan's location | When a plan has a location set |
| Frost dates and hardiness zone | [Open-Meteo](https://open-meteo.com) (historical archive) | Latitude and longitude of the location you look up | When you click *Lookup from Coordinates* in the location dialog |
| Satellite background | [Google Maps Platform](https://policies.google.com/privacy) | Your own Google Maps API key and the map area you view, search or import | Only when you open the satellite import with a key you entered |
| Online plant search | [Trefle](https://trefle.io), [Perenual](https://perenual.com), [Permapeople](https://permapeople.org) | Your search term and, where needed, your own API key; result images are then loaded from the addresses the provider returns | Only when you search the online plant database |
| Update check (GitHub download only) | [GitHub](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) | A request for the latest release | When the version installed from GitHub starts. The Microsoft Store version does not check GitHub; the Store updates it |

Links in the app (for example to Wikipedia or a plant database) open in your web browser;
what that site receives is between you and that site.

Downloading the app from the Microsoft Store is covered by
[Microsoft's privacy statement](https://privacy.microsoft.com/privacystatement).

## Questions and changes

Ask in the project's issue tracker: <https://github.com/cofade/open-garden-planner/issues>.
Changes to this statement are visible in this file's history in the repository.
