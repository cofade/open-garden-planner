## Owner taste and measured correction - 29 October 2026

During PR #645 manual acceptance, the owner marked the gravel path's outer
bend: the 2D corner was rounded, but the raised 3D edging crossed it as a chord.
Preserve the rounded painted outline and keep relief on its actual rim,
including caps. A bevelled paved corner remains a separate style contract.

The existing ground-detail dimensions and palette stay unchanged. Independent
Qt stroke coverage/exclusion tests pin the actual rim; nominal square/butt
shadow footprints remain analytical. Reference: #605 and
`tests/integration/test_gravel_rim_relief.py`.
