# Enterprise collection appliance evidence

This directory is the deterministic MS #28 appliance evidence set. It contains the final
content-addressed checkpoint, one bounded capture per required MS #21 adapter, the eight-scenario
fault-laboratory receipt, and the aggregate appliance receipt.

Rebuild and compare it byte-for-byte with:

```bash
./collection-appliance.sh verify
```

The artifacts use simulated responses and faults. They qualify pagination, retry, recovery,
retention, authentication-policy, and fail-closed behavior only. They do not record a customer
mainframe, IdP, vault, purge scheduler, or production network run.
