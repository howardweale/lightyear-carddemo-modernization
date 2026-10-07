# Mac commands for the Verify graph review

Run these in Terminal on the Mac after this PR is merged. Multipass must already
be installed. This creates a new Ubuntu 24.04 VM on the Mac's native architecture.
It does not mount your Mac home, use Maintec data, run Docker or call a model.
Keep previous VMs and receipts. Do not reuse a VM name after a failed run.

## Create and pin

Use the exact merge commit reported with this change as `VERIFY_REF`. The script
refuses a placeholder. Package downloads require internet access.

```sh
export VERIFY_REF=REPLACE_WITH_REPORTED_MERGE_COMMIT
export VM=lyverify-graph-off-review
/bin/bash <<'BASH'
set -euo pipefail
[[ "$VERIFY_REF" =~ ^[0-9a-f]{40}$ ]] || { echo 'Set the exact reviewed merge SHA first'; exit 1; }
multipass version
multipass launch 24.04 --name "$VM" --cpus 4 --memory 8G --disk 30G
multipass exec "$VM" -- uname -m
multipass exec "$VM" -- sudo apt-get update
multipass exec "$VM" -- sudo apt-get install -y git
multipass exec "$VM" -- git clone https://github.com/howardweale/lightyear-carddemo-modernization.git /home/ubuntu/lightyear-source
multipass exec "$VM" -- git -C /home/ubuntu/lightyear-source checkout --detach "$VERIFY_REF"
ACTUAL=$(multipass exec "$VM" -- git -C /home/ubuntu/lightyear-source rev-parse HEAD)
[[ "$ACTUAL" == "$VERIFY_REF" ]] || { echo 'Revision mismatch'; exit 1; }
multipass exec "$VM" -- sudo bash /home/ubuntu/lightyear-source/tools/verify_smoke/setup.sh
BASH
```

Stop on any failure and preserve the VM/output. Do not disable AppArmor, relax
permissions or reset an attempt ledger to get a pass.

## Run the isolation suite

```sh
multipass exec "$VM" -- sudo /opt/lightyear-verify-venv/bin/python -I /opt/lightyear-verify/tools/verify_smoke/acceptance.py
multipass exec "$VM" -- sudo find /var/lib/lightyear-verify-smoke/platform -name report.json -exec cat '{}' ';'
```

Require `status: passed` with no skipped acceptance tests. This tests actual
separate-user Java/bubblewrap behavior with public/synthetic data, not Maintec
acceptance. Keep failures as evidence. An arm64 pass does not establish x86_64.

## Start the manual judge and check the baseline MCP tools

Only after platform acceptance passes:

```sh
multipass exec "$VM" -- sudo bash /opt/lightyear-verify/tools/verify_smoke/start.sh
multipass exec "$VM" -- sudo python3 -I /opt/lightyear-verify/tools/verify_smoke/agent.py /opt/lightyear-verify-venv/bin/python /opt/lightyear-verify/tools/verify_graph_activation_check.py --workspace /srv/dev --public-manifest /srv/dev/public.json --judge-url http://127.0.0.1:8770 --expect baseline --out /srv/dev/graph-off-protocol-report.json
multipass exec "$VM" -- sudo cat /srv/dev/graph-off-protocol-report.json
```

Expect `status: passed`, `tool_count: 10`, `budget_unchanged: true`, zero model
calls and zero submissions from this protocol check. The launcher gives the token
only to the lyagent process environment; do not print it or copy session keys.
The platform acceptance suite itself executes candidate submissions separately.

Send back the platform report and protocol report, or the first error. Do not
send private logs, tokens or keys. Then complete the [15-step Inspector walkthrough](smoke-runbook.md#a-mcp-inspector-manual-no-model)
in this VM; Claude/Codex live sections remain unapproved. Inspector has no model
calls but does consume the manual task's candidate attempts.

After inspection, stop the judge without deleting its evidence:

```sh
multipass exec "$VM" -- sudo bash /opt/lightyear-verify/tools/verify_smoke/stop.sh
multipass stop "$VM"
```

Graph activation is a later step requiring the separate Verify authority and an
exact projection approval. These commands do not provision an authority or
approve a projection. See the [activation checklist](graph-activation-checklist.md).
