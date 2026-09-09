# Bounded MS67 network enforcement

This runner exercises 65 connection cases twice and verifies both allowed traffic
and enforced denials against the live non-production deployment. It uses the
locked TestRunner Java image, overriding its command with the small reviewed
`network-probe/NetworkProbe.java` class. The shipped class is rebuilt byte for byte
in Windows CI with JDK 17. The operator needs Python, gcloud and kubectl, without
an additional Java installation or image build.

The checks cover all eight applications' database access, rejection of a reachable
database-port listener outside the approved destination, same-namespace application
access, both model replicas, wrong-service and wrong-namespace model ingress,
default-deny ingress and egress, and blocked model egress to the database, a
controlled listener and the deployment's own public HTTPS endpoint. No database
queries, OAuth calls, application writes or model inference requests are sent.

Every denied case must time out twice at connection establishment. Refusal,
read timeout, DNS failure, missing output, stale images, configuration drift and
failed controls cannot pass. All positive connections, including a nonce-bearing
listener and each probe's loopback check, must pass before and after the negative
tests. Literal IPv4 addresses avoid treating a DNS failure as policy enforcement.

## Scope and traffic isolation

The TCP clients run in twelve temporary pods. Nine copy the policy selector labels
of the eight applications and Ollama; their selected live NetworkPolicy UID/spec
sets must match the original pods exactly throughout the drill. The evidence
explicitly identifies these as policy-equivalent probes, not commands executed
inside the application processes. The original two pods per workload must remain
ready, with their locked image and UID/GID 65532 runtime sandbox.

Probe pods have an unsatisfied readiness gate and a ConfigMap controller owner.
They cannot be adopted by existing ReplicaSets. The runner rejects any matching
Service that publishes unready addresses and any serving EndpointSlice entry for
a probe. No probe listens on application port 8080. These checks follow Kubernetes'
[readiness gate behavior](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-readiness)
and [additive NetworkPolicy selection](https://kubernetes.io/docs/concepts/services-networking/network-policies/).

Run this drill by itself. Because its pods share policy labels, they temporarily
match PodDisruptionBudget selectors too; do not run a rollout or disruption drill
at the same time. Each pod has a 30-minute deadline and requests 50m CPU / 96 MiB.
No existing Deployment, Service, NetworkPolicy or Secret is modified. A single
temporary egress policy selects only the uniquely labelled wrong-service probe;
it enables the source side of the model-ingress negative control.

## Windows execution

Use a clean checkout of the merged controller and the same three bound input
files already used for runtime identity and image security:

```powershell
& .\factory\cloudbank\platform-qualification\gke\run-network-enforcement.ps1 `
    -InputsRoot 'C:\Users\howar\ms67-image-security-f2fd6f6cb0da460988e06f111d4f5afc'
```

The launcher prints its private output directory and durable recovery URI before
creation. Its successful final marker is `MS67_NETWORK_VERIFICATION=PASSED` after
independent signature, binding, matrix and cleanup verification. The signed
observation is uploaded and read back under the project's private
`network-enforcement/<run-id>/` prefix. An interrupted or failed run never emits
that marker. Failure details include bounded case IDs and outcomes, not raw logs.

## Recovery

Normal failures attempt cleanup immediately. If `recovery-required` remains,
stop the original process, download the printed signed recovery state, then run:

```powershell
& .\factory\cloudbank\platform-qualification\gke\run-network-enforcement.ps1 `
    -InputsRoot 'C:\Users\howar\ms67-image-security-f2fd6f6cb0da460988e06f111d4f5afc' `
    -RecoveryState 'C:\path\network-enforcement.recovery.json' `
    -OriginalProcessStopped
```

Recovery fetches the latest signed object generation before doing anything. Every
create has a durable intent; lost create replies can be reconciled against exact
run-owned objects. Deletes use Kubernetes UID preconditions. A replacement object
is preserved, as are parent ConfigMaps/namespaces if a child cannot be removed.
The run lease is deleted only after all owned resources are confirmed absent.
Recovery is idempotent and cannot award a passing network qualification result.

The result supplies the bounded network/runtime evidence for MS67. It does not
close MS67 itself or replace load, node/failure-domain disruption, distinct-image
rollout, canary, rollback or final evidence admission. Previously verified MS65
and MS66 receipts are inputs to final admission and are not rerun by this tool.
