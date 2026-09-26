# MS87 native journey replay

This work order replays the unchanged MS86 Java harnesses on isolated local Oracle and PostgreSQL copies. The builder is idle and the model budget is zero. A successful replay reproduces two known findings; it does not mean the application is defect-free.

## Prerequisites

Run from the repository root with Python 3.11+ and the `control-tower` extra installed. Docker must provide at least 12 GiB memory and 60 GiB free disk. Failure retention can require an additional Oracle filesystem export of roughly 22 GiB per failed pair. No GCP resources are used.

The two engine image IDs in `work-order.json` are local, admitted checkpoint images. They are not public registry tags. Supply the retained MS84 Oracle checkpoint image and the stopped PostgreSQL seed volume, not a clean vendor image or a database already modified by a journey. The runner verifies every starting table row multiset before and after the reviewed repairs and rollback-only probes.

`work/ms87/local-runtime.json` binds the prepared offline runner image, PostgreSQL seed volume and seed container identity. The runner image contains the pinned iDempiere source (`731515dcdd5278b843db33b9d3109d155b881951`), its compiled reactor and Maven dependency cache. `Dockerfile.runner` provisions the native client environment. Building dependencies is a separate preparation step with network access; recorded native runs use `mvn -o`, internal Docker networking and no published ports.

## Review and run (PowerShell)

```powershell
$env:PYTHONPATH = 'src'
python -m lightyear_calibration.journey_order plan
# Read work/ms87/plan.json. Use the exact digest printed by plan.
python -m lightyear_calibration.journey_order approve --plan-sha256 <digest> --actor <name> --reason "Authorized local replay of this declaration"
python -m lightyear_calibration.journey_order start --plan-sha256 <digest>
python -m lightyear_calibration.journey_order status --run factory/idempiere/ms86-journeys/runs/<run-id>
```

On Linux, use `export PYTHONPATH=src` and the same Python commands. Start is detached. A watchdog handles interruption recovery. Each pair uses fresh data and runs sequentially; the separate original `firstOnly()` harness is required to reproduce the locking finding.

The first approved declaration is reusable by its exact file hash. Changed declarations require a new approval. Plans also bind implementation and evidence hashes; start refuses a stale plan.

## Designed human stops

The first successful replay asks about Oracle's lost fractional shipment timestamp. The decision can remain open: run cleanup happens before waiting. An operator may record `retain-open-finding` to acknowledge the unresolved limit for subsequent replay; that does **not** accept data loss or establish boundary equivalence.

```powershell
python -m lightyear_calibration.journey_order decision --run <run-path> --decision-id <request-id> --outcome retain-open-finding --actor <name> --reason "Keep timestamp loss open; replay only"
python -m lightyear_calibration.journey_order resume --run <run-path>
```

Resume runs only the affected cases and binds unchanged case results to the parent's signed receipt. A known finding that disappears routes to `classify-intentional-change`. An unknown difference routes to `propose-normalization`; the replay cannot admit it or rewrite its own expectations. Semantic acceptance or a changed claim requires a new reviewed declaration and supporting evidence.

## Cancel, recovery and retained data

```powershell
python -m lightyear_calibration.journey_order cancel --run <run-path> --actor <name>
python -m lightyear_calibration.journey_order recover --run <run-path>
```

Cancel is signed. Cleanup removes only resources carrying this run's ownership label, destroys ephemeral credentials, records remaining resources and signs a receipt. Failure observations are retained; live failure databases are retained as filesystem data or stopped PostgreSQL volumes. Never use a global Docker prune to clean these runs. A cleanup failure prevents a completed claim.

The local signing key is under `work/ms87/operator`, excluded from source control. Local operator signatures provide integrity and attribution; they are not independent attestation.

## Control Tower

Select **iDempiere Reference Estate (Large)**, retain the estate evidence campaign, and choose a native journey run. **Run** shows verified journal events and recorded cleanup. **Work queue** shows signed requests and recorded answers. The browser reads evidence; use the CLI above to authorize or record decisions. The run index records terminal history for Convergence.

## Declaration corrections

`work-order.supplied.json` preserves the attachment byte for byte. Archived MS86 row-comparison evidence uses `fresh-unique-generated-UUID`, not the supplied `validated-generated-uuid`, and also uses `exact-native-decimal-value`. The executable declaration corrects those two row-rule names. Existing trace comparators retain their own separately named, unchanged UUID and numeric rules. No expected outcome, harness byte, timestamp finding or claim boundary was changed.

## MS88

`../partial-invoicing/work-order.json` is the bounded extension scope authorized by the user. Its builder proposes a new harness through a constrained patch broker. Generation provenance alone does not establish native execution or equivalence; those require independent readback and whole-state comparison.

The prepared builder prompt contains the extension declaration and MS86 Java API reference. It contains no database contents or credentials. Sending that source to the authenticated Codex service requires the operator's approval of that transfer. Native execution still stays local. The controller requires two accepted MS87 replays of the current plan before admitting MS88 execution.

After that transfer is approved, one command runs generation, patch validation and paired native verification:

```powershell
python -m lightyear_calibration.partial_invoicing factory-run --build work/ms88/<new-build-directory> --executable <path-to-compatible-codex.exe> --prompt <reviewed-prompt.json>
```

Use a current compatible Codex CLI. The original installed 0.101.0 client could not use the configured account model; the recorded compatible client was 0.155.0-alpha.9.2. The reviewed prompt must contain the exact active declaration. Existing build directories cannot be reused.

The builder has one file, at most 420 changed lines, five total invocations (including failed client attempts), and 900 seconds per invocation. The third invocation was explicitly approved after a generated harness compared a Java Boolean to the SQL string `Y`; the repair guidance requires the typed Boolean API and declared trace fields. The third candidate then introduced a posting API compile error. A fourth invocation was explicitly approved for one exact API-call replacement; a source hash guard rejects every other change before execution. The fourth candidate completed both native journeys, but the independent footprint gate rejected accounting-history writes caused by redundant reposting. A fifth exact repair was approved to skip reposting documents already posted by the application workflow. All three earlier native receipts remain failed, with their observed evidence retained. The builder receives no gate output or permission to change expected business values. Its proposal is applied by the existing `PatchBroker`; the builder cannot edit the verifier. The native gate separately reads invoice lines, tax, payments, allocations, inventory and accounting entries. A trace saying "passed" is insufficient. An unexplained difference remains a decision, even when both Java test processes exit successfully.

## Review a completed replay without databases

The publication command includes only selected evidence, excluding private signing keys, credentials, journal locks and retained database filesystem exports. Identical row blobs are stored once.

```powershell
python tools/publish_native_journeys.py publish --run <first-run-path> --run <second-run-path> --output <new-publication-directory>
python tools/publish_native_journeys.py verify --output <publication-directory>
```

Verification checks the archive against its reviewed receipt, every file hash, authorization, journal sequence, signatures and terminal receipt, then recomputes all six gates. The receipt/public-key pair is the review trust anchor. Replacing both with a different locally generated pair is not independent proof of the original operator's identity.

## Reading the result correctly

A successful first replay can show `halted-for-decision` together with `known_findings_reproduced: true`, `unattended_run: true` and `error: null`. This means execution and deterministic checks completed and cleanup finished; the remaining stop is the declared human decision about shipment timestamp precision. It does not mean that timestamp loss was accepted. After an explicit `retain-open-finding` decision, later identical replays can report `reproduced-with-known-findings`.

For example, an operator can confirm that both databases produced the declared operational totals while leaving the timestamp contract unresolved. A replay that unexpectedly preserves the Oracle fraction must stop for investigation too: an upstream fix and a broken probe need different explanations. A run that writes an unexpected business-table value cannot create a new normalization rule for itself.

The iDempiere Discovery graph remains a static dependency reference. Selecting a native journal does not turn every graph edge into measured runtime evidence. The Run panel is the source for this execution's observations and limits.
