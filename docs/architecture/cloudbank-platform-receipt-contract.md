# Plan-bound CloudBank platform receipts

Not yet live-qualified: this is an offline, public-data judge and operator handoff
for the reference estate. No apply, cloud command, credential access, signature or
model request occurs in these modules. MS67 retained records remain unchanged.

## Inputs and ownership

The Phase A module emits `platform_infrastructure` in Terraform 1.13.3 plan JSON.
It binds the existing qualification policy and a public rendered rollout digest.
The rollout is a Kubernetes List containing the application deployments,
NetworkPolicies and ExternalSecrets, with explicit runtime UID/GID declarations.
Terraform owns infrastructure; existing controllers own rollout and drill actions.
No Secret objects or expected private answers belong in the public rollout.

`tools/cloudbank_platform_receipt.py expectations` takes the raw plan, rollout and
externally approved commit/digests. It rejects incomplete, destructive, deferred,
sensitive or unresolved required inputs. It recomputes expectations from resource
values and the bound rollout. The plan's existence does not establish provenance:
the operator must approve the exact plan and source bindings out of band.

`recipes` emits seven NOT RUN controller recipes. Context, SQL instance and secret
target arguments come from the plan. `cli_arguments` refuses overrides of those
arguments or the run action. Existing controller prerequisites, admissions,
private evidence, cleanup and no-retry guards remain in force. The recipes do not
dispatch controllers. Live execution requires the separate costed apply/drill
packet and Howard's approval; this work supplies no such approval.

| Drill | Expectations derived from code | Public observation compared by the judge |
| --- | --- | --- |
| NETWORK-ENFORCEMENT | Dataplane and rendered policy specs; default-deny directions | Actual policies and repeated negative probes bracketed by positive controls |
| RUNTIME-IDENTITY | Workload pool and each rendered service UID/GID | Live deployment identity and both pods' startup UID/GID/readiness |
| SECRET-ROTATION | Declared secret IDs, reader IAM, ExternalSecret references and refresh interval | Live mappings plus rotation, fresh replicas and restoration |
| SQL-HA | Regional/private SQL resource and instance name | Live SQL settings, standby promotion, unchanged endpoint/processes and acknowledged state |
| SQL-RECOVERY | Backup/PITR configuration and existing policy RPO/RTO | Live backup settings, measured restoration/RPO/RTO and cleanup |
| ALERT-DRILL | Monitoring/logging, telemetry roles and alert obligation | Live configuration, same alert OPEN/CLOSED and cleanup |
| SUSTAINED-LOAD | Declared service inventory and existing policy load limits | Measured duration/concurrency/requests/errors/p95 and service coverage |

The new comparison is additional to the unchanged legacy verifier. A changed
declaration cannot relax an existing drill gate. Unsupported probe scopes fail
closed. Reference-estate default-deny probes are supported; this is not a general
network-policy compiler or proof that every possible flow is covered.

## Producer boundary and signatures

Existing MS67 receipts use HMAC and are not converted into public signatures.
The operator runs the existing verifier in its authorized environment and retains
the original receipt. `observe` projects its result and fresh API readbacks into
public bytes. It requires the original receipt hash, verifier digest, controller
run ID and generated recipe hash. No expected configuration is copied into the
observation: live fields are projected independently and compared.

The operator supplies `readback.context`, `started_at`, `finished_at`, `cluster`
(GKE describe JSON), `sql` (SQL describe JSON), `kubernetes` (public List),
`secret_reader_bindings` (secret ID to role/member), and `telemetry_roles`.
Only public projections are inputs here; never supply Secret values or private
keys. Freshness and authenticity ultimately depend on the designated observer's
signature. This is an explicit human attestation boundary for legacy verification,
not independent public verification of an HMAC secret.

Howard separately reviews/signs each observation with the designated Ed25519 role.
The trust policy pins each observer key and legacy verifier digest, code key,
judge key, run/context, source/plan/rollout/policy bindings, evidence class and
offset-bearing start/expiry timestamps. Its exact file hash is an out-of-band
input, never taken from the evidence being verified. No wildcard or renewal exists.

The code envelope uses `cloudbank-code-qualification/1`: run ID, code commit,
rollout digest, verifier receipt digest, evidence class and PASS/FAIL/NOT RUN.
It is a separately signed public attestation about the code result, not a rewrite
of the original code evidence. `judge` verifies it and all supplied observations,
recomputes the seven comparisons and prepares one compound body containing the
signed code envelope and platform verdict. Howard signs that whole body externally.
`verify` authenticates the compound envelope and recomputes it from all inputs.

Envelopes use the existing `lightyear_cloud_runner.signing.verify` canonical JSON
format: `body`, `content_sha256`, and `signature` with algorithm `Ed25519`, the
SHA256 of the independently trusted public PEM as `key_id`, and base64 signature.
P256 image keys, HMAC, embedded replacement keys and unsigned receipts are rejected.
This is the public verification interface for an Aperture caller; no Aperture
deployment or integration result is claimed.

Absent observations remain NOT RUN; invalid or mismatched ones are FAIL. All
seven plus code must pass. Offline fixtures can exercise PASS logic but can never
set `live_platform_verified`. Every result keeps MS67 closeout and native/P5 false.
The CLI writes exclusively to a new file and cannot overwrite retained evidence.

## Offline acceptance

CI covers plan/rollout binding and resource drift, all seven configuration and
measurement failures, missing evidence, unknown drill IDs, wrong keys/algorithms,
expired policy, changed code/plan joins and tampered compound verdicts. Synthetic
logic tests isolate crypto with explicit mocks; a public RFC8032 verification
vector and real rejection paths exercise Ed25519 without generating/signing keys.
Live apply, operator signing and seven fresh live drills remain NOT RUN.
