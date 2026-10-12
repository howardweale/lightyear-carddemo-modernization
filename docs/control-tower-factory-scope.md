# Factory scope administration

This delivery prepares software and unsigned requests only. Port 8768 is proposed;
no service, authority, identity or grant has been created on Howard's machine.
Use a separate operator-owned root, authority directory and journal. Never reuse
CardDemo intake or B06 directories. Factory disclosure is `public-development`.

## Operator installation after review

Use the existing CLI in a separately approved installation. The following are
commands for the administrator, not actions performed by the coding agent:

```powershell
python -m lightyear_control_tower provision --authority <authority>/authority.json --scope factory --operator-id howard --operator-name Howard
python -m lightyear_control_tower grant-roles --root <factory-root> --authority <authority>/authority.json --operator-id howard --roles operator qualification-approver campaign-authorizer business-owner --workloads factory:INTCALC factory:POSTTRAN factory:B06 factory:B07 factory:factory --reason "Factory public development review"
python -m lightyear_control_tower serve --root <factory-root> --authority <authority>/authority.json --port 8768
```

Use `add-identity` for another person, with their own credential output outside
the data root. Assign only their required roles. Agents receive no approving
roles. `propose_factory_decision` is an MCP draft annotation on an existing
request, not a decision or execution API. There is no approve MCP tool.

## Public artifact ingestion

`python -m lightyear_control_tower.factory_import --repository <public-checkout>
--root <factory-root> --contract <contract.json>` imports only regular committed
Git blobs below `docs/factory/`, each at its exact commit and SHA-256. Symlinks,
path traversal, duplicate JSON fields, nonfinite numbers and files over 8 MiB
are refused. Existing different bytes are never overwritten; use a new versioned
snapshot/root for new evidence. No arbitrary filesystem path is a public adapter.
The runtime uses `confined` and `read_bytes` and checks the imported bytes again.

Import `docs/factory/tower-backfill-request-2026-10-12.json` first. Its inventory
is independently compared with every `howard-decisions-*.json` in the pinned
Git tree. The complete dated documents remain visible as historical statements,
including conditions and hashes. No omitted hash is invented. Howard reviews and
signs one `factory-decision-backfill`; all three approving roles are required.
This acceptance does not itself satisfy a future spend, release or native gate.

Import `docs/factory/tower-posttran-review-request-2026-10-12.json` separately.
It binds the public unsigned decisions and review sheet. The queue requires an
explicit outcome and reason for every record; the historical file is evidence,
not a pre-filled signature. Generic decision contracts are specified in
`factory_policy.FIELDS`; unknown fields are refused.

## Activate signed-only consumers after Howard signs

Do not set the following setting before backfill acceptance. An operator-owned
`factory-consumer-trust/1` JSON file has exactly these fields: `schema`,
`public_key` (absolute path to the PUBLIC PEM), `trusted_head` (fresh journal
SHA-256 obtained out of band), `backfill_proof` (complete exported proof at that
head), and `backfill_contract` (the exact imported contract). Set the service
startup environment `LIGHTYEAR_FACTORY_AUTHORITY` to its absolute path.

The private key is never read by a consumer. The setting is deployment trust,
not part of an engine input packet. Protect it like the existing public trust
configuration. A missing or invalid configured file fails closed. Removing the
setting is an administrative rollback, not an input a request can supply.
Refresh the head and backfill proof together before consumption; an old proof
cannot establish current online authorization. Historical replay proves only
validity at its supplied head.

POSTTRAN spend and human review automatically consult this setting. The shared
`FactoryAuthority.spend` is the required entry point for future B07 spending;
there is no B07 dispatcher to enable. `scenario_policy.release` requires a signed
threshold bundle (`threshold`, `approval`, `io`, `equivalents`, `claim_scope`).
Threshold hashes use canonical JSON; equivalence packet hashes bind the complete
signed assessment. Only `unconditional` is effective; an accepted conditional
policy needs a later explicit effective approval. No condition is auto-waived.
Keep-or-fix consumers use `FactoryAuthority.behaviour`; absent decisions preserve
the legacy default. Engineering verification binds commit, seal, observer/class
hashes, caps and window; it does not dispatch anything.

The seven operational kinds and the backfill kind are Factory-only. The
presentation layer exposes only validated contract fields. Business-owner fix
requires acknowledging the exact dependency list; signed later fixes invalidate
prior equivalence acceptances for that entry. A changed plan requires a new
request. Work queue review is authenticated operator review, never independent
attestation. Intake retains four kinds and no-values rules. No B06 gate changes.


The dedicated POSTTRAN CLI accepts `--approval-proof <public-proof.json>` after
activation and rejects `--go`. This changes its source hash. The historical
Phase 1 plan is deliberately not amended or dispatched by this delivery; it
will refuse the new transport bytes until Howard approves an exact amended
plan. The HTTP worker's TLS, dedicated credential, no-retry and cap rules are
unchanged. No model or token-count call is made by this change.


## Programs snapshot and public index trust

Run `python -B tools/import_factory_tower_snapshot.py --repository <checkout>
--commit <full-40-character-commit> --root <new-factory-data-root>`. The destination
must be new. The importer reads only the closed `presentation.FACTORY_FILES` table
from regular Git blobs, writes exact bytes and prints a `factory-evidence-trust/1`
object. After independently checking its index hash, the administrator installs
that PUBLIC trust object as `factory-evidence-trust.json` beside the authority
file, outside the engine-writable root. This code does not install that trust.
The request importer can then add unsigned decision requests to that same root.
Do not point it at another scope or preserved B06 snapshot.

The Programs API rejects altered bytes, extra adapters, unlisted paths and a
changed index. Eight-MiB bounds apply per file. The receipt import under
`docs/factory/tower-run-38198096890/` is an exact copy of compact public artifacts;
provenance lists archive and file hashes. These observations remain attributed to
2dd787642e66176f78dbf749ec2659e82672cd3e. Historical records are not overwritten.
