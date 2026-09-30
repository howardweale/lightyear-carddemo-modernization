# Equipment 06, A2 revision 1: prospective diagnostic qualification

Howard authorized the four next steps on September 30, 2026: revise the failed
control, freeze and publish a fresh qualification, perform native A3 invariance,
and launch B04 only after all gates pass. This is a new 18-pair campaign, not a
restart of A2 or a replacement for its five unstarted slots. No outcome of this
campaign is yet claimed.

The original A2 failed at control 13: removing the post-rollback wait still left
native rollback witnesses in both engines. That failed qualification, its
12 expected outcomes, five unstarted slots, signed archives, independent replay
and costs remain unchanged in [stage-a2](../stage-a2/README.md).

## Revised control and scope

`missing-rollback-stimulus-and-wait` omits the draft `C_BPartner` database write
as well as the post-rollback wait. It allocates a genuine unused identifier using
the application's native sequence API, records that allocated identifier, opens
a read-only transaction, and raises the same injected failure. The unchanged
support helper rolls back that read-only transaction. The retry, repeated-request
and row-lock interleaving code remain intact. The private observer runs normally
throughout; no observer record is removed or rewritten.

This tests the absence of a target-table rollback witness. It is deliberately
stronger than skipping a wait alone and does not qualify the original wait-only
fault. The accepted next-step authorization changes this control's scope; the
original supplied specification's wait-only result must not be reported as met.
Both engines must yield `contract-violation`, exactly the
`missing-public-rollback-witness` finding, and intact lock-wait witnesses. A
pass, business failure, execution failure, evidence failure, or missing lock
witness does not satisfy this control.

The other five planted Java sources are byte-identical to their A2 versions.
The native executor and publication verifier use new module names solely to bind
the revised controls and assessment. The controller additionally binds the
preserved failed A2 report and verification. The judge, observer, runtime
exporter, public support, public contract and all inherited A1/A2 source files
remain byte-identical. A1's successful qualification remains applicable to those
unchanged components. All six diagnostic controls are freshly qualified here.

## Fixed schedule and stopping rule

| Order | Control | Fresh Oracle/PostgreSQL pairs | Required result |
|---|---|---:|---|
| 1–3 | No draft database write and no post-rollback wait | 3 | Missing rollback witness contract violation, both engines; lock witness retained |
| 4–6 | Reversal-allocation assertion | 3 | Candidate / reversal allocation / AssertionError / exact candidate frame |
| 7–9 | Unloaded invoice null dereference | 3 | Candidate / invoice / NullPointerException / exact candidate frame |
| 10–12 | Rejected shipment API call | 3 | Application / shipment / AdempiereException / exact candidate frame |
| 13–15 | Test-only support throw | 3 | Execution failure, empty feedback, equipment-suspect |
| 16–18 | Nonnumeric public order identifier | 3 | Invalid public identifier contract violation in both engines |

The revised control runs first to expose any remaining qualification defect
before the unchanged controls. The campaign has an eight-hour cap, zero model
calls, no restarts or replacement slots, and stops at its first unexpected result.
It provides no autonomous cohort-success credit. Preparation compilation and
unit tests are reported separately and do not establish native qualification.

The exact plan, signed declaration, source and snapshot manifest must be publicly
pushed and verified before authorization and execution. Existing signing
authority is used in place; no private key is copied or mounted. Every available
native archive must replay with the frozen revision verifier, followed by a
separate terminal replay and actual owned Docker cleanup verification. Only safe
signed metadata is published; captures and archives remain local.

A3 must then demonstrate identical exported diagnostic bytes on native runs
against both the admitted checkpoint and a genuine private checkpoint with
perturbed monetary values, quantities and identifiers. No synthetic log editing
can satisfy that requirement. A2 revision success alone cannot admit B04. B04
still requires its own publicly pushed freeze, unchanged initial builder inputs,
three excluded pilots and 20 fresh cohort trials under the original caps.

B03 remains 12/20 first-try, Wilson 38.7%–78.1%, nonvoid. All earlier measurement
and qualification outcomes and costs stay separate. Operator review is not
independent human source attestation.
