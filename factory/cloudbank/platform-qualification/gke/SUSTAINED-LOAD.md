# Bounded MS67 sustained business load

The load gate measures 10 constant k6 virtual users for 300 seconds, at least
1,000 HTTP requests, zero unexpected HTTP or business errors, and overall HTTP
p95 at or below 500 ms. Its signed result can supply the
`bounded-sustained-load-threshold-passed` row. It does not close MS67 by itself.

The runner requires and independently verifies the existing signed MS66 receipt
and its exact PostgreSQL 18-journey observation, bound to the current MS64 receipt,
eight-image lock, project, cluster and namespace. The load measurement is a
declared steady business workload. The intentional restart, dependency-failure
and recovery journeys retain their separate MS66 evidence; they are not counted
as successful requests in a zero-error load window. No acceptance-contract hash
or load threshold changes are required.

## Workload and measurement

Each user receives three fresh marked synthetic accounts with balances 1000,
250 and 5. Users never share accounts or write an unmarked customer. A cycle:

1. Checks unauthenticated rejection and the authenticated customer identity.
2. Reads account balances, transfers one unit forward and back, and checks that
   invalid and insufficient-funds requests leave the state unchanged.
3. Enqueues a check deposit through TestRunner, observes its PENDING Account
   journal from the Checks worker, clears it, and observes DEPOSIT. Replaying both
   commands must be suppressed, with exactly one deposit effect and unchanged
   available balances, matching the declared MS66 settlement semantics.
4. Checks the credit-score range and the bounded authenticated chatbot response.
5. Rechecks balances and every journal effect. Final independent Python reads
   verify the state for all users after k6 has exited.

Cycles start no faster than once per ten seconds per user, retaining 10 virtual
users throughout the five-minute schedule. A 120-second grace period allows
in-flight cycles to finish; interrupted or partial cycles cannot pass. Fewer
than 1,000 requests fails. No warm-up, retries of failed requests, slow responses
or authentication requests are removed from the measured HTTP population.
Expected 401/400/409/422 responses qualify only on their specified negative
business paths. Unexpected status codes, timeouts and invalid response bodies
all fail. Redirects are disabled. Queue polling is bounded and all its HTTP
requests are counted; queue completion time is also reported separately.

The client targets both exact ready pods of each of seven HTTP services through
local-only Kubernetes port forwards. Checks is an asynchronous worker: its
coverage is deposit and clearance effects, not an invented HTTP business API.
All eight deployments and sixteen service pods must retain their locked image
and identity, and the pinned model deployment must remain ready. The measurement
includes the operator-to-GKE tunnel. It does not measure the public ingress load
balancer or establish customer-scale throughput. The observation records this
transport explicitly.

## Run from macOS

Prerequisites: Python 3.11+, Google Cloud CLI with the GKE auth plugin, kubectl,
and **k6 2.2.0** (the native summary API tested in CI). Authenticate as the
authorized operator. From the reviewed controller checkout:

```bash
export LIGHTYEAR_NON_PRODUCTION_ACK=I-AUTHORIZE-MS67-NON-PRODUCTION-MUTATIONS
caffeinate -i bash factory/cloudbank/platform-qualification/gke/run-sustained-load.sh
```

The launcher downloads the exact existing Lightyear MS67 inputs into a fresh
directory under `~/ms67-evidence`. It checks the recorded content hashes, then
the Python controller verifies signatures, all cross-bindings and live identity.
No prerequisite build, image build, deployment or MS66 rerun is performed.
Supply an `INPUTS_ROOT` argument to use another explicitly selected set with
`image-lock.json`, `ms64-receipt.json`, `platform-profile.json`,
`ms66-receipt.json` and `journeys.json`. Project, region, cluster and namespace
use the same `GCP_PROJECT_ID`, `GCP_REGION`, `GKE_CLUSTER_NAME` and
`GKE_NAMESPACE` variables as the other GKE launchers.

The runner prints progress every 20 seconds. Setup and final checks add time to
the five-minute measurement. Keep Terminal open; `caffeinate` prevents idle
sleep while the launcher runs. The final marker is printed only after the signed
observation has been uploaded, independently read back and independently verified:

```text
MS67_LOAD_EVIDENCE_READBACK=VERIFIED
MS67_LOAD_VERIFICATION=PASSED
```

The signed object is stored under the printed URI:
`gs://PROJECT-ms67-evidence/sustained-load/RUN_ID/sustained-load.observation.json`.
Failures save bounded phase, error counters and per-operation latency when
available. A process exit, an in-progress checkpoint, or a failed threshold is
never a passing observation. If interrupted, terminate the original launcher
before starting a fresh run. The only owned infrastructure resources are local
k6/port-forward processes; the runner creates no Kubernetes resources and never
changes replicas, selectors, policies, secrets or image digests. Its at most 30
new marked account fixtures and their bounded journals remain as synthetic data.

Credentials and bearer tokens reach k6 through an anonymous stdin pipe. They
are never saved in a script, argv, environment, output or metric tag. k6 runs with
an empty config and a restricted environment, with debugging, cloud outputs,
usage reporting, trace exports and the control API disabled. The script emits
only aggregate counts and timings; no response, token or chatbot text is kept.

## Verification development

`tests/test_cloudbank_sustained_load.py` checks admission and evidence tampering.
`tools/test_cloudbank_sustained_load.py` runs the actual pinned k6 binary against
a local HTTP application double, including expiring OAuth tokens, body validation,
expected business rejections, real HTTP failures and isolation from inherited
k6 debug/export settings. Linux and macOS CI run these native checks. The optional
`--full-duration` test exercises the full 300-second schedule locally. These are
runner tests and never issue signed GKE qualification evidence.

References: [k6 constant VUs](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-vus/),
[custom summaries](https://grafana.com/docs/k6/latest/results-output/end-of-test/custom-summary/),
[expected HTTP statuses](https://grafana.com/docs/k6/latest/javascript-api/k6-http/expected-statuses/).
