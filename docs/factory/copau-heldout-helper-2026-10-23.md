# COPAU held-out helper: review before private use

This is an operator helper proposal, not a qualified private answer key or a
factory-run approval. CI uses public synthetic seeds and disposable files only.
Howard alone chooses and enters the real seed. No signing, model calls, Tower
writes, proof exports, database connections, candidate execution or batch twin
execution are part of this helper.

## Producer and selection

The producer is the frozen independent raw-COBOL reference in
`factory/carddemo-web/runtime/prove_slice.py:Engine`, using the **unchanged**
`Proof.run.authorizations` session body. It covers COPAUS0C and COPAUS1C plus the
linked COPAUS2C fraud reference. The helper verifies the complete effective
153-file judge freeze before imports. It retains the original session assertions,
including the fraud insert/removal after-state checks. It does not call
`Proof.__init__`, which would snapshot a database, or `seed.main`, which would
populate one. Shared BMS parsing and physical data codecs remain disclosed
dependencies; this is not a native CICS/IMS result.

The new adapter keeps the pinned public base records and creates seven held-out
authorization records from the operator's private 256-bit seed. Merchant display
identifiers, merchant IDs, cities and transaction IDs vary by scenario. The seed,
producer/version hashes, actual input fields, creation time, fixture/output
hashes, and selected output locations are retained only in the private store.

Selected strings are **literal 40-character fragments of the reference's returned
COMMAREA hexadecimal serialization**, corresponding to 20 real EBCDIC merchant
bytes. They are selected only if the original reference actually returned them.
No answer string is invented by hashing a result, padding a short message or
appending a canary. The 20-letter domain has approximately 94 bits of seed-derived
variation; this is a domain-size estimate, not a proof that an individual output
has that entropy. Repeated/low-diversity selections refuse preparation.

These fragments are evidence of held-out output exposure when reproduced; they
are not a correctness oracle or proof of malicious intent. Other implementations
can produce the same correct output. A 22-character merchant display field by
itself is shorter than the scanner's exact 40-character threshold: this design
**does not detect isolated short-field leakage**. It protects the selected
returned-state representation, not all possible encodings or all possible leaks.
The original casefold/whitespace/base64/hex/URL scanner and all limits are unchanged.

## Public corpus closure is a separate prerequisite

`tools/copau_public_corpus_index.py` collects the currently available public GitHub
artifact/Release catalog and verified downloadable bytes. It binds the 403-file
worker manifest, the retained Git ref/object inventory and a supplied graph export.
It never generates private values. It emits an **unreviewed** index and explicit
unknown-history entries for deleted assets/refs and an unreviewed query boundary.

GitHub's current API cannot prove the absence of deleted or expired historical
artifacts. A directory listing cannot prove which graph snapshots agents can
query. There is deliberately no `--allow-missing` or `--force-clean` option.
Before private generation, independent review must reconcile these entries
against retained inventories/archives and the actual F2 agent-query boundary.
That review must produce the exact approved corpus-index digest. Changing a
status string or deleting an unavailable entry without evidence is not a review.
Unavailable historical IDs stay explicitly listed and make qualification fail.
No reviewed complete closure index currently accompanies this proposal.

The scanner reads all 403 worker files, every blob reachable from the approved
retained refs, every inventoried public artifact/asset and all inventoried graph
snapshot files. It verifies exact file closure, hashes, sizes and ref/object
inventories. ZIP/JAR/wheel members are read in memory without extraction or
execution; nested archives, names and contents are scanned. Unsupported,
overlarge, encrypted, corrupt, linked or ambiguous input is an error, never a
skipped success. Large archives may therefore prevent qualification.

The public collision report contains only corpus hashes, file/record/window counts,
match/missing/error counts and public unavailable identifiers. It exposes no
matched values, seed, private path or private input. Match count means records
containing at least one scanner match, not the number of matching substrings.

## Operator sequence after exact-head approval and green CI

1. Use a separate clean checkout of the approved helper commit with the already
   reviewed Python environment and `psycopg` import dependency. Do not run in a
   worker workspace. Keep the private store outside every exposed root.
2. Collect public corpora before entering a private seed. Supply the exact worker
   bundle, a full retained public Git mirror, and all agent-queryable graph exports.
   `--graph-boundary` is a JSON record with schema `copau-query-boundary/1` and a
   positive `records` count; its full bytes must be reviewed against the F2 query
   boundary. It cannot establish completeness by itself.
3. Run the public collector with explicit `--worker`, `--manifest`, `--history`,
   `--graph`, `--graph-boundary`, a new `--public-destination` and a new `--out`.
   It performs only public GitHub GETs. Review the closure index separately and
   retain every unavailable identifier. Obtain approval for its exact digest.
4. Use #430's existing secure-store initialization if needed. This helper does not
   create or read a signing/HMAC key. Run from the approved checkout, setting
   `PYTHONPATH` to `src;.` on Windows:

   ```powershell
   python -B -m tools.copau_answer_key --reviewed-commit $ApprovedHelperCommit `
     --corpus-index $ReviewedCorpusIndex --reviewed-corpus-sha256 $ApprovedCorpusDigest `
     --exposed-root $WorkerRoot --exposed-root $GraphRoot
   ```

   Enter a new private 64-hex-digit seed at the hidden prompt. Do not place it in
   command arguments, environment variables, chat, Git or a CI job. CI seeds are
   rejected. Every actual exposed root must be supplied; indexed roots are also
   excluded automatically. The helper refuses to overwrite any existing output.
5. On any match, missing item or error, the helper retains private provenance and
   the report but produces no usable bundle. Preserve files and review the cause;
   do not keep choosing seeds to evade collisions. No automatic retry occurs.
6. Only after all four scans qualify, the private store receives
   `expected-source.json`, `copau-expected-values.json`, `bundle-binding.json` and
   `heldout-bundle-attestation.json`. The bundle matches #430's exact format. The
   bundle attestation has only SHA-256, byte size and count. These facts and the
   collision report may be posted; the private provenance and bundle must not be.

The helper target is review by Sunday 25 October. Complete private-key and corpus
qualification is still unproved. The go/no-go remains Wednesday 28 October
18:00 Pacific; unresolved coverage moves the factory window to about 6 November.
The first-run scope, 8-hour cap, 30 October 08:00–20:00 Pacific window and USD 10
cap are unchanged. F2 binding and `request_ready=true` require later concrete
inputs and CI validation; this proposal does not set readiness or grant authority.
