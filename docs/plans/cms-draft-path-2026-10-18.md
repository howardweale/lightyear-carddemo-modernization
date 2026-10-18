# CMS draft path: decision proposal

Snapshot as of 2026-10-18T17:25:34.612149+00:00. proposal-only; Howard and counsel decisions outstanding.

| PR | State | Draft | Head | Base |
|---|---|---|---|---|
| [#360](https://github.com/howardweale/lightyear-carddemo-modernization/pull/360) | open | True | `70aa78b8743988445791d8633e9a23ea240500eb` | `main` |
| [#370](https://github.com/howardweale/lightyear-carddemo-modernization/pull/370) | open | True | `ea2d060cdf829bcc49570c7a96fd34e779bd2aad` | `codex/cms-pricer-feasibility` |

Payment equivalence: **NO-GO**. Java workload execution in the inspected workflow: **False**.

## Why the drafts remain

PR360 is an F0 feasibility investigation. PR370 adds feasibility guards and targets its branch. Green checks establish those bounded checks, not same-revision cross-language payment equivalence. The retained observation explicitly leaves the COBOL/Java revision mismatch and F1-F4 work unresolved.

## Proposed review and merge path

Recommend one consolidated CMS integration review after A1 is complete and the separate dependency repair is green. Preserve individual commit provenance and the upload guards, but present the combined diff, exact sources and remaining gates once. Do not merge two independent copies of the stack. Keep the small A1 and dependency reviews separate until Howard chooses this integration plan.

Before approval: verify the four approved artifact deletions; pass the metadata-only upload guard with one-day retention; correct the diagnostic-audit count without exposing text; complete same-revision feasibility evidence or explicitly limit the review to F0 preparation. Retarget/integrate against actual current main only after the integration decision, then require all applicable checks on the final combined SHA and Howard approval of that SHA.

## Java CI proposal

The inspected workflow calls `tools.cms.f0_probe --compile` and `tools.cms.f0_smoke`; it does not invoke the available `--java` probe option. Merely having Java files or Python fixture checks is not Java workload evidence. Propose a separate, bounded CI job that pins the reviewed Java toolchain and exact same CMS revision, uses public or synthetic permitted inputs, records compilation/execution and input/output hashes separately, and fails on an absent Java run. The metadata sanitizer must run before upload and refuse raw source, logs, rate values and payment output. Do not add that execution until Howard approves the scope and counsel resolves publication constraints.

## Publication decision

45 field identifiers are within the publication decision described by the review. Do not reproduce them here. Recommend withholding any further CMS-derived identifiers, text or generated source until counsel confirms the permitted use and Howard approves the exact publication scope. Already-public material does not by itself authorize new publication. A1 metadata fixes and the expressly approved artifact deletion are separate.

## Decisions needed

Howard: approve or change the single-integration proposal and the bounded Java CI scope. Counsel and Howard: decide whether the field identifiers and any additional CMS-derived material may be published. Once those decisions and the stated evidence gates are satisfied, present the exact final green SHA for merge approval.

This plan changes no CMS source, workflow, draft state or merge state. It signs, imports, activates and executes nothing; Phase 2 remains prohibited. Public PR metadata and exact PR370 workflow; no CMS source or diagnostic artifacts inspected.
