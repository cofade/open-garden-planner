## Case study: an empty Qt bounding rectangle hides an infinite line span (#453)

**Symptom.** A construction line with x1=-1e308 and x2=1e308 passed finite-input
validation. Qt returned an empty bounding rectangle despite infinite dx and length.
**Wrong theories.** A finite or empty bounding rectangle does not prove that the
underlying primitive has finite intermediate geometry.
**Evidence.** Independent review measured infinite QLineF dx/length. The real
load-preservation regression failed DID NOT RAISE ValueError before the fix.
**Root cause.** The raw preflight omitted endpoint spans, and Qt's empty rectangle
concealed the overflow from the detached bounds check.
**Fix.** Check both endpoint differences and hypot length before construction,
including point/anchor/control segments and polygon closing edges. Check arc
endpoint/midpoint angle sums at the raw boundary; do not construct enormous sweeps
to test arithmetic. Polyline, polygon and arc regressions also failed first.
Pure huge-finite Qt path rendering limits preserve the serialized model and stay
outside A1; no coordinate cap or zero-length rejection was introduced.
**Lesson.** Validate primitive arithmetic when invalid geometry can collapse to an
empty bounding rectangle. Keep the detached Qt composition gate as well.


