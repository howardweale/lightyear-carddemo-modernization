# COPAU F2 private prerequisites — 22 October 2026

Scope: the first COPAU factory run only. G3 requires a separate later request.
This additive record supersedes the assumption of "existing" private material in
the earlier F8 proposals and October 22 preparation README. It changes no old record.

## What can be pointed to today

| Item | Finding and exact public record |
| --- | --- |
| Work-order HMAC key and production ID | No provisioned COPAU key, custody record or production issuer/key ID is evidenced. No private storage path is known. |
| Defined fixture ID | `factory/execution/policy.json` lists `lightyear-release-operator` for the Python fixture policy. That string proves neither key existence nor approval for COPAU. |
| Secret input interface | `src/lightyear_execution/cli.py` and `src/lightyear_factory/cli.py` consume `LIGHTYEAR_WORK_ORDER_SIGNING_KEY`; neither provisions or persists it. Environment values were not inspected. |
| Admission requirements | `src/lightyear_execution/admission.py` requires a trusted ID and at least 32 key bytes. It does not supply a key store or production key. |
| COPAU policy IDs | `docs/factory/copau-f2-preparation-2026-10-22/request.json` has an empty `trusted_key_ids` list. The checker sentinel is parser-only and is never an admitted key. |
| COPAU private expected bundle | None is registered in the reviewed COPAU records. Its digest, byte count, value count and source are null in that request. No exact private path is known. |
| Private-bundle input interface | `--factory-private-expected-values` in `src/lightyear_factory/cli.py`; `FactoryModelAdmission.private_expected_values` in `src/lightyear_factory/model_admission.py` validates a separately supplied absolute path after signed admission. |
| New Tower | [#420](https://github.com/howardweale/lightyear-carddemo-modernization/pull/420) prepares installation only. `tools/factory_install/Install-FactoryTower.ps1` creates no keys, journal, accounts or expected bundle. |

The inspected repository metadata covers `factory/`, the COPAU input records,
execution admission and #420's installation sources. CI cannot establish absence
on Howard's private filesystem. Therefore both private prerequisites are treated
as unprovisioned for this request until Howard supplies public custody/provenance
metadata; no "existing" key or bundle is assumed. No private file, environment
value, secret store, private bundle contents or Tower endpoint was opened.

## Proposed creation plan — review before Howard performs private steps

1. Engineering prepares a separate reviewed operator helper and public metadata
   schema, tested in CI with synthetic data only. It must refuse links, overwrite,
   exposed roots and unsafe ACLs, suppress private output, and never sign or start
   a run. This document alone does not authorize installing that helper.
2. Howard checks privately whether suitable material actually exists. If it does,
   he identifies its location/custody and records only the permitted public metadata.
   Preserve it; do not replace or regenerate it to make a check pass.
3. If no suitable HMAC key exists, Howard generates at least 32 cryptographically
   random bytes privately, chooses a production issuer/key ID, and stores the secret
   with Howard/controller-only access and a private recovery copy. Proposed NEW
   location, not a claim of existence or an approved installation:
   `C:\ProgramData\Lightyear\FactoryControllerPrivate-v1\work-order-hmac.txt`.
   The CLI consumes UTF-8 bytes; a 64-character hex encoding of 32 random bytes is
   compatible. The helper must never print the secret, put it in a command line,
   transcript, Git, CI variable, artifact or candidate environment. Provision the
   existing environment interface only in the privately controlled controller
   process. Publish only issuer/key ID, algorithm, custody/ACL attestation and
   the reviewed record reference. This HMAC key is distinct from the Tower Ed25519 key.
4. If no suitable COPAU private bundle exists, Howard privately creates it using
   the reviewed helper and approved frozen judge's controller-private expected-state
   sources. Proposed NEW location, subject to separate review:
   `C:\ProgramData\Lightyear\FactoryControllerPrivate-v1\copau-expected-values.json`.
   It must stay outside the checkout, workspace, run-artifact and exposed roots.
   Do not relabel an old public evidence archive or invent arbitrary canaries as
   the private expected bundle. Retain private source/coverage provenance privately.
5. The existing bundle contract is exactly `schema` plus `values`, with schema
   `factory-private-expected-values/1`: 1–64 unique strings, each at least 40
   characters after whitespace removal and case folding; exact UTF-8 bytes total
   1–262144. Require a regular single-link file and safe, non-link ancestors.
   Howard's helper validates this privately and reports only exact byte SHA-256,
   byte count, value count and a public attestation reference. No values or
   private path enter the public F2 request, CI, model context or worker.
6. After his Friday October 23 setup, Howard publishes the NEW Tower's public PEM,
   SHA-256 of its exact bytes and current trusted journal head. Proposed #420
   locations are `C:\ProgramData\Lightyear\FactoryAuthority\authority.public.pem`
   and `factory-evidence-trust.json` in that directory; neither is asserted present
   now. No old PEM, fixture ID, private key or proof export substitutes.
7. Engineering then creates additive dated concrete policy, WorkOrder, model config,
   plan and unsigned engineering-run contract using the actual executable/source
   commits, actual workspace/image hashes and Howard's supplied public records.
   CI rechecks policy/WorkOrder round trips, source provenance, estimate arithmetic,
   exact role/model, first-run scope, window, caps and every final binding.
   Until ALL inputs and checks pass, `request_ready=false`; `run_authorized=false`
   remains separate from document readiness. Signing and running remain Howard's
   later actions under separate approval.

## Already bound public preparation

The October 22 request binds the approved model for all three roles and USD10
across billed calls, failures, retries and reasoning output. Its conservative
reservation is USD9.395056: 808192 input tokens and 200000 output tokens, eight
role invocations, no automatic retries/tools/fallback. This is an upper reservation,
not predicted use or a promise of completion. Published pricing and long-context/
regional headroom are linked in the preparation README.

The wall-clock limit is 28800 seconds. The allowed window is Friday October 30,
08:00–20:00 America/Los_Angeles, exactly 15:00 UTC October 30 through 03:00 UTC
October 31. A late start cannot extend the window; the controller must stop at
the earlier of start plus eight hours and the window end. Scope/model/cost caps
are unchanged. Public preparation and its refusal tests run only in CI.
