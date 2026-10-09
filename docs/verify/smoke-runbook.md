# Lightyear Verify: Multipass smoke test

This is a **public-fixture rehearsal**, not Maintec acceptance. Setup, Maven/JAR
builds, Inspector and the optional acceptance suite make **zero model calls** and
use **no Docker**. The live Claude Code/Codex section requires Howard's separate
approval **before launching either live client or making any model call**.

Use a dedicated Ubuntu **24.04** VM per manual test session/client. The kit
records `uname -m` as `arm64` (aarch64) or `x86_64`; it does not emulate the other
CPU. Run on an Apple Silicon Mac and an Intel Mac to claim both platform checks.
The [recorded smoke results](smoke-results.md) distinguish operator-reported arm64
walkthrough/client results from outstanding platform checks; x86_64 remains
untested in that record. Host-side kit tests and Java builds are not a VM
isolation test.

## Create and provision (Mac administrator terminal)

Install the official macOS [Multipass package](https://canonical.com/multipass/docs/latest/how-to-guides/install-multipass/).
The VM stays on its native Linux filesystem; do not mount your Mac home, source
tree, credentials or any Maintec directory into it.

Start from a reviewed local checkout containing this kit. Before the kit is
published, the transfer below adds just the kit to the public base checkout;
`setup.json` records the base commit **and every installed source hash**.
After publication, select the reviewed kit commit instead. Do not assume that an
unpublished branch can be cloned from GitHub.

```sh
# macOS: set this to your local checkout containing tools/verify_smoke.
KIT_CHECKOUT="$PWD"
VERIFY_REF=$(git -C "$KIT_CHECKOUT" rev-parse HEAD)
VM=lyverify-inspector
multipass version
multipass launch 24.04 --name "$VM" --cpus 4 --memory 8G --disk 30G
multipass exec "$VM" -- uname -m
multipass exec "$VM" -- sudo apt-get update
multipass exec "$VM" -- sudo apt-get install -y git
multipass exec "$VM" -- git clone https://github.com/howardweale/lightyear-carddemo-modernization.git /home/ubuntu/lightyear-source
multipass exec "$VM" -- git -C /home/ubuntu/lightyear-source checkout --detach "$VERIFY_REF"
# If VERIFY_REF is not public, select its reviewed public base commit above.
# Copy only this kit; never transfer work/, evaluation deliveries or whole home directories.
multipass exec "$VM" -- mkdir -p /home/ubuntu/lightyear-source/tools/verify_smoke
multipass transfer "$KIT_CHECKOUT"/tools/verify_smoke/*.sh "$KIT_CHECKOUT"/tools/verify_smoke/*.py "$VM":/home/ubuntu/lightyear-source/tools/verify_smoke/
multipass exec "$VM" -- sudo bash /home/ubuntu/lightyear-source/tools/verify_smoke/setup.sh
multipass shell "$VM"
```

Inside the VM, setup installs Ubuntu packages, the distribution AppArmor profile,
two locked, non-admin accounts with separate groups, a root-owned reviewed install
at `/opt/lightyear-verify` and its venv at `/opt/lightyear-verify-venv`.
Maven builds as `lyagent`, not root. Only the literal public
`INTCALC-run1-2026-10-05` fixture enters the private evaluation directory.
No option accepts a different evaluation delivery. Run2 is deliberately divergent
and is not a positive manual fixture.

The private config has `fixture: true`, field diagnostics, five submissions and
five attempt slots. `/srv/dev` contains public Java sources, `account.cpy`,
`accounts.bin`, `job.txt`, hash-bound `public.json`, and
`good.jar`, `rounding.jar`, `skipped.jar`, `date.jar`.
`candidates.json` records their actual build hashes. The three mutants use the
same edits as `tests/test_verify_mcp.py`: one extra cent, an omitted account,
and the incorrect transaction date (both timestamp arguments).

Setup runs `apparmor_parser -r /etc/apparmor.d/bwrap-userns-restrict`,
requires active AppArmor, and runs the namespace check as lyjudge. It neither
disables the global user-namespace restriction nor installs an unconfined profile.
An existing profile is not replaced. A missing distro profile, namespace denial,
unexpected account privileges, or changed private fixture fails setup.
See [deployment rationale](README.md#apparmor-on-ubuntu-2404-and-wsl).

The three separation checks run before init and again **after the real key exists**:

```sh
sudo -u lyagent test ! -r /var/lib/lightyear-verify/session/authority.pem
sudo -u lyagent test ! -r /var/lib/lightyear-verify/evaluation
sudo -u lyagent test ! -w /opt/lightyear-verify/src/lightyear_judge/service.py
```

All must exit 0. Before init the first check is explicitly recorded as key absent;
only the after-init check proves denial of an existing key. Trusted-installation
validation also checks the Java runtime, venv and linked paths.

Rerunning setup from identical inputs verifies without reinstalling packages,
rebuilding artifacts, initializing another task or resetting the inventory ledger.
A different revision/config/evaluation is refused. Do not upgrade Java, bwrap or
Python packages during a sealed session. If initial setup fails, fix the reported
environment problem and rerun; preserve its logs. Partial session initialization
is **never** deleted automatically. Do not use this kit on a general-purpose VM.

## Optional zero-model platform check

Run this before starting the manual service, preferably in a separate acceptance
VM. Allow roughly 10–20 minutes including package downloads/builds; actual native
time is recorded, not assumed.

```sh
sudo /opt/lightyear-verify-venv/bin/python -I /opt/lightyear-verify/tools/verify_smoke/acceptance.py
```

This invokes the existing `tools/run_verify_acceptance.py` supervisor. It uses
UID 1000 and UID 65534 in temporary protected installations, independently of the
manual lyjudge/lyagent service. In Multipass UID 1000 normally belongs to ubuntu;
run only in this dedicated fixture VM. The suite adds its synthetic canary in
scratch, tests real MCP/Java/bwrap, mutants, hostile-candidate isolation, leakage,
budgets and offline replay; it does not insert that canary into the manual fixture.

The result is saved under
`/var/lib/lightyear-verify-smoke/platform/<UTC>-<arm64-or-x86_64>/report.json`,
with a private log, setup/log hashes, elapsed time and exit code. An absent native
acceptance marker or any skipped tests produces **failed**, even if unittest
exits 0. Reports are never overwritten. Inspect with sudo; copy only the reviewed
report for sharing. This is a platform check, not a live-harness compatibility or
Maintec equivalence claim. A failure is evidence to investigate, not permission
to fall back to unsandboxed Java.

## Start, connect and stop

```sh
# VM administrator:
sudo bash /opt/lightyear-verify/tools/verify_smoke/start.sh
sudo journalctl -u lightyear-verify-smoke --no-pager -n 20
sudo tail -n 5 /var/lib/lightyear-verify/service.log
sudo python3 -I /opt/lightyear-verify/tools/verify_smoke/agent.py
# You are now lyagent in /srv/dev:
id
```

First start prints an initialized status, separation checks and readiness.
The private service log contains
`{"status": "ready", "port": 8770, "task": "verify-intcalc"}`.
The systemd unit runs as lyjudge, survives terminal disconnection, has no automatic
restart and binds the judge only to loopback. Start is idempotent and its readiness
probe only reads the budget.

The administrator's launcher reads the existing token, drops supplementary
groups/GID/UID and execs lyagent with a clean environment. The token is not printed,
copied to an agent file or put in argv. Only that agent process tree receives
`LIGHTYEAR_VERIFY_TOKEN`; a separate `sudo -u lyagent` shell does not inherit it.
Never run `env`, `printenv`, shell tracing or an environment dump into a transcript.
The operator is trusted; lyagent receives no sudo privilege. Neither a model nor
Inspector gets the signing key.

To stop, exit the agent shell and run as the VM administrator:

```sh
sudo bash /opt/lightyear-verify/tools/verify_smoke/stop.sh
```

Stop only after pending attempts finish unless deliberately testing interruption.
Stopping while pending can consume an attempt and require operator review.
Receipts, keys and cumulative budgets survive stop/start. No reset command exists.

## (a) Scripted walkthrough: default, no model

Use **only a fresh VM/task with five unused cumulative attempts**. This check
consumes all five. Never reset a ledger or rename a task to evade its limit.
The graph-off VM recorded on October 9 is spent and must be preserved. Use a
separate fresh walkthrough VM, for example `lyverify-walkthrough-r1`; reserve
`lyverify-graph-on-r1` for the separately reviewed graph activation task.

After the reviewed walkthrough revision is published, use that exact commit in
the provisioning commands above, then start the judge. Do not replace code or
configuration in an already sealed installation. From the Mac:

```sh
VM=lyverify-walkthrough-r1
multipass exec "$VM" -- sudo bash /opt/lightyear-verify/tools/verify_smoke/start.sh
multipass exec "$VM" -- sudo python3 -I /opt/lightyear-verify/tools/verify_smoke/agent.py /opt/lightyear-verify-venv/bin/python /opt/lightyear-verify/tools/verify_smoke/walkthrough.py
multipass exec "$VM" -- sudo -u lyagent cat /srv/dev/walkthrough-report.json
```

The client uses the same stdio server and token environment as Inspector, runs
as lyagent, and never calls a model. It generates UUIDv4 IDs, deliberately reuses
the first ID once, polls at intervals of at least two seconds, and stops at the
first mismatch or the 360-second attempt deadline. A timeout never causes a
resubmission. Do not run the manual fallback afterward on that consumed task.

`walkthrough-report.json` is exclusively created before connection: an existing
file refuses without submitting. It preserves completed steps and attempted
submission IDs on failure; investigate and retain it. Each public receipt is
retained as exact base64 bytes with its byte SHA-256, distinct from the signed
body's `content_sha256`. No parse/re-serialization supplies that byte hash.
No token, private key or raw evaluation data belongs in the report.

The fixture-only judge response now advertises `smoke_evidence` in `get_task`
and includes exact public receipt bytes, the repeated-diagnostic alert and the
observed journal head with `get_receipt`. Old judges refuse the walkthrough at
step 1 before consuming attempts. Non-fixture receipt responses are unchanged.
The existing ten MCP tools and input schemas are unchanged.

The report's final head is the head observed after step 15, not a claim that
shutdown or subsequent ingress cannot append events. An administrator must stop
the judge and pin the actual sealed head for the independent offline replay
below. A successful client check is not signature replay or native isolation
acceptance. Host fake-judge tests are not a Linux walkthrough result.

<a id="a-mcp-inspector-manual-no-model"></a>

### MCP Inspector: manual fallback, no model

Install Node 24 inside the lyagent shell from the
[official Linux binary distribution](https://nodejs.org/en/download).
This selects the native architecture and verifies the downloaded archive against
the official SHA-256 list. Installation makes no model call.

```sh
case "$(uname -m)" in aarch64) node_arch=arm64;; x86_64) node_arch=x64;; *) exit 1;; esac
mkdir -p "$HOME/.local/node-download" "$HOME/.local/bin"
cd "$HOME/.local/node-download"
curl -fsSLO https://nodejs.org/dist/latest-v24.x/SHASUMS256.txt
node_archive=$(awk -v suffix="-linux-$node_arch.tar.xz" '$2 ~ suffix "$" {print $2}' SHASUMS256.txt)
test -n "$node_archive"
curl -fsSLO "https://nodejs.org/dist/latest-v24.x/$node_archive"
grep "  $node_archive\$" SHASUMS256.txt | sha256sum -c -
tar -xJf "$node_archive" -C "$HOME/.local"
node_dir="$HOME/.local/${node_archive%.tar.xz}"
ln -sfn "$node_dir/bin/node" "$HOME/.local/bin/node"
ln -sfn "$node_dir/bin/npm" "$HOME/.local/bin/npm"
ln -sfn "$node_dir/bin/npx" "$HOME/.local/bin/npx"
node --version
cd /srv/dev
mkdir -p inspector
cd inspector
npm init -y
npm install --save-exact @modelcontextprotocol/inspector@2
npm list @modelcontextprotocol/inspector
cd /srv/dev
python3 -I /opt/lightyear-verify/tools/verify_smoke/inspector.py
```

This runbook targets [Inspector v2](https://github.com/modelcontextprotocol/inspector/blob/main/clients/launcher/README.md);
record its exact resolved version and lockfile hash. The helper uses a read-only
session config in an anonymous Linux memory file, explicitly forwarding the token
as the MCP child environment. No token is written to disk or argv. Inspector's
secret store is memory-only. Do not export connection configurations or capture
the token-bearing settings pane. The judge's HTTP endpoint is **not** an MCP HTTP
endpoint; connect through the supplied stdio command.

For the Mac browser, tunnel the loopback UI through SSH, keeping authentication
enabled. In a second **Mac** terminal, add a dedicated SSH public key to the VM
administrator via Multipass (no private key is transferred):

```sh
VM=lyverify-inspector
ssh-keygen -t ed25519 -f "$HOME/.ssh/lyverify-smoke" -N ''
multipass transfer "$HOME/.ssh/lyverify-smoke.pub" "$VM":/home/ubuntu/lyverify-smoke.pub
multipass exec "$VM" -- bash -c 'mkdir -p ~/.ssh; chmod 700 ~/.ssh; cat ~/lyverify-smoke.pub >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys'
VM_IP=$(multipass info "$VM" --format json | python3 -c 'import json,sys; x=json.load(sys.stdin); print(next(iter(x["info"].values()))["ipv4"][0])')
ssh -i "$HOME/.ssh/lyverify-smoke" -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:6274:127.0.0.1:6274 ubuntu@"$VM_IP"
```

Open the authenticated localhost URL printed by Inspector in the Mac browser.
Keep its API token private too. This test uses tools only; Inspector's Apps
sandbox ports are unnecessary. Do not bind Inspector or the judge to 0.0.0.0.
[Inspector network and secret-store settings](https://github.com/modelcontextprotocol/inspector/blob/main/docs/environment-variables.md).

Select lightyear-verify, connect, and list tools. Expect **10** tools: the nine
specified Verify tools plus `propose_normalization`. Use the Tools form (ordinary
calls, not MCP sampling). Save the tool results, excluding connection secrets.

| Step | Tool and input | Expected result |
| --- | --- | --- |
| 1 | `get_task {}`, `get_budget {}` | CBACT04C → Java; public shapes; initially 5 submissions and 5 attempt slots |
| 2 | `describe_copybook {"path":"account.cpy"}` | Public layout; record length 300 |
| 3 | `decode_records {"path":"accounts.bin","copybook":"account.cpy","codec":"cp037","framing":"fixed"}` | Public development records only |
| 4 | `read_job_log {"path":"job.txt"}` | Parsed public rehearsal log |
| 5 | `lane_status {}` | Unqualified; no fabricated lane qualification |
| 6 | `decode_records {"path":"../private","copybook":"account.cpy"}` | Refused; budget unchanged |
| 7 | `submit_candidate {"path":"good.jar","request_id":"<fresh UUID>"}` | `pending` and a new attempt ID |
| 8 | Repeat step 7 with **identical** UUID and JAR | Same attempt; no second charge |
| 9 | `get_verdict {"attempt_id":"<returned ID>"}` every ≥2 seconds | Eventually `equivalent`; empty diagnostics |
| 10 | `get_receipt {"attempt_id":"<returned ID>"}` | Signed public envelope, completed status, operator-review label |
| 11 | Submit `rounding.jar`, fresh UUID; poll and receipt | `divergent`; diagnostic field ending TRAN-AMT |
| 12 | Submit `skipped.jar`, fresh UUID; poll and receipt | `divergent`; missing-record for STEP15/ACCTFILE |
| 13 | Submit `date.jar`, fresh UUID; poll and receipt | `divergent`; TRAN-PROC-TS diagnostic |
| 14 | Submit `date.jar` again with another fresh UUID; poll and receipt | Same diagnostic, fifth consumed attempt; repeated-diagnostic alert |
| 15 | Submit any JAR with a sixth UUID | Budget refusal; no new execution; `get_budget` shows zero left |

Generate each UUID with `python3 -c 'import uuid; print(uuid.uuid4())'` in another
lyagent terminal; UUIDs are not secrets. Wait for each terminal result before
starting another. Save the **inner** `receipt` object byte-for-byte; do not
re-serialize it for signature checking. A polling limit of 360 seconds is a
troubleshooting deadline, not permission to resubmit or reset state. An
indeterminate/equipment outcome is a failed smoke check: retain evidence and stop.
This kit does not configure a Tower authority or bypass a review pause.

## (b) Live Claude Code and Codex — approval required

**STOP: obtain Howard's explicit approval of client, model, maximum spend and
allowed prompts/tool outputs before proceeding with this section.** Setup does
not authorize these calls. Login itself is not a model test, but this runbook gates
the whole live-client section to avoid accidental requests. No automated script
launches either harness.

Use a new dedicated VM/session for each client so both have five unused attempts.
Do not erase the cumulative ledger to obtain more submissions. The exact same
single prompt below is used for each client; this tests MCP orchestration, not
the model's ability to implement INTCALC.

After approval, provision/start the new VM, enter its `agent.py` shell, and install
only the approved client **as lyagent**. Do not install or log in as root/lyjudge.

Claude Code ([installation](https://code.claude.com/docs/en/setup),
[login](https://code.claude.com/docs/en/authentication),
[MCP configuration](https://code.claude.com/docs/en/mcp)):

```sh
curl -fsSL https://claude.ai/install.sh -o "$HOME/claude-install.sh"
# Review the downloaded installer before executing.
bash "$HOME/claude-install.sh" stable
claude --version
claude mcp add --transport stdio lightyear-verify -- \
  /opt/lightyear-verify-venv/bin/lightyear-verify-mcp \
  --workspace /srv/dev --public-manifest /srv/dev/public.json --judge-url http://127.0.0.1:8770
claude mcp list
claude
```

Follow the login prompt (or `/login`), open its link in the Mac browser and return
the requested authorization code. Check `/mcp` and select the approved model.
If the installed version does not inherit the token, stop; do not paste it into
`--env`, screenshots or the model prompt.

### Codex installation and VM sign-in

Use the official npm package, as shown in OpenAI's
[npm installation example](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex#quickstart-using-goals).
Inside the approved Codex VM's **lyagent** shell, install Node using the Node-only
steps above (through `node --version`; Inspector is not needed), then:

```sh
export PATH="$HOME/.local/bin:$PATH"
npm install --global --prefix "$HOME/.local" @openai/codex
hash -r
command -v codex
codex --version
npm list --global --prefix "$HOME/.local" @openai/codex
mkdir -p "$HOME/.codex"
# New dedicated identity only: do not overwrite an existing configuration.
test ! -e "$HOME/.codex/config.toml"
cp /srv/dev/codex-mcp.toml "$HOME/.codex/config.toml"
chmod 600 "$HOME/.codex/config.toml"
```

Record the resolved package and CLI versions. The former install-script build
failed sign-in with `invalid_client` in the [reported test](smoke-results.md);
npm version 0.160.0 was installed, but its device login was not completed.

For browser sign-in from the VM, forward the callback to the Mac. In a separate
**Mac terminal**, provision the dedicated SSH public key on this VM and leave the
tunnel running:

```sh
VM=lyverify-codex
test -f "$HOME/.ssh/lyverify-smoke" || ssh-keygen -t ed25519 -f "$HOME/.ssh/lyverify-smoke" -N ''
multipass transfer "$HOME/.ssh/lyverify-smoke.pub" "$VM":/home/ubuntu/lyverify-smoke.pub
multipass exec "$VM" -- bash -c 'mkdir -p ~/.ssh; chmod 700 ~/.ssh; cat ~/lyverify-smoke.pub >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys'
VM_IP=$(multipass info "$VM" --format json | python3 -c 'import json,sys; x=json.load(sys.stdin); print(next(iter(x["info"].values()))["ipv4"][0])')
ssh -i "$HOME/.ssh/lyverify-smoke" -N -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:1455:localhost:1455 ubuntu@"$VM_IP"
```

Back in the VM's **lyagent** shell:

```sh
codex login
# Open the printed sign-in URL in the Mac browser and complete sign-in.
codex login status
```

The browser's `localhost:1455` callback reaches the VM through SSH. Keep that
port free on the Mac; stop if the tunnel fails. Close the tunnel after login
succeeds. This adapts OpenAI's documented
[localhost callback forwarding](https://learn.chatgpt.com/docs/auth#fallback-forward-the-localhost-callback-over-ssh).
Device login (`codex login --device-auth`) remains an alternative where enabled;
it was not completed in the reported test. Keep auth files and login URLs out of
results. Do not copy credentials between identities.

After successful sign-in, and only with live-test approval:

```sh
codex mcp list
codex
```

Confirm the approved model and connected server before sending the task. Keep
normal tool approvals enabled. See the
[MCP environment allowlist](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
for passing the existing Verify token to the MCP child.

**Exact single task prompt for either client:**

> Perform one public-fixture Lightyear Verify MCP smoke test in /srv/dev. First call get_task, get_budget, describe_copybook on account.cpy, decode_records on accounts.bin with account.cpy/cp037/fixed, read_job_log on job.txt, and lane_status. Then submit the existing good.jar, rounding.jar, skipped.jar and date.jar in that order, with one fresh UUID per artifact. Do not modify or rebuild them. After each submit, poll get_verdict no more often than every two seconds until terminal, then fetch get_receipt and save the inner signed receipt unchanged. Stop on an indeterminate/equipment outcome or a refusal. Use at most four submissions; do not request budget increases, normalization or operator decisions. Never read private judge paths, credentials, tokens, process environments or raw evaluation logs. Do not use another model or external service. Report actual attempts, verdicts, closed diagnostics, receipt identities and tool-call counts; distinguish measured results from expectations. This is a public-fixture compatibility test, not Maintec equivalence or independent attestation.

Pass checklist for each approved live client:

- Runs as lyagent, ten MCP tools discovered, public reads succeed.
- Four submissions return pending then equivalent/divergent/divergent/divergent;
  expected diagnostic fields/kinds match the Inspector table.
- Four completed public receipts retained unchanged; one attempt remains.
- No private file access, token disclosure, model switching, budget changes or
  unapproved external calls. Record actual tool calls including polls and errors.
- Record client/model versions, token use and cost from the client's usage report
  or billing. If subscription pricing gives no per-run cost, write **unavailable**;
  do not invent a dollar estimate or equate attempt slots to build minutes.

## Results, replay and disposal

Use one record per VM/client, including failures:

```text
Date/operator:
Review: operator review; not independent attestation
Mac CPU / macOS / Multipass version / VM name:
Ubuntu / uname -m / kernel / architecture (arm64 or x86_64):
Base commit / setup.json SHA-256 / candidates.json SHA-256:
AppArmor profile hash and loaded status:
bwrap check / three after-init separation checks:
Platform acceptance report path/hash/status (or not run):
Client/version: Inspector | Claude Code | Codex
Approval reference for live model calls (Inspector: not applicable):
Model and reasoning setting (Inspector: none):
Start/end UTC / wall time:
Attempts: UUID → attempt ID → artifact hash → verdict → receipt hash
Diagnostics:
Tool calls: names/counts, poll count, refusals/errors
Tokens: input / cached input / output / unavailable
Cost/currency and source: actual | unavailable (Inspector model cost: $0)
Budget before/after:
Offline replay: trusted journal head, result, record location
Limitations/failures:
```

For an operator offline replay, stop after all terminal receipts, retain
`session/authority.public.pem` and pin the final signed journal head in your local
results. Then, as administrator, run (replace the head with the recorded value):

```sh
sudo -u lyjudge /opt/lightyear-verify-venv/bin/lightyear-judge replay \
  --data-root /var/lib/lightyear-verify/session \
  --public-key /var/lib/lightyear-verify/session/authority.public.pem \
  --journal-head '<recorded terminal content_sha256>'
```

Preserve reviewed results before deleting a fixture VM. Do not copy private keys,
tokens, raw private logs or the entire session into the repository. Unset the
task token by exiting the agent shell; stop Inspector with Ctrl-C and close its
browser session/SSH tunnel. Delete only the explicitly named dedicated VM:

```sh
# macOS
multipass stop lyverify-inspector
multipass delete --purge lyverify-inspector
```

Repeat using separate names for the approved Claude/Codex VMs. Deletion is
intentional disposal of a public-fixture test machine, not an evaluation budget
reset on protected data.
