# B06 unmatched-return r3 terminal milestone — October 10, 2026

The approved diagnostic failed on Oracle. The observer reported
`java.lang.OutOfMemoryError: Java heap space` while serializing an entry event,
through `PostingObserver.json`, `emit` and `entry`. The trace identifies the
allocation failure; it does not prove a memory leak or a complete root cause.
No repair or automatic retry is claimed.

The application worker started at 12:49:14 PM PDT. The controller recorded the
Oracle failure at 12:56:48 PM, stopped the attempt, and exited at 1:00:37 PM.
Native receipt duration is 1,319.781 seconds; group duration is 1,547.875 seconds
(25 minutes 47.875 seconds). PostgreSQL application execution never started.
The result remains `equipment-failure`, with zero model calls and zero
qualification or measurement credit. The accepted narrow empty-pending return
exception did not authorize continuing through this different anomaly.

## Preserved evidence and verification

The signed partial audit authenticates 231,158 Oracle events and the entry state.
It explicitly reports missing clock, execution and business-gate artifacts; it
makes no completed observation, provenance or full-gate claim. The failed run is
not relabelled passed merely because cleanup and prefix authentication succeeded.

| Binding | SHA-256 |
|---|---|
| Frozen snapshot | `510b33966417dc247de3a97170d06e64dfd009ea66f6807e91ad12a212ef9377` |
| Group plan | `83a92cdc0ea79d3c7408999684c68f9380400afbb2417a56dc8d2d3fa659d7fb` |
| Terminal report | `85065a01fa0ac55875b683af57ac604e8a5ca420ba7ea33eda01b27fa0f10aef` |
| Partial audit | `24801ae4fdb51a9fc2ffec26e679fe7038d81ce338d63bcfee103a3de4401a95` |
| Native receipt | `ddbd95fc637ded2f51b3054cb710d3c105b4117b625ea8486e48b8cf3e7f08c7` |
| Preserved archive | `c68672e795815139ffa2ce8f18fa3c1cbf9af254714ac0672acf7ffd97e395cd` |
| Collector failure | `8ddfc6eaa12c5dcdb72f7ce99f36c1ed0c8d4d6f64fe8abcb3b10950339b7cc8` |

After exit, read-only verification passed all 13 signed control/evidence records,
the archive digest and all 113,616 frozen file hashes. The full frozen-file check
took 128.704 seconds. The audit reports eight owned resources checked; independent
exact-owner Docker inventory found no remaining containers, networks or volumes.
The monitor is paused. Captures, archives, catalogues and class blobs remain local.

This run adds an authenticated failure prefix and a concrete observer allocation
failure to the engineering evidence. It does not add a qualified journey, business
pass, measurement result or proof that the observer is fixed. Follow-up engineering
must use fresh owners and its own authorized scope. All earlier failures, expired
windows and invalid requests remain unchanged. Operator review, not independent
attestation.
