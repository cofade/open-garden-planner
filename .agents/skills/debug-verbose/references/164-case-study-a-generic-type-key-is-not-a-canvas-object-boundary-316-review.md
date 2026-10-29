## Case study: a generic type key is not a canvas object boundary (#316 review)

**Symptom.** Template export removed a plant's custom_fields when its type value
was background_image or journal_pin, and a list/dict-valued type raised TypeError.
**Wrong theory.** Every nested dictionary with the item discriminator was an item.
**Evidence.** Four observed-failing custom-field cases reproduced both silent
removal and the unhashable-type traceback in test_custom_type_fields_are_data_not_canvas_records.
**Root cause.** Structural record filtering was mixed into the generic recursive
path scrubber. Arbitrary custom data shares dictionary keys with scene records.
**Fix.** Filter image/pin types only in structural objects and children sequences;
preserve the generic recursive path scrubber for all other data. The four cases pass.
**Lesson.** Choose record semantics from the enclosing schema boundary, not a key
name that untrusted or custom metadata can also use.

