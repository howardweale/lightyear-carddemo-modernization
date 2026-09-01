# Live Evidence and Control Tower Plane

v0.47.2 makes the canonical Knowledge Graph and source-evidence pack a first-class source in the
live, read-only operational projection first introduced in v0.17. The browser uses the approved
paper-white, stone, and burnt-orange visual system with locally served IBM Plex typography.

Operator navigation is graph-bound in this order: **Company → Business problem → Workload →
Technology scope → Operator lens**. Company and problem determine the permitted workload choices;
the workload supplies the graph root and curated perspective; scope and lens visually refine that
bounded graph without silently changing the selected business problem.

The plane
observes the authoritative stores already owned by Factory, Portfolio, Recovery, Quality, Memory,
Data, Runtime, and Audit; emits canonical events when their identities change; and streams those
events to the browser with Server-Sent Events (SSE). Graph changes refresh the live explorer and
invalidate a mismatched source-evidence pack, Runtime projection, or Audit projection until
graph-bound evidence is regenerated.

The event stream is not an execution bus. The browser has no approve, lease, retry, recover,
dispatch, promote, or exception-authoring endpoint. Production commands remain disabled until an
authenticated command API can bind SSO identity, role authorization, signed intent, policy,
idempotency, and audit evidence.

## Run locally

macOS or Linux:

```bash
./live-control-tower.sh serve
```

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\live-control-tower.ps1 serve
```

Open `http://127.0.0.1:8765`. The server refuses `0.0.0.0`, LAN addresses, and hostnames unless the
operator supplies `--i-understand-this-is-unauthenticated`; the warning does not replace enterprise
authentication. `127.0.0.0` is the loopback network identifier, not the Control Tower address. A
per-session bearer token printed in the terminal is required for verifier-audience routes. For a
customer deployment, place the service behind the customer's approved SSO/OIDC reverse proxy. Do
not open `knowledge/viewer/index.html` directly; static file mode cannot use the API or SSE stream.

## Operational contract

Each event carries a sequence, type, source, subject, severity, trust class, optional correlation
ID, occurrence and observation times, bounded payload, previous-event hash, and content hash. The
SQLite WAL ledger is the locally executable reference. Its tables and event contract intentionally
avoid UI-specific data so PostgreSQL and managed event-stream adapters can preserve the same
interface in production.

| Source | Typical latency | Authority shown |
|---|---:|---|
| Graph | seconds | canonical graph identity, source-evidence binding, entities and relationships |
| Factory | seconds | controller receipts and station transitions |
| Portfolio | seconds | approved plan, conflicts, waves, composite runs |
| Recovery | immediate | transactional leases, retries, dead letters |
| Quality | evaluation completion | signed, policy-evaluated receipts |
| Memory | verified promotion | controller-approved experience only |
| Runtime | near-real-time | observed execution evidence and trust class |
| Audit | immediate append | hash-chained decisions and release posture |

The status API reports freshness, age, last observation, last identity change, expected interval,
and trust class for every source. It also returns the graph identity and downstream binding status.
Alert rules cover graph-binding invalidation, dead letters, expired worker leases, stale runtime
evidence, unavailable recovery projections, and blocked release promotion.

## HTTP surface

- `GET /api/operations/status` — live connection, source freshness, sequence and alerts;
- `GET /api/operations/events?after=N` — bounded replay for diagnostics;
- `GET /api/operations/stream?after=N` — resumable SSE stream;
- all existing domain APIs remain read-only.

## Production hardening path

1. Replace the local event database with PostgreSQL plus an outbox or a managed stream.
2. Put the UI and API behind enterprise SSO, mTLS, RBAC/ABAC, rate limits and CSRF protection.
3. Separate query and command hosts; commands require signed, expiring, idempotent envelopes.
4. Project operational events into independently rebuildable read models.
5. Add trusted timestamps, asymmetric checkpoint signing, immutable retention and legal holds.
6. Connect z/OSMF/JES/SMF capture and surface source-system lag and collection health.
7. Route alerts to the enterprise incident system with acknowledgement and escalation evidence.

The Control Tower may explain and observe authority. It may not become authority merely because a
button exists in a browser.
