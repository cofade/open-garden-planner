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

## Addendum: the functional requirements as prefix-keyed topic files (#1036)

**Status**: Accepted (2026-11-28)

**Context**: The single file of functional requirements had the same problems as the ADR record
(about 317 KB, 1,584 lines). Its 36 numbered chapters plus FR-EXAMPLE and FR-STATS
followed the delivery history (phase, package, user story), not the product. One family
was spread over several chapters: FR-AGENT over four, FR-SNAP over three. Some
requirements had no ID or sat in a table, and three definition forms were in use:
`- **FR-X-nn**:`, `- **FR-X-nn:**` and `### FR-SUN-09: …`.

**Decision**:

- **Topic files keyed by prefix.** `docs/functional-requirements/<topic>.md`, plus
  `3d/<topic>.md` for the 13 `FR-3D-*` families, one file each. The file name is a
  kebab-case topic name, never a number. Every ID prefix belongs to exactly one file. The
  owner approved the map before the move (2026-11-28); the generated index states it.
- **Front matter.** `title` (a JSON string) and `prefixes` (a JSON list).
  The body opens with the only H1, `# <title>`. `##` sections group the families. A
  section may end with an `Acceptance:` paragraph that names its tests.
- **One definition form.** A requirement is one top-level bullet whose first word is its
  bold ID: `- **FR-<PREFIX>-nn**: …`, with a number of at least two digits. An issue ref
  may sit between the ID and the colon: `- **FR-IMG-12** (Issue #659): …`. Detail goes in
  that bullet's indented sub-bullets and
  paragraphs. #1034's reference graph can therefore read every definition with one rule.
- **Every requirement has an ID.** The move gave the ID-less ones the next free number of
  their family: FR-OBJ-05 … FR-OBJ-08 (the object catalogue, checked against
  `ObjectType` and `PathFenceStyle`), FR-OBJ-09 (the property object table), FR-PLANT-26
  (the per-plant metadata table) and FR-UI-23 … FR-UI-28 (the object gallery).
  Smart Symbols (old chapter 25) were dropped: their UI was retired in #770 and their
  engine in #1009, so the chapter described nothing a user can reach. Chapter
  history (phase, package and user-story labels, scope notes, the retired Paper Space
  note) was dropped; git history keeps it.
- **A generated index.** `docs/functional-requirements/README.md` lists each topic file
  with its title, prefixes and count, and each prefix with its file and next free ID.
  The same `scripts/generate_doc_indexes.py` writes it. Old chapter numbers (`FR-<n>`)
  are not kept: links into the deleted file 404.
- **The gate.** `generate_doc_indexes.py --check` (through `tests/unit/test_fr_topic_files.py`)
  also fails when any of these hold:
  - a topic file name is not kebab-case or sits more than one folder deep;
  - its front matter is malformed, or its H1 differs from its `title`;
  - a prefix is not `FR-<NAME>[-<NAME>…]`, is listed twice, has no requirement, or is
    owned by two files;
  - an ID uses a prefix its file does not own, or is defined twice;
  - a top-level bullet has no ID, an ID's number has one digit, or an ID is defined in
    another form (colon inside the bold, nested bullet, heading, table row, blockquote,
    bold without a bullet);
  - the index differs from the generated output.

  The same test file also fails when a tracked file names the deleted single file or
  cites a chapter number (`FR-<n>`, `FR-<n>.<m>`). Exempt are the issue-title mirror, the
  2026-10 audit (a dated snapshot), commit permalinks, the migration and the tests' own
  fixtures. `scripts/check_skill_citations.py` reads the topic files and resolves the full
  ID grammar (`FR-3D-WS-01`, `FR-ICON-3C-02`, `FR-AGENT-12a`) and every family name
  (`FR-SNAP`, `FR-3D-*`), so a bare chapter number or a misspelt family fails there too.
- **How to add one.** Append `- **FR-<PREFIX>-nn**: …` with the prefix's next free number to
  the file that owns it, then run the generator. A new family goes into one file's
  `prefixes`. The `ogp-docs-and-writing` skill carries the template.
- **The migration.** `scripts/split_fr_record.py` is one-off and deterministic. It reads
  the old file from git and places every ID by `LAYOUT`; `RULES` decides each ID-less
  block (drop, acceptance paragraph, or new entry). Its proof: every old ID is in exactly
  one topic file with the same words, except two cross-references to old chapter numbers
  that `TEXT_FIXES` names (in FR-SUN-06 and FR-UI-ICON-01); every old non-blank line is an entry, a heading or
  a block that exactly one rule handled; and the only new IDs are the ones listed above.
  It ran once, on #1036's branch.

**Consequences**:

- A reader finds a capability by topic, and the index answers "which file owns FR-SNAP?"
  and "what is the next free FR-SNAP number?".
- A link to an old chapter anchor of the deleted file 404s.
- Requirements are ordered by ID inside each family, not by delivery date.
