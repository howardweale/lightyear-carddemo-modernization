# Oracle 26ai / AlloyDB NUMBER pilot — 17 September 2026

The final run, `number-fdaa176106914350aa5659c93aab0eaa`, is **passed-bounded-native**: 20 Oracle observations, 20 AlloyDB observations, 20 comparisons and 20 equivalent pairs covering five NUMBER behaviours. Its signed terminal summary confirms the temporary VM and firewall were deleted and AlloyDB was stopped.

The observed source was Oracle AI Database 26ai Free `23.26.3.0.0`, container `FREEPDB1`, using the official image digest bound in the authorization. The target was the existing AlloyDB PostgreSQL `16.13` primary in `lightyear-ms67-nonproduction/us-west1`. The source image, SQL hashes, implementation hashes, resource scope, runtime and estimated budget are part of the signed authorization.

Raw error codes remain different: Oracle `-1438` and PostgreSQL `22003` match only through the approved numeric-precision-overflow mapping. Target SQL explicitly supplies decimal-separator formatting. Values, nulls, independent expectations and comparison results are preserved in the journal. An unknown source isolation level remains null.

## Retained attempts and cleanup

Five earlier attempts failed before any case observation was admitted. Their original signed authorizations, journals and terminal summaries are included. They exposed Windows SSH stdin handling, Oracle SID selection, an unsupported Oracle metadata parameter, managed endpoint/server-address differences, and container-scoped output setup. The fixes are in the PR history; the case expectations and comparator were not weakened.

The oldest attempt originally ended `cleanup-required`. Its separate signed recovery confirms later cleanup without rewriting that original verdict. Every attempt has confirmed cleanup. Failed attempts contribute no equivalent pairs.

## Cost and scope

The user authorized a cumulative **$10 estimated incremental budget**. Authorization-to-terminal/recovery time for all six attempts, multiplied by the authorized **$2/hour planning allowance**, totals **$2.40**. This is an elapsed-time estimate, not a GCP billing measurement or guaranteed cap; existing storage and backup charges remain outside it.

This result establishes bounded NUMBER equivalence under the approved transformation. It does not establish 1,000-case coverage, full Oracle compatibility, application equivalence, production readiness or full platform qualification. It is not automatically admitted into the separate native-catalog coverage gate, whose evidence contract differs.

## Verify without cloud access

From the repository root with the Control Tower signing dependencies installed:

```powershell
$env:PYTHONPATH = "src"
py -3.12 -m unittest discover -s tests -p test_paired_campaign_export.py -v
```

The test verifies every exported file hash, Ed25519 authorizations/events/summaries/recovery, journal sequence and hash links, terminal counts and cleanup, then replays the comparisons. It makes no cloud calls. Dedicated signing CI runs it on Linux, macOS and Windows.

`manifest.json` identifies the successful run, export revision and exact artifact hashes. The execution implementation is retained at revision `06cfb059a7548c87c63fc91e5b3bffcd456bf47d`; preserve that revision for historical replay if future contracts change. Git attributes retain the original export bytes on every platform.

The public key's SHA-256 fingerprint is `36fdf4766568b1880c1bddef92f450c6a41279d01ff11c0abd6f78e2215c6552`. These signatures establish integrity under the local operator authority, not independent vendor attestation. The actor is explicitly **Codex acting on user authorization**. No private key, operator credential or database password is exported.

The [operator guide](../../control-tower-campaigns.md) explains authorization, live observation, history, spending limits and interruption recovery.
