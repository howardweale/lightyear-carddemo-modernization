# Lightyear Verify: INTCALC through MCP

Lightyear Verify accepts a runnable Java JAR, executes it against operator-held
evaluation inputs, and returns an INTCALC verdict, policy-limited diagnostics and an
Ed25519 receipt. It reuses the existing z/OS intake, comparator and offline replay.
The toolkit and judge live in separate Python namespaces; this does not select a
new licence. This release supports one operator-owned INTCALC task per judge
process, JAR submission, and Linux isolation. Source-bundle builds and hosted
multi-tenant operation are outside this implementation.

See the [confidential evaluation milestone](hardening-milestone.md),
[implementation milestone](milestone.md) and [acceptance record](acceptance.md)
for the original delivery. The [PR235 follow-up record](pr235-hardening.md) covers
these disclosure, budget, decision and execution changes.

For a dedicated macOS Multipass Ubuntu 24.04 rehearsal, use the
[zero-model smoke setup kit and manual runbook](smoke-runbook.md). It records
arm64/x86_64 platform checks separately; live model tests require approval.
The [smoke-kit milestone](smoke-milestone.md) records local validation and the
remaining VM checks.

## Optional graph context

The [operator guide](graph-context-operator.md) describes signed public-source
projections, a judge-side leak check and the expiring Tower approval. With no
approved projection configured, tool names and schemas remain the original ten.
No private graph, evidence pack or evaluation records are loaded by the toolkit.
The [graph implementation milestone](graph-context-milestone.md) records the
offline checks and remaining platform limits; the [A/B draft](specs/graph-context-ab.md)
requires separate approval before any live model test.

| Optional tool | Read-only output |
| --- | --- |
| `graph_search` | Paged node identities, summaries and provenance |
| `graph_node` | Allowlisted properties and optional approved source |
| `graph_neighbors` | Paged structural edges, depth one or two |
| `graph_references` | Up to 50 lexical source references to a field |
| `explain_divergence` | Code/layout context for the existing visible verdict |

Graph responses default to 8 KiB and are capped at 32 KiB. With graph tools
enabled, `decode_records` also accepts `offset`, `limit` (50 default, 200 max),
`fields` and `summary`; these operate only on bound public development files.
The graph-off decode signature/default stays unchanged for existing smoke clients.
Receipt v2 binds the approved projection hash; old v1 receipts imply null.
See the [supplied spec](specs/graph-context-tools.md) and the
[prospective A/B draft](specs/graph-context-ab.md). No live comparison is authorized.

## Trust boundary and installation

The agent runs `lightyear-verify-mcp` over stdio. The operator separately launches
`lightyear-judge`. Only the judge can read evaluation inputs, expected outputs,
private execution logs and its signing key. The agent has a task-scoped HTTP
capability token, not a signing key or filesystem credential. The service binds
only 127.0.0.1. Do not expose it through a proxy or public listener.

Use a Linux filesystem, Python 3.11+, Java 17+ and bubblewrap with working user,
mount, PID and network namespaces. WSL Ubuntu is supported with the installation
and private data on its Linux filesystem, not under `/mnt/c`. The stdio toolkit
also supports Windows. The judge refuses Windows, root, shared agent/judge UIDs,
agent-writable installations and private roots with group/other permissions.
There is no unsandboxed fallback.

Example setup by an administrator (adapt the paths and existing user accounts):

```sh
sudo apt-get install bubblewrap openjdk-21-jdk-headless python3-venv
sudo useradd --create-home --shell /bin/bash lyjudge
sudo useradd --create-home --shell /bin/bash lyagent
# Put this reviewed checkout at /opt/lightyear-verify, owned by root.
sudo python3 -m venv /opt/lightyear-verify-venv
sudo /opt/lightyear-verify-venv/bin/pip install -e '/opt/lightyear-verify[verify]'
sudo chmod -R go-w /opt/lightyear-verify /opt/lightyear-verify-venv
sudo install -d -m 700 -o lyjudge -g lyjudge /var/lib/lightyear-verify
sudo install -d -m 700 -o lyjudge -g lyjudge /var/lib/lightyear-verify/evaluation
sudo install -d -m 755 -o lyjudge -g lyjudge /srv/verify-tower
```

The editable installation is deliberate: existing bindings resolve the reviewed
repository's `spec/mainframe` assets. Use the protected installation for the judge;
the agent's development checkout is separate. Keep evaluation data outside that
installation. Neither account may have sudo/admin access, membership in the
other account's group, ptrace privileges, or filesystem ACLs granting access to
private storage. A privileged local user is outside this trust boundary.

Copy the approved evaluation delivery into the private evaluation directory as
the judge account, preserving `run.json`, before/after files and intake metadata.
For a rehearsal use only `tests/mainframe/fixtures/arrival-rehearsal/INTCALC-run1-*`.
Run 2 deliberately contains processing-timestamp drift; it is a negative control,
not an equivalent positive control without a separately approved normalization.
Never place Maintec files in the agent workspace or public manifest.

Create private operator `config.json` (replace `agent_uid` with `id -u lyagent`):

```json
{
  "task_id": "verify-intcalc",
  "agent_uid": 1002,
  "evaluation": "/var/lib/lightyear-verify/evaluation",
  "exports": "/srv/verify-tower/exports",
  "tower_workspace": "/srv/verify-tower",
  "submissions": 5,
  "attempt_slots": 5,
  "disclosure_mode": "field",
  "fixture": true,
  "public_task": {
    "source": "CBACT04C",
    "target": "Java",
    "development_manifest": "public.json",
    "shapes": ["ACCTFILE", "TRANSACT"]
  }
}
```

`public_task` is explicitly public operator-authored metadata. Review it before
initialization; it must contain no evaluation values. The example is public-fixture
mode. For non-public data set `fixture: false` and omit `disclosure_mode` (or set
it to `confidential`). Non-fixture tasks cannot select field mode. Confidential
receipts return only the verdict and the affected dataset identities with the
single kind `differs`: no field, exception kind, counts or count bands. Do not
claim rehearsal coverage as Maintec equivalence.

For Tower review, put the independently trusted Console public PEM **contents** in
`tower_public_key` before initialization. This pins the operator authority; a
proof cannot select its own key. Bind the same authority for every task using an
inventory. Omitting it disables review imports and budget increases, fail-closed.

```sh
sudo -u lyjudge /opt/lightyear-verify-venv/bin/lightyear-judge init \
  --data-root /var/lib/lightyear-verify/session --config /var/lib/lightyear-verify/config.json
sudo -u lyjudge /opt/lightyear-verify-venv/bin/lightyear-judge serve \
  --data-root /var/lib/lightyear-verify/session --task verify-intcalc --port 8770
```

Startup emits `{"status":"ready","port":8770,"task":"verify-intcalc"}`.
Use an operator-managed service manager for persistence. Initialization never
overwrites an existing task. Restarting the service preserves budgets and journal;
an interrupted accepted attempt is consumed, becomes indeterminate, and blocks
new submissions pending operator investigation. A crash cannot reset the budget.

Provision **only** the contents of `session/token` into the agent launcher's
`LIGHTYEAR_VERIFY_TOKEN` environment through the operator's local secret channel.
Do not copy the private key, evaluation data, config or entire session folder.
Keep tokens out of checked-in configs and command-line arguments.

Prove separation before admitting non-public data:

```sh
sudo -u lyagent test ! -r /var/lib/lightyear-verify/session/authority.pem
sudo -u lyagent test ! -r /var/lib/lightyear-verify/evaluation
sudo -u lyagent test ! -w /opt/lightyear-verify/src/lightyear_judge/service.py
```

Run the two-user acceptance suite below as well. A submitted candidate sees only
its JAR, evaluation **inputs**, a minimal Java runtime and three writable output
files. It cannot see expected outputs, host home, signing material, service token
or the host network. Logs stay private. Heap, process, file, CPU and wall-time
limits bound execution. This is local namespace isolation, not a VM or a claim
against kernel exploits, malicious native-memory exhaustion or timing side channels.

## AppArmor on Ubuntu 24.04 and WSL

Keep host user-namespace restrictions enabled. Ubuntu 24.04 supplies the dedicated
bubblewrap policy in the optional `apparmor-profiles` package. Install and load
that policy; it is not necessarily present in `/etc/apparmor.d` by default:

```sh
sudo apt-get install apparmor apparmor-profiles bubblewrap
if [ ! -f /etc/apparmor.d/bwrap-userns-restrict ]; then
  sudo install -o root -g root -m 0644 /usr/share/apparmor/extra-profiles/bwrap-userns-restrict /etc/apparmor.d/bwrap-userns-restrict
fi
sudo apparmor_parser -r /etc/apparmor.d/bwrap-userns-restrict
sudo aa-status
sudo -u lyjudge bwrap --unshare-all --ro-bind / / --proc /proc --dev /dev /usr/bin/true
```

Use the distribution's `bwrap-userns-restrict` policy where available: it grants
bubblewrap setup permissions and restricts namespace creation by its children.
If the profile is missing, update the distro packages or have the host administrator
install the reviewed upstream profile for the actual resolved bwrap path. Do not
silently replace an existing profile with a blanket unconfined profile. AppArmor
availability varies with the WSL kernel; if `aa-status` reports that its filesystem
is not mounted, record that limitation and validate namespace isolation separately.
Production relying on AppArmor needs a host/kernel with the LSM and policy active.
Our WSL native tests do not constitute an Ubuntu AppArmor policy-load test.

References: [Ubuntu namespace restrictions](https://discourse.ubuntu.com/t/understanding-apparmor-user-namespace-restriction/58007),
[upstream bubblewrap policy](https://gitlab.com/apparmor/apparmor/-/blob/master/profiles/apparmor/profiles/extras/bwrap-userns-restrict),
[Ubuntu AppArmor administration](https://ubuntu.com/server/docs/how-to/security/apparmor/).
CI loads the distro profile and fails if it is unavailable; it no longer disables
the host restriction through `sysctl`.

## Public development workspace and tools

`public.json` binds approved public bytes, not just filenames:

```json
{"files": {
  "account.cpy": {"purpose":"copybook","sha256":"<64 lowercase hex>"},
  "accounts.bin": {"purpose":"development-records","copybook":"account.cpy","sha256":"<64 lowercase hex>"},
  "job.txt": {"purpose":"development-log","sha256":"<64 lowercase hex>"}
}}
```

Generate the hashes from the public fixture bytes with SHA-256. Copybooks are
UTF-8, records use an explicit supported EBCDIC code page and fixed/RDW framing.
Unbound or changed bytes, absolute/traversal paths, links, devices and oversized
files are refused. Toolkit files are capped at 4 MiB, JARs at 64 MiB. The manifest
is not a way to authorize evaluation disclosures: only reviewed public files belong
in it. `lane_status` reports unqualified if no trusted signed catalogue is bound;
it never infers qualification from one successful submission.

The nine specified tools are available, plus `propose_normalization` for human
drafts. `submit_candidate` accepts a JAR and UUID `request_id`. An identical retry
returns the same attempt; changing bytes under the same UUID is refused. Outputs
are never accepted as evidence. `get_receipt` returns `{ok:true, receipt:{...}}`;
preserve the inner signed envelope byte-for-byte.

`submit_candidate` durably reserves an attempt and returns
`{ok:true, attempt_id:"attempt-…", verdict:"pending"}` before evaluation completes.
Poll `get_verdict` at intervals of at least two seconds until it is no longer
pending, then fetch the signed public receipt. `get_budget` remains responsive.
There is at most one active candidate per task; idempotent retries return the same
attempt. A second new submission while pending is refused without consuming it.
The evaluator is a separate process, so task-private arrival roots cannot race
between HTTP threads or task processes. Service death kills its evaluator;
restart consumes an unfinished reservation as an interrupted attempt, never reruns it.

The limit is now named **attempt_slots**, not build minutes: no builds take place
in this JAR-only judge. A slot admits at most 300 seconds of sandbox execution
across the evaluation runs; the supervisor also limits worker lifetime to 360
seconds including evidence preparation/replay. Slots are never refunded. Old
`build_minutes` configurations are refused rather than silently reinterpreted.

The judge also maintains a signed cumulative ledger under the judge account's
OS-registered home, `.lightyear-verify-ledger/<evaluation_inventory_sha256>/`.
Neither task paths nor the `HOME` environment select this location. Identical
relative filenames and content hashes share the ledger even when copied into
another task folder. Its initial cap is the smaller of the first task's submission
and slot limits. New tasks inherit usage and cannot raise this cap. Cross-process
locks make reservation and budget checking atomic; an interrupted reservation or
operator-voided attempt remains consumed. A task's own smaller limit still applies.
Use one managed judge identity for the protected inventory; backup the ledger and
pin its terminal head. An administrator deleting ledgers, changing input bytes or
creating new judge identities is outside the probing-budget trust boundary.

HTTP requests are capped at 120 per minute per service. Invalid/unauthenticated
traffic and ordinary queries use fixed-cardinality, saturating memory counters.
Only a summary per minute with traffic (plus shutdown) is journaled; the last
unflushed counters can be lost on a crash. Accepted attempts, receipts and operator
decisions still have individual durable signed records. No URLs, tokens, error
messages or candidate text enter the summaries. Flooding a local endpoint can
still deny availability; this is not a public multi-tenant service.

## Control Tower

Register the task scope using the existing Decision Console provisioning flow.
Add this entry to the workspace's `control-tower/campaigns.json`:

```json
{"schema":"tower-campaign-registry/1","campaigns":[{
  "id":"verify-intcalc","scope":"verify-intcalc",
  "adapter":"tower-status-export","read_mode":"write-once-status",
  "producer_profile":"lightyear-verify",
  "export_directory":"/srv/verify-tower/exports",
  "trusted_public_key":"/srv/verify-tower/producer.public.pem",
  "bindings":{"task":"<signed task.json content_sha256>"}
}]}
```

The operator copies only `authority.public.pem` to `producer.public.pem`. Tower
needs read access to exports, not the judge's private root. Exports are signed,
chained and exclusively renamed from temporary files into new sequence numbers.
The generic reader verifies every link and signature, flags gaps and stale active
trials. The Verify profile shows attempts, verdicts, used limits, refusals, exhaustion
and repeated diagnostics. Alerts do not change verdicts.

A timestamp proposal becomes a `verify-normalization` draft in
`work/control-tower/requests/<task-id>/`. Only a human with the normalization role
may decide. Approval alone does **not** change this task's comparator. This release
applies no normalization rules through the service. Any future rule integration
must use the existing CardDemo qualification and verified rule-register workflow
in a separately prepared, bound task. No agent approval tool exists.

A non-completed receipt creates a `verify-attempt-review` Tower request, bound to
the exact public receipt bytes. The task is paused for human review. A human with
`campaign-authorizer` can choose `continue` (allow the next fresh attempt) or
`void` (exclude the failed attempt from interpretation and allow the next fresh
attempt). Neither rewrites a verdict, refunds a slot, reruns a candidate, or voids
a completed receipt. Both are **operator review, not independent attestation**.
The original indeterminate/equipment receipt and decision remain in the audit.

Export the decision proof from Tower and obtain its current trusted journal head
through the operator channel. As the judge account, import it while the service
is running (this CLI does not acquire the service's writer lock):

```sh
lightyear-judge import-decision --data-root /var/lib/lightyear-verify/session \
  --attempt attempt-<32 hex> --proof /private/tower-proof.json \
  --trusted-head <current-Tower-journal-head>
```

The CLI verifies the pinned key, journal, human role, outcome, scope and receipt
binding and writes a new signed import file. The service consumes it before the
next submission; no agent approval tool or HTTP decision endpoint exists. A
stale, mismatched or completed-receipt proof is refused. Import one decision per
receipt. Offline replay re-verifies its complete proof at the imported head.

To propose a cumulative inventory cap increase as the operator:

```sh
lightyear-judge inventory-budget --data-root /var/lib/lightyear-verify/session --new-limit 7
# Review the resulting verify-budget-increase request in Tower, then:
lightyear-judge inventory-budget --data-root /var/lib/lightyear-verify/session --new-limit 7 \
  --proof /private/budget-proof.json --trusted-head <current-Tower-journal-head>
```

The decision binds the inventory, current ledger head/usage/limit and proposed
new limit. If reservations intervene, prepare a fresh request. It cannot increase
a task's sealed local limit. No authority bound on first use means no increases.
The higher cap also increases the disclosure budget and must be reviewed as such.

## Offline evidence

Public receipts can be verified with `lightyear_control_tower.decisions.verify_envelope`
and the separately trusted public key. Full replay is an operator operation:

```sh
lightyear-judge replay --data-root /var/lib/lightyear-verify/session \
  --public-key /trusted/producer.public.pem --journal-head <trusted-terminal-hash>
```

Replay checks the task, every journal signature/link, request identities, budget,
artifact hash, signed inventory reservations, public/private receipt bindings and
Tower decisions, then runs the existing
INTCALC replay and reconstructs the policy-projected result. Task fingerprints bind
all four packages, every `spec/mainframe` asset, the resolved bubblewrap executable
and the full Java runtime including linked configuration. Admission, worker start
and completion, and replay reject changed fingerprints. Runtime updates require
a newly prepared task; they cannot silently change an existing comparator.
Pin the terminal journal head
externally: signatures alone cannot detect deletion of an entire valid suffix.
Archive private evidence locally; publish only reviewed value-free receipts and
status. The receipt explicitly states operator review, not independent attestation.

## Leakage bound

A candidate can read evaluation **inputs** inside `/inputs`. A malicious candidate
can deliberately encode those values by selecting which output fields differ and
which count bands appear. A literal protected-value scan does not detect this
encoding attack. Isolation prevents direct file/network escape; it does not make
the result channel confidential by itself.

Deployment policy:

- For public/synthetic fixtures, field mode is useful for development. For F=29,
  seven kinds and four states (absent/three bands), the conservative business-result
  bound is `B * (log2(9) + 14F)`, about 2,046 bits for five submissions.
- For a customer's own trusted agent, confidential mode is still the default on
  non-public data. The customer must review what information reaches any external
  model provider; ownership alone does not imply authorization to disclose it.
- For a third-party agent on bank/Maintec data, require confidential mode and an
  operator-approved cumulative cap, preferably smaller than five if appropriate.
  With two dataset presence bits, three verdicts and three statuses, a conservative
  business-result bound is `B * log2(36)`: under 26 bits for five attempts. This
  intentionally uses a conservative bound rather than claiming exactly 16 bits.
  It is a bounded deliberate channel, **not zero leakage**. If even this budget is
  unacceptable, do not expose adaptive evaluation to that agent.

Confidential public receipts contain no private-evidence hash or raw verdict hash.
Their signed body consists of known task/artifact identities, generated attempt
identity, deterministic budgets, review label and the closed result. Private
receipts retain full commitments for operator replay. Public responses and Tower
exports refer to the public receipt. Ed25519 signatures are deterministic for that
body and repeated reads do not create new result encodings. Operator-authored
public metadata needs separate disclosure review. Exact runtime stays private;
pending-result polling, completion timing, status-export timestamps and shared-host
side channels are outside the result-alphabet bound. Do not describe this service
as cryptographic privacy or approve actual customer data solely from these tests.

The acceptance leak scan decodes every hidden input and expected output, trims
padding and scans all strings/numbers/keys of at least four characters. Howard's
approved exception excludes exact values already in the documented, hash-bound
public rehearsal fixtures. It does not exempt classes of numbers or keys. An
evaluation-only canary remains protected. Responses, receipts, Tower views,
requests and status exports must contain zero protected-value matches. This
synthetic rehearsal is not a substitute for scanning an actual held-out delivery.

## Harness configuration

The operator must already be serving the judge. All examples inherit the task
token from the agent launch environment; none starts a judge or makes a model call.
Submissions return pending; allow time for JAR transfer and poll for completion.
Harness model smoke tests require
Howard's separate approval and cost recording.

Claude Code ([official MCP setup](https://code.claude.com/docs/en/mcp)):

```sh
claude mcp add --transport stdio lightyear-verify -- \
  /opt/lightyear-verify-venv/bin/lightyear-verify-mcp \
  --workspace /srv/dev --public-manifest /srv/dev/public.json --judge-url http://127.0.0.1:8770
```

Codex `config.toml` ([official MCP settings](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)):

```toml
[mcp_servers.lightyear_verify]
command = "/opt/lightyear-verify-venv/bin/lightyear-verify-mcp"
args = ["--workspace", "/srv/dev", "--public-manifest", "/srv/dev/public.json", "--judge-url", "http://127.0.0.1:8770"]
env_vars = ["LIGHTYEAR_VERIFY_TOKEN"]
tool_timeout_sec = 60
```

Strands Harness `mcp.json`, consumed by `create_harness(mcp_servers="./mcp.json")`
([official configuration](https://strandsagents.com/docs/user-guide/harness/configure/mcp-servers/)):

```json
{"mcpServers":{"lightyear-verify":{
  "command":"/opt/lightyear-verify-venv/bin/lightyear-verify-mcp",
  "args":["--workspace","/srv/dev","--public-manifest","/srv/dev/public.json","--judge-url","http://127.0.0.1:8770"]
}}}
```

Google ADK ([official MCP tools](https://adk.dev/tools-custom/mcp-tools/)):

```python
import os
from mcp import StdioServerParameters
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams

tools = McpToolset(connection_params=StdioConnectionParams(
    server_params=StdioServerParameters(
        command="/opt/lightyear-verify-venv/bin/lightyear-verify-mcp",
        args=["--workspace", "/srv/dev", "--public-manifest", "/srv/dev/public.json",
              "--judge-url", "http://127.0.0.1:8770"],
        env={"LIGHTYEAR_VERIFY_TOKEN": os.environ["LIGHTYEAR_VERIFY_TOKEN"]}),
    timeout=60))
# Attach tools to an agent only when a separately approved model run is intended.
```

Load [the legacy-modernization skill](../../skills/legacy-modernization/SKILL.md)
through the harness's supported Agent Skills directory.

## Zero-model validation

```sh
python -m pip install -e '.[verify]'
mvn -f candidate-java/pom.xml package
PYTHONPATH=src python -m unittest tests.test_verify_mcp.PublicToolkitTests
# Root supervises only; service UID=1000, MCP UID=65534. Use a disposable Linux host.
sudo /opt/lightyear-verify-venv/bin/python tools/run_verify_acceptance.py
```

The supervisor copies public code/fixtures to a temporary protected Linux
installation. Tests use the real MCP SDK client, Java and bubblewrap; no model,
Docker, Maintec data, B05/B06 state or private campaign evidence is needed.
The rounding mutant adds one erroneous cent after truncation; changing only a
rounding mode on these exact-cent fixtures would not expose a defect. The other
faults skip an account and change the posting timestamp's date. All outcomes use
the unchanged business comparator. Optional live harness compatibility is not
claimed by scripted protocol tests.
