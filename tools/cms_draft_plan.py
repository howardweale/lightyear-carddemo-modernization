"""Render a metadata-only CMS draft decision plan; never runs CMS workloads."""
import json
from pathlib import Path

RECORD='docs/plans/cms-draft-path-2026-10-18.json'

def render(value):
    lines=['# CMS draft path: decision proposal', '', 'Snapshot as of '+value['checked_at']+'. '+value['decision_status']+'.', '',
           '| PR | State | Draft | Head | Base |', '|---|---|---|---|---|']
    for row in value['pull_requests']:
        lines.append(f"| [#{row['number']}]({row['url']}) | {row['state']} | {row['draft']} | `{row['head']}` | `{row['base']}` |")
    lines+=['', 'Payment equivalence: **'+value['payment_equivalence']+'**. Java workload execution in the inspected workflow: **'+str(value['ci_java_execution'])+'**.', '',
        '## Why the drafts remain', '',
        'PR360 is an F0 feasibility investigation. PR370 adds feasibility guards and targets its branch. Green checks establish those bounded checks, not same-revision cross-language payment equivalence. The retained observation explicitly leaves the COBOL/Java revision mismatch and F1-F4 work unresolved.', '',
        '## Proposed review and merge path', '',
        'Recommend one consolidated CMS integration review after A1 is complete and the separate dependency repair is green. Preserve individual commit provenance and the upload guards, but present the combined diff, exact sources and remaining gates once. Do not merge two independent copies of the stack. Keep the small A1 and dependency reviews separate until Howard chooses this integration plan.', '',
        'Before approval: verify the four approved artifact deletions; pass the metadata-only upload guard with one-day retention; correct the diagnostic-audit count without exposing text; complete same-revision feasibility evidence or explicitly limit the review to F0 preparation. Retarget/integrate against actual current main only after the integration decision, then require all applicable checks on the final combined SHA and Howard approval of that SHA.', '',
        '## Java CI proposal', '',
        'The inspected workflow calls `tools.cms.f0_probe --compile` and `tools.cms.f0_smoke`; it does not invoke the available `--java` probe option. Merely having Java files or Python fixture checks is not Java workload evidence. Propose a separate, bounded CI job that pins the reviewed Java toolchain and exact same CMS revision, uses public or synthetic permitted inputs, records compilation/execution and input/output hashes separately, and fails on an absent Java run. The metadata sanitizer must run before upload and refuse raw source, logs, rate values and payment output. Do not add that execution until Howard approves the scope and counsel resolves publication constraints.', '',
        '## Publication decision', '',
        str(value['field_identifiers_under_review'])+' field identifiers are within the publication decision described by the review. Do not reproduce them here. Recommend withholding any further CMS-derived identifiers, text or generated source until counsel confirms the permitted use and Howard approves the exact publication scope. Already-public material does not by itself authorize new publication. A1 metadata fixes and the expressly approved artifact deletion are separate.', '',
        '## Decisions needed', '',
        'Howard: approve or change the single-integration proposal and the bounded Java CI scope. Counsel and Howard: decide whether the field identifiers and any additional CMS-derived material may be published. Once those decisions and the stated evidence gates are satisfied, present the exact final green SHA for merge approval.', '',
        'This plan changes no CMS source, workflow, draft state or merge state. It signs, imports, activates and executes nothing; Phase 2 remains prohibited. '+value['source']+'.', '']
    return '\n'.join(lines)
