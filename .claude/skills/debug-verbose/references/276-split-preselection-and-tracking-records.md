# Case study: Split cut the lawn under a selected raised bed (PR #981)

**Symptom.** In the German raised-bed example, a cutting line across the selected
bed, gravel path and lawn split the lawn.

**Wrong lead.** A crossed outline or a blue selection border does not establish
that a shape is in scope and eligible. Inspect both before debugging the geometry.

**Key trace.** The isolated app loaded the actual German example and printed
`[SPLIT] selected ['RAISED_BED'] scope None`. The bed, path and lawn each returned
two geometric pieces for the same line. The eligibility checks returned
`The shape has tracking records that a split cannot preserve` for the bed and
`This shape type has no polygonal form to split into` for the path.

**Root cause.** Toolbar activation always armed the whole scene, even with an
explicit selection. The selected bed's soil and succession references excluded
it, while the lawn passed the eligibility check.

**Lesson.** Capture the scope before filtering candidates for eligibility.
Exercise a refused selection over an eligible background and assert that both
objects and undo history are intact. See
[the split integration tests](../../../../tests/integration/test_split_shapes.py).
