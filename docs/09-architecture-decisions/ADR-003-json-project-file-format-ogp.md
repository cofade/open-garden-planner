---
id: ADR-003
title: "JSON Project File Format (.ogp)"
status: "Accepted"
legacy_anchor: adr-003-json-project-file-format-ogp
---

# ADR-003: JSON Project File Format (.ogp)

**Status**: Accepted
**Context**: Need a project file format for saving/loading garden plans.
**Decision**: JSON-based .ogp files with embedded images (base64).
**Rationale**: Human-readable, VCS-friendly, no external database needed. Embedded images ensure portability.
**Consequences**: Large file sizes with embedded images. No binary efficiency. Version migration requires JSON schema evolution.

## Addendum — strict numeric boundaries and atomic persistence (A1, #453, 2026-10-13)

`core/plan_io.py` is the Qt-free `.ogp` read/write boundary. Normal open/save,
autosave and season reads/writes use it. JSON constants, exponent/conversion
overflow and non-finite nested values are refused before scene preparation.
During detached preparation, `ProjectManager` checks Qt's computed local and mapped
bounds, transform coefficients, every child and aggregate group before active-scene
mutation. This catches overflow from finite rotation, translation and image calibration
without duplicating Qt's geometry arithmetic. Decoded image dimensions are checked
before applying calibration. Opaque metadata strings remain text. The existing agent
canvas range (50–100000 cm) now has
one validator shared with the file boundary. Unknown items, finite off-canvas
geometry and ordinary legacy defaults retain their existing handling.

Encode with `allow_nan=False` before opening a destination, then write a sibling
temporary file, flush/fsync and atomically replace. Invalid data or an unsuccessful
replacement cannot truncate the previous file. Journal-pin reconciliation is made
in a detached candidate and applied to project metadata only after a successful
save. Rejected Phase 1 loads preserve filename, dirty state, history and recovery;
unexpected failures after scene mutation retain the existing protective reset.
The format remains 1.4. This is input/persistence hardening, not a geometry clamp
or a claim that finite hostile outlines have bounded rendering costs.

## Addendum — complete autosave snapshots (#797)

**Status:** Shipped in v1.40.5 (PR #932) after owner manual acceptance.

Autosave binds to the live `ProjectManager`. Its `recovery_dict(scene)` emits
`before_save` to flush pending form edits, then uses Save's `_build_project_data`
with detached journal-pin reconciliation. `AutoSaveManager` adds recovery metadata
and writes through the same atomic `write_plan` boundary. It never constructs a
temporary manager or serializes the scene alone: scene geometry is only one part
of a document. Autosave neither marks clean nor changes the current file, recent
files or the journal store. Recovery still loads a standalone complete document,
then makes it untitled and dirty. No format/version change. The rejected alternative
was a second list of plan-level stores in the autosave service, which would drift.

`tests/integration/test_autosave_recovery.py` compares a normal save and a recovered
autosave with every `ProjectData` field represented, exercises the window's actual
binding and pending name edit, and preserves the old recovery on a failed write.

**Owner-test addendum (PR #932): discovery and snapshot ownership.** A complete
snapshot was insufficient: startup searched only the untitled temp path, and
opening a saved original rebound the autosave path before cleanup, deleting the
very backup that had not been offered. Discover adjacent backups for the ten
recent plans at startup and for an explicitly opened original before its GUI
load. Ignore an older backup, preserve a declined one, and delete one only on
explicit Discard. Recover at most one document at startup; nested/delayed startup
callbacks must not overwrite recovered work. Programmatic loads remain non-modal.

`AutoSaveManager` owns the paths its current document wrote or adopted after
recovery. Save/discard cleanup uses that set, not the current filename, which may
already have changed. Adopted sources survive until a successful save or explicit
document discard. Cleanup keeps the named symlink entry, never resolves it into
another file to delete. The rejected alternative was unconditional deletion of
`~autosave_<current filename>.ogp` after load/Save As. Startup/open/No/Discard,
failed recovery, Save As, duplicate prompts and foreign-backup regressions are
pinned in `tests/integration/test_autosave_recovery.py` and `tests/unit/test_autosave.py`.

The review found that cleanup ownership alone did not protect a declined recovery
from the next autosave write. New snapshots therefore have a per-document UUID
suffix, reused on timer ticks. Discovery recognizes both legacy fixed names and
UUID names, validates their original association and offers the newest valid
snapshot first. Other versions remain on disk; no recursive directory search or
new settings/file-format field is introduced. Distinct untitled documents also
keep distinct temp snapshots. A deliberate GUI retry after failed Yes asks again;
the startup guard still prevents nested/delayed startup from replacing the work.
