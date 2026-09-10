# MS67 nonproduction SQL recovery acceptance

**Decision: SQL recovery passes the revised nonproduction PITR requirement.**

On 2026-09-10 Howard Weale explicitly approved changing the PITR recovery-time
requirement from 600 to **630 seconds** because MS67 uses a synthetic,
noncustomer environment. The change applies to the acceptance of existing
measurements as well as future runs.

| Reported measurement | Attempt 1 | Attempt 2 | Requirement |
| --- | ---: | ---: | ---: |
| PITR recovery time | 626 s | 622 s | At most 630 s |
| Backup restore time | 455 s | 455 s | At most 600 s |
| Recovery-point age | 16 s | 18 s | At most 60 s |
| Exact restored state | Matched | Matched | Required |
| Applications restored and isolated target deleted | Passed | Passed | Required |

These values are the operator-provided results. The second attempt has 8 seconds
of margin against the revised PITR limit. No timings were shortened and no new
recovery execution is claimed.

The previous signed failures remain historical evidence of the 600-second
assessment. `tools/ms67_accept_sql_recovery.py` verifies the original private
evidence and writes a separate signed acceptance under policy
`ms67-nonproduction-pitr-rto-630-2026-09-10`. The reassessment embeds the original
signed observation and preserves all measurements and release bindings.

This decision accepts the SQL recovery component. It does not certify a
production SLA or assert that the separate MS65/MS67 platform controls have
all completed.
