"""Fail if a credential-shaped string is committed anywhere in the tree.

WHY THIS EXISTS
---------------
A live Agent API write token was committed to the repo root in a throwaway
verification script and pushed, while driving the manual MCP pass for PR #369
(2026-09-29). It had to be rotated by hand.

Bandit never saw it: ``ci.yml`` runs Bandit as ``-r src/``, and the file was
at the repo root — outside that scope. Bandit also has no rule for a
credential in a URL query string, which is exactly how OGP's Agent API token
travels (ADR-036 / #366 moved the *default* hand-out to a read-only URL
precisely because that URL becomes a WRITE credential when it carries the
token).

WHY NOT gitleaks
----------------
gitleaks was tried first and rejected, for two measured reasons:

  1. Its ``generic-api-key`` rule matches on IDENTIFIER NAMES, and this
     codebase's vocabulary is saturated with them — ``species_key``,
     ``exclude_antagonists_of``, a ``"Shift+Arrow Keys"`` row in the
     translation table. A scan of this tree produced 29 findings with zero real
     secrets.
  2. Suppressing that rule is not an option, because it is the rule that
     actually catches an OGP token. A second attempt to allowlist the noise
     (``[[allowlists]]`` scoped by rule + path) was silently ignored under
     ``[extend] useDefault`` — the finding count was identical with and
     without the allowlist block.

A gate that cannot distinguish a credential from a variable name is a gate
that gets deleted after its first false alarm, and then it catches nothing.
This checker targets the specific shapes a real leak takes here, so it has no
false positives to suppress in the first place.

WHAT IT SCANS
-------------
Every git-TRACKED file (so an untracked local scratch file does not fail a
build), for:

  * ``?token=<40-50 chars>`` — OGP's own Agent API write credential, the exact
    shape that leaked. This is the one that matters.
  * Common provider key prefixes with a plausible-length body: AWS
    ``AKIA…``, GitHub ``ghp_``/``github_pat_``, Slack ``xox[baprs]-``, Google
    ``AIza``, Stripe ``sk_live_``, private-key headers, and ``Bearer <jwt>``.

Deliberately NOT matched: high-entropy strings in general, and anything that
looks like an identifier assignment. Those are what produced the 29 noise hits.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (rule name, regex, human explanation). Each pattern is deliberately
# high-signal: it names a credential FORMAT, not a shape that merely looks
# random, because a vague pattern is what makes secret scanners unusable.
RULES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "ogp-agent-api-token-in-url",
        re.compile(r"\?token=[A-Za-z0-9_\-]{40,50}"),
        "Open Garden Planner Agent API write token in a URL. This is a WRITE "
        "credential (ADR-036); a read-only client must not carry it. If a "
        "client needs it, mint a fresh one with the 'Connect AI Assistant' "
        "dialog instead of committing one.",
    ),
    (
        "ogp-agent-api-token-bearer",
        re.compile(r"\bBearer\s+[A-Za-z0-9_\-]{40,50}\b"),
        "The same Agent API write token delivered as an Authorization header. "
        "This is NOT a hypothetical channel: _bearer_token_middleware accepts "
        "it, and WriteAuthError's own guidance tells users to fall back to it "
        "when a client drops the header on tool-call requests. A gate for a "
        "write-token incident that covered only the URL channel would be half "
        "a gate.",
    ),
    (
        "aws-access-key-id",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key ID.",
    ),
    (
        "github-token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b"),
        "GitHub personal access / OAuth / app / refresh token.",
    ),
    (
        "github-fine-grained-pat",
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,255}\b"),
        "GitHub fine-grained personal access token.",
    ),
    (
        "slack-token",
        re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),
        "Slack API token.",
    ),
    (
        "google-api-key",
        re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
        "Google API key.",
    ),
    (
        "stripe-live-secret",
        re.compile(r"\bsk_live_[0-9A-Za-z]{24,}\b"),
        "Stripe live secret key.",
    ),
    (
        "private-key-header",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        "Private key material. Only a fixture with an obviously fake body "
        "belongs in the repository.",
    ),
    (
        "jwt-bearer",
        re.compile(r"\bBearer\s+eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\."),
        "A bearer JWT in source. Test fixtures must use a syntactically "
        "obvious placeholder, never a real token.",
    ),
]

# Lines that legitimately mention a FORMAT rather than carrying a credential —
# this checker's own documentation, and the rules above quoted in prose.
_ALLOW_MARKERS = (
    "?token=<40-50 chars>",
    "?token=[A-Za-z0-9_",
    "Bearer\\s+[A-Za-z0-9_\\-]{40,50}",
    "AKIA[0-9A-Z]",
    "ghp|gho|ghu|ghs|ghr",
    "github_pat_",
    "xox[baprs]-",
    "AIza[0-9A-Za-z_",
    "sk_live_",
    "-----BEGIN (?:RSA ",
    "Bearer eyJ",
    "secrets.token_urlsafe",
)

# Binary-ish and vendored paths, skipped for speed and noise.
_SKIP_DIR_PARTS = {
    ".git",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

_SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".zip", ".gz",
    ".qm", ".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".woff",
    ".woff2", ".ttf", ".otf", ".mo", ".ogp",
}


def _tracked_files(root: Path) -> list[Path]:
    """Return git-tracked files, falling back to a walk if git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return [
            p
            for p in root.rglob("*")
            if p.is_file() and not _skip(p, root)
        ]
    files = []
    for rel in out.split("\0"):
        if not rel:
            continue
        p = root / rel
        if p.is_file() and not _skip(p, root):
            files.append(p)
    return files


def _skip(path: Path, root: Path) -> bool:
    try:
        parts = set(path.relative_to(root).parts)
    except ValueError:
        parts = set()
    if parts & _SKIP_DIR_PARTS:
        return True
    return path.suffix.lower() in _SKIP_SUFFIXES


def check_repo(root: Path) -> list[str]:
    """Return one finding string per (rule, file, line); empty means clean."""
    findings: list[str] = []
    for path in _tracked_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if any(marker in line for marker in _ALLOW_MARKERS):
                continue
            for name, pattern, _why in RULES:
                if pattern.search(line):
                    rel = path.relative_to(root).as_posix()
                    findings.append(
                        f"{rel}:{lineno}: {name} — {line.strip()[:100]}"
                    )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)

    findings = check_repo(args.root)
    if not findings:
        print("No secrets found in tracked files.")
        return 0

    print(f"{len(findings)} potential secret(s) found in tracked files:\n")
    for f in findings:
        print(f"  {f}")
    print("\nRule reference:")
    for name, _pattern, why in RULES:
        print(f"  {name}: {why}")
    print(
        "\nIf one of these is a real credential, ROTATE IT — deleting the file "
        "in a later commit does not unpublish it (git serves any blob by SHA "
        "for any reachable commit). If it is a placeholder, reword it so the "
        "pattern does not match."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
