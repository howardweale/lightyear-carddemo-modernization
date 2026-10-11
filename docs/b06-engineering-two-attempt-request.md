# B06 two-attempt engineering request — prepared, not authorized

Prepared for Howard on 2026-10-11T16:16:37.2253714Z. Proposed calendar: **October 12, 2026,
9:00 AM–noon PDT (16:00–19:00 UTC)**. This is a proposal; the October 11 hold
remains in force. No Docker, native application or model call has been made.

## Exact review bindings

- Request content seal: `00a037b87f50305928718d3b5282e7692d4e0d883214942750779de31cb4e3d4`.
- Exact implementation commit: `3080de6a5483bcffb8275451123cdc0172e1c82e`. Any later documentation commit is a
  publication commit, not a replacement runtime implementation.
- Observer Java SHA-256: `02b2f7fd4080bfbcd821ef51147c455d7f57620eac797b809d406d73f935c64b`.
- JDI helper SHA-256: `1f3de745c960e4e9451c382705ea848859df264e8e61c52d4640b93dcac5aa0b`.
- Native template seal: `b2be5fd81163f3b8c98dce79a755036074a271e5fe3dd1c342928272c1dc34cc`.
- Private asset index seal: `94e57ee681bc70d12cbfce9e6ba03352ca647d2f7f0914129719e1b3fb6c4f77`; 111291
  verified bound files, 852 public source files,
  14 compiled observer classes. No old native outputs are copied.
- Engineering public-key fingerprint:
  `4ce00cfa28c13f74c12e6569b6aae010fe7e7185849accad8340c2fc367be9f0`.
- Retained application image:
  `sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`.
- Oracle image: `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
- Supporting image: `sha256:96c4bda58cd8a8dfda586b2d83a2eb2a3e9f28fda0f1915d3fd758c890dc02b7`.

The [public request summary](calibration/idempiere-ms94/stage-b-06/preparation/engineering-bounded-r1/request-summary.json)
contains every public numeric/hash binding. The exact unsigned request with
local operational paths is retained at `work/b06-engineering-proposal-r1/request.json`.
Private inputs, captures and catalogue/class blobs are not published.

## Sequence and limits

Exactly two consumed attempts, Oracle-only J1 retained reference:

1. **Strict.** Stop at the first anomaly. Capture lifecycle/class-prepare and
   application-phase context around the historical 12,400 generation-entry point.
2. **Diagnostic-unmatched-return.** Accept only the existing narrowly defined
   empty-pending/matching-live-top exception, up to ten occurrences. Every other
   anomaly stops; the eleventh accepted-return request stops. Capture what follows
   the cluster, with heap telemetry, guard receipt and OOM dump if triggered.

Each attempt has 3,600 seconds work plus 600 seconds cleanup and a 1,800-second
candidate timeout. First start must leave both 4,200-second budgets (latest
9:40 AM PDT); second start must leave 4,200 seconds (latest 10:50 AM PDT).
The guard rechecks at reservation and immediately before worker/native startup.
Those are mathematical ceilings; sealing and manual review consume margin.
Attempt two is a separate invocation after the first evidence and cleanup are
sealed and reviewed. A failed attempt is consumed. No replacement, retry,
automatic continuation or third attempt is authorized.

| Resource | Bound |
| --- | --- |
| Observer Java / container | 1,536 MiB / 2,048 MiB; 1 CPU |
| Oracle | 6,144 MiB; 2 CPUs |
| Carrier and application, each | 8,192 MiB; 4 CPUs |
| Heap telemetry / guard | Every 1,000 events / 85% heap |
| Pending activations | 512 preallocated slots; exhaustion stops |
| Definition index / heap cache | 262,144 disk slots / 256 cached definitions |
| Structural audit and other diagnostic metadata | 500,000 records and 128 MiB combined |
| Ordinary evidence | 50,000 records |
| Private output / minimum free space | 8 GiB stop / 60 GiB required |
| Model calls / qualification / measurement credit | Zero / zero / zero |

No J1/B06 evidence-window overlap is permitted. Six previously started native
launch directories have report/exit markers bound in the local registry; failed
unstarted windows remain preserved separately. Fresh liveness, no-overlap,
image and approval checks remain necessary before any future authorized start.
No Docker inventory was performed to prepare this request.

## Hold and required decision

Howard may approve or decline the proposed two-attempt scope. **This request is
unsigned and `approved: false`; it does not lift the hold.** The current
implementation intentionally refuses execution at every entry point, even if a
caller alters a JSON approval flag. A hold-release code change would create a
new implementation commit and must receive fresh exact bindings and Howard's
explicit approval before execution. No approval can silently substitute that
new commit for the implementation reviewed here.

The complete request must be delivered at least four hours before the proposed
9:00 AM start. Approval after the deadline does not extend the window. All
historical failures stay failed; engineering signatures cannot enter
qualification admission even if labels or paths are changed.

After these two attempts, report phase/lifecycle context, the initiating cause
if identified, heap/guard/OOM evidence and how far attempt two progressed. If the
cause remains unresolved, stop observer repair and present the measured
alternatives for Howard's decision. No further repair attempt is automatic.

## Compiled observer SHA-256 values

| Class | SHA-256 |
| --- | --- |
| `lightyear/observer/BoundedJdiMirrors.class` | `2765b6bf3b38f1beddfac6eac1eacd2804bc48f92bc262a363888dfb1f2b48bc` |
| `lightyear/observer/PostingObserver$1.class` | `6914be007436b9dd5188c7c2b2ed95ed99f054c9f34b9f3a98d55409bbe23ece` |
| `lightyear/observer/PostingObserver$Call.class` | `50689fec3132a0f975b60f8065a60ba955b6c68033155b56152018e213f9e13d` |
| `lightyear/observer/PostingObserver$DefinitionIndex$1.class` | `ea6a38f195f6796e2abee7ee170a56a61aa04889ac56340795fb14654b001f8f` |
| `lightyear/observer/PostingObserver$DefinitionIndex.class` | `2c61b4389c03088434de11e95652565561087b51bddb78be13cf59a1c9a23ef6` |
| `lightyear/observer/PostingObserver$DiagnosticDictionary.class` | `f1fd7d7efbd07c09819915625d1ec1b1c355d9783a7fd6a5acfafe08c3fcaa9d` |
| `lightyear/observer/PostingObserver$Generation$ReturnArm.class` | `c1541187c1aed2c1992c0148a5083f827b1fd05bc34949e82fb7fa053d504ccd` |
| `lightyear/observer/PostingObserver$Generation.class` | `f697eea093e754b3a3b5fa409e1db523102cbebf886f77555e4ca91b90fcc2ae` |
| `lightyear/observer/PostingObserver$GenerationCatch.class` | `56a9ab512ec6ebfa05c98d856c85fd7e153a29ed8b7379b6d592d03eca2b761c` |
| `lightyear/observer/PostingObserver$PendingEntry.class` | `4e15f36979ecbc3572375d1d878d3db11eac40271a719bc038f5e7fbbba8d5cb` |
| `lightyear/observer/PostingObserver$PendingPool.class` | `c0b49a1926e17226ea7f378be7cd5ddcde4246ddd83e040e145e89f024b04fc5` |
| `lightyear/observer/PostingObserver$PendingSnapshot.class` | `ae4581e26fca894bf4d1751da6c17a69b288889098365b0482dedbb9f7a2926e` |
| `lightyear/observer/PostingObserver$PendingWitness.class` | `b35b96aa3821f978d5d501c164a69b00dc9d311e81688a0de5f7a21be89d54e5` |
| `lightyear/observer/PostingObserver.class` | `abb1fcef2620e63dde6f2a7d12592b76dc8bce5173affa6bf47804de7126d253` |

This is operator review of offline preparation, not independent attestation or
native proof. Final-head green CI and commit-specific merge approval remain
separate requirements.
