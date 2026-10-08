# Prospective pool and modifier comparison r3

Status: approval required; diagnostic comparison only. The production exact-class rule is unchanged. r10 and the failed r2 host report remain preserved.

For an abstract class, derive missing abstract interface methods from its byte-bound superclass/interface closure. Class-declared methods suppress inherited requirements. Maximally specific interface defaults suppress ancestor abstract declarations; ambiguous defaults fail. The original constant-pool byte prefix must remain exact. Only the semantic multiset of the derived AbstractMethodError overpass entries may follow it. Counts, references and every declared method bytecode remain exact.

One additional, narrowly scoped host metadata mapping is proposed. For AbstractTestDescriptor class SHA ae8b6f3bd6318a3b4d506b55d7f9a9abebe9cc0cae7e160caf184ce5e21c89e5, a declared method with exact class-file flags 0x100a may have JDI modifiers 0xf000100a (signed -268431350). Record both values and the method identity. Every other modifier difference fails. This is not a general high-bit mask and conveys no generated-class trust.

All eight preserved host observations compare successfully under this proposal: six HierarchicalTestEngine and two AbstractTestDescriptor observations. Report content hash: 01e68ba3204c828508c170584da813c9a13fe5800c82f86009bc16a6327bda47. These are host Corretto observations, not pinned Linux native qualification. Negative tests reject other high bits, another host class and changed pool/method content.

Approval would permit implementing this exact comparison prospectively. It would not approve a Docker window, native census, changed verdict, five-path snapshot, or measurement.
