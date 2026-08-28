# Mainframe access campaign

## Enterprise collection appliance (MS #28)

MS #28 preserves the campaign's exact read-only parsers and graph bindings while adding an
operational envelope around collection.

| Control | Bounded behavior |
|---|---|
| Authentication | `bearer-env`, externally issued OAuth bearer, or mTLS plus bearer |
| TLS | HTTPS with TLS 1.2 minimum; mTLS requires separate certificate and key files |
| Pagination | Server continuation only; three pages per adapter; approved query keys only |
| Retry | Three attempts; bounded exponential backoff; capped `Retry-After` |
| Recovery | Content-addressed checkpoint; at most three resumes; completed work is not repeated |
| Retention | Redacted claims and digests only; seven-day checkpoint and thirty-day evidence policy |
| Faults | DNS, TLS, timeout, redirect, loop, rate limit, truncation, and checkpoint tamper |

The deterministic appliance fixture forces an interruption after page two, resumes once, and
completes three adapters over four pages after two bounded retries. The fault receipt must detect
all eight scenarios before `enterprise_mechanism_ready` can be true.

```bash
./collection-appliance.sh verify
```

For an authorized live run, provide the bearer and independent signing key through the environment.
Use `resume` with the same arguments and output directory after a bounded transport failure. For
mTLS, also set `LIGHTYEAR_MAINFRAME_CLIENT_CERTIFICATE` and
`LIGHTYEAR_MAINFRAME_CLIENT_KEY`; a private CA can be selected with
`LIGHTYEAR_MAINFRAME_CA_FILE`.

```bash
export LIGHTYEAR_MAINFRAME_BEARER='operator-supplied-value'
export LIGHTYEAR_EXTENSION_EVIDENCE_KEY='customer-owned-value-at-least-32-bytes'
./collection-appliance.sh live https://mainframe.example customer-key \
  work/customer-appliance mtls-bearer-env
./collection-appliance.sh resume https://mainframe.example customer-key \
  work/customer-appliance mtls-bearer-env
./collection-appliance.sh validate-live customer-key work/customer-appliance
```

The accepted OAuth mode consumes a bearer token issued by an external enterprise identity system;
LIGHTYEAR does not claim to implement or execute that IdP's authorization flow. Likewise, the
retention durations are enforced profile bounds, while automatic purge remains customer-operated.
No simulated appliance artifact can set `live_observed`, `mainframe_equivalent`, or
`production_ready` to true.

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
