# Local agent workflow: CLI and MCP

The first complete agent workflow is **`cloudbank-retained-v1`**. An external
project can discover its capabilities, review a plan, start the existing headless
engine, disconnect, reconnect, inspect progress, verify the journal and export
evidence. The terminal run also appears in Control Tower's existing history.

This adapter verifies CloudBank's retained evidence and, when separately
authorized, applies its existing bounded ledger projection. It does **not** run
new Oracle/AlloyDB tests, start cloud resources, convert an arbitrary customer
application, or grant approval. Existing native campaign receipts stay unchanged.
The next adapters can reuse this service contract without changing MCP clients.

## Install and bind a project

Use Python 3.11 or newer and an evidence checkout matching the installed code.
From the Lightyear checkout, in PowerShell:

```powershell
py -3.12 -m venv .venv
& .venv/Scripts/python.exe -m pip install -e ".[agent]"

# Use an existing customer repository. The manifest is created exclusively;
# init refuses to replace an existing file and creates no human authorization.
& .venv/Scripts/lightyear-agent.exe init `
  --project C:/projects/customer/lightyear.project.json `
  --project-id customer-pilot --evidence-root $PWD
```

On Linux/macOS use `python3 -m venv .venv`, `.venv/bin/python` and
`.venv/bin/lightyear-agent`. The optional `agent` dependency pins the official
MCP Python SDK to the tested version; the base engine does not require MCP.

The manifest has exactly four fields:

```json
{
  "schema_version": "1.0",
  "project_id": "customer-pilot",
  "workflow": "cloudbank-retained-v1",
  "evidence_root": "../lightyear-carddemo-modernization"
}
```

`evidence_root` is absolute or relative to the manifest. The external project
owns this configuration; the retained adapter reads the configured evidence
checkout, not the external project's application code. Keep credentials out of
the manifest. Unknown fields, workflows, symbolic links and junctions are rejected.
The MCP process is bound to one manifest at startup; tools cannot switch projects.
Changing the manifest requires restarting the server and reviewing a new plan.

Project state is isolated under the evidence checkout's
`work/agent-workflows/<project-identity>/`. The identity includes the manifest's
location and contents. Moving it creates a different project identity. Preserve
the original manifest and state to revisit historical runs.

For an immediate local example, use the included
[`examples/local-agent/lightyear.project.json`](../examples/local-agent/lightyear.project.json).

## One workflow from the command line

On **Windows**, first start the project worker in a separate terminal and leave
it running while jobs execute (stop it with Ctrl+C when finished):

```powershell
lightyear-agent worker --project C:/projects/customer/lightyear.project.json
```

Start this worker independently of the MCP host. Windows MCP clients may place
their server and its children in a kill-on-close job; a new process group alone
does not survive that job closing. The independent worker owns execution, while
MCP submits durable local requests. If the worker is absent, start returns
`worker-required` before accepting a new run. Restart a stopped worker and use
`resume` for a run interrupted during execution. Queued requests remain durable.
Linux/macOS use a detached worker per run and do not require this separate step.

Commands emit one JSON response on stdout. Diagnostics and the convenience
runner's run ID go to stderr. These examples use an activated environment:

```powershell
$project = 'C:/projects/customer/lightyear.project.json'
lightyear-agent capabilities --project $project
$plan = lightyear-agent plan --project $project | ConvertFrom-Json
if (-not $plan.ok) { throw $plan.error.message }

# Review scope, limits and human_decision before starting.
$requestId = [guid]::NewGuid().ToString()
$run = lightyear-agent start --project $project `
  --plan-sha256 $plan.plan_sha256 --request-id $requestId | ConvertFrom-Json
if (-not $run.ok) { throw $run.error.message }

lightyear-agent status --project $project --run-id $run.run_id
lightyear-agent events --project $project --run-id $run.run_id --after 0 --limit 10
lightyear-agent verify --project $project --run-id $run.run_id
# Once terminal, including a human-decision halt:
lightyear-agent export --project $project --run-id $run.run_id
```

The shell may report exit 4 for a successfully accepted asynchronous start. It
means the run is pending, not that dispatch should be repeated with a new ID.
Reuse the **same request ID and plan digest** if a response is lost. The durable
index atomically reserves the request and permits only its first dispatch.
Reusing it for another plan returns `request-conflict`.

`lightyear-agent run --project <manifest> --request-id <UUID>` is a CI convenience:
it prepares and starts the local-policy plan, then waits up to 360 seconds. Set
`--wait-seconds` between 0 and 600. A timeout leaves the detached run intact.
Persist the UUID in the calling workflow so a retry can find the same run.

| Exit | Meaning | CI treatment |
|---:|---|---|
| 0 | Operation succeeded; for run/verify, workflow completed | An export success alone is not a workflow pass |
| 1 | Comparison or execution failed | Fail the check and retain evidence |
| 2 | Invalid configuration, input, plan or evidence | Fix the reported error code; do not infer a result |
| 3 | Verified run requires a human decision | Route to review; keep acceptance incomplete |
| 4 | Accepted, queued, running, uncertain dispatch or resume requested | Poll the same run; do not treat as failure or completion |

Every tool response has `schema_version`, `project_id`, `workflow`, `ok` and
`status`. An unsuccessful operation has `error.code` and `error.message`.
`verify` additionally distinguishes `verified` from `workflow_completed`:
a valid journal can prove that work stopped, rather than that it passed.
This is hash-chain and semantic replay verification, not a newly signed or
independently attested run. Original retained evidence keeps its own provenance.

## Connect a local MCP client

The server supports **stdio only** and opens no network listener:

```powershell
lightyear-mcp --project C:/projects/customer/lightyear.project.json
```

On Windows, keep the independently started project worker running as described above.

An MCP host launches that command and speaks the protocol on its stdin/stdout.
Do not type normal CLI commands into those streams. A host using an
`mcpServers` configuration can use this shape (substitute real absolute paths):

```json
{
  "mcpServers": {
    "lightyear": {
      "command": "C:/tools/lightyear/.venv/Scripts/lightyear-mcp.exe",
      "args": ["--project", "C:/projects/customer/lightyear.project.json"]
    }
  }
}
```

Clients with a different configuration format need the same executable and
argument array. There is no port, cloud login or operator credential to supply.
The official SDK provides tool discovery, input schemas and structured output.
See the [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/) for protocol
and client details.

| Tool | Purpose |
|---|---|
| `capabilities` | Discover supported operations and their bounded scope |
| `plan` | Get the current digest, budgets and human-decision requirements |
| `start(plan_sha256, request_id)` | Start under existing local execution policy |
| `status(run_id)` | Read replay-verified progress and the Tower history identity |
| `events(run_id, after, limit)` | Read at most 25 events; continue with `next_cursor` |
| `verify(run_id)` | Verify the journal independently of the cached dispatch state |
| `export(run_id)` | Exclusively publish a terminal bundle; return its path and byte hash |
| `resume(run_id)` | Recover interrupted work under the unchanged plan |

Read-only resources provide the full plan at `lightyear://plan/current`, the
first event page at `lightyear://runs/{run_id}/events`, and terminal evidence at
`lightyear://runs/{run_id}/evidence`. Subsequent pages use the events tool.
Reading a resource never launches a worker or writes an export. Tool clients
must check `ok` and `status`, even when the MCP protocol call itself succeeded.

## Disconnects, decisions and Control Tower

The engine process is detached from the MCP server and CLI client. Losing the
client connection does not cancel it. The existing execution policy still bounds
run time, action count and worker timeouts. On Windows, the separately started
worker owns queued execution; the MCP client never owns its lifetime.
The adapter neither forwards cloud credentials nor accepts
caller-supplied commands, SQL or file paths in tool arguments.

`running-or-interrupted` deliberately does not assert that a process is alive.
After a machine interruption or uncertain dispatch, call `resume` on the same
ID. A cross-platform OS lease prevents concurrent workers, and the engine
resumes its journal without repeating committed actions. Changed inputs or
policy require a new reviewed plan. Terminal runs remain terminal.

**Hypothetical review:** an agent verifies all eight services, then reaches the
existing value-conservation decision. With no valid approval it records 19
actions and returns `human-decision-required`, exit 3. A reviewer separately
signs the exact terms in Control Tower. The agent plans a **new run with a new
request ID**. If that approval is still valid when consumed, the engine can
complete the twentieth action. The original halt remains in history. The MCP
server exposes no approve, credential-provisioning or verdict-override tool.
Follow the existing [human-decision provisioning runbook](control-tower-execution.md#provision-and-review-the-sixth-action).

Serve Control Tower from the **same evidence checkout**. When a run terminates,
refresh its context and select **CloudBank → Retained estate evidence** and the
history ID returned in `status.tower.run_id`. The Tower, CLI and MCP replay the
same journal. In this first adapter, active progress is available through CLI/MCP;
the existing Tower history selector lists the run after terminal publication.

## Verification and scope limits

```powershell
python -m unittest tests.test_agent_workflow tests.test_agent_mcp -v
```

CI runs the workflow and real stdio integration tests on Windows and Linux.
The integration test launches a real engine from an external project (using
an independently started worker on Windows),
disconnects MCP, reconnects, reads the export resource and checks the same
journal hash through the CLI. Unit tests cover exact-plan binding, concurrent
duplicate requests, interruption recovery, tamper rejection, project isolation,
bounded pagination and separately signed synthetic test approvals.

This local interface is not a sandbox against a malicious process with the same
OS account. Use reviewed project configuration and a trusted evidence checkout.
Remote transport, arbitrary customer adapters, fresh paired-database execution,
remote identities, cancellation and customer production acceptance are future
capabilities, not claims made by this workflow.
