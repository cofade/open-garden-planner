---
id: ADR-083
title: "Documentation structure: one file per ADR and a generated index"
status: "Accepted (2026-11-27)"
refs: ["#1035"]
---

# ADR-083: Documentation structure: one file per ADR and a generated index

**Status**: Accepted (2026-11-27)

**Context**: Until #1035 every architecture decision lived in one file,
`docs/09-architecture-decisions/README.md`: about 1.55 MB and 14,700 lines with 82 ADRs
and 131 addenda. The sections were not in number order (ADR-015 came before ADR-013).
An agent could only read that file in slices. It grepped for a heading and read a window
of lines, so it could miss an addendum further down or read a neighbouring ADR's text.
Two branches that each added an addendum to a different ADR still edited the same file
and often conflicted. A file-level graph, for example Obsidian's graph view or the
reference graph proposed in #1034, showed the whole record as one node.

**Decision**:

- **One file per ADR.** `docs/09-architecture-decisions/ADR-nnn-<slug>.md`. The number has
  three digits and is the stable key. The slug is the kebab-case, ASCII form of the title,
  at most 60 characters. A later title change does not rename the file. Every addendum
  stays inside its ADR's file, in its order. `adr-048-evidence/` and `assets/` stay where
  they are.
- **Heading levels.** The file's only H1 is `# ADR-nnn: <title>`. Addenda and other
  sections start at `##`.
- **Front matter, minimal and gated.** The keys are `id`, `title`, `status`, `refs`,
  `superseded_by` and `legacy_anchor`, in that order.
  - `title` and `status` are JSON strings. `status` is the ADR's own `**Status**:`
    paragraph, verbatim and joined to one line. The body keeps that line, and the body
    is the source: the generator copies it into `status`, and into `superseded_by` when
    it starts "Superseded by ADR-nnn". A version sync therefore edits only the body
    line, then runs the generator.
  - `refs` and `superseded_by` are optional JSON lists of strings.
  - `id` and `legacy_anchor` are bare tokens.

  JSON values are valid YAML, so any front-matter reader can parse the block. The gate
  parses it with the standard library alone.
- **Clean titles.** When the split ran, 30 titles ended in an issue/PR list such as
  `(issues #664, #771)`. That list moved from the H1 into `refs`. Bodies, status lines and
  addenda were copied verbatim, because the ADRs are the record of why.
- **A generated index.** `docs/09-architecture-decisions/README.md` stays at its path.
  `scripts/generate_doc_indexes.py` writes it from the front matter: a short preamble, then
  one row per ADR with number, title, short status and link. Nobody edits it by hand.
- **Old deep links keep working at ADR level.** GitHub builds a heading's anchor from the
  full old heading text, including the ref list that the cleaned title dropped, so the
  generator cannot compute an old anchor again. The split therefore recorded each ADR's
  old anchor once, as `legacy_anchor`. The generator writes it as a hidden
  `<a id="…">` in that ADR's index row, so an old link `README.md#adr-069-…` lands on
  ADR-069's row. Addendum anchors are not kept outside the repo. The in-repo links that
  pointed at an addendum were rewritten to the new file's anchor. ADRs from ADR-083 on
  have no `legacy_anchor`.
- **The gate.** `scripts/generate_doc_indexes.py --check` runs in the test suite, through
  `tests/unit/test_doc_indexes.py`. This list is the one statement of its rules; other
  documents link here. It fails when any of these hold:
  - a file name, its front matter, `id` and H1 disagree, or a file named `adr-…` in
    any letter case does not match `ADR-nnn-<slug>.md`;
  - a front-matter key is unknown or malformed;
  - `status` or `superseded_by` differs from what the body's `**Status**:` line says;
  - a number is used twice;
  - a number between ADR-001 and the highest is missing (a deliberate gap goes in
    `ALLOWED_GAPS` with its reason);
  - `superseded_by` names no existing ADR;
  - two `legacy_anchor` values collide;
  - the README differs from the generated output;
  - a tracked file links `…/README.md#anchor` that is neither an index stub nor a commit
    permalink.

  `scripts/check_skill_citations.py` accepts an ADR citation only when
  `ADR-nnn-*.md` exists and opens with that H1.
- **How to add one.** A new ADR is the next free number, as a new file, followed by a run
  of the generator. A new addendum is appended to that ADR's own file. The
  `ogp-docs-and-writing` skill carries the template.
- **The migration.** `scripts/split_adr_record.py` is a one-off and deterministic. It
  reads the old file from git, writes the ADR files, regenerates the index and rewrites
  in-repo anchor links. It also proves that each ADR file restores to its old section,
  and that every old line is in an ADR file, the index preamble or a blank separator. It
  ran for the last time on #1035's branch, after a rebase. From then on the ADR files
  are the record, and a re-run would overwrite their later edits with the old text. The
  script therefore refuses when the revision's README is already the index, and when an
  ADR file differs from the old text (unless `--replace`). It stays in `scripts/` as the
  record of how the files came to be.
- **A branch that still edits the old file** moves its hunk by hand into the ADR's own
  file, with its headings one level up, and then runs the generator.

**Consequences**:

- An agent reads one decision whole, with all its addenda. A diff or a merge conflict
  touches the one ADR it changes.
- A file-level graph gets one node per ADR.
- A branch opened before the split that edits an ADR must rebase. Its addendum then goes
  into the ADR's file by hand, and the generator must run after it.
- The front matter holds a second copy of the status. The gate keeps the two copies
  equal, and the generator writes the front-matter copy.
- An addendum deep link from outside the repo, for example an old issue comment, now
  lands on the top of the index, not on the addendum.
- The pattern is meant to extend to the functional requirements (#1036). There, topic
  files are keyed by ID prefix, and the shared generator writes their index.
