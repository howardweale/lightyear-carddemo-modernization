# Control Tower v2: combined review remediation

The changes implement the two review rounds together on
`codex/decision-console-review-r1-r2`, based on main
`1b204fe7cf36f180f4a96ab36070536b6d4661cd`. They change the Decision Console,
its future-controller admission library, regression tests and operating guide.
No frozen measurement, running B05 file, historical signature or verdict was
changed. B04 remains VOID. No model calls, native database runs or campaign
operations were performed. The [milestone document](control-tower-review-v2-milestone.md)
records the delivery scope; Git history and the corresponding pull request record
publication and merge status.

## Finding coverage

| Review finding | Implementation and verification |
| --- | --- |
| 1. Live-journal disclosure | Version 2 release exports freeze in the second approval transaction. The approved bundle binds a disclosure contract and signed prefix commitments. Only the two release-event bodies are added; later events cannot change the export. Private canaries before and after release are absent. |
| 2. Qualification trust | Acceptance, catalogue reads, publisher and catalogue-check use a separate externally configured qualification key. Regression uses two distinct disposable keys and rejects the wrong key. |
| 3. Authenticated authorship | Independent decisions bind a journaled proposal event and derive authorship from its authenticated actor. Inbox and rule-file author spoofing is refused. |
| 4. Subject supersession | Authorization and acceptance checks find newer decisions by subject hashes across request IDs. Tests revoke an earlier authorization and qualification acceptance through new requests. |
| 5. Isolation | Two populated scopes run separate live HTTP servers. Every read/write route, bounded SSE response and all seven MCP tools are exercised with own and foreign credentials. Evidence-source canaries and their derived validation hashes are distinct. |
| 6. Blocking files | Reads reject non-regular/reparse files. POSIX uses nonblocking/no-follow opens. Evidence hashing and trusted validators run outside the writer transaction; the journal head is rechecked before commit. |
| 7. Review dates | New decisions enforce a maximum review interval of 366 days. |
| 8. Logout | Logout requires authentication, not domain-write roles. Auditor, partner and empty-role sessions can end. |
| 9. Two release identities | A second release role held by the first approver is refused before a decision is appended. |
| 10. HTTP bounds | Socket timeout, short-body timeout response and a catch-all 500 for deeply nested JSON are tested. |
| 11. General failure fingerprints | Fingerprints bind gate status, error type, stage and message hash. Origins come from evidence. A non-accounting business failure regression proves detection is general. |
| 12. Actual observer integrity | Tests call the adapter, verify complete signed journal prefixes, detect tampering, and check bytes/mtime preservation. The POSIX test overlaps actual projection with replace/append operations. |
| 13. Windows writer safety | Live Windows observation fails closed before opening producer files. A Windows concurrent writer completes 80 progress/active replacement cycles while projections are refused. Completed immutable exports are supported. Safe live Windows observation is **not claimed**; see below. |
| 14. Campaign identity | Future controllers require the campaign hash in the verified authorization and refuse constructor/binding mismatches. |
| 15. Multiple pauses | Each pause needs its own exact signed resume. An unrelated continue and a resume of only one of two pauses remain blocked. |
| 16. Historical display | Published terminal reports and receipts are read when local run data is absent. Missing gates produce unavailable evidence, not false binding mismatches; unknown historical slots are not presented as pending work. |
| 17. Budget alerts | Alerts cover calls, compilations and hours only. Slot completion no longer triggers budget alarms. |
| 18. Clock handling | Epoch and ISO times normalize to aware UTC; missing/naive values are guarded. Signed start times drive elapsed/stale alerts. Missing recorded costs remain unavailable. |
| 19. Catalogue lifecycle | Known pending changes yield upcoming-expiry warnings. Active-rule membership changes advance register major versions; metadata renewal does not. Review-due reminders and dependent-entry warnings are rendered. Retirement permits publishing an expired dependency record. |
| 20. Portable projections | Evidence identities use root-relative POSIX paths; relocated fixture roots produce equal projection hashes. |
| 21. Malformed campaigns | Invalid campaign projections are isolated. A live SSE regression preserves a healthy campaign alongside an unavailable malformed campaign. |
| 22. Smaller alert issues | Locations must be nonempty; gate declines require rejection; equipment suspicion alerts; legacy approval identities hash the original bytes. |
| 23. Partner disclosure | Status uses field allowlists without per-journey details. Separate partner shares remain independent; revoking one does not revoke another. |
| 24. Agent sessions | MCP sessions refresh on expiry. Draft labelling follows the agent role. |
| 25. Authority separation | Console configuration, key targets, credential output and qualification trust must remain outside the engine-writable root. Sensitive directories are refused as evidence paths. |

## Windows limitation and evidence

The review's suspected race was reproduced with disposable files. An open reader
using Win32 `CreateFileW` and `FILE_SHARE_READ | FILE_SHARE_WRITE |
FILE_SHARE_DELETE` still caused Python's `os.replace` to fail with WinError 5 on
this host. The writer succeeded with the reader closed. This is consistent with
the documented distinction between destination replacement through MoveFileEx and
newer NT rename semantics in the
[CPython Windows replacement discussion](https://github.com/python/cpython/issues/90161).

Retrying or copying on the reader side cannot undo an error already delivered to
the unmodified frozen writer. Consequently this patch does not advertise safe
live Windows polling. Registry `read_mode: live` is refused before evidence I/O
on Windows. `read_mode: immutable-export` is an explicit operator assertion that
the selected, separate export has no writer; it must never be used to relabel a
live campaign. A future producer-coordinated export protocol could support live
status, but is outside this patch and cannot be added to frozen B05.

## Compatibility and migration

See [the operating guide](control-tower-decision-console.md) for external authority
configuration, qualification trust and release format details. Existing evidence
is preserved; old approvals do not acquire new bindings by reinterpretation.
Requests needing independent review must first journal an authenticated proposal.
Future campaign authorizations require an explicit campaign identity. Old v1
release proofs need fresh reviews before producing a new frozen v2 export.

The final release-event signatures cannot be hashed into their own approval input.
The approved bundle therefore includes the exact disclosure format and signed
pre-release commitments; the final signed artifact includes the two resulting
decisions and commitments ending at the second decision. The verifier reports
validity at that archived head, not a claim of present-day authorization. Curated
bundle members are themselves approved disclosure; a private journal must not be
included as a member.

## Local validation

- Decision Console suite: 50 tests, successful on Windows; two POSIX-only tests
  skipped (FIFO rejection and concurrent open-destination replacement).
- Legacy decision, action-plan, run-index, live-control-tower, comparator, workflow
  history/campaign and paired-campaign compatibility suites: 117 tests passed.
- Local Chromium Decision Console flow passed with zero external browser requests.
- Additional key/credential location refusal test passed after the final security
  pass. Cross-platform CI already discovers the new tests; Linux/macOS results
  are not claimed by this local run.
- The compatibility run emitted a legacy Explorer SSE teardown traceback after
  its disposable database was removed; its unittest result was successful. That
  unrelated Explorer implementation was not changed.

The archived B04 regression fixture is still checked against its original byte
manifest and signatures. No public publication, qualification or measurement
result is created by these disposable tests. Live Windows observation remains a
disabled capability, not a completed live-monitoring qualification.
