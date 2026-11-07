# Privacy statement - Open Garden Planner

Last updated: 7 November 2026

**Open Garden Planner itself sends nothing to its developer.** It has no account, no
telemetry, no analytics, no advertising and no crash reporting of its own. Your plans,
settings and logs stay on your computer unless you use one of the online features or
connect an AI assistant, both described below.

If you installed the app from the Microsoft Store, Microsoft may give the developer
aggregated download and usage statistics and crash reports, depending on your Windows diagnostic-data
settings. That is Microsoft's reporting, covered by
[Microsoft's privacy statement](https://privacy.microsoft.com/privacystatement); the app
does not send it.

## What stays on your computer

- **Plan files** (`.ogp`) are saved where you choose. **Autosaves** are written next to the
  plan file (`~autosave_<name>.ogp`), or to your temp folder for a plan that was never saved.
- **Settings** are kept in your user registry. **Logs, caches and the data you keep outside
  plans** - custom plants, seed inventory, custom companion rules, guild templates, smart
  symbols, plan templates, plant lists, cached weather, climate and companion answers - are
  kept in your user profile (`AppData`).
- **Microsoft Store version:** Windows keeps the settings and the files the Store version
  creates in `AppData` inside the app's own package folder
  (`%LOCALAPPDATA%\Packages\<package folder>\LocalCache`) and **deletes them when you
  uninstall the app** - including your custom plants, seed inventory, custom companion rules,
  guild templates, smart symbols, plan templates and plant lists. Copy that folder first if
  you want to keep them. Files left by an earlier installation from GitHub stay where they
  are, and plan files and the autosaves next to them are not affected.

## When the app goes online

Only the features below connect to the internet. Each connection goes directly from your
computer to the provider named; the developer is not involved and receives nothing
(GitHub publicly counts downloads of its release files; that count is all the developer
sees). Like
every internet connection, each one shows the provider your IP address.

| Feature | Provider | What is sent | When |
| --- | --- | --- | --- |
| Weather forecast and frost alerts | [Open-Meteo](https://open-meteo.com/en/terms) | Latitude and longitude of the plan's location | When a plan has a location set |
| Frost dates and hardiness zone | [Open-Meteo](https://open-meteo.com/en/terms) (historical archive) | Latitude and longitude of the location you look up | When you click *Lookup from Coordinates* in the location dialog |
| Satellite background | [Google Maps Platform](https://policies.google.com/privacy) | The address or place you type into the map's search box (sent while you type), your Windows language and region, the map area you view or import, and your own Google Maps API key | Only when you open the satellite import with your own API key |
| Online plant search | [Trefle](https://trefle.io), [Perenual](https://perenual.com), [Permapeople](https://permapeople.org) | Your search term and, where needed, your own API key | Only when you search the online plant database |
| Plant thumbnail download | Image hosts returned by plant providers (e.g. Wikimedia Commons, Perenual, Permapeople) | The image URL the provider returned | When viewing plant details that include a thumbnail image |
| Companion plants | [Permapeople](https://permapeople.org) | The selected plant's scientific name (or common name) and, where needed, your own API key | Only when you click *Fetch from Permapeople* or *Refresh* in the companion panel |
| Update check (GitHub download only) | [GitHub](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) | A request for the latest release; if you click *Download & Install*, the download of the new installer | When the version installed from GitHub starts. The Microsoft Store version does not check GitHub; the Store updates it |

Links in the app (for example to Wikipedia or a plant database) open in your web browser;
what that site receives is between you and that site.

## AI assistants

The built-in Agent API is on by default and listens on `127.0.0.1` only, so other computers
cannot reach it. An AI assistant **you connect** to it (*Help > Connect AI Assistant...*, or
by hand) can read your whole plan - including its location, plants, tasks and notes - and
can save the open plan and export it to files on your computer. It can change the plan
itself only if you turn on *Allow AI assistants to edit the plan* in the preferences. What
the assistant then sends to its own provider is decided by that assistant, under its
provider's privacy terms, not by Open Garden Planner.

The *Connect AI Assistant* dialog runs the command-line tools of the assistants it finds on
your computer to detect them. Connecting one runs that tool or writes Open Garden Planner's
local address - with the access token, if AI editing is on - into that assistant's
configuration file; those entries stay when you uninstall Open Garden Planner. You can turn
the Agent API off in the preferences.

## Questions and changes

Ask in the project's issue tracker: <https://github.com/cofade/open-garden-planner/issues>.
Changes to this statement are visible in this file's history in the repository.
