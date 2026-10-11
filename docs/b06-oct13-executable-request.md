# B06 October 13 exact engineering technical plan

Status: **replacement r3 prepared offline, not authorized**. The full technical
plan was delivered on **2026-10-11T22:19:17Z**. The subsequently sealed unsigned
request is `107c20733d9bc7862461b6e13ba4c180cdf1dad160f51be410c5523587900f35`
(file SHA-256 `663fa537b827dbdf71be14e27cce9a5f26155dea6c19671765e7fa7f5e344fc9`).
Howard must later supply the exact
`go B06 62eafdaf29dce1d40603d38c3a394f150b98f686 107c20733d9bc7862461b6e13ba4c180cdf1dad160f51be410c5523587900f35`
line. No approval, native execution or merge to main is implied.

## Window, attempts and stopping rules

Tuesday **October 13, 2026, 9:00 AM-noon PDT** (16:00-19:00 UTC).
Exactly two consumed Oracle-only J1 retained-reference attempts, separately
invoked: **strict first**, then **diagnostic-unmatched-return, cap ten**. Every
other anomaly stops immediately. An attempt that fails is consumed; no retry,
replacement, degradation, automatic continuation, or third attempt.

Each attempt has 3,600 seconds work, 600 seconds cleanup, and a 1,800-second
candidate timeout. The first must leave both 4,200-second budgets: latest start
**9:40 AM PDT**. The second must leave one: **10:50 AM PDT**. The guards recheck
at reservation and immediately before worker/native startup. Full input/runtime
hash verification and manual inter-attempt review consume real margin. These
latest starts are mathematical ceilings, not promised launch times. Plan to
begin preflight at 9 AM. No extension is permitted.

The first evidence and actual owned cleanup must be sealed and reviewed before
a separate second invocation. Existing B06 evidence windows cannot overlap.
Six historical launch directories are bound for future read-only seal/liveness
checks; their path-list canonical digest is `1ff93bae28efdd579ee501e310fb73fbfb810ff969941c6ef8427c68a0eb2448`.
The preserved hash-only registry metadata file SHA-256 is
`feae9a1a1e0e641dadae8d9a0f699df9236673011a8c2f49232cd36110103db8`; their contents were not inspected during this preparation. Any current
Docker overlap or missing pinned image refuses after exact approval. No pulls,
configuration changes or image replacement are authorized.

## Exact implementation and evidence

- Implementation commit: `62eafdaf29dce1d40603d38c3a394f150b98f686`.
- Observer source: `6420e836dcf69eb433cfab6beafaeca237ae1f3e0dcf48a05a4b16cb92246bac`.
- Accepted baseline source: `02b2f7fd4080bfbcd821ef51147c455d7f57620eac797b809d406d73f935c64b`.
- Unchanged helper Git source: `1f3de745c960e4e9451c382705ea848859df264e8e61c52d4640b93dcac5aa0b`.
- Native template seal: `bd0ade82a34af685750eb871a56ff4869529bddceb54e1371d719a85e47218f8`.
- New private asset index seal: `19df0da05eafb6eaef950d91ae6b45094ec9835e717ddd266b105d5ec70fd518`; **111,311 files**.
- Existing engineering public-key fingerprint:
  `4ce00cfa28c13f74c12e6569b6aae010fe7e7185849accad8340c2fc367be9f0`.
- Application image:
  `sha256:554a5203449ab2d4b19089b16df5fac4e9fde3334f6762de3760f2a9d48b6268`.
- Oracle image: `sha256:f3bed005214fbaec7f580a2d27e0dffa7a868bfc913db8c231d6f2b3fe4e0300`.
- Supporting image: `sha256:96c4bda58cd8a8dfda586b2d83a2eb2a3e9f28fda0f1915d3fd758c890dc02b7`.

**Changed-source alternative:** B3.4 explicitly requires missing genuine input
witnesses to be added and revalidated. This changes B3.1's proposed unchanged
source. Howard's eventual exact go must therefore refer to this changed source;
the baseline is preserved and is not silently substituted. Later documentation
commits are publication commits. The execution checkout must be the exact
implementation above, clean, and must match every bound source/class/input/runtime
hash; no later docs HEAD can stand in for it.

All 14 compiled classes are individually bound:

| Class path | SHA-256 |
|---|---|
| `lightyear/observer/BoundedJdiMirrors.class` | `2765b6bf3b38f1beddfac6eac1eacd2804bc48f92bc262a363888dfb1f2b48bc` |
| `lightyear/observer/PostingObserver$1.class` | `e856c0fc91725bd0428f9f8bf2f6738dd4b3a67afdde2a86bce440063a615e4f` |
| `lightyear/observer/PostingObserver$Call.class` | `b67417daefe359892d05db69f9e2320e1d43c56335bc367ad0eff1817907ea71` |
| `lightyear/observer/PostingObserver$DefinitionIndex$1.class` | `d0be0c08a4c10a0da516724c3c11ccd3c25f273a7c7947243659dbe442b35b79` |
| `lightyear/observer/PostingObserver$DefinitionIndex.class` | `eae23423f17251c26cff23a8debf61620a64b6fef9377587893bf930d125e39a` |
| `lightyear/observer/PostingObserver$DiagnosticDictionary.class` | `9eeb1b0a00ba6d25cf5d60c33d57f396677c8b2102a415a501653a28cdcc05d2` |
| `lightyear/observer/PostingObserver$Generation$ReturnArm.class` | `52b245343a0232d4135bc40fbfc5545137abe436c07c1985a83297aa4b58a223` |
| `lightyear/observer/PostingObserver$Generation.class` | `47224a9057a05cccddac5ad08066ae82c3afd76e3c10365f6d45a2434c7fd0f6` |
| `lightyear/observer/PostingObserver$GenerationCatch.class` | `cb0cc55be05b55cf9ca2e7678c331dc300f6d8e20071a3f3e3d7a3ad0ff8996c` |
| `lightyear/observer/PostingObserver$PendingEntry.class` | `7f7d25dfb69dcfe93078d338c4cf0f1bdc71c54972c44c321c2c987329018f31` |
| `lightyear/observer/PostingObserver$PendingPool.class` | `a3cd895fad478289564d1aa91cba6cacafc34a3bd317eea153a2a18583fd4980` |
| `lightyear/observer/PostingObserver$PendingSnapshot.class` | `135300ca4fdcad33c182f76596bc2af748b3f0d0bea8dc264da37c9afeb449ff` |
| `lightyear/observer/PostingObserver$PendingWitness.class` | `9fecb8c779b4a4e81c9cafed69719e8df04aeff2de41a2f6aa3d294d35c15a17` |
| `lightyear/observer/PostingObserver.class` | `d9292e3b389e0d73aa7aa2c1925f84f19e15f2503c78cb49bddce2dd22d79330` |

The host helper compilation source used CRLF; its bound Git blob uses LF. The
asset preparation proved that this is the only byte transformation and separately
verified its exact compiled class hash. The original assets and both interim
copies remain untouched. Private inputs, catalogue/blob paths and captures stay
local; only hashes/counts are published.

## Authenticated execution boundaries

The reviewed Python-only correction binds the entire deterministic prepared
plan to a signed supervisor handoff: owner, request, consumed attempt number,
mode, implementation, asset index and plan hash. A changed-and-resealed Oracle
image or carrier image refuses before the worker opens its signing key. Native
preparation repeats complete asset/template and input verification, compares the
actual in-memory plan, and freshly checks remaining time before Docker. The
application boundary uses the reserved attempt's exact limits; CPU and memory
remain fixed while only the authorized second-attempt evidence caps expand.

Advancing to attempt two and releasing the lease require public-key authentication
of the previous terminal, cleanup and artifact inventory; owner/request/mode/
attempt bindings, every artifact hash and actual-absence cleanup assertion must
agree. A failed attempt remains consumed, and tampering keeps continuation closed.

The superseded unapproved request `bd53f4ccc4baa48e473e596d484429b62a2f3d7586b8ef549e05ae7a80e11de0`
was delivered at 2026-10-11T21:58:38Z but never approved or executed. It remains
preserved with its previous assets. That delivery timestamp does not apply to
this replacement. The observer and all 14 compiled classes did not change for
these Python boundary fixes, so the exact host memory proof remains applicable.

The new asset copy verified **111,311 files and 872 source files** in 182.281
seconds. A previous complete read-only template verification took 75 seconds.
Complete hashing repeats at preflight, prepared-plan construction, worker
admission and native preparation; prior-evidence verification also consumes
margin. None of those costs is excluded from deadline guards or promised to fit
a native 37,000-entry collection within 60 minutes. **78 focused regressions**
passed, including ephemeral-key tampering and mock-Docker application boundaries.

## Resource limits

| Limit | Attempt 1: strict | Attempt 2: diagnostic |
|---|---:|---:|
| Ordinary evidence records | 50,000 | 150,000 |
| Metadata records | 500,000 | 1,500,000 |
| Metadata bytes | 128 MiB | 384 MiB |
| Accepted unmatched returns | 0 | 10 |
| Java heap / observer container | 1,536 / 2,048 MiB | same |
| Heap guard | 85% | 85% |
| Private output stop / minimum free disk | 8 GiB / 60 GiB | same |
| Pending entries / definition-index slots / cache entries | 512 / 262,144 / 256 | same |

Oracle has 6 GiB / 2 CPUs; carrier and application each 8 GiB / 4 CPUs;
observer 2 GiB / 1 CPU. Heap telemetry is emitted every 1,000 events. The fixed
index, bounded pending pool, `SoftRefLRUPolicyMSPerMB=0`, owned private state,
85% guard, phase markers and heap-dump path remain bound. The version-pinned JDI
adapter refuses unsupported runtime bytes. Qualification and measurement credit
are zero; model calls are zero. The engineering key cannot admit qualification
evidence even if labels are changed.

## Memory and witness proof

The first witness host run remains **failed**: positive slope 0.175978 bytes per
emitted record, 95% interval [0.032609, 0.319348]. It completed without OOM but
did not satisfy the unchanged flatness rule.

The corrected descriptor preserves the same identity fields without unnecessary
class-definition lookups. The new named same r6 workload passed at 192 MiB:
**40,985 generation entries / 517,283 emitted records**, no OOM,
1195.937 seconds, peak after-GC heap 6,170,168 bytes.
Slope **-0.076915 bytes per emitted record**, 95% interval
**[-0.227845, 0.074015]**, using the same 50,000-record warmup and Newey-West
method. Complete output hashes and every witness were verified.

All 40,985 witnesses are present: 12,608 application-derived inputs, 25,374
bootstrap-only captured-input candidates, 3,003 explicitly unresolved bytecode
inputs. Caller stacks are not inputs. Bootstrap candidates do not prove image
independence. The gate requires this exact source/class-bound memory evidence;
a failed memory gate refuses even with exact-go text. Host success is not a
native pass or proof of why JDI missed the earlier entry.

## Projection to 37,000 generation entries

The authenticated historical prefix contains 12,396 generation entries. The
projection retains all its old audit rows in the compression estimate and adds
all current host metadata as a conservative allowance. At 37,000 it estimates:

- 98,265 ordinary records;
- 984,688 metadata records;
- 179.35 MiB metadata;
- 5.11 GiB private output;
- 219.4 pending entries, using the maximum host observation.

Projected stopping points in **generation entries**, by each independent cap:

| Resource cap | Strict attempt 1 | Diagnostic attempt 2 |
|---|---:|---:|
| Ordinary evidence records | 18,826 | 56,480 |
| Metadata records | 18,787 | 56,363 |
| Metadata bytes | 26,406 | 79,219 |
| Private output | 78,038 | 78,038 |
| Pending entries | 86,355 | 86,355 |

Attempt two's first projected resource stop is about
**56,363 entries**. This is a linear scenario, not a worst-case or
confidence bound. **Native time to 37,000 within 60 minutes is unproven.** The
strict refusal, ten-return cap, future payload tails or actual resource guards
may stop earlier. Non-stream capture/log overhead is unmeasured; a 1 GiB scenario
reserve is included, plus 1,536 MiB heap dump and 12 MiB index. An automatic
approval review blocked a historical directory-size read; it was not retried
indirectly. The separately approved manifest-bound asset copy is complete.

## Preregistered cause criteria and report

**(a)** At the first unmatched-return sequence, lifecycle/class-prepare evidence
explains the missed entry through a disabled request, class redefinition/reload,
or thread-filter mismatch.

**(b)** An application-phase marker ties the approximately 12,400-generation
point to one operation and reproduces in both attempts.

If neither criterion is supported, report **cause not identified**, stop observer
repair, and have Howard choose an alternative. A complete diagnostic collection
is never a qualified pass. The report template records exact supporting sequence
and record hashes, both attempt outcomes, witness counts, telemetry, guard/dump
hashes and actual cleanup. It begins with no native outcome or cause claim.

This is operator review, not independent attestation. No native run, Docker call,
model call, key operation, signing, machine change or approval has occurred in
this preparation. Howard's commit-specific merge approval remains separate.

The complete [technical bindings JSON](calibration/idempiere-ms94/stage-b-06/preparation/engineering-oct13-r3/technical-plan.json)
has content seal `20c368edcec03c2dd0dfa6c5a0347cc0e079c1ba7769e0cc36c659601367ad87`.
That immutable technical record was assembled before delivery and preserves its
then-pending fields. The later [unsigned request summary](calibration/idempiere-ms94/stage-b-06/preparation/engineering-oct13-r3/request-summary.json)
records the actual delivery and request seal; it grants no approval.
