# Installation Guide

## Windows installer

Download the installer and `SHA256SUMS.txt` from the [latest release](https://github.com/cofade/open-garden-planner/releases/latest).
The installer supports Windows 10/11, 64-bit.
Its default directory is `C:\Program Files (x86)\Open Garden Planner`.
The wizard offers shortcuts and `.ogp` file association.

As measured on **9 October 2026**, the v1.29.6 installer download is about **171 MiB**.
The local frozen application folder is about **611 MiB**.
Allow at least **1 GiB** for the application, plus download, temporary installation, and plan storage.
These sizes are dated measurements, not fixed limits. A minimum RAM requirement has not been measured.

Keep plans in `Documents\Open Garden Planner` or another user folder.
Do not store plans in the installation directory. Upgrades replace that directory.

## Verify the download

Calculate the installer's SHA-256 hash with PowerShell:

```powershell
# Replace <version> with the downloaded version, for example v1.29.6.
(Get-FileHash .\OpenGardenPlanner-<version>-Setup.exe -Algorithm SHA256).Hash
```

Compare the result with `SHA256SUMS.txt` from the same release.
The release workflow also creates build-provenance attestations for the installer and application executable.
Check provenance with the [GitHub CLI](https://cli.github.com/):

```text
gh attestation verify OpenGardenPlanner-<version>-Setup.exe -R cofade/open-garden-planner --signer-workflow cofade/open-garden-planner/.github/workflows/release.yml
```

The same command accepts `OpenGardenPlanner.exe` as the file argument.
Attestations run after release publication. If none are found, check the release workflow's result.
The checksum remains available while that step runs or if it fails.

The installer is **not Authenticode-signed**. Windows or antivirus software may warn.
An attestation proves build provenance. It does not remove these warnings or certify that software is harmless.
Check the download before deciding whether to run it.
See the [repository download guidance](https://github.com/cofade/open-garden-planner/blob/master/README.md#verify-your-download).

## Run from source

Requires Python 3.11+ and Git:

```text
git clone https://github.com/cofade/open-garden-planner.git
cd open-garden-planner
python -m venv venv
venv\Scripts\python.exe -m pip install -e .
venv\Scripts\python.exe -m open_garden_planner
```

This installs current dependency constraints. For development or installer builds,
use the committed lock as described below.
Windows is the primary application platform. Linux CI tests do not establish a supported Linux or macOS installer.

## Build the installer

Use the [locked setup in CONTRIBUTING.md](https://github.com/cofade/open-garden-planner/blob/master/CONTRIBUTING.md#development-setup).
It installs the project-pinned uv, Python 3.11 environment, development tools, and build tools.
Do not install an independently selected PyInstaller version.

Install [NSIS](https://nsis.sourceforge.io/) separately on Windows, then run:

```text
.venv\Scripts\python.exe installer/build_installer.py --version <version>
```

Use the source version from `pyproject.toml` for `<version>`, without the `v` prefix.
The output is in `dist/`. This local build does not create a GitHub release or CI attestation.
See [deployment documentation](https://github.com/cofade/open-garden-planner/blob/master/docs/07-deployment-view/README.md)
for the frozen-build verification requirements.

## Optional plant search

Online providers require their own credentials.
See the [Plant API Setup Guide](https://github.com/cofade/open-garden-planner/blob/master/docs/03-context-and-scope/PLANT_API_SETUP.md).
Do not include API keys or write-enabled Agent API URLs in public reports.
