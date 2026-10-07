# J1 smoke resource-owner correction r9

October 6, 2026 PDT (October 7 UTC). Operator review, not independent attestation.

The r8-authorized smoke stopped after 7.093 seconds. Its retained slot used the
logical ID `j1-smoke-r6-001` as the Docker resource owner, but the existing network
policy accepts only `journey-` followed by 32 hexadecimal characters. The failure
occurred before network creation or candidate execution. Native time was 1.938
seconds; zero candidates and zero models ran. Two slots remained unstarted.

Finalization and the recovery absence check also failed because `resources.json`
did not yet exist. The signed cleanup record said complete; a separate read-only
terminal audit confirmed absence by all three slot labels and name prefixes.
No archive existed to replay. Full-entry, gate and diagnostic replay are false,
not inferred from absence. Nine signed records and all 2,106 frozen files verified.
The failed snapshot, receipts, stop record, terminal report and audit remain local
and unchanged. Nothing in r9 upgrades that failed qualification.

Preserved terminal report:
`6737870b2bccf4fa1f7aeeff052553c494df20107322bcab38a3f9c60e047f75`.
Separate terminal audit:
`fc35d2c370ab0505ddf39092f38ac7376c28842a52fcf8035f59c049d05c3bf0`.

## Correction

Howard requested: “correct the plan and approved”. Each logical slot now maps
to a fresh revision-scoped native journey ID. Assembly, freeze and executable
conversion validate it using the actual inherited network policy. That policy
and J1 predicates are unchanged. This is a new correction group, not a restart
of the failed slot. It still requires the exact new public plan commit and a
fresh signed operator decision from the distinct Tower authority.

The frozen implementation changes only `tools/ms94_b06_executable.py` and
`tools/ms94_b06_qualification_plan.py`. Candidate sources, private input bytes,
images, observers, judges, support, diagnostic policy and real-clock behavior are
inherited unchanged. Physical run paths and their runtime/declaration bindings
change; logical source/expectation bindings do not. No new Java compile, Docker
command, native pair or model call was used to assemble r9.

| Binding | SHA-256 |
| --- | --- |
| Executable plan | `b1ee6503e8648c70e1303f75bc531429e64ef07c0bbe23ef0d90bbd0e3e4574c` |
| Immutable snapshot, 2,106 files | `a9a532df45a0db27602da668394437dc3efd189143eaec32ef336073ab7e6c70` |
| Previous failed snapshot | `cc2f9522d3be2d7a527780f98de42391ede4d3c7438ddce0dee6cd64fa38b77b` |

The three slots remain retained reference, duplicate invoice-line mutant, and
candidate null dereference with direct closed-diagnostic delivery. The window
remains October 7, 03:00–09:00 UTC (October 6, 8 PM through October 7, 2 AM PDT).
Each new slot must have its full 7,190 seconds available; late approval does not
extend the window or permit reduced budgets. Maximum group window is six hours;
actual remaining time depends on approval/launch. Zero model calls are allowed.

## Validation and remaining work

Sixteen focused offline tests passed, including the old-name rejection before
slot creation, revision-scoped identities accepted by the real network policy,
snapshot integrity, Tower decisions and controller stopping behavior. All 141
B06 offline regressions passed in 30.449 seconds. The first full-suite run found
one old conversion fixture whose parent directory was not a native journey ID;
correcting that test fixture required no runtime or frozen-snapshot change.
Public publication bindings follow separately.
No native qualification success is claimed. Full J1/J2/J3 qualification,
measurement admission and measurement preflight remain outstanding.

The absence of a resources file on an early equipment failure remains a
finalization limitation; it is not silently repaired in frozen evidence. Such
failures still stop and require an explicit terminal failure audit. B05,
`work/ms94`, template-r1 and J1 predicates remain unchanged.
