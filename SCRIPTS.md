# Entrypoint catalog

`scripts.catalog.json` is the machine-checkable source of truth for every top-level POSIX and
PowerShell entry point. `./lightyear.sh catalog` verifies that the catalog is hash-valid, that no
script is undocumented, and that every POSIX entry point has a PowerShell twin.

## Supported roles

| Role | When to use it | Release behavior |
|---|---|---|
| `aggregator` | Supported composite commands such as `lightyear` and `verify` | Delegates to named controls |
| `release-gated` | Deterministic evidence build and verification | Included in the complete verifier |
| `developer` | Interactive exploration, tests, benchmarks, and focused gauntlets | Covered by tests or dedicated CI |
| `operator` | Inputs that require a human-selected catalog or evaluation | Never started implicitly |
| `live-authorized` | Credentialed, read-only customer-system collection | Only the offline `verify` action is automatic |
| `internal` | Shared runtime helpers sourced by other scripts | Not a standalone workflow |

## Which command should I run?

- `./verify.sh` is the authoritative, complete release verifier. It fails if the pinned upstream
  fixture is absent, any receipt claim is promoted without authority, or script ownership drifts.
- `./test.sh` runs the complete Python suite and requires the pinned upstream fixture.
- `./test.sh unit-only` permits missing upstream data only after printing an explicit incomplete-run
  warning; the skipped integration tests must never be interpreted as a complete green build.
- `./lightyear.sh doctor` checks repository prerequisites and the graph toolchain.
- `./lightyear.sh catalog` checks entry-point coverage without running workloads.
- `./quality-gate.sh` and `./mainframe-access.sh live` are operator-controlled by design; they are
  not release-verifier substitutes.

See `scripts.catalog.json` for the exact purpose, role, and verification owner of all entry points.
