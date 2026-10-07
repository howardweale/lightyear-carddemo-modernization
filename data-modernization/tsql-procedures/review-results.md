# PR269 review: ordered results and procedure contracts

October 7, 2026. Operator review; not independent attestation. Zero model calls.
Native work ran on the previously approved dedicated x86-64 Ubuntu Linux VM.
No B06, Windows Docker, B05, template-r1 or work/ms94 execution or modification.

## Fresh native result

Run 015 executed **108/108 planned pairs** in **312.470 seconds**. All captures
and signed outcomes were preserved; no fatal error. Public-corpus acceptance
passed for 43 authored procedures across 26 trap families:

| Measure | Result |
| --- | --- |
| Individual pair verdicts | 40 equivalent, 53 divergent, 15 insufficient evidence |
| Aggregated procedure/twin variants | 41 equivalent correct variants; 43 divergent wrong variants; 2 correct variants require policy decisions |
| Row-order trap (family 26) | Correct twin equivalent; wrong NULL/collation order divergent |
| Ambiguous UPDATE FROM wrong twin | Divergent on all 5 fresh repetitions |
| Named/typed invocation | dbo.calculate, positive and negative integer division cases, both twin variants |
| Offline replay | 108 pairs, 1,856 files verified on Linux and again locally |
| Actual cleanup | Owned-label containers, networks and volumes all absent |

Aggregate coverage is recomputed across bound cases/repetitions; it is not the
sum of individual equivalent verdicts. All 15 insufficient individual outcomes
are retained. Repeated coincident outputs do not approve unordered business
choices. Both correct policy-gated families remain pending.

SQL profile set/read back: Latin1_General_100_CI_AS, compatibility 160. Images:

- SQL Server: `sha256:4402d880dd4c34bfa7d8705e56a86cd6c88da80a1f6bbbe741f999e76264a090`.
- PostgreSQL/plpgsql_check: `sha256:b03ef125d79567173ab5622d9c5b05c9baf353a4eb78f8c13a938de4141de30d`.

## Audit bindings and costs

| Artifact | SHA-256 |
| --- | --- |
| Signed native report content | `c3b2534082f961beb0b9f8d463975c23fb95ee80c9804737216ebae81bb78fee` |
| Recorder public key bytes | `6be40d9f3e66163de4f25e7b7af07659348ac963bef2286c07f83f02dac3cb63` |
| Linux audit plus actual cleanup checks | `9e69393318192f9100f8751e66ee0a26afa46232bc3f41d6898a219e1f8c6fd4` |
| Local independent audit | `7b1dc6bf0bbf3fe4502da90acd5a66a31ce83e260192cc83522c9b8a9e28543d` |

Linux independent replay: 1.793 seconds. Local replay: 1.06 seconds rounded.
Those costs are separate from native duration. 108 SQL resets totalled 78.306
seconds (mean 0.725, min 0.688, max 0.838); PG resets totalled 6.616 seconds
(mean 0.061, min 0.057, max 0.088). Throughput: 20.738 pairs/minute for this small
public corpus. Preparation total monotonic time was not measured. No model cost.

The signed run binds its exact code. Subsequent offline hardening adds strict
decimal argument limits and collector-v2 selection; these did not run in 015
and are not retroactively covered by its native result. Current comparison code
reproduced all 108 signed results locally. Earlier comparator/collector revisions
remain available for historical runs and their original controls.

## Review changes and limits

ORDER BY survives normalization; policy detection uses ScriptDom AST spans, not
the corpus label. Observed differences win over unresolved policy in wrong-twin
verdicts. Procedure names/types and named arguments come from bound parser output;
every case has a fresh reset. Family 26 covers NULL/collation sort order. The
three previously corrected return-contract twins were included in the full rerun.

Expanded numeric/date/binary/UUID and error mappings have offline tests. Decimal
normalization retains more than 28 significant digits without context rounding.
SQL SEQUENCE metadata is captured; unmapped standalone sequences still block
equivalence. Missing twins refuse per pair; AST references replace lexical
three-part-name assumptions.

Coverage revision 1 is unchanged and retains seven native controls. Revision 2
is separately selectable, adds PG schemas and excludes views, and is **not
natively qualified**. It cannot reuse revision 1 control evidence. Case
generation, bounded same-failure shrinking and Tower policy verification are
offline-tested APIs, not completed customer workflow qualification.

Full transitive dependency closure, automatic branch-solving, native validation
of every expanded type/error contract, customer intake and policy/certificate
release remain outside this result. See [current boundaries](README.md).

Preserved failures: an invalid dotnet build switch before correction; attempt
014 stopped before Docker for a missing coverage-evidence path; the first
post-run cleanup audit lacked socket permission after successful replay. The
corrected audit used approved sudo read-only owned-label queries and confirmed
absence. No failed slot was reused or replaced.
