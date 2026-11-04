## Case study: hosted dependency updater lags the pinned tool (2026-10-09)

**Symptom:** project CI and release succeeded, but Dependabot could not prepare the newly
reported setuptools security update. **Assumption refuted:** hosted update tooling can run
the same uv version as the project runners. **Key log:** `tool_version_not_supported`
reported detected uv `==0.12.23` and supported uv `0.12.18` in
[run 37951191628](https://github.com/cofade/open-garden-planner/actions/runs/37951191628).
**Root cause:** the hosted updater's supported tool version lagged the approved exact pin.
**Disposition:** retain reproducible installation and keep the moderate setuptools advisory
open for a separately reviewed manual setuptools/lock update; no remediation is claimed.
**Lesson:** check updater compatibility when introducing a lock/tool pin. A green project
workflow does not prove automatic security updates work. See risks sections 11.2 and 11.4.


