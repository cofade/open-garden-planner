#!/usr/bin/env bash
# check_mojibake.sh — detect UTF-8 double-encoding ("mojibake") in .ts/.py files.
#
# Background (docs/11-risks-and-technical-debt §11.4): PowerShell 5.1
# `Set-Content -Encoding UTF8` mis-decodes UTF-8-without-BOM as Latin-1 and
# re-encodes, turning every umlaut into a two-character sequence:
#   ö -> Ã¶   ä -> Ã¤   ü -> Ã¼   ß -> ÃŸ   (capitals: Ö -> Ã–  Ä -> Ã„  Ü -> Ãœ)
# Any hit means the file is double-encoded and must be restored from git.
#
# Usage:
#   bash .claude/skills/ogp-diagnostics-and-tooling/scripts/check_mojibake.sh [DIR ...]
#
# With no args, scans the repo root (resolved via git, falling back to CWD).
# Only *.ts and *.py are scanned by default — docs/*.md legitimately QUOTE the
# mojibake byte sequences when documenting this very pitfall, so scanning .md
# would false-positive on docs/11-risks-and-technical-debt/README.md.
#
# Exit codes: 0 = clean, 1 = mojibake found, 2 = usage/environment error.

set -u

PATTERN='Ã¶|Ã¤|Ã¼|ÃŸ|Ã–|Ã„|Ãœ'

if [ "$#" -gt 0 ]; then
    ROOTS=("$@")
else
    ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    ROOTS=("$ROOT")
fi

for r in "${ROOTS[@]}"; do
    if [ ! -e "$r" ]; then
        echo "check_mojibake: no such path: $r" >&2
        exit 2
    fi
done

hits="$(grep -rnIE "$PATTERN" \
    --include='*.ts' --include='*.py' \
    --exclude-dir=.git --exclude-dir=venv --exclude-dir=.venv \
    --exclude-dir=dist --exclude-dir=build --exclude-dir=__pycache__ \
    --exclude-dir=node_modules \
    "${ROOTS[@]}" 2>/dev/null)"

if [ -n "$hits" ]; then
    echo "MOJIBAKE FOUND (double-encoded UTF-8). Restore with: git checkout HEAD -- <file>"
    echo "$hits"
    count="$(printf '%s\n' "$hits" | wc -l | tr -d ' ')"
    echo "-- $count offending line(s) --"
    exit 1
fi

echo "OK: no mojibake in *.ts/*.py under: ${ROOTS[*]}"
exit 0
