# Lightyear Verify: INTCALC through MCP

Lightyear Verify accepts a runnable Java JAR, executes it against operator-held
evaluation inputs, and returns an INTCALC verdict, closed field diagnostics and an
Ed25519 receipt. It reuses the existing z/OS intake, comparator and offline replay.
The toolkit and judge live in separate Python namespaces; this does not select a
new licence. This release supports one operator-owned INTCALC task per judge
process, JAR submission, and Linux isolation. Source-bundle builds and hosted
multi-tenant operation are outside this implementation.

See the [implementation milestone](milestone.md) and [acceptance record](acceptance.md)
for delivered behavior, validation and remaining limits.

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
  "build_minutes": 25,
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
initialization; it must contain no evaluation values. Set `fixture` false only for
an actual held-out delivery. Do not claim rehearsal coverage as Maintec equivalence.

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

Each new accepted submission reserves one attempt and five build/execution minutes
before execution. Unused minutes are not refunded. The default 5 submissions and
25 minutes permit at most five candidate executions. The execution allowance is
shared across all evaluation runs in the attempt. There is no source compilation
in the judge's JAR-only mode. Reads do not consume submissions, but are journaled.
An equipment error yields indeterminate and blocks further submissions.

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

## Offline evidence

Public receipts can be verified with `lightyear_control_tower.decisions.verify_envelope`
and the separately trusted public key. Full replay is an operator operation:

```sh
lightyear-judge replay --data-root /var/lib/lightyear-verify/session \
  --public-key /trusted/producer.public.pem --journal-head <trusted-terminal-hash>
```

Replay checks the task, every journal signature/link, request identities, budget,
artifact hash, receipt bindings and private evidence, then runs the existing
INTCALC replay and reconstructs the closed result. Pin the terminal journal head
externally: signatures alone cannot detect deletion of an entire valid suffix.
Archive private evidence locally; publish only reviewed value-free receipts and
status. The receipt explicitly states operator review, not independent attestation.

## Leakage bound

Let F be the sum of the allowed output-copybook field counts plus one `$record`
sentinel per dataset. For each of seven diagnostic kinds at each allowed field,
there are at most four states: absent, count 1, count 2–10, count >10. There are
three verdicts and three completion statuses. The closed business-result alphabet
is at most `9 * 4^(7F)` per submission, hence at most
`B * (log2(9) + 14F)` bits across B accepted submissions (default B=5). This is a
conservative finite upper bound, not a claim that zero information is disclosed.
Receipts also contain fixed-width commitments and signatures. Conservatively add
2,560 bits per attempt for eight 256-bit fields plus a 512-bit signature; random
attempt IDs, operator-fixed metadata, known artifact hashes and deterministic
budget counters carry no additional hidden-answer semantics. Reads return the
same receipt; no new business evaluation occurs. Exact runtime is not exposed in
the public receipt. Wall-clock response timing and shared-host side channels are
outside this JSON-alphabet bound. Protect the service from untrusted host users
and resource denial of service; do not market this as cryptographic privacy.

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
Allow at least 340 seconds for a submission. Harness model smoke tests require
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
tool_timeout_sec = 360
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
    timeout=360))
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
