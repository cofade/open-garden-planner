## Case study: Unicode wiki diffs fail in a Windows pipe (fixed 2026-10-09, issue #417)

**Symptom**: the real comparison CLI returned the expected drift exit code, but its UTF-8 subprocess reader failed to decode stdout. A longer diff also failed while printing a check mark.

**Theories entertained (wrong)**: none. The captured traceback and stream instrumentation identified the encoding directly.

**What instrumentation revealed** (real CLI against the existing wiki):

```text
[WIKI] stdout_encoding=cp1252 utf8_mode=0
[WIKI] non_utf8_byte_0x96=True
```

The next print failed because the code page could not encode a check mark.

**Root cause**: redirected Python stdout used the Windows system code page, while the parent correctly expected UTF-8. UTF-8 file I/O alone did not set console encoding.

**Fix**: `scripts/sync_wiki.py` configures its CLI stdout and stderr as UTF-8 before printing. Temporary diagnostic prints were removed.

**Lesson**: specify both file and CLI stream encoding for Unicode tooling. Pinned by `tests/integration/test_wiki_publication.py`, whose real subprocess comparisons exercise Unicode diffs without a UTF-8 environment override.


