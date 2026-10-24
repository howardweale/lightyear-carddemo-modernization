# First COPAU run-visible boundary — 24 October 2026

Howard selected **graph=none, memory=disabled, context=packed** on 24 October.
This additive decision applies only to the first COPAU run. The model, USD 10
cap, eight-hour wall cap and 30 October 08:00–20:00 Pacific window are unchanged.
No signature, model call, private generation, Tower write or proof export is
authorized. `request_ready` remains false. This record is not merge approval.

## Explicit disabled-surface exception

The 23 October qualification amendment required positive records on every surface.
Howard explicitly excepted the disabled graph on 24 October. The boundary retains
schema `copau-run-visible-boundary/1` and records **zero graph data records**,
status `disabled`, exception `copau-empty-graph-2026-10-24`, and the exact hash of
one `copau-disabled-graph/1` declaration. The declaration says zero nodes, edges
and tool calls. It is a configuration record, not a fictional graph node.
The helper still scans that declaration's actual bytes; the scanner and its
40-character matching, normalization and decoding rules are unchanged.

Howard also accepted that the unchanged 40-character scan cannot detect isolated
short-field leaks, **for this first COPAU run only**. No broader leak guarantee,
accepted P5 gap or weakened collision/selection requirement follows from that.

## Enforced launch and pending signed bindings

For WorkOrder `copau-first-factory-run-2026-10-30`, the CLI requires
`--factory-run-boundary`. After verifying the WorkOrder envelope, but before
nonce consumption, identity issuance or provider credential leasing, it refuses
any explicit graph/evidence/projection option, any graph tool policy or roots,
and any memory option or metadata. Abbreviated and `--option=value` forms are
covered. It passes actual `None` objects for graph/evidence to the controller and
disables semantic memory. Host compatibility mode cannot bypass this requirement.

The existing signed-plan verifier must validate the exact boundary and launch
settings binding. The later concrete F2 plan must contain `run_visible_boundary`
with `path`, exact-file `sha256`, `launch_settings_sha256` and `main_commit`.
The plan executable must equal that main commit. No existing F2 record or seal
is rewritten by this PR. After the approved P5 repair merges, recompute F2 from
the exact merge commit, publish before/after hashes, rebuild the boundary and
index, and obtain Howard's digest review. No readiness before all fields pass CI.

## Public collection and limits

The CI collector derives inputs from the committed F2 request, its exact 403-file
manifest (`bb11b3644a6070d7176767d82826d451e0b5055a6ce3e5eda0495c45591b0771`),
and the actual controller call paths. It reconstructs the retained worker from
380 independently hash-checked capsule members plus 23 exact source objects.
Only these current operational public Release inputs are downloaded. Historical
CI artifacts and other Release payloads remain **not inspected; not relevant to
freshly generated values**. Known IDs, expired IDs, catalog errors and unknown
deleted history are retained without turning historical absence into a gate.

Prompt coverage follows `ModelAgentSet.plan/build/analyze_failure`, `_call_once`,
the configured router and provider request envelopes. Context coverage follows
`FactoryOrchestrator._context`, the assembler's planner/builder projections,
WorkOrder serialization, gate failure views and worker construction. Each source
template record names its function, line span and exact source hash. Full source
bytes conservatively include unused literal branches. The public order, all 403
worker input files and three actual rendered context records are also indexed.
This is an explicit call-path inventory, not a folder listing used as closure.

Current F2 `allowed_paths` names a directory, while the packer reads regular-file
paths; therefore the present packed context has zero allowed-file excerpts.
That limitation is disclosed, not repaired or silently replaced with a broader
context. Model-generated plans/edits and sanitized runtime failures are dynamic;
their schemas/packing source are included, and runtime isolation scanning remains
required. Howard reviews those limits along with the exact index digest.

CI invokes `tools/copau_public_corpus_index.py` and uploads `boundary.json`,
`index.json`, public surfaces and `receipt.json`. Both index and boundary remain
**unreviewed**. The receipt gives hashes, counts, gaps and the CI run URL. Changes
to main, graph, workspace, templates or launch settings invalidate prior approval.
The Windows public layout is `C:\Users\howar\Lightyear\COPAUReview-v1` so exact
index paths can be reproduced on Howard's PC without rewriting the approved index.
Public files may be relocated only by creating and reviewing a new index digest.

## PowerShell: prepare arguments only; no private-store access

Run from normal Howard PowerShell. These commands inspect only the public
checkout and index, then build an argument array. They do not invoke the private
helper, read a private path, initialize a directory, create a seed or signing key.
No seed value, seed argument or seed environment variable is used. Every exposed
root must be listed. Do not substitute an unreviewed index or omit a root.

```powershell
$ErrorActionPreference = 'Stop'
$ReviewedCommit = '<EXACT_REVIEWED_40_CHARACTER_COMMIT>'
$Index = '<ABSOLUTE_REVIEWED_INDEX_PATH>'
$IndexDigest = '<EXACT_APPROVED_INDEX_SHA256>'
$Checkout = 'C:\Users\howar\Lightyear\COPAUReview-v1\repository'
$ExposedRoots = @('<WORKER_ROOT>', '<DISABLED_GRAPH_DECLARATION_ROOT>',
  '<PROMPTS_ROOT>', '<CONTEXTS_ROOT>', '<FACTORY_RUN_OUTPUT_ROOT>', '<EACH_OTHER_EXPOSED_ROOT>')
Set-Location -LiteralPath $Checkout
$env:PYTHONPATH = 'src;.'
$env:PYTHONDONTWRITEBYTECODE = '1'
if ((git rev-parse HEAD) -cne $ReviewedCommit) { throw 'Reviewed checkout mismatch' }
if ((Get-FileHash -LiteralPath $Index -Algorithm SHA256).Hash.ToLowerInvariant() -cne $IndexDigest) {
  throw 'Reviewed public index mismatch'
}
$HelperArgs = @('-B','-m','tools.copau_answer_key','--reviewed-commit',$ReviewedCommit,
  '--corpus-index',$Index,'--reviewed-corpus-sha256',$IndexDigest,
  '--expected-owner-sid',[Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
foreach ($Root in $ExposedRoots) { $HelperArgs += @('--exposed-root',$Root) }
# STOP. Arguments only. The private helper is not invoked by these commands.
```

The helper's already reviewed default private location and custody rules remain
unchanged. A later separately authorized private invocation uses this argument
array; generating the public boundary does not authorize that invocation.
