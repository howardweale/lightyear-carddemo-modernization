# CI evidence guards — 17 October 2026

Authorized by Howard; implemented by Codex. Validation is CI-only and remains pending until the published head completes its workflows.

The existing Bash and PowerShell verification wrappers already discover the full tests directory. A new static collection check follows those literal wrapper calls and explicit unittest module/discovery commands, and rejects any test module with no collection route. The three named review tests also run in the scenario-policy job.

The image preflight tests call the actual verifier with in-memory API and ZIP fixtures. They accept matching bytes and reject changed, missing, duplicate or incompletely listed artifacts. They download and launch no image.

The primary compiler mirror now has a 60-second retry budget before fallback. Curl may still finish an individual attempt within its separate timeout; this is not a hard 60-second wall-clock promise.

Scope overlays must match an explicitly accepted canonical hash. The original dated transcription is preserved. Any later promotion to twin-and-zos additionally needs an exact-row-bound, accepted equivalence-review decision verified against an externally supplied public key and journal head. The independent denominator cross-check parses the overlay separately. No new production overlay or authority is created.

New commit references in changed current records must have a matching entry in `commit-claims-2026-10-17.json`. Each entry names the record, reference, full commit and role. A source claim supplies `source_path` and the exact Git blob SHA-256; a merge claim supplies its PR number, exact parents and head commit; an ancestor claim supplies its descendant. Resolution alone is insufficient. Earlier dated records remain preserved.

Disposable CI keys and signatures are authorized only for the guard tests. Real requests remain unsigned; no import, activation, attempt consumption or Phase 2 execution is performed.
