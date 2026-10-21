# Plain-search adapter and G3 fixture parity

The plain-search context mode implements G3's source-only retrieval arm. It is
available only through the existing bounded factory controller and model-call
accounting, with network access denied. This implementation does not authorize
model calls, installation, signing, activation or a comparison campaign.

Set work-order metadata `graph` to `plain-search`, `context_schema` to `1.1`,
and `graph_policy` to `call_budget`, `response_bytes`, and `corpus_sha256`.
The corpus digest is the canonical hash of the controller's entire public
workspace read manifest (relative path to raw-file SHA-256). The controller
verifies and scans every file before constructing a private in-memory snapshot.
The source snapshot stays fixed across candidate edits and repair attempts.
It is not an unrestricted filesystem search or a search over a graph export.

Planner and failure Analyst may share at most eight tool calls, each with a
complete response cap of 1,024–8,192 bytes and a total ceiling of 65,536 bytes.
`search_code(query)` searches all pinned files literally and case-sensitively.
It returns every matching line or refuses the whole oversized result; it does
not silently choose hits. `read_file(path,line_start,line_end)` returns an
inclusive range of at most 200 lines from a listed file. No shell, regex,
embedding, graph or judge tool is exposed. Builder has no tool envelope.

The initial context is constructed without graph nodes, edges, annotations,
memory, curated symbols or source previews. Queries return hash-bound source
capsules. A validated plan may select those capsules for Builder; fabricated
IDs are refused. The shared model loop counts every request and retry under
the existing run budget. Each retrieval records run/work-order/corpus binding,
role, attempt, scanned arguments, result hash and complete byte count in the
controller ledger. Rejected content is not copied into diagnostics. Receipt
construction checks persisted events and their preceding isolation scans.

CI runs the real controller paths for on-demand graph, packed graph and plain
search using the same pinned public sources, scripted providers and stub gates.
The audit verifies every projection excerpt against the public source bytes,
identical non-context work-order fields, base role instructions and answer
schemas, Builder's lack of tools, actual delivered result hashes and sizes,
and all captured prompt bytes including repeated input. Differences in tool
schemas, context and disclosure timing are intentional and retained for review.
The G3 plan therefore continues to estimate a context-mode policy effect.

The `g3-zero-model-parity-<CI checkout SHA>` artifact contains `parity.json`
and complete public fixture requests for all three modes. Its source SHA is
the actual GitHub CI checkout SHA (which may be a pull-request merge SHA), with
run and attempt recorded. The existing boundary workflow must pass; refusal
fixtures cover private and encoded material, paths, hashes, budgets, changed
prompts and unaccounted responses. Tests execute only in CI.

These fixture measurements are neither production token/cost estimates nor
proof of real-model equivalence. Before any comparison spend, freeze and
review real prompt diffs, model/effort, the executable corpus and projection,
packing policy, schedule, analysis implementation and approved scope/budget/
window. Retain the original dated preregistration unchanged. The audit has no
authority to seal a request, approve a run or issue a production acceptance.
