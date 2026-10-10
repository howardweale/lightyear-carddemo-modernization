# B06 engineering approval milestone — October 10, 2026

This dated update supersedes the approval-pending language in PR #301's original
preparation milestone. Howard explicitly approved the proposed engineering window
in chat; the local sealed receipt was recorded at 19:54:24 UTC on October 10.
No engineering attempt has run and the native adapter remains unproven.

- October 11, 2026, 9 AM–9 PM PDT (16:00 UTC October 11–04:00 UTC October 12).
- Up to ten fresh Oracle-only J1 retained-reference attempts, including failures.
- Strict #293 diagnostics; no unmatched-return degradation mode.
- Application image `sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`.
- Per attempt: 60 minutes work plus ten minutes cleanup; candidate timeout 30 minutes.
- Oracle 6 GiB / 2 CPUs; carrier and application each 8 GiB / 4 CPUs; observer
  768 MiB / 1 CPU. Output stop threshold 8 GiB; existing evidence caps unchanged.
- Zero model calls, qualification and measurement credit. No automatic retries.
- No overlap with any J1/B06 evidence window; prior evidence must be sealed.

Approval content seal:
`8ae72f28259363c0be56aa968ae2d8f93f4b368ef64b0e7fbae7ceefd324f97d`.
Exact local approval-file digest:
`06707cf831623bddc8b9c0c945fa2668b9bcf6b8fa36b9852c5bdb7b8ffe6889`.
The receipt binds implementation `9cde638d1379f08713403ab21e8e08834f7849ab`;
this milestone does not broaden its calendar, runtime, limits or experiment scope.
Runtime eligibility and overlap are checked again at invocation. Approval is not
proof of execution and does not authorize unreviewed JVM or image treatments.

Published implementation validation is 41 focused mocked/pure tests in 2.203 seconds.
The original preparation milestone's 1.963-second number describes an earlier run.
Alternative observer designs still have no native comparative measurements. The
latest diagnostic heap failure is preserved in the separate terminal milestone.
