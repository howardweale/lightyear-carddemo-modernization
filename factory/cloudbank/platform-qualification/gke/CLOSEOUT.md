# MS67 closeout continuation

Keep the previously passed MS65/MS66 milestones, the matching MS66 receipt,
the regional load and the accepted 630-second SQL reassessment. The next step
is to find reusable evidence before deciding which platform drills remain.

Run from this reviewed checkout on the operator's Mac:

```bash
python3 tools/ms67_reconcile_closeout.py
```

This reads existing JSON evidence under `~/ms67-evidence` and the existing
nonproduction evidence bucket. It verifies the recorded passing load and the
accepted SQL assessment with their canonical validators. It then inventories
the six remaining groups against the recorded release and deployment identities.

The output `MS67_CLOSEOUT_REPORT` is a local, minimized diagnostic. It contains
evidence locations, hashes and validation classifications, with no copied
payloads or credentials. It is not a qualification receipt or a fresh live
cluster check. An unsupported contract, matching signature, or candidate count
does not make a scenario pass. Historical signed evidence is never rewritten.

The cloud reader is limited to the evidence bucket's list/read operations and
metadata/access for the existing evidence key version 1. It performs no cloud
writes. JSON payloads have a size bound, local repository trees and symbolic
links are excluded, and inventory limits or unreadable evidence are explicit
gaps. If needed, increase `--max-cloud-candidates` up to 2000 and repeat the
reader; it does not create a new drill.

To also resume the already approved MS65 continuation only when the matching
receipt is absent:

```bash
python3 tools/ms67_reconcile_closeout.py --resume-ms65
```

The inventory is saved first. An incomplete inventory or invalid existing MS65
receipt prevents automatic continuation. A valid matching receipt is reused.
Otherwise `ms67_resume_ms65.py` uses its existing submission journal and
duplicate-build guards. That separate phase runs the bounded CreditScore canary,
SLO check and rollback; it does not repeat load or SQL recovery. Its result is
separate from the earlier read-only inventory report.

## Remaining platform work

| Group | Coverage to establish |
| --- | --- |
| MS65/deployment | Receipt and deployment bundle for the current release |
| Operations | Rotation, all-service metrics, correlated logs/traces, alert fire/recovery |
| Security | Current image signature/provenance/scan chain, manifest/runtime policies and network enforcement |
| Resilience | Controlled worker-node and failure-domain evacuation, all-service recovery, zero normalized data loss |
| Rolling deployment | All eight services, distinct signed candidate images, zero unavailable replicas |
| Cutover/rollback | Canary, full target traffic, 18 business journeys, rollback and recovered state |

The reader does not implement or start the remaining platform drills. The
existing `cloudbank-platform-qualification` launcher admits already collected
observations; it is not an end-to-end drill executor. Follow
[the live runbook](LIVE-RUNBOOK.md#5-backup-ha-rollout-cutover-and-rollback)
for their existing requirements. MS67 closes only when the completed 28-row
observation is admitted and the resulting signed
`cloudbank-platform-qualification.receipt.json` is independently verified.
