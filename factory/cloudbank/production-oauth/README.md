# CloudBank production OAuth boundary

MS #62 replaces the MS #60 development Basic-authentication and static internal-token shortcuts
with a live OAuth 2.0/OIDC application boundary. The isolated target runs the CloudBank
authorization server on PostgreSQL, issues RSA-signed client-credentials JWTs, and configures
Account and Transfer as issuer-, audience-, lifetime-, signature-, and scope-validating resource
servers.

The external caller receives only `cloudbank.transfer` for the `cloudbank-transfer` audience.
Transfer obtains its own `cloudbank.internal` credential for the `cloudbank-account` audience.
The caller subject remains the business actor used by Account ownership checks; the service token
does not replace or elevate that identity. A transfer is accepted only when both identities are
valid.

The native gate proves twelve paths: discovery and JWKS publication, invalid-client rejection,
scope-escalation rejection, caller and service claim bindings, missing bearer rejection,
insufficient-scope rejection, tamper rejection, audience isolation, owner rejection before
mutation, successful value conservation, and acceptance of a pre-restart caller credential after
all three Java processes restart with the same RSA key.

## Run

Use the same `LIGHTYEAR_CLOUDBANK_BASELINE_EVIDENCE_KEY` that signed the MS #61 receipt:

```bash
./cloudbank-production-oauth.sh run \
  ../cloudbank-upstream \
  work/cloudbank-oracle-equivalence/cloudbank-oracle-postgresql-equivalence.receipt.json \
  work/cloudbank-production-oauth \
  operator-id

./cloudbank-production-oauth.sh verify-receipt \
  work/cloudbank-production-oauth/cloudbank-production-oauth.receipt.json
```

The run needs Java 21, Maven, Docker, OpenSSL, and the already-pulled pinned PostgreSQL image. It
uses synthetic data and loopback-only ephemeral ports. Client secrets, access credentials, the
private signing key, and raw service logs are never written to the receipt.

The runner explicitly enables Transfer's service-token provider and pins its requested scope to
`cloudbank.internal`. The generated Transfer configuration also enables the provider in a later
`cloudbank-oauth` YAML document, after the imported `common.yaml` disabled default. An explicit
disable outside the runner fails startup because Transfer requires its own service identity.
The `TransferServiceTests` CI suite loads the real Spring application context and imported
configuration to check both provider creation and failure when the provider is disabled.

## Evidence boundary

A passing signed receipt qualifies the production-shaped OAuth application profile for the
bounded Authorization/Account/Transfer workcell. It does not prove external TLS termination,
managed-secret rotation, browser authorization-code execution, enterprise IdP federation, Checks
AQ/JMS, the remaining services, whole-application equivalence, migration completion, promotion,
or production readiness. Those remain separate governed gates.
