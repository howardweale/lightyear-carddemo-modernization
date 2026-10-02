# Scoped decision kernel

This is delivery unit 1 of the Decision Console. It adds a scoped kernel and a
closed decision-kind registry over the existing `DecisionService` journal/signing
code. Legacy normalization event bytes and `verify-session` stay compatible.
The cockpit, workflow validators, catalogue and customer views are later units;
missing modules are unavailable and guarded approvals fail closed.

Provision a dedicated data root with `python -m lightyear_control_tower provision`.
No roles are granted. Use the local `grant-roles` command with an explicit reason
to assign roles, or an empty role list to revoke them. The authority must reside
inside the root. One scope/key owns that root; a second scope/key is refused.
Administrative commands require the console's writer to be closed.

An engine's `tower-request/1` record lives under
`work/control-tower/requests/<scope>/<id>.json`. Required fields are `schema`,
`scope`, `id`, `kind`, `summary`, `proposed_by`, `bound`, and `evidence`.
`bound` maps names to SHA-256 hashes of the exact bytes at matching relative
`evidence` paths. Each kind declares its required names. The entire request is
additionally hashed to bind its summary, author and disclosure metadata.

The kernel checks current roles, independent-review requirements, exact current
evidence, same-session review and the previous decision before appending a
`tower-decision/1` event. A request UUID is idempotent only for the same actor and
payload. An agent can propose but cannot be assigned an approving role or decide.
The service countersigns intent; it never claims a person's cryptographic signature.

The verifier accepts a `tower-decision-proof/1` containing the decision hash and a
signed `tower-journal-export/1`. Consumers supply the exact expected bound map,
kind, permitted outcomes, scope and a **fresh trusted journal head**. Offline
verification is limited to the head in the archive. A valid old signature alone
cannot establish that no newer stop/void exists.

MCP exposes only `queue`, `item`, `campaign_status`, `catalogue`, `propose_rule`,
`prepare_classification`, and `annotate_request`. It uses an agent credential and
the loopback service, keeping one journal writer. No model client, engine dispatch
or approval tool is exposed. Source modules for later read views are discovered
only from a closed built-in list, never a module/command named by a request.

Validation: `tests/test_decision_console.py` plus the unchanged
`tests/test_control_tower_decisions.py`. No frozen MS94 file, historical signature,
campaign process or result changes in this unit.
