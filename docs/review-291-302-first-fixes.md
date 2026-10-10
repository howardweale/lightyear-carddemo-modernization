# PRs 291â€“302 review: first corrective batch

This batch implements the urgent execution hold and focused admission, cache and
host-test fixes from Howard's October 10 review. It is not completion of the
whole review list. Historical evidence, signed catalogues, fixture v2, B04â€“B06,
work/ms94, template-r1 and J1 are unchanged. No private intake, native/container
run, model call, private-key read or machine configuration change is involved.

## Implemented

- [October 11 engineering hold](b06-engineering-review-hold.md): supervisor,
  worker and native execute refuse before signing/Docker. Renewed approval is
  required after the amended observer is implemented and tested.
- Census now rejects engineering plans/paths before reading evidence and rejects
  engineering receipts/execution metadata. Direct `replay_stream` rejects
  engineering receipts and relocated files beneath an engineering marker.
  The entrypoint test actually invokes census and direct replay.
- VerificationReadCache validates each loader result against the expected
  SHA-256 key before caching; failed loads cannot poison later reads. Archive,
  entry-count, total-uncompressed, nested-member and depth limits precede
  decompression. The generic content reader checks file size before loading a
  path and checks archive entry count/declared total before hashing members.
  Limits are per archive/member, not a claimed process-wide memory bound.
- Captured-refusal, unmatched-return and stress tools select the explicitly
  configured JDK executable names on Windows or Linux. A missing configured
  tool fails instead of falling back to PATH. Host stress defaults to an explicit
  `-Xmx192m` and records that limit; native-volume/3,000-class stress is not yet
  implemented or claimed complete.
- An Ubuntu 24.04 Corretto 21 CI job sets B06_HOST_JDK and runs real JDI probes,
  including startup and captured-return dispatch, plus the refusal/cache tests.
- The two requested native/replay development files are restored to LF. The
  edited posting-replay file also uses LF. A prospective CI check rejects CRLF
  in changed Python/Java files under src and tools. It intentionally does not
  rewrite unrelated historically pinned sources or B05 files.

## Validation

The final local suite ran 94 tests in 34.796 seconds: 83 passed and 11 were
explicitly skipped. The LF guard and diff check passed; byte comparison proved
the two requested files differ only by CRLF-to-LF normalization. Final-head CI
is reported separately on the PR and is not inferred from local success. Host
probes use Corretto 21.0.10_7 locally; CI uses its recorded Corretto 21 version.
Windows can skip the ProcessHandle.Info command/arguments check when the JVM
omits that metadata. Ten historical observer evidence cases require private
local fixtures and remain explicit optional skips; host JDI probes are enabled.
No CI or host result establishes native memory stability or qualification.

## Remaining review work

| Review item | Still outstanding and why |
|---|---|
| 1 | Memory-bounded observer, lifecycle/heap telemetry, explicit runtime limits, capped diagnostic mode and exact amended approval: require the substantive memory redesign and host proof; execution stays held |
| 2 | Separate engineering key, pinned source/observer approval binding and real Linux native-adapter acceptance: not replaced by labels or this hold; require a reviewed authority contract and future approved native execution |
| 3 | Native-like stress with thousands of distinct stack classes and measured heap curve: portability/heap cap alone do not satisfy it |
| 4 | New r3 metadata/hash supplement from the preserved stream, including accepted unmatched indices and last audit context: no historical record rewritten |
| 5 | Measured JLI/CDS/dump alternatives and JDK/application split: no numbers invented from source inspection |
| 6 | Business-rule scoping, summaries and new v3 fixture: separate semantic correction and regeneration work; v2 and signed v1 records preserved |
| 7 | Mounted-reader hash binding, pinned pre-extraction equality harnesses, real before/after build-once observations, CardDemo adopter and ledger update: cache bounds and LF guard do not imply these are complete |
| 8 | Historical merge-commit CI audit/reruns and branch protection: not represented by this PR's tests; repository settings unchanged |

## Merge gate

No merge is authorized by this build request. Howard's commit-specific approval
and all required checks completed green on the final head are necessary. Queued,
running, cancelled or failed required checks do not satisfy the gate. The prior
merges are historical facts, not precedent for bypassing this rule.
