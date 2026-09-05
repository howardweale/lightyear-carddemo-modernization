# MS #67 GKE live qualification runbook

This runbook creates real, chargeable, non-production effects. Use a dedicated project labelled
`environment=non-production`. Keep the evidence key and every secret outside the repository. The
scripts use an IAM-authenticated GKE DNS endpoint and refuse mutable base-image tags, production-labelled projects,
missing chart versions, and missing mutation acknowledgements.

## 1. Account and DNS

- Confirm billing, quota, and the exact project with `gcloud config get-value project`.
- Confirm the active principal with `gcloud auth list`.
- Copy `qualification.env.example` outside the repository and source it.
- Run `bootstrap.sh`. Delegate the printed Cloud DNS name servers from the parent DNS zone.
- Add one JSON secret version to each of the eight Secret Manager containers. Use only synthetic
  credentials and configuration. Do not pipe values through shell command-line arguments.
- If the operator-held MS #54 through MS #64 execution receipts are unavailable, create one
  Secret Manager value named `cloudbank-ms67-evidence-key` and run
  `submit-prerequisite-chain.sh SIGNER`. The asynchronous Cloud Build job executes the complete
  signed dependency chain and exports only minimized receipts to the private evidence bucket.
  Do not substitute committed readiness receipts for these execution receipts.

## 2. Build and deploy

- Produce signed MS #65 and MS #66 execution receipts with the same operator-held evidence key.
- Materialize the exact MS #64 eight-service target into a fresh directory.
- Run `render-site-inputs.sh`, then `build-push-images.sh`, then `deploy.sh`.
- Sign every digest with the configured Cloud KMS key and attach a content-addressed provenance
  predicate. Verify both before continuing. Record only result hashes and aggregate counts.
- Confirm all 16 service Pods are ready and every running image ID equals the image lock.

The deployment supplies the same PostgreSQL dialect override used by the native qualification
lane, above the imported Oracle defaults. Account and Transfer use the `cloudbank-oauth` profile;
Authorization disables sample human-user
bootstrapping for this client-credentials lane. OAuth client secrets and the persistent signing key
remain in External Secrets; this setting does not provision or qualify customer human-user login.

Checks and Transfer explicitly set `CLOUDBANK_SECURITY_SERVICE_TOKEN_ENABLED=true` in their
deployment environment. The imported common configuration otherwise defaults it to false, which
prevents Checks' `AccountService` from receiving its required `CloudBankServiceTokenProvider`.
The Checks deployment context regression runs the actual configuration import and verifies both
the missing-provider failure and successful startup with this override. It isolates database I/O
and scheduling; it does not establish live token exchange or queue processing. This deployment
correction can reuse the existing signed images and MS64 receipt.

Kubernetes health probes remain HTTP liveness/readiness checks on the application port. If probes
return 401, rebuild from the corrected MS64 target rather than changing probes to TCP or exposing
all actuator endpoints. Refresh the MS64 receipt and image lock after application patch changes.

## 3. TLS, secrets, and telemetry

The GKE add-ons include `cloudbank-acme-http01-ingress`. MS65's namespace-wide default deny
also selects cert-manager's temporary HTTP-01 solver pods, which do not carry the CloudBank
application labels. This policy permits TCP 8089 only from the `ingress-nginx` controller pods
in the `ingress-nginx` namespace to pods labelled `acme.cert-manager.io/http01-solver=true`.
Both source selectors apply together; application isolation, solver egress isolation and the
application HTTPS redirect remain in force. The rule also covers subsequent certificate renewals.

If the issuer is Ready but a Challenge remains pending with a self-check timeout, inspect its
Reason, the solver pod readiness, this policy and the ingress controller labels. Confirm public
DNS resolves to the ingress address and test the exact challenge URL externally. A timeout alone
does not distinguish missing network access from DNS, ingress or load-balancer issues. Apply the
corrected policy to an existing deployment without rebuilding images or deleting the Certificate,
Order or Secret; cert-manager retries a pending self-check. Observe Certificate Ready and externally
verify trust and hostname before recording TLS success. Keep the applied policy and resulting
bounded certificate status with the deployment evidence.

- Use OpenSSL and curl from an external network to prove certificate trust, SAN equality, at least
  30 days remaining, TLS 1.2 or newer, and HTTP rejection or redirect to HTTPS.
- Confirm all ExternalSecret resources are Ready. Add a new Secret Manager version for one bounded
  synthetic value, wait for propagation, restart its workload, prove the new version is active, and
  disable the prior version. Record no value.
- Confirm Managed Prometheus metrics, Cloud Logging entries, and Cloud Trace spans for all eight
  services under one hashed correlation ID. Trigger one synthetic alert and prove it recovers.

## 4. Load and security

- Run the same 18 MS #66 business journeys through k6 for at least 300 seconds, 1,000 requests and
  concurrency 10. The gate requires zero errors and p95 latency no greater than 500 ms.
- Verify all eight image signatures and provenance statements with Cosign.
- Scan every digest with Trivy. The gate permits zero critical and zero high findings.
- Scan the rendered manifests and the live cluster configuration; prove zero critical/high findings,
  zero runtime policy violations, default deny, bounded PostgreSQL egress, and Chatbot-only model
  egress.

## 5. Backup, HA, rollout, cutover, and rollback

- Create an on-demand Cloud SQL backup and verify it. Restore/clone it into an isolated validation
  instance, run the normalized state query, and require the restored hash to equal the pre-backup
  hash. RPO must be at most 60 seconds and RTO at most 600 seconds.
- Cordon and drain one worker node, verify all eight services and business journeys, then uncordon.
  Repeat for all nodes in one failure domain. This is a controlled evacuation test, not a claim that
  Google Cloud suffered a zone outage. Require zero normalized data loss.
- Roll all eight services from baseline to separately signed candidate digests. Observe
  `maximumUnavailable=0` for every rollout and run the journeys during the change.
- Put one candidate behind the bounded canary path, then switch 100% target traffic, run all 18
  journeys, invoke the documented rollback trigger, restore the prior release, and rerun recovery.
- Complete all 28 scenario rows in a `platform-qualification-observation.schema.json` document, hash every source
  evidence item, sign the minimized observation, and admit it with the MS #67 launcher.

## 6. Evidence and teardown

- Independently run `verify-receipt` before removing infrastructure.
- Retain only signed profiles, observations, receipts, contracts, aggregate scan counts, and hashes.
- Set `LIGHTYEAR_MS67_DESTROY_ACK=DESTROY-CLOUDBANK-MS67-NON-PRODUCTION` and run `destroy.sh`.
- Verify billing-visible resources. KMS and service-networking remnants may require later manual
  cleanup; the destroy script reports this rather than claiming the project is empty.

Customer IdP integration, representative customer data volume, customer workload, the customer's
formal approval process, production deployment, and final production readiness remain MS #68.
