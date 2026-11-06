# M4 z/OS confirmation list - backlog draft

Recorded 30 October 2026. Public synthetic questions only; no native outcome.

| ID | Question | State / reference |
| --- | --- | --- |
| M4-INTCALC-XREF-001 | How does CBACT04C behave with two cards on one account given its unique alternate-key declaration and XREFFILE.jcl NONUNIQUEKEY? | UNFILLED; OPEN KF-006; [existing question in #476](https://github.com/howardweale/lightyear-carddemo-modernization/blob/codex/backlog-intcalc-m2-xref/docs/backlog/m4-zos-confirmation-2026-10-30.md). |
| M4-INTCALC-ABEND-002 | How does CBACT04C CEE3ABD code 999 surface natively, and how does the scheduler see and act on it? | UNFILLED; [twin-convention policy](m2-intcalc-abend-policy-2026-10-30.json). |

## M4-INTCALC-ABEND-002 - native termination and scheduler interpretation

Question: when CBACT04C reaches 9999-ABEND-PROGRAM and calls CEE3ABD with
ABCODE=999 and TIMING=0, is the native outcome U0999, an ordinary return code,
or another termination? What raw completion information does the scheduler
receive, what status does it assign, and which failure, dependency or restart
rules does it apply? These are separate observations, all currently unknown.

The policy's process exit 12 is the **twin convention, pending z/OS confirmation**.
It does not establish a native return code, native abend, scheduler status or
legacy-faithful behavior. A scheduler's normalized status is not a substitute
for the original native job and step completion evidence.

Planned: Howard arranges a separately reviewed native check with authored public
synthetic inputs for the M1 missing-disclosure abend path and a successful
control. Bind exact COBOL/copybook/JCL bytes, compiler/runtime and Language
Environment options, the actual 999/0 call arguments, input hashes and job/step
identity. This list grants no execution, infrastructure or signing authority.

Planned: retain the original JES/job/step completion fields, abend and LE
diagnostics, stdout/stderr and output/control-total hashes. Distinguish user
abend codes from ordinary step return codes, derived job/MAXCC fields and any
wrapper-translated process status. Do not translate U0999 into 12 by assumption.

Planned: retain scheduler product/version, applicable job definition and
completion-code rules, raw event or log received, resulting scheduler status,
and the actual failure/dependency/restart branch selected. Keep native and
scheduler evidence separately identifiable and hash-bound.

Planned: keep raw captures in the customer's or separately reviewed private
infrastructure, with no customer data, estate source, credentials or private
logs in either Git repository. Only disclosure-reviewed public-safe receipt
metadata and hashes may later inform this public list. No arrivals access here.

Native completion type/code: UNFILLED

Native receipt and exact hashes: UNFILLED

Scheduler observation and applicable rules: UNFILLED

Scheduler receipt and exact hashes: UNFILLED

Keep-or-fix disposition: OPEN

## Joint review trigger

Planned: if z/OS shows U0999, revisit the Java mapping and existing twin shim
together under a keep-or-fix decision. Preserve the original observations.
Decide whether and how to represent abend versus return-code semantics, scheduler
behavior and the judge's status/data contract before changing either mapping.
A twin exit-12 match alone cannot close this question.

This draft changes documentation only. CI uses [skip ci]; full CI remains
necessary before any later merge after the 5 November run's verification.
