MS94 B05 executable freeze r2: preflight passed; measurement launch awaits approval

B04 remains VOID. Operator review; not independent. The pre-outcome [r2 amendment](../amendment-r2/README.md) changes review control flow only. The approved plan `56b13b23a319af3d207552f5022fd3bbaeb9744dba2f79cf535acb2b5fd49951` and declaration `07bf81eb26edb82f9e74be3535af23e7ec51ae965f1581047bf82b87a6404cd2` remain byte-identical, as does the October 1 builder prompt. No B05 measurement slot or model call has started.

| Artifact | Content SHA-256 |
| --- | --- |
| Amendment | `04a8b0d6405e1cd964f023e56da32afed3e518a82ee55dfb56c5baf2a52e6561` |
| Executable snapshot (1085 files) | `8cb754f83165b64ffb8e36a311fe633724e9b889b4e047299f66a9e6ce9a9ada` |
| Executable declaration | `c37568d6c398aa86c2e343e113bbd73dd81ddbb081785a6a9b10b999a4a025bb` |
| Zero-model preflight authorization | `cb2b07bc8e017673c16e9ce3bdc9f5ec9856dce928dd8b676e3d88992a558497` |
| Preflight report | `5f3f56eb73154b49d70cb030cad1c6ec57c692613342431184c451993a14ee43` |
| Supervisor receipt | `b3b211eed9c5659f48c7dc714d142e4e613926a163d16435f7d61d61c3642d4f` |
| Terminal readback | `5d5d5e9cb019b6af006f61b670b59ad99586722b12136246dfd6fcc326d970c1` |
| Qualified snapshot | `47baa4aeef7c778ac3f3ac65a01d91085a391d1ab364174ced2ff668a5dd3214` |
| Qualification terminal audit | `e9cbd4f6bf6c2afa854ce10facf80fccc3962a0236461ad4e26d7503e16217e5` |

Repeated causes and equipment-suspect outcomes pause after the current trial's finalization, cleanup and replay, before the next fresh slot. Each fingerprint contributes once per trial; attempts in the same trial never match each other. Matching origin or business checks is not proof of a common equipment cause: repeated candidate mistakes can trigger review but never automatically change a verdict or terminate the campaign.

The live controller waits for a signed operator decision bound to the exact pause, snapshot, amendment, campaign and trial receipt. `continue` with a reason advances the next fresh slot, changes no verdict, and is not replacement, restart or resumption. `stop` ends the campaign incomplete; `void` ends it as void. Decisions remain operator review, not independent. Pending reviews block new slots; signed decisions and their bindings are independently checked. The operator wait consumes the existing 26-hour campaign budget. Calendar or hard-stop failures cannot be overridden by continue.

Controller, provenance, evidence, cleanup and deadline failures remain hard stops. As in r1, a host supervisor enforces **7,190 seconds** total per trial, including admission, model/native work, cleanup, audit, signing, archive, independent replay and worker exit. **600 seconds** are reserved for finalization. Late results are never accepted. Timeout stops and voids; actual emergency process/resource recovery time is retained separately and charged to the campaign. An OS or Docker failure cannot promise bounded recovery. No stopped trial is restarted or replaced.

The corrected freeze uses the qualified calendar, entry checker, judge, observer, exporter, direct route, application executor and image digests unchanged. All **980** qualified input files match their qualification hashes; all **1085** executable hashes match. Application and database clocks remain real, with the qualified period guard. October 1 documents predate later real-time orders. Latest safe launch remains **2026-10-29 12:59:59 PDT / 19:59:59 UTC**; the full 26-hour duration ends October 30 21:59:59 UTC, before November 1.

The fresh zero-model preflight used two fixed native pairs. The planted invoice NullPointerException produced the closed candidate-origin diagnostic in both engines and was delivered directly to the deterministic builder-interface receiver without an analyst. The receiver returned the unchanged qualified retained reference, which passed the complete business judge in both engines with empty diagnostics and no suspicion. This checks delivery plumbing, not AI repair. Controls never count as measurement successes.

Both private archives independently replayed full entry, complete gate, diagnostic, calendar, provenance and delivery evidence. All **18** owned Docker resources were absent after native execution, replay and terminal readback. The supervisor exited normally. There is no measurement authorization or model invocation. The previous original/r1 executable freezes are unchanged.

Validation: **102 tests passed in development and 102 from this immutable snapshot**; **63 B05 tests and 9 documentation checks passed** in the isolated publication worktree. Tests cover same-trial deduplication, cross-trial review, signed continue advancing the next fresh slot, stop/void, equipment-suspect pause, decision tampering and missing bindings, unchanged verdicts, hard deadline and calendar enforcement, direct forwarding and support/outside-origin empty-feedback halts. Controlled sleeping-child tests exercise actual process termination and recovery recording.

The first r2 preflight preparation failure is [preserved separately](../executable-r2-failed-preflight/README.md), including its failed report and unchanged 1085-file snapshot. It retained an r1 native-plan path and failed before any native pair or resource allocation. Correction added a current-configuration path guard and regression test, then created a **separate** immutable root (`stage-b-05-r2-fixed`). The failed snapshot was not amended or restarted. Its body cost was 1.766 seconds; supervised total 4.688 seconds; zero native pairs/models. That failure is not replaced by this successful preflight.

Successful preflight costs: native pairs **798.297 seconds**; archive creation plus independent replay **334.110 seconds**; preflight body **1211.922 seconds**; total supervised preflight **1215.906 seconds**. Preparation total monotonic time is unavailable. Zero model/analyst calls or model-tool compilation calls; native JVM builds are included in native time. All preparation/preflight costs remain separate from measurement budgets.

Measurement design is unchanged: **3 excluded pilots + 20 cohort; 115 calls, 69 compilations, 26 hours; 5 calls and 3 compilations per trial, strictly under 2 hours with finalization included**. The primary metric remains final cohort pass rate with Wilson 95% interval, only for a complete nonvoid cohort. No B03 pooling; comparison is descriptive only. B03 failure categories remain operator review, not independent. No verdict or primary metric changes, and no automatic MS95.

Publication includes only named integration code/tests, safe plans/declarations, amendment, signed authorizations/receipts, verification and readable results. Archives, captures, checkpoints, keys, private qualification-plan contents and reference sources stay local. Publication was authorized; model launch is not. After public commit byte verification, work stops for an explicit launch approval binding this snapshot, declaration, preflight and amendment. No additional preflight is required merely because these exact bytes are published.
