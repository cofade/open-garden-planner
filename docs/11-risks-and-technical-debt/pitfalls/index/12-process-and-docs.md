# Process & Documentation Pitfalls (PF-PRC)

| ID | Rule | Status | Where | Legacy |
|---|---|---|---|---|
| PF-PRC-01 | Read a persisted setting with the API that wrote it, since a `QSettings` slash key is a registry subkey, and check the branch's own diff before treating a behaviour report as a bug. | standing | [12](../12-process-and-docs.md#pf-prc-01) |  |
| PF-PRC-02 | A user-visible claim is delivered only when a test drives the user's own path and asserts what reaches the user, so grep every new result field for its consumers. | standing | [12](../12-process-and-docs.md#pf-prc-02) |  |
| PF-PRC-03 | Before treating a UI that does not update as a bug, grep the ADRs for an accepted decision it may contradict, and render any change to pixels before trusting it. | standing | [12](../12-process-and-docs.md#pf-prc-03) |  |
| PF-PRC-04 | Never edit non-ASCII files with PowerShell `Set-Content -Encoding UTF8`, which double-encodes UTF-8 into mojibake; edit them with Python using `encoding="utf-8"` or with the `Edit` tool. | standing | [12](../12-process-and-docs.md#pf-prc-04) |  |
| PF-PRC-05 | A file-and-line citation copied into skill or agent-context files drifts silently as unrelated code grows, so every cited identifier is resolved by a mechanical gate rather than by review. | standing | [12](../12-process-and-docs.md#pf-prc-05) |  |
| PF-PRC-06 | A regression test for a gate defect has teeth only if it asserts the original defect itself, so reintroduce the bug and watch the test go red before trusting it. | standing | [12](../12-process-and-docs.md#pf-prc-06) |  |
| PF-PRC-07 | A drift-tolerance window must sit strictly below the smallest measured real drift it has to catch, so the citation checker's `_SYMBOL_WINDOW_LINES` is 20 lines rather than a generous guess. | pointer | [12](../12-process-and-docs.md#pf-prc-07) |  |
| PF-PRC-08 | The citation checker's window limits drift distance but not symbol selectivity, so a citation of a common identifier such as `execute` in a large file is only weak protection. | standing | [12](../12-process-and-docs.md#pf-prc-08) |  |
| PF-PRC-09 | Treat an issue's verified repo facts as claims to check against the code, and confirm that a reusable-looking method can see the shape of the question before reusing it. | standing | [12](../12-process-and-docs.md#pf-prc-09) |  |
| PF-PRC-10 | Verify every file-and-line citation and every reuse instruction in an issue against the code before writing any code, treating the issue's context section as a hypothesis. | standing | [12](../12-process-and-docs.md#pf-prc-10) |  |
