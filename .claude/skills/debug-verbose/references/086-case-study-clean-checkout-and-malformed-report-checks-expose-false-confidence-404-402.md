## Case study: clean checkout and malformed-report checks expose false confidence (#404/#402)

**Symptom:** the initial local lock check passed, but the reviewer's fresh Windows checkout
failed it. **Assumption refuted:** a byte comparison passing in the developer working copy
proves portability. **Key measured evidence:** `[LOCK] checkout CRLF: 1857 export CRLF: 0
normalized equal: True`. Git autocrlf transformed a generated artifact. **Fix:** LF attributes
for uv.lock and pylock.toml; rerun the real CLI in a fresh checkout.

The same review's malformed coverage probe declared two statements with one covered, but
repeated a covered line eight times: the old aggregation reported 8/9 and passed an 80% floor.
**Root cause:** counting XML elements without checking file/line identities or supplied totals.
**Fix:** refuse duplicate files/lines and contradictory totals before aggregation, with an
actual subprocess refusal test. A successful write test also does not prove rollback: an
injected failure on the second version-sync file now verifies the first file was changed and
all four inputs were restored. **Lesson:** measure fresh checkout behavior and adversarial
report shape as well as ordinary tool output; keep temporary diagnostics out of commits.


