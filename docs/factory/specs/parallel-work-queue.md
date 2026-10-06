# Verification-bounded queue seam

Status: interface and in-memory conformance implementation only. No production
runner, model calls or Docker. Operator review; not independent attestation.

`lightyear_factory.parallel_queue.WorkQueue` defines submit, claim, heartbeat and
complete. `InMemoryWorkQueue` is for tests and process-local experiments only;
it loses state when the process exits. The existing SQLite `DurableQueue` remains
unchanged. A future adapter should use its transactional store rather than add
another persistence engine.

The production adapter must atomically store order identity, status, lease owner,
expiry, fencing token, claim request ID, heartbeat history and receipt identity.
An identical submit/claim is idempotent. Reusing an ID with a different body is an
error. Expired claims require a new request ID and token; stale workers cannot
heartbeat or complete. Completion is idempotent only for the same token/receipt.
Only independently verified receipts may free production verification capacity.

Scheduling reuses `portfolio._conflicts`: overlapping paths, shared nodes,
declared dependencies and graph distance serialize work. Capacity is the number
of available **verification** slots, capped at 64 in the seam. Generation capacity
does not raise this ceiling. A durable implementation must lock conflict checks
and lease allocation in one transaction and recover abandoned leases explicitly.

There is intentionally no execution callback, thread pool, Docker control or
model provider in this queue. A future runner requires separate review, including
lease recovery during long native checks, fairness, capacity reservation across
hosts, cancellation and a replayable audit trail. Target tens of work orders.
