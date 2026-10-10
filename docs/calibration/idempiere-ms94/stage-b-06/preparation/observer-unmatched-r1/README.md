# B06 unmatched-return diagnostic — full frozen plan

Prepared October 10, 2026 for Howard's review. **Not armed or authorized to run.**

## Window and approvals

One fresh J1 retained-reference Oracle/PostgreSQL diagnostic pair on **October 10,
10:30 AM–1:30 PM PDT** (17:30–20:30 UTC). Latest full-budget start is
**11:20:10 AM PDT** (18:20:10 UTC). Pair budget: 7,190 seconds, including native
execution, finalization, archive replay and cleanup. Additional cleanup reserve:
600 seconds. Candidate timeout: 1,800 seconds. No extension, retries or replacement.

Howard explicitly shortened the four-hour full-plan review lead for this window
only. Fresh exact Tower authorization and separate explicit Docker approval are
still required. The prior diagnostic's approvals and owner are consumed.
No approval receipt has been created for this new run.

## Accepted exception and remaining stop conditions

Policy `diagnostic-unmatched-return-v1` accepts only a selected generation return
with an empty pending activation stack, no active return arm, and a matching live
top-frame location. It records the structural context as unobserved and continues
collection. It creates no synthetic entry, generation, class identity or provenance.
The broker checks each exception against the preceding JDI audit event and seals
its sequence in the collector receipt and census.

An unmatched return makes observation globally **indeterminate**. Duplicate arms,
method/depth/location mismatches, missing other evidence, audit or evidence caps,
clock/window violations, and cleanup failures still stop immediately. Original
caps remain 500,000 audit records/128 MiB and 50,000 non-audit evidence records.
No general degradation mode, model transport or automatic retry is permitted.

This is collection only: **zero qualification and measurement credit**, even if
no unmatched return occurs. A completely collected pair terminates `diagnostic-only`
and cannot issue a business gate. The archive audit authenticates signatures,
hashes, structural events, contexts, execution bindings and clocks; it does not
claim complete provenance or gate replay. The legacy equipment-suspicion flag
remains conservative. The retained-reference `passed` expectation in slot metadata
identifies the unchanged input baseline, not a diagnostic qualification verdict.

## Exact bindings

| Binding | Value |
|---|---|
| Source commit | `3784ba75797e802dada6dddd250183eb392658da` |
| Executable plan content | `2d81a2505cf9993f8311a154662354141d7388d5cd275013faab586e8f3f8004` |
| Frozen snapshot | `ffdf878cdb6e11ddeaefd86701bb162dea931e4616f9d37cf5d552cfef23d780` |
| Frozen verification | `e70a63fa53fd07246207d7bc7f179fb38da80680dd646aaf5ce1271e561be9d1` |
| Frozen files verified | 113,606 |
| Public source comparisons | 783 |
| Focused frozen tests | 69, passed |
| New owner | `journey-212875091b535f02baa637bbe6a5309e` |
| Observer Java SHA-256 | `6945d3ad0a98429010a54f685061d836dfccee26eec6903a1e790012c4adeeae` |

The source count includes Python source, observer Java and host-probe Java. Five
fresh compiled observer classes are bound in the native plan. Full native input
and 110,544-class manifest validation completed before the immutable freeze.

Pinned built application image:
`sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`. Direct Java, no Maven.
Carrier image: `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
Oracle image: `sha256:96c4bda58cd8a8dfda586b2d83a2eb2a3e9f28fda0f1915d3fd758c890dc02b7`.
PostgreSQL image: `sha256:6820c00e2aa9770bea672bc036646175d2bb5f5ce7343dc51e1dba5eb1d3da7f`.
Real clocks and the October 1 scenario/period guard remain mandatory.

## Launch, evidence and limits

The prepared one-shot launcher must check exact public bytes, source, all frozen
hashes, window/full budget, fresh owner, review exception and Docker approval;
then freshly authenticate the exact Tower decision before Docker inventory or
signing. No active Docker overlap is permitted. Only the controller may mutate
its exact owned resources. Monitoring is read-only. No machine configuration
changes or competing heavy work during the native window.

After termination: verify signed report/audit, all frozen hashes and actual owned
cleanup, retaining captures and archives locally. Any new failure remains failed;
no automatic further window. Business predicates, B05 and historical evidence are
unchanged. The original missing-entry delivery cause remains unproven. Host tests
demonstrate the narrow exception, not native success. This amendment cannot qualify
unobserved provenance; qualification still requires a separately proven repair.

Full machine-readable records: [review plan](review-plan.json),
[executable plan](executable-plan.json), [snapshot](snapshot-summary.json),
[verification](frozen-verification.json). These publish metadata and hashes only;
private values, references, blobs, captures and archives remain local.

Operator review, not independent attestation.
