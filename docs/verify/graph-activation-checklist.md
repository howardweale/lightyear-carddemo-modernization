# Verify graph activation: zero-model operator checklist

Operator review; not independent attestation. Preparation is not activation.
No Maintec data, Docker, model client, B06 service change or campaign launch.
The review's 15-tool target predates `graph_guidance`: current target is **16**.

## 1. Fresh graph-off Linux acceptance

Use a fresh dedicated Ubuntu 24.04 VM on the Mac; preserve the October 4 VM and
sealed evidence. Choose the exact reviewed **published** revision containing
these fixes. Use the [smoke runbook](smoke-runbook.md#create-and-provision-mac-administrator-terminal)
with `VM=lyverify-graph-off-review` and that revision. Do not reset old ledgers.
Inside the new VM:

```sh
sudo /opt/lightyear-verify-venv/bin/python /opt/lightyear-verify/tools/verify_smoke/acceptance.py
sudo bash /opt/lightyear-verify/tools/verify_smoke/start.sh
sudo python3 -I /opt/lightyear-verify/tools/verify_smoke/agent.py
# Now lyagent with its existing token in the environment:
python /opt/lightyear-verify/tools/verify_graph_activation_check.py \
  --workspace /srv/dev --public-manifest /srv/dev/public.json \
  --judge-url http://127.0.0.1:8770 --expect baseline \
  --out /srv/dev/graph-off-protocol-report.json
```

Require passed platform acceptance with no skips, ten tools and unchanged budget.
Complete the runbook's 15-step Inspector walkthrough and retain its four receipts.
Do not launch Claude/Codex or the A/B. Record architecture, install hash, actual
time and report/receipt hashes. Host Windows tests do not satisfy this gate.
An unrun x86_64 platform remains untested.

## 2. Prepare public INTCALC and request the actual approval

Use separately trusted operator/judge keys and a Verify-specific Tower authority.
Never reuse B06 authority or manufacture Howard's approval. Bind the real new
judge's INTCALC-run1 public fixture inventory. Do not evade cumulative five-attempt
limits by renaming the task; a budget increase needs prior explicit approval.

Run `graph-project` and `graph-leak-check` exactly as in the
[operator guide](graph-context-operator.md#build-and-check), using that evaluation
folder, not a substitute watch set. Preserve failed scans. Protected matches
block release; public overlaps require every exact hash acknowledgment.
The scan writes a pending request to the configured Verify Tower root/scope.

Howard opens **Work queue → Review and decide**, inspects the bound manifest,
source policy, inventory and exceptions, then records approved/rejected with
reason, owner and a review date allowing the entire session. Expiry is 00:00 UTC
at the start of that date. This decision grants no model calls.

Obtain the signed proof and current journal head. Configure independently trusted
public keys, exact projection, lane/mode and inventory in a new Linux judge task,
using [the two-side configuration](graph-context-operator.md#configure-the-two-sides).
Initialize it under lyjudge, preserving the signed task. Do not edit the sealed
smoke config or public manifest. A refusal never authorizes bypassing isolation.
The agent receives only the approved projection, manifest, certificate, public
trust and proof; no detailed leak report, evaluation, keys or source evidence pack.

## 3. Observe the actual toolkit

As the new task's agent, with that task's existing token environment:

```sh
python /opt/lightyear-verify/tools/verify_graph_activation_check.py \
  --workspace /srv/graph-dev --public-manifest /srv/graph-dev/public.json \
  --judge-url http://127.0.0.1:8771 \
  --graph-projection /srv/graph-dev/context \
  --graph-decision /srv/graph-dev/context-proof.json \
  --expect approved --out /srv/graph-dev/activation-approved.json
```

The checker connects through real stdio MCP, reads the loopback judge task and
budget, lists exactly 16 tools, queries one public graph result and verifies an
unchanged budget. No submissions or models. A new report is mandatory; no overwrite.
This proves protocol behavior, not Linux isolation or human independence.

## 4. Expiry and revocation

Observe the same toolkit after real UTC crosses the signed expiry: tools/list
returns the original ten, and graph calls refuse. Do not change the clock or
signed dates. Until observed, label live expiry pending; time-injected regression
tests are separate evidence.

For revocation Howard records rejected for the same exact projection. Preserve
the old proof, obtain a fresh proof/head and have the operator stop the old judge.
A new initialization bound to the rejection must refuse; toolkit startup with
that current rejected proof must expose ten tools. Retain the refusal and proof
hash. An offline old proof cannot discover a later decision automatically.
A baseline-only tool count alone does not establish the reason for refusal.

## Completion record

Record the reviewed revision; CPU/OS/setup hash; graph-off acceptance and Inspector;
projection/manifest/policy/inventory/certificate; Tower scope/key/decision/head;
judge task; active tool count; actual expiry/revocation versus regression tests;
model calls 0; acceptance's actual native candidate submissions; and all pending
steps. Do not call activation complete until the actual authority and Linux gates
are satisfied. No graph comparison before separate commit/model/cost approval.

Copyable [Mac commands](mac-graph-review-commands.md) and the [Verify authority proposal](tower-authority-proposal.md) accompany this checklist. Howard confirmed no Verify authority exists; provisioning remains pending approval.
