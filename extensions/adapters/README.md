# Mainframe access campaign

This campaign is the customer-access entry point for MS #21. It is deliberately read-only and
content-minimized. Its purpose is to turn three narrow remote observations into signed,
graph-addressed evidence without storing credentials or response bodies.

## Trust boundary

| Control | Enforced behavior |
|---|---|
| Transport | HTTPS only, normal certificate validation, no redirects, `GET` only |
| Credentials | Bearer value comes from `LIGHTYEAR_MAINFRAME_BEARER`; never stored |
| Evidence key | Separate value from `LIGHTYEAR_EXTENSION_EVIDENCE_KEY`; minimum 32 bytes |
| Responses | Exact content types, 64 KiB default maximum, bounded fields only |
| Retention | Raw body is SHA-256 hashed and discarded |
| Graph | Every claim must resolve against the exact canonical graph hash |
| Completion | z/OSMF, Db2, and CICS captures must all validate or the campaign fails |
| Promotion | Always `production_ready: false`; collection cannot self-authorize promotion |

The checked-in profile contains paths, bounds, source aliases, and graph entity IDs only. Do not add
passwords, tokens, authorization headers, cookies, private keys, or other secrets to it; validation
rejects credential-shaped fields.

## Endpoint contracts

The z/OSMF collector requests the Jobs status resource with `step-data=Y` and `exec-data=Y`. It
retains bounded job identity, status, return code, step name, program name, and step completion code.

The CICS collector accepts CMCI XML containing one `cicslocaltransaction` or `transaction` resource
and retains its APPLID, transaction, program, and enablement metadata. XML namespaces are accepted.

Db2 for z/OS does not expose arbitrary catalog SQL through this campaign. The configured path is a
customer-approved, read-only REST service that must return exactly this bounded projection:

```json
{
  "schema": "CARDDEMO",
  "table": "AUTHFRDS",
  "column_count": 26,
  "primary_key": ["CARD_NUM", "AUTH_TS"],
  "index_count": 1,
  "package_count": 1
}
```

The gateway or Db2 REST service owns database authentication and `SELECT` authority. LIGHTYEAR does
not send SQL text through this adapter.

## Development verification

```bash
./mainframe-access.sh verify
./mainframe-access.sh simulate work/mainframe-access-simulated
```

```powershell
.\mainframe-access.ps1 verify
.\mainframe-access.ps1 simulate -Output work\mainframe-access-simulated
```

The committed response set is simulated evidence. It proves deterministic parsing and enforcement,
not connectivity to IBM Z.

## Authorized live run

1. Copy `mainframe-access.profile.json` and replace only customer-specific paths, source alias, and
   graph entity bindings. Keep the exact three-adapter set and bounds.
2. Configure the mainframe gateway for read-only resources and a certificate trusted by the host.
3. Export the access credential and a separate evidence-signing key in the operator environment.
4. Run the campaign from an approved host and preserve the resulting directory as governed evidence.

```bash
export LIGHTYEAR_MAINFRAME_BEARER='operator-supplied-value'
export LIGHTYEAR_EXTENSION_EVIDENCE_KEY='customer-owned-value-at-least-32-bytes'
./mainframe-access.sh live https://mainframe.example customer-campaign-key work/customer-capture
```

No command-line argument contains a credential. Do not enable shell tracing during the run. A
failure emits only a bounded failure class; it does not echo the remote body or credential.

## What a passing receipt means

A passing live receipt means all three configured remote resources were observed over verified
HTTPS, each capture validated against the exact graph, and the customer evidence key signed the
content identities. It does **not** mean the entire application was discovered, behavior was proven
equivalent, nonfunctional requirements passed, or production cutover was approved.
