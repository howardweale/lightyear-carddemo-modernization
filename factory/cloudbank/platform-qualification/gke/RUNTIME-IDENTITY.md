# Explicit MS67 application identities

The live application containers reported UID 65532 and primary GID 0 despite the
runtime Dockerfile's `USER 65532:65532`. Kubernetes documents that omitting
`runAsGroup` leaves the container's primary group as root. Set both `runAsUser`
and `runAsGroup` to 65532 explicitly on the main container of each of the eight
CloudBank deployments. Container settings take precedence over pod settings.

This MS67 overlay runs after the request-logging overlay in `deploy.sh`. The MS65
template, acceptance contracts and previously signed MS65/MS66 receipts keep their
original hashes. The overlay uses the existing locked application images. Ollama
already declares both IDs and is outside this change.

The live runner verifies the signed MS64 receipt, image lock and platform profile
against the explicit non-production project, cluster and namespace. It requires
two ready replicas, the existing sandbox, one application container, no init or
ephemeral containers, and `maxUnavailable: 0` / `maxSurge: 1`. All eight services
must pass preflight before the first patch.

Each service changes sequentially. A signed intent is uploaded with a generation
precondition and independently read back before patching. The JSON patch tests
deployment UID and resource version, and changes only the two identity fields.
Unrelated changes since preflight stop the run. The runner verifies two owned
running pods, their locked image digest, readiness, and each container's reported
startup UID/GID before advancing. A final check covers all eight deployments.
Minimized signed evidence is uploaded and read back under `runtime-identity/`.

## Windows execution

Use a controller checkout containing this change and the existing directory with
`image-lock.json`, `ms64-receipt.json` and `platform-profile.json`:

```powershell
& .\factory\cloudbank\platform-qualification\gke\run-runtime-identity.ps1 `
    -InputsRoot 'C:\Users\howar\ms67-image-security-f2fd6f6cb0da460988e06f111d4f5afc'
```

The launcher uses the SDK's bundled Python and existing authenticated account.
It creates a fresh output directory and prints a success marker only after the
run and independent signature/binding verification both exit successfully.
Optional `-Python` and `-OutputRoot` parameters accept explicit alternate paths.
The Python CLI also offers a read-only `preflight` action with a fresh
`--output-root`, and a `render` action for a Kubernetes JSON List.

## Interrupted or failed runs

Keep the printed state URI and local output. The runner stops at the first
failure and retains submitted identity changes. It does not roll back to GID 0
or scale an application down. Once the previous operator process has stopped,
rerun with a fresh output directory. Already-configured services must finish
their rollout and pass identity/readiness checks; they receive no new patch.
An unhealthy or drifted deployment stops the retry before additional mutations.
Do not run another deployment or disruption drill during this rollout.

After a passing run, collect a fresh manifest scan and any operational evidence
that requires current pod/spec identities. Previous signed evidence still describes
its original run; the overlay does not relabel or regenerate that evidence. This
observation qualifies explicit startup UID and primary GID only. It does not
certify supplementary group membership, a distinct-image rollout, all MS67
scenarios, or production readiness. The Trivy registry-rule configuration is
separate; this change does not suppress its findings.

Reference: [Kubernetes security contexts](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/).
