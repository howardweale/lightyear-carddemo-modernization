# Diligence: claims, evidence and unfinished work

Review draft — 7 November 2026. This index separates bounded retained results from design and unmeasured work. Native/P5 production qualification remains open.

## Retained public evidence

| Claim | Inspectable evidence | Boundary |
|---|---|---|
| 260 / 260 Oracle â†’ AlloyDB pairs matched | [Paired-campaign manifest](https://github.com/howardweale/lightyear-carddemo-modernization/blob/6c496ce3b232443a8ba62be4baaed56e655108e7/docs/receipts/oracle26ai-alloydb-types260-20260917/manifest.json#sha256=f94b7ae6f09edfdbe9b9bba231e660bc42a6a7d3102ca895a1de16155eaaad10) | Bounded native probes; not exhaustive datatype conformance, Oracle 19c coverage or platform qualification. |
| 43 / 43 deliberately wrong T-SQL conversions caught | [Public review result](https://github.com/howardweale/lightyear-carddemo-modernization/blob/6c496ce3b232443a8ba62be4baaed56e655108e7/data-modernization/tsql-procedures/review-results.json#sha256=a9b713cb78714466a79db76aed81e55b46799e141cf201234cb51fc87b601275) | Authored public procedures and 26 trap families; not a customer workload or independent attestation. |
| CloudBank: two database targets, GKE, cutover and rollback | [Two-target equivalence](https://github.com/howardweale/lightyear-carddemo-modernization/blob/6c496ce3b232443a8ba62be4baaed56e655108e7/docs/receipts/ms71-20260912a/ms71-alloydb-second-target.receipt.json#sha256=e49486a7746ec97ff077342eda5601344ae3aefc4cb83ef86f70ec337108e87a); [Cloud SQL / GKE platform](https://github.com/howardweale/lightyear-carddemo-modernization/blob/6c496ce3b232443a8ba62be4baaed56e655108e7/docs/receipts/ms67-final-635689566db6425aadf6fb1fc6cf3de7/receipts/ms67-platform-receipt.json#sha256=c0e5684375cb1e73f6669c54533164f939542d2e886f856cedc5fd0b3318a210); [AlloyDB platform](https://github.com/howardweale/lightyear-carddemo-modernization/blob/6c496ce3b232443a8ba62be4baaed56e655108e7/docs/receipts/alloydb-platform-20260912a/alloydb-platform.receipt.json#sha256=f8eb4d39719c24b992ceff164da5b76304e7c51d308873d59537d82f5af9865a) | Synthetic data and bounded non-production qualification. Production readiness, customer certification and complete migration remain false. |
| ERP factory journey: 12m25s | [Signed campaign result](https://github.com/howardweale/lightyear-carddemo-modernization/blob/6c496ce3b232443a8ba62be4baaed56e655108e7/docs/calibration/idempiere-declared-factory/campaign.json#sha256=2ea8300ddd9d6bed4cc3525d0ace7375a4b136bc1997f6eb6b353361c03f6b81) | One declared journey under a frozen comparison register; not whole-ERP qualification. Transient interleavings include application-trace evidence. |

The CloudBank MS67 legacy HMAC evidence has a human observer-attestation boundary; it is not public HMAC verification. No retained result above is first-run COPAU native/P5 qualification.

## Material carried forward before closing #472

The former P9 draft remains pinned at [#472](https://github.com/howardweale/lightyear-carddemo-modernization/pull/472), head de24bf682df2c245b24279f1ae2ab88c15468889. Its useful review content is retained here as a separate historical-evidence queue, not silently promoted to current proof.
- [Historical claim-by-claim wording and limitations](https://github.com/howardweale/lightyear-carddemo-modernization/blob/de24bf682df2c245b24279f1ae2ab88c15468889/docs/diligence/p9-2026-10-30/README.md#sha256=c59aa3735ebb8349dd028153a45835f4883d7462fb4ecf62684b8f5ed39f23ad)
- [Original source and digest index](https://github.com/howardweale/lightyear-carddemo-modernization/blob/de24bf682df2c245b24279f1ae2ab88c15468889/docs/diligence/p9-2026-10-30/source-index.md#sha256=e6246cd221fbb0da3cf685becaf0418d033823926363d7270fa68970353adef8)
- [Independent evidence review checklist](https://github.com/howardweale/lightyear-carddemo-modernization/blob/de24bf682df2c245b24279f1ae2ab88c15468889/docs/diligence/p9-2026-10-30/review-checklist.md#sha256=23dd6ddffcd5db1a49634fccebf7437e02bf04991444e7677806da92f51a9709)
- [Bounded measurement denominator index](https://github.com/howardweale/lightyear-carddemo-modernization/blob/de24bf682df2c245b24279f1ae2ab88c15468889/docs/diligence/p9-2026-10-30/receipts/evidence-index.json#sha256=9ca9192213779d17f2d03c5e74f0cbc95afd3e757f881f5d398405cae2add14d)

Carry-forward review items: POSTTRAN29/29 provisional comparison with promotion defect still open; INTCALC311/424 mutation/not-releasable; screen proof701/768 mutation and678/678 interactions; corrected8/227 equivalence resolution; historical4,238-test two-platform suite with skips; separate structural estate-discovery scopes; historical human approval path. These are historical denominators from the linked P9 index, not fresh runs, first-run authorization scores or present whole-repository test totals.

Retain the P9 rule: inspect original retrievable bytes, hashes, exact input/source identity, negative controls, excluded scope and reviewer independence for every claim. Wrapper receipts do not replace originals. No private presentation or commercial material is carried into this document.

## Material carried forward before closing #466

Backlog item DIL-MLOGICA-TSQL-INTAKE: starting point for the mLogica T-SQL intake, using the ten public SQL Server/PostgreSQL pairs, pinned at [#466](https://github.com/howardweale/lightyear-carddemo-modernization/pull/466), head d2cb28bbba6bd1480370c91de03f2bfd8baa7172. No new execution or delivery claim.
- [Harness, intake and execution contract](https://github.com/howardweale/lightyear-carddemo-modernization/blob/d2cb28bbba6bd1480370c91de03f2bfd8baa7172/docs/tsql-readiness/README.md#sha256=5215c9012b0b8c39a49d90ff73b852d584ddcccdcf37fc8b1a2a8d93d2a1280c)
- [Exact public ten-pair selection](https://github.com/howardweale/lightyear-carddemo-modernization/blob/d2cb28bbba6bd1480370c91de03f2bfd8baa7172/docs/tsql-readiness/selection.json#sha256=93aa92f10fcd4c7129b484f1f2310375430bae272c39f21f40f3f750f816c205)
- [Artifact integrity and retention requirements](https://github.com/howardweale/lightyear-carddemo-modernization/blob/d2cb28bbba6bd1480370c91de03f2bfd8baa7172/docs/tsql-readiness/artifact-integrity.md#sha256=6e69fc5c39f35798ff5749b8a8ca98f760b1f158ac835739a90373705afdca95)

Preserved scope: LEN, integer division, ISNULL length, DATEDIFF day/year, negative ROUND precision, MONEY scale, BIT, UUID case and trailing VARCHAR spaces; both correct and deliberately wrong twins. Preserve typed parameters/calling conventions, session/reset settings, exact asset hashes, ordered cases/repeats, full state/errors/OUT/RETURN comparison, insufficient-evidence handling and owned-database cleanup.

Still missing: separately reviewed CI provisioning/connection custody, qualified controls, native captures, independent retained-byte replay and measured effort. No credentials, provisioning, native execution or cleanup action follows from this backlog entry. Reconcile the historical blackout/date rule with the current run schedule before future adoption. Do not extrapolate ten authored public pairs into private-estate readiness.

The retained branch `codex/public-tsql-ten-readiness-oct26` is the starting implementation reference. Its proposed `verify.yml` integration waits for the post-freeze window. No private mLogica input, source, fixture or result is read or copied here.

Next review: after native/P5 no longer needs the hours, select a scoped implementation/rebase proposal and a separately costed native packet. Preserve the old branch and all diagnostics.

## Current limits and review queue

- First qualified-run scope: one existing authorization-pages-and-fraud scenario, subject to private-input/judge contract review and exact freeze. Seven records are not seven cases. B/C unavailable; cutoff10 unchanged. No run is admitted by this documentation.
- Second-run catalogue: L01,L02,L04,L06,L11,L12,L15,D07; N8/Bfrom5. No13Novemberdeadline or competing adapter capacity reservation. Freeze before any results.
- Native/P5: component implementations and disposable signature interoperability do not establish production-controller/Tower/original-deadline/all-process-cleanup proof.
- [Secret-scan review](SECRET-SCAN-REPORT.json):2101commits/1501refs/4141findings, no real credential confirmed; scanner limitations remain explicit.
- [Close-only draft inventory](BRANCHES.md): keep branches/evidence; no deletion plan.
- Dependency lock and protected workflows remain a separate postfreeze draft. Missing installed versions are unknown; resolution drift requires a human choice. No silent upgrade.

## Evidence review path

Read the linked source receipt and its limitations, retrieve the exact retained bytes, verify digests, then use the receipt-specific verifier under its execution/custody rules. Local project tests/apps/compilers are not part of this review. Source-only inspection is not runtime evidence. Exact-head merges, private operations and spend remain separate decisions.


## Candid limits, carried forward from P9 and refreshed

| Question | Current bounded statement | What it does not establish |
|---|---|---|
| Native datatype comparison | Retained260/260 Oracle26ai�AlloyDB pairs across13families/65behaviours, linked above. | Other engine versions, exhaustive conformance or production readiness. |
| T-SQL negatives | Retained43/43 wrong variants caught in108pairs; correct variants41equivalent and2policy decisions. | Customer/general workload correctness or readiness of the #466 intake harness. |
| Platform results | Separate retained Cloud SQL/GKE and AlloyDB platform receipts. | Live current health, production rollout or independent HMAC verification. |
| ERP journey | Retained745.157seconds for one declared journey. | Whole-ERP qualification or guaranteed duration. |
| First authorization run | N1selected subject to private-input/judge contract review; no qualified run result. | A pass, native/P5 closure or a signed/admitted run. |
| Source discovery | Structural source/dependency inventories only. | Executed behavior, equivalence or mutation credit. |
| Historical test totals | P9's4,238-test figure belongs to its original snapshot only. | Current-main suite totals or whole-repository green status. |
| Security | History scan2101commits/1501refs/4141reviewed findings; no real credential confirmed. | Exhaustive detection, external security audit, penetration test or certification. |
| Human approval evidence | Each historical receipt has its own identity and scope. | Independent third-party assurance, current signer designation or blanket authority. |
| Retention | Exact original bytes and matching digests must be retrievable. | Availability from a design note, wrapper, digest or Actions URL alone. |

Claim-to-receipt structure: each measurable statement names its original source
snapshot, numerator/denominator, direct digest-bound receipt and limits. Keep
failures, skips, indeterminate results and missing observations visible.
The figures above are current review references to retained results, not newly
measured results. Never overwrite original receipts to make a current summary.
Public source paths retain upstream naming; public prose uses descriptive estate
and program names. The [privacy decision notes](REPO-PRIVACY-DECISIONS.md) retain
the measured transition-inventory reference without making a visibility change.
