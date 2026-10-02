# Decision Console

The console records service-countersigned authenticated human intent. It cannot
launch, resume, cancel, schedule or determine engine verdicts. Agent credentials
can read scoped evidence and prepare labelled drafts; they cannot approve.

Existing `DecisionService` normalization records, routes and session exports retain
their wire format. The new scoped `ConsoleService` reuses its authentication/journal
kernel and registers typed decision kinds. The legacy `init-operator` provisioner
historically grants normalization/proof roles; it is retained for compatibility.
The new `provision` command grants **no roles**. Local `grant-roles` assignments are
journaled and checked on every request, including already-open sessions.

Each deployment has one root, scope, authority key and journal. Configuration is
local; request paths cannot escape their root or traverse symbolic links. Requests
live in `work/control-tower/requests/<scope>/<id>.json`, schema `tower-request/1`.
They include `id`, `scope`, registered `kind`, `summary`, `proposed_by`, `bound` and
`evidence`. Every bound value is the SHA-256 of the exact bytes at the matching
relative evidence path. The service additionally binds the entire request object.
Invalid or partially written requests are visible as invalid and cannot be decided.

`tower-decision/1` records preserve evidence hashes, identity and held roles, the
session that viewed the item, request idempotency and independence. A different
account alone does not justify an independence claim: operator-review-allowed
kinds are labelled operator review. Independent-review kinds refuse self-review.

Engines use `verify_decision` with an exported signed journal, exact expected bound
map and **fresh trusted journal head**. The four-argument offline form verifies at
the supplied archive head only; it cannot discover a newer withheld export.
Neither this API nor a Tower signature bypasses an execution environment's own
approval policy. Frozen MS94 controllers do not consume these decisions.

Development is on `codex/control-tower-decision-console`, based on `819ef1e`.
No frozen MS94 input, running campaign, historical signature or result is modified.
The delivery is split into foundation, cockpit, queue, catalogue and customer
workspaces. The Lane Adapter Standard is an external dependency: catalogue views
remain unavailable (or explicitly fixture-labelled in tests) until signed records
are provided. No lane qualification is inferred from fixture data.

## Run locally

Install the existing `control-tower` extra. Use a dedicated data root for each
engagement. The authority must be inside that root. An ownership record prevents
reusing the same root with another scope/key.

```powershell
$consoleRoot = Join-Path (Get-Location) 'work/console-local'
$consoleAuthority = Join-Path $consoleRoot 'private/authority.json'
python -m lightyear_control_tower provision --authority $consoleAuthority --scope local-review --operator-id reviewer --operator-name 'Local reviewer'
python -m lightyear_control_tower grant-roles --root $consoleRoot --authority $consoleAuthority --operator-id reviewer --roles operator campaign-authorizer --reason 'Explicit local operator assignment'
python -m lightyear_control_tower serve --root $consoleRoot --authority $consoleAuthority
```

Open `http://127.0.0.1:8766/` and sign in using the generated individual credential
file. The existing viewer's **Campaigns and decisions** link opens this console.
The console is loopback-only and rejects foreign-origin writes. No network hosting
override is provided. Tokens stay in browser memory, not local storage or URLs.

Local administrative commands run while the console is closed; the service owns
the single journal-writer lock. `add-identity` creates another credential with no
roles. `grant-roles --workloads <workload-id>` is required for a business owner;
workload ownership is enforced at decision time. Empty `--roles` revokes access,
including existing sessions. A `customer-sponsor` must be a customer identity;
an agent cannot receive any approving role.

MCP connects to the running service, so it never opens a second journal writer or
loads the authority key:

```text
python -m lightyear_control_tower.mcp --url http://127.0.0.1:8766 --credential-file <agent-credential-file>
```

The `agent` optional dependency supplies the existing MCP runtime. Only the seven
read/draft tools are exposed. Human approval remains in the console.

## Local campaign registry and evidence

Copy `control-tower/campaigns.example.json` into the **data root's**
`control-tower/campaigns.json`, with explicitly selected local roots, a trusted
public key and a scope matching the authority. Registry paths are ignored by Git
and never returned by the campaign-list API. Adapters read signed MS94 Stage B and
equipment artifacts, and checkpointed NUMBER journal exports. A missing private
snapshot remains unavailable; verifying public signatures never becomes a claim
that private files were checked.

Observer settings extend the existing policy under `decision_console_observer`.
Alerts carry that policy's hash. Polling is 3 seconds while visible, 30 while hidden.
The bounded SSE endpoint uses the same scoped projection. Incomplete final JSONL
records are ignored without truncation, repair, locking or writing to the source.

The B04 fixture preserves exact selected original signed records and a VOID report.
Its provenance manifest hashes every copied file. It intentionally excludes private
captures, checkpoints, reference sources and the full executable. Regression tests
require `accounting_cache` to pair cohorts 1 and 3, and require the analyst's
`insufficient-type-evidence` rejection on cohort 2 to trigger a gate-decline alert.
No historic decision is re-signed or upgraded. B04 remains VOID.

## Rules, catalogue and customer release

Rule proposals are typed records using registered operations. They bind a workload,
field, lane pair, owner, review date and planted still-caught fixture. Technical
approval runs the existing normalization-ledger validator and the registered
still-caught validator. A rule proposer cannot approve their own rule. Business
approval binds a current technical decision and records whether the business owner
also performed that technical review. A derived register includes only approved,
unretired rules; review-due warnings do not silently retire a rule. The Tower never
installs rules into the judge or changes an existing divergent verdict.

LAS is not present at this baseline. The included qualification replay backend
accepts only explicitly labelled **fixture** records and replays signed control
receipt bindings/outcomes. A production qualification is refused until its trusted
native LAS replay adapter is implemented. This is not a replacement native
qualification or an MS94 replay. Unknown rule operations likewise fail closed.

`tools/catalogue_publish.py` is an engine-side generator, never a browser/MCP route.
It requires accepted qualification proofs at the current journal head, checks exact
record bytes and applies expiry to platform-major, adapter, judge or register-major
changes before signing the catalogue. The viewer only renders the resulting signed
status. `catalogue-check` compares that hash and every status with both public
projections. CI exercises its success and nonzero drift paths using disposable
signed fixtures. No production catalogue/website claim is created by these tests.

Customer roots use `control-tower/workspace.json` to select a scoped signed estate
projection and curated public-evidence bundle. Default views exclude observation
values and raw captures. Release requires two identities, one customer sponsor and
one campaign authorizer, approving the exact same canonical archive bytes. Partners
see only the customer's current share level; evidence sharing binds the released
archive hash. Auditors can read and verify but all domain-write routes return 403.

```text
python -m lightyear_control_tower verify-export --archive export.json --trusted-public-key trusted.pem
python -m lightyear_control_tower catalogue-check --root <root> --trusted-public-key trusted.pem --public lanes.public.json --website coverage.json
```

Offline export verification checks the trusted signature, scope, members, journal
chain and both release decisions at the archived head. It does **not** re-execute
native databases or claim a newer, withheld decision does not exist.

## Delivery and validation

The five delivery units are foundation; cockpit and future-controller admission;
rule/qualification queue; catalogue and consistency checks; customer isolation and
release. Later units are discovered only from a closed list of built-in modules.
Missing units expose unavailable views and cannot approve guarded decisions.

`TowerControllerV2.run` is the new headless controller boundary: it obtains a fresh
trusted handoff before every slot. Missing authorization, changed plan bindings,
pause without verified resume, and any terminal stop/void refuse execution. It is
not wired into any frozen MS94 controller. A future measurement must explicitly
freeze this new controller and its authorization contract.

A resume request binds the SHA256 of the exact pause evidence file. Engine
adapters write that file using `controller_decisions.pause_evidence(event)`;
this binds the signed envelope bytes, not only its internal content hash.
Missing historical cost fields display as unavailable, never as zero cost.

Run the unchanged normalization tests and the new `test_decision_console*.py`
suite. The browser test is `node tests/browser/decision-console.mjs` after installing
the existing pinned browser dependencies. It uses a disposable local authority and
archive fixture, checks the alerts and decision flow, and asserts zero external
browser requests. No models, native campaign pairs or cloud APIs are used.

Outside this milestone: production LAS replay, SSO implementation, multi-tenant
hosting, WORM retention, actual engine dispatch, remote customer deployment and
migration/launch of existing measurements. No signing key is exported.
