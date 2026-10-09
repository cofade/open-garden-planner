# Security Policy

## Supported versions

Security fixes target the **latest stable release**.
Earlier releases do not receive separate backports. Please update before checking whether a problem persists.
Find the current version on the [latest release page](https://github.com/cofade/open-garden-planner/releases/latest).

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/cofade/open-garden-planner/security/advisories/new).
Open the repository's Security and quality page, select Advisories, then select **Report a vulnerability**.
The default GitHub form sends a private report to repository maintainers.
Do not open a public issue or discussion for an undisclosed vulnerability.

Include:

- The affected application version, operating system, and installation method.
- Reproduction steps or a small proof of concept.
- The expected and observed behaviour.
- The possible impact and any affected data.
- Whether the problem involves an imported file, an online provider, or the Agent API.

Remove live credentials and personal data from examples and attachments.
If you exposed a credential, revoke or replace it. Do not send its value in the report.

This volunteer project offers no fixed response or repair deadline.
Maintainers assess reports and coordinate fixes and disclosure through GitHub's advisory workflow.

## Current security boundaries

The Agent API binds to loopback. Local reads and exports do not require authentication.
Editing requires explicit enablement and a valid token.
Write-enabled connection URLs contain credentials. Keep them private.
These boundaries do not establish an encrypted or fully authenticated API.

Release checksums and build attestations help check downloaded artifacts.
They do not make the unsigned installer Authenticode-signed or guarantee that software is harmless.
See [download verification](README.md#verify-your-download).

Report harassment through [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
That reporting route is separate from private vulnerability reporting.
