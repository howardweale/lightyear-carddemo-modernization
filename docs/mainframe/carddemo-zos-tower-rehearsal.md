# CardDemo z/OS Tower integration rehearsal

Completed October 3, 2026 on branch `codex/carddemo-zos-tower`, using the pinned
public CardDemo fixtures. This is preparation for intake, not Maintec execution,
production equivalence or an actual Howard approval.

The workspace now enforces `carddemo-zos-no-values/1` for all routes, SSE, MCP
and exports. Four request kinds are connected: intake acceptance, authenticated
agent normalization proposal followed by Howard's decision, difference disposition,
and dual-role evidence release. The arrival view is read-only. INTCALC compares
fields exactly unless supplied a verified Tower decision or signed rule register;
the legacy comparison ledger is not consumed in parallel.

## Validation

| Check | Result |
|---|---|
| Selected intake, Tower, HTTP, workspace and mainframe suite | 171 cases: 165 passed, 6 skipped initially |
| Four pinned public-source cases previously skipped for missing environment setting | All passed with `CARDDEMO_SOURCE` set, including byte-preserving decoding of all 501 public binary records |
| Additional real Java divergence-to-request regression | Passed |
| Enhanced real Java timestamp-rule regression | Exact comparison divergent; verified Tower register equivalent; signed result replays offline |
| Final seven scoped disclosure/decision tests | All passed |
| Browser rehearsal | Arrival view read-only; Howard owner fixed; no page errors, external requests or submitted decision |
| Existing milestone documentation checks | 9 passed |
| JavaScript syntax and whitespace checks | Passed |

Across the selected cases and supplemental checks, 170 distinct regression cases
passed. Two existing cases remain skipped: optional MCP SDK registration metadata
(SDK not installed in this venv), and POSIX FIFO behavior on Windows. All seven
MCP method implementations were exercised over the actual loopback HTTP client;
the disclosure test did not depend on the optional registration test.

The no-values regression plants a canary into a public EBCDIC record and decodes
it, then tests request metadata, filenames, free-text notes, unrelated adapters,
every HTTP read route, SSE, write-route refusal responses, all seven MCP methods
and a valid released export. No planted record value appears. Additional cases
reject unknown evidence fields, private arrival paths, journal tampering, missing
agent provenance, agent decisions, expired/stale/tampered/superseded rules and
incomplete releases. Default comparison retains filler and trailing-space differences.

## Fresh complete public-data rehearsal

Arrival `arrival-20261003T150441Z-1bbce01faca0` contains two synthetic INTCALC runs
and one POSTTRAN run: 50 files, three runs, zero intake findings and one unapplied
timestamp proposal. The public bridge self-test passed with its previously
documented source-fixture exceptions. Values were not rewritten.

The unchanged local Java INTCALC candidate completed. Exact comparison without
normalization was **equivalent** for the first retained fixture, and offline replay
verified original bytes and the signed verdict without executing Java again.

| Signed record | Content SHA-256 |
|---|---|
| Rehearsal | `012add20ebece693c25e1fc2d07235ce16da734af203d78599336031a7552252` |
| Java execution | `1a376202f06d63d43e7152cc885b6ae74b7ddd88f98a96fb55598056011747c2` |
| Verdict | `39b177c571ddf1fd128be25e0b34bffd2dc83cc7e9056ad380c1be02a0f31789` |

Signed records, original/decoded files and screenshots remain local and ignored.
The report binds the implementation hashes used for this rehearsal. Prior signed
rehearsals remain unchanged and require their original implementation for replay.

No model calls, Docker calls or native z/OS runs occurred. B05 and `work/ms94`
were not accessed or modified by this integration. No production authority,
credential grant, approval, publication or campaign action was performed.

See [workspace setup](carddemo-zos-tower.md) and the updated
[Monday runbook](monday-runbook.md) for operator commands and the release boundary.
