## 8. Release-workflow races (chore race; #229 date matching)

Source: §11.4 ("Release workflow race condition with chore commits"),
`.claude/skills/finalize-us/SKILL.md` steps 8–9, commits `dfddf28` and `745c4bb`.

- Race 1: post-merge chore commits (version sync + roadmap) land ~37 s after the PR
  merge, but the release build takes ~2m50s. The chore commits' Release runs started
  before the new tag existed, computed a stale version, and failed with "release with
  the same tag name already exists". Fix: `if: "!startsWith(github.event.head_commit.message, 'chore:')"`
  on the release job. Later hardened (commit `745c4bb`) to also skip **scoped**
  `chore(...)` commits, not just bare `chore:`.
- Race 2 (#229, fixed in the `finalize-us` skill itself, commit `dfddf28`): the
  end-of-story automation waited for the CI release by grepping `createdAt` against
  `$(date ...)`. Two failure modes: local-vs-UTC mismatch, and same-day re-runs — plus a
  date match **cannot detect failure**. Fix: capture the top release tag *before* the
  merge, then poll until the top tag *differs* (tag-transition, timezone-independent,
  ~10 min ceiling), and stop-and-report if no new tag appears. PR checks are gated with
  `gh pr checks --watch --fail-fast`.
- Status: closed. No pinning test (workflow-level); re-verify against
  `.github/workflows/release.yml` and finalize-us step 9 before changing either.

---

