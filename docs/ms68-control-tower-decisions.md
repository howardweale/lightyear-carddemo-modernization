# Control Tower: human decisions as evidence

The Control Tower now opens on **Work queue**. Its first decision type is the existing normalization
ledger for CardDemo interest calculation. Discovery remains available in the adjacent navigation.

This is one bounded operator-workflow increment for MS68. It does not redefine the existing MS68
customer-representative production-readiness milestone. That milestone still requires a passing
MS67 receipt, customer IdP, representative customer data and workload, customer infrastructure,
and a signed readiness decision. No MS67 execution inputs or existing receipts are changed here.

## What an operator does

1. Sign in with an individually issued operator credential. The service supplies the registered
   identity; the decision form cannot choose the approver's identity.
2. Open one of the three pending normalization entries. Inspect its scope, allowed difference,
   rationale, existing owner, review date, and exact evidence hashes. The view enters the session record.
3. Enter your reason, a named accountable owner, and a future review date. Choose **Approve and sign**
   or **Reject and sign**. An approval expires at the start of its review date in UTC. It cannot
   extend the ledger's review date or exceed 366 days.
4. The decision appears immediately with who, when, why, owner, expiry, and signed record identity.
   A later rejection or renewed decision appends history; it never overwrites the earlier event.
5. Choose **Run proof for this workload**, or use **Open proof run for this workload** in Discovery.
   The INTCALC reference checks actually execute in a staged copy. Progress and the result appear
   in **Proof runs**. No further human interaction is required while the checks run.
6. Download the signed gate receipt and session record. A passing proof can still have a blocked
   normalization gate until every current entry has a valid approval.

**All normalizations** includes approved entries and their decision history. Changed ledger content,
expired decisions, and rejections return entries to **Needs a decision**. Invalid ledger contracts
block the queue with an explicit error; an operator cannot approve malformed or out-of-contract rules.

The first release deliberately supports normalization decisions only. A schema field declaring
`promotion_decision` or `operator_attestation` is not, by itself, a pending task. Divergence
classification, claim promotion, and live-capture attestation need their own bound evidence and
roles before commands can be enabled. They are not fabricated as actionable queue items.

## Start locally

Use the same Python interpreter as the repository's launchers. Install the optional signing support:

```bash
python3 -m pip install -e '.[control-tower]'
./live-control-tower.sh init-operator --operator-id YOUR_INDIVIDUAL_ID --operator-name 'Your Full Name'
./live-control-tower.sh serve
```

On Windows, use the selected Python interpreter and `live-control-tower.ps1` with the same commands.
The provisioning command prints the credential file path, not the credential. Open that local file
and paste its contents into **Sign in to decide** at `http://127.0.0.1:8765`.

Provisioning generates an Ed25519 key pair, an individual random credential, and an authority
configuration under `work/control-tower/`. It does **not** approve any normalization. It refuses to
replace existing authority files. An administrator can provision more operators in the authority
configuration with distinct IDs, names, token SHA-256 digests, and the `normalization-approver` and/or
`proof-runner` roles; restart the server to apply configuration changes. Keep credentials individual.

The service enables when `work/control-tower/authority.json` exists, or when explicitly selected with
`serve --decision-config PATH`. Without a configured authority the UI reports that decisions are
unavailable. Static pages cannot sign decisions or dispatch proof runs. The existing verifier token
cannot authorize decisions.

Decision commands require an explicit loopback bind, a recognized local Host, JSON POST requests,
and an exact same-origin header. Sessions expire after one hour and end immediately on sign-out;
restarting the service invalidates active sessions. Tokens stay in browser memory. Customer-network
exposure is not enabled by the discovery server's unauthenticated-network override.

## The enforced gate

The browser calls the authoritative gate for a selected proof run. A pipeline can use the same gate:

```bash
./live-control-tower.sh qualify --run-id RUN_ID_FROM_THE_UI --output work/control-tower/operator-workflow.receipt.json
```

Use `--graph` if the server was launched against a different graph from the composite default.
There is no CLI approval or signature-bypass option. `qualify` exits nonzero unless all of these hold:

- The UI-dispatched INTCALC proof passed its actual policy checks and normalization contract validation.
- Its source manifest, canonical graph identity, and normalization ledger match current inputs.
- Every journal event has a valid Ed25519 signature and the entire hash chain is continuous.
- Every normalization has a current approved decision, bound to its exact entry and complete ledger.
- The approver reviewed that ledger version in the same authenticated session; reason and owner are
  present, and the review date remains in the future.

The receipt embeds the signed approval records and binds the proof record, ledger, source, graph,
and journal head. `operator_workflow_complete` can become true only through that gate. The receipt
always keeps `human_promotion_authorized`, `production_ready`, and `ms68_complete` false: this is a
required operator-workflow proof, not customer certification. There is no existing MS68 customer
execution controller to wire into yet; its future completion path must invoke this gate rather than
accept a supplied boolean. Existing automated MS1–MS67 paths keep their existing contracts.

The gate must be evaluated at acceptance time. A previously exported passing receipt is historical
evidence; it cannot override a later expiry, changed input, or superseding rejection. A malformed or
unverifiable journal blocks commands and qualification. A second decision-service writer is refused.
After a service crash, unfinished proof runs become **interrupted**; they are never silently retried
or reported as passing. A read-only qualification invocation does not interrupt a live run.

## Audit and signatures

Every session start/end, reviewed normalization, decision, proof start, and proof finish is appended
to `work/control-tower/decisions.sqlite3`. A transactional write binds actor, session ID, UTC time,
payload, sequence, previous hash, content hash, signing-key ID, and Ed25519 signature. Decision
submissions use a UUID and exact request digest; a repeated identical request returns the same
record, and conflicting reuse fails. Stale forms cannot overwrite a newer decision.

The service **countersigns authenticated operator intent**. The signature is the Control Tower
service's signature, not a personal hardware signature or proof that a biological human clicked.
A caller with an operator credential can call the same authenticated API. The browser is the
supported decision workflow; there is no honest technical claim that HTTP alone proves UI usage.
An agent must not impersonate an operator or manufacture their decisions.

Session exports include the full signed chain and an index of the selected session's events, so
continuity can be checked. They contain no bearer token, credential, or private key. Verify with a
public key obtained separately from the trusted authority, never a key accepted from the receipt:

```bash
./live-control-tower.sh verify-session --record SESSION_EXPORT.json --trusted-public-key work/control-tower/authority.public.pem
```

The local database provides durable, signed, tamper-evident history, not independently anchored
immutable retention. An administrator who controls the signer and database remains trusted; an
old valid database prefix cannot be distinguished from a rollback without an external checkpoint.
Customer admission needs customer identity and managed signing/retention controls before this
local-reference authority can be treated as a customer audit authority.

## Validation and first dogfood run

The dedicated CI workflow runs on Linux, macOS, and Windows. Tests execute the real bounded proof
and cover gate blockage before approvals, valid signatures, expiry, rejection, content changes,
role/session authorization, same-origin requests, request retries, concurrent decisions, tampering,
failed proofs, restart persistence, and exclusive writer ownership. Existing graph, operational
stream, and comparator regression suites run alongside it.

Automated test decisions use temporary authorities named **Test Operator**. They do not count as
operator dogfooding or customer evidence. The first real operator must review the three entries
in the UI, dispatch the proof, and retain its signed session and gate receipt. This is the remaining
human step; the implementation does not approve the ledger on the operator's behalf.
