COBOL semantics runtime slice 1A (no PR yet, r1)
Proposed storage foundation only. No candidate, wrapper or gate imports this code.
The trusted caller supplies reviewed PIC metadata; no copybook parser is claimed.
Fields read current arena bytes on each call; aliases share storage. Reload changes
logical length and clears unused bytes. Out-of-length views refuse on every access.
Raw load/snapshot/replace are trusted storage APIs, not approved candidate APIs.
Their future exposure is subject to the slice-4 source checker and closed wrapper.

Pic.parse handles unedited S/9/V/P and repetition; 18 arithmetic digit positions.
Binary storage is 2/4/8 bytes by stored PIC digits; packed has a trailing sign nibble.
NOPFD numeric decoding and NUMCLS(PRIM) decimal class tests are separate. Binary
class semantics are not supplied here. Exact writes refuse loss and unsigned
negative inputs; they do not implement MOVE, arithmetic truncation or SIZE ERROR.
Signed decimal negative zero is retained. Binary zero has no negative representation.
Invalid digits/zones, nonzero packed padding and out-of-PIC binary sending data
refuse under the valid-data profile. INVDATA recovery is not implemented.

Slice 1B supplies descriptor compiler/auditor and variable layout; 1C supplies
operation-specific arithmetic and assignment policy. No logical slice is declared
complete by 1A. All five slices and independent qualification precede runtime use.
Documented semantics, not mainframe-proven.
Candidate output is runtime-bound Java, not idiomatic Java.

Independent suite: Claude authors a separate codec JSON file under VECTOR-SCHEMA.
Expected values are not obtained from this runtime. Each vector hash is SHA256 of
canonical sorted UTF-8 JSON excluding sha256, ensure_ascii=false, no spaces/LF.
The raw file hash and profile hash are independently pinned. IDs are unique and
every vector has an IBM 6.4 locator and a worked-example or stepwise derivation.
The CI driver --independent-sha256 argument requires author Claude and exact bytes.
No independent suite has been supplied: qualification is BLOCKED. The new workflow
runs author-derived regression vectors only and does not claim independent proof.
Later suite admission must include exact review of immutable bytes and workflow pin.
Arena assertions derive expected offsets and byte preservation directly from inputs;
they check implementation invariants, not a general COBOL REDEFINES/group MOVE verb.
No local Java compiler, suite or runtime was run in preparing this proposal.
