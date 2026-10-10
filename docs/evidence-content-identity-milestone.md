# P3 content identity extraction — October 10, 2026

`lightyear_evidence.content` implements a named-byte view of trees and archives with explicit selection policy, required entries and bounds. The B06 wrapper supplies its unchanged exclusion names, policy ID, manifest requirement and legacy path interpretation. JAR content is never filtered; omitted folder paths remain explicit evidence. No archive is extracted or rewritten.

`VerificationReadCache` is created inside each observer manifest verification. Archive bytes and opened nested ZIPs are reused only within that pass and closed even on refusal; a later pass reads the source again. No global cache or native adapter is introduced. Generic raw-name validation also checks `ZipInfo.orig_filename` because Windows normalizes backslashes; B06 explicitly retains its historical filename interpretation so this extraction does not change its acceptance contract.

Validation: six generic tests cover mutation, omission, duplicates, traversal, stable identity, tree/archive equality, cache reuse and fresh passes. Unchanged B06 tests: capture fidelity 10, built-native 15, build-once 7, observer-v2 18 (8 ran, 10 optional native-evidence cases skipped). Exact old/new B06 archive byte maps and omission policy compared equal on public fixtures. Existing tests and historical evidence remain byte-identical; no frozen checkout changed. No Docker, model or native run.

Next adopter: Oracle saved-package inventory, to share archive identity and a per-replay cache. That adoption is outside this PR.

Standalone worker preparation also copies and hashes the shared package at the worker import root. The package files are copied from the selected Git bytes for frozen preparation. A clean `python -S` import test checks that no installed or checkout package masks a missing worker dependency. Historical snapshots are not modified.
