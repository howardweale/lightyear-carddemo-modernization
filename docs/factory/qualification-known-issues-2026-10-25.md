# Factory qualification known issues — 25 October 2026

This note separates multi-workload portfolio qualification from the first COPAU
run's controller verdict and factory build receipt. It grants no run, merge,
signing, spending, routing or gap-acceptance authority.

Static review found three related defects:

1. `src/lightyear_factory/qualification.py::_run_provenance` compares the
   `model-call-evidence` envelope `content_sha256` values with
   `intelligence.call_evidence_sha256`, which contains the enclosed call-content
   hashes. The real `ArtifactStore.write` hashes the envelope separately.
2. `tests/test_multi_workload_qualification.py::evaluation_root` reproduces that
   mismatch by putting envelope hashes in its synthetic intelligence summary.
3. `qualification.py` requires `request_manifest.schema_sha256`, but
   `providers.py::_request_manifest(instruction, payload)` omits it. The current
   OpenAI and additional JSON provider emitters use that shared manifest.

Consequently, `qualify_factory` cannot currently accept a real-model receipt
produced by these emitters. The first COPAU run's verdict and receipt do not use
`qualify_factory`: the controller finalizer uses `build_receipt.py`, whose
accounting-digest check compares the summary to the enclosed call-content hashes.
These qualification defects do not affect that first-run verdict or receipt.
This statement does not establish first-run readiness or waive any run gate.

Planned: after the first COPAU run, a separate PR must fix all three together,
before any D3 model-routing work. Preserve envelope hash validity, reference
staleness, run identity, schema, content hashes, provider identity, metrics and
totals. Compare validated enclosed call hashes one-to-one with the summary,
reject duplicates, missing and extra calls, and require the count to equal
`intelligence.calls`.

Planned: retain every existing test method and assertion, correct only the
fixture's call-hash derivation, and retain envelope-hash values as a negative
test. Add a real-finalizer positive case using stub transport, plus tampered
envelope/content, swapped call, missing/extra artifact and count-mismatch cases.
Show derivation and exact production/fixture hashes and hunks for Howard's
review before publication. No qualification, fixture or emitter repair belongs
in PR 455; all such proposals remain unpublished.
