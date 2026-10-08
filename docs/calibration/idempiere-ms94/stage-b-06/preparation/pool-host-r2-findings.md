# Host pool comparison: preserved failure and prospective decision

The saved exact JUnit classes were loaded under the host Corretto 21 JDK and observed with JDI before and after lambda linkage. No Docker, database, candidate or model ran. This is a host diagnostic, not pinned Linux runtime qualification.

The prospective interface-inherited overpass calculation reproduces HierarchicalTestEngine's 159-entry pool and `b6eb2698546644b688cf9fc195a7445dff77fea21a0de5125e5f929440e14411` pool hash in all six observations. It also reproduces AbstractTestDescriptor's semantic pool extension, but the strict declared-method check fails at both recorded stages. The complete report remains failed in [pool-proposal-host-r2.json](pool-proposal-host-r2.json).

Two AbstractTestDescriptor methods differ only in JDI's modifier representation:

| Method | Class-file flags | JDI modifiers |
|---|---:|---:|
| lambda$findByUniqueId$1 | 4106 (`0x100a`) | -268431350 (`0xf000100a`, unsigned) |
| lambda$removeFromHierarchy$0 | 4106 (`0x100a`) | -268431350 (`0xf000100a`, unsigned) |

The lower 16 bits agree. All recorded declared-method bytecode hashes agree. This establishes the discrepancy, not authority to ignore modifier bits. Native admission and the approved exact-class production comparison remain unchanged. A future proposal must specify the permitted JDI/class-file modifier mapping and negative controls; this report does not approve a mask or widen binding.

Generated-class provenance, actual runtime-closure collection, native LambdaForm verification and the five-path census remain separately gated. r10 and all earlier failures remain preserved. See [the alternative mechanism](generated-class-alternative-r2.md) for the prospective JVMTI route if the JDI time box expires. Any runtime/extraction or census requires its exact Tower decision.
