# Campaign-neutral status exports

`tower-status-export/1` is the shared signed status transport for any campaign.
`lightyear_control_tower.status_export` owns writing, reading, chain verification
and freshness. It imports no B06 code. B06 is the first producer profile; its
journey rules remain in `lightyear_control_tower.b06`.

## Signed format

Every export has these fields, with no additional top-level fields:

| Field | Meaning |
|---|---|
| `schema` | `tower-status-export/1` |
| `scope`, `campaign_id`, `profile` | Scoped public identifiers; no hardcoded campaign name |
| `sequence` | Positive integer, starting at 1 |
| `previous_sha256` | Previous export's signed canonical-body `content_sha256`; 64 zeros for the first |
| `at_utc` | UTC timestamp of the state observation |
| `bindings` | Nonempty map of public artifact identifiers to SHA-256 hashes |
| `state` | `ready`, `running`, `paused`, `completed`, `stopped` or `void` |
| `active_trial` | Null, or public `id` with optional `journey` and `phase` identifiers |
| `limits`, `used` | Matching maps of named numeric budgets; used values cannot decrease |
| `fixture` | Boolean identifying test evidence |
| `details` | Profile-specific object, not exposed by the generic projection |
| `content_sha256`, `signature` | Existing Tower canonical-body hash and Ed25519 envelope |

The generic profile does not impose B06's journeys, slot counts, budget values,
calendar or trial predicates. Profile-specific consumers may add closed-schema
validation and projections. B06 puts `calendar`, `trials` and `pause` in details
and checks its full profile on every export, including unchanged prior verdicts.
Only reviewed public status belongs in exports; do not insert private values,
captures, keys or hidden work orders into a signed profile object.

## Producer and reader

```python
from lightyear_control_tower.status_export import StatusWriter, read_exports

writer = StatusWriter(export_directory, sign, producer_public_key,
                      scope="example", profile="generic")
writer.emit({
    "campaign_id": "example-campaign", "at_utc": observed_at_utc,
    "bindings": {"plan": plan_file_sha256}, "state": "running",
    "active_trial": {"id": "trial-1"}, "fixture": False,
    "limits": {"items": 100}, "used": {"items": 1}, "details": {},
})
latest = read_exports(export_directory, producer_public_key, "example-campaign",
                      {"plan": plan_file_sha256}, scope="example")
```

The writer creates a unique dot-prefixed `.pending` file in the export directory,
writes canonical JSON, flushes and fsyncs it, closes it, then **renames once** to
`000001.json`, `000002.json`, etc. The operating system must reject an existing
destination. A collision fails; it never overwrites a completed export. A writer
refuses an already populated directory. There is no restart or overwrite fallback.

Windows uses `os.rename`, whose Windows behavior refuses an existing destination.
Linux uses `renameat2(RENAME_NOREPLACE)`; macOS uses `renamex_np(RENAME_EXCL)`.
Unsupported exclusive rename fails closed. See the [Linux rename manual](https://man7.org/linux/man-pages/man2/rename.2.html)
and [Apple exclusive rename documentation](https://developer.apple.com/documentation/foundation/urlresourcekey/volumesupportsexclusiverenamingkey?language=objc).
The directory must be on one local filesystem; this is not a network-filesystem
durability or rollback guarantee.

The reader takes one directory listing, ignores dot-prefixed `.pending` files,
and reads only completed numbered exports. It verifies the trusted producer key,
signature, scope, bindings, sequence, predecessor hash and monotonic timestamps
and counters. It rejects policy changes and sequence gaps. Gaps appear in the
cockpit as unavailable with the closed issue code `export-sequence-gap`.
Neither reader nor Tower opens mutable controller state. The current reader bounds
a stream to 10,000 exports and rejects an oversized stream rather than silently
skipping history.

During an active trial, 45 minutes without a fresh export sets `stale: true`,
adds a stale alert and displays a stale campaign badge. This freshness label
does not alter the signed controller state or any verdict. Idle and terminal
campaigns are not labelled stale solely because time passes.

Verification proves the visible signed prefix. It cannot prove that a producer
has not withheld a later export; there is no claim of independent capture replay.

## Tower registry

Use a locally provisioned scope and trusted producer public key. A registry row is:

```json
{
  "id": "example-campaign",
  "scope": "example",
  "adapter": "tower-status-export",
  "producer_profile": "generic",
  "read_mode": "write-once-status",
  "export_directory": "<absolute local export directory>",
  "trusted_public_key": "<absolute local public key path>",
  "bindings": {"plan": "<64-hex plan hash>"}
}
```

B06's registration helper writes this adapter with `producer_profile: ms94-b06`.
The generic projection omits profile details; it grants no roles, consumes no
decisions and starts no processes. A campaign-specific controller remains
responsible for decision handling, admission, deadlines and cleanup.

## Verification

`tests.test_tower_status_export` runs a non-B06 producer and reader concurrently
on the actual host filesystem, including Windows CI. It also checks competing
writers cannot replace the same final filename, ignored incomplete temp files,
signature and chain tampering, gaps, scope mismatch and the exact 45-minute
stale boundary. `tests.test_b06_tower` concurrently runs the real B06 writer and
reader while the controller replaces its separate mutable file. No native
campaign, Docker operation or model call is part of these tests.

Local Windows validation passed: 70 tests passed and two existing tests skipped,
including both real writer/reader concurrency regressions. The generic stale
view and B06 cockpit passed the Chromium rehearsal. Linux and macOS exclusive
rename paths are covered by the configured CI matrix but were not executed
locally on this Windows host.
