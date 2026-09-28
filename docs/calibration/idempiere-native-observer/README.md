# Native transaction observer qualification

This publication preserves four instrument-development attempts before any scored MS92 declaration: three unsuccessful attempts and the final pass. It contains signed run receipts, plans, cleanup records and raw engine samples. Zero model calls and zero scored factory journeys were performed.

| Run suffix | Result | What was learned |
| --- | --- | --- |
| e28a0c204db04e4880c7929585954bb1 | Failed | PostgreSQL snapshot completion horizon could not safely resolve an active transaction ID. |
| 90d75fc601b84ddb87a2591e42947f0f | Failed | Non-atomic Oracle session/lock queries lost the rollback transaction association. |
| fa89ca1c8b8640a79d3dc7ba8e1f8ffb | Failed | Reordering the PostgreSQL queries alone did not fix transaction identity. |
| 0876955b3bc14e65b18a530ba6882a88 | Passed | Private observer transaction identity and retained Oracle transaction association captured both event types. |

The final capture has 14 Oracle and 33 PostgreSQL lock-witness samples, plus two rollback witnesses per engine. Consecutive samples are **not independent lock-wait experiments**. The controlled fixture uses two transactions, waits on a business-partner row and rolls back. Before/after application row multisets were checked unchanged; those large business snapshots remain in the local qualification runs and are not part of this compact publication.

Raw samples and query texts/hashes allow replay of the final engine-observation check. Only the final attempt has the original three observer source files copied alongside it. Earlier failed captures are preserved and hash-verified; complete historical source replay is not claimed for them. These were pre-freeze development changes, never campaign repairs.

```powershell
$env:PYTHONPATH='src;.'
python -m tools.publish_observer_qualification verify `
  --output docs/calibration/idempiere-native-observer `
  --trusted-key-sha256 c2fbae3453e8bcae03e0830a9eb83f310f027ad51929deee967ecee1a41f399f
```

The verification requires the qualified observer implementation. Check the public-key fingerprint through a separately trusted channel. Local signatures provide attribution and tamper evidence, not independent attestation.

This is bounded engine-side observation involving `adempiere.c_bpartner`, not exact per-row undo history, crash recovery, platform qualification or application equivalence. Dedicated observer output is inaccessible to the generated application until it stops. PostgreSQL observer transactions allocate private transaction IDs without application-row writes.

Primary engine references: [PostgreSQL transaction identity and status](https://www.postgresql.org/docs/15/functions-info.html#FUNCTIONS-PG-SNAPSHOT), [PostgreSQL locks](https://www.postgresql.org/docs/15/view-pg-locks.html), [Oracle V$LOCK](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/V-LOCK.html), [Oracle V$SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/V-SESSION.html).
