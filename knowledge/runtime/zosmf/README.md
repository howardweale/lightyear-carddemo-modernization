# z/OSMF adapter kit

This kit lets the runtime evidence plane rehearse its mainframe connection before a system is
available. It implements the read-only IBM z/OSMF Jobs surface used by the `INTCALC` vertical
slice and maps returned JES facts to exact knowledge-graph entities.

## What is collected

| z/OSMF call | Retained evidence | Raw body policy |
|---|---|---|
| List jobs | Job name, ID, owner, status, return code, execution system | No job URL retained |
| Job status with step data | Job result, timestamps, step and program identity | Bounded metadata only |
| List spool files | DD name, step, record count, byte count | Records URL discarded |
| Get spool records | SHA-256 plus approved JCL relationship matches | Body discarded after parsing |

The v0.9 adapter is intentionally read only. It cannot submit, hold, release, cancel, purge, or
write a data set. `JESJCL`, `JESMSGLG`, and `JESYSMSG` are the only spool DD names retrieved by
default. The response limit is 1 MiB and the record request is bounded to 5,000 records.

## Rehearse without a mainframe

On macOS or Linux:

```bash
./zosmf-adapter.sh simulate
./zosmf-adapter.sh verify
```

On Windows:

```powershell
.\zosmf-adapter.ps1 simulate
.\zosmf-adapter.ps1 verify
```

The local server implements IBM-shaped Jobs, status, spool-list, and spool-record endpoints. Its
capture must remain `simulated`: it can pass `development_readiness`, but it must fail
`mainframe_equivalence`. The conformance test asserts this boundary.

## Diagnose the real connection

Keep secrets in the launching terminal. Do not put them in a file or command-line URL.

```bash
export ZOSMF_BASE_URL="https://zosmf.example.com:10443"
export ZOSMF_SYSTEM_ALIAS="SY1"
export ZOSMF_USER="IBMUSER"
export ZOSMF_PASSWORD="..."
# Optional enterprise CA and mutual-TLS identity:
export ZOSMF_CA_BUNDLE="/absolute/path/company-ca.pem"
export ZOSMF_CLIENT_CERT="/absolute/path/client-cert.pem"
export ZOSMF_CLIENT_KEY="/absolute/path/client-key.pem"

PYTHONPATH=src python3 -m lightyear_runtime zosmf-diagnose \
  --owner IBMUSER --prefix 'INTCALC*'
```

Bearer authentication is available through `ZOSMF_BEARER_TOKEN`; it is mutually exclusive with
`ZOSMF_USER`/`ZOSMF_PASSWORD`. HTTPS certificate validation is always enabled. The client does not
follow redirects, refuses credentials embedded in URLs, bounds response size and time, validates
content types, and never serializes authentication headers or secret values.

## Capture an authorized run

After confirming the job name and ID:

```bash
PYTHONPATH=src python3 -m lightyear_runtime capture-zosmf \
  --job-name INTCALC \
  --job-id JOB00001 \
  --output work/zosmf-capture/intcalc.runtime.snapshot.json.gz \
  --attest-real-zos
```

`--attest-real-zos` is a deliberate trust decision. It is accepted only for a non-loopback HTTPS
endpoint. Without it, even a remote endpoint produces `simulated` evidence. This prevents a local
mock or accidental test system from satisfying mainframe equivalence. The resulting snapshot
still needs normal policy review and comparison with the Java candidate.

## Mapping boundary

`intcalc-mapping.json` is the reviewed bridge between z/OS names and proprietary graph IDs. The
adapter only emits relationships declared there. If a step, program, or DD allocation is absent,
the corresponding required graph entity remains a policy gap. A different program is emitted as
a contradiction and blocks both acceptance policies.
