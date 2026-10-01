# Equipment 06, Stage A′2: stopped, qualification failed

A2 stopped at control 13, the first omitted-rollback-wait control. Its declared
result was `contract-violation` with `missing-public-rollback-witness`; the frozen
judge returned `passed`, with no diagnostic. Both native observers still recorded
rollback and lock-wait witnesses despite the omitted wait. The predeclared control
expectation was therefore unmet. The recorded verdict is preserved; A2 has not
qualified and cannot admit B04.

| Planted control | Expected outcomes obtained | Unstarted slots |
|---|---:|---:|
| Reversal-allocation assertion | 3/3 | 0 |
| Invoice null dereference | 3/3 | 0 |
| Shipment API rejection | 3/3 | 0 |
| Test-only support throw, feedback suppressed | 3/3 | 0 |
| Omitted rollback observation wait | 0/1 | 2 |
| Nonnumeric order identifier | Not run | 3 |

The first nine controls exported the declared runtime diagnostic in both engines,
with the exact expected origin, stage, exception class and candidate frame. All
three support controls suppressed feedback and recorded `halted-equipment-suspect`.
Native classes were 12 execution failures and one pass. The latter is a failed
qualification control, not an autonomous success. No business-failure,
contract-violation, judge-error or insufficient-evidence class was recorded.
Five slots remain unstarted; none was replaced or resumed. The controller exited
normally after the declared stopping condition, with no controller error.

All 13 signed archives independently replayed with the unchanged frozen
`tools.ms94_diagnostic_publication_v6`, reproducing the complete gates, diagnostic
bytes, suspect flags and dispositions. All 65 native, cleanup,
projection, publication and verification signatures checked. Actual Docker
inventory before and after replay confirmed all 117 owned resources
absent (91 containers,
13 networks and
13 volumes), plus all six offline preparation compilation
containers absent. Successful replay preserves the failed qualification; it does
not turn it into a pass.

| Cost | Value |
|---|---:|
| Campaign elapsed seconds, including controller publication/replay | 4,829.547 |
| Sum of native-pair elapsed seconds, included in campaign elapsed | 4,290.639 |
| Independent terminal replay and cleanup verification seconds | 242.531 |
| Native pairs / lane executions | 13 / 26 |
| Model calls / model tokens | 0 / 0 |
| Separate preparation compilation seconds | 270.313 |
| Separate offline preparation compilations | 6 |

Independent replay added no native executions or model calls. The six preparation
compilations, 28 focused tests and nine documentation tests are preparation evidence,
not native qualification. This campaign and its cost remain separate from A1 and
all B01/B02/B03 measurements. The B03 result remains 12/20, Wilson 38.7%–78.1%.
A1's 10/10 retained-reference false-rejection upper bound remains 25.9% (one-sided
95%); it does not establish that the diagnostic qualification passed.

The follow-up is paused under the declared failure rule. A3 has not been run and
B04 has not been admitted or started. The frozen judge, sources, plan, outcomes
and all inherited accepted files remain unchanged. No repair, new qualification,
restart or replacement is authorized by this result. Any future equipment revision
requires the appropriate fresh qualification; this run cannot be reinterpreted.

[Signed terminal report](report.json), [independent verification](terminal-verification.json),
and per-publication receipt and verification JSON are published. Full captures,
native archives and secrets remain local. Operator review of B03 is not independent
human attestation of these new planted sources. No broader or production claim follows.

## Original prospective declaration

This qualification has 18 fresh Oracle/PostgreSQL pairs: six planted faults,
each repeated three times. It makes zero model calls and gives no autonomous
success credit. Execution is sequential, with an eight-hour cap and a stop on
the first unexpected outcome. There are no restart or replacement slots.

| Planted control | Required result in both engines |
|---|---|
| Nonempty reversal-allocation fact assertion | Candidate / reversal allocation / `AssertionError`, exact candidate frame |
| Null dereference on an unloaded invoice | Candidate / invoice / `NullPointerException`, exact candidate frame |
| Shipment constructor rejects an incompatible document type | Application / shipment / `AdempiereException`, exact candidate frame |
| Test-only JourneySupport throw | Execution failure, no diagnostic, `halted-equipment-suspect` |
| Omitted post-rollback observation wait | Contract violation, missing public rollback witness |
| Nonnumeric public `order.id` | Contract violation, invalid public identifier |

The candidate sources are constructed from the retained reference. Only the
support-fault test changes its private assembled copy of support; the accepted
public support file and every inherited A1 source remain byte-identical. Source
construction manifests declare the expected result before execution. Compilation
and unit checks are preparation evidence, not native qualification or independent
human source attestation.

The unchanged A1 judge determines the native class. The pinned runtime exporter
adds only closed exception provenance, candidate-frame and public-stage fields;
exception messages and private values are excluded. Support or outside-candidate
throws suppress feedback and receive an equipment-suspect disposition. They do
not automatically void a cohort. Missing or corrupt equipment evidence retains
its equipment-failure path.

Each native archive is signed and replayed with the frozen A2 publication tool,
which checks the complete gate, diagnostic bytes, suspect flag and disposition.
After termination, a separate replay and actual owned Docker inventory check are
required. Only safe signed metadata is published; native archives stay local.

The plan binds the successful A1 report and its independent terminal verification,
as well as Howard Weale's accepted B03 operator adjudication. A2 alone does not
admit B04: A3 must still establish byte-identical diagnostics on native runs
against a second checkpoint with perturbed private values and identifiers. No
B04 model call is permitted until all prerequisites and the new public freeze
are complete. B03's 12/20 result and all earlier costs remain separate.

This is a prospective declaration, not an A2 pass claim. The exact plan,
declaration and snapshot manifest are published before the one-shot launch.
